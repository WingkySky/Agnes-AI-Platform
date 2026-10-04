<!-- =====================================================
     资产库页面 AssetsView（子批次 2a 统一入口：单池）
     - 一个资产池：生成结果（自动入库）/ 上传素材 / 合成产物 / 归档记录 全在此
     - 筛选：媒体类型 / 来源 / 所属作品 / 关键词；分页加载
     - 卡片操作：预览 / 用于生成 / 分享到广场 / 编辑 / 删除
     - 「我的资产 / 创作单元」两池已合并：container 降级为来源维度
     ===================================================== -->

<template>
  <div class="assets-view">
    <div class="page-head">
      <h2 class="page-title">{{ t('assets.title') }}</h2>
      <span class="page-total">{{ t('assets.total').replace('{n}', String(total)) }}</span>
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
      <el-radio-group v-model="filters.media_type" class="type-tabs" @change="reload">
        <el-radio-button value="">{{ t('assets.mediaType.all') }}</el-radio-button>
        <el-radio-button value="image">{{ t('assets.mediaType.image') }}</el-radio-button>
        <el-radio-button value="video">{{ t('assets.mediaType.video') }}</el-radio-button>
        <el-radio-button value="audio">{{ t('assets.mediaType.audio') }}</el-radio-button>
      </el-radio-group>
      <el-select v-model="filters.source" clearable :placeholder="t('assets.filter.source')" class="f-item" @change="reload">
        <el-option v-for="s in SOURCE_OPTIONS" :key="s.value" :label="t(s.labelKey)" :value="s.value" />
      </el-select>
      <el-select v-model="filters.work_id" clearable :placeholder="t('assets.filter.work')" class="f-item" @change="reload">
        <el-option :label="t('assets.filter.allWork')" :value="-1" />
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
          <div class="card-cover" @click="openPreview(a)">
            <video
              v-if="a.media_type === 'video' && coverUrl(a)"
              :src="coverUrl(a) || ''"
              class="cover-media"
              muted
              playsinline
              preload="metadata"
            />
            <ImageWithWatermark v-else-if="coverUrl(a)" :src="coverUrl(a) || ''" :alt="a.name" />
            <div v-else class="cover-placeholder">
              <el-icon><Picture /></el-icon>
            </div>
          </div>
          <div class="card-meta">
            <span class="card-name" :title="a.name">{{ a.name }}</span>
            <div class="card-tags">
              <el-tag size="small" type="info">{{ typeLabel(a.type) }}</el-tag>
              <el-tag size="small" type="warning">{{ sourceLabel(a.source) }}</el-tag>
              <el-tag v-if="workTitleOf(a.work_id)" size="small">{{ workTitleOf(a.work_id) }}</el-tag>
            </div>
          </div>
          <div class="card-actions">
            <el-button size="small" text @click="openPreview(a)">
              <el-icon><View /></el-icon>{{ t('assets.preview') }}
            </el-button>
            <el-button size="small" text type="primary" @click="useForGeneration(a)">
              <el-icon><MagicStick /></el-icon>{{ t('assets.useInGeneration') }}
            </el-button>
            <el-button size="small" text @click="openEdit(a)">
              <el-icon><EditPen /></el-icon>{{ t('common.edit') }}
            </el-button>
            <el-tooltip
              v-if="a.moderation_status === 'rejected'"
              :content="t('assets.blockedTip')"
              placement="top"
            >
              <span class="share-switch blocked">
                <el-tag size="small" type="danger">{{ t('assets.blocked') }}</el-tag>
              </span>
            </el-tooltip>
            <span v-else class="share-switch">
              <el-switch
                :model-value="a.is_public"
                :loading="sharingIds.has(a.id)"
                :disabled="sharingIds.has(a.id)"
                inline-prompt
                :active-text="t('assets.shareToPlaza')"
                :inactive-text="t('assets.unshare')"
                @change="(v: boolean) => toggleShare(a, v)"
              />
              <el-tag v-if="a.is_public && a.moderation_status === 'pending'" size="small" type="warning">
                {{ t('assets.moderating') }}
              </el-tag>
            </span>
            <el-button size="small" text type="danger" @click="removeAsset(a)">
              <el-icon><Delete /></el-icon>{{ t('common.delete') }}
            </el-button>
          </div>
        </div>
      </div>
      <div v-if="items.length < total" class="load-more">
        <el-button :loading="loading" @click="loadMore">{{ t('assets.loadMore') }}</el-button>
      </div>
    </div>

    <!-- 预览弹窗 -->
    <el-dialog
      v-model="previewVisible"
      :title="previewItem?.name"
      width="min(90vw, 880px)"
      align-center
    >
      <div class="preview-body">
        <video
          v-if="previewItem && previewItem.media_type === 'video' && coverUrl(previewItem)"
          :src="coverUrl(previewItem) || ''"
          class="preview-video"
          controls
          playsinline
        />
        <el-image
          v-else-if="previewItem && coverUrl(previewItem)"
          :src="coverUrl(previewItem) || ''"
          fit="contain"
          class="preview-image"
        />
        <el-empty v-else :description="t('assets.noPreview')" />
      </div>
    </el-dialog>

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
  Search, Plus, Picture, View, Delete, MagicStick, EditPen,
} from '@element-plus/icons-vue'
import { useAssetStore } from '@/stores/asset'
import AssetDetailModal from '@/components/pipeline/AssetDetailModal.vue'
import ImageWithWatermark from '@/components/ImageWithWatermark.vue'
import { listAssets, type UnifiedAsset } from '@/api/assets'
import { listWorks, type WorkItem } from '@/api/works'
import { updateAssetShare, deleteAsset } from '@/api/pipeline'

const { t } = useI18n()
const { confirm } = useConfirm()
const assetStore = useAssetStore()
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
const PAGE_SIZE = 60
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
const previewVisible = ref(false)
const previewItem = ref<UnifiedAsset | null>(null)

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

function coverUrl(a: UnifiedAsset): string | null {
  return a.asset_url || a.thumb_url || (a.reference_images && a.reference_images[0]) || null
}

/** 作品标题（作品标记展示） */
function workTitleOf(workId: number | null): string | null {
  if (workId == null) return null
  return works.value.find((w) => w.id === workId)?.title ?? null
}

// ---------- 数据加载 ----------
async function load(): Promise<void> {
  loading.value = true
  try {
    const data = await listAssets({
      media_type: filters.media_type || undefined,
      source: filters.source || undefined,
      work_id: filters.work_id === null ? undefined : (filters.work_id === -1 ? undefined : filters.work_id),
      keyword: filters.keyword.trim() || undefined,
      page: page.value,
      page_size: PAGE_SIZE,
    })
    if (page.value === 1) items.value = data.items
    else items.value = items.value.concat(data.items)
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

function loadMore(): void {
  page.value += 1
  void load()
}

async function loadWorks(): Promise<void> {
  try {
    works.value = (await listWorks()).items
  } catch (_e) { /* 筛选项加载失败不阻塞列表 */ }
}

// 关键词防抖（300ms）
let keywordTimer: ReturnType<typeof setTimeout> | null = null
watch(() => filters.keyword, () => {
  if (keywordTimer) clearTimeout(keywordTimer)
  keywordTimer = setTimeout(reload, 300)
})

// ---------- 交互 ----------
function openPreview(a: UnifiedAsset): void {
  previewItem.value = a
  previewVisible.value = true
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
}

.card-cover {
  height: 150px;
  background: var(--el-fill-color-light);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  overflow: hidden;
}

.cover-media {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.cover-placeholder {
  color: var(--el-text-color-placeholder);
  font-size: 32px;
}

.card-meta {
  padding: 10px 12px 6px;
}

.card-name {
  font-weight: 600;
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.card-tags {
  display: flex;
  gap: 6px;
  margin-top: 6px;
  flex-wrap: wrap;
}

.card-actions {
  padding: 4px 8px 10px;
  display: flex;
  align-items: center;
  gap: 2px;
  flex-wrap: wrap;
}

.share-switch {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.load-more {
  display: flex;
  justify-content: center;
  padding: 20px 0;
}
</style>
