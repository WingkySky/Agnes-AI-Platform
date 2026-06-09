<!-- =====================================================
     历史记录视图 HistoryView（已接入 i18n 国际化）
     - 筛选：全部 / 图片 / 视频
     - 分页加载
     - 点击卡片弹出详情（可预览、下载、删除）
     - 所有 UI 文案通过 t() 函数调用
     ===================================================== -->

<template>
  <div class="history-view">
    <h2 class="page-title">📜 {{ t('history.title') }}</h2>
    <p class="page-desc">{{ t('history.desc') }}</p>

    <!-- 筛选 Tab -->
    <div class="filter-wrap">
      <el-radio-group v-model="filterType" @change="loadList(true)">
        <el-radio-button value="all">{{ t('history.all') }} ({{ imageCount + videoCount }})</el-radio-button>
        <el-radio-button value="image">{{ t('history.image') }} ({{ imageCount }})</el-radio-button>
        <el-radio-button value="video">{{ t('history.video') }} ({{ videoCount }})</el-radio-button>
      </el-radio-group>
      <div class="filter-actions">
        <el-button type="primary" :icon="Refresh" :loading="loading" @click="loadList(true)">
          {{ t('common.refresh') }}
        </el-button>
        <!-- 编辑模式切换按钮 -->
        <el-button
          :type="editMode ? 'warning' : 'default'"
          :icon="editMode ? CloseIcon : Edit"
          @click="toggleEditMode">
          {{ editMode ? t('history.exitEdit') : t('history.edit') }}
        </el-button>
      </div>
    </div>

    <!-- 编辑模式操作栏（全选 + 批量删除） -->
    <div v-if="editMode && list.length > 0" class="edit-toolbar">
      <div class="edit-left">
        <el-checkbox
          v-model="isAllSelected"
          :indeterminate="isIndeterminate"
          @change="toggleSelectAll">
          {{ t('history.selectAllPage') }}
        </el-checkbox>
        <span class="selection-info">
          {{ t('history.selectedCount') }} <b class="selection-count">{{ selectedIds.length }}</b> {{ t('common.item') }}
        </span>
      </div>
      <div class="edit-right">
        <el-button
          type="danger"
          :icon="DeleteIcon"
          :disabled="selectedIds.length === 0"
          :loading="batchDeleting"
          @click="confirmBatchDelete">
          {{ t('history.deleteSelected') }} ({{ selectedIds.length }})
        </el-button>
      </div>
    </div>

    <!-- 加载中 -->
    <div v-if="loading && list.length === 0" class="loading-state">
      <el-icon :size="32" class="spinner"><LoadingIcon /></el-icon>
      <div>{{ t('history.loading') }}</div>
    </div>

    <!-- 空状态 -->
    <div v-else-if="list.length === 0" class="empty-state">
      <el-icon :size="48"><Document /></el-icon>
      <p class="empty-text">{{ t('history.emptyTip') }}</p>
    </div>

    <!-- 卡片网格 -->
    <div v-else class="history-grid">
      <div
        v-for="item in list"
        :key="item.id"
        class="history-card"
        :class="{ 'is-selected': selectedIds.includes(item.id) }"
        @click="handleCardClick(item)">
        <!-- 编辑模式下的选择框 -->
        <div v-if="editMode" class="card-checkbox" @click.stop="toggleSelect(item.id)">
          <el-checkbox :model-value="selectedIds.includes(item.id)" />
        </div>
        <div class="card-preview">
          <img
            v-if="item.type === 'image'"
            :src="item.result_url"
            :alt="t('history.thumbnailAlt')"
            loading="lazy"
          />
          <!-- 视频卡片：首帧缩略图 + 悬停 GIF 预览 -->
          <div
            v-else-if="item.type === 'video'"
            class="video-thumb"
            @mouseenter="onVideoCardHover(item)"
            @mouseleave="onVideoCardLeave(item)"
          >
            <!-- 首帧缩略图（静态） -->
            <img
              v-if="videoThumbnails[item.id]"
              :src="videoThumbnails[item.id]"
              :alt="t('history.videoThumbAlt')"
              class="video-thumb-img"
              loading="lazy"
            />
            <!-- 缩略图加载失败时的占位 -->
            <div v-else class="video-thumb-placeholder">
              <el-icon :size="44" class="play-icon"><VideoPlay /></el-icon>
              <span class="video-thumb-label">{{ t('history.clickToPlay') }}</span>
            </div>
            <!-- 悬停时的 GIF 预览 -->
            <img
              v-if="hoveredVideoId === item.id && videoPreviews[item.id]"
              :src="videoPreviews[item.id]"
              :alt="t('history.videoPreviewAlt')"
              class="video-preview-gif"
            />
            <!-- 播放图标蒙层 -->
            <div class="video-play-overlay">
              <el-icon :size="32"><VideoPlay /></el-icon>
            </div>
          </div>
          <div class="type-badge" :class="item.type">
            {{ item.type === 'image' ? t('history.image') : t('history.video') }}
          </div>
        </div>
        <div class="card-meta">
          <div class="card-prompt">{{ truncate(item.prompt, 80) }}</div>
          <div class="card-time">{{ formatTime(item.created_at) }}</div>
        </div>
      </div>
    </div>

    <!-- 分页 -->
    <div v-if="list.length > 0" class="pagination-wrap">
      <el-pagination
        v-model:current-page="page"
        v-model:page-size="pageSize"
        :page-sizes="[12, 24, 48, 100]"
        :total="totalCount"
        layout="total, sizes, prev, pager, next"
        background
        @size-change="handleSizeChange"
        @current-change="handlePageChange"
      />
    </div>

    <!-- 详情弹窗 -->
    <el-dialog
      v-model="detailVisible"
      :title="detailItem ? (detailItem.type === 'image' ? t('history.imageDetail') : t('history.videoDetail')) : t('history.detail')"
      width="70%"
      top="5vh"
      destroy-on-close>
      <div v-if="detailItem" class="detail-content">
        <div class="detail-media">
          <img v-if="detailItem.type === 'image'" :src="detailItem.result_url" :alt="t('history.imageDetailAlt')" />
          <div v-else class="detail-video-wrap">
            <video
              v-if="detailItem.result_url"
              ref="detailVideoEl"
              :src="getVideoStreamUrl(detailItem)"
              :poster="detailPoster"
              controls
              playsinline
              preload="metadata"
              class="detail-video"
              @loadeddata="captureDetailPoster"
              @canplay="onDetailVideoCanPlay"
              @error="onDetailVideoError"
              @abort="onDetailVideoAbort"
            ></video>
            <div v-else class="detail-video-empty">
              <el-icon :size="36" color="#ff9b9b"><CircleCloseFilled /></el-icon>
              <div>{{ t('history.videoUrlEmpty') }}</div>
            </div>
            <div v-if="detailVideoLoading" class="detail-video-status">
              <el-icon :size="24" class="spinner"><LoadingIcon /></el-icon>
              <span>{{ t('history.videoLoading') }}</span>
            </div>
            <div v-if="detailVideoFailed" class="detail-video-status error">
              <el-icon :size="24"><CircleCloseFilled /></el-icon>
              <span>{{ t('history.videoCannotPlay') }}</span>
            </div>
          </div>
        </div>
        <div class="detail-info">
          <div class="info-row"><span class="label">{{ t('history.promptLabel') }}：</span><span>{{ detailItem.prompt }}</span></div>
          <div class="info-row"><span class="label">{{ t('history.typeLabel') }}：</span><span>{{ detailItem.type === 'image' ? t('history.image') : t('history.video') }}</span></div>
          <div class="info-row" v-if="detailItem.model"><span class="label">{{ t('history.modelLabel') }}：</span><span>{{ detailItem.model }}</span></div>
          <div class="info-row"><span class="label">{{ t('history.statusLabel') }}：</span><span>{{ detailItem.status || 'success' }}</span></div>
          <div class="info-row"><span class="label">{{ t('history.createdAtLabel') }}：</span><span>{{ detailItem.created_at }}</span></div>
          <div class="info-row url-row">
            <span class="label">{{ t('history.linkLabel') }}：</span>
            <span class="url-value">{{ detailItem.result_url }}</span>
            <el-button size="small" link type="primary" @click="copyLink(detailItem.result_url)">{{ t('history.copyLink') }}</el-button>
            <el-button size="small" link type="primary" @click="downloadDetail">{{ t('history.download') }}</el-button>
            <el-button size="small" link type="primary" @click="openInNewTab">{{ t('history.openNewTab') }}</el-button>
          </div>
        </div>
      </div>
      <template #footer>
        <el-button @click="detailVisible = false">{{ t('common.close') }}</el-button>
        <el-button type="danger" :icon="DeleteIcon" @click="confirmDelete">{{ t('history.deleteRecord') }}</el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="deleteVisible"
      :title="t('history.confirmDeleteTitle')"
      width="400px">
      <div>{{ t('history.confirmDeleteMsg') }}</div>
      <template #footer>
        <el-button @click="deleteVisible = false">{{ t('common.cancel') }}</el-button>
        <el-button type="danger" @click="doDelete">{{ t('common.confirm') }}</el-button>
      </template>
    </el-dialog>

    <!-- 批量删除确认弹窗 -->
    <el-dialog
      v-model="batchDeleteVisible"
      :title="t('history.confirmBatchDeleteTitle')"
      width="460px">
      <div>
        {{ t('history.confirmBatchDeleteMsg1') }} <b style="color:#ff9b9b">{{ selectedIds.length }}</b> {{ t('history.confirmBatchDeleteMsg2') }}
      </div>
      <template #footer>
        <el-button @click="batchDeleteVisible = false">{{ t('common.cancel') }}</el-button>
        <el-button type="danger" :loading="batchDeleting" @click="doBatchDelete">
          {{ t('history.confirmDelete') }} ({{ selectedIds.length }})
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch, nextTick, reactive } from 'vue'
import { ElMessage } from 'element-plus'
import { Refresh, Loading, Document, Delete, VideoPlay, CircleCloseFilled, Edit, Close } from '@element-plus/icons-vue'
import { getHistoryList, deleteHistoryRecord, batchDeleteHistory } from '@/api/history'
import { useI18n } from '@/i18n'

const { t } = useI18n()

// 图标别名：避免与本地方法同名
const LoadingIcon = Loading
const DeleteIcon = Delete
const CloseIcon = Close

const list = ref([])
const loading = ref(false)
const totalCount = ref(0)
const imageCount = ref(0)
const videoCount = ref(0)
const page = ref(1)
const pageSize = ref(12)
const filterType = ref('all')

const detailVisible = ref(false)
const deleteVisible = ref(false)
const detailItem = ref(null)
const detailVideoEl = ref(null)
const detailPoster = ref('')
const detailVideoLoading = ref(false)
const detailVideoFailed = ref(false)

const videoThumbnails = reactive({})
const videoPreviews = reactive({})
const hoveredVideoId = ref(null)
const thumbnailLoading = reactive({})
const previewLoading = reactive({})
const thumbnailFailed = reactive({})

const editMode = ref(false)
const selectedIds = ref([])
const batchDeleteVisible = ref(false)
const batchDeleting = ref(false)

const isAllSelected = computed(() => {
  if (!list.value.length) return false
  return list.value.every(item => selectedIds.value.includes(item.id))
})
const isIndeterminate = computed(() => {
  if (!list.value.length) return false
  const pageIds = list.value.map(item => item.id)
  const selectedOnPage = pageIds.filter(id => selectedIds.value.includes(id))
  return selectedOnPage.length > 0 && selectedOnPage.length < pageIds.length
})

function getVideoStreamUrl(item) {
  if (item.type !== 'video' || !item.result_url) return ''
  return `/api/history/video/${item.id}/stream`
}

function simpleHash(str) {
  let hash = 0
  for (let i = 0; i < str.length; i++) {
    const char = str.charCodeAt(i)
    hash = ((hash << 5) - hash) + char
    hash |= 0
  }
  return Math.abs(hash).toString(36)
}

async function loadVideoThumbnail(item) {
  if (videoThumbnails[item.id] || thumbnailLoading[item.id] || thumbnailFailed[item.id]) return
  thumbnailLoading[item.id] = true
  try {
    const urlHash = item.result_url ? simpleHash(item.result_url) : 'nourl'
    const url = `/api/history/video/${item.id}/thumbnail?v=${urlHash}`
    await new Promise((resolve, reject) => {
      const img = new Image()
      img.onload = resolve
      img.onerror = reject
      img.src = url
    })
    videoThumbnails[item.id] = url
  } catch (e) {
    console.warn('[History] ' + t('history.thumbLoadFail') + ' id=' + item.id, e)
    thumbnailFailed[item.id] = true
  } finally {
    thumbnailLoading[item.id] = false
  }
}

async function loadVideoPreview(item) {
  if (videoPreviews[item.id] || previewLoading[item.id]) return
  previewLoading[item.id] = true
  try {
    const urlHash = item.result_url ? simpleHash(item.result_url) : 'nourl'
    const url = `/api/history/video/${item.id}/preview?v=${urlHash}`
    await new Promise((resolve, reject) => {
      const img = new Image()
      img.onload = resolve
      img.onerror = reject
      img.src = url
    })
    videoPreviews[item.id] = url
  } catch (e) {
    console.warn('[History] ' + t('history.gifLoadFail') + ' id=' + item.id, e)
  } finally {
    previewLoading[item.id] = false
  }
}

function onVideoCardHover(item) {
  hoveredVideoId.value = item.id
  loadVideoPreview(item)
}

function onVideoCardLeave(item) {
  hoveredVideoId.value = null
}

watch(detailVisible, (val) => {
  if (val) {
    detailPoster.value = ''
    detailVideoLoading.value = detailItem.value?.type === 'video' && !!detailItem.value?.result_url
    detailVideoFailed.value = false
  }
})

async function loadList(resetPage = false) {
  if (resetPage) page.value = 1
  loading.value = true
  try {
    const data = await getHistoryList({
      type: filterType.value,
      page: page.value,
      page_size: pageSize.value
    })
    list.value = data.items || []
    totalCount.value = data.total || list.value.length
    imageCount.value = data.total_image_count ?? 0
    videoCount.value = data.total_video_count ?? 0
    list.value.filter(i => i.type === 'video').forEach(item => {
      loadVideoThumbnail(item)
    })
  } catch (e) {
    console.error('[History] ' + t('history.loadFail') + '：', e)
  } finally {
    loading.value = false
  }
}

function handlePageChange(p) {
  page.value = p
  loadList()
}
function handleSizeChange(size) {
  pageSize.value = size
  page.value = 1
  loadList()
}

function showDetail(item) {
  detailItem.value = item
  detailPoster.value = ''
  detailVideoLoading.value = item.type === 'video' && !!item.result_url
  detailVideoFailed.value = false
  detailVisible.value = true
}

function toggleEditMode() {
  editMode.value = !editMode.value
  if (!editMode.value) {
    selectedIds.value = []
  }
}

function handleCardClick(item) {
  if (editMode.value) {
    toggleSelect(item.id)
  } else {
    showDetail(item)
  }
}

function toggleSelect(id) {
  const idx = selectedIds.value.indexOf(id)
  if (idx >= 0) {
    selectedIds.value.splice(idx, 1)
  } else {
    selectedIds.value.push(id)
  }
}

function toggleSelectAll(val) {
  if (val) {
    const pageIds = list.value.map(item => item.id)
    const newSet = new Set(selectedIds.value)
    pageIds.forEach(id => newSet.add(id))
    selectedIds.value = Array.from(newSet)
  } else {
    const pageIds = new Set(list.value.map(item => item.id))
    selectedIds.value = selectedIds.value.filter(id => !pageIds.has(id))
  }
}

function confirmBatchDelete() {
  if (selectedIds.value.length === 0) {
    ElMessage.warning(t('history.pleaseSelectOne'))
    return
  }
  batchDeleteVisible.value = true
}

async function doBatchDelete() {
  if (selectedIds.value.length === 0) return
  batchDeleting.value = true
  try {
    const res = await batchDeleteHistory(selectedIds.value)
    const deletedCount = res?.deleted_count ?? selectedIds.value.length
    ElMessage.success(t('history.batchDeleted').replace('{n}', deletedCount))
    batchDeleteVisible.value = false
    selectedIds.value = []
    loadList()
  } catch (e) {
    // 错误已在拦截器弹出
  } finally {
    batchDeleting.value = false
  }
}

function copyToClipboard(text) {
  if (!text) return Promise.resolve()
  if (navigator.clipboard && window.isSecureContext) {
    return navigator.clipboard.writeText(text)
  }
  const ta = document.createElement('textarea')
  ta.value = text
  ta.style.position = 'fixed'
  ta.style.left = '-9999px'
  ta.style.top = '0'
  document.body.appendChild(ta)
  ta.select()
  let ok = false
  try { ok = document.execCommand('copy') } catch (e) { ok = false }
  document.body.removeChild(ta)
  return ok ? Promise.resolve() : Promise.reject(new Error('copy failed'))
}

function copyLink(url) {
  if (!url) {
    ElMessage.warning(t('history.noValidLink'))
    return
  }
  copyToClipboard(url)
    .then(() => ElMessage.success(t('history.linkCopied')))
    .catch(() => ElMessage.error(t('history.copyLinkFailed')))
}

async function downloadDetail() {
  if (!detailItem.value?.result_url) {
    ElMessage.warning(t('history.noValidResource'))
    return
  }
  const url = detailItem.value.result_url
  const type = detailItem.value.type
  try {
    ElMessage.info(t('history.preparingDownload'))
    const response = await fetch(url, { mode: 'cors' })
    if (!response.ok) throw new Error('HTTP ' + response.status)
    const blob = await response.blob()
    const blobUrl = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = blobUrl
    a.download = 'agnes-' + type + '-' + (detailItem.value.id || Date.now())
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    setTimeout(() => URL.revokeObjectURL(blobUrl), 1000)
    ElMessage.success(t('history.downloadStarted'))
  } catch (err) {
    console.warn('[History] ' + t('history.downloadFallback') + '：', err)
    ElMessage.warning(t('preview.videoCorsWarning'))
    window.open(url, '_blank', 'noopener,noreferrer')
  }
}

function openInNewTab() {
  if (!detailItem.value?.result_url) {
    ElMessage.warning(t('history.noValidResource'))
    return
  }
  window.open(detailItem.value.result_url, '_blank', 'noopener,noreferrer')
  ElMessage.success(t('history.openedInNewTab'))
}

function captureDetailPoster() {
  const el = detailVideoEl.value
  if (!el || !el.videoWidth || detailPoster.value) return
  try {
    const canvas = document.createElement('canvas')
    const scale = Math.min(1, 720 / el.videoWidth)
    canvas.width = Math.floor(el.videoWidth * scale)
    canvas.height = Math.floor(el.videoHeight * scale)
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    ctx.drawImage(el, 0, 0, canvas.width, canvas.height)
    detailPoster.value = canvas.toDataURL('image/jpeg', 0.82)
  } catch (e) {
    console.warn('[History] ' + t('history.canvasFailed') + '：', e)
  }
}

function onDetailVideoCanPlay() {
  detailVideoLoading.value = false
  detailVideoFailed.value = false
}

function onDetailVideoError(e) {
  console.error('[History] ' + t('history.videoPlayFail') + '：', e)
  detailVideoLoading.value = false
  detailVideoFailed.value = true
  ElMessage.error(t('history.videoLoadFailed'))
}

function onDetailVideoAbort() {
  console.warn('[History] ' + t('history.videoAborted'))
  detailVideoLoading.value = false
  detailVideoFailed.value = true
  ElMessage.warning(t('history.videoPlayRestricted'))
}

function confirmDelete() {
  deleteVisible.value = true
}
async function doDelete() {
  if (!detailItem.value) return
  try {
    await deleteHistoryRecord(detailItem.value.id)
    ElMessage.success(t('history.deleted'))
    deleteVisible.value = false
    detailVisible.value = false
    loadList()
  } catch (e) {
    // 错误已在拦截器弹出
  }
}

function truncate(text, max) {
  if (!text) return ''
  return text.length > max ? text.slice(0, max) + '…' : text
}
function formatTime(t) {
  if (!t) return ''
  const d = new Date(t)
  if (isNaN(d.getTime())) return String(t).slice(0, 19)
  return d.toLocaleString()
}

onMounted(() => loadList())
</script>

<style scoped>
.history-view { color: #e8eef7; }

.filter-wrap {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  padding: 12px 16px;
  background: rgba(15, 24, 42, 0.5);
  border-radius: 10px;
  border: 1px solid rgba(120, 170, 255, 0.15);
}

.filter-actions {
  display: flex;
  gap: 10px;
  align-items: center;
}

.edit-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  margin-bottom: 16px;
  background: rgba(60, 30, 30, 0.45);
  border: 1px solid rgba(255, 155, 155, 0.25);
  border-radius: 10px;
}
.edit-left {
  display: flex;
  align-items: center;
  gap: 16px;
  color: #d5e3f7;
}
.selection-info {
  font-size: 13px;
  color: #8ba3c9;
}
.selection-count {
  color: #ff9b9b;
  font-size: 15px;
}
.edit-right {
  display: flex;
  gap: 10px;
}

.loading-state, .empty-state {
  padding: 80px 20px;
  text-align: center;
  color: #6b84aa;
}
.spinner { animation: spin 1.2s linear infinite; color: #6b9cff; }
@keyframes spin { to { transform: rotate(360deg); } }
.empty-text { margin-top: 16px; font-size: 14px; }

.history-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 18px;
}
.history-card {
  background: rgba(15, 24, 42, 0.7);
  border: 1px solid rgba(120, 170, 255, 0.15);
  border-radius: 12px;
  overflow: hidden;
  cursor: pointer;
  transition: all 0.2s ease;
  position: relative;
}
.history-card.is-selected {
  border-color: rgba(255, 155, 155, 0.75);
  box-shadow: 0 0 0 2px rgba(255, 155, 155, 0.4), 0 8px 24px rgba(100, 150, 255, 0.2);
  transform: translateY(-2px);
}
.card-checkbox {
  position: absolute;
  top: 10px;
  right: 10px;
  z-index: 2;
  padding: 6px 8px;
  background: rgba(15, 24, 42, 0.7);
  border-radius: 8px;
  border: 1px solid rgba(120, 170, 255, 0.2);
  cursor: pointer;
}
.history-card:hover {
  transform: translateY(-4px);
  box-shadow: 0 8px 32px rgba(100, 150, 255, 0.25);
  border-color: rgba(120, 170, 255, 0.4);
}
.history-card.is-selected:hover {
  transform: translateY(-2px);
}
.card-preview {
  position: relative;
  width: 100%;
  aspect-ratio: 4/3;
  background: #0a1220;
  overflow: hidden;
}
.card-preview img,
.card-preview video {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.video-thumb {
  width: 100%;
  height: 100%;
  position: relative;
  background: linear-gradient(135deg, #1a2744 0%, #0f1a30 100%);
  overflow: hidden;
}
.video-thumb-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
  transition: opacity 0.3s ease;
}
.video-thumb-placeholder {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  color: #8ba3c9;
}
.video-thumb-placeholder .play-icon {
  color: #6b9cff;
  filter: drop-shadow(0 4px 12px rgba(107, 156, 255, 0.4));
}
.video-thumb-label {
  font-size: 13px;
  font-weight: 500;
}
.video-preview-gif {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
  z-index: 1;
}
.video-play-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.25);
  z-index: 2;
  transition: opacity 0.2s ease;
  color: rgba(255, 255, 255, 0.85);
}
.video-play-overlay .el-icon {
  filter: drop-shadow(0 2px 8px rgba(0, 0, 0, 0.5));
}
.video-thumb:hover .video-play-overlay {
  opacity: 0;
}
.video-thumb:hover .video-thumb-img {
  opacity: 0;
}
.type-badge {
  position: absolute;
  top: 10px;
  left: 10px;
  padding: 4px 10px;
  border-radius: 20px;
  font-size: 11px;
  font-weight: 600;
  background: rgba(15, 24, 42, 0.75);
  backdrop-filter: blur(4px);
}
.type-badge.image { color: #8bb4ff; border: 1px solid rgba(139, 180, 255, 0.5); }
.type-badge.video { color: #c4a7ff; border: 1px solid rgba(196, 167, 255, 0.5); }
.card-meta { padding: 12px 14px; }
.card-prompt {
  font-size: 13px;
  color: #d5e3f7;
  line-height: 1.5;
  min-height: 40px;
  overflow: hidden;
}
.card-time {
  margin-top: 8px;
  font-size: 12px;
  color: #6b84aa;
}

.pagination-wrap {
  margin-top: 24px;
  text-align: center;
}

.detail-content { display: flex; gap: 24px; flex-direction: column; align-items: center; }
.detail-media { width: 100%; text-align: center; }
.detail-media img {
  max-width: 100%;
  max-height: 400px;
  border-radius: 10px;
  object-fit: contain;
}
.detail-media video {
  max-width: 100%;
  max-height: 400px;
  border-radius: 10px;
  background: #000;
}
.detail-info {
  width: 100%;
  background: rgba(15, 24, 42, 0.5);
  padding: 16px;
  border-radius: 10px;
}
.info-row { padding: 6px 0; font-size: 13px; line-height: 1.6; color: #d5e3f7; }
.label { color: #8ba3c9; margin-right: 8px; font-weight: 500; }
.url-row {
  margin-top: 8px;
  padding: 12px !important;
  background: rgba(10, 20, 40, 0.6);
  border: 1px solid rgba(120, 170, 255, 0.15);
  border-radius: 8px;
  word-break: break-all;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
}
.url-row .url-value {
  color: #d5e3f7;
  font-family: monospace;
  font-size: 12px;
  max-width: 100%;
  flex: 1;
  min-width: 200px;
}
.detail-video {
  max-width: 100%;
  max-height: 400px;
  border-radius: 10px;
  background: #000;
}

.detail-video-wrap {
  position: relative;
  width: 100%;
  max-width: 100%;
}

.detail-video-empty {
  padding: 40px 20px;
  background: #0a1220;
  border-radius: 10px;
  text-align: center;
  color: #8ba3c9;
  font-size: 13px;
}
.detail-video-empty div { margin-top: 10px; }

.detail-video-status {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  background: rgba(0, 0, 0, 0.72);
  border-radius: 10px;
  color: #d5e3f7;
  font-size: 13px;
  pointer-events: none;
}
.detail-video-status.error {
  color: #ff9b9b;
}

.spinner {
  display: inline-block;
  animation: spin 1.2s linear infinite;
  color: #6b9cff;
}
@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>
