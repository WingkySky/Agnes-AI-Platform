/* =====================================================
 * 快捷生成面板
 * - 输入 prompt 触发生成
 * - 选择生成类型（图片/视频）
 * - 任务 9：流程落地 —— 接入后端 /api/images/tasks 真实生成
 *   · 点击生成 → createImageTask 拿 task_id → 写入自身 content.task_id
 *   · 启动轮询 getImageTaskStatus，完成后把 imageUrl 写回 content
 *   · 通过 emit('produced', { imageUrl }) 通知父节点 BaseNode
 *     由 BaseNode 调 store.propagateResultToDownstream 回填下游 ImagePanel
 * - 任务 9 扩展：支持图生图 / 多输入合并
 *   · 生成前调 store.collectUpstreamInputs 收集上游面板的图和文本
 *   · 上游图 → 作为参考图传给 createImageTask（image_urls 字段）
 *   · 上游文本 → 拼接到本地 prompt 末尾（用换行分隔）
 *   · 无上游图时走文生图，有上游图时自动走图生图
 * - 当前仅支持图片生成（视频生成走 VideoPanel）
 * ===================================================== */

<template>
  <div class="quick-gen-panel">
    <el-input
      v-model="prompt"
      type="textarea"
      :rows="3"
      :placeholder="t('canvas.enterPrompt')"
      resize="none"
    />
    <div class="gen-type-selector">
      <el-radio-group v-model="genType">
        <el-radio-button value="image">{{ t('canvas.genTypeImage') }}</el-radio-button>
        <el-radio-button value="video">{{ t('canvas.genTypeVideo') }}</el-radio-button>
      </el-radio-group>
    </div>
    <!-- 上游输入预览：让用户感知到参考图/文本已被收集 -->
    <div v-if="upstreamSummary" class="upstream-summary">
      <span class="upstream-label">{{ t('canvas.upstreamInputs', '上游输入') }}:</span>
      <span class="upstream-content">{{ upstreamSummary }}</span>
    </div>
    <el-button
      type="primary"
      size="small"
      class="gen-btn"
      :loading="generating"
      :disabled="genType !== 'image'"
      @click="handleGenerate"
    >
      {{ generating ? t('canvas.generating', '生成中...') : t('canvas.generate') }}
    </el-button>
    <!-- 任务状态行：展示当前 task 状态，便于用户感知流程 -->
    <div v-if="statusText" class="status-line" :class="statusClass">{{ statusText }}</div>
  </div>
</template>

<script setup>
import { ref, computed, onBeforeUnmount, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useI18n } from '@/i18n'
import { useCanvasStore } from '@/stores/canvas'
import { createImageTask, getImageTaskStatus } from '@/api/images'

const { t } = useI18n()
const store = useCanvasStore()

const props = defineProps({
  panel: { type: Object, required: true },
})

const emit = defineEmits(['update', 'produced'])

const prompt = ref(props.panel.content?.prompt ?? '')
const genType = ref(props.panel.content?.genType ?? 'image')
const generating = ref(false)
// 任务状态：'idle' | 'pending' | 'success' | 'failed' | 'cancelled'
const taskStatus = ref(props.panel.content?.taskStatus ?? 'idle')
const errorMsg = ref('')

// 轮询句柄
let pollTimer = null
// 轮询间隔（ms）：图片生成通常 10~30s，2s 一次足够
const POLL_INTERVAL = 2000
// 最大轮询次数（约 5 分钟超时）
const MAX_POLL_COUNT = 150

/** 上游输入预览文案：实时反映当前面板连了哪些上游产出 */
const upstreamInputs = computed(() => store.collectUpstreamInputs(props.panel.id))
const upstreamSummary = computed(() => {
  const imgs = upstreamInputs.value.images.length
  const texts = upstreamInputs.value.texts.length
  if (imgs === 0 && texts === 0) return ''
  const parts = []
  if (imgs > 0) parts.push(`${imgs} 张图`)
  if (texts > 0) parts.push(`${texts} 段文本`)
  return parts.join(' + ')
})

const statusText = computed(() => {
  switch (taskStatus.value) {
    case 'pending': return t('canvas.generating', '生成中...')
    case 'success': return t('canvas.genSuccess', '生成完成')
    case 'failed': return t('canvas.genFailed', '生成失败') + (errorMsg.value ? `：${errorMsg.value}` : '')
    case 'cancelled': return t('canvas.genCancelled', '已取消')
    default: return ''
  }
})
const statusClass = computed(() => ({
  'is-pending': taskStatus.value === 'pending',
  'is-success': taskStatus.value === 'success',
  'is-failed': taskStatus.value === 'failed',
}))

/** 把当前状态同步回 panel.content（持久化 + 给 BaseNode 监听） */
function syncToContent(extra = {}) {
  emit('update', {
    content: {
      ...(props.panel.content || {}),
      prompt: prompt.value,
      genType: genType.value,
      taskStatus: taskStatus.value,
      ...extra,
    },
  })
}

/**
 * 触发生成：调后端创建异步任务，拿到 task_id 后启动轮询
 * - 先调 store.collectUpstreamInputs 收集上游图/文本
 * - 上游图 → image_urls 参数（图生图）
 * - 上游文本 + 本地 prompt → 拼接为最终 prompt
 * - 无上游图时走文生图
 */
async function handleGenerate() {
  if (!prompt.value.trim() && upstreamInputs.value.texts.length === 0) {
    ElMessage.warning(t('canvas.enterPrompt'))
    return
  }
  if (genType.value !== 'image') {
    ElMessage.info(t('canvas.videoNotSupportedHere', '视频生成请使用视频面板'))
    return
  }

  // 取消上一次未完成的轮询
  stopPolling()
  errorMsg.value = ''
  generating.value = true
  taskStatus.value = 'pending'
  syncToContent({ imageUrl: null, task_id: null })

  try {
    // 收集上游输入
    const inputs = store.collectUpstreamInputs(props.panel.id)
    // 拼接 prompt：本地 prompt + 上游文本（换行分隔）
    const promptParts = [prompt.value.trim()]
    for (const txt of inputs.texts) {
      if (txt && !promptParts.includes(txt)) promptParts.push(txt)
    }
    const finalPrompt = promptParts.filter(Boolean).join('\n')
    if (!finalPrompt) {
      throw new Error('提示词为空')
    }

    // 构造请求参数
    const reqParams = {
      prompt: finalPrompt,
      model: 'agnes-image-2.1-flash',
      size: '1024x1024',
      response_format: 'url',
    }
    // 有上游图 → 图生图模式
    if (inputs.images.length > 0) {
      // 后端按是否 http 开头区分 url / base64，这里统一传 image_urls
      // （后端 all_reference_images 会合并 image_urls 和 base64_images）
      reqParams.image_urls = inputs.images
      reqParams.mode = 'image2image'
    }

    const resp = await createImageTask(reqParams)
    const taskId = resp?.task_id || resp?.id
    if (!taskId) {
      throw new Error('后端未返回 task_id')
    }
    syncToContent({ task_id: taskId, imageUrl: null })
    startPolling(taskId)
  } catch (err) {
    generating.value = false
    taskStatus.value = 'failed'
    errorMsg.value = err?.message || '创建任务失败'
    syncToContent({ task_id: null, imageUrl: null })
  }
}

/** 启动轮询：每 POLL_INTERVAL 查一次状态，成功/失败/超时终止 */
function startPolling(taskId) {
  let count = 0
  stopPolling()
  pollTimer = setInterval(async () => {
    count++
    if (count > MAX_POLL_COUNT) {
      stopPolling()
      generating.value = false
      taskStatus.value = 'failed'
      errorMsg.value = '轮询超时'
      syncToContent({})
      return
    }
    try {
      const st = await getImageTaskStatus(taskId)
      const status = String(st?.status || '').toLowerCase()
      // 成功：取 url 并回填
      if (status === 'success' || status === 'succeeded' || status === 'completed') {
        stopPolling()
        generating.value = false
        const imageUrl = st?.result_url || st?.url
        if (!imageUrl) {
          taskStatus.value = 'failed'
          errorMsg.value = '后端未返回图片地址'
          syncToContent({})
          return
        }
        taskStatus.value = 'success'
        syncToContent({ imageUrl, task_id: taskId })
        // 通知父节点：产出就绪，由 BaseNode 触发下游回填
        emit('produced', { imageUrl, sourcePanelId: props.panel.id })
        ElMessage.success(t('canvas.genSuccess', '生成完成'))
        return
      }
      // 失败
      if (status === 'failed' || status === 'error' || status === 'cancelled') {
        stopPolling()
        generating.value = false
        taskStatus.value = status === 'cancelled' ? 'cancelled' : 'failed'
        errorMsg.value = st?.message || st?.error || ''
        syncToContent({})
        return
      }
      // 其它（pending/processing/running）继续轮询
    } catch (err) {
      // 单次查询失败不立即终止，继续重试直到超时
      // eslint-disable-next-line no-console
      console.warn('[QuickGenerate] 轮询失败，将继续重试：', err?.message)
    }
  }, POLL_INTERVAL)
}

/** 停止轮询 */
function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

// 外部 prompt 变化时同步本地（例如右键编辑弹窗改了 prompt）
watch(
  () => props.panel.content?.prompt,
  (v) => {
    if (typeof v === 'string' && v !== prompt.value) prompt.value = v
  },
)

onBeforeUnmount(() => {
  stopPolling()
})
</script>

<style scoped>
.quick-gen-panel {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.gen-type-selector {
  display: flex;
  justify-content: center;
}

.gen-btn {
  width: 100%;
}

/* 上游输入预览：弱化样式，让用户知道参考图/文本已被收集 */
.upstream-summary {
  font-size: 11px;
  padding: 4px 8px;
  border-radius: 4px;
  background: var(--canvas-panel-bg, rgba(255,255,255,0.05));
  border: 1px solid var(--canvas-node-border, rgba(255,255,255,0.1));
  color: var(--canvas-node-muted-text, #6b84aa);
  display: flex;
  gap: 4px;
  align-items: center;
}
.upstream-label {
  flex-shrink: 0;
  opacity: 0.7;
}
.upstream-content {
  color: var(--canvas-connection-active, #50a0ff);
  font-weight: 500;
}

/* 任务状态行：弱化样式，融入面板 */
.status-line {
  font-size: 12px;
  text-align: center;
  padding: 2px 0;
  color: var(--canvas-node-muted-text, #6b84aa);
}
.status-line.is-pending { color: var(--canvas-connection-active, #50a0ff); }
.status-line.is-success { color: #67c23a; }
.status-line.is-failed  { color: #f56c6c; }
</style>

