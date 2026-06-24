<!-- =====================================================
     CanvasNode 画布节点组件
     - 1:1 复刻参考项目 infinite-canvas 的节点设计与图标
     - 节点外壳：rounded-3xl（24px 圆角）+ border-2（2px 边框）
     - 选中态：边框 #2f80ff + 0 0 0 1px #2f80ff55 阴影
     - 四角缩放手柄：size-7（28px）透明热区，外侧 14px
     - 左右连线锚点：size-12（48px）热区 + size-3（12px）圆形锚点
     - 按类型渲染内容：text/image/video/audio/config
     - 交互：拖拽移动、双击编辑/查看、右键菜单、hover、缩放、连线
     ===================================================== -->

<template>
  <div
    class="canvas-node"
    :class="{ 'is-selected': selected }"
    :data-node-id="panel.id"
    :style="nodeStyle"
    @mouseenter="handleMouseEnter"
    @mouseleave="handleMouseLeave"
    @contextmenu="handleContextMenu"
  >
    <!-- 节点外壳：圆角 + 边框 + 选中高亮 -->
    <div
      class="node-shell"
      :style="shellStyle"
      @mousedown="handleMouseDown"
      @dblclick="handleDoubleClick"
    >
      <!-- 内容区：按类型渲染 -->
      <div class="node-content-wrap" :style="contentWrapStyle">
        <!-- 加载状态：旋转加载圈 + "生成中"文字 -->
        <div
          v-if="metadata.status === 'loading'"
          class="node-loading"
          :style="{ color: theme.node.activeStroke }"
        >
          <div class="loading-spinner" :style="loadingSpinnerStyle"></div>
          <span class="loading-text">{{ t('canvas.node.generating') }}</span>
        </div>

        <!-- 错误状态：红色错误文字 + 重试按钮 -->
        <div v-else-if="metadata.status === 'error'" class="node-error">
          <div class="error-text">{{ metadata.errorDetails || t('canvas.node.generateFailed') }}</div>
          <button
            type="button"
            class="retry-btn"
            :style="retryBtnStyle"
            @click.stop="handleRetry"
            @mousedown.stop
          >
            <RefreshCw :size="14" />
            {{ t('canvas.node.retry') }}
          </button>
        </div>

        <!-- 文本节点：可编辑文本区（生图/生视频入口由悬停工具栏提供） -->
        <div v-else-if="panel.type === 'text'" class="text-content">
          <!-- 编辑态：textarea -->
          <textarea
            v-if="isEditingContent"
            ref="textareaRef"
            class="text-textarea"
            :style="textStyle"
            :value="metadata.content || ''"
            :placeholder="t('canvas.node.doubleClickToEdit')"
            @input="handleContentInput"
            @blur="stopEditing"
            @keydown.escape="stopEditing"
            @mousedown.stop
            @pointerdown.stop
            @wheel.stop
          />
          <!-- 展示态：div -->
          <div v-else class="text-display" :style="textStyle" @wheel.stop>
            <span v-if="metadata.content">{{ metadata.content }}</span>
            <span v-else :style="{ color: theme.node.placeholder }">{{ t('canvas.node.doubleClickToEdit') }}</span>
          </div>
        </div>

        <!-- 图片节点：空状态 / 有图显示图片 -->
        <div v-else-if="panel.type === 'image'" class="image-content">
          <!-- 空状态：Image 图标 + "空图片节点" -->
          <div
            v-if="!hasImageContent"
            class="empty-state"
            :style="{ color: theme.node.placeholder }"
          >
            <div class="empty-icon" :style="{ background: theme.toolbar.activeBg }">
              <ImageIcon :size="24" />
            </div>
            <span class="empty-text">{{ t('canvas.node.emptyImage') }}</span>
          </div>
          <!-- 有图：显示图片（object-contain） -->
          <WatermarkOverlay v-else class="canvas-image-wrapper">
            <img
              :src="metadata.content"
              :alt="panel.title || ''"
              class="image-img"
              :class="{ 'object-fill': metadata.freeResize }"
              draggable="false"
              @dragstart.prevent
              @load="onImageLoad"
            />
          </WatermarkOverlay>
        </div>

        <!-- 视频节点：空状态 / 有视频显示播放器 -->
        <div v-else-if="panel.type === 'video'" class="video-content">
          <!-- 空状态：Video 图标 + "空视频节点" -->
          <div
            v-if="!hasVideoContent"
            class="empty-state"
            :style="{ color: theme.node.placeholder }"
          >
            <Video :size="28" />
            <span class="empty-text empty-text-sm">{{ t('canvas.node.emptyVideo') }}</span>
          </div>
          <!-- 有视频：video 播放器 -->
          <video
            v-else
            :src="metadata.content"
            controls
            class="video-player"
            data-canvas-no-zoom
            @loadedmetadata="onVideoMetadataLoaded"
          />
        </div>

        <!-- 音频节点：空状态 / 有音频显示信息 + 播放器 -->
        <div v-else-if="panel.type === 'audio'" class="audio-content">
          <!-- 空状态：Music2 图标 + "空音频节点" -->
          <div
            v-if="!hasAudioContent"
            class="empty-state"
            :style="{ color: theme.node.placeholder }"
          >
            <Music2 :size="28" />
            <span class="empty-text empty-text-sm">{{ t('canvas.node.emptyAudio') }}</span>
          </div>
          <!-- 有音频：音频信息 + audio 播放器 -->
          <div
            v-else
            class="audio-player-wrap"
            :style="{ background: theme.node.fill, color: theme.node.text }"
          >
            <div class="audio-info">
              <Music2 :size="16" />
              <span class="audio-title">{{ panel.title || t('canvas.node.audio') }}</span>
            </div>
            <audio
              :src="metadata.content"
              controls
              class="audio-player"
              data-canvas-no-zoom
            />
          </div>
        </div>

        <!-- 配置节点：生成配置面板（模式切换 + 模型选择 + 参数 + 提示词 + 生成按钮） -->
        <div v-else-if="panel.type === 'config'" class="config-content">
          <!-- 上半部分：参数 + 提示词，可滚动 -->
          <div class="config-scroll-area">
            <!-- 生成模式切换 -->
            <div class="config-mode-tabs">
              <button
                v-for="m in configModes"
                :key="m.value"
                type="button"
                :class="['config-mode-tab', { active: configContent.mode === m.value }]"
                @click="updateConfigContent('mode', m.value)"
                @mousedown.stop
              >
                {{ m.label }}
              </button>
            </div>

            <!-- 模型选择（按当前模式自动筛选对应类型模型） -->
            <select
              class="config-select"
              :value="configContent.model"
              @change="updateConfigContent('model', ($event.target as HTMLSelectElement)?.value)"
              @mousedown.stop
            >
              <option v-for="m in availableModels" :key="m.id" :value="m.id">{{ m.name }}</option>
            </select>

            <!-- 尺寸选择（图片模式）：显示友好标签 -->
            <select
              v-if="isImageMode"
              class="config-select"
              :value="configContent.size"
              @change="updateConfigContent('size', ($event.target as HTMLSelectElement)?.value)"
              @mousedown.stop
            >
              <option v-for="s in imageSizeOptions" :key="s.value" :value="s.value">{{ s.label }}</option>
            </select>

            <!-- 视频参数（视频模式）：分辨率 + 比例 + 帧率 + 时长，两行两列紧凑布局 -->
            <div v-if="isVideoMode" class="config-video-params">
              <select
                class="config-select"
                :value="configContent.resolution"
                @change="updateConfigContent('resolution', Number(($event.target as HTMLSelectElement)?.value))"
                @mousedown.stop
              >
                <option v-for="r in videoResolutionOptions" :key="r.value" :value="r.value">{{ r.label }}</option>
              </select>
              <select
                class="config-select"
                :value="configContent.aspect_ratio"
                @change="updateConfigContent('aspect_ratio', ($event.target as HTMLSelectElement)?.value)"
                @mousedown.stop
              >
                <option v-for="r in videoAspectRatioOptions" :key="r.value" :value="r.value">{{ r.label }}</option>
              </select>
              <select
                class="config-select"
                :value="configContent.frame_rate"
                @change="onFrameRateChange(Number(($event.target as HTMLSelectElement)?.value))"
                @mousedown.stop
              >
                <option v-for="fr in videoFrameRateOptions" :key="fr" :value="fr">{{ fr }} FPS</option>
              </select>
              <select
                class="config-select"
                :value="configContent.seconds"
                @change="updateConfigContent('seconds', Number(($event.target as HTMLSelectElement)?.value))"
                @mousedown.stop
              >
                <option v-for="s in availableDurations" :key="s" :value="s">{{ s }}{{ t('canvas.node.secondsSuffix') }}</option>
              </select>
            </div>
            <!-- 关键帧模式开关（仅图生视频模式显示） -->
            <div v-if="configContent.mode === 'image2video'" class="keyframes-toggle-row">
              <el-switch
                :model-value="configContent.use_keyframes || false"
                @update:model-value="updateConfigContent('use_keyframes', $event)"
                @mousedown.stop
                size="small"
              />
              <span class="toggle-label">{{ t('canvas.node.keyframesMode') }}</span>
              <el-tooltip :content="t('canvas.node.keyframesModeHint')" placement="top">
                <el-icon class="info-icon"><InfoFilled /></el-icon>
              </el-tooltip>
            </div>

            <!-- 提示词输入 -->
            <textarea
              class="config-prompt"
              v-model="configPrompt"
              :placeholder="t('canvas.node.configPromptPlaceholder')"
              @mousedown.stop
              @wheel.stop
            />
          </div>

          <!-- 底部固定：生成按钮（异步操作，点击后不阻塞，可连续点击） -->
          <button
            type="button"
            class="config-generate-btn"
            @click="handleConfigGenerate"
            @mousedown.stop
          >
            {{ isVideoMode ? t('canvas.node.generateVideoBtn') : t('canvas.node.generateImageBtn') }}
          </button>
        </div>

        <!-- 未知节点类型 -->
        <div
          v-else
          class="unknown-content"
          :style="{ color: theme.node.placeholder }"
        >
          {{ t('canvas.node.unknownNode') }}
        </div>
      </div>

      <!-- 图片信息条：尺寸·大小（可选） -->
      <div v-if="showImageInfo && hasImageContent" class="image-info-bar">
        <span class="image-info-text">
          {{ imageInfoWidth }} x {{ imageInfoHeight }}{{ imageInfoSize ? ' · ' + imageInfoSize : '' }}
        </span>
      </div>

      <!-- 底部渐变遮罩（非媒体节点） -->
      <div
        v-if="!hasImageContent && !hasVideoContent && !hasAudioContent"
        class="bottom-gradient"
        :style="{ background: `linear-gradient(to top, ${theme.canvas.background}66, transparent)` }"
      ></div>

      <!-- 四角缩放手柄：size-7（28px）透明热区，外侧 14px -->
      <div
        v-for="corner in resizeCorners"
        :key="corner.name"
        class="resize-handle"
        :class="'resize-' + corner.name"
        :style="{ cursor: corner.cursor }"
        @mousedown.stop.prevent="handleResizeStart($event, corner)"
      />
    </div>

    <!-- 左侧连线锚点（target）：size-12 热区 + size-3 圆形锚点 -->
    <div
      class="connection-handle connection-left"
      :class="{ 'is-visible': isLeftAnchorVisible }"
      @mousedown.stop="handleConnectStart($event, 'target')"
    >
      <div class="connection-dot" :style="connectionDotStyle"></div>
    </div>

    <!-- 右侧连线锚点（source）：config 节点不显示 -->
    <div
      v-if="panel.type !== 'config'"
      class="connection-handle connection-right"
      :class="{ 'is-visible': isRightAnchorVisible }"
      @mousedown.stop="handleConnectStart($event, 'source')"
    >
      <div class="connection-dot" :style="connectionDotStyle"></div>
    </div>
  </div>
</template>

<script setup lang="ts">
/* =====================================================
 * CanvasNode 画布节点组件
 * 1:1 复刻参考项目 infinite-canvas 的节点设计与图标
 *
 * 数据约定：panel.content 作为节点元数据（对应参考项目的 metadata）
 *   - content.content：文本内容 / 媒体 URL（图片/视频/音频）
 *   - content.status：'idle' | 'loading' | 'error' | 'success'
 *   - content.errorDetails：错误详情
 *   - content.fontSize：文本字体大小
 *   - content.naturalWidth/naturalHeight/bytes：图片元数据
 *   - content.freeResize：是否自由缩放（不保持比例）
 * ===================================================== */

import { computed, ref, nextTick, watch, onMounted, onUnmounted } from 'vue'
import { Image as ImageIcon, Video, Music2, RefreshCw } from 'lucide-vue-next'
import { InfoFilled } from '@element-plus/icons-vue'
import { useI18n } from '@/i18n'
import { useCanvasStore } from '@/stores/canvas'
import { useModelsStore } from '@/stores/models'
import WatermarkOverlay from '@/components/WatermarkOverlay.vue'

/* ---------- i18n ---------- */
const { t } = useI18n()

/* ---------- Props 定义 ---------- */
const props = defineProps({
  panel: { type: Object, required: true }, // { id, type, x, y, width, height, content, title, ... }
  selected: { type: Boolean, default: false },
  isConnecting: { type: Boolean, default: false }, // 是否正在拖拽连线
  showImageInfo: { type: Boolean, default: false }, // 是否显示图片信息条
  theme: { type: Object, required: true }, // 主题 token
  viewport: { type: Object, required: true }, // { x, y, zoom }
})

/* ---------- Emits 定义 ---------- */
const emit = defineEmits([
  'select',
  'drag-start',
  'drag',
  'drag-end',
  'resize-start',
  'resize',
  'resize-end',
  'start-connecting', // (anchorType: 'source' | 'target')
  'context-menu', // (event)
  'hover-enter',
  'hover-leave',
  'view-image', // (imageUrl)
  'edit-text', // (text)
  'generate-image', // 从 text 节点生图（保留用于 retry 等场景）
  'generate', // 从 config 节点触发合并生成
  'retry', // 重试生成
  'upload', // 上传文件
])

/* ---------- 常量 ---------- */
const MIN_WIDTH = 220 // 最小宽度
const MIN_HEIGHT = 160 // 最小高度

/* ---------- Store 实例（供 config 节点直接更新面板内容） ---------- */
const store = useCanvasStore()

/* ---------- 配置节点常量 ---------- */
// 生成模式：文生图 / 图生图 / 文生视频 / 图生视频（关键帧由接入图片数量自动触发）
const configModes = computed(() => [
  { value: 'text2image', label: t('canvas.node.configMode.text2image') },
  { value: 'image2image', label: t('canvas.node.configMode.image2image') },
  { value: 'text2video', label: t('canvas.node.configMode.text2video') },
  { value: 'image2video', label: t('canvas.node.configMode.image2video') },
])
// 模型列表：从后端 API 获取，按类型自动分类
const modelsStore = useModelsStore()
const availableModels = computed(() => modelsStore.getModelsByMode(configContent.value.mode || 'text2image'))
// 图片尺寸选项（结构化，含友好标签）
const imageSizeOptions = computed(() => {
  const opts = modelsStore.imageSizeOptions
  if (opts.length > 0) return opts
  // 兜底：从纯字符串列表生成
  return (modelsStore.imageSizes.length > 0 ? modelsStore.imageSizes : ['1024x1024', '768x1024', '1024x768', '1280x720'])
    .map(v => ({ value: v, w: 1, h: 1, label: v }))
})
// 视频宽高比选项（结构化，含友好标签）
const videoAspectRatioOptions = computed(() => {
  const config = modelsStore.getModelParamsConfig()
  return config.videoAspectRatios
})
// 视频分辨率选项（以高度为基准）
const videoResolutionOptions = computed(() => {
  const config = modelsStore.getModelParamsConfig()
  return config.videoResolutions || []
})
// 视频帧率选项
const videoFrameRateOptions = computed(() => {
  const config = modelsStore.getModelParamsConfig()
  return config.videoFrameRates
})
// 可用视频时长：根据帧率自动过滤（FPS 越高时长越短）
// 官方 Q&A 限制：24 FPS ≤ 15s；30 FPS ≤ 10s；60 FPS ≤ 5s
const availableDurations = computed(() => {
  const config = modelsStore.getModelParamsConfig()
  const fps = configContent.value.frame_rate || 24
  const maxDuration = fps >= 60 ? 5 : fps >= 30 ? 10 : 15
  return config.videoDurations.filter((s: number) => s <= maxDuration)
})

/* ---------- 响应式状态 ---------- */
const hovered = ref(false) // 是否悬停
const isEditingContent = ref(false) // 是否正在编辑文本
const textareaRef = ref<HTMLTextAreaElement | null>(null) // 文本编辑区引用

/* ---------- 四角缩放手柄配置 ---------- */
const resizeCorners = [
  { name: 'top-left', cursor: 'nwse-resize', dx: -1, dy: -1 },
  { name: 'top-right', cursor: 'nesw-resize', dx: 1, dy: -1 },
  { name: 'bottom-left', cursor: 'nesw-resize', dx: -1, dy: 1 },
  { name: 'bottom-right', cursor: 'nwse-resize', dx: 1, dy: 1 },
]

/* ---------- 计算属性 ---------- */

/** 节点元数据（统一访问 panel.content） */
const metadata = computed(() => props.panel.content || {})

/** 是否有图片内容 */
const hasImageContent = computed(
  () => props.panel.type === 'image' && Boolean(metadata.value.content),
)

/** 是否有视频内容 */
const hasVideoContent = computed(
  () => props.panel.type === 'video' && Boolean(metadata.value.content),
)

/** 是否有音频内容 */
const hasAudioContent = computed(
  () => props.panel.type === 'audio' && Boolean(metadata.value.content),
)

/** 是否处于激活态（选中） */
const isActive = computed(() => props.selected)

/** 图片边框颜色：选中蓝色 / 否则 muted */
const imageBorderColor = computed(() => {
  if (isActive.value) return props.theme.canvas.selectionStroke
  return props.theme.node.muted
})

/** 节点根容器样式：世界坐标 transform + 尺寸 + z-index */
const nodeStyle = computed(() => ({
  transform: `translate(${props.panel.x}px, ${props.panel.y}px)`,
  width: props.panel.width + 'px',
  height: props.panel.height + 'px',
  zIndex: props.selected ? 50 : 10,
}))

/** 节点外壳样式：背景 + 边框颜色 + 选中阴影 */
const shellStyle = computed(() => {
  const isMedia = hasImageContent.value || hasVideoContent.value
  const background = isMedia ? 'transparent' : props.theme.node.fill
  let borderColor
  if (hasImageContent.value) {
    borderColor = imageBorderColor.value
  } else if (isActive.value) {
    borderColor = props.theme.canvas.selectionStroke
  } else {
    borderColor = props.theme.node.stroke
  }
  const boxShadow = isActive.value ? `0 0 0 1px ${props.theme.canvas.selectionStroke}55` : undefined
  return { background, borderColor, boxShadow }
})

/** 内容区包裹样式：媒体节点背景透明 */
const contentWrapStyle = computed(() => {
  const isMedia = hasImageContent.value || hasVideoContent.value
  return { background: isMedia ? 'transparent' : props.theme.node.fill }
})

/** 文本样式：字体大小 + 行高 + 颜色 */
const textStyle = computed(() => {
  const fontSize = metadata.value.fontSize || 14
  return {
    fontSize: `${fontSize}px`,
    lineHeight: `${Math.round(fontSize * 1.65)}px`,
    color: props.theme.node.text,
  }
})

/** 加载旋转圈样式：边框颜色 */
const loadingSpinnerStyle = computed(() => ({
  borderColor: props.theme.node.stroke,
  borderTopColor: props.theme.node.activeStroke,
}))

/** 重试按钮样式 */
const retryBtnStyle = computed(() => ({
  background: props.theme.toolbar.panel,
  borderColor: props.theme.toolbar.border,
  color: props.theme.node.text,
}))

/** 连线锚点圆点样式 */
const connectionDotStyle = computed(() => ({
  background: props.theme.node.panel,
  borderColor: props.theme.node.muted,
}))

/** 左侧锚点是否可见：hover/选中/连线中 */
const isLeftAnchorVisible = computed(
  () => hovered.value || props.selected || props.isConnecting,
)

/** 右侧锚点是否可见：config 节点不显示 */
const isRightAnchorVisible = computed(
  () =>
    props.panel.type !== 'config' &&
    (hovered.value || props.selected || props.isConnecting),
)

/** 图片信息：宽度 */
const imageInfoWidth = computed(
  () => Math.round(metadata.value.naturalWidth || props.panel.width),
)

/** 图片信息：高度 */
const imageInfoHeight = computed(
  () => Math.round(metadata.value.naturalHeight || props.panel.height),
)

/** 图片信息：文件大小（格式化） */
const imageInfoSize = computed(() => formatBytes(metadata.value.bytes || 0))

/* ---------- 配置节点计算属性 ---------- */

/** 配置节点内容（从 panel.content 读取，带默认值） */
const configContent = computed(() => ({
  mode: 'text2image',
  model: modelsStore.defaultImageModel,
  size: '1024x1024',
  prompt: '',
  generating: false,
  progress: 0,
  // 视频参数默认值
  aspect_ratio: modelsStore.defaultVideoAspectRatio,
  resolution: modelsStore.defaultVideoResolution,
  frame_rate: modelsStore.defaultFrameRate,
  seconds: modelsStore.defaultVideoDuration,
  ...(props.panel.content || {}),
}))

/** 是否为图片模式（含 text2image / image2image，且非视频） */
const isImageMode = computed(
  () => configContent.value.mode?.includes('image') && !configContent.value.mode?.includes('video'),
)

/** 是否为视频模式（text2video / image2video，关键帧由接入图片数量自动触发） */
const isVideoMode = computed(() => configContent.value.mode?.includes('video'))

/** 提示词双向绑定：get 读 configContent.prompt，set 调 updateConfigContent */
const configPrompt = computed({
  get: () => configContent.value.prompt || '',
  set: (val) => updateConfigContent('prompt', val),
})

/* ---------- 工具函数 ---------- */

/** 格式化字节数为可读字符串 */
function formatBytes(bytes: number) {
  if (!Number.isFinite(bytes) || bytes <= 0) return ''
  const units = ['B', 'KB', 'MB', 'GB']
  let value = bytes
  let unitIndex = 0
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024
    unitIndex += 1
  }
  return `${value >= 10 || unitIndex === 0 ? value.toFixed(0) : value.toFixed(1)} ${units[unitIndex]}`
}

/* ---------- 交互：拖拽移动 ---------- */

/** 鼠标按下：开始拖拽节点 */
function handleMouseDown(event: MouseEvent) {
  // 输入类元素不拦截，让元素正常工作
  const tag = (event.target instanceof Element ? event.target.tagName : '') || ''
  if (['INPUT', 'TEXTAREA', 'BUTTON', 'SELECT'].includes(tag)) return

  emit('select', props.panel.id)
  emit('drag-start', { id: props.panel.id, event })

  const startClientX = event.clientX
  const startClientY = event.clientY
  const startX = props.panel.x
  const startY = props.panel.y
  const zoom = props.viewport?.zoom || 1

  function onMove(ev: MouseEvent) {
    // 屏幕坐标差 → 世界坐标差
    const screenDx = ev.clientX - startClientX
    const screenDy = ev.clientY - startClientY
    const worldDx = screenDx / zoom
    const worldDy = screenDy / zoom
    emit('drag', {
      id: props.panel.id,
      x: startX + worldDx,
      y: startY + worldDy,
    })
  }

  function onUp() {
    window.removeEventListener('mousemove', onMove)
    window.removeEventListener('mouseup', onUp)
    emit('drag-end', { id: props.panel.id })
  }

  window.addEventListener('mousemove', onMove)
  window.addEventListener('mouseup', onUp)
}

/* ---------- 交互：缩放（四角手柄） ---------- */

/** 缩放手柄按下：开始缩放 */
function handleResizeStart(event: MouseEvent, corner: any) {
  event.stopPropagation()
  event.preventDefault()

  emit('resize-start', { id: props.panel.id, corner: corner.name })

  const startClientX = event.clientX
  const startClientY = event.clientY
  const startLeft = props.panel.x
  const startTop = props.panel.y
  const startWidth = props.panel.width
  const startHeight = props.panel.height
  const zoom = props.viewport?.zoom || 1

  // 是否保持比例：图片节点（非自由缩放）和视频节点保持比例
  const keepRatio =
    (props.panel.type === 'image' && !metadata.value.freeResize) ||
    props.panel.type === 'video'
  const ratio =
    (metadata.value.naturalWidth || startWidth) /
    (metadata.value.naturalHeight || startHeight || 1)

  const startRight = startLeft + startWidth
  const startBottom = startTop + startHeight
  const fromLeft = corner.dx === -1
  const fromTop = corner.dy === -1

  function onMove(ev: MouseEvent) {
    // 屏幕坐标差 → 世界坐标差
    const dx = (ev.clientX - startClientX) / zoom
    const dy = (ev.clientY - startClientY) / zoom

    // 计算原始宽高（限制最小尺寸）
    let width = Math.max(MIN_WIDTH, startWidth + (fromLeft ? -dx : dx))
    let height = Math.max(MIN_HEIGHT, startHeight + (fromTop ? -dy : dy))

    // 保持比例：以主导方向为准
    if (keepRatio) {
      if (Math.abs(dx) >= Math.abs(dy)) {
        height = width / ratio
      } else {
        width = height * ratio
      }
      // 限制最小尺寸后重新计算
      if (height < MIN_HEIGHT) {
        height = MIN_HEIGHT
        width = height * ratio
      }
      if (width < MIN_WIDTH) {
        width = MIN_WIDTH
        height = width / ratio
      }
    }

    // 计算新位置（左侧/上侧拖动时位置反向移动）
    const x = fromLeft ? startRight - width : startLeft
    const y = fromTop ? startBottom - height : startTop

    emit('resize', { id: props.panel.id, width, height, x, y })
  }

  function onUp() {
    window.removeEventListener('mousemove', onMove)
    window.removeEventListener('mouseup', onUp)
    emit('resize-end', { id: props.panel.id })
  }

  window.addEventListener('mousemove', onMove)
  window.addEventListener('mouseup', onUp)
}

/* ---------- 交互：连线锚点 ---------- */

/** 连线锚点按下：开始连线 */
function handleConnectStart(event: MouseEvent, anchorType: string) {
  event.stopPropagation()
  emit('start-connecting', anchorType)
}

/* ---------- 交互：媒体元数据读取 ---------- */

/** 图片加载完成：读取原始像素尺寸写回 store，避免显示 340×240 这种画布缩放尺寸 */
function onImageLoad(e: Event) {
  const img = e.target as HTMLImageElement
  if (!img?.naturalWidth || !img?.naturalHeight) return
  const panel = props.panel
  // 如果已经有正确的元数据就不用重复写，避免无意义的 store 更新
  if (
    panel.content?.naturalWidth === img.naturalWidth
    && panel.content?.naturalHeight === img.naturalHeight
  ) {
    return
  }
  store.updatePanel(panel.id, {
    content: { naturalWidth: img.naturalWidth, naturalHeight: img.naturalHeight },
  })
}

/** 视频元数据加载完成：读取原始像素尺寸写回 store */
function onVideoMetadataLoaded(e: Event) {
  const video = e.target as HTMLVideoElement
  if (!video?.videoWidth || !video?.videoHeight) return
  const panel = props.panel
  if (
    panel.content?.naturalWidth === video.videoWidth
    && panel.content?.naturalHeight === video.videoHeight
  ) {
    return
  }
  store.updatePanel(panel.id, {
    content: { naturalWidth: video.videoWidth, naturalHeight: video.videoHeight },
  })
}

/* ---------- 交互：双击 ---------- */

/** 双击：图片查看大图 / 文本进入编辑 */
function handleDoubleClick(event: MouseEvent) {
  // 图片节点：双击查看大图
  if (props.panel.type === 'image' && hasImageContent.value) {
    event.stopPropagation()
    emit('view-image', metadata.value.content)
    return
  }
  // 文本节点：双击进入编辑
  if (props.panel.type !== 'text') return
  event.stopPropagation()
  isEditingContent.value = true
  nextTick(() => {
    const textarea = textareaRef.value
    if (textarea) {
      textarea.focus()
      textarea.setSelectionRange(textarea.value.length, textarea.value.length)
    }
  })
}

/* ---------- 交互：文本编辑 ---------- */

/** 文本输入：emit edit-text */
function handleContentInput(event: Event) {
  const value = (event.target as HTMLTextAreaElement)?.value
  emit('edit-text', value)
}

/** 停止编辑 */
function stopEditing() {
  isEditingContent.value = false
}

/* ---------- 外部触发文本编辑（通过 store.editingPanelId） ---------- */
// 当 store.editingPanelId 等于本节点 id 时，自动进入文本编辑模式
watch(
  () => store.editingPanelId,
  (newId) => {
    if (newId === props.panel.id && props.panel.type === 'text') {
      isEditingContent.value = true
      nextTick(() => {
        const textarea = textareaRef.value
        if (textarea) {
          textarea.focus()
          textarea.setSelectionRange(textarea.value.length, textarea.value.length)
        }
      })
      // 触发后清空，避免重复触发
      store.editingPanelId = null
    }
  },
)

/* ---------- 交互：快速生成 / 重试 ---------- */

/** 点击重试按钮 */
function handleRetry() {
  emit('retry', props.panel)
}

/* ---------- 交互：配置节点 ---------- */

/** 更新配置节点内容，切换模式时自动切换对应类型的默认模型 */
function updateConfigContent(key: string, value: any) {
  const updates: Record<string, any> = { [key]: value }
  // 切换模式时自动切换模型
  if (key === 'mode') {
    const currentModel = configContent.value.model
    const targetModels = modelsStore.getModelsByMode(value)
    const targetIds = targetModels.map((m) => m.id)
    // 当前模型不在目标列表中时，自动切到该类型默认模型
    if (!targetIds.includes(currentModel)) {
      updates.model = modelsStore.getDefaultModelByMode(value)
    }
  }
  store.updatePanel(props.panel.id, { content: updates })
}

/** 帧率变化：如果当前时长超过新帧率的最大限制，自动调整为最大可用时长 */
function onFrameRateChange(newFps: number) {
  const updates: Record<string, any> = { frame_rate: newFps }
  const maxDuration = newFps >= 60 ? 5 : newFps >= 30 ? 10 : 15
  const currentSeconds = configContent.value.seconds
  if (currentSeconds > maxDuration) {
    updates.seconds = maxDuration
  }
  store.updatePanel(props.panel.id, { content: updates })
}

/** 点击配置节点的生成按钮：emit generate 事件交由父组件执行生成流程 */
function handleConfigGenerate() {
  emit('generate', props.panel)
}

/* ---------- 交互：hover / 右键菜单 ---------- */

/** 鼠标进入：触发 hover-enter */
function handleMouseEnter() {
  hovered.value = true
  emit('hover-enter', props.panel.id)
}

/** 鼠标离开：触发 hover-leave */
function handleMouseLeave() {
  hovered.value = false
  emit('hover-leave', props.panel.id)
}

/** 右键菜单 */
function handleContextMenu(event: MouseEvent) {
  emit('context-menu', event)
}

/* ---------- 编辑态外部点击关闭 ---------- */

/** 外部点击：关闭文本编辑 */
function handleOutsidePointerDown(event: PointerEvent) {
  if (!isEditingContent.value) return
  const target = event.target as Node | null
  if (textareaRef.value && target && textareaRef.value.contains(target)) return
  isEditingContent.value = false
}

onMounted(() => {
  if (typeof window !== 'undefined') {
    window.addEventListener('pointerdown', handleOutsidePointerDown, true)
  }
})

onUnmounted(() => {
  if (typeof window !== 'undefined') {
    window.removeEventListener('pointerdown', handleOutsidePointerDown, true)
  }
})
</script>

<style scoped>
/* ===== 节点根容器 ===== */
.canvas-node {
  position: absolute;
  display: flex;
  flex-direction: column;
  user-select: none;
  transition: box-shadow 200ms ease;
  contain: layout style;
  will-change: transform;
}

/* ===== 节点外壳：rounded-3xl + border-2 ===== */
.node-shell {
  position: relative;
  width: 100%;
  height: 100%;
  overflow: visible;
  border-radius: 24px;
  border: 2px solid;
  transition: box-shadow 200ms ease;
}

/* ===== 内容区包裹 ===== */
.node-content-wrap {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
  border-radius: inherit;
  overflow: hidden;
}

/* ===== 加载状态：旋转加载圈 + "生成中"文字 ===== */
.node-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  width: 100%;
  height: 100%;
}

.loading-spinner {
  width: 40px;
  height: 40px;
  border: 2px solid;
  border-radius: 50%;
  animation: canvas-node-spin 1s linear infinite;
}

.loading-text {
  font-size: 10px;
  letter-spacing: 0.2em;
}

@keyframes canvas-node-spin {
  to {
    transform: rotate(360deg);
  }
}

/* ===== 错误状态：红色错误文字 + 重试按钮 ===== */
.node-error {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  max-width: 260px;
  padding: 0 20px;
  text-align: center;
}

.error-text {
  font-size: 12px;
  line-height: 20px;
  color: var(--agnes-error);
}

.retry-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 32px;
  padding: 0 12px;
  border-radius: 9999px;
  border: 1px solid;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: transform 0.15s ease;
}

.retry-btn:hover {
  transform: scale(1.02);
}

/* ===== 文本节点 ===== */
.text-content {
  display: flex;
  flex-direction: column;
  width: 100%;
  height: 100%;
  overflow: hidden;
}

/* 文本编辑区 / 展示区 */
.text-textarea,
.text-display {
  display: block;
  width: 100%;
  height: 100%;
  overflow-y: auto;
  white-space: pre-wrap;
  word-break: break-word;
  overflow-wrap: break-word;
  background: transparent;
  padding: 16px;
  font-family: monospace;
  box-sizing: border-box;
}

.text-textarea {
  border: none;
  outline: none;
  resize: none;
  appearance: none;
  user-select: text;
}

/* ===== 图片节点 ===== */
.image-content {
  width: 100%;
  height: 100%;
}

.image-img {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: contain;
  pointer-events: none;
  user-select: none;
}

.image-img.object-fill {
  object-fit: fill;
}

/* ===== 视频节点 ===== */
.video-content {
  width: 100%;
  height: 100%;
}

.video-player {
  width: 100%;
  height: 100%;
  border-radius: 18px;
  background: var(--agnes-bg-dark-surface);
  object-fit: contain;
}

/* ===== 音频节点 ===== */
.audio-content {
  width: 100%;
  height: 100%;
}

.audio-player-wrap {
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 12px;
  width: 100%;
  height: 100%;
  padding: 0 16px;
  box-sizing: border-box;
}

.audio-info {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  opacity: 0.7;
  min-width: 0;
}

.audio-title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.audio-player {
  width: 100%;
}

/* ===== 配置节点：生成配置面板 ===== */
.config-content {
  display: flex;
  flex-direction: column;
  gap: 10px;
  width: 100%;
  height: 100%;
  padding: 12px;
  box-sizing: border-box;
}

/* 上半部分可滚动区域：参数 + 提示词 */
.config-scroll-area {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
  overflow-y: auto;
  overflow-x: hidden;
  padding-right: 2px;
}

/* 自定义滚动条：更细更淡，不干扰视觉 */
.config-scroll-area::-webkit-scrollbar {
  width: 4px;
}
.config-scroll-area::-webkit-scrollbar-track {
  background: transparent;
}
.config-scroll-area::-webkit-scrollbar-thumb {
  background: var(--agnes-border);
  border-radius: 2px;
}
.config-scroll-area::-webkit-scrollbar-thumb:hover {
  background: var(--agnes-text-faint);
}

/* 生成模式切换标签栏 */
.config-mode-tabs {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
}

.config-mode-tab {
  flex: 1;
  min-width: 60px;
  height: 28px;
  padding: 0 8px;
  border-radius: 8px;
  border: 1px solid var(--agnes-border);
  background: transparent;
  font-size: 11px;
  font-weight: 500;
  color: inherit;
  cursor: pointer;
  transition: background 0.15s ease, border-color 0.15s ease;
  white-space: nowrap;
}

.config-mode-tab:hover {
  background: var(--agnes-nav-hover-bg);
}

.config-mode-tab.active {
  background: var(--agnes-info-bg);
  border-color: var(--agnes-primary);
  color: var(--agnes-primary);
}

/* 下拉选择框 */
.config-select {
  height: 30px;
  padding: 0 8px;
  border-radius: 8px;
  border: 1px solid var(--agnes-border);
  background: var(--agnes-bg-input);
  font-size: 12px;
  color: inherit;
  cursor: pointer;
  outline: none;
  box-sizing: border-box;
}

.config-select:focus {
  border-color: var(--agnes-primary);
}

/* 视频参数区：分辨率+比例 / 帧率+时长，两行两列网格布局 */
.config-video-params {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}

.config-video-params .config-select {
  width: 100%;
  min-width: 0;
}

/* 关键帧模式开关行 */
.keyframes-toggle-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 4px;
  padding: 6px 8px;
  background: var(--agnes-bg-secondary);
  border-radius: 6px;
  font-size: 12px;
}
.keyframes-toggle-row .toggle-label {
  color: var(--agnes-text-primary);
  font-weight: 500;
}
.keyframes-toggle-row .info-icon {
  font-size: 13px;
  color: var(--agnes-text-tertiary);
  cursor: help;
  margin-left: auto;
}
.keyframes-toggle-row .info-icon:hover {
  color: var(--agnes-primary);
}

/* 提示词输入框 */
.config-prompt {
  flex: 1;
  min-height: 120px;
  padding: 8px 10px;
  border-radius: 8px;
  border: 1px solid var(--agnes-border);
  background: var(--agnes-bg-input);
  font-size: 12px;
  font-family: monospace;
  color: inherit;
  resize: vertical;
  outline: none;
  box-sizing: border-box;
  line-height: 1.6;
  overflow-y: auto;
}

.config-prompt:focus {
  border-color: var(--agnes-primary);
}

.config-prompt::placeholder {
  color: var(--agnes-text-faint);
}

/* 生成按钮（底部固定，不随内容滚动消失） */
.config-generate-btn {
  flex-shrink: 0;
  height: 38px;
  border-radius: 10px;
  border: 1px solid var(--agnes-primary);
  background: var(--agnes-info-bg);
  font-size: 13px;
  font-weight: 600;
  color: var(--agnes-primary);
  cursor: pointer;
  transition: background 0.15s ease, transform 0.15s ease, box-shadow 0.15s ease;
  margin-top: auto;
}

.config-generate-btn:hover {
  background: var(--agnes-primary);
  color: #fff;
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(47, 128, 255, 0.25);
}

.config-generate-btn:active {
  transform: translateY(0);
}

/* ===== 未知节点 ===== */
.unknown-content {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
  font-size: 14px;
}

/* ===== 空状态：图标 + 文字 ===== */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  width: 100%;
  height: 100%;
}

.empty-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 56px;
  height: 56px;
  border-radius: 16px;
  opacity: 0.3;
}

.empty-text {
  font-size: 10px;
  letter-spacing: 0.18em;
  opacity: 0.5;
}

.empty-text-sm {
  font-size: 14px;
  letter-spacing: normal;
  opacity: 0.35;
}

/* ===== 图片信息条：尺寸·大小 ===== */
.image-info-bar {
  position: absolute;
  bottom: 12px;
  right: 12px;
  z-index: 40;
  max-width: calc(100% - 24px);
  pointer-events: none;
}

.image-info-text {
  display: inline-block;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  border-radius: 6px;
  background: var(--agnes-bg-dark-surface);
  padding: 4px 8px;
  font-size: 11px;
  font-weight: 500;
  line-height: 1;
  color: white;
  backdrop-filter: blur(4px);
}

/* ===== 底部渐变遮罩（非媒体节点） ===== */
.bottom-gradient {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  height: 48px;
  pointer-events: none;
}

/* ===== 四角缩放手柄：size-7（28px）透明热区，外侧 14px ===== */
.resize-handle {
  position: absolute;
  z-index: 50;
  width: 28px;
  height: 28px;
}

.resize-top-left {
  left: -14px;
  top: -14px;
}

.resize-top-right {
  right: -14px;
  top: -14px;
}

.resize-bottom-left {
  left: -14px;
  bottom: -14px;
}

.resize-bottom-right {
  right: -14px;
  bottom: -14px;
}

/* ===== 连线锚点：size-12（48px）热区 + size-3（12px）圆形锚点 ===== */
.connection-handle {
  position: absolute;
  top: 50%;
  z-index: 30;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 48px;
  height: 48px;
  transform: translateY(-50%);
  cursor: crosshair;
  transition: opacity 150ms ease;
  opacity: 0;
  pointer-events: none;
}

.connection-handle.is-visible {
  opacity: 1;
  pointer-events: auto;
}

/* 左侧锚点：圆点位于节点外侧 6px（热区中心在 -6px） */
.connection-left {
  left: -30px;
}

/* 右侧锚点：圆点位于节点外侧 6px */
.connection-right {
  right: -30px;
}

.connection-dot {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  border: 2px solid;
  transition: transform 0.15s ease;
}

.connection-dot:hover {
  transform: scale(1.25);
}
</style>
