<!-- =====================================================
     资产库页面 AssetsView（子批次 2a 统一入口：单池）
     - 呈现方式与生成历史页同款：历史风格卡片网格 / 批量处理模式 / 点击查看详情窗口
     - 一个资产池：生成结果（自动入库）/ 上传素材 / 合成产物 / 归档记录
     - 筛选：媒体类型 / 来源 / 所属作品 / 分类 / 关键词（服务端分页）
     ===================================================== -->

<template>
  <div class="assets-view">
    <div class="page-head">
      <h2 class="page-title">{{ t('assets.title') }}</h2>
      <span class="page-total">{{ t('assets.total').replace('{n}', String(total)) }}</span>
    </div>

    <!-- 筛选条 + 批量处理入口 -->
    <div class="filter-bar">
      <el-radio-group v-model="filters.media_type" @change="reload">
        <el-radio-button value="">{{ t('assets.mediaType.all') }}</el-radio-button>
        <el-radio-button value="image">{{ t('assets.mediaType.image') }}</el-radio-button>
        <el-radio-button value="video">{{ t('assets.mediaType.video') }}</el-radio-button>
        <el-radio-button value="audio">{{ t('assets.mediaType.audio') }}</el-radio-button>
      </el-radio-group>
      <el-select v-model="filters.source" clearable :placeholder="t('assets.filter.source')" class="f-item" @change="reload">
        <el-option v-for="s in SOURCE_OPTIONS" :key="s.value" :label="t(s.labelKey)" :value="s.value" />
      </el-select>
      <el-select v-model="filters.work_id" clearable :placeholder="t('assets.filter.work')" class="f-item" @change="reload">
        <el-option v-for="w in works" :key="w.id" :label="w.title" :value="w.id" />
      </el-select>
      <el-select v-model="filters.type" clearable :placeholder="t('assets.filter.type')" class="f-item" @change="reload">
        <el-option v-for="(labelKey, tp) in TYPE_KEYS" :key="tp" :label="t(labelKey)" :value="tp" />
      </el-select>
      <el-input
        v-model="filters.keyword"
        :placeholder="t('assets.searchPlaceholder')"
        class="search-input"
        clearable
        @keyup.enter="reload"
        @clear="reload"
      >
        <template #prefix>
          <el-icon><Search /></el-icon>
        </template>
      </el-input>
      <div class="filter-actions">
        <el-button type="primary" :icon="Refresh" :loading="loading" @click="reload">
          {{ t('common.refresh') }}
        </el-button>
        <!-- 批量处理模式切换按钮（历史页同款） -->
        <el-button
          :type="editMode ? 'warning' : 'default'"
          :icon="editMode ? CloseIcon : EditIcon"
          @click="toggleEditMode">
          {{ editMode ? t('history.exitEdit') : t('history.batchManage') }}
        </el-button>
      </div>
    </div>

    <!-- 批量处理模式操作栏（全选 + 下载 / 批量公开 / 私有 / 删除） -->
    <div v-if="editMode && items.length > 0" class="edit-toolbar">
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
          type="success"
          :icon="Share"
          :disabled="selectedIds.length === 0"
          :loading="batchSettingPublic"
          @click="confirmBatchSetPublic">
          {{ t('plaza.batchSetPublic') }} ({{ selectedIds.length }})
        </el-button>
        <el-button
          type="info"
          :icon="Share"
          :disabled="selectedIds.length === 0"
          :loading="batchSettingPrivate"
          @click="confirmBatchSetPrivate">
          {{ t('plaza.batchSetPrivate') }} ({{ selectedIds.length }})
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

    <!-- 统一资产网格（历史卡片同款结构） -->
    <div v-loading="loading" class="assets-section">
      <el-empty v-if="!loading && items.length === 0" :description="t('assets.standaloneEmpty')" />
      <div v-else class="asset-grid">
        <div
          v-for="a in items"
          :key="a.id"
          class="asset-card"
          :class="{ 'is-selected': editMode && selectedIds.includes(a.id) }"
          @click="handleCardClick(a)">
          <!-- 批量模式下的选择框 -->
          <div v-if="editMode" class="card-checkbox" @click.stop="toggleSelect(a.id)">
            <el-checkbox :model-value="selectedIds.includes(a.id)" />
          </div>
          <div class="card-preview">
            <!-- 图片：水印图组件 -->
            <ImageWithWatermark
              v-if="a.media_type !== 'video' && a.media_type !== 'audio' && a.asset_url"
              :src="a.asset_url"
              :alt="a.name"
              loading="lazy"
              fit="cover"
              class="card-media"
            />
            <!-- 视频：原生 video（首帧即缩略图，悬停播放） -->
            <video
              v-else-if="a.media_type === 'video' && a.asset_url"
              :src="a.asset_url"
              class="card-media"
              muted
              playsinline
              preload="metadata"
              @mouseenter="playCardVideo($event)"
              @mouseleave="pauseCardVideo($event)"
            />
            <!-- 音频：占位图标 -->
            <div v-else-if="a.media_type === 'audio'" class="media-placeholder">
              <el-icon :size="40"><Headset /></el-icon>
            </div>
            <div v-else class="media-placeholder">
              <el-icon :size="40"><Picture /></el-icon>
            </div>

            <!-- 类型 / 分类 / 公开 / 屏蔽标签 -->
            <div class="type-badge" :class="a.media_type">
              {{ mediaLabel(a.media_type) }}
            </div>
            <div v-if="cardBadge(a)" class="mode-badge" :class="a.media_type === 'video' ? 'mode-video' : 'mode-image'">
              {{ cardBadge(a) }}
            </div>
            <div v-if="a.is_public && !editMode" class="public-badge">
              <el-icon size="10"><Share /></el-icon>
              {{ t('plaza.isPublic') }}
            </div>
            <div v-if="a.moderation_status === 'rejected' && !editMode" class="rejected-badge">
              <el-icon size="10"><Warning /></el-icon>
              {{ t('history.rejected') }}
            </div>

            <!-- 悬浮快捷操作按钮组（非批量模式下显示）：放大 / 用于生成 / 编辑 / 下载 / 分享 / 删除 -->
            <div v-if="!editMode" class="card-actions" @click.stop>
              <div
                v-if="a.media_type === 'image' && a.asset_url"
                class="card-action-btn"
                @click.stop="openImageViewer(a)"
                :title="t('imageViewer.title')">
                <el-icon size="16"><ZoomIn /></el-icon>
              </div>
              <div
                class="card-action-btn"
                @click.stop="useForGeneration(a)"
                :title="t('assets.useInGeneration')">
                <el-icon size="16"><MagicStick /></el-icon>
              </div>
              <div
                class="card-action-btn"
                @click.stop="openEdit(a)"
                :title="t('common.edit')">
                <el-icon size="16"><EditPen /></el-icon>
              </div>
              <div
                class="card-action-btn"
                @click.stop="downloadAsset(a)"
                :title="t('history.download')">
                <el-icon size="16"><Download /></el-icon>
              </div>
              <!-- 分享状态切换：私有时低调，公开时高亮；被屏蔽时禁用 -->
              <div
                class="card-action-btn card-action-share"
                :class="{ 'is-public': a.is_public, 'is-disabled': a.moderation_status === 'rejected' && !a.is_public }"
                @click.stop="handleCardShare(a)"
                :title="a.is_public ? t('plaza.isPublic') : t('assets.shareToPlaza')">
                <el-icon size="16"><Share /></el-icon>
              </div>
              <div
                class="card-action-btn card-action-delete"
                @click.stop="removeAsset(a)"
                :title="t('common.delete')">
                <el-icon size="16"><Delete /></el-icon>
              </div>
            </div>
          </div>

          <div class="card-meta">
            <div class="card-name" :title="a.name">{{ a.name }}</div>
            <div class="card-footer-row">
              <span class="card-id" @click.stop="copyRecordId(a.id)" :title="t('history.clickToCopyId')">
                <el-icon size="11"><Document /></el-icon>
                {{ t('history.idLabel') }}: {{ a.id }}
              </span>
              <span class="card-time">{{ formatTime(a.created_at) }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- 分页 -->
      <div v-if="total > 0" class="pagination-wrap">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :page-sizes="[12, 24, 48, 100]"
          :total="total"
          layout="total, sizes, prev, pager, next"
          background
          @size-change="reload"
          @current-change="load"
        />
      </div>
    </div>

    <!-- 详情查看窗口（点击卡片进入，历史详情同款布局） -->
    <el-dialog
      v-model="detailVisible"
      :title="detailTitle"
      width="70%"
      top="5vh"
      destroy-on-close>
      <div v-if="detailItem" class="detail-content">
        <div class="detail-media">
          <ImageWithWatermark
            v-if="detailItem.media_type !== 'video' && detailItem.media_type !== 'audio' && detailItem.asset_url"
            :src="detailItem.asset_url"
            :alt="detailItem.name"
            :img-class="'detail-image'"
            fit="contain"
            style="cursor: zoom-in"
            @load="onDetailImageLoad"
            @click="openImageViewer(detailItem)"
          />
          <div v-else-if="detailItem.media_type === 'video' && detailItem.asset_url" class="detail-video-wrap">
            <video
              v-if="!detailVideoFailed"
              :key="detailItem.id"
              :src="detailItem.asset_url"
              controls
              playsinline
              preload="metadata"
              class="detail-video"
              @loadedmetadata="onDetailVideoMeta"
              @error="detailVideoFailed = true"
            ></video>
            <!-- 视频加载失败占位：优雅降级避免黑屏 -->
            <div v-else class="video-failed-placeholder">
              <el-icon :size="64"><VideoCamera /></el-icon>
              <span>{{ t('common.resourceExpired') }}</span>
            </div>
          </div>
          <audio
            v-else-if="detailItem.media_type === 'audio' && detailItem.asset_url"
            :src="detailItem.asset_url"
            controls
            class="detail-audio"
          />
          <el-empty v-else :description="t('assets.noPreview')" />
        </div>
        <div class="detail-info">
          <div class="info-row"><span class="label">{{ t('assets.fields.name') }}：</span><span>{{ detailItem.name }}</span></div>
          <div class="info-row" v-if="detailDescription"><span class="label">{{ t('assets.description') }}：</span><span>{{ detailDescription }}</span></div>
          <div class="info-row"><span class="label">{{ t('history.typeLabel') }}：</span><span>{{ mediaLabel(detailItem.media_type) }}</span></div>
          <div class="info-row" v-if="detailItem.type"><span class="label">{{ t('assets.type.label') }}：</span><span class="mode-text">{{ typeLabel(detailItem.type) }}</span></div>
          <div class="info-row" v-if="detailItem.source"><span class="label">{{ t('assets.filter.source') }}：</span><span>{{ sourceLabel(detailItem.source) }}</span></div>
          <div class="info-row"><span class="label">{{ t('assets.filter.work') }}：</span><span>{{ workTitleOf(detailItem.work_id) || '-' }}</span></div>
          <!-- 媒体实际尺寸（图片 naturalWidth / 视频 videoWidth，浏览器解码后读取） -->
          <div class="info-row" v-if="detailNatural">
            <span class="label">{{ t('history.actualSizeLabel') }}：</span>
            <span class="size-value">
              {{ detailNatural.w }}×{{ detailNatural.h }}
              <span class="size-mp">({{ formatPixels(detailNatural.w * detailNatural.h) }})</span>
            </span>
          </div>
          <div class="info-row"><span class="label">{{ t('history.statusLabel') }}：</span><span>{{ detailStatusText }}</span></div>
          <div class="info-row"><span class="label">{{ t('history.createdAtLabel') }}：</span><span>{{ detailItem.created_at }}</span></div>
          <div class="info-row url-row" v-if="detailItem.asset_url">
            <span class="label">{{ t('history.linkLabel') }}：</span>
            <span class="url-value">{{ detailItem.asset_url }}</span>
            <el-button size="small" link type="primary" @click="copyLink(detailItem.asset_url)">{{ t('history.copyLink') }}</el-button>
            <el-button size="small" link type="primary" @click="downloadDetail">{{ t('history.download') }}</el-button>
            <el-button size="small" link type="primary" @click="openInNewTab">{{ t('history.openNewTab') }}</el-button>
          </div>
        </div>
      </div>
      <template #footer>
        <el-button @click="detailVisible = false">{{ t('common.close') }}</el-button>
        <el-button type="danger" :icon="DeleteIcon" @click="detailItem && removeAsset(detailItem)">{{ t('history.deleteRecord') }}</el-button>
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

    <!-- 图片查看器 -->
    <ImageViewer
      v-model:visible="viewerVisible"
      :url="viewerUrl"
    />

    <!-- 资产编辑弹窗 -->
    <AssetDetailModal
      v-model="modalVisible"
      :asset-id="currentAssetId"
      @saved="reload"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from '@/i18n'
import { ElMessage } from 'element-plus'
import { useConfirm } from '@/composables/useConfirm'
import {
  Search, Picture, Headset, Share, Download, Delete, MagicStick, EditPen,
  ZoomIn, Document, Warning, Refresh, Edit, Close, VideoCamera,
} from '@element-plus/icons-vue'
import { useAssetStore } from '@/stores/asset'
import AssetDetailModal from '@/components/pipeline/AssetDetailModal.vue'
import ImageWithWatermark from '@/components/ImageWithWatermark.vue'
import ImageViewer from '@/components/ImageViewer.vue'
import { listAssets, batchUpdateAssetShare, batchDeleteAssets, type UnifiedAsset } from '@/api/assets'
import { listWorks, type WorkItem } from '@/api/works'
import { updateAssetShare, deleteAsset } from '@/api/pipeline'
import { useDownload } from '@/composables/useDownload'
import { useCopyText } from '@/composables/useCopyText'
import { formatPixels } from '@/config/model-params'

const { t } = useI18n()
const { confirm } = useConfirm()
const { downloadViaProxy } = useDownload()
const { copyText } = useCopyText()
const assetStore = useAssetStore()
const router = useRouter()

const SOURCE_OPTIONS = [
  { value: 'generation', labelKey: 'assets.source.generation' },
  { value: 'upload', labelKey: 'assets.source.upload' },
  { value: 'compose', labelKey: 'assets.source.compose' },
  { value: 'archive', labelKey: 'assets.source.archive' },
]

// 图标别名：避免与本地方法/变量同名
const DeleteIcon = Delete
const CloseIcon = Close
const EditIcon = Edit

// ---------- 状态 ----------
const loading = ref(false)
const items = ref<UnifiedAsset[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(24)
const works = ref<WorkItem[]>([])
const filters = reactive<{ media_type: string; source: string | null; work_id: number | null; type: string | null; keyword: string }>({
  media_type: '',
  source: null,
  work_id: null,
  type: null,
  keyword: '',
})
const modalVisible = ref(false)
const currentAssetId = ref<number | null>(null)
const sharingIds = ref<Set<number>>(new Set())
const detailVisible = ref(false)
const detailItem = ref<UnifiedAsset | null>(null)
const viewerVisible = ref(false)
const viewerUrl = ref('')
// 媒体实际尺寸（<img> @load / <video> loadedmetadata 回填）
const detailImageNatural = ref<{ w: number; h: number } | null>(null)
const detailVideoNatural = ref<{ w: number; h: number } | null>(null)
const detailVideoFailed = ref(false)

// ---------- 批量处理模式（历史页同款） ----------
const editMode = ref(false)
const selectedIds = ref<number[]>([])
const batchDeleteVisible = ref(false)
const batchDeleting = ref(false)
const batchDownloading = ref(false)
const batchSettingPublic = ref(false)
const batchSettingPrivate = ref(false)

const isAllSelected = computed(() => {
  if (!items.value.length) return false
  return items.value.every((a) => selectedIds.value.includes(a.id))
})
const isIndeterminate = computed(() => {
  if (!items.value.length) return false
  const pageIds = items.value.map((a) => a.id)
  const picked = pageIds.filter((id) => selectedIds.value.includes(id))
  return picked.length > 0 && picked.length < pageIds.length
})

const TYPE_KEYS: Record<string, string> = {
  character: 'assets.type.character',
  prop: 'assets.type.prop',
  scene: 'assets.type.scene',
  brand: 'assets.type.brand',
  material: 'assets.type.material',
  clip: 'assets.type.clip',
  final: 'assets.type.final',
}

function typeLabel(type: string): string {
  const key = TYPE_KEYS[type]
  return key ? t(key) : type
}

// 实体分类：卡片徽标上有展示价值（区分角色/道具/场景/品牌库条目）
const ENTITY_TYPES = new Set(['character', 'prop', 'scene', 'brand'])

/**
 * 卡片分类徽标：实体分类（角色/道具/场景/品牌）优先；
 * 其次显示生成模式（文生图/图生视频…，来自来源生成记录）；
 * 行政分类（分镜图/视频片段/成片）与媒体类型徽标语义重复，不显示
 */
function cardBadge(a: UnifiedAsset): string {
  if (ENTITY_TYPES.has(a.type)) return typeLabel(a.type)
  return a.mode ? (t('params.mode.' + a.mode) || a.mode) : ''
}

function sourceLabel(value: string | null): string {
  const opt = SOURCE_OPTIONS.find((s) => s.value === value)
  return opt ? t(opt.labelKey) : (value || '-')
}

function mediaLabel(mediaType: string | null): string {
  const map: Record<string, string> = {
    image: t('assets.mediaType.image'),
    video: t('assets.mediaType.video'),
    audio: t('assets.mediaType.audio'),
  }
  return map[mediaType ?? ''] || t('assets.mediaType.all')
}

function workTitleOf(workId: number | null): string | null {
  if (workId == null) return null
  return works.value.find((w) => w.id === workId)?.title ?? null
}

function formatTime(value: string | null): string {
  return value ? value.replace('T', ' ').slice(0, 16) : '-'
}

// ---------- 详情弹窗派生信息 ----------
const detailTitle = computed(() => {
  if (!detailItem.value) return t('history.detail')
  if (detailItem.value.media_type === 'video') return t('history.videoDetail')
  if (detailItem.value.media_type === 'image') return t('history.imageDetail')
  return t('history.detail')
})

const detailDescription = computed(() => {
  const a = detailItem.value
  if (!a) return ''
  return a.description || a.visual_description || ''
})

const detailNatural = computed(() => detailImageNatural.value ?? detailVideoNatural.value)

const detailStatusText = computed(() => {
  const a = detailItem.value
  if (!a) return ''
  if (a.moderation_status === 'rejected') return t('assets.blocked')
  if (a.is_public) return a.moderation_status === 'pending' ? t('assets.moderating') : t('plaza.isPublic')
  return t('plaza.isPrivate')
})

// ---------- 数据加载 ----------
async function load(): Promise<void> {
  loading.value = true
  try {
    const data = await listAssets({
      media_type: filters.media_type || undefined,
      source: filters.source || undefined,
      work_id: filters.work_id ?? undefined,
      type: filters.type || undefined,
      keyword: filters.keyword.trim() || undefined,
      page: page.value,
      page_size: pageSize.value,
    })
    items.value = data.items
    total.value = data.total
  } catch (e: unknown) {
    const err = e as { message?: string }
    ElMessage.error(err.message || t('assets.loadFailed'))
  } finally {
    loading.value = false
  }
}

function reload(): void {
  page.value = 1
  void load()
}

async function loadWorks(): Promise<void> {
  try {
    works.value = (await listWorks()).items
  } catch (_e) { /* 筛选项加载失败不阻塞列表 */ }
}

let keywordTimer: ReturnType<typeof setTimeout> | null = null
watch(() => filters.keyword, () => {
  if (keywordTimer) clearTimeout(keywordTimer)
  keywordTimer = setTimeout(reload, 300)
})

// ---------- 卡片交互（历史同款） ----------
function handleCardClick(a: UnifiedAsset): void {
  if (editMode.value) {
    toggleSelect(a.id)
  } else {
    openDetail(a)
  }
}

/** 视频卡片悬停播放 / 离开复位 */
function playCardVideo(e: MouseEvent): void {
  (e.currentTarget as HTMLVideoElement)?.play().catch(() => {})
}

function pauseCardVideo(e: MouseEvent): void {
  const el = e.currentTarget as HTMLVideoElement
  if (el) {
    el.pause()
    try { el.currentTime = 0 } catch (_e) { /* ignore */ }
  }
}

function openDetail(a: UnifiedAsset): void {
  detailItem.value = a
  detailImageNatural.value = null
  detailVideoNatural.value = null
  detailVideoFailed.value = false
  detailVisible.value = true
}

function openImageViewer(a: UnifiedAsset): void {
  if (!a.asset_url) return
  viewerUrl.value = a.asset_url
  viewerVisible.value = true
}

/** 图片加载完成：读取真实像素尺寸 */
function onDetailImageLoad(e: Event): void {
  const img = e.target as HTMLImageElement
  if (img.naturalWidth && img.naturalHeight) {
    detailImageNatural.value = { w: img.naturalWidth, h: img.naturalHeight }
  }
}

/** 视频元数据加载完成：读取真实分辨率 */
function onDetailVideoMeta(e: Event): void {
  const el = e.target as HTMLVideoElement
  if (el.videoWidth && el.videoHeight) {
    detailVideoNatural.value = { w: el.videoWidth, h: el.videoHeight }
  }
}

async function toggleShare(a: UnifiedAsset, val: boolean): Promise<void> {
  sharingIds.value = new Set(sharingIds.value).add(a.id)
  try {
    const res = await updateAssetShare(a.id, val)
    a.is_public = res.is_public
    a.moderation_status = val ? 'pending' : a.moderation_status
    ElMessage.success(t(val ? 'assets.shareSuccess' : 'assets.unshareSuccess'))
  } catch (e: unknown) {
    const err = e as { message?: string }
    ElMessage.error(err.message || t('assets.shareFailed'))
  } finally {
    const next = new Set(sharingIds.value)
    next.delete(a.id)
    sharingIds.value = next
  }
}

/** 卡片分享切换：被管理员屏蔽的资产不允许再次公开 */
function handleCardShare(a: UnifiedAsset): void {
  if (a.moderation_status === 'rejected' && !a.is_public) {
    ElMessage.warning(t('assets.blockedTip'))
    return
  }
  void toggleShare(a, !a.is_public)
}

async function removeAsset(a: UnifiedAsset): Promise<void> {
  await confirm(t('assets.deleteConfirm'), t('common.confirm'))
  try {
    await deleteAsset(a.id)
    ElMessage.success(t('assets.deleteSuccess'))
    items.value = items.value.filter((x) => x.id !== a.id)
    total.value = Math.max(0, total.value - 1)
    selectedIds.value = selectedIds.value.filter((id) => id !== a.id)
    if (detailItem.value?.id === a.id) detailVisible.value = false
  } catch (e: unknown) {
    const err = e as { message?: string }
    ElMessage.error(err.message || t('assets.deleteFailed'))
  }
}

/** 详情弹窗下载：fetch 资产地址 → blob 触发保存 */
async function downloadDetail(): Promise<void> {
  if (!detailItem.value?.asset_url) return
  await downloadAsset(detailItem.value)
}

/** 下载：fetch 资产地址（/uploads 与公开对象存储均可匿名读）→ blob 触发保存 */
async function downloadAsset(a: UnifiedAsset): Promise<void> {
  if (!a.asset_url) return
  try {
    const resp = await fetch(a.asset_url)
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
    const blob = await resp.blob()
    const objUrl = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = objUrl
    link.download = a.name || `asset-${a.id}`
    link.click()
    URL.revokeObjectURL(objUrl)
    ElMessage.success(t('history.downloadStarted'))
  } catch (e: unknown) {
    ElMessage.error(t('assets.loadFailed'))
    // eslint-disable-next-line no-console
    console.warn('[assets] 下载失败:', e)
  }
}

function openEdit(a: UnifiedAsset): void {
  currentAssetId.value = a.id
  modalVisible.value = true
}

/** 「用于生成」：写入 pendingUse 并跳转生成页（video → 视频页，其余 → 生图页） */
function useForGeneration(a: UnifiedAsset): void {
  assetStore.setPendingUse(a as unknown as Parameters<typeof assetStore.setPendingUse>[0])
  router.push(a.media_type === 'video' ? '/videos' : '/images')
  ElMessage.success(t('assets.useForGenerationTip'))
}

// ---------- 批量处理（历史页同款交互） ----------
function toggleEditMode(): void {
  editMode.value = !editMode.value
  if (!editMode.value) {
    selectedIds.value = []
  }
}

function toggleSelect(id: number): void {
  const idx = selectedIds.value.indexOf(id)
  if (idx >= 0) {
    selectedIds.value.splice(idx, 1)
  } else {
    selectedIds.value.push(id)
  }
}

function toggleSelectAll(val: boolean | string | number): void {
  const pageIds = items.value.map((a) => a.id)
  if (val) {
    const set = new Set(selectedIds.value)
    pageIds.forEach((id) => set.add(id))
    selectedIds.value = Array.from(set)
  } else {
    const pageSet = new Set(pageIds)
    selectedIds.value = selectedIds.value.filter((id) => !pageSet.has(id))
  }
}

/** 批量下载选中项（单个直接下载，多个打包 zip） */
async function batchDownload(): Promise<void> {
  if (selectedIds.value.length === 0) {
    ElMessage.warning(t('history.pleaseSelectOne'))
    return
  }
  batchDownloading.value = true
  try {
    if (selectedIds.value.length === 1) {
      const a = items.value.find((x) => x.id === selectedIds.value[0])
      if (a) await downloadAsset(a)
    } else {
      const baseURL = import.meta.env.VITE_API_BASE_URL || ''
      const ids = selectedIds.value.join(',')
      await downloadViaProxy(`${baseURL}/api/assets/batch-download?ids=${ids}`, `agnes-assets-batch-${Date.now()}.zip`)
      ElMessage.success(t('history.downloadStarted'))
    }
  } catch (err: unknown) {
    const e = err as { message?: string }
    ElMessage.error(e.message || t('assets.loadFailed'))
  } finally {
    batchDownloading.value = false
  }
}

function confirmBatchDelete(): void {
  if (selectedIds.value.length === 0) {
    ElMessage.warning(t('history.pleaseSelectOne'))
    return
  }
  batchDeleteVisible.value = true
}

async function doBatchDelete(): Promise<void> {
  if (selectedIds.value.length === 0) return
  batchDeleting.value = true
  try {
    const res = await batchDeleteAssets(selectedIds.value)
    const deletedCount = res?.deleted_count ?? selectedIds.value.length
    ElMessage.success(t('history.batchDeleted').replace('{n}', String(deletedCount)))
    batchDeleteVisible.value = false
    selectedIds.value = []
    void load()
  } catch (e: unknown) {
    const err = e as { message?: string }
    ElMessage.error(err.message || t('assets.deleteFailed'))
  } finally {
    batchDeleting.value = false
  }
}

/** 批量设为公开：被屏蔽的资产跳过 */
async function confirmBatchSetPublic(): Promise<void> {
  if (selectedIds.value.length === 0) {
    ElMessage.warning(t('history.pleaseSelectOne'))
    return
  }
  const rejectedCount = items.value.filter(
    (a) => selectedIds.value.includes(a.id) && a.moderation_status === 'rejected'
  ).length
  const validIds = selectedIds.value.filter((id) => {
    return items.value.find((a) => a.id === id)?.moderation_status !== 'rejected'
  })
  if (validIds.length === 0) {
    ElMessage.warning(t('history.allSelectedRejected'))
    return
  }
  const text = rejectedCount > 0
    ? t('history.confirmBatchPublicWithRejected', { valid: validIds.length, rejected: rejectedCount })
    : t('plaza.confirmBatchPublic', { n: selectedIds.value.length })
  await confirm(text, t('plaza.batchSetPublic'))
  batchSettingPublic.value = true
  try {
    await batchUpdateAssetShare(validIds, true)
    ElMessage.success(t('plaza.batchSuccess'))
    selectedIds.value = []
    void load()
  } catch (e: unknown) {
    const err = e as { message?: string }
    ElMessage.error(err.message || t('assets.shareFailed'))
  } finally {
    batchSettingPublic.value = false
  }
}

/** 批量设为私有 */
async function confirmBatchSetPrivate(): Promise<void> {
  if (selectedIds.value.length === 0) {
    ElMessage.warning(t('history.pleaseSelectOne'))
    return
  }
  await confirm(t('plaza.confirmBatchPrivate', { n: selectedIds.value.length }), t('plaza.batchSetPrivate'))
  batchSettingPrivate.value = true
  try {
    await batchUpdateAssetShare(selectedIds.value, false)
    ElMessage.success(t('plaza.batchSuccess'))
    selectedIds.value = []
    void load()
  } catch (e: unknown) {
    const err = e as { message?: string }
    ElMessage.error(err.message || t('assets.shareFailed'))
  } finally {
    batchSettingPrivate.value = false
  }
}

/** 复制资产 ID 到剪贴板 */
async function copyRecordId(id: number): Promise<void> {
  const okCopy = await copyText(String(id), t('history.idCopied', { id }))
  if (!okCopy) ElMessage.info(`${t('history.idLabel')}: ${id}`)
}

async function copyLink(url: string): Promise<void> {
  const okCopy = await copyText(url, t('history.linkCopied'))
  if (!okCopy) ElMessage.error(t('history.copyLinkFailed'))
}

function openInNewTab(): void {
  if (!detailItem.value?.asset_url) return
  window.open(detailItem.value.asset_url, '_blank', 'noopener,noreferrer')
  ElMessage.success(t('history.openedInNewTab'))
}

// ---------- 生命周期 ----------
onMounted(() => {
  void load()
  void loadWorks()
})
</script>

<style scoped>
.assets-view {
  /* 宽度交给外层 app-main（max-width 1600 + padding），与历史页同款铺满，保证卡片密度 */
  color: var(--agnes-text-primary);
}

.page-head {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}

.page-title {
  font-size: 24px;
  font-weight: 600;
  margin: 0;
  color: var(--agnes-text-primary);
}

.page-total {
  font-size: 13px;
  color: var(--agnes-text-secondary);
}

.filter-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
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
  margin-left: auto;
}

.f-item {
  width: 150px;
}

.search-input {
  width: 220px;
}

/* 批量处理操作栏（历史同款） */
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
.edit-right {
  display: flex;
  gap: 10px;
}

/* 资产网格（历史卡片同款结构） */
.asset-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 18px;
}

.asset-card {
  background: var(--agnes-bg-elevated);
  border: 1px solid var(--agnes-primary-border-faint);
  border-radius: 12px;
  overflow: hidden;
  cursor: pointer;
  transition: all 0.2s ease;
  position: relative;
}

.asset-card:hover {
  transform: translateY(-4px);
  box-shadow: 0 8px 32px var(--agnes-brand-glow);
  border-color: var(--agnes-primary-border);
}

.asset-card.is-selected {
  border-color: var(--agnes-error);
  box-shadow: 0 0 0 2px var(--agnes-error-border), 0 8px 24px var(--agnes-primary-border-faint);
  transform: translateY(-2px);
}
.asset-card.is-selected:hover {
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

.card-preview {
  position: relative;
  width: 100%;
  aspect-ratio: 4/3;
  background: var(--agnes-bg-base);
  overflow: hidden;
}

.card-media {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.media-placeholder {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--agnes-text-muted);
}

/* 类型标签（图片/视频/音频）：半透明深色背景 + 浅色文字 */
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
.type-badge.audio { color: #8be9d0; border: 1px solid rgba(139, 233, 208, 0.5); }

/* 资产分类标签（角色/场景/分镜图 等）：紧随类型标签 */
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

/* 公开状态标签 */
.public-badge {
  position: absolute;
  top: 10px;
  right: 10px;
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 3px 8px;
  border-radius: 20px;
  font-size: 11px;
  font-weight: 600;
  color: #ffffff;
  background: var(--agnes-accent);
  border: 1px solid rgba(255, 255, 255, 0.25);
  backdrop-filter: blur(4px);
  z-index: 3;
}

.rejected-badge {
  position: absolute;
  top: 44px;
  right: 10px;
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 3px 8px;
  border-radius: 20px;
  font-size: 11px;
  font-weight: 600;
  color: #ffffff;
  background: #ef4444;
  border: 1px solid rgba(255, 255, 255, 0.25);
  backdrop-filter: blur(4px);
  z-index: 3;
}

/* 悬浮快捷操作按钮组（hover 展示，历史同款） */
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
.asset-card:hover .card-action-btn {
  opacity: 1;
  pointer-events: auto;
}
.card-action-btn:hover {
  background: var(--agnes-info-bg);
  border-color: var(--agnes-primary);
  color: #fff;
}
.card-action-btn.card-action-delete {
  color: var(--agnes-error);
  border-color: var(--agnes-error-border);
}
.card-action-btn.card-action-delete:hover {
  background: var(--agnes-error-bg);
  border-color: var(--agnes-error);
  color: #fff;
}
.card-action-btn.card-action-share {
  color: var(--agnes-text-muted);
  border-color: var(--agnes-primary-border-faint);
}
.card-action-btn.card-action-share.is-public {
  color: var(--agnes-accent);
  border-color: var(--agnes-accent);
  opacity: 1;
  pointer-events: auto;
}
.card-action-btn.card-action-share:hover {
  background: var(--agnes-info-bg);
  border-color: var(--agnes-accent);
  color: var(--agnes-accent);
}
.card-action-btn.card-action-share.is-disabled {
  opacity: 0.4;
  cursor: not-allowed;
  pointer-events: none;
}

.card-meta { padding: 12px 14px; }
.card-name {
  font-size: 13px;
  color: var(--agnes-text-primary);
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.card-footer-row {
  margin-top: 8px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
}
.card-id {
  font-size: 12px;
  color: var(--agnes-text-faint);
  display: flex;
  align-items: center;
  gap: 4px;
  cursor: pointer;
  transition: color 0.2s;
}
.card-id:hover {
  color: var(--agnes-text-secondary);
}
.card-time {
  font-size: 12px;
  color: var(--agnes-text-faint);
}

.batch-delete-count {
  color: var(--agnes-error);
  font-weight: 700;
}

.pagination-wrap {
  display: flex;
  justify-content: center;
  padding: 20px 0;
}

/* 详情查看窗口（历史详情同款布局） */
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
.detail-audio {
  width: 100%;
}
.detail-info {
  width: 100%;
  background: var(--agnes-bg-inset);
  padding: 16px;
  border-radius: 10px;
}
.info-row { padding: 6px 0; font-size: 13px; line-height: 1.6; color: var(--agnes-text-primary); }
.label { color: var(--agnes-text-muted); margin-right: 8px; font-weight: 500; }
.mode-text {
  color: var(--agnes-warning);
  font-weight: 600;
}
.size-value { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
.size-mp { color: var(--agnes-text-muted); margin-left: 4px; font-size: 12px; }
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
</style>
