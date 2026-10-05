<!--
  CanvasAssetLibrary.vue
  画布素材库面板（重新设计版）
  - 右侧滑出大面板，宽度 420px，高度占满画布
  - 范围切换：本作品 / 全部；媒体类型筛选：全部 / 图片 / 视频 / 音频
  - 检索行：关键词搜索（防抖 300ms，搜名称/描述）+ 分类下拉（七类，复用后端 type/keyword 参数）
  - 网格布局展示缩略图（完整显示不裁剪，固定高度），点击创建画布节点
  - 鼠标悬浮卡片时通过 Teleport 到 body 显示放大预览（position: fixed）
  - 分页（上一页/下一页），避免一次性加载过多数据
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
        <span class="asset-title">{{ t('canvas.assetLibrary.title') }}</span>
        <span class="asset-subtitle">{{ scope === 'work' ? t('canvas.assetLibrary.scopeWork') : t('canvas.assetLibrary.scopeAll') }}</span>
      </div>
      <button class="asset-close" @click="$emit('close')">
        <X :size="18" />
      </button>
    </div>

    <!-- 范围切换：本作品 / 全部 -->
    <div class="asset-tabs">
      <button
        :class="['asset-tab', { active: scope === 'work' }]"
        @click="setScope('work')"
      >
        <FolderOpen :size="14" />
        <span>{{ t('canvas.assetLibrary.scopeWork') }}</span>
      </button>
      <button
        :class="['asset-tab', { active: scope === 'all' }]"
        @click="setScope('all')"
      >
        <History :size="14" />
        <span>{{ t('canvas.assetLibrary.scopeAll') }}</span>
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
      <!-- 素材入库：上传按钮 -->
      <button
        class="asset-upload-btn"
        @click="triggerUpload"
      >
        <Upload :size="14" />
        <span>{{ t('canvas.assetLibrary.upload') }}</span>
      </button>
    </div>

    <!-- 检索行：关键词 + 分类（回退态分类不可用，置灰） -->
    <div class="asset-search-row">
      <div class="asset-search-box">
        <Search :size="14" />
        <input
          v-model="searchKeyword"
          :placeholder="t('canvas.assetLibrary.searchPlaceholder')"
        />
      </div>
      <select v-model="currentType" class="asset-type-select" :disabled="useLocalFallback" @change="onTypeChange">
        <option value="">{{ t('canvas.assetLibrary.allTypes') }}</option>
        <option v-for="tp in typeOptions" :key="tp.value" :value="tp.value">{{ tp.label }}</option>
      </select>
    </div>

    <!-- 素材网格 -->
    <div class="asset-grid" ref="gridRef">
      <!-- 加载中（首次） -->
      <div v-if="loading && displayItems.length === 0" class="asset-loading">
        <Loader2 :size="24" class="spin-icon" />
        <span>{{ t('canvas.assetLibrary.loading') }}</span>
      </div>

      <!-- 空状态 -->
      <div v-else-if="displayItems.length === 0" class="asset-empty">
        <Inbox :size="40" />
        <span>{{ emptyText }}</span>
        <span v-if="useLocalFallback" class="asset-empty-hint">
          {{ t('canvas.assetLibrary.emptyHint') }}
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
          <!-- 视频：首帧缩略图（thumb_url 或视频本身） -->
          <template v-else-if="item.type === 'video'">
            <video
              v-if="item.url"
              :src="item.url"
              :alt="item.name"
              class="video-static-thumb"
              muted
              playsinline
              preload="metadata"
            />
          </template>
          <span v-else class="card-thumb-icon">
            <Music2 :size="24" />
          </span>
          <!-- 视频播放标识 -->
          <span v-if="item.type === 'video'" class="card-play-icon">
            <Play :size="18" />
          </span>
          <!-- 来源标签（生成/上传/合成/归档） -->
          <span class="card-source-badge" :class="item.source">
            {{ sourceLabel(item.source) }}
          </span>
          <!-- 类型标签 -->
          <span class="card-type-badge">{{ typeLabel(item.type) }}</span>
        </div>
        <!-- 名称 -->
        <div class="card-name">{{ item.name }}</div>
        <!-- 删除按钮（统一资产：本人皆可删） -->
        <button
          class="card-delete"
          :title="t('canvas.assetLibrary.delete')"
          @click.stop="removeUnified(item)"
        >
          <Trash2 :size="14" />
        </button>
      </div>
    </div>

    <!-- 分页栏 -->
    <div class="asset-pager">
      <button
        class="pager-btn"
        :disabled="assetPage <= 1 || loading"
        @click="goPage(assetPage - 1)"
      >
        <ChevronLeft :size="16" />
      </button>
      <span class="pager-info">
        {{ assetTotal > 0 ? `${assetPage} / ${totalPages}` : '0 / 0' }}
        <span class="pager-total">{{ t('canvas.assetLibrary.pagerTotal', { n: assetTotal }) }}</span>
      </span>
      <button
        class="pager-btn"
        :disabled="assetPage >= totalPages || loading"
        @click="goPage(assetPage + 1)"
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
      <!-- 视频：首帧缩略图（thumb_url 或视频本身） -->
      <template v-else-if="previewItem.type === 'video'">
        <video
          v-if="previewItem.url"
          :src="previewItem.url"
          class="preview-video-poster"
          muted
          playsinline
          preload="metadata"
        />
      </template>
      <div v-if="previewItem.name" class="preview-name">{{ previewItem.name }}</div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
/* =====================================================
 * 画布素材库面板（子批次 2a 同源改造）
 * - 单池数据源：统一资产端点 /api/assets（与资产库页同源同身份）
 * - 范围切换：本作品（默认，work_id 筛选）/ 全部素材
 * - 类型筛选：全部 / 图片 / 视频（切换重新请求）
 * - 网格布局，点击/拖拽创建画布节点，上传文件即入库
 * - 分页（上一页/下一页），每页 20 条
 * - 悬浮预览通过 Teleport + position:fixed，避免被面板裁剪
 * ===================================================== */
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import { useI18n } from '@/i18n'
import { X, Trash2, Music2, Inbox, Loader2, Upload, Play, ChevronLeft, ChevronRight, Search } from 'lucide-vue-next'
import { useAssetStore } from '@/stores/canvasAsset'
import { listAssets } from '@/api/assets'
import { deleteAsset as deleteAssetApi } from '@/api/pipeline'

const { t } = useI18n()

const props = defineProps({
  theme: { type: Object, required: true },
  /** 当前画布所属作品（scope=work 时按此筛选） */
  workId: { type: Number, default: undefined },
})

const emit = defineEmits(['close', 'use-asset', 'delete-asset', 'upload-asset'])

const assetStore = useAssetStore()

// ---------- 范围切换 ----------
const scope = ref<'work' | 'all'>('work')

function setScope(s: 'work' | 'all') {
  if (scope.value === s) return
  scope.value = s
  assetPage.value = 1
  loadAssets()
}

// ---------- 类型筛选 ----------
const filters = computed(() => [
  { value: 'all', label: t('canvas.assetLibrary.filters.all') },
  { value: 'image', label: t('canvas.assetLibrary.filters.image') },
  { value: 'video', label: t('canvas.assetLibrary.filters.video') },
  { value: 'audio', label: t('canvas.assetLibrary.filters.audio') },
])
const currentFilter = ref('all')

// ---------- 检索：关键词 + 分类 ----------
// 复用统一资产端点现成的 keyword（名称/描述/视觉描述三列）与 type（七类）参数
const searchKeyword = ref('')
const currentType = ref('')
let searchTimer: ReturnType<typeof setTimeout> | null = null

watch(searchKeyword, () => {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    assetPage.value = 1
    loadAssets()
  }, 300)
})

/** 分类下拉选项（实体四类 + 影子归档行政三类，标签与资产库页同源） */
const typeOptions = computed(() =>
  ['character', 'prop', 'scene', 'brand', 'material', 'clip', 'final'].map((v) => ({
    value: v,
    label: t('assets.type.' + v),
  }))
)

function onTypeChange() {
  assetPage.value = 1
  loadAssets()
}

// ---------- 统一资产数据（分页） ----------
const assetRows = ref<any[]>([])
const assetPage = ref(1)
const assetPageSize = 20
const assetTotal = ref(0)
const loading = ref(false)
const useLocalFallback = ref(false) // 未登录/接口失败时回退本地素材索引

// 总页数
const totalPages = computed(() => {
  if (assetTotal.value <= 0) return 0
  return Math.ceil(assetTotal.value / assetPageSize)
})

// ---------- 本地素材数据（仅回退态使用） ----------
const localAssets = computed(() => assetStore.assets || [])

// ---------- 统一展示列表 ----------
// { uid, id, type, url, thumbUrl, posterUrl, name, prompt, source, createdAt }
const displayItems = computed(() => {
  if (useLocalFallback.value) {
    // 回退态（未登录/接口失败）：本地素材前端过滤（分类字段缺失，下拉已禁用）
    const kw = searchKeyword.value.trim().toLowerCase()
    return localAssets.value
      .filter((item) => {
        if (currentFilter.value !== 'all' && item.type !== currentFilter.value) return false
        if (!kw) return true
        return `${item.name || ''} ${item.prompt || ''}`.toLowerCase().includes(kw)
      })
      .map((item) => ({
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
  }
  return assetRows.value.map((a) => ({
    uid: 'a-' + a.id,
    id: a.id,
    type: a.media_type,
    url: a.asset_url || '',
    thumbUrl: a.media_type === 'video' ? (a.thumb_url || '') : (a.asset_url || ''),
    posterUrl: a.thumb_url || '',
    name: truncate(a.name || `${typeLabel(a.media_type)}-${a.id}`, 28),
    prompt: '',
    source: 'asset',
    createdAt: a.created_at,
  }))
})

// ---------- 空状态文案 ----------
const emptyText = computed(() => {
  // 检索条件生效时区分「无匹配」与「暂无素材」
  if (searchKeyword.value.trim() || currentType.value) return t('canvas.assetLibrary.noMatch')
  if (currentFilter.value === 'image') return t('canvas.assetLibrary.empty.noImageHistory')
  if (currentFilter.value === 'video') return t('canvas.assetLibrary.empty.noVideoHistory')
  return t('canvas.assetLibrary.empty.noHistory')
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
  const labels: Record<string, string> = {
    image: t('canvas.assetLibrary.typeLabel.image'),
    video: t('canvas.assetLibrary.typeLabel.video'),
    audio: t('canvas.assetLibrary.typeLabel.audio'),
  }
  return labels[type] || type
}

/** 来源标签（生成/上传/合成/归档） */
function sourceLabel(source: string | null) {
  const map: Record<string, string> = {
    generation: t('assets.source.generation'),
    upload: t('assets.source.upload'),
    compose: t('assets.source.compose'),
    archive: t('assets.source.archive'),
    canvas: t('assets.source.canvas'),
  }
  return map[source ?? ''] || source || '-'
}

/** 删除统一资产（面板内直删 + 列表同步移除） */
async function removeUnified(item: any) {
  try {
    await deleteAssetApi(Number(item.id))
    assetRows.value = assetRows.value.filter((x) => x.id !== Number(item.id))
    assetTotal.value = Math.max(0, assetTotal.value - 1)
  } catch (err) {
    console.warn('[asset-library] 删除失败:', err)
  }
}

// ---------- 类型筛选切换 ----------
function setFilter(value: string) {
  if (currentFilter.value === value) return
  currentFilter.value = value
  assetPage.value = 1
  loadAssets()
}

// ---------- 分页跳转 ----------
function goPage(page: number) {
  if (loading.value) return
  if (page < 1 || page > totalPages.value) return
  assetPage.value = page
  loadAssets()
}

// ---------- 加载统一资产（分页：每次只加载当前页） ----------
async function loadAssets() {
  loading.value = true
  try {
    const resp = await listAssets({
      media_type: currentFilter.value === 'all' ? undefined : currentFilter.value,
      work_id: scope.value === 'work' && props.workId ? props.workId : undefined,
      type: currentType.value || undefined,
      keyword: searchKeyword.value.trim() || undefined,
      page: assetPage.value,
      page_size: assetPageSize,
    })
    assetRows.value = resp.items || []
    assetTotal.value = resp.total || 0
    useLocalFallback.value = false
    // 滚动回顶部
    if (gridRef.value) gridRef.value.scrollTop = 0
  } catch (err) {
    // 未登录 / 接口失败：回退本地素材索引（匿名画布仍可用）
    console.warn('[asset-library] 统一资产加载失败，回退本地素材:', err)
    useLocalFallback.value = true
  } finally {
    loading.value = false
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


function onCardHover(item: any) {
  previewItem.value = item
  // 延迟一帧计算位置，确保预览框已渲染
  requestAnimationFrame(() => {
    updatePreviewPosition()
  })
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

/** 登录/切换用户后，切换素材库数据空间 */
const handleUserSwitchWrapper: EventListener = (e: Event) => {
  handleUserSwitch(e as CustomEvent)
}
const handleUserLogoutWrapper: EventListener = () => {
  handleUserLogout()
}

// ---------- 生命周期 ----------
onMounted(() => {
  assetStore.hydrate()
  loadAssets()
  window.addEventListener('resize', onResize)
  // 监听用户登录/退出，切换素材库数据空间
  window.addEventListener('agnes:user-login', handleUserSwitchWrapper)
  window.addEventListener('agnes:user-logout', handleUserLogoutWrapper)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', onResize)
  window.removeEventListener('agnes:user-login', handleUserSwitchWrapper)
  window.removeEventListener('agnes:user-logout', handleUserLogoutWrapper)
})

/** 登录/切换用户后，重新加载统一资产 */
async function handleUserSwitch(e: CustomEvent) {
  await assetStore._switchUserStorage((e as CustomEvent).detail?.userId ?? null)
  assetPage.value = 1
  loadAssets()
}

/** 退出登录：回退本地素材索引（匿名画布仍可用） */
async function handleUserLogout() {
  await assetStore._switchUserStorage(null)
  assetPage.value = 1
  loadAssets()
}

// ---------- 暴露刷新方法（供父组件在保存素材后调用） ----------
defineExpose({
  refreshLocal() {
    // 本地素材来自 store 响应式数据，自动更新；此处仅触发重新渲染
    assetStore.hydrate()
  },
  refreshHistory() {
    assetPage.value = 1
    loadAssets()
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

/* 检索行：关键词搜索 + 分类下拉（原生控件，主题变量适配画布暗色） */
.asset-search-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px 12px;
  border-bottom: 1px solid var(--agnes-border);
  flex-shrink: 0;
}

.asset-search-box {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 0 10px;
  border: 1px solid var(--agnes-border);
  border-radius: 8px;
  background: var(--agnes-bg-hover);
  color: inherit;
  transition: border-color 0.15s;
}

.asset-search-box:focus-within {
  border-color: var(--agnes-primary-border);
}

.asset-search-box input {
  flex: 1;
  min-width: 0;
  border: none;
  outline: none;
  background: transparent;
  color: inherit;
  font-size: 12px;
  padding: 7px 0;
}

.asset-search-box input::placeholder {
  color: inherit;
  opacity: 0.4;
}

.asset-type-select {
  max-width: 110px;
  padding: 6px 8px;
  border: 1px solid var(--agnes-border);
  border-radius: 8px;
  background: var(--agnes-bg-hover);
  color: inherit;
  font-size: 12px;
  cursor: pointer;
  outline: none;
}

.asset-type-select:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.asset-type-select option {
  background: var(--agnes-bg-elevated);
  color: var(--agnes-text-primary);
}

/* 网格区域（可滚动） */
.asset-grid {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  /* auto 行在 Chrome 里会忽略固定高度子元素的贡献导致行高塌陷，显式按内容计算 */
  grid-auto-rows: min-content;
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
