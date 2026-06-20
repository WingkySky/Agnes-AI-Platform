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
          <span class="loading-text">生成中</span>
        </div>

        <!-- 错误状态：红色错误文字 + 重试按钮 -->
        <div v-else-if="metadata.status === 'error'" class="node-error">
          <div class="error-text">{{ metadata.errorDetails || '生成失败' }}</div>
          <button
            type="button"
            class="retry-btn"
            :style="retryBtnStyle"
            @click.stop="handleRetry"
            @mousedown.stop
          >
            <RefreshCw :size="14" />
            重试
          </button>
        </div>

        <!-- 文本节点：可编辑文本区 + 右上角"生图"按钮 -->
        <div v-else-if="panel.type === 'text'" class="text-content">
          <!-- 生图按钮（Image 图标 + 文字） -->
          <button
            type="button"
            class="generate-btn"
            :style="generateBtnStyle"
            @click.stop="handleGenerateImage"
            @mousedown.stop
            @pointerdown.stop
            title="用文本生图"
            aria-label="用文本生图"
          >
            <ImageIcon :size="14" />
            生图
          </button>
          <!-- 编辑态：textarea -->
          <textarea
            v-if="isEditingContent"
            ref="textareaRef"
            class="text-textarea"
            :style="textStyle"
            :value="metadata.content || ''"
            placeholder="双击编辑文字"
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
            <span v-else :style="{ color: theme.node.placeholder }">双击编辑文字</span>
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
            <span class="empty-text">空图片节点</span>
          </div>
          <!-- 有图：显示图片（object-contain） -->
          <img
            v-else
            :src="metadata.content"
            :alt="panel.title || ''"
            class="image-img"
            :class="{ 'object-fill': metadata.freeResize }"
            draggable="false"
            @dragstart.prevent
          />
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
            <span class="empty-text empty-text-sm">空视频节点</span>
          </div>
          <!-- 有视频：video 播放器 -->
          <video
            v-else
            :src="metadata.content"
            controls
            class="video-player"
            data-canvas-no-zoom
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
            <span class="empty-text empty-text-sm">空音频节点</span>
          </div>
          <!-- 有音频：音频信息 + audio 播放器 -->
          <div
            v-else
            class="audio-player-wrap"
            :style="{ background: theme.node.fill, color: theme.node.text }"
          >
            <div class="audio-info">
              <Music2 :size="16" />
              <span class="audio-title">{{ panel.title || '音频' }}</span>
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

          <!-- 模型选择 -->
          <select
            class="config-select"
            :value="configContent.model"
            @change="updateConfigContent('model', ($event.target as HTMLSelectElement)?.value)"
            @mousedown.stop
          >
            <option v-for="m in availableModels" :key="m" :value="m">{{ m }}</option>
          </select>

          <!-- 尺寸选择（图片模式） -->
          <select
            v-if="isImageMode"
            class="config-select"
            :value="configContent.size"
            @change="updateConfigContent('size', ($event.target as HTMLSelectElement)?.value)"
            @mousedown.stop
          >
            <option v-for="s in availableSizes" :key="s" :value="s">{{ s }}</option>
          </select>

          <!-- 视频参数（视频模式）：比例 + 时长 -->
          <div v-if="isVideoMode" class="config-video-params">
            <select
              class="config-select"
              :value="configContent.aspect_ratio"
              @change="updateConfigContent('aspect_ratio', ($event.target as HTMLSelectElement)?.value)"
              @mousedown.stop
            >
              <option v-for="r in ['16:9','9:16','1:1','4:3']" :key="r" :value="r">{{ r }}</option>
            </select>
            <select
              class="config-select"
              :value="configContent.seconds"
              @change="updateConfigContent('seconds', ($event.target as HTMLSelectElement)?.value)"
              @mousedown.stop
            >
              <option v-for="s in [3,5,8,10]" :key="s" :value="s">{{ s }}秒</option>
            </select>
          </div>

          <!-- 提示词输入 -->
          <textarea
            class="config-prompt"
            v-model="configPrompt"
            placeholder="输入提示词，可用 @[node:xxx] 引用上游节点"
            @mousedown.stop
            @wheel.stop
          />

          <!-- 生成按钮（异步操作，点击后不阻塞，可连续点击） -->
          <button
            type="button"
            class="config-generate-btn"
            @click="handleConfigGenerate"
            @mousedown.stop
          >
            {{ isVideoMode ? '生成视频' : '生成图片' }}
          </button>
        </div>

        <!-- 未知节点类型 -->
        <div
          v-else
          class="unknown-content"
          :style="{ color: theme.node.placeholder }"
        >
          未知节点
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
import { useCanvasStore } from '@/stores/canvas'

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
  'generate-image', // 从 text 节点生图
  'generate', // 从 config 节点触发合并生成
  'retry', // 重试生成
  'upload', // 上传文件
])

/* ---------- 常量 ---------- */
const SELECTION_BLUE = '#2f80ff' // 选中态蓝色
const MIN_WIDTH = 220 // 最小宽度
const MIN_HEIGHT = 160 // 最小高度

/* ---------- Store 实例（供 config 节点直接更新面板内容） ---------- */
const store = useCanvasStore()

/* ---------- 配置节点常量 ---------- */
// 生成模式：文生图 / 图生图 / 文生视频 / 图生视频
const configModes = [
  { value: 'text2image', label: '文生图' },
  { value: 'image2image', label: '图生图' },
  { value: 'text2video', label: '文生视频' },
  { value: 'image2video', label: '图生视频' },
]
// 可用模型列表
const availableModels = ['agnes-image-2.1-flash', 'agnes-image-2.1', 'agnes-video-v2.0']
// 可用图片尺寸
const availableSizes = ['1024x1024', '768x1024', '1024x768', '768x768']

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
  if (isActive.value) return SELECTION_BLUE
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
    borderColor = SELECTION_BLUE
  } else {
    borderColor = props.theme.node.stroke
  }
  const boxShadow = isActive.value ? `0 0 0 1px ${SELECTION_BLUE}55` : undefined
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

/** 生图按钮样式 */
const generateBtnStyle = computed(() => ({
  background: `${props.theme.toolbar.panel}dd`,
  borderColor: props.theme.node.stroke,
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
  model: 'agnes-image-2.1-flash',
  size: '1024x1024',
  prompt: '',
  generating: false,
  progress: 0,
  ...(props.panel.content || {}),
}))

/** 是否为图片模式（含 text2image / image2image，且非视频） */
const isImageMode = computed(
  () => configContent.value.mode?.includes('image') && !configContent.value.mode?.includes('video'),
)

/** 是否为视频模式（含 text2video / image2video） */
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

/* ---------- 交互：生图 / 重试 ---------- */

/** 点击生图按钮 */
function handleGenerateImage() {
  emit('generate-image', props.panel)
}

/** 点击重试按钮 */
function handleRetry() {
  emit('retry', props.panel)
}

/* ---------- 交互：配置节点 ---------- */

/** 更新配置节点内容字段（直接调用 store 更新） */
function updateConfigContent(key: string, value: any) {
  store.updatePanel(props.panel.id, { content: { [key]: value } })
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
  color: #fca5a5;
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
  padding-top: 32px;
}

/* 生图按钮：右上角，Image 图标 + 文字 */
.generate-btn {
  position: absolute;
  right: 12px;
  top: 12px;
  z-index: 20;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  height: 32px;
  padding: 0 10px;
  border-radius: 9999px;
  border: 1px solid;
  font-size: 12px;
  font-weight: 500;
  opacity: 0.85;
  backdrop-filter: blur(12px);
  cursor: pointer;
  transition: transform 0.15s ease, opacity 0.15s ease;
}

.generate-btn:hover {
  transform: scale(1.02);
  opacity: 1;
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
  padding: 0 56px 16px 16px;
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
  background: black;
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
  gap: 8px;
  width: 100%;
  height: 100%;
  padding: 12px;
  box-sizing: border-box;
  overflow-y: auto;
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
  border: 1px solid rgba(120, 170, 230, 0.2);
  background: transparent;
  font-size: 11px;
  font-weight: 500;
  color: inherit;
  cursor: pointer;
  transition: background 0.15s ease, border-color 0.15s ease;
  white-space: nowrap;
}

.config-mode-tab:hover {
  background: rgba(120, 170, 255, 0.1);
}

.config-mode-tab.active {
  background: rgba(107, 156, 255, 0.2);
  border-color: #6b9cff;
  color: #6b9cff;
}

/* 下拉选择框 */
.config-select {
  height: 30px;
  padding: 0 8px;
  border-radius: 8px;
  border: 1px solid rgba(120, 170, 230, 0.2);
  background: rgba(15, 22, 38, 0.6);
  font-size: 12px;
  color: inherit;
  cursor: pointer;
  outline: none;
  box-sizing: border-box;
}

.config-select:focus {
  border-color: #6b9cff;
}

/* 视频参数行：比例 + 时长并排 */
.config-video-params {
  display: flex;
  gap: 8px;
}

.config-video-params .config-select {
  flex: 1;
}

/* 提示词输入框 */
.config-prompt {
  flex: 1;
  min-height: 60px;
  padding: 8px;
  border-radius: 8px;
  border: 1px solid rgba(120, 170, 230, 0.2);
  background: rgba(15, 22, 38, 0.6);
  font-size: 12px;
  font-family: monospace;
  color: inherit;
  resize: none;
  outline: none;
  box-sizing: border-box;
  line-height: 1.5;
}

.config-prompt:focus {
  border-color: #6b9cff;
}

.config-prompt::placeholder {
  color: rgba(107, 132, 170, 0.6);
}

/* 生成按钮 */
.config-generate-btn {
  height: 34px;
  border-radius: 10px;
  border: 1px solid #6b9cff;
  background: rgba(107, 156, 255, 0.2);
  font-size: 13px;
  font-weight: 600;
  color: #6b9cff;
  cursor: pointer;
  transition: background 0.15s ease, transform 0.15s ease;
}

.config-generate-btn:hover {
  background: rgba(107, 156, 255, 0.35);
  transform: scale(1.01);
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
  background: rgba(0, 0, 0, 0.55);
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
