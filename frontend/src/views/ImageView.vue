<!-- =====================================================
     图片生成视图 ImageView（已接入全局任务队列 Store）
     模式：
       - 文生图 (text2image)
       - 图生图 (image2image)
     - 所有 UI 文案通过 i18n.t() 调用实现多语言
     ===================================================== -->

<template>
  <div class="image-view">
    <h2 class="page-title">{{ t('view.imageTitle') }}</h2>
    <p class="page-desc">{{ t('view.imageDesc') }}</p>

    <el-row :gutter="24">
      <!-- 左侧：参数区 -->
      <el-col :xs="24" :md="11">
        <el-card shadow="never">
          <template #header>
          <div class="card-header">
            <span>{{ t('params.title') }}</span>
          </div>
          </template>

          <!-- 模式切换：图标 + 标题 + 短副标签 -->
          <el-tabs v-model="mode" class="mode-tabs">
              <el-tab-pane name="text2image">
                <template #label>
                  <span class="mode-label">
                    <el-icon class="mode-icon"><Edit /></el-icon>
                    <span class="mode-text">
                      <span class="mode-title">{{ t('params.mode.text2image') }}</span>
                      <span class="mode-sub">{{ t('params.mode.textOnly') }}</span>
                    </span>
                  </span>
                </template>
              </el-tab-pane>
              <el-tab-pane name="image2image">
                <template #label>
                  <span class="mode-label">
                    <el-icon class="mode-icon"><PictureFilled /></el-icon>
                    <span class="mode-text">
                      <span class="mode-title">{{ t('params.mode.image2image') }}</span>
                      <span class="mode-sub">{{ t('params.mode.imageOnly') }}</span>
                    </span>
                  </span>
                </template>
              </el-tab-pane>
          </el-tabs>

          <!-- 图生图时的上传区 -->
          <ImageUploader
            v-if="mode === 'image2image'"
            :optional="false"
            @change="handleImageChange"
            @clear="handleImageClear"
          />

          <!-- Prompt 输入 -->
          <el-form label-position="top" class="param-form">
            <el-form-item :label="t('params.prompt')">
              <el-input
              v-model="prompt"
              type="textarea"
              :rows="4"
              :placeholder="t('params.promptPlaceholder')"
              maxlength="20000"
              show-word-limit
            />
              <div :class="['prompt-length-hint', promptLengthLevel]">
                <el-icon><InfoFilled /></el-icon>
                <span>{{ promptLengthText }}</span>
              </div>
            </el-form-item>

            <!-- 预设风格 -->
            <PromptTemplates
              :templates="imageTemplates"
              @select="appendStylePrompt"
            />

            <!-- 紧凑参数选择：尺寸 + 模型，一行标签搞定 -->
            <el-form-item :label="t('params.size')">
              <ParamSelector mode="image" v-model:size="size" v-model:model="model" />
            </el-form-item>

            <!-- 生成按钮 -->
            <el-button
              type="primary"
              size="large"
              class="generate-btn"
              :disabled="!canSubmit"
              @click="handleGenerate">
              <el-icon><MagicStick /></el-icon>
              <span>{{ t('generate.imageBtn') }}</span>
            </el-button>

            <!-- 分享到广场开关：提交时携带 is_public 参数 -->
            <div class="share-toggle">
              <el-icon class="share-icon"><Share /></el-icon>
              <span class="share-label">{{ t('plaza.shareToPlaza') }}</span>
              <el-switch v-model="shareToPlaza" size="small" />
            </div>

            <!-- 积分扣除提示：显示本次生成预估消耗的积分 -->
            <div v-if="userStore.credits > 0" class="cost-hint">
              <span v-if="costLoading" class="cost-loading">{{ t('generate.costLoading') }}</span>
              <span v-else-if="cost !== null" :class="['cost-value', { insufficient: costInsufficient }]">
                {{ t('generate.costHint').replace('{n}', String(cost)) }}
              </span>
            </div>

            <!-- 积分不足提示：禁用生成按钮时引导用户充值 -->
            <div v-if="userStore.credits <= 0" class="no-credits-hint">
              {{ t('generate.noCreditsImage') }}
            </div>

            <div class="queue-hint">
              {{ t('generate.running') }}: {{ queue.runningImageCount }} / 5 · {{ t('generate.submitted') }}: {{ taskCount }}
            </div>
          </el-form>
        </el-card>
      </el-col>

      <!-- 右侧：预览/结果区（显示 "当前选中任务"） -->
      <el-col :xs="24" :md="13">
        <el-card shadow="never">
          <template #header>
          <div class="card-header">
            <div class="header-title">
              <span>{{ t('preview.resultTitle') }}</span>
              <span v-if="activeTask" class="task-pill" :class="'status-' + activeTask.status">
                {{ statusLabel }}
              </span>
            </div>
            <span v-if="resultUrl" class="header-actions">
              <el-button size="small" @click="downloadImage">
              <el-icon><Download /></el-icon>
              {{ t('preview.download') }}
              </el-button>
              <el-button size="small" type="primary" link @click="copyImageUrl">
              <el-icon><Link /></el-icon>
              {{ t('preview.copyLink') }}
              </el-button>
            </span>
          </div>
          </template>

          <!-- 情况 A：有选中任务且正在进行中 -->
          <div v-if="activeTask && taskRunning" class="result-loading">
            <div class="task-id-row">{{ t('status.taskId') }}: {{ activeTask.taskId }}</div>
            <el-progress
              :percentage="taskProgress"
              :stroke-width="12"
              :color="progressColor" />
            <div class="loading-text">{{ statusLabel }} ...</div>
            <div class="loading-sub">{{ t('status.elapsedSeconds') }} {{ taskElapsedSec }} {{ t('common.seconds') }}</div>
            <div class="prompt-row">{{ activeTask.prompt }}</div>
            <el-button
              type="danger"
              size="small"
              class="cancel-btn-inline"
              @click="cancelActiveTask">
              <el-icon><CircleCloseFilled /></el-icon>
              {{ t('status.cancelTask') }}
            </el-button>
          </div>

          <!-- 情况 B：有选中任务且已成功 -->
          <div v-else-if="activeTask && activeTask.status === 'success'" class="result-wrap">
            <ImageWithWatermark
              v-if="resultUrl"
              :src="resultUrl"
              :alt="'generated'"
              :img-class="'result-img'"
              fit="contain"
              :title="t('imageViewer.title')"
              style="cursor: zoom-in"
              @click="openViewerWithUrl(resultUrl)"
            />
            <ImageWithWatermark
              v-else-if="(activeTask as any).imageB64"
              :src="'data:image/png;base64,' + (activeTask as any).imageB64"
              :alt="'generated'"
              :img-class="'result-img'"
              fit="contain"
              :title="t('imageViewer.title')"
              style="cursor: zoom-in"
              @click="openViewerWithUrl('data:image/png;base64,' + (activeTask as any).imageB64)"
            />
            <div class="result-meta">
              <div class="meta-row">
              <span class="meta-label">{{ t('params.prompt') }}：</span>
              <span class="meta-value">{{ activeTask.prompt }}</span>
              </div>
              <div class="meta-row">
              <span class="meta-label">{{ t('params.size') }}：</span>
              <span class="meta-value">{{ getImageSizeLabel(size) }}</span>
              </div>
            </div>
          </div>

          <!-- 情况 C：任务失败 -->
          <div v-else-if="activeTask && activeTask.status === 'failed'" class="result-failed">
            <el-icon :size="48" :color="'var(--agnes-error)'"><CircleCloseFilled /></el-icon>
            <div class="failed-text">{{ t('status.imageGenerateFailed') }}</div>
            <div class="failed-sub">{{ activeTask.errorMessage || '' }}</div>
            <el-button type="primary" size="small" class="retry-btn" @click="retryActiveTask">
              {{ t('status.retryWithSame') }}
            </el-button>
          </div>

          <!-- 情况 D：已取消 -->
          <div v-else-if="activeTask && activeTask.status === 'cancelled'" class="result-failed">
            <el-icon :size="48" :color="'var(--agnes-warning)'"><CircleCloseFilled /></el-icon>
            <div class="failed-text">{{ t('status.cancelled') }}</div>
            <div class="failed-sub">{{ t('preview.wrongTypeHint') }}</div>
          </div>

          <!-- 情况 E：选中的是视频任务，不匹配当前视图 -->
          <div v-else-if="activeTaskIsOtherType" class="empty-state">
            <el-icon :size="48"><VideoPlay /></el-icon>
            <p class="empty-text">{{ t('preview.wrongTypeImage') }}</p>
            <p class="empty-sub">{{ t('preview.switchPageHint') }}</p>
          </div>

          <!-- 情况 F：没有选中的任务 -->
          <div v-else class="empty-state">
            <el-icon :size="48"><PictureFilled /></el-icon>
            <p class="empty-text">{{ t('preview.notSelectable') }}</p>
            <p class="empty-sub">{{ t('preview.emptyHint') }}</p>
          </div>
        </el-card>

        <!-- 使用技巧 -->
        <div class="tips-card">
          <div class="tip-title">{{ t('tips.title') }}</div>
          <ul>
            <li>{{ t('tips.concurrentImage') }}</li>
            <li>{{ t('tips.queueSwitch') }}</li>
            <li>{{ t('tips.historyKeep') }}</li>
          </ul>
        </div>

        <!-- 独立图片查看器：点击生成结果图片后弹出，支持缩放/平移/旋转/下载 -->
        <ImageViewer
          v-model:visible="viewerVisible"
          :url="viewerUrl"
          :download-url="viewerDownloadUrl"
        />
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import {
  MagicStick, Download, Link, PictureFilled, Edit, Loading, CircleCloseFilled, VideoPlay, Share, InfoFilled
} from '@element-plus/icons-vue'
import PromptTemplates from '@/components/PromptTemplates.vue'
import ImageUploader from '@/components/ImageUploader.vue'
import ImageViewer from '@/components/ImageViewer.vue'
import ImageWithWatermark from '@/components/ImageWithWatermark.vue'
import ParamSelector from '@/components/ParamSelector.vue'
import { useTaskQueueStore } from '@/stores/taskQueue'
import { useModelsStore } from '@/stores/models'
import { useUserStore } from '@/stores/user'
import { usePreferencesStore } from '@/stores/preferences'
import { useI18n } from '@/i18n'
import { useCreditEstimate } from '@/composables/useCreditEstimate'
import { useDownload } from '@/composables/useDownload'
import { matchImageSize, getImageSizeLabel, getModelParams } from '@/config/model-params'
import type { FileInfo } from '@/types'

const { t } = useI18n()
const userStore = useUserStore()
const prefsStore = usePreferencesStore()
const { downloadViaProxy } = useDownload()

// ---------- 图片查看器：点击预览图片弹出 ----------
const viewerVisible = ref(false)
const viewerUrl = ref('')
const viewerDownloadUrl = ref('')
function openViewerWithUrl(url: string) {
  if (!url) return
  viewerUrl.value = url
  // 网络图片走后端水印下载接口；base64 直接用原图
  if (url.startsWith('http://') || url.startsWith('https://')) {
    const baseURL = import.meta.env.VITE_API_BASE_URL || ''
    viewerDownloadUrl.value = `${baseURL}/api/images/download/watermark?url=${encodeURIComponent(url)}`
  } else {
    viewerDownloadUrl.value = url
  }
  viewerVisible.value = true
}

// 预设风格：不同语言下显示不同的 label（prompt 本身保持原样，不随语言变化）
// 注意：这里用 computed 动态读取当前语言下的显示名，避免语言切换后不同步
const imageTemplates = computed(() => ([
  { label: t('presets.surrealism'), prompt: '，超现实主义风格，梦幻，高细节' },
  { label: t('presets.cinematic'), prompt: '，电影感，戏剧性光照，宽银幕' },
  { label: t('presets.anime'), prompt: '，日式动漫风格，鲜艳色彩，细腻线条' },
  { label: t('presets.oilPainting'), prompt: '，古典油画风格，厚重笔触，文艺复兴质感' },
  { label: t('presets.realisticPhoto'), prompt: '，专业摄影，8K 超高清，自然光照' },
  { label: t('presets.cyberpunk'), prompt: '，赛博朋克，霓虹光，未来都市感' },
  { label: t('presets.inkStyle'), prompt: '，中国水墨风格，留白艺术，意境悠远' },
]))

// 模型列表：从后端 API 动态获取
const modelsStore = useModelsStore()
const IMAGE_MODELS = computed(() => modelsStore.imageModels)

// ---------- 表单参数 ----------
const mode = ref('text2image')
const prompt = ref('')

// ---------- 提示词长度分阶提示 ----------
// 图片：0-3000 适中，3000-8000 较长，8000+ 过长
const promptLengthLevel = computed(() => {
  const len = prompt.value.length
  if (len <= 3000) return 'level-good'
  if (len <= 8000) return 'level-long'
  return 'level-too-long'
})
const promptLengthText = computed(() => {
  const len = prompt.value.length
  if (len === 0) return ''
  if (len <= 3000) return t('params.promptLengthGood')
  if (len <= 8000) return t('params.promptLengthLong')
  return t('params.promptLengthTooLong')
})

// 分享到广场开关：是否将本次生成结果公开到广场
const shareToPlaza = ref(false)

/** 根据偏好设置的比例（如 "1:1"）匹配对应的图片尺寸（如 "1024x1024"） */
function sizeFromAspectRatio(ratio: string): string {
  const params = getModelParams()
  const [w, h] = ratio.split(':').map(Number)
  if (w && h) {
    const matched = params.imageSizes.find(o => o.w === w && o.h === h)
    if (matched) return matched.value
  }
  return modelsStore.defaultImageSize || '1024x1024'
}

// 默认尺寸：优先从偏好设置的比例匹配，其次从 store 配置获取
const size = ref(sizeFromAspectRatio(prefsStore.generation.default_aspect_ratio) || modelsStore.defaultImageSize || '1024x1024')
const model = ref('')  // 初始值在 store 加载后自动设置

// ---------- 积分预估：根据 mode + size 自动计算本次生成消耗 ----------
const { cost, loading: costLoading, insufficient: costInsufficient } = useCreditEstimate(
  () => ({
    type: 'image' as const,
    mode: mode.value,
    size: size.value,
  })
)

// store 加载完成后自动设置默认模型和默认尺寸
watch(() => modelsStore.defaultImageModel, (v) => {
  if (v && !model.value) model.value = v
}, { immediate: true })
watch(() => modelsStore.defaultImageSize, (v) => {
  if (v && size.value === '1024x1024') size.value = v
})
const referenceFileList = ref<FileInfo[]>([])   // 【多图】数组

// ---------- 使用全局 Store 管理任务 ----------
const queue = useTaskQueueStore()

// 当前预览的任务 = Store 中的 activeTask，但仅当其是图片类型
const activeTask = computed(() => {
  if (!queue.activeTaskId) return null
  const task = queue.tasks[queue.activeTaskId]
  if (!task) return null
  return task.type === 'image' ? task : null
})

// 选中任务是否为视频类型（在图片视图中不显示预览，仅提示）
const activeTaskIsOtherType = computed(() => {
  if (!queue.activeTaskId) return false
  const task = queue.tasks[queue.activeTaskId]
  return task && task.type !== 'image'
})

// 当前任务是否在运行
const taskRunning = computed(() => {
  if (!activeTask.value) return false
  return ['pending', 'queued', 'processing'].includes(activeTask.value.status)
})

// 进度、耗时
const taskProgress = computed(() => {
  if (!activeTask.value) return 0
  return Math.min(activeTask.value.progress || 0, 99)
})
const taskElapsedSec = computed(() => {
  if (!activeTask.value) return 0
  const created = activeTask.value.createdAt || 0
  if (!created) return 0
  queue._tick
  return Math.floor((Date.now() - created) / 1000)
})

// 结果 URL
const resultUrl = computed(() => {
  if (!activeTask.value) return ''
  return activeTask.value.resultUrl || (activeTask.value as any).url || ''
})

// 状态标签（使用 i18n 显示本地化名称）
const statusLabel = computed(() => {
  if (!activeTask.value) return ''
  const s = activeTask.value.status
  const key = `status.${s}`
  const localized = t(key)
  // 若翻译值与 key 相同（未翻译），则原样返回
  return localized === key ? s : localized
})

const progressColor = 'var(--agnes-warning)'

// 任务总数
const taskCount = computed(() => {
  if (!queue.tasks) return 0
  return Object.keys(queue.tasks).length
})

// 能否提交：提示词不为空 + 未达并发上限 + 积分大于 0
const canSubmit = computed(() => {
  if (!prompt.value.trim()) return false
  if (queue.runningImageCount >= 5) return false
  if (userStore.credits <= 0) return false
  return true
})

function appendStylePrompt(tpl: string) {
  if (!prompt.value.trim().endsWith(tpl)) {
    prompt.value = prompt.value.trim() + tpl
  }
}

function handleImageChange(fileList: FileInfo[]) {
  // fileList 为数组（可能为 null 表示清空）
  referenceFileList.value = Array.isArray(fileList) ? fileList : (fileList ? [fileList] : [])
  // 图生图自适应分辨率：上传参考图后自动匹配最接近的预设尺寸
  if (referenceFileList.value.length > 0 && referenceFileList.value[0].previewUrl) {
    autoMatchSize(referenceFileList.value[0])
  }
}
function handleImageClear() {
  referenceFileList.value = []
}

/** 根据上传图片的实际尺寸自动匹配最接近的预设分辨率 */
function autoMatchSize(file: FileInfo) {
  const img = new Image()
  img.onload = () => {
    const matched = matchImageSize(img.naturalWidth, img.naturalHeight)
    if (matched && matched !== size.value) {
      size.value = matched
    }
  }
  img.src = file.previewUrl || file.url || ''
}

// ---------- 提交任务 ----------
async function handleGenerate() {
  if (!prompt.value.trim()) {
    ElMessage.warning(t('message.pleaseFillPrompt'))
    return
  }
  if (mode.value === 'image2image' && referenceFileList.value.length === 0) {
    ElMessage.warning(t('message.pleaseUploadRefImage'))
    return
  }
  if (queue.runningImageCount >= 5) {
    ElMessage.warning(t('generate.concurrentImageLimit'))
    return
  }
  // 积分预检：避免无积分用户提交后被后端 402 拒绝
  if (userStore.credits <= 0) {
    ElMessage.warning(t('generate.noCreditsImage'))
    return
  }

  const params: Record<string, any> = {
    prompt: prompt.value.trim(),
    model: model.value,
    size: size.value,
    mode: mode.value,
    is_public: shareToPlaza.value,
  }
  // 【多图】图生图时：区分为 base64_images 与 image_urls
  if (mode.value === 'image2image' && referenceFileList.value.length > 0) {
    const b64Imgs = referenceFileList.value
      .filter(f => f.source === 'file' && f.base64)
      .map(f => f.base64)
    const urlImgs = referenceFileList.value
      .filter(f => f.source === 'url' && f.url)
      .map(f => f.url)
    if (b64Imgs.length) params.base64_images = b64Imgs
    if (urlImgs.length) params.image_urls = urlImgs
  }

  try {
    // 根据偏好设置中的默认生成数量提交多次任务
    const count = prefsStore.generation.default_image_count || 1
    const taskIds: string[] = []
    for (let i = 0; i < count; i++) {
      const taskId = await queue.submitImageTask(params)
      taskIds.push(taskId)
    }
    // 选中最后一个任务作为当前预览
    if (taskIds.length > 0) {
      queue.setActiveTask(taskIds[taskIds.length - 1])
    }
    ElMessage.success(count > 1
      ? `${t('generate.imageSubmitted')} (${count} 张)`
      : t('generate.imageSubmitted'))
  } catch (e) {
    console.error('[ImageView] 提交任务失败：', e)
    ElMessage.error(t('generate.createTaskFailed') + ((e as Error).message || ''))
  }
}

// ---------- 中止当前任务 ----------
function cancelActiveTask() {
  if (!queue.activeTaskId) return
  queue.cancelTask(queue.activeTaskId)
  ElMessage.info(t('status.taskCancelled'))
}

// ---------- 重试当前任务 ----------
function retryActiveTask() {
  if (!activeTask.value) return
  const taskId = queue.retryTask(activeTask.value.taskId)
  if (taskId) {
    queue.setActiveTask(taskId)
    ElMessage.success(t('status.taskResubmitted'))
  } else {
    ElMessage.warning(t('status.retryFailed'))
  }
}

// ---------- 下载 / 复制 ----------
async function downloadImage() {
  if (!resultUrl.value) {
    ElMessage.warning(t('preview.imageEmpty'))
    return
  }
  try {
    const baseURL = import.meta.env.VITE_API_BASE_URL || ''
    const proxyUrl = `${baseURL}/api/images/download/watermark?url=${encodeURIComponent(resultUrl.value)}`
    await downloadViaProxy(proxyUrl, `agnes-image-${Date.now()}.png`)
    ElMessage.success(t('preview.download'))
  } catch (err: any) {
    console.warn('[ImageView] 下载失败：', err)
    ElMessage.error(err?.message || t('preview.corsWarning'))
  }
}

function copyImageUrl() {
  if (!resultUrl.value) {
    ElMessage.warning(t('preview.imageEmpty'))
    return
  }
  if (navigator.clipboard && window.isSecureContext) {
    navigator.clipboard.writeText(resultUrl.value)
      .then(() => ElMessage.success(t('preview.copySuccess')))
      .catch(() => ElMessage.error(t('preview.copyFailed')))
  } else {
    const ta = document.createElement('textarea')
    ta.value = resultUrl.value
    document.body.appendChild(ta)
    ta.select()
    document.execCommand('copy')
    document.body.removeChild(ta)
    ElMessage.success(t('preview.copySuccess'))
  }
}
</script>

<style scoped>
.image-view { color: var(--agnes-text-primary); }
.page-title { margin: 0 0 4px 0; }
.page-desc { color: var(--agnes-text-muted); font-size: 14px; margin-bottom: 20px; line-height: 1.6; }
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 600;
}
.header-title {
  display: flex;
  align-items: center;
  gap: 10px;
}
.task-pill {
  display: inline-block;
  padding: 2px 10px;
  border-radius: 10px;
  font-size: 12px;
  font-weight: 500;
}
.task-pill.status-queued,
.task-pill.status-pending,
.task-pill.status-processing {
  background: var(--agnes-info-bg);
  color: var(--agnes-info);
}
.task-pill.status-success {
  background: var(--agnes-success-bg);
  color: var(--agnes-success);
}
.task-pill.status-failed {
  background: var(--agnes-error-bg);
  color: var(--agnes-error);
}
.task-pill.status-cancelled {
  background: var(--agnes-warning-bg);
  color: var(--agnes-warning);
}
.tab-sub { font-size: 12px; color: var(--agnes-text-muted); margin-left: 6px; }
/* 模式切换：图标 + 标题 + 短副标签 */
.mode-tabs :deep(.el-tabs__nav) {
  width: 100%;
  display: flex;
  justify-content: space-between;
  border-bottom: 1px solid var(--agnes-border);
}
.mode-tabs :deep(.el-tabs__item) {
  flex: 1;
  min-width: 0;
  text-align: center;
  padding: 14px 16px;
  height: auto;
  line-height: 1.4;
}
.mode-tabs :deep(.el-tabs__active-bar) {
  height: 3px;
  background: linear-gradient(90deg, var(--agnes-primary), var(--agnes-primary-soft));
  border-radius: 3px 3px 0 0;
}
.mode-tabs .mode-label {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  width: 100%;
}
.mode-tabs .mode-icon {
  font-size: 22px;
  flex-shrink: 0;
}
.mode-tabs .mode-text {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  text-align: left;
  line-height: 1.3;
}
.mode-tabs .mode-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--agnes-text-primary);
  white-space: nowrap;
}
.mode-tabs :deep(.is-active) .mode-title,
.mode-tabs :deep(.is-active) .mode-icon {
  color: var(--agnes-primary-soft);
}
.mode-tabs .mode-sub {
  font-size: 12px;
  color: var(--agnes-text-muted);
  margin-top: 2px;
  white-space: nowrap;
}
.mode-tabs { margin-bottom: 12px; }
.param-form { margin-top: 12px; }

/* 提示词长度分阶提示 */
.prompt-length-hint {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 6px;
  font-size: 12px;
}
.prompt-length-hint .el-icon {
  font-size: 14px;
}
.prompt-length-hint.level-good {
  color: var(--agnes-success);
}
.prompt-length-hint.level-long {
  color: var(--agnes-warning);
}
.prompt-length-hint.level-too-long {
  color: var(--agnes-error);
}

/* 统一表单标签：更醒目、更有视觉层级 */
.param-form :deep(.el-form-item__label) {
  color: var(--agnes-text-secondary) !important;
  font-size: 13px !important;
  font-weight: 500 !important;
  padding-bottom: 6px !important;
  letter-spacing: 0.3px;
}

/* 统一输入/下拉控件：贴合深色主题 */
.param-form :deep(.el-input__wrapper),
.param-form :deep(.el-textarea__inner),
.param-form :deep(.el-select) {
  background: var(--agnes-bg-input) !important;
  border-color: var(--agnes-border) !important;
  border-radius: 10px !important;
  box-shadow: none !important;
  color: var(--agnes-text-primary) !important;
}

.param-form :deep(.el-textarea__inner) {
  padding: 12px !important;
  font-size: 14px !important;
  line-height: 1.55 !important;
}

.param-form :deep(.el-input__wrapper:hover),
.param-form :deep(.el-textarea__inner:hover),
.param-form :deep(.el-select .el-select__wrapper:hover) {
  border-color: var(--agnes-primary) !important;
}

.param-form :deep(.el-select .el-select__wrapper) {
  box-shadow: none !important;
  background: var(--agnes-bg-input) !important;
  border-radius: 10px !important;
  min-height: 36px !important;
}

.param-form :deep(.el-input__inner),
.param-form :deep(.el-select__placeholder),
.param-form :deep(.el-select__selected-item) {
  color: var(--agnes-text-primary) !important;
  font-size: 14px !important;
}

.param-form :deep(.el-input__placeholder),
.param-form :deep(.el-select__placeholder) {
  color: var(--agnes-text-muted) !important;
}

.generate-btn {
  width: 100%;
  height: 48px;
  font-size: 16px;
  font-weight: 600;
  margin-top: 8px;
  border-radius: 12px !important;
}
/* 分享到广场开关：低调显示在生成按钮下方 */
.share-toggle {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  margin-top: 10px;
  font-size: 12px;
  color: var(--agnes-text-muted);
}
.share-toggle .share-icon {
  font-size: 14px;
}
.share-toggle .share-label {
  margin-right: 4px;
}
.queue-hint {
  margin-top: 8px;
  font-size: 12px;
  color: var(--agnes-text-muted);
  text-align: center;
}

/* 积分不足提示 */
.no-credits-hint {
  margin-top: 8px;
  padding: 8px 12px;
  background: var(--agnes-error-bg);
  border: 1px solid var(--agnes-error-border);
  border-radius: 8px;
  font-size: 12px;
  color: var(--agnes-error);
  text-align: center;
}

/* 积分扣除提示 */
.cost-hint {
  margin-top: 8px;
  font-size: 12px;
  text-align: center;
  color: var(--agnes-credits-text);
}
.cost-hint .cost-loading {
  color: var(--agnes-text-muted);
}
.cost-hint .cost-value.insufficient {
  color: var(--agnes-error);
}

/* 结果区 */
.result-loading {
  padding: 50px 20px;
  text-align: center;
}
.task-id-row {
  font-size: 12px;
  color: var(--agnes-text-faint);
  margin-bottom: 16px;
  font-family: monospace;
}
.loading-text {
  margin-top: 16px;
  font-size: 16px;
  color: var(--agnes-text-primary);
}
.loading-sub {
  margin-top: 6px;
  font-size: 12px;
  color: var(--agnes-text-muted);
}
.prompt-row {
  margin-top: 16px;
  padding: 10px 14px;
  background: var(--agnes-bg-inset);
  border-radius: 8px;
  font-size: 13px;
  color: var(--agnes-text-secondary);
  text-align: left;
  word-break: break-word;
  max-height: 80px;
  overflow: auto;
}
.cancel-btn-inline { margin-top: 20px; }
.result-wrap { text-align: center; }
.result-img {
  width: 100%;
  max-height: 520px;
  object-fit: contain;
  border-radius: 12px;
  background: var(--agnes-bg-dark-surface);
  display: block;
  cursor: zoom-in;
  transition: opacity 0.2s ease, transform 0.2s ease;
}
.result-img:hover {
  opacity: 0.92;
  transform: scale(1.005);
}
.result-meta {
  margin-top: 16px;
  padding: 12px;
  background: var(--agnes-bg-inset);
  border-radius: 8px;
  text-align: left;
}
.meta-row { font-size: 13px; padding: 4px 0; color: var(--agnes-text-primary); }
.meta-label { color: var(--agnes-text-muted); margin-right: 8px; }
.meta-value { word-break: break-word; }

.result-failed {
  padding: 60px 20px;
  text-align: center;
  color: var(--agnes-error);
}
.failed-text { margin-top: 16px; font-size: 16px; color: var(--agnes-error); }
.failed-sub { font-size: 12px; color: var(--agnes-text-muted); margin-top: 6px; }
.retry-btn { margin-top: 20px; }

.empty-state {
  padding: 80px 20px;
  text-align: center;
  color: var(--agnes-text-faint);
}
.empty-text { margin-top: 16px; font-size: 14px; }
.empty-sub { margin-top: 8px; font-size: 12px; color: var(--agnes-text-muted); line-height: 1.6; }

.tips-card {
  margin-top: 16px;
  padding: 16px 20px;
  background: var(--agnes-bg-inset);
  border: 1px solid var(--agnes-border);
  border-radius: 12px;
  font-size: 13px;
  color: var(--agnes-text-secondary);
}
.tip-title { font-weight: 600; color: var(--agnes-text-primary); margin-bottom: 8px; }
.tips-card ul { margin: 0; padding-left: 20px; line-height: 1.8; }
</style>
