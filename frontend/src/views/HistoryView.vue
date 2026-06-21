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
        <!-- 批量处理模式切换按钮 -->
        <el-button
          :type="editMode ? 'warning' : 'default'"
          :icon="editMode ? CloseIcon : Edit"
          @click="toggleEditMode">
          {{ editMode ? t('history.exitEdit') : t('history.batchManage') }}
        </el-button>
      </div>
    </div>

    <!-- 批量处理模式操作栏（全选 + 批量下载 + 批量删除） -->
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
          type="primary"
          :icon="Download"
          :disabled="selectedIds.length === 0"
          :loading="batchDownloading"
          @click="batchDownload">
          {{ t('history.downloadSelected') }} ({{ selectedIds.length }})
        </el-button>
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
            :src="item.result_url ?? ''"
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
          <!-- 生成模式标签（文生图 / 图生图 / 文生视频 / 图生视频 / 关键帧） -->
          <div v-if="item.mode" class="mode-badge" :class="'mode-' + item.type">
            {{ t('params.mode.' + item.mode) || item.mode }}
          </div>
          <!-- 快捷操作按钮组（非编辑模式下显示）：放大 / 下载 / 删除，分别调用不同模块 -->
          <!-- 放在 card-preview 内，z-index 足够高以确保不被其他蒙层遮挡 -->
          <div v-if="!editMode" class="card-actions">
            <!-- 放大：调用 ImageViewer 图片查看器模块 -->
            <div
              v-if="item.type === 'image'"
              class="card-action-btn"
              @click.stop="openImageViewer(item)"
              :title="t('imageViewer.title')">
              <el-icon size="16"><ZoomIn /></el-icon>
            </div>
            <!-- 下载：调用后端代理下载模块 -->
            <div
              class="card-action-btn"
              @click.stop="downloadItem(item)"
              :title="t('history.download')">
              <el-icon size="16"><Download /></el-icon>
            </div>
            <!-- 删除：调用历史记录删除模块（带确认弹窗） -->
            <div
              class="card-action-btn card-action-delete"
              @click.stop="quickDelete(item)"
              :title="t('history.delete')">
              <el-icon size="16"><Delete /></el-icon>
            </div>
          </div>
        </div>
        <div class="card-meta">
          <div class="card-prompt">{{ truncate(item.prompt, 80) }}</div>
          <div class="card-time">{{ formatTime(item.created_at ?? '') }}</div>
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
          <img
            v-if="detailItem.type === 'image'"
            :src="detailItem.result_url ?? ''"
            :alt="t('history.imageDetailAlt')"
            @click="openImageViewer(detailItem)"
            class="detail-image"
          />
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
              <el-icon :size="36" :color="'var(--agnes-error)'"><CircleCloseFilled /></el-icon>
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
          <div class="info-row" v-if="detailItem.mode"><span class="label">{{ t('history.modeLabel') }}：</span><span class="mode-text">{{ t('params.mode.' + detailItem.mode) || detailItem.mode }}</span></div>
          <div class="info-row"><span class="label">{{ t('history.statusLabel') }}：</span><span>{{ detailItem.status || 'success' }}</span></div>
          <div class="info-row"><span class="label">{{ t('history.creditsConsumedLabel') }}：</span><span class="credits-value">{{ detailItem.credits_consumed ?? 0 }}</span></div>
          <div class="info-row"><span class="label">{{ t('history.createdAtLabel') }}：</span><span>{{ detailItem.created_at }}</span></div>
          <div class="info-row url-row">
            <span class="label">{{ t('history.linkLabel') }}：</span>
            <span class="url-value">{{ detailItem.result_url }}</span>
            <el-button size="small" link type="primary" @click="copyLink(detailItem.result_url ?? '')">{{ t('history.copyLink') }}</el-button>
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
        {{ t('history.confirmBatchDeleteMsg1') }} <b class="batch-delete-count">{{ selectedIds.length }}</b> {{ t('history.confirmBatchDeleteMsg2') }}
      </div>
      <template #footer>
        <el-button @click="batchDeleteVisible = false">{{ t('common.cancel') }}</el-button>
        <el-button type="danger" :loading="batchDeleting" @click="doBatchDelete">
          {{ t('history.confirmDelete') }} ({{ selectedIds.length }})
        </el-button>
      </template>
    </el-dialog>

    <!-- 独立图片查看器：点击历史图片后弹出，支持缩放/平移/旋转/下载 -->
    <ImageViewer
      v-model:visible="viewerVisible"
      :url="viewerUrl"
      :download-url="viewerDownloadUrl"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, watch, nextTick, reactive } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Refresh, Loading, Document, Delete, VideoPlay, CircleCloseFilled, Edit, Close, Download, ZoomIn } from '@element-plus/icons-vue'
import ImageViewer from '@/components/ImageViewer.vue'
import { getHistoryList, deleteHistoryRecord, batchDeleteHistory } from '@/api/history'
import client from '@/api/client'
import { useTaskQueueStore } from '@/stores/taskQueue'
import { useI18n } from '@/i18n'
import type { GenerationRecord } from '@/types'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()

// ---------- 从积分明细跳转过来时，通过 task_id 自动定位并打开详情 ----------
const pendingTaskId = ref<string>('')

// ---------- 图片查看器：历史记录图片点击后弹出，支持缩放/平移/旋转/下载 ----------
const viewerVisible = ref(false)
const viewerUrl = ref('')
const viewerDownloadUrl = ref('')
function openImageViewer(item: GenerationRecord) {
  if (!item || item.type !== 'image' || !item.result_url) return
  viewerUrl.value = item.result_url
  // 下载时优先走代理下载接口，确保可以下载
  viewerDownloadUrl.value = '/api/history/' + item.id + '/download'
  viewerVisible.value = true
}

// 监听全局任务队列的刷新信号，实现生成按钮点击后自动刷新历史列表
const queue = useTaskQueueStore()

// 图标别名：避免与本地方法同名
const LoadingIcon = Loading
const DeleteIcon = Delete
const CloseIcon = Close

const list = ref<GenerationRecord[]>([])
const loading = ref(false)
const totalCount = ref(0)
const imageCount = ref(0)
const videoCount = ref(0)
const page = ref(1)
const pageSize = ref(12)
const filterType = ref('all')

const detailVisible = ref(false)
const deleteVisible = ref(false)
const detailItem = ref<GenerationRecord | null>(null)
const detailVideoEl = ref<HTMLVideoElement | null>(null)
const detailPoster = ref('')
const detailVideoLoading = ref(false)
const detailVideoFailed = ref(false)

const videoThumbnails = reactive<Record<string, string>>({})
const videoPreviews = reactive<Record<string, string>>({})
const hoveredVideoId = ref<number | null>(null)
const thumbnailLoading = reactive<Record<string, boolean>>({})
const previewLoading = reactive<Record<string, boolean>>({})
const thumbnailFailed = reactive<Record<string, boolean>>({})

const editMode = ref(false)
const selectedIds = ref<number[]>([])
const batchDeleteVisible = ref(false)
const batchDeleting = ref(false)
const batchDownloading = ref(false)

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

/**
 * 获取视频播放地址
 * 直接使用 Agnes CDN 的 result_url，因为 CDN 本身就是公开可访问的
 * 不走后端代理流（代理流需要鉴权，而 <video> 标签无法携带 JWT）
 */
function getVideoStreamUrl(item: GenerationRecord) {
  if (item.type !== 'video' || !item.result_url) return ''
  return item.result_url
}

/**
 * 通过 axios 下载二进制资源并生成 blob URL
 * 这样请求会经过 axios 请求拦截器，自动携带 JWT token
 * 解决 <img src="url"> 或 new Image().src 无法携带 JWT 的问题
 */
async function fetchBlobAsUrl(url: string): Promise<string> {
  const blob = await client.get(url, {
    responseType: 'blob',
    silent: true,
  }) as unknown as Blob
  return URL.createObjectURL(blob)
}

async function loadVideoThumbnail(item: GenerationRecord) {
  if (videoThumbnails[item.id] || thumbnailLoading[item.id] || thumbnailFailed[item.id]) return
  thumbnailLoading[item.id] = true
  try {
    // 通过 axios 下载，请求拦截器会自动注入 JWT token
    // 后端按 user_id 隔离，只有当前用户能获取自己视频的缩略图
    const url = `/api/history/video/${item.id}/thumbnail`
    const blobUrl = await fetchBlobAsUrl(url)
    videoThumbnails[item.id] = blobUrl
  } catch (e) {
    console.warn('[History] ' + t('history.thumbLoadFail') + ' id=' + item.id, e)
    thumbnailFailed[item.id] = true
  } finally {
    thumbnailLoading[item.id] = false
  }
}

async function loadVideoPreview(item: GenerationRecord) {
  if (videoPreviews[item.id] || previewLoading[item.id]) return
  previewLoading[item.id] = true
  try {
    // 通过 axios 下载，自动携带 JWT token
    const url = `/api/history/video/${item.id}/preview`
    const blobUrl = await fetchBlobAsUrl(url)
    videoPreviews[item.id] = blobUrl
  } catch (e) {
    console.warn('[History] ' + t('history.gifLoadFail') + ' id=' + item.id, e)
  } finally {
    previewLoading[item.id] = false
  }
}

function onVideoCardHover(item: GenerationRecord) {
  hoveredVideoId.value = item.id
  loadVideoPreview(item)
}

function onVideoCardLeave(_item: GenerationRecord) {
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

    // 如果是从积分明细跳转过来（带 task_id），自动定位并打开详情
    if (pendingTaskId.value) {
      const matched = list.value.find(i => i.task_id === pendingTaskId.value)
      if (matched) {
        showDetail(matched)
      } else {
        ElMessage.warning(t('history.taskIdNotFound'))
      }
      pendingTaskId.value = ''
      // 清除 URL 上的 task_id 参数，避免刷新重复弹出
      router.replace({ path: route.path, query: {} })
    }
  } catch (e) {
    console.error('[History] ' + t('history.loadFail') + '：', e)
  } finally {
    loading.value = false
  }
}

function handlePageChange(p: number) {
  page.value = p
  loadList()
}
function handleSizeChange(size: number) {
  pageSize.value = size
  page.value = 1
  loadList()
}

function showDetail(item: GenerationRecord) {
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

function handleCardClick(item: GenerationRecord) {
  if (editMode.value) {
    toggleSelect(item.id)
  } else {
    showDetail(item)
  }
}

function toggleSelect(id: number) {
  const idx = selectedIds.value.indexOf(id)
  if (idx >= 0) {
    selectedIds.value.splice(idx, 1)
  } else {
    selectedIds.value.push(id)
  }
}

function toggleSelectAll(val: boolean) {
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

/** 批量下载选中项（单图直接下载，多图打包为 zip） */
async function batchDownload() {
  if (selectedIds.value.length === 0) {
    ElMessage.warning(t('history.pleaseSelectOne'))
    return
  }
  batchDownloading.value = true
  try {
    const baseURL = import.meta.env.VITE_API_BASE_URL || ''

    if (selectedIds.value.length === 1) {
      // 单图：复用已有的单文件下载逻辑，直接下载
      const downloadUrl = `${baseURL}/api/history/${selectedIds.value[0]}/download`
      const a = document.createElement('a')
      a.href = downloadUrl
      a.download = ''
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
    } else {
      // 多图：打包为 zip 下载
      const ids = selectedIds.value.join(',')
      const downloadUrl = `${baseURL}/api/history/batch-download?ids=${ids}`
      const a = document.createElement('a')
      a.href = downloadUrl
      a.download = ''
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
    }
    ElMessage.success(t('history.downloadStarted'))
  } catch (err) {
    console.warn('[History] 批量下载失败：', err)
    ElMessage.warning(t('preview.videoCorsWarning'))
  } finally {
    batchDownloading.value = false
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
    ElMessage.success(t('history.batchDeleted').replace('{n}', String(deletedCount)))
    batchDeleteVisible.value = false
    selectedIds.value = []
    loadList()
  } catch (e) {
    // 错误已在拦截器弹出
  } finally {
    batchDeleting.value = false
  }
}

function copyToClipboard(text: string) {
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

function copyLink(url: string) {
  if (!url) {
    ElMessage.warning(t('history.noValidLink'))
    return
  }
  copyToClipboard(url)
    .then(() => ElMessage.success(t('history.linkCopied')))
    .catch(() => ElMessage.error(t('history.copyLinkFailed')))
}

/** 卡片快捷下载（列表中直接点击下载图标） */
function downloadItem(item: GenerationRecord) {
  if (!item?.result_url) {
    ElMessage.warning(t('history.noValidResource'))
    return
  }
  const baseURL = import.meta.env.VITE_API_BASE_URL || ''
  const downloadUrl = `${baseURL}/api/history/${item.id}/download`
  const a = document.createElement('a')
  a.href = downloadUrl
  a.download = ''
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  ElMessage.success(t('history.downloadStarted'))
}

/** 卡片快捷删除（列表中直接点击删除图标）——调用历史记录删除模块 */
async function quickDelete(item: GenerationRecord) {
  if (!item?.id) return
  // 复用详情弹窗中的 confirmDelete 逻辑，先设置当前项再弹出确认
  detailItem.value = item
  confirmDelete()
}

async function downloadDetail() {
  if (!detailItem.value?.result_url) {
    ElMessage.warning(t('history.noValidResource'))
    return
  }
  const url = detailItem.value.result_url
  const type = detailItem.value.type
  const recordId = detailItem.value.id
  try {
    // 通过后端代理下载（使用 record_id 端点），强制浏览器保存文件
    const baseURL = import.meta.env.VITE_API_BASE_URL || ''
    const downloadUrl = `${baseURL}/api/history/${recordId}/download`
    const a = document.createElement('a')
    a.href = downloadUrl
    a.download = ''  // 让后端 Content-Disposition 控制文件名
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    ElMessage.success(t('history.downloadStarted'))
  } catch (err) {
    console.warn('[History] 下载失败：', err)
    ElMessage.warning(t('preview.videoCorsWarning'))
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

function onDetailVideoError(e: Event) {
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

function truncate(text: string, max: number) {
  if (!text) return ''
  return text.length > max ? text.slice(0, max) + '…' : text
}
function formatTime(t: string) {
  if (!t) return ''
  const d = new Date(t)
  if (isNaN(d.getTime())) return String(t).slice(0, 19)
  return d.toLocaleString()
}

// 【历史自动刷新】每当有新任务完成/失败/取消时，自动刷新历史列表
// 使用 watch 监听全局 taskQueue store 的 historyRefreshSignal，避免手动点击刷新按钮
watch(
  () => queue.historyRefreshSignal,
  (newVal, oldVal) => {
    if (oldVal === 0 && newVal === 0) return
    // 稍微延迟一点，确保后端数据已写入（任务可能需要几百毫秒入库）
    setTimeout(() => {
      loadList()
    }, 500)
  },
)

/**
 * 释放所有视频相关的 blob URL，避免内存泄漏
 */
function clearVideoBlobUrls() {
  Object.values(videoThumbnails).forEach(url => {
    if (url && url.startsWith('blob:')) URL.revokeObjectURL(url)
  })
  Object.values(videoPreviews).forEach(url => {
    if (url && url.startsWith('blob:')) URL.revokeObjectURL(url)
  })
}

// 【用户隔离】用户登录/登出后自动刷新历史列表，确保只看自己的数据
// 由于 HistoryView 在 cachedViews 中被 keep-alive，不会重新 onMounted，
// 因此需要通过事件监听来触发数据空间切换
function handleUserSwitch() {
  clearVideoBlobUrls()
  list.value = []
  totalCount.value = 0
  imageCount.value = 0
  videoCount.value = 0
  loadList()
}

onMounted(() => {
  // 读取 URL 查询参数 task_id（从积分明细跳转过来时携带）
  const qTaskId = route.query.task_id
  if (typeof qTaskId === 'string' && qTaskId) {
    pendingTaskId.value = qTaskId
  }
  loadList()
  if (typeof window !== 'undefined') {
    window.addEventListener('agnes:user-login', handleUserSwitch as EventListener)
    window.addEventListener('agnes:user-logout', handleUserSwitch as EventListener)
  }
})

onBeforeUnmount(() => {
  clearVideoBlobUrls()
  if (typeof window !== 'undefined') {
    window.removeEventListener('agnes:user-login', handleUserSwitch as EventListener)
    window.removeEventListener('agnes:user-logout', handleUserSwitch as EventListener)
  }
})
</script>

<style scoped>
.history-view { color: var(--agnes-text-primary); }

.filter-wrap {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  padding: 12px 16px;
  background: var(--agnes-bg-inset);
  border-radius: 10px;
  border: 1px solid var(--agnes-primary-border-faint);
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
  background: var(--agnes-error-bg);
  border: 1px solid var(--agnes-error-border);
  border-radius: 10px;
}
.edit-left {
  display: flex;
  align-items: center;
  gap: 16px;
  color: var(--agnes-text-primary);
}
.selection-info {
  font-size: 13px;
  color: var(--agnes-text-muted);
}
.selection-count {
  color: var(--agnes-error);
  font-size: 15px;
}
/* 批量删除确认弹窗中的数字高亮 */
.batch-delete-count {
  color: var(--agnes-error);
  font-weight: 700;
}
.edit-right {
  display: flex;
  gap: 10px;
}

.loading-state, .empty-state {
  padding: 80px 20px;
  text-align: center;
  color: var(--agnes-text-faint);
}
.spinner { animation: spin 1.2s linear infinite; color: var(--agnes-primary); }
@keyframes spin { to { transform: rotate(360deg); } }
.empty-text { margin-top: 16px; font-size: 14px; }

.history-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 18px;
}
.history-card {
  background: var(--agnes-bg-elevated);
  border: 1px solid var(--agnes-primary-border-faint);
  border-radius: 12px;
  overflow: hidden;
  cursor: pointer;
  transition: all 0.2s ease;
  position: relative;
}
.history-card.is-selected {
  border-color: var(--agnes-error);
  box-shadow: 0 0 0 2px var(--agnes-error-border), 0 8px 24px var(--agnes-primary-border-faint);
  transform: translateY(-2px);
}
.card-checkbox {
  position: absolute;
  top: 10px;
  right: 10px;
  z-index: 2;
  padding: 6px 8px;
  background: var(--agnes-bg-elevated);
  border-radius: 8px;
  border: 1px solid var(--agnes-primary-border-faint);
  cursor: pointer;
}
.history-card:hover {
  transform: translateY(-4px);
  box-shadow: 0 8px 32px var(--agnes-brand-glow);
  border-color: var(--agnes-primary-border);
}
.history-card.is-selected:hover {
  transform: translateY(-2px);
}
.card-preview {
  position: relative;
  width: 100%;
  aspect-ratio: 4/3;
  background: var(--agnes-bg-base);
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
  background: var(--agnes-bg-elevated);
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
  color: var(--agnes-text-muted);
}
.video-thumb-placeholder .play-icon {
  color: var(--agnes-primary);
  filter: drop-shadow(0 4px 12px var(--agnes-primary-border));
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
/* 播放图标蒙层：视频缩略图属于沉浸式媒体预览，两套主题都用固定深色半透明背景，确保缩略图本身和白色播放图标都可见 */
.video-play-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(10, 15, 30, 0.4);
  z-index: 2;
  transition: opacity 0.2s ease;
  color: rgba(255, 255, 255, 0.9);
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
/* 类型标签（图片 / 视频）：叠在缩略图上，两套主题都用半透明深色背景 + 浅色文字 */
.type-badge {
  position: absolute;
  top: 10px;
  left: 10px;
  padding: 4px 10px;
  border-radius: 20px;
  font-size: 11px;
  font-weight: 600;
  color: #ffffff;
  border: 1px solid rgba(255, 255, 255, 0.25);
  background: rgba(10, 15, 30, 0.55);
  backdrop-filter: blur(4px);
}
.type-badge.image { color: #8bb4ff; border: 1px solid rgba(139, 180, 255, 0.5); }
.type-badge.video { color: #c4a7ff; border: 1px solid rgba(196, 167, 255, 0.5); }

/* 生成模式标签（文生图 / 图生图 等）：叠在缩略图上，两套主题都用半透明深色背景 + 浅色文字 */
.mode-badge {
  position: absolute;
  top: 10px;
  left: 90px;
  padding: 4px 10px;
  border-radius: 20px;
  font-size: 11px;
  font-weight: 600;
  background: rgba(10, 15, 30, 0.55);
  backdrop-filter: blur(4px);
}
.mode-badge.mode-image {
  color: #ffd98b;
  border: 1px solid rgba(255, 217, 139, 0.5);
}
.mode-badge.mode-video {
  color: #8be9d0;
  border: 1px solid rgba(139, 233, 208, 0.5);
}
/* 详情页生成模式文字：用主题感知的 warning 色，浅色模式下为深橙、深色模式下为亮橙黄，保证两套主题下对比度均达标 */
.mode-text {
  color: var(--agnes-warning);
  font-weight: 600;
}

/* 卡片快捷操作按钮组（放大 / 下载 / 删除）—— 放在 card-preview 内部，z-index 足够高以确保不被内部 overlay 遮挡 */
.card-actions {
  position: absolute;
  bottom: 10px;
  right: 10px;
  z-index: 100;
  display: flex;
  gap: 6px;
}
.card-action-btn {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--agnes-bg-elevated);
  backdrop-filter: blur(4px);
  border-radius: 8px;
  border: 1px solid var(--agnes-primary-border);
  color: var(--agnes-primary-soft);
  cursor: pointer;
  opacity: 0;
  pointer-events: none;
  transition: all 0.2s ease;
}
.history-card:hover .card-action-btn {
  opacity: 1;
  pointer-events: auto;
}
.card-action-btn:hover {
  background: var(--agnes-info-bg);
  border-color: var(--agnes-primary);
  color: #fff;
}
/* 删除按钮：独立的危险色样式，区别于放大/下载 */
.card-action-btn.card-action-delete {
  color: var(--agnes-error);
  border-color: var(--agnes-error-border);
}
.card-action-btn.card-action-delete:hover {
  background: var(--agnes-error-bg);
  border-color: var(--agnes-error);
  color: #fff;
}
.card-meta { padding: 12px 14px; }
.card-prompt {
  font-size: 13px;
  color: var(--agnes-text-primary);
  line-height: 1.5;
  min-height: 40px;
  overflow: hidden;
}
.card-time {
  margin-top: 8px;
  font-size: 12px;
  color: var(--agnes-text-faint);
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
  cursor: zoom-in;
  transition: opacity 0.2s ease, transform 0.2s ease, box-shadow 0.2s ease;
}
.detail-media img:hover {
  opacity: 0.92;
  transform: scale(1.008);
  box-shadow: 0 8px 28px var(--agnes-primary-border-faint);
}
.detail-media video {
  max-width: 100%;
  max-height: 400px;
  border-radius: 10px;
  background: var(--agnes-bg-dark-surface);
}
.detail-info {
  width: 100%;
  background: var(--agnes-bg-inset);
  padding: 16px;
  border-radius: 10px;
}
.info-row { padding: 6px 0; font-size: 13px; line-height: 1.6; color: var(--agnes-text-primary); }
.label { color: var(--agnes-text-muted); margin-right: 8px; font-weight: 500; }
.credits-value { color: var(--agnes-credits-value); font-weight: 600; }
.url-row {
  margin-top: 8px;
  padding: 12px !important;
  background: var(--agnes-bg-elevated);
  border: 1px solid var(--agnes-primary-border-faint);
  border-radius: 8px;
  word-break: break-all;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
}
.url-row .url-value {
  color: var(--agnes-text-primary);
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
  background: var(--agnes-bg-dark-surface);
}

.detail-video-wrap {
  position: relative;
  width: 100%;
  max-width: 100%;
}

.detail-video-empty {
  padding: 40px 20px;
  background: var(--agnes-bg-base);
  border-radius: 10px;
  text-align: center;
  color: var(--agnes-text-muted);
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
  background: var(--agnes-bg-dark-surface);
  border-radius: 10px;
  color: var(--agnes-text-primary);
  font-size: 13px;
  pointer-events: none;
}
.detail-video-status.error {
  color: var(--agnes-error);
}

.spinner {
  display: inline-block;
  animation: spin 1.2s linear infinite;
  color: var(--agnes-primary);
}
@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>
