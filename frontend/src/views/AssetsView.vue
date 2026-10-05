<!-- =====================================================
     资产库页面 AssetsView（子批次 2a 统一入口：单池）
     - 呈现方式复用生成历史页范式：卡片悬浮快捷钮 / 视频悬停播放 / 点击查看窗口 / 分页
     - 一个资产池：生成结果（自动入库）/ 上传素材 / 合成产物 / 归档记录
     - 筛选：媒体类型 / 来源 / 所属作品 / 关键词（服务端分页）
     ===================================================== -->

<template>
  <div class="assets-view">
    <div class="page-head">
      <h2 class="page-title">{{ t('assets.title') }}</h2>
      <span class="page-total">{{ t('assets.total').replace('{n}', String(total)) }}</span>
      <el-button
        v-if="userStore.isAdmin"
        :loading="backfilling"
        class="head-create"
        @click="runBackfill"
      >
        <el-icon><Refresh /></el-icon>
        {{ t('assets.backfill') }}
      </el-button>
      <el-button
        v-permission="'pipeline:save_asset'"
        type="primary"
        class="head-create"
        @click="openCreate"
      >
        <el-icon><Plus /></el-icon>
        {{ t('assets.createAsset') }}
      </el-button>
    </div>

    <!-- 筛选条 -->
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
    </div>

    <!-- 统一资产网格 -->
    <div v-loading="loading" class="assets-section">
      <el-empty v-if="!loading && items.length === 0" :description="t('assets.standaloneEmpty')" />
      <div v-else class="asset-grid">
        <div v-for="a in items" :key="a.id" class="asset-card">
          <div class="card-preview" @click="handleCardClick(a)">
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
              @click.stop="openDetail(a)"
            />
            <!-- 音频：占位图标 -->
            <div v-else-if="a.media_type === 'audio'" class="media-placeholder">
              <el-icon :size="40"><Headset /></el-icon>
            </div>
            <div v-else class="media-placeholder">
              <el-icon :size="40"><Picture /></el-icon>
            </div>

            <!-- 类型 / 来源 / 作品标签 -->
            <div class="type-badge" :class="a.media_type">
              {{ mediaLabel(a.media_type) }}
            </div>
            <div v-if="a.is_public" class="public-badge">
              <el-icon size="10"><Share /></el-icon>
              {{ t('plaza.isPublic') }}
            </div>

            <!-- 悬浮快捷钮：用于生成 / 编辑 / 下载 / 分享 / 删除 -->
            <div class="card-actions" @click.stop>
              <div class="card-action-btn" :title="t('assets.useInGeneration')" @click.stop="useForGeneration(a)">
                <el-icon size="16"><MagicStick /></el-icon>
              </div>
              <div class="card-action-btn" :title="t('common.edit')" @click.stop="openEdit(a)">
                <el-icon size="16"><EditPen /></el-icon>
              </div>
              <div class="card-action-btn" :title="t('history.download')" @click.stop="downloadAsset(a)">
                <el-icon size="16"><Download /></el-icon>
              </div>
              <el-switch
                :model-value="a.is_public"
                :loading="sharingIds.has(a.id)"
                :disabled="sharingIds.has(a.id)"
                size="small"
                @change="(v: boolean) => toggleShare(a, v)"
              />
              <div class="card-action-btn" :title="t('common.delete')" @click.stop="removeAsset(a)">
                <el-icon size="16"><Delete /></el-icon>
              </div>
            </div>
          </div>

          <div class="card-info">
            <span class="card-name" :title="a.name">{{ a.name }}</span>
            <span class="card-time">{{ formatTime(a.updated_at) }}</span>
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

    <!-- 详情查看窗口（点击卡片进入） -->
    <el-dialog
      v-model="detailVisible"
      :title="detailItem?.name || t('assets.title')"
      width="70%"
      top="5vh"
      destroy-on-close
    >
      <div v-if="detailItem" class="detail-content">
        <div class="detail-media">
          <ImageWithWatermark
            v-if="detailItem.media_type !== 'video' && detailItem.media_type !== 'audio' && detailItem.asset_url"
            :src="detailItem.asset_url"
            :alt="detailItem.name"
            :img-class="'detail-image'"
            fit="contain"
            style="cursor: zoom-in"
            @click="openImageViewer(detailItem)"
          />
          <video
            v-else-if="detailItem.media_type === 'video' && detailItem.asset_url"
            :src="detailItem.asset_url"
            controls
            playsinline
            preload="metadata"
            class="detail-video"
          />
          <audio
            v-else-if="detailItem.media_type === 'audio' && detailItem.asset_url"
            :src="detailItem.asset_url"
            controls
            class="detail-audio"
          />
          <el-empty v-else :description="t('assets.noPreview')" />
        </div>
        <div class="detail-meta">
          <div class="detail-row"><span class="detail-label">{{ t('assets.filter.source') }}</span><span>{{ sourceLabel(detailItem.source) }}</span></div>
          <div class="detail-row"><span class="detail-label">{{ t('assets.filter.work') }}</span><span>{{ workTitleOf(detailItem.work_id) || '-' }}</span></div>
          <div class="detail-row"><span class="detail-label">{{ t('assets.type.label') }}</span><span>{{ typeLabel(detailItem.type) }}</span></div>
          <div class="detail-row">
            <span class="detail-label">{{ t('common.delete') }}</span>
            <el-button size="small" type="danger" @click="removeAsset(detailItem); detailVisible = false">
              <el-icon><Delete /></el-icon>{{ t('common.delete') }}
            </el-button>
          </div>
        </div>
      </div>
    </el-dialog>

    <!-- 图片查看器 -->
    <ImageViewer
      v-model:visible="viewerVisible"
      :url="viewerUrl"
    />

    <!-- 资产创建/编辑弹窗 -->
    <AssetDetailModal
      v-model="modalVisible"
      :asset-id="currentAssetId"
      @saved="reload"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from '@/i18n'
import { ElMessage, ElImage } from 'element-plus'
import { useConfirm } from '@/composables/useConfirm'
import {
  Search, Plus, Picture, View, Delete, MagicStick, EditPen, Headset, Share, Refresh,
} from '@element-plus/icons-vue'
import { useAssetStore } from '@/stores/asset'
import { useUserStore } from '@/stores/user'
import AssetDetailModal from '@/components/pipeline/AssetDetailModal.vue'
import ImageWithWatermark from '@/components/ImageWithWatermark.vue'
import ImageViewer from '@/components/ImageViewer.vue'
import { listAssets, backfillAssets, type UnifiedAsset } from '@/api/assets'
import { listWorks, type WorkItem } from '@/api/works'
import { updateAssetShare, deleteAsset } from '@/api/pipeline'

const { t } = useI18n()
const { confirm } = useConfirm()
const assetStore = useAssetStore()
const userStore = useUserStore()
const router = useRouter()

const SOURCE_OPTIONS = [
  { value: 'generation', labelKey: 'assets.source.generation' },
  { value: 'upload', labelKey: 'assets.source.upload' },
  { value: 'compose', labelKey: 'assets.source.compose' },
  { value: 'archive', labelKey: 'assets.source.archive' },
]

// ---------- 状态 ----------
const loading = ref(false)
const items = ref<UnifiedAsset[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(24)
const works = ref<WorkItem[]>([])
const filters = reactive<{ media_type: string; source: string | null; work_id: number | null; keyword: string }>({
  media_type: '',
  source: null,
  work_id: null,
  keyword: '',
})
const modalVisible = ref(false)
const currentAssetId = ref<number | null>(null)
const sharingIds = ref<Set<number>>(new Set())
const detailVisible = ref(false)
const detailItem = ref<UnifiedAsset | null>(null)
const viewerVisible = ref(false)
const viewerUrl = ref('')

const TYPE_LABELS: Record<string, string> = {
  character: '角色',
  scene: '场景',
  material: '分镜图',
  clip: '视频片段',
  final: '成片',
  prop: '道具',
  brand: '品牌',
}

function typeLabel(type: string): string {
  return TYPE_LABELS[type] || type
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

// ---------- 数据加载 ----------
async function load(): Promise<void> {
  loading.value = true
  try {
    const data = await listAssets({
      media_type: filters.media_type || undefined,
      source: filters.source || undefined,
      work_id: filters.work_id ?? undefined,
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

// ---------- 存量补课（管理员）：资产行回填 + 历史生成批量入库 ----------
const backfilling = ref(false)

async function runBackfill(): Promise<void> {
  backfilling.value = true
  try {
    // 循环调用直到两阶段 remaining 都归零（每次最多 500 条，避免一次拉爆）
    let gensRemaining = Infinity
    let created = 0
    let migrated = 0
    for (let i = 0; i < 50 && gensRemaining > 0; i++) {
      const res = await backfillAssets(500)
      created += res.generations.created
      migrated += res.rows.migrated
      gensRemaining = res.generations.remaining
      if (res.rows.processed === 0 && res.generations.processed === 0) break
    }
    ElMessage.success(t('assets.backfillDone').replace('{n}', String(created)))
    reload()
  } catch (e: unknown) {
    const err = e as { message?: string }
    ElMessage.error(err.message || t('assets.loadFailed'))
  } finally {
    backfilling.value = false
  }
}

let keywordTimer: ReturnType<typeof setTimeout> | null = null
watch(() => filters.keyword, () => {
  if (keywordTimer) clearTimeout(keywordTimer)
  keywordTimer = setTimeout(reload, 300)
})

// ---------- 卡片交互（历史同款） ----------
function handleCardClick(a: UnifiedAsset): void {
  if (a.media_type === 'image' && a.asset_url) {
    openImageViewer(a)
    return
  }
  openDetail(a)
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
  detailVisible.value = true
}

function openImageViewer(a: UnifiedAsset): void {
  if (!a.asset_url) return
  viewerUrl.value = a.asset_url
  viewerVisible.value = true
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

async function removeAsset(a: UnifiedAsset): Promise<void> {
  await confirm(t('assets.deleteConfirm'), t('common.confirm'))
  try {
    await deleteAsset(a.id)
    ElMessage.success(t('assets.deleteSuccess'))
    items.value = items.value.filter((x) => x.id !== a.id)
    total.value = Math.max(0, total.value - 1)
  } catch (e: unknown) {
    const err = e as { message?: string }
    ElMessage.error(err.message || t('assets.deleteFailed'))
  }
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
  } catch (e: unknown) {
    ElMessage.error(t('assets.loadFailed'))
    // eslint-disable-next-line no-console
    console.warn('[assets] 下载失败:', e)
  }
}

function openCreate(): void {
  currentAssetId.value = null
  modalVisible.value = true
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

// ---------- 生命周期 ----------
onMounted(() => {
  void load()
  void loadWorks()
})
</script>

<style scoped>
.assets-view {
  padding: 24px 32px;
  max-width: 1280px;
  margin: 0 auto;
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
  color: var(--el-text-color-secondary);
}

.head-create {
  margin-left: auto;
}

.filter-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 20px;
}

.f-item {
  width: 150px;
}

.search-input {
  width: 220px;
}

/* 资产网格（历史卡片同款结构） */
.asset-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 18px;
}

.asset-card {
  border: 1px solid var(--agnes-border, #2a2a2a);
  border-radius: 10px;
  overflow: hidden;
  background: var(--el-bg-color);
  cursor: pointer;
  transition: box-shadow 0.2s;
}

.asset-card:hover {
  box-shadow: var(--el-box-shadow-light);
}

.card-preview {
  position: relative;
  height: 170px;
  background: var(--el-fill-color-light);
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
  color: var(--el-text-color-placeholder);
}

.type-badge {
  position: absolute;
  left: 8px;
  top: 8px;
  padding: 2px 8px;
  font-size: 11px;
  border-radius: 8px;
  background: rgba(0, 0, 0, 0.55);
  color: #fff;
}

.public-badge {
  position: absolute;
  right: 8px;
  top: 8px;
  display: flex;
  align-items: center;
  gap: 3px;
  padding: 2px 7px;
  font-size: 11px;
  border-radius: 8px;
  background: rgba(0, 0, 0, 0.55);
  color: var(--el-color-success);
}

/* 悬浮快捷钮（cover 内，hover 展示） */
.card-actions {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  padding: 6px 8px;
  background: linear-gradient(transparent, rgba(0, 0, 0, 0.65));
  opacity: 0;
  transition: opacity 0.15s;
}

.asset-card:hover .card-actions {
  opacity: 1;
}

.card-action-btn {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 6px;
  color: #fff;
  cursor: pointer;
}

.card-action-btn:hover {
  background: rgba(255, 255, 255, 0.18);
}

.card-info {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 8px 12px 10px;
}

.card-name {
  font-weight: 600;
  font-size: 13px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.card-time {
  font-size: 12px;
  color: var(--el-text-color-placeholder);
  white-space: nowrap;
}

.pagination-wrap {
  display: flex;
  justify-content: center;
  padding: 20px 0;
}

/* 详情查看窗口 */
.detail-content {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.detail-media {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 200px;
}

.detail-image {
  max-width: 100%;
  max-height: 65vh;
}

.detail-video {
  max-width: 100%;
  max-height: 65vh;
}

.detail-audio {
  width: 100%;
}

.detail-meta {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.detail-row {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 13px;
}

.detail-label {
  color: var(--el-text-color-secondary);
  min-width: 60px;
}
</style>
