<!-- =====================================================
  CanvasNodeComposer 节点悬浮 AI 对话框（LibTV 复刻）
  - 选中节点时悬浮在节点正下方，所有可 AI 生成的节点共用此输入条
  - 支持：script（剧情→生分镜）/ text（提示词→AI 生成回填）/ config（生图/视频提示词生成）
  - config 模式切换/模型/参数全部在条内，写回节点 content，发送复用现有生成链路
  - 文本节点走会话 SSE 流式回填（会话 id 存节点 content 复用）
  - 定位由父组件（CanvasView）按视口变换计算，本组件只管交互
===================================================== -->

<template>
  <div v-if="panel" class="node-composer" :style="boxStyle">
    <!-- 生成模式切换（仅 config 节点） -->
    <div v-if="isConfig" class="composer-tabs">
      <button
        v-for="m in configModes"
        :key="m.value"
        type="button"
        :class="['composer-tab', { active: configContent.mode === m.value }]"
        :style="tabStyle(configContent.mode === m.value)"
        @click="updateContent({ mode: m.value })"
      >{{ m.label }}</button>
    </div>

    <!-- 提示词输入区 -->
    <textarea
      ref="inputRef"
      v-model="text"
      class="composer-input"
      :style="inputStyle"
      rows="2"
      :placeholder="placeholder"
      @input="onInput"
      @keydown="onKeyDown"
      @blur="handleMentionBlur"
    ></textarea>

    <!-- 底部：参数 + 状态 + 发送 -->
    <div class="composer-bottom">
      <!-- script 参数：镜头数 + 风格 -->
      <template v-if="panelType === 'script'">
        <span class="composer-param-label">{{ t('canvas.script.shotCount') }}</span>
        <input v-model.number="scriptShotMin" type="number" min="1" max="30" class="composer-num" :style="selectStyle" @input="persistScriptParams">
        <span class="composer-param-label">–</span>
        <input v-model.number="scriptShotMax" type="number" min="1" max="30" class="composer-num" :style="selectStyle" @input="persistScriptParams">
        <input v-model="scriptStyle" class="composer-style" :style="selectStyle" :placeholder="t('canvas.script.stylePlaceholder')" @input="persistScriptParams">
      </template>
      <template v-if="isConfig">
        <!-- 模型选择（按模式筛选） -->
        <select
          class="composer-select"
          :style="selectStyle"
          :value="configContent.model"
          @change="updateContent({ model: ($event.target as HTMLSelectElement)?.value })"
        >
          <option v-for="m in availableModels" :key="m.id" :value="m.id">{{ m.name }}</option>
        </select>
        <!-- 图片尺寸 -->
        <select
          v-if="isImageMode"
          class="composer-select"
          :style="selectStyle"
          :value="configContent.size"
          @change="updateContent({ size: ($event.target as HTMLSelectElement)?.value })"
        >
          <option v-for="s in imageSizeOptions" :key="s.value" :value="s.value">{{ s.label }}</option>
        </select>
        <!-- 视频参数：分辨率/比例/帧率/时长 -->
        <template v-if="isVideoMode">
          <select class="composer-select" :style="selectStyle" :value="configContent.resolution" @change="updateContent({ resolution: Number(($event.target as HTMLSelectElement)?.value) })">
            <option v-for="r in videoResolutionOptions" :key="r.value" :value="r.value">{{ r.label }}</option>
          </select>
          <select class="composer-select" :style="selectStyle" :value="configContent.aspect_ratio" @change="updateContent({ aspect_ratio: ($event.target as HTMLSelectElement)?.value })">
            <option v-for="r in videoAspectRatioOptions" :key="r.value" :value="r.value">{{ r.label }}</option>
          </select>
          <select class="composer-select" :style="selectStyle" :value="configContent.frame_rate" @change="updateContent({ frame_rate: Number(($event.target as HTMLSelectElement)?.value), seconds: clampedSeconds(Number(($event.target as HTMLSelectElement)?.value), configContent.seconds) })">
            <option v-for="fr in videoFrameRateOptions" :key="fr" :value="fr">{{ fr }} FPS</option>
          </select>
          <select class="composer-select" :style="selectStyle" :value="configContent.seconds" @change="updateContent({ seconds: Number(($event.target as HTMLSelectElement)?.value) })">
            <option v-for="s in availableDurations" :key="s" :value="s">{{ s }}{{ t('canvas.node.secondsSuffix') }}</option>
          </select>
          <!-- 关键帧开关（仅图生视频） -->
          <label v-if="configContent.mode === 'image2video'" class="composer-kf">
            <el-switch
              :model-value="configContent.use_keyframes || false"
              size="small"
              @update:model-value="updateContent({ use_keyframes: $event })"
            />
            <span class="composer-kf-label">{{ t('canvas.node.keyframesMode') }}</span>
          </label>
        </template>
      </template>

      <!-- 状态提示 -->
      <span class="composer-tip" :style="mutedStyle">
        {{ busy ? t('canvas.composer.busy') : t('canvas.composer.sendTip') }}
      </span>
      <!-- 发送按钮 -->
      <button
        type="button"
        class="composer-send"
        :style="sendStyle"
        :disabled="!canSend"
        :title="t('canvas.composer.send')"
        @click="onSend"
      >↑</button>
    </div>

    <!-- @ 提及弹窗（config 节点） -->
    <Teleport to="body">
      <div
        v-if="mentionVisible && mentionCandidates.length > 0"
        class="composer-mention"
        :style="{ top: mentionPosition.top + 'px', left: mentionPosition.left + 'px' }"
        @mousedown="handlePopupMouseDown"
      >
        <div
          v-for="(candidate, idx) in mentionCandidates"
          :key="candidate.id"
          class="composer-mention-item"
          :class="{ active: idx === mentionActiveIndex }"
          @mousedown.prevent.stop="selectMention(candidate)"
        >
          <span class="mention-index">{{ candidate.index }}</span>
          <span class="mention-name">{{ candidate.label }}</span>
          <span v-if="candidate.preview" class="mention-preview">{{ candidate.preview }}</span>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch, nextTick } from 'vue'
import { useI18n } from '@/i18n'
import { ElMessage } from 'element-plus'
import { useCanvasStore } from '@/stores/canvas'
import { useModelsStore } from '@/stores/models'
import { createChatSession, sendMessageStream } from '@/api/chat'
import { generateStoryboard, type StoryboardShot } from '@/api/storyboard'
import { getErrorMessage } from '@/lib/type-helpers'
import {
  getUpstreamNodes,
  executeImageReferenceGeneration,
  executeVideoFromFrameGeneration,
} from '@/lib/canvas-generation'
import { readShots } from '@/lib/canvas-storyboard'
import { checkCreditsBeforeGenerate } from '@/lib/canvas-credits'
import { useNodeMention } from '@/composables/useNodeMention'

const props = defineProps<{ panelId: string }>()
const emit = defineEmits<{ (e: 'generate'): void }>()

const { t } = useI18n()
const store = useCanvasStore()
const modelsStore = useModelsStore()

/** 当前节点 */
const panel = computed(() => store.panels.find((p) => p.id === props.panelId) || null)
const panelType = computed(() => panel.value?.type || '')

/** 是否 config（生图/视频配置节点） */
const isConfig = computed(() => panelType.value === 'config')

/** 是否媒体节点（图片=图生图，视频=首帧生视频） */
const isMedia = computed(() => panelType.value === 'image' || panelType.value === 'video')

/* ---------- config 节点内容与参数选项 ---------- */
const configContent = computed<Record<string, any>>(() => ({
  mode: 'text2image',
  model: modelsStore.defaultImageModel,
  size: '1024x1024',
  prompt: '',
  aspect_ratio: modelsStore.defaultVideoAspectRatio,
  resolution: modelsStore.defaultVideoResolution,
  frame_rate: modelsStore.defaultFrameRate,
  seconds: modelsStore.defaultVideoDuration,
  ...(panel.value?.content || {}),
}))

const isImageMode = computed(() => configContent.value.mode?.includes('image') && !configContent.value.mode?.includes('video'))
const isVideoMode = computed(() => configContent.value.mode?.includes('video'))

const configModes = computed(() => [
  { value: 'text2image', label: t('canvas.node.configMode.text2image') },
  { value: 'image2image', label: t('canvas.node.configMode.image2image') },
  { value: 'text2video', label: t('canvas.node.configMode.text2video') },
  { value: 'image2video', label: t('canvas.node.configMode.image2video') },
])
const availableModels = computed(() => modelsStore.getModelsByMode(configContent.value.mode || 'text2image'))
const imageSizeOptions = computed(() => {
  const opts = modelsStore.imageSizeOptions
  if (opts.length > 0) return opts
  return (modelsStore.imageSizes.length > 0 ? modelsStore.imageSizes : ['1024x1024', '768x1024', '1024x768', '1280x720'])
    .map((v) => ({ value: v, w: 1, h: 1, label: v }))
})
const videoAspectRatioOptions = computed(() => modelsStore.getModelParamsConfig().videoAspectRatios)
const videoResolutionOptions = computed(() => modelsStore.getModelParamsConfig().videoResolutions || [])
const videoFrameRateOptions = computed(() => modelsStore.getModelParamsConfig().videoFrameRates)
/** 可用时长随帧率过滤（24FPS≤15s，30FPS≤10s，60FPS≤5s） */
const availableDurations = computed(() => {
  const config = modelsStore.getModelParamsConfig()
  const fps = configContent.value.frame_rate || 24
  const maxDuration = fps >= 60 ? 5 : fps >= 30 ? 10 : 15
  return config.videoDurations.filter((s: number) => s <= maxDuration)
})

/** 切帧率后把时长钳制回合法范围 */
function clampedSeconds(fps: number, seconds: number): number {
  const config = modelsStore.getModelParamsConfig()
  const maxDuration = fps >= 60 ? 5 : fps >= 30 ? 10 : 15
  const list = config.videoDurations.filter((s: number) => s <= maxDuration)
  return list.includes(seconds) ? seconds : list[list.length - 1] || 5
}

/* ---------- 输入状态（按节点类型读写不同字段） ---------- */
const text = ref('')
const busy = ref(false)
const inputRef = ref<HTMLTextAreaElement | null>(null)

/** 占位文案：按节点类型区分 */
const placeholder = computed(() => {
  if (panelType.value === 'script') return t('canvas.composer.placeholderScript')
  if (panelType.value === 'text') return t('canvas.composer.placeholderText')
  if (panelType.value === 'image') return t('canvas.composer.placeholderImage')
  if (panelType.value === 'video') return t('canvas.composer.placeholderVideo')
  return t('canvas.composer.placeholderGenerate')
})

/** 输入写回：config→prompt，script→story，text→仅本地 */
function persistText() {
  if (!panel.value) return
  if (panelType.value === 'config') store.updatePanel(panel.value.id, { content: { prompt: text.value } })
  else if (panelType.value === 'script') store.updatePanel(panel.value.id, { content: { story: text.value } })
}

function updateContent(patch: Record<string, unknown>) {
  if (panel.value) store.updatePanel(panel.value.id, { content: patch })
}

/* ---------- script 节点生成参数（镜头数/风格，随输入持久化） ---------- */
const scriptShotMin = ref(6)
const scriptShotMax = ref(12)
const scriptStyle = ref('')

// 切换目标节点时重新载入输入内容
watch(() => props.panelId, () => {
  busy.value = false
  if (panelType.value === 'config') text.value = configContent.value.prompt || ''
  else if (panelType.value === 'script') {
    text.value = typeof panel.value?.content?.story === 'string' ? panel.value.content.story : ''
    scriptShotMin.value = typeof panel.value?.content?.shotMin === 'number' ? panel.value.content.shotMin : 6
    scriptShotMax.value = typeof panel.value?.content?.shotMax === 'number' ? panel.value.content.shotMax : 12
    scriptStyle.value = typeof panel.value?.content?.style === 'string' ? panel.value.content.style : ''
  }
  else text.value = ''
  nextTick(autosize)
}, { immediate: true })

/** 镜头数范围钳制并持久化 */
function persistScriptParams() {
  const clamp = (v: number, min: number, max: number) =>
    Number.isFinite(v) ? Math.min(max, Math.max(min, Math.round(v))) : min
  scriptShotMin.value = clamp(scriptShotMin.value, 1, scriptShotMax.value || 12)
  scriptShotMax.value = clamp(scriptShotMax.value, scriptShotMin.value || 1, 30)
  updateContent({ shotMin: scriptShotMin.value, shotMax: scriptShotMax.value, style: scriptStyle.value })
}

/* ---------- @ 提及（config 节点） ---------- */
const {
  mentionPopupVisible: mentionVisible,
  mentionActiveIndex,
  mentionCandidates,
  mentionPopupPosition: mentionPosition,
  handleInput: handleMentionInput,
  handleKeyDown: handleMentionKeyDown,
  handleBlur: handleMentionBlur,
  handlePopupMouseDown,
  selectMention,
  setCurrentPanel,
} = useNodeMention(inputRef)

watch(() => props.panelId, (id) => setCurrentPanel(isConfig.value ? id : null), { immediate: true })

/** 输入事件：v-model 之外做 @ 提及处理 + 自适应高度 */
function onInput() {
  if (isConfig.value) handleMentionInput()
  persistText()
  autosize()
}

/** 自适应高度（上限 180px 后滚动） */
function autosize() {
  const el = inputRef.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = Math.min(el.scrollHeight, 180) + 'px'
}

/** 键盘：Enter 发送（@ 弹窗打开时交给提及导航），Shift+Enter 换行 */
function onKeyDown(event: KeyboardEvent) {
  if (isConfig.value && mentionVisible.value) {
    handleMentionKeyDown(event)
    if (mentionVisible.value) return
  }
  if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
    event.preventDefault()
    onSend()
  }
}

const canSend = computed(() => text.value.trim().length > 0 && !busy.value)

/* ---------- 发送：按节点类型分发 ---------- */
function onSend() {
  if (!canSend.value || !panel.value) return
  if (panelType.value === 'config') sendConfig()
  else if (panelType.value === 'script') void sendScript()
  else if (panelType.value === 'text') void sendText()
  else if (panelType.value === 'image') void sendImage()
  else if (panelType.value === 'video') void sendVideo()
  else ElMessage.info(t('canvas.composer.unsupported'))
}

/** config：写入 prompt 后交由父组件走现有合并生成流程 */
function sendConfig() {
  persistText()
  emit('generate')
}

/** script：剧情 → 生成分镜脚本 → 唤起分镜向导 */
async function sendScript() {
  if (!panel.value) return
  busy.value = true
  try {
    persistText()
    // 上游图片节点 = 角色参考图，上游文本节点 = 角色设定
    const upstreamNodes = getUpstreamNodes(panel.value.id, store.panels, store.connections)
    const characters = upstreamNodes.map((p) => {
      const content = typeof p.content?.content === 'string' ? p.content.content : ''
      if (p.type === 'image') return { name: p.name || '', description: '', ref_image_url: content }
      return { name: p.name || '', description: content, ref_image_url: null }
    })
    const resp = await generateStoryboard({
      story: text.value.trim(),
      characters,
      shot_count_min: scriptShotMin.value,
      shot_count_max: scriptShotMax.value,
      style: scriptStyle.value.trim() || undefined,
    })
    const shots = (resp.data?.shots || []).map((s: StoryboardShot, i: number) => ({
      id: `shot_${Date.now().toString(36)}_${i}_${Math.random().toString(36).slice(2, 6)}`,
      no: s.no || i + 1,
      duration: 5,
      shotSize: s.shot_size || '中景',
      camera: s.camera || '',
      description: s.description || '',
      dialogue: s.dialogue || '',
    }))
    updateContent({ shots: JSON.parse(JSON.stringify(shots)) })
    // 已有分镜数量变化时清空旧的派生标记由向导处理；这里唤起向导进入确认镜头
    if (readShots(panel.value!).length > 0) {
      store.openScriptWizardId = panel.value!.id
      text.value = ''
    } else {
      ElMessage.warning(t('canvas.messages.shotsEmpty'))
    }
  } catch (err) {
    ElMessage.error(getErrorMessage(err) || t('canvas.composer.generateFailed'))
  } finally {
    busy.value = false
  }
}

/** text：提示词 → 聊天 SSE 流式回填节点内容（会话 id 存节点复用） */
async function sendText() {
  if (!panel.value) return
  busy.value = true
  try {
    let sessionId = typeof panel.value.content?.chat_session_id === 'number'
      ? panel.value.content.chat_session_id
      : null
    if (!sessionId) {
      const session = await createChatSession({ title: panel.value.name || 'Canvas Text' })
      sessionId = session.id
      updateContent({ chat_session_id: sessionId })
    }
    let acc = ''
    updateContent({ content: '', status: 'loading' })
    await sendMessageStream(sessionId, text.value.trim(), [], (event) => {
      if (event.type === 'text' && event.content) {
        acc += event.content
        updateContent({ content: acc, status: 'loading' })
      } else if (event.type === 'error') {
        throw new Error(event.content || t('canvas.composer.generateFailed'))
      }
    })
    updateContent({ content: acc, status: 'idle' })
    text.value = ''
  } catch (err) {
    updateContent({ status: 'idle' })
    ElMessage.error(getErrorMessage(err) || t('canvas.composer.generateFailed'))
  } finally {
    busy.value = false
  }
}

/** image：图生图 —— 以当前图片为参考图生成新图片节点 */
async function sendImage() {
  if (!panel.value) return
  const ok = await checkCreditsBeforeGenerate({ type: 'image', mode: 'image2image', size: '1024x1024' })
  if (!ok) return
  busy.value = true
  try {
    await executeImageReferenceGeneration(panel.value, text.value.trim(), store)
    text.value = ''
    autosize()
  } finally {
    busy.value = false
  }
}

/** video：首帧生视频 —— 抽取当前视频首帧作为参考图图生视频，生成新视频节点 */
async function sendVideo() {
  if (!panel.value) return
  const videoUrl = String(panel.value.content?.content || '')
  if (!videoUrl) {
    ElMessage.warning(t('canvas.composer.emptyVideo'))
    return
  }
  const ok = await checkCreditsBeforeGenerate({ type: 'video', mode: 'image2video', seconds: 5 })
  if (!ok) return
  busy.value = true
  try {
    const frame = await extractFirstFrame(videoUrl)
    await executeVideoFromFrameGeneration(panel.value, frame, text.value.trim(), store)
    text.value = ''
    autosize()
  } catch (err) {
    ElMessage.error(getErrorMessage(err) || t('canvas.composer.firstFrameFailed'))
  } finally {
    busy.value = false
  }
}

/** 抽取视频首帧：加载视频 -> 跳到 0.1s -> 绘制到 canvas 导出 dataURI */
function extractFirstFrame(videoUrl: string): Promise<string> {
  return new Promise((resolve, reject) => {
    const video = document.createElement('video')
    video.crossOrigin = 'anonymous'
    video.muted = true
    video.src = videoUrl
    video.addEventListener('loadeddata', () => {
      video.currentTime = 0.1
    })
    video.addEventListener('seeked', () => {
      try {
        const canvas = document.createElement('canvas')
        canvas.width = video.videoWidth || 1280
        canvas.height = video.videoHeight || 720
        canvas.getContext('2d')?.drawImage(video, 0, 0, canvas.width, canvas.height)
        resolve(canvas.toDataURL('image/png'))
      } catch (err) {
        // 跨域污染画布时无法导出
        reject(err instanceof Error ? err : new Error(String(err)))
      }
    })
    video.addEventListener('error', () => reject(new Error('video load failed')))
  })
}

/* ---------- 主题样式 ---------- */
const theme = computed(() => store.canvasTheme)
const boxStyle = computed(() => ({
  background: theme.value.node.panel,
  borderColor: theme.value.node.stroke,
  color: theme.value.node.text,
}))
const inputStyle = computed(() => ({
  background: 'transparent',
  borderColor: theme.value.node.faint,
  color: theme.value.node.text,
}))
const selectStyle = computed(() => ({
  background: theme.value.node.fill,
  borderColor: theme.value.node.stroke,
  color: theme.value.node.text,
}))
const mutedStyle = computed(() => ({ color: theme.value.node.muted }))

function tabStyle(active: boolean) {
  return active
    ? { background: theme.value.node.activeStroke, color: '#fff', borderColor: theme.value.node.activeStroke }
    : { background: 'transparent', color: theme.value.node.muted, borderColor: theme.value.node.stroke }
}

const sendStyle = computed(() => {
  if (canSend.value) {
    return { background: theme.value.node.activeStroke, borderColor: theme.value.node.activeStroke, color: '#fff' }
  }
  return { background: theme.value.node.fill, borderColor: theme.value.node.stroke, color: theme.value.node.muted }
})
</script>

<style scoped>
/* 悬浮对话框：圆角深色卡，父组件控制 left/top/width */
.node-composer {
  position: absolute;
  z-index: 40;
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 10px;
  border: 1px solid;
  border-radius: 14px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.35);
  box-sizing: border-box;
}

/* 模式切换 tabs */
.composer-tabs {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}
.composer-tab {
  border: 1px solid;
  border-radius: 8px;
  padding: 3px 10px;
  font-size: 11px;
  cursor: pointer;
}
.composer-tab.active {
  font-weight: 600;
}

/* 输入区 */
.composer-input {
  width: 100%;
  border: 1px solid;
  border-radius: 10px;
  padding: 8px 10px;
  font-size: 13px;
  line-height: 1.6;
  outline: none;
  resize: none;
  box-sizing: border-box;
  font-family: inherit;
  min-height: 52px;
  max-height: 180px;
  overflow-y: auto;
}
.composer-input:focus {
  border-color: rgba(107, 156, 255, 0.6);
}

/* 底部参数行 */
.composer-bottom {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}
.composer-select {
  border: 1px solid;
  border-radius: 8px;
  padding: 3px 6px;
  font-size: 11px;
  outline: none;
  cursor: pointer;
  max-width: 150px;
}
.composer-kf {
  display: flex;
  align-items: center;
  gap: 4px;
}
.composer-kf-label {
  font-size: 11px;
  white-space: nowrap;
}
/* script 参数：镜头数/风格 */
.composer-param-label {
  font-size: 11px;
  white-space: nowrap;
}
.composer-num {
  width: 52px;
  border: 1px solid;
  border-radius: 8px;
  padding: 3px 6px;
  font-size: 11px;
  outline: none;
}
.composer-style {
  width: 130px;
  border: 1px solid;
  border-radius: 8px;
  padding: 3px 6px;
  font-size: 11px;
  outline: none;
}
.composer-tip {
  margin-left: auto;
  font-size: 11px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.composer-send {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  border: 1px solid;
  font-size: 16px;
  font-weight: 700;
  cursor: pointer;
  flex: none;
  line-height: 1;
  transition: opacity 0.15s, transform 0.15s;
}
.composer-send:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}
.composer-send:not(:disabled):hover {
  transform: scale(1.06);
}

/* @ 提及弹窗（Teleport 到 body） */
.composer-mention {
  position: fixed;
  z-index: 99999;
  min-width: 220px;
  max-width: 320px;
  max-height: 260px;
  overflow-y: auto;
  background: rgba(15, 22, 38, 0.98);
  border: 1px solid rgba(120, 170, 230, 0.25);
  border-radius: 10px;
  padding: 4px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
}
.composer-mention-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  border-radius: 6px;
  font-size: 12px;
  color: #e8eef7;
  cursor: pointer;
}
.composer-mention-item:hover,
.composer-mention-item.active {
  background: rgba(107, 156, 255, 0.15);
}
.mention-index {
  color: #8ba3c9;
  font-size: 11px;
  width: 16px;
  text-align: right;
  flex: none;
}
.mention-name {
  flex: none;
}
.mention-preview {
  color: #6b84aa;
  font-size: 11px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
