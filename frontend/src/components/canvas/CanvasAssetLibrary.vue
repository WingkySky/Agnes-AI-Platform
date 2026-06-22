<!--
  CanvasAssetLibrary.vue
  画布素材库面板（重新设计版）
  - 右侧滑出大面板，宽度 420px，高度占满画布
  - 双 Tab：生成历史（后端 API 分页） + 我的素材（localforage 本地）
  - 类型筛选：全部 / 图片 / 视频（切换时重新请求后端）
  - 网格布局展示缩略图（完整显示不裁剪，固定高度），点击创建画布节点
  - 鼠标悬浮卡片时通过 Teleport 到 body 显示放大预览（position: fixed）
  - 历史记录用分页（上一页/下一页），避免一次性加载过多数据
  - 视频历史记录用后端缩略图接口，避免直接加载完整视频
  - 本地素材支持删除 + 上传新素材
-->

<template>
  <div
    class="asset-library-panel"
    :class="{ 'drag-over': isDragOver }"
    :style="panelStyle"
    @dragover.prevent="onPanelDragOver"
    @dragenter.prevent="onPanelDragEnter"
    @dragleave.prevent="onPanelDragLeave"
    @drop.prevent="onPanelDrop"
  >
    <!-- 标题栏 -->
    <div class="asset-header">
      <div class="asset-title-wrap">
        <span class="asset-title">素材库</span>
        <span class="asset-subtitle">{{ activeTab === 'history' ? '生成历史' : '本地素材' }}</span>
      </div>
      <button class="asset-close" @click="$emit('close')">
        <X :size="18" />
      </button>
    </div>

    <!-- 来源 Tab 切换 -->
    <div class="asset-tabs">
      <button
        :class="['asset-tab', { active: activeTab === 'history' }]"
        @click="switchTab('history')"
      >
        <History :size="14" />
        <span>生成历史</span>
      </button>
      <button
        :class="['asset-tab', { active: activeTab === 'local' }]"
        @click="switchTab('local')"
      >
        <FolderOpen :size="14" />
        <span>我的素材</span>
      </button>
    </div>

    <!-- 类型筛选 + 操作区 -->
    <div class="asset-toolbar">
      <div class="asset-filters">
        <button
          v-for="f in filters"
          :key="f.value"
          :class="['asset-filter-btn', { active: currentFilter === f.value }]"
          @click="setFilter(f.value)"
        >
          {{ f.label }}
        </button>
      </div>
      <!-- 本地素材：上传按钮 -->
      <button
        v-if="activeTab === 'local'"
        class="asset-upload-btn"
        @click="triggerUpload"
      >
        <Upload :size="14" />
        <span>上传</span>
      </button>
    </div>

    <!-- 素材网格 -->
    <div class="asset-grid" ref="gridRef">
      <!-- 加载中（首次） -->
      <div v-if="loading && displayItems.length === 0" class="asset-loading">
        <Loader2 :size="24" class="spin-icon" />
        <span>加载中...</span>
      </div>

      <!-- 空状态 -->
      <div v-else-if="displayItems.length === 0" class="asset-empty">
        <Inbox :size="40" />
        <span>{{ emptyText }}</span>
        <span v-if="activeTab === 'local'" class="asset-empty-hint">
          点击上方"上传"按钮，或在画布节点上点击"存素材"按钮
        </span>
      </div>

      <!-- 网格内容 -->
      <div
        v-for="item in displayItems"
        :key="item.uid"
        class="asset-card"
        :title="item.name"
        draggable="true"
        @click="$emit('use-asset', item)"
        @mouseenter="onCardHover(item)"
        @mouseleave="onCardLeave"
        @dragstart="onCardDragStart(item, $event)"
      >
        <!-- 缩略图（完整显示，不裁剪，固定高度） -->
        <div class="card-thumb">
          <!-- 图片：直接显示 -->
          <img
            v-if="item.type === 'image'"
            :src="item.thumbUrl || item.url"
            :alt="item.name"
            loading="lazy"
          />
          <!-- 视频：首帧缩略图 + hover 时 GIF 动图覆盖 -->
          <template v-else-if="item.type === 'video'">
            <img
              v-if="item.thumbUrl"
              :src="item.thumbUrl"
              :alt="item.name"
              loading="lazy"
              class="video-static-thumb"
            />
            <!-- hover 时加载 GIF 动图预览 -->
            <img
              v-if="previewItem?.uid === item.uid && videoPreviews[item.id]"
              :src="videoPreviews[item.id]"
              :alt="item.name"
              class="video-gif-preview"
            />
          </template>
          <span v-else class="card-thumb-icon">
            <Music2 :size="24" />
          </span>
          <!-- 视频播放标识 -->
          <span v-if="item.type === 'video'" class="card-play-icon">
            <Play :size="18" />
          </span>
          <!-- 来源标签 -->
          <span class="card-source-badge" :class="item.source">
            {{ item.source === 'history' ? '历史' : '本地' }}
          </span>
          <!-- 类型标签 -->
          <span class="card-type-badge">{{ typeLabel(item.type) }}</span>
        </div>
        <!-- 名称 -->
        <div class="card-name">{{ item.name }}</div>
        <!-- 删除按钮（仅本地素材） -->
        <button
          v-if="item.source === 'local'"
          class="card-delete"
          title="删除"
          @click.stop="$emit('delete-asset', item.id)"
        >
          <Trash2 :size="14" />
        </button>
      </div>
    </div>

    <!-- 分页栏（仅历史记录） -->
    <div v-if="activeTab === 'history'" class="asset-pager">
      <button
        class="pager-btn"
        :disabled="historyPage <= 1 || loading"
        @click="goPage(historyPage - 1)"
      >
        <ChevronLeft :size="16" />
      </button>
      <span class="pager-info">
        {{ historyTotal > 0 ? `${historyPage} / ${totalPages}` : '0 / 0' }}
        <span class="pager-total">（共 {{ historyTotal }} 条）</span>
      </span>
      <button
        class="pager-btn"
        :disabled="historyPage >= totalPages || loading"
        @click="goPage(historyPage + 1)"
      >
        <ChevronRight :size="16" />
      </button>
    </div>

    <!-- 隐藏的文件上传 input -->
    <input
      ref="fileInputRef"
      type="file"
      accept="image/*,video/*"
      multiple
      style="display: none"
      @change="onFileSelected"
    />
  </div>

  <!-- 悬浮放大预览（Teleport 到 body，用 position: fixed 定位，避免被面板 overflow 裁剪） -->
  <Teleport to="body">
    <div
      v-if="previewItem"
      class="card-preview-global"
      :style="previewStyle"
    >
      <!-- 图片：直接显示大图 -->
      <img
        v-if="previewItem.type === 'image'"
        :src="previewItem.thumbUrl || previewItem.url"
        :alt="previewItem.name"
      />
      <!-- 视频：GIF 动图预览（可动画面），加载中显示首帧缩略图 -->
      <template v-else-if="previewItem.type === 'video'">
        <img
          v-if="previewItem.thumbUrl"
          :src="previewItem.thumbUrl"
          :alt="previewItem.name"
          class="preview-video-poster"
        />
        <img
          v-if="videoPreviews[previewItem.id]"
          :src="videoPreviews[previewItem.id]"
          :alt="previewItem.name"
          class="preview-video-gif"
        />
        <div v-else class="preview-loading">
          <Loader2 :size="20" class="spin-icon" />
          <span>加载预览...</span>
        </div>
      </template>
      <div v-if="previewItem.name" class="preview-name">{{ previewItem.name }}</div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
/* =====================================================
 * 画布素材库面板（重新设计版）
 * - 双 Tab：生成历史（后端 API 分页） + 我的素材（localforage 本地）
 * - 类型筛选：全部 / 图片 / 视频（切换时重新请求后端历史）
 * - 网格布局，点击素材触发 use-asset 事件
 * - 历史记录用分页（上一页/下一页），每页 20 条
 * - 视频历史记录用后端缩略图接口，避免直接加载完整视频
 * - 本地素材支持删除 + 上传新文件
 * - 悬浮预览通过 Teleport + position:fixed，避免被面板裁剪
 * ===================================================== */
import { ref, computed, reactive, onMounted, onBeforeUnmount } from 'vue'
import { X, Trash2, Music2, Inbox, Loader2, History, FolderOpen, Upload, Play, ChevronLeft, ChevronRight } from 'lucide-vue-next'
import { useAssetStore } from '@/stores/asset'
import { getHistoryList } from '@/api/history'
import client from '@/api/client'

const props = defineProps({
  theme: { type: Object, required: true },
})

const emit = defineEmits(['close', 'use-asset', 'delete-asset', 'upload-asset'])

const assetStore = useAssetStore()

// ---------- Tab 切换 ----------
const activeTab = ref('history') // 'history' | 'local'

// ---------- 类型筛选 ----------
const filters = [
  { value: 'all', label: '全部' },
  { value: 'image', label: '图片' },
  { value: 'video', label: '视频' },
]
const currentFilter = ref('all')

// ---------- 历史记录数据（分页） ----------
const historyList = ref<any[]>([])
const historyPage = ref(1)
const historyPageSize = 20
const historyTotal = ref(0)
const loading = ref(false)

// 总页数
const totalPages = computed(() => {
  if (historyTotal.value <= 0) return 0
  return Math.ceil(historyTotal.value / historyPageSize)
})

// ---------- 本地素材数据 ----------
const localAssets = computed(() => assetStore.assets || [])

// ---------- 统一展示列表 ----------
// 将历史记录和本地素材统一为统一格式
// { uid, id, type, url, thumbUrl, posterUrl, name, prompt, source, mode, createdAt }
const displayItems = computed(() => {
  if (activeTab.value === 'history') {
    return historyList.value.map((item) => ({
      uid: 'h-' + item.id,
      id: item.id,
      type: item.type,
      // 创建节点时用流式 URL（视频）或原图 URL（图片）
      url: item.result_url || '',
      // 视频缩略图：用异步加载的 blob URL（解决 JWT 鉴权问题，
      // 浏览器原生 <img src> 无法携带 Authorization 头）
      thumbUrl:
        item.type === 'video'
          ? videoThumbnails[item.id] || ''
          : item.result_url || '',
      posterUrl:
        item.type === 'video'
          ? videoThumbnails[item.id] || ''
          : '',
      name: truncate(item.prompt || `${typeLabel(item.type)}-${item.id}`, 28),
      prompt: item.prompt || '',
      source: 'history',
      mode: item.mode || '',
      createdAt: item.created_at,
    }))
  }
  return localAssets.value.map((item) => ({
    uid: 'l-' + item.id,
    id: item.id,
    type: item.type,
    url: item.url,
    thumbUrl: item.type === 'image' ? item.url : item.posterUrl || '',
    posterUrl: item.posterUrl || '',
    name: item.name || truncate(item.prompt || `${item.type}-${item.id.slice(0, 8)}`, 28),
    prompt: item.prompt || '',
    source: 'local',
  }))
})

// ---------- 空状态文案 ----------
const emptyText = computed(() => {
  if (activeTab.value === 'history') {
    if (currentFilter.value === 'image') return '暂无图片生成历史'
    if (currentFilter.value === 'video') return '暂无视频生成历史'
    return '暂无生成历史'
  }
  return '暂无本地素材'
})

// ---------- 面板样式 ----------
const panelStyle = computed(() => ({
  background: props.theme.toolbar.panel,
  borderColor: props.theme.toolbar.border,
  color: props.theme.node.text,
}))

// ---------- 工具函数 ----------
function truncate(str: string, len: number) {
  if (!str) return ''
  return str.length > len ? str.slice(0, len) + '...' : str
}

function typeLabel(type: string) {
  const labels: Record<string, string> = { image: '图片', video: '视频', audio: '音频' }
  return labels[type] || type
}

// ---------- Tab 切换 ----------
function switchTab(tab: string) {
  if (activeTab.value === tab) return
  activeTab.value = tab
}

// ---------- 类型筛选切换 ----------
function setFilter(value: string) {
  if (currentFilter.value === value) return
  currentFilter.value = value
  // 历史记录需要重新请求后端（按类型筛选），回到第 1 页
  if (activeTab.value === 'history') {
    historyPage.value = 1
    loadHistory()
  }
}

// ---------- 分页跳转 ----------
function goPage(page: number) {
  if (loading.value) return
  if (page < 1 || page > totalPages.value) return
  historyPage.value = page
  loadHistory()
}

// ---------- 加载历史记录（分页：每次只加载当前页） ----------
async function loadHistory() {
  loading.value = true
  try {
    const resp = await getHistoryList({
      type: currentFilter.value,
      page: historyPage.value,
      page_size: historyPageSize,
    })
    // client 拦截器已解包，resp 即后端 HistoryListResponse
    historyList.value = resp.items || []
    historyTotal.value = resp.total || 0
    // 异步加载视频缩略图（通过 axios 携带 JWT）
    historyList.value
      .filter((item: any) => item.type === 'video')
      .forEach((item: any) => {
        loadVideoThumbnail(item.id)
      })
    // 滚动回顶部
    if (gridRef.value) gridRef.value.scrollTop = 0
  } catch (err) {
    console.error('[asset-library] 加载历史失败:', err)
  } finally {
    loading.value = false
  }
}

// 加载视频缩略图（通过 axios 携带 JWT，解决 <img src> 无法鉴权的问题）
async function loadVideoThumbnail(id: string) {
  if (videoThumbnails[id] || thumbnailFailed[id]) return
  try {
    const url = `/api/history/video/${id}/thumbnail`
    const blobUrl = await fetchBlobAsUrl(url)
    videoThumbnails[id] = blobUrl
  } catch (err) {
    console.warn('[asset-library] 视频缩略图加载失败 id=' + id, err)
    thumbnailFailed[id] = true
  }
}

// ---------- 本地素材上传 ----------
const fileInputRef = ref<HTMLInputElement | null>(null)
function triggerUpload() {
  fileInputRef.value?.click()
}

async function onFileSelected(e: Event) {
  const target = e.target as HTMLInputElement
  const files = Array.from(target.files || [])
  if (files.length === 0) return
  emit('upload-asset', files)
  // 清空 input，允许重复选择同一文件
  target.value = ''
}

// ---------- 拖拽上传到素材库面板 ----------
const isDragOver = ref(false)

function onPanelDragEnter(e: DragEvent) {
  // 仅当拖入的是文件时才高亮
  if (e.dataTransfer && e.dataTransfer.types.includes('Files')) {
    isDragOver.value = true
  }
}

function onPanelDragOver(e: DragEvent) {
  // 必须 preventDefault 才能触发 drop；设置 effectAllowed 提示
  if (e.dataTransfer && e.dataTransfer.types.includes('Files')) {
    e.dataTransfer.dropEffect = 'copy'
  }
}

function onPanelDragLeave(e: DragEvent) {
  // 仅当离开面板本身（而非子元素）时才取消高亮
  if (e.target === e.currentTarget) {
    isDragOver.value = false
  }
}

function onPanelDrop(e: DragEvent) {
  isDragOver.value = false
  const files = Array.from(e.dataTransfer?.files || [])
  if (files.length === 0) return
  emit('upload-asset', files)
}

// ---------- 拖拽素材到画布 ----------
// dragstart 时把素材信息写入 dataTransfer，画布 drop 时读取并创建节点
function onCardDragStart(item: any, e: DragEvent) {
  // 拖拽开始时立即隐藏悬浮预览，避免阻碍拖拽视线
  previewItem.value = null
  if (!e.dataTransfer) return
  // 设置拖拽效果
  e.dataTransfer.effectAllowed = 'copy'
  // 写入素材数据（JSON 字符串），画布通过 'application/x-asset' 类型读取
  e.dataTransfer.setData('application/x-asset', JSON.stringify({
    id: item.id,
    type: item.type,
    url: item.url,
    thumbUrl: item.thumbUrl,
    name: item.name,
    prompt: item.prompt,
    source: item.source,
  }))
  // 同时设置 text/plain 兼容性
  e.dataTransfer.setData('text/plain', item.name || item.url || '')
}

// ---------- 悬浮放大预览（Teleport + position:fixed） ----------
// 鼠标悬浮卡片时，在面板左侧显示放大预览
// 视频卡片 hover 时懒加载 GIF 动图预览（参考 HistoryView 的 ffmpeg 渲染效果）
const previewItem = ref<any>(null)
const previewX = ref(0)
const previewY = ref(0)
const gridRef = ref<HTMLElement | null>(null)
const videoPreviews = reactive<Record<string, string>>({}) // { [id]: gifUrl } 已加载的视频 GIF 预览
const previewLoading = reactive<Record<string, boolean>>({}) // { [id]: boolean } GIF 加载状态
const videoThumbnails = reactive<Record<string, string>>({}) // { [id]: blobUrl } 视频静态缩略图
const thumbnailFailed = reactive<Record<string, boolean>>({}) // { [id]: boolean } 缩略图加载失败

/**
 * 通过 axios 下载二进制资源并生成 blob URL
 * 解决 <img src="url"> 无法携带 JWT 的用户隔离问题
 */
async function fetchBlobAsUrl(url: string): Promise<string> {
  const blob = await client.get(url, {
    responseType: 'blob',
    silent: true,
  }) as unknown as Blob
  return URL.createObjectURL(blob)
}

function clearVideoBlobUrls() {
  Object.values(videoThumbnails).forEach(url => {
    if (url && url.startsWith('blob:')) URL.revokeObjectURL(url)
  })
  Object.values(videoPreviews).forEach(url => {
    if (url && url.startsWith('blob:')) URL.revokeObjectURL(url)
  })
}

function onCardHover(item: any) {
  previewItem.value = item
  // 延迟一帧计算位置，确保预览框已渲染
  requestAnimationFrame(() => {
    updatePreviewPosition()
  })
  // 视频：懒加载 GIF 动图预览
  if (item.type === 'video' && item.source === 'history') {
    loadVideoPreview(item.id)
  }
}

// 加载视频 GIF 预览（后端 ffmpeg 生成，悬停时可动）
// 通过 axios 下载 blob URL，解决 <img src> 无法携带 JWT 的问题
async function loadVideoPreview(id: string) {
  if (videoPreviews[id] || previewLoading[id]) return
  previewLoading[id] = true
  try {
    const url = `/api/history/video/${id}/preview`
    const blobUrl = await fetchBlobAsUrl(url)
    videoPreviews[id] = blobUrl
  } catch (err) {
    console.warn('[asset-library] GIF 预览加载失败 id=' + id, err)
  } finally {
    previewLoading[id] = false
  }
}

function updatePreviewPosition() {
  if (!previewItem.value) return
  // 预览框显示在面板左侧
  // 面板在右侧 right:0，宽 420px，面板左边缘 = window.innerWidth - 420
  const panelLeft = window.innerWidth - 420
  const previewW = 320
  const previewH = 320
  // 预览框右边缘紧贴面板左边缘，留 8px 间距
  let x = panelLeft - previewW - 8
  if (x < 8) x = 8
  // 垂直居中于视口
  let y = (window.innerHeight - previewH) / 2
  if (y < 16) y = 16
  previewX.value = x
  previewY.value = y
}

function onCardLeave() {
  previewItem.value = null
}

// 预览框定位样式（position: fixed，相对视口）
const previewStyle = computed(() => ({
  left: previewX.value + 'px',
  top: previewY.value + 'px',
}))

// 窗口大小变化时更新预览位置
function onResize() {
  if (previewItem.value) updatePreviewPosition()
}

// ---------- 生命周期 ----------
onMounted(() => {
  assetStore.hydrate()
  loadHistory()
  window.addEventListener('resize', onResize)
  // 监听用户登录/退出，切换素材库数据空间
  window.addEventListener('agnes:user-login', handleUserSwitch as unknown as EventListener)
  window.addEventListener('agnes:user-logout', handleUserLogout as unknown as EventListener)
})

onBeforeUnmount(() => {
  clearVideoBlobUrls()
  window.removeEventListener('resize', onResize)
  window.removeEventListener('agnes:user-login', handleUserSwitch as unknown as EventListener)
  window.removeEventListener('agnes:user-logout', handleUserLogout as unknown as EventListener)
})

/** 登录/切换用户后，切换素材库数据空间 */
async function handleUserSwitch(e: CustomEvent) {
  clearVideoBlobUrls()
  const userId: number | null = (e?.detail?.id as number) ?? null
  await assetStore._switchUserStorage(userId)
  loadHistory()
}

/** 退出登录：切换到匿名素材库空间 */
async function handleUserLogout() {
  clearVideoBlobUrls()
  await assetStore._switchUserStorage(null)
  loadHistory()
}

// ---------- 暴露刷新方法（供父组件在保存素材后调用） ----------
defineExpose({
  refreshLocal() {
    // 本地素材来自 store 响应式数据，自动更新；此处仅触发重新渲染
    assetStore.hydrate()
  },
  refreshHistory() {
    historyPage.value = 1
    loadHistory()
  },
})
</script>

<style scoped>
/* 素材库面板：右侧滑出大面板 */
.asset-library-panel {
  position: absolute;
  top: 0;
  right: 0;
  bottom: 0;
  width: 420px;
  display: flex;
  flex-direction: column;
  border-left: 1px solid;
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  box-shadow: -4px 0 24px rgba(0, 0, 0, 0.2);
  z-index: 45;
  overflow: hidden;
  pointer-events: auto;
  transition: box-shadow 0.2s, border-color 0.2s;
}

/* 拖拽文件上传时面板高亮提示 */
.asset-library-panel.drag-over {
  border-color: var(--agnes-primary);
  box-shadow: -4px 0 24px rgba(0, 0, 0, 0.2), inset 4px 0 0 var(--agnes-primary);
}

/* 拖拽中的卡片降低透明度 */
.asset-card[draggable="true"]:active {
  opacity: 0.5;
}

/* 标题栏 */
.asset-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 18px 20px 14px;
  border-bottom: 1px solid var(--agnes-border);
  flex-shrink: 0;
}

.asset-title-wrap {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.asset-title {
  font-size: 17px;
  font-weight: 600;
  letter-spacing: 0.5px;
}

.asset-subtitle {
  font-size: 11px;
  opacity: 0.5;
}

.asset-close {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border: none;
  border-radius: 8px;
  background: transparent;
  cursor: pointer;
  color: inherit;
  opacity: 0.6;
  transition: all 0.15s;
}

.asset-close:hover {
  opacity: 1;
  background: var(--agnes-bg-hover);
}

/* Tab 切换条 */
.asset-tabs {
  display: flex;
  gap: 4px;
  padding: 10px 16px 0;
  flex-shrink: 0;
}

.asset-tab {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  border: none;
  border-bottom: 2px solid transparent;
  background: transparent;
  cursor: pointer;
  color: inherit;
  font-size: 13px;
  font-weight: 500;
  opacity: 0.5;
  transition: all 0.15s;
}

.asset-tab:hover {
  opacity: 0.8;
}

.asset-tab.active {
  opacity: 1;
  border-bottom-color: var(--agnes-primary);
  color: var(--agnes-primary);
}

/* 工具栏（筛选 + 上传） */
.asset-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 10px 16px 12px;
  border-bottom: 1px solid var(--agnes-border);
  flex-shrink: 0;
}

.asset-filters {
  display: flex;
  gap: 4px;
}

.asset-filter-btn {
  padding: 5px 12px;
  border: none;
  border-radius: 6px;
  background: transparent;
  cursor: pointer;
  color: inherit;
  font-size: 12px;
  opacity: 0.5;
  transition: all 0.15s;
}

.asset-filter-btn:hover {
  background: var(--agnes-bg-hover);
  opacity: 0.8;
}

.asset-filter-btn.active {
  background: var(--agnes-info-bg);
  opacity: 1;
  color: var(--agnes-primary);
}

.asset-upload-btn {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 5px 12px;
  border: none;
  border-radius: 6px;
  background: var(--agnes-info-bg);
  cursor: pointer;
  color: var(--agnes-primary);
  font-size: 12px;
  font-weight: 500;
  transition: all 0.15s;
}

.asset-upload-btn:hover {
  background: var(--agnes-info-bg);
}

/* 网格区域（可滚动） */
.asset-grid {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px;
  align-content: start;
}

/* 加载中 */
.asset-loading {
  grid-column: 1 / -1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 80px 0;
  opacity: 0.5;
  font-size: 13px;
}

.spin-icon {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* 空状态 */
.asset-empty {
  grid-column: 1 / -1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 80px 20px;
  opacity: 0.3;
  font-size: 13px;
  text-align: center;
}

.asset-empty-hint {
  font-size: 11px;
  opacity: 0.7;
  max-width: 260px;
  line-height: 1.6;
  margin-top: 4px;
}

/* 素材卡片 */
.asset-card {
  position: relative;
  border-radius: 12px;
  overflow: hidden;
  cursor: pointer;
  transition: transform 0.15s, box-shadow 0.15s;
  background: var(--agnes-bg-hover);
  border: 1px solid var(--agnes-border);
}

.asset-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 20px rgba(0, 0, 0, 0.25);
  border-color: var(--agnes-primary-border);
}

/* 缩略图（完整显示，不裁剪，固定高度确保布局稳定） */
.card-thumb {
  width: 100%;
  height: 110px;
  overflow: hidden;
  background: var(--agnes-bg-hover);
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
}

/* 图片/视频缩略图：填满容器，object-fit:contain 保持比例完整显示 */
/* 用 width/height:100% 代替 max-width/max-height，避免 flex 布局中大图 max-height 失效 */
.card-thumb > img {
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.card-thumb-icon {
  opacity: 0.3;
}

/* 视频静态首帧缩略图 */
.video-static-thumb {
  width: 100%;
  height: 100%;
  object-fit: contain;
  transition: opacity 0.2s ease;
}

/* 视频 hover 时的 GIF 动图预览（覆盖在缩略图上） */
.video-gif-preview {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: contain;
  z-index: 1;
}

/* 视频播放标识 */
.card-play-icon {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: var(--agnes-bg-dark-surface);
  color: #fff;
  backdrop-filter: blur(4px);
  pointer-events: none;
  z-index: 2;
}

/* hover 时隐藏播放图标（GIF 预览接管） */
.asset-card:hover .card-play-icon {
  opacity: 0;
  transition: opacity 0.2s;
}

/* 来源标签 */
.card-source-badge {
  position: absolute;
  top: 6px;
  left: 6px;
  padding: 1px 6px;
  border-radius: 4px;
  font-size: 9px;
  font-weight: 600;
  backdrop-filter: blur(4px);
  letter-spacing: 0.3px;
}

.card-source-badge.history {
  background: var(--agnes-primary);
  color: #fff;
}

.card-source-badge.local {
  background: var(--agnes-accent);
  color: #fff;
}

/* 类型标签 */
.card-type-badge {
  position: absolute;
  top: 6px;
  right: 6px;
  padding: 1px 6px;
  border-radius: 4px;
  font-size: 9px;
  background: var(--agnes-bg-dark-surface);
  color: #fff;
  backdrop-filter: blur(4px);
}

/* 名称 */
.card-name {
  padding: 6px 8px;
  font-size: 10px;
  line-height: 1.3;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  opacity: 0.7;
}

/* 删除按钮（仅本地素材） */
.card-delete {
  position: absolute;
  bottom: 8px;
  right: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  border: none;
  border-radius: 6px;
  background: var(--agnes-bg-dark-surface);
  cursor: pointer;
  color: #fff;
  opacity: 0;
  transition: opacity 0.15s, color 0.15s, background 0.15s;
  backdrop-filter: blur(4px);
}

.asset-card:hover .card-delete {
  opacity: 0.85;
}

.card-delete:hover {
  opacity: 1 !important;
  color: var(--agnes-error);
  background: var(--agnes-error);
}

/* 分页栏 */
.asset-pager {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 10px 16px;
  border-top: 1px solid var(--agnes-border);
  flex-shrink: 0;
}

.pager-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  border: none;
  border-radius: 6px;
  background: var(--agnes-bg-hover);
  cursor: pointer;
  color: inherit;
  transition: all 0.15s;
}

.pager-btn:hover:not(:disabled) {
  background: var(--agnes-info-bg);
  color: var(--agnes-primary);
}

.pager-btn:disabled {
  opacity: 0.3;
  cursor: not-allowed;
}

.pager-info {
  font-size: 12px;
  opacity: 0.7;
  min-width: 100px;
  text-align: center;
}

.pager-total {
  opacity: 0.6;
  font-size: 11px;
}

/* 滚动条样式 */
.asset-grid::-webkit-scrollbar {
  width: 6px;
}

.asset-grid::-webkit-scrollbar-track {
  background: transparent;
}

.asset-grid::-webkit-scrollbar-thumb {
  background: var(--agnes-border);
  border-radius: 3px;
}

.asset-grid::-webkit-scrollbar-thumb:hover {
  background: var(--agnes-bg-hover);
}
</style>

<!-- 预览框样式：非 scoped，因为通过 Teleport 到 body，不在组件 DOM 树内 -->
<style>
/* 悬浮放大预览框（Teleport 到 body，position: fixed） */
.card-preview-global {
  position: fixed;
  width: 320px;
  max-height: 380px;
  padding: 8px;
  border-radius: 12px;
  background: var(--agnes-bg-elevated);
  border: 1px solid var(--agnes-border);
  box-shadow: var(--agnes-shadow-card);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  z-index: 9999;
  pointer-events: none;
  display: flex;
  flex-direction: column;
  gap: 6px;
  animation: preview-fade-in 0.15s ease;
}

@keyframes preview-fade-in {
  from { opacity: 0; transform: translateX(8px); }
  to { opacity: 1; transform: translateX(0); }
}

.card-preview-global img,
.card-preview-global video {
  width: 100%;
  max-height: 320px;
  object-fit: contain;
  border-radius: 8px;
  background: var(--agnes-overlay-bg);
}

/* 视频预览：首帧缩略图（底层） */
.card-preview-global .preview-video-poster {
  width: 100%;
  max-height: 320px;
  object-fit: contain;
  border-radius: 8px;
  background: var(--agnes-overlay-bg);
}

/* 视频预览：GIF 动图（覆盖在首帧上） */
.card-preview-global .preview-video-gif {
  position: absolute;
  top: 8px;
  left: 8px;
  right: 8px;
  width: calc(100% - 16px);
  max-height: 320px;
  object-fit: contain;
  border-radius: 8px;
  background: var(--agnes-overlay-bg);
  z-index: 1;
}

/* 视频预览加载中提示 */
.card-preview-global .preview-loading {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  color: var(--agnes-text-muted);
  font-size: 12px;
  z-index: 2;
}

.card-preview-global .preview-name {
  font-size: 12px;
  line-height: 1.4;
  opacity: 0.75;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  padding: 0 4px;
  color: var(--agnes-text-primary);
}
</style>
