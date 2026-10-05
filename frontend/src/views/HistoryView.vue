<!-- =====================================================
     生成历史视图 HistoryView —— 任务视图定位
     - 与资产库分工：资产库=成果媒体库（浏览/批量/分享），历史=任务执行记录
     - 行式任务列表：缩略图 + 提示词 + 模型/模式 + 状态（含失败原因）+ 积分/时间
     - 筛选：类型 / 来源 / 状态；批量模式下仅保留批量删除（成果类批量操作归资产库）
     - 保留任务侧独有能力：失败归因透出、后期处理（调色/剪辑）、存为资产兜底、
     - 积分明细 task_id 跳转定位
     - 所有 UI 文案通过 t() 函数调用
     ===================================================== -->

<template>
  <div class="history-view">
    <h2 class="page-title"><el-icon><Document /></el-icon> {{ t('history.title') }}</h2>
    <p class="page-desc">{{ t('history.desc') }}</p>

    <!-- 筛选 Tab：类型 / 来源 / 状态 -->
    <div class="filter-wrap">
      <el-radio-group v-model="filterType" @change="loadList(true)">
        <el-radio-button value="all">{{ t('history.all') }} ({{ imageCount + videoCount }})</el-radio-button>
        <el-radio-button value="image">{{ t('history.image') }} ({{ imageCount }})</el-radio-button>
        <el-radio-button value="video">{{ t('history.video') }} ({{ videoCount }})</el-radio-button>
      </el-radio-group>
      <!-- 来源筛选已随画廊定位退役：任务视图统一展示全部来源任务，成果媒体在资产库按来源筛 -->
      <!-- 状态筛选（任务视图）：成果浏览去资产库，这里按任务执行状态排查 -->
      <el-radio-group v-model="filterStatus" @change="loadList(true)" class="source-filter">
        <el-radio-button value="">{{ t('history.statusFilter.all') }}</el-radio-button>
        <el-radio-button value="success">{{ t('history.statusFilter.success') }}</el-radio-button>
        <el-radio-button value="failed">{{ t('history.statusFilter.failed') }}</el-radio-button>
        <el-radio-button value="pending">{{ t('history.statusFilter.pending') }}</el-radio-button>
      </el-radio-group>
      <div class="filter-actions">
        <el-button type="primary" :icon="Refresh" :loading="loading" @click="loadList(true)">
          {{ t('common.refresh') }}
        </el-button>
        <!-- 批量处理模式切换按钮（历史仅保留批量删除，成果批量操作在资产库） -->
        <el-button
          :type="editMode ? 'warning' : 'default'"
          :icon="editMode ? CloseIcon : Edit"
          @click="toggleEditMode">
          {{ editMode ? t('history.exitEdit') : t('history.batchManage') }}
        </el-button>
      </div>
    </div>

    <!-- 批量处理模式操作栏（全选 + 批量删除） -->
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

    <!-- 任务列表（行式） -->
    <div v-else class="task-list">
      <div
        v-for="item in list"
        :key="item.id"
        class="task-row"
        :class="{ 'is-selected': editMode && selectedIds.includes(item.id) }"
        @click="handleRowClick(item)">
        <!-- 批量模式下的选择框 -->
        <div v-if="editMode" class="row-checkbox" @click.stop="toggleSelect(item.id)">
          <el-checkbox :model-value="selectedIds.includes(item.id)" />
        </div>

        <!-- 缩略图：图片直接渲染；视频取首帧缩略图；失败/进行中任务显示状态图标 -->
        <div class="row-thumb">
          <ImageWithWatermark
            v-if="item.type === 'image' && item.result_url"
            :src="item.result_url"
            :alt="t('history.thumbnailAlt')"
            loading="lazy"
            fit="cover"
            class="row-thumb-media"
          />
          <img
            v-else-if="item.type === 'video' && item.result_url && videoThumbnails[item.id]"
            :src="videoThumbnails[item.id]"
            :alt="t('history.videoThumbAlt')"
            class="row-thumb-media"
            loading="lazy"
          />
          <div v-else class="thumb-placeholder">
            <el-icon v-if="item.status === 'failed'" :size="26" class="fail-icon"><CircleCloseFilled /></el-icon>
            <el-icon v-else-if="item.status === 'pending' || item.status === 'processing'" :size="26" class="spinner"><LoadingIcon /></el-icon>
            <el-icon v-else :size="26"><VideoPlay /></el-icon>
          </div>
        </div>

        <!-- 主信息：提示词 + 类型/模式/模型/失败原因 -->
        <div class="row-main">
          <div class="row-prompt" :title="item.prompt">{{ item.prompt || '-' }}</div>
          <div class="row-meta">
            <span class="meta-chip">{{ item.type === 'image' ? t('history.image') : t('history.video') }}</span>
            <span v-if="item.mode" class="meta-chip meta-mode">{{ t('params.mode.' + item.mode) || item.mode }}</span>
            <span v-if="item.model" class="meta-model">{{ item.model }}</span>
            <span
              v-if="item.status === 'failed' && rowErrorText(item)"
              class="row-error"
              :title="rowErrorText(item)">
              {{ rowErrorText(item) }}
            </span>
          </div>
        </div>

        <!-- 右侧：状态 / 积分 / 时间 / 行内操作 -->
        <div class="row-side">
          <span class="status-chip" :class="'st-' + item.status">
            <el-icon v-if="item.status === 'pending' || item.status === 'processing'" class="spinner"><LoadingIcon /></el-icon>
            {{ statusText(item.status) }}
          </span>
          <span class="row-credits" :title="t('history.creditsConsumedLabel')">{{ item.credits_consumed ?? 0 }}</span>
          <span class="row-time">{{ formatTime(item.created_at, { emptyText: '-' }) }}</span>
        </div>
        <div v-if="!editMode" class="row-actions" @click.stop>
          <!-- 复制提示词 -->
          <div
            v-if="item.prompt"
            class="row-action-btn"
            @click="copyPrompt(item)"
            :title="t('history.copyPrompt')">
            <el-icon size="15"><CopyDocument /></el-icon>
          </div>
          <!-- 查看资产：成功生成已自动入库，跳转资产库 -->
          <div
            v-if="item.asset_id"
            class="row-action-btn"
            @click="router.push('/assets')"
            :title="t('history.viewAsset')">
            <el-icon size="15"><Collection /></el-icon>
          </div>
          <!-- 存为资产：无资产行的成功记录补存兜底（后端按生成记录幂等去重） -->
          <div
            v-else-if="item.status === 'success'"
            class="row-action-btn"
            @click="openSaveAsAsset(item)"
            :title="t('history.saveAsAsset')">
            <el-icon size="15"><Collection /></el-icon>
          </div>
          <!-- 后期处理-调色：仅成功视频 -->
          <div
            v-if="item.type === 'video' && item.status === 'success'"
            class="row-action-btn"
            @click="openPostProcess(item, 'color_grade')"
            :title="t('history.postProcess.colorGrade')">
            <el-icon size="15"><MagicStick /></el-icon>
          </div>
          <!-- 后期处理-剪辑：仅成功视频 -->
          <div
            v-if="item.type === 'video' && item.status === 'success'"
            class="row-action-btn"
            @click="openPostProcess(item, 'video_edit')"
            :title="t('history.postProcess.videoEdit')">
            <el-icon size="15"><Scissor /></el-icon>
          </div>
          <!-- 删除 -->
          <div
            class="row-action-btn row-action-delete"
            @click="quickDelete(item)"
            :title="t('history.delete')">
            <el-icon size="15"><Delete /></el-icon>
          </div>
        </div>
      </div>
    </div>

    <!-- 分页 -->
    <div v-if="list.length > 0" class="pagination-wrap">
      <el-pagination
        v-model:current-page="page"
        v-model:page-size="pageSize"
        :page-sizes="[20, 50, 100]"
        :total="totalCount"
        layout="total, sizes, prev, pager, next"
        background
        @size-change="handleSizeChange"
        @current-change="handlePageChange"
      />
    </div>

    <!-- 任务详情弹窗 -->
    <el-dialog
      v-model="detailVisible"
      :title="detailItem ? (detailItem.type === 'image' ? t('history.imageDetail') : t('history.videoDetail')) : t('history.detail')"
      width="70%"
      top="5vh"
      destroy-on-close>
      <div v-if="detailItem" class="detail-content">
        <div class="detail-media">
          <ImageWithWatermark
            v-if="detailItem.type === 'image' && detailItem.result_url"
            :src="detailItem.result_url"
            :alt="t('history.imageDetailAlt')"
            :img-class="'detail-image'"
            fit="contain"
            style="cursor: zoom-in"
            @load="onDetailImageLoad"
            @click="openImageViewer(detailItem)"
          />
          <div v-else-if="detailItem.type === 'video' && detailItem.result_url" class="detail-video-wrap">
            <video
              v-if="!detailVideoFailed"
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
            <!-- 视频加载失败占位：上游 Provider URL 过期（如 Seedance 404），优雅降级避免破图 -->
            <div v-else class="video-failed-placeholder">
              <el-icon :size="64"><VideoCamera /></el-icon>
              <span>{{ t('common.resourceExpired') }}</span>
            </div>
            <div v-if="detailVideoLoading" class="detail-video-status">
              <el-icon :size="24" class="spinner"><LoadingIcon /></el-icon>
              <span>{{ t('history.videoLoading') }}</span>
            </div>
          </div>
          <!-- 无结果（失败/进行中）占位 -->
          <div v-else class="video-failed-placeholder">
            <el-icon :size="48" :class="{ 'fail-icon': detailItem.status === 'failed' }"><CircleCloseFilled /></el-icon>
            <span>{{ detailItem.status === 'failed' ? rowErrorText(detailItem) || t('taskStatus.failed') : t('taskStatus.processing') }}</span>
          </div>
        </div>
        <div class="detail-info">
          <div class="info-row"><span class="label">{{ t('history.promptLabel') }}：</span><span>{{ detailItem.prompt }}</span></div>
          <div class="info-row"><span class="label">{{ t('history.typeLabel') }}：</span><span>{{ detailItem.type === 'image' ? t('history.image') : t('history.video') }}</span></div>
          <div class="info-row" v-if="detailItem.model"><span class="label">{{ t('history.modelLabel') }}：</span><span>{{ detailItem.model }}</span></div>
          <!-- 图片实际尺寸（通过浏览器 naturalWidth/naturalHeight 读取，无需 EXIF） -->
          <div class="info-row" v-if="detailItem.type === 'image' && detailImageNatural">
            <span class="label">{{ t('history.actualSizeLabel') }}：</span>
            <span class="size-value">
              {{ detailImageNatural.w }}×{{ detailImageNatural.h }}
              <span class="size-mp" v-if="detailActualPixels">({{ formatPixels(detailActualPixels) }})</span>
            </span>
          </div>
          <!-- 请求尺寸（从 params.size 提取）+ 清晰度等级 -->
          <div class="info-row" v-if="detailItem.type === 'image' && detailRequestSize">
            <span class="label">{{ t('history.requestSizeLabel') }}：</span>
            <span class="size-value">
              {{ detailRequestSize }}
              <span class="size-tier" v-if="detailRequestTier" :style="{ color: IMAGE_TIER_CONFIG[detailRequestTier].color }">
                · {{ IMAGE_TIER_CONFIG[detailRequestTier].label }}
              </span>
              <span class="size-mismatch" v-if="detailSizeMismatch">
                · {{ t('history.sizeMismatchHint') }}
              </span>
            </span>
          </div>
          <!-- 视频实际分辨率（通过 <video> loadedmetadata 读取 videoWidth/videoHeight） -->
          <div class="info-row" v-if="detailItem.type === 'video' && detailVideoNatural">
            <span class="label">{{ t('history.actualSizeLabel') }}：</span>
            <span class="size-value">
              {{ detailVideoNatural.w }}×{{ detailVideoNatural.h }}
              <span class="size-mp" v-if="detailVideoActualPixels">({{ formatPixels(detailVideoActualPixels) }})</span>
            </span>
          </div>
          <!-- 视频请求参数：宽高比 + 时长 + 帧率 -->
          <div class="info-row" v-if="detailItem.type === 'video' && (detailRequestAspectRatio || detailRequestSeconds || detailRequestFrameRate)">
            <span class="label">{{ t('history.requestVideoParamsLabel') }}：</span>
            <span class="size-value">
              <template v-if="detailRequestAspectRatio">
                {{ detailRequestAspectRatio }}
                <span class="size-mismatch" v-if="detailVideoRatioMismatch">
                  · {{ t('history.sizeMismatchHint') }}
                </span>
              </template>
              <template v-if="detailRequestSeconds">
                <span v-if="detailRequestAspectRatio"> · </span>
                {{ detailRequestSeconds }}s
              </template>
              <template v-if="detailRequestFrameRate">
                <span v-if="detailRequestAspectRatio || detailRequestSeconds"> · </span>
                {{ detailRequestFrameRate }} FPS
              </template>
            </span>
          </div>
          <div class="info-row" v-if="detailItem.mode"><span class="label">{{ t('history.modeLabel') }}：</span><span class="mode-text">{{ t('params.mode.' + detailItem.mode) || detailItem.mode }}</span></div>
          <div class="info-row">
            <span class="label">{{ t('history.statusLabel') }}：</span>
            <span class="status-chip" :class="'st-' + detailItem.status">{{ statusText(detailItem.status) }}</span>
          </div>
          <!-- 失败归因（任务视图独有：错误类目 + 原始文案） -->
          <div class="info-row" v-if="detailItem.status === 'failed' && rowErrorText(detailItem)">
            <span class="label">{{ t('history.errorLabel') }}：</span>
            <span class="error-text">{{ rowErrorText(detailItem) }}</span>
          </div>
          <div class="info-row"><span class="label">{{ t('history.creditsConsumedLabel') }}：</span><span class="credits-value">{{ detailItem.credits_consumed ?? 0 }}</span></div>
          <div class="info-row"><span class="label">{{ t('history.createdAtLabel') }}：</span><span>{{ detailItem.created_at }}</span></div>
          <div class="info-row url-row" v-if="detailItem.result_url">
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

    <!-- 存为资产弹窗：把独立生成记录保存进资产库（自动归档失败的补存兜底） -->
    <el-dialog
      v-model="saveAsAssetVisible"
      :title="t('history.saveAsAssetTitle')"
      width="460px"
      @closed="resetSaveAsAssetForm">
      <el-form :model="saveAsAssetForm" label-width="80px">
        <el-form-item :label="t('assets.fields.name')" required>
          <el-input
            v-model="saveAsAssetForm.name"
            :placeholder="t('history.saveAsAssetNamePlaceholder')"
            maxlength="200"
            show-word-limit />
        </el-form-item>
        <el-form-item :label="t('assets.fields.type')" required>
          <el-select v-model="saveAsAssetForm.type" :placeholder="t('assets.type.all')">
            <el-option :label="t('assets.type.character')" value="character" />
            <el-option :label="t('assets.type.prop')" value="prop" />
            <el-option :label="t('assets.type.scene')" value="scene" />
            <el-option :label="t('assets.type.brand')" value="brand" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="saveAsAssetVisible = false">{{ t('common.cancel') }}</el-button>
        <el-button type="primary" :loading="savingAsAsset" @click="confirmSaveAsAsset">
          {{ t('history.saveAsAssetConfirm') }}
        </el-button>
      </template>
    </el-dialog>
    <ImageViewer
      v-model:visible="viewerVisible"
      :url="viewerUrl"
      :download-url="viewerDownloadUrl"
    />

    <!-- 后期处理弹窗（调色/剪辑）：对单个历史视频做二次后期处理 -->
    <PostProcessDialog
      v-model:visible="postProcessVisible"
      :generation-id="postProcessGenId"
      :video-url="postProcessVideoUrl"
      @success="handlePostProcessSuccess"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, watch, reactive } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Refresh, Loading, Document, Delete, VideoPlay, CircleCloseFilled, VideoCamera, Edit, Close, CopyDocument, MagicStick, Scissor, Collection } from '@element-plus/icons-vue'
import ImageViewer from '@/components/ImageViewer.vue'
import { getHistoryList, deleteHistoryRecord, batchDeleteHistory } from '@/api/history'
import { saveAssetFromGeneration } from '@/api/pipeline'
import { useDownload } from '@/composables/useDownload'
import { useCopyText } from '@/composables/useCopyText'
import { fetchBlobAsUrl } from '@/lib/blob'
import { formatTime } from '@/lib/format'
import { useTaskQueueStore } from '@/stores/taskQueue'
import { useI18n } from '@/i18n'
import { formatPixels, getTierBySize, IMAGE_TIER_CONFIG } from '@/config/model-params'
import type { GenerationRecord } from '@/types'
import ImageWithWatermark from '@/components/ImageWithWatermark.vue'
import PostProcessDialog from '@/components/PostProcessDialog.vue'

const { t } = useI18n()
const { copyText } = useCopyText()
const route = useRoute()
const router = useRouter()

// ---------- 从积分明细跳转过来时，通过 task_id 自动定位并打开详情 ----------
const pendingTaskId = ref<string>('')

// ---------- 图片查看器：详情图片点击后弹出，支持缩放/平移/旋转/下载 ----------
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

// 监听全局任务队列的刷新信号，实现生成按钮点击后自动刷新任务列表
const queue = useTaskQueueStore()

// 通用下载组合式函数（携带 JWT，避免 <a> 标签不带 token 导致鉴权失败）
const { downloadViaProxy } = useDownload()

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
const pageSize = ref(20)
const filterType = ref('all')
// 状态筛选（任务视图）：'' / success / failed / pending
const filterStatus = ref('')

const detailVisible = ref(false)
const deleteVisible = ref(false)
const detailItem = ref<GenerationRecord | null>(null)
const detailVideoEl = ref<HTMLVideoElement | null>(null)
const detailPoster = ref('')
const detailVideoLoading = ref(false)
const detailVideoFailed = ref(false)
// 后期处理弹窗状态（调色/剪辑）
const postProcessVisible = ref(false)
const postProcessGenId = ref<number | null>(null)
const postProcessVideoUrl = ref('')
// 图片实际尺寸（通过 <img> @load 读取 naturalWidth/naturalHeight）
const detailImageNatural = ref<{ w: number; h: number } | null>(null)
// 视频实际尺寸（通过 <video> loadedmetadata 读取 videoWidth/videoHeight）
const detailVideoNatural = ref<{ w: number; h: number } | null>(null)

const videoThumbnails = reactive<Record<string, string>>({})
const thumbnailLoading = reactive<Record<string, boolean>>({})
const thumbnailFailed = reactive<Record<string, boolean>>({})

const editMode = ref(false)
const selectedIds = ref<number[]>([])
const batchDeleteVisible = ref(false)
const batchDeleting = ref(false)

// ---------- 存为资产：把独立生成记录手动归档进资产库（兜底） ----------
const saveAsAssetVisible = ref(false)
const savingAsAsset = ref(false)
const saveAssetTarget = ref<GenerationRecord | null>(null)
const saveAsAssetForm = reactive({
  name: '',
  type: 'character' as string,
})

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

/** 任务状态文案（库内状态：success / failed / pending / cancelled） */
function statusText(status: string | undefined): string {
  switch (status) {
    case 'success': return t('taskStatus.done')
    case 'failed': return t('taskStatus.failed')
    case 'pending':
    case 'processing': return t('taskStatus.processing')
    case 'cancelled': return t('taskStatus.cancelled')
    default: return status || '-'
  }
}

/** 失败归因文案：原始错误信息优先，缺省回落错误类目 */
function rowErrorText(item: GenerationRecord): string {
  return (item.error_message || item.error_category || '').trim()
}

/**
 * 获取视频播放地址
 * 直接使用 Agnes CDN 的 result_url，因为 CDN 本身就是公开可访问的
 * 不走后端代理流（代理流需要鉴权，而 <video> 标签无法携带 JWT）
 */
function getVideoStreamUrl(item: GenerationRecord) {
  if (item.type !== 'video' || !item.result_url) return ''
  return item.result_url
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
      // 任务视图统一展示全部来源（后端 source 缺省为 independent，须显式传 all）
      source: 'all',
      status: filterStatus.value || undefined,
      page: page.value,
      page_size: pageSize.value
    })
    list.value = data.items || []
    totalCount.value = data.total || list.value.length
    imageCount.value = data.total_image_count ?? 0
    videoCount.value = data.total_video_count ?? 0
    list.value.filter(i => i.type === 'video' && i.result_url).forEach(item => {
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
  detailImageNatural.value = null  // 重置图片实际尺寸，等 img load 后回填
  detailVideoNatural.value = null  // 重置视频实际尺寸，等 loadedmetadata 后回填
  detailVideoLoading.value = item.type === 'video' && !!item.result_url
  detailVideoFailed.value = false
  detailVisible.value = true
}

/**
 * 图片加载完成回调：读取真实像素尺寸
 * 不依赖 EXIF，直接用浏览器解码后的 naturalWidth/naturalHeight
 */
function onDetailImageLoad(e: Event) {
  const img = e.target as HTMLImageElement
  if (img.naturalWidth && img.naturalHeight) {
    detailImageNatural.value = { w: img.naturalWidth, h: img.naturalHeight }
  }
}

// 详情图片的请求尺寸（从 params.size 提取，如 "1024x1024"）
const detailRequestSize = computed(() => {
  const p = detailItem.value?.params as Record<string, unknown> | null
  const s = p?.size
  return typeof s === 'string' ? s : ''
})

// 详情图片请求尺寸对应的清晰度等级
const detailRequestTier = computed(() => {
  if (!detailRequestSize.value) return null
  return getTierBySize(detailRequestSize.value) || null
})

// 详情图片实际像素数
const detailActualPixels = computed(() => {
  const n = detailImageNatural.value
  if (!n) return 0
  return n.w * n.h
})

// 实际尺寸与请求尺寸是否一致（不一致说明被 Agnes 降级）
const detailSizeMismatch = computed(() => {
  const n = detailImageNatural.value
  const req = detailRequestSize.value
  if (!n || !req) return false
  const m = req.match(/^(\d+)x(\d+)$/i)
  if (!m) return false
  return parseInt(m[1], 10) !== n.w || parseInt(m[2], 10) !== n.h
})

// ---------- 视频实际分辨率相关 ----------
// 视频请求参数：宽高比（如 "16:9"）
const detailRequestAspectRatio = computed(() => {
  const p = detailItem.value?.params as Record<string, unknown> | null
  const r = p?.aspect_ratio
  return typeof r === 'string' ? r : ''
})

// 视频请求参数：时长（秒）
const detailRequestSeconds = computed(() => {
  const p = detailItem.value?.params as Record<string, unknown> | null
  const s = p?.seconds ?? p?.duration
  return typeof s === 'number' ? s : (typeof s === 'string' ? Number(s) || 0 : 0)
})

// 视频请求参数：帧率（FPS）
const detailRequestFrameRate = computed(() => {
  const p = detailItem.value?.params as Record<string, unknown> | null
  const fps = p?.frame_rate ?? p?.fps
  return typeof fps === 'number' ? fps : (typeof fps === 'string' ? Number(fps) || 0 : 0)
})

// 视频实际像素数
const detailVideoActualPixels = computed(() => {
  const n = detailVideoNatural.value
  if (!n) return 0
  return n.w * n.h
})

// 视频实际宽高比是否匹配请求（如请求 16:9，实际 1920x1080 → 匹配）
const detailVideoRatioMismatch = computed(() => {
  const n = detailVideoNatural.value
  const req = detailRequestAspectRatio.value
  if (!n || !req) return false
  const m = req.match(/^(\d+):(\d+)$/)
  if (!m) return false
  const rw = parseInt(m[1], 10)
  const rh = parseInt(m[2], 10)
  // 用交叉乘法比较比例，允许微小误差
  return Math.abs(n.w * rh - n.h * rw) > 1
})

function toggleEditMode() {
  editMode.value = !editMode.value
  if (!editMode.value) {
    selectedIds.value = []
  }
}

function handleRowClick(item: GenerationRecord) {
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

function toggleSelectAll(val: boolean | string | number) {
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

// ---------- 存为资产：把独立生成记录手动归档进资产库（自动归档失败时的兜底） ----------

/** 打开「存为资产」弹窗（仅无资产行的成功记录可手动归档） */
function openSaveAsAsset(item: GenerationRecord) {
  saveAssetTarget.value = item
  saveAsAssetForm.name = (item.prompt || '').trim().slice(0, 50) || `生成记录 ${item.id}`
  saveAsAssetForm.type = 'character'
  saveAsAssetVisible.value = true
}

/** 关闭弹窗时重置表单 */
function resetSaveAsAssetForm() {
  saveAssetTarget.value = null
  saveAsAssetForm.name = ''
  saveAsAssetForm.type = 'character'
}

/** 确认保存为资产 */
async function confirmSaveAsAsset() {
  const target = saveAssetTarget.value
  if (!target) return
  if (!saveAsAssetForm.name.trim()) {
    ElMessage.warning(t('history.saveAsAssetNamePlaceholder'))
    return
  }
  savingAsAsset.value = true
  try {
    await saveAssetFromGeneration({
      generation_id: target.id,
      type: saveAsAssetForm.type,
      name: saveAsAssetForm.name.trim(),
      visual_description: target.prompt || undefined,
    })
    ElMessage.success(t('history.saveAsAssetSuccess'))
    saveAsAssetVisible.value = false
  } catch (e) {
    // 错误已在拦截器弹出
  } finally {
    savingAsAsset.value = false
  }
}

async function copyLink(url: string) {
  if (!url) {
    ElMessage.warning(t('history.noValidLink'))
    return
  }
  const ok = await copyText(url, t('history.linkCopied'))
  if (!ok) ElMessage.error(t('history.copyLinkFailed'))
}

/** 行内快捷复制提示词：复用通用剪贴板复制模块 */
async function copyPrompt(item: GenerationRecord) {
  if (!item.prompt) return
  const ok = await copyText(item.prompt, t('history.promptCopied'))
  if (!ok) ElMessage.error(t('history.copyLinkFailed'))
}

/**
 * 打开后期处理弹窗（调色/剪辑）
 * 由成功视频行上的 MagicStick/Scissor 按钮触发
 */
function openPostProcess(item: GenerationRecord, _operation: 'color_grade' | 'video_edit') {
  if (!item?.id || item.type !== 'video') return
  postProcessGenId.value = item.id
  // result_url 可能是相对路径（/api/...），PostProcessDialog 内部用 HTML5 video 加载时长
  // 需要 baseURL 拼接才能正确加载
  const baseURL = import.meta.env.VITE_API_BASE_URL || ''
  postProcessVideoUrl.value = item.result_url?.startsWith('http')
    ? item.result_url
    : `${baseURL}${item.result_url}`
  postProcessVisible.value = true
}

/**
 * 后期处理成功回调：刷新任务列表，提示用户新记录已生成
 */
function handlePostProcessSuccess(result: { result_url: string; new_generation_id: number; operation: string }) {
  // 刷新列表，让新记录显示出来
  loadList()
  ElMessage.success(t('history.postProcess.processDone', { id: result.new_generation_id }))
}

async function downloadDetail() {
  if (!detailItem.value?.result_url) {
    ElMessage.warning(t('history.noValidResource'))
    return
  }
  const recordId = detailItem.value.id
  const type = detailItem.value.type
  try {
    // 通过后端代理下载（使用 record_id 端点），携带 JWT 强制浏览器保存文件
    const baseURL = import.meta.env.VITE_API_BASE_URL || ''
    const proxyUrl = `${baseURL}/api/history/${recordId}/download`
    const defaultName = `agnes-${type}-${recordId}.${type === 'video' ? 'mp4' : 'png'}`
    await downloadViaProxy(proxyUrl, defaultName)
    ElMessage.success(t('history.downloadStarted'))
  } catch (err: any) {
    console.warn('[History] 下载失败：', err)
    ElMessage.error(err?.message || t('preview.videoCorsWarning'))
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
  // 顺便记录视频实际分辨率（videoWidth/videoHeight 在 loadedmetadata 后可用）
  if (!detailVideoNatural.value && el.videoWidth && el.videoHeight) {
    detailVideoNatural.value = { w: el.videoWidth, h: el.videoHeight }
  }
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

/** 行内快捷删除 —— 复用详情删除确认逻辑 */
function quickDelete(item: GenerationRecord) {
  if (!item?.id) return
  detailItem.value = item
  confirmDelete()
}

// 【任务自动刷新】每当有新任务完成/失败/取消时，自动刷新任务列表
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
 * 释放所有视频缩略图相关的 blob URL，避免内存泄漏
 */
function clearVideoBlobUrls() {
  Object.values(videoThumbnails).forEach(url => {
    if (url && url.startsWith('blob:')) URL.revokeObjectURL(url)
  })
}

// 【用户隔离】用户登录/登出后自动刷新任务列表，确保只看自己的数据
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

// 用户登录/退出事件处理器（稳定引用，用于 addEventListener/removeEventListener）
const handleLogin = (_e: Event) => handleUserSwitch()
const handleLogout = (_e: Event) => handleUserSwitch()

onMounted(() => {
  // 读取 URL 查询参数 task_id（从积分明细跳转过来时携带）
  const qTaskId = route.query.task_id
  if (typeof qTaskId === 'string' && qTaskId) {
    pendingTaskId.value = qTaskId
  }
  loadList()
  if (typeof window !== 'undefined') {
    window.addEventListener('agnes:user-login', handleLogin)
    window.addEventListener('agnes:user-logout', handleLogout)
  }
})

onBeforeUnmount(() => {
  clearVideoBlobUrls()
  if (typeof window !== 'undefined') {
    window.removeEventListener('agnes:user-login', handleLogin)
    window.removeEventListener('agnes:user-logout', handleLogout)
  }
})
</script>

<style scoped>
.history-view { color: var(--agnes-text-primary); }

.page-title {
  font-size: 24px;
  font-weight: 600;
  margin: 0 0 8px;
  color: var(--agnes-text-primary);
  display: flex;
  align-items: center;
  gap: 8px;
}
.page-desc {
  margin: 0 0 16px;
  font-size: 13px;
  color: var(--agnes-text-muted);
}

.filter-wrap {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
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

/* ---------- 任务行列表 ---------- */
.task-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.task-row {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 10px 14px;
  background: var(--agnes-bg-elevated);
  border: 1px solid var(--agnes-primary-border-faint);
  border-radius: 12px;
  cursor: pointer;
  transition: all 0.2s ease;
  position: relative;
}
.task-row:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 24px var(--agnes-brand-glow);
  border-color: var(--agnes-primary-border);
}
.task-row.is-selected {
  border-color: var(--agnes-error);
  box-shadow: 0 0 0 2px var(--agnes-error-border), 0 8px 24px var(--agnes-primary-border-faint);
}
.row-checkbox {
  padding: 4px 6px;
  background: var(--agnes-bg-elevated);
  border-radius: 8px;
  border: 1px solid var(--agnes-primary-border-faint);
  cursor: pointer;
  flex-shrink: 0;
}

/* 缩略图：固定 4:3 小图 */
.row-thumb {
  width: 96px;
  height: 72px;
  flex-shrink: 0;
  border-radius: 8px;
  overflow: hidden;
  background: var(--agnes-bg-base);
  position: relative;
}
.row-thumb img,
.row-thumb-media {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.thumb-placeholder {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--agnes-text-faint);
}
.fail-icon { color: var(--agnes-error); }

/* 主信息列 */
.row-main {
  flex: 1;
  min-width: 0;
}
.row-prompt {
  font-size: 13px;
  color: var(--agnes-text-primary);
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.row-meta {
  margin-top: 6px;
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}
.meta-chip {
  flex-shrink: 0;
  padding: 1px 8px;
  border-radius: 10px;
  font-size: 11px;
  font-weight: 600;
  color: #8bb4ff;
  border: 1px solid rgba(139, 180, 255, 0.5);
  background: rgba(10, 15, 30, 0.35);
}
.meta-chip.meta-mode {
  color: #ffd98b;
  border-color: rgba(255, 217, 139, 0.5);
}
.meta-model {
  font-size: 12px;
  color: var(--agnes-text-faint);
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.row-error {
  font-size: 12px;
  color: var(--agnes-error);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  min-width: 0;
}

/* 右侧信息列 */
.row-side {
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 4px;
  width: 88px;
}
/* 状态徽标：success 绿 / failed 红 / pending 蓝 / cancelled 灰 */
.status-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 10px;
  border-radius: 10px;
  font-size: 11px;
  font-weight: 600;
}
.status-chip .el-icon { font-size: 12px; }
.status-chip.st-success {
  color: var(--agnes-success, #67c23a);
  background: rgba(103, 194, 58, 0.12);
  border: 1px solid rgba(103, 194, 58, 0.4);
}
.status-chip.st-failed {
  color: var(--agnes-error);
  background: var(--agnes-error-bg);
  border: 1px solid var(--agnes-error-border);
}
.status-chip.st-pending,
.status-chip.st-processing {
  color: var(--agnes-primary);
  background: var(--agnes-info-bg);
  border: 1px solid var(--agnes-primary-border);
}
.status-chip.st-cancelled {
  color: var(--agnes-text-muted);
  background: var(--agnes-bg-inset);
  border: 1px solid var(--agnes-primary-border-faint);
}
.row-credits {
  font-size: 12px;
  color: var(--agnes-credits-value);
  font-weight: 600;
}
.row-time {
  font-size: 12px;
  color: var(--agnes-text-faint);
  white-space: nowrap;
}

/* 行内快捷操作（hover 展示，叠在行右侧） */
.row-actions {
  position: absolute;
  right: 12px;
  top: 50%;
  transform: translateY(-50%);
  z-index: 10;
  display: flex;
  gap: 6px;
  padding: 4px 6px;
  background: var(--agnes-bg-elevated);
  border: 1px solid var(--agnes-primary-border-faint);
  border-radius: 10px;
  box-shadow: 0 4px 16px var(--agnes-primary-border-faint);
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.2s ease;
}
.task-row:hover .row-actions {
  opacity: 1;
  pointer-events: auto;
}
.row-action-btn {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--agnes-bg-elevated);
  border-radius: 6px;
  border: 1px solid var(--agnes-primary-border-faint);
  color: var(--agnes-primary-soft);
  cursor: pointer;
  transition: all 0.15s ease;
}
.row-action-btn:hover {
  background: var(--agnes-info-bg);
  border-color: var(--agnes-primary);
  color: #fff;
}
.row-action-btn.row-action-delete {
  color: var(--agnes-error);
  border-color: var(--agnes-error-border);
}
.row-action-btn.row-action-delete:hover {
  background: var(--agnes-error-bg);
  border-color: var(--agnes-error);
  color: #fff;
}
/* 行内操作浮层盖住右侧信息列时的过渡底色 */
.task-row:hover .row-side {
  opacity: 0.25;
}
.row-side {
  transition: opacity 0.2s ease;
}

.pagination-wrap {
  margin-top: 24px;
  text-align: center;
}

/* ---------- 任务详情弹窗 ---------- */
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
/* 图片尺寸信息 */
.size-value { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
.size-mp { color: var(--agnes-text-muted); margin-left: 4px; font-size: 12px; }
.size-tier { font-weight: 600; margin-left: 4px; }
.size-mismatch {
  color: var(--agnes-warning, #e6a23c);
  margin-left: 4px;
  font-size: 12px;
  font-weight: 500;
}
/* 详情页生成模式文字：用主题感知的 warning 色 */
.mode-text {
  color: var(--agnes-warning);
  font-weight: 600;
}
.error-text {
  color: var(--agnes-error);
  word-break: break-all;
}
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

/* 视频加载失败/无结果占位：居中展示图标 + 文案，避免破图 */
.video-failed-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  width: 100%;
  aspect-ratio: 16 / 9;
  background: var(--agnes-bg-base);
  color: var(--agnes-text-muted);
  border-radius: 10px;
}
.video-failed-placeholder span {
  font-size: 14px;
}

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

.spinner {
  display: inline-block;
  animation: spin 1.2s linear infinite;
  color: var(--agnes-primary);
}
</style>
