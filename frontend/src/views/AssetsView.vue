<!-- =====================================================
     资产库页面 AssetsView（M3 重构）
     - 一级两区：创作单元（画布/项目自动归档，按容器分组）+ 我的资产（传统手动资产）
     - 创作单元点击进入详情：按容器内实际存在的类型分 Tab 展示资产卡
       （预览 / 分享到广场开关 / 删除）
     - 深链：/assets?container=type:id 直达单元详情
     ===================================================== -->

<template>
  <div class="assets-view">
    <h2 class="page-title">{{ t('assets.title') }}</h2>

    <!-- ============ 单元详情视图 ============ -->
    <template v-if="selectedContainer">
      <div class="detail-head">
        <el-button text @click="closeContainer">
          <el-icon><ArrowLeft /></el-icon>
          {{ t('assets.back') }}
        </el-button>
        <div class="detail-title">
          <el-tag size="small" type="info">{{ selectedContainer.type_label || selectedContainer.container_type }}</el-tag>
          <span class="detail-name">{{ selectedContainer.container_name || t('assets.unnamedUnit') }}</span>
        </div>
      </div>

      <el-tabs v-if="assetGroups.length" v-model="activeTypeTab" class="detail-tabs">
        <el-tab-pane v-for="grp in assetGroups" :key="grp.type" :label="grp.label" :name="grp.type">
          <div class="unit-asset-grid">
            <div v-for="a in grp.items" :key="a.id" class="unit-asset-card">
              <div class="unit-asset-cover" @click="openPreview(a)">
                <video
                  v-if="a.kind === 'video' && coverUrl(a)"
                  :src="coverUrl(a) || ''"
                  class="cover-media"
                  muted
                  playsinline
                  preload="metadata"
                />
                <ImageWithWatermark
                  v-else-if="coverUrl(a)"
                  :src="coverUrl(a) || ''"
                  :alt="a.name"
                />
                <div v-else class="cover-placeholder">
                  <el-icon><Picture /></el-icon>
                </div>
              </div>
              <div class="unit-asset-meta">
                <span class="unit-asset-name" :title="a.name">{{ a.name }}</span>
                <el-tag size="small" type="info">{{ typeLabel(a.type) }}</el-tag>
              </div>
              <div class="unit-asset-actions">
                <el-button size="small" text @click="openPreview(a)">
                  <el-icon><View /></el-icon>{{ t('assets.preview') }}
                </el-button>
                <el-button size="small" text type="primary" @click="useForGeneration(a)">
                  <el-icon><MagicStick /></el-icon>{{ t('assets.useInGeneration') }}
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
        </el-tab-pane>
      </el-tabs>

      <el-empty v-else :description="t('assets.unitEmpty')" />
    </template>

    <!-- ============ 总览视图 ============ -->
    <template v-else>
      <!-- 创作单元区 -->
      <section class="zone">
        <div class="zone-head">
          <h3 class="zone-title">{{ t('assets.zones.creationUnits') }}</h3>
          <span class="zone-desc">{{ t('assets.zones.creationUnitsDesc') }}</span>
        </div>
        <div v-if="containersLoading" v-loading="true" class="zone-body" />
        <div v-else-if="containers.length" class="unit-card-grid">
          <div
            v-for="c in containers"
            :key="containerKey(c)"
            class="unit-card"
            @click="openContainer(c)"
          >
            <div class="unit-card-cover">
                <video
                  v-if="c.cover_kind === 'video' && c.cover_url"
                  :src="c.cover_url || ''"
                  class="cover-media"
                  muted
                  playsinline
                  preload="metadata"
                />
                <ImageWithWatermark v-else-if="c.cover_url" :src="c.cover_url || ''" :alt="c.container_name || ''" />
              <div v-else class="cover-placeholder">
                <el-icon><FolderOpened /></el-icon>
              </div>
            </div>
            <div class="unit-card-meta">
              <el-tag size="small" type="info">{{ c.type_label }}</el-tag>
              <span class="unit-card-name" :title="c.container_name || ''">{{ c.container_name || t('assets.unnamedUnit') }}</span>
              <span class="unit-card-count">{{ c.asset_count }} {{ t('assets.assetsCountUnit') }}</span>
            </div>
          </div>
        </div>
        <el-empty v-else :description="t('assets.containerEmpty')" />
      </section>

      <!-- 我的资产区 -->
      <section class="zone">
        <div class="zone-head">
          <h3 class="zone-title">{{ t('assets.zones.standalone') }}</h3>
          <span class="zone-desc">{{ t('assets.zones.standaloneDesc') }}</span>
        </div>
        <div class="filter-bar">
          <el-radio-group v-model="activeType" class="type-tabs">
            <el-radio-button value="">{{ t('assets.type.all') }}</el-radio-button>
            <el-radio-button value="character">{{ t('assets.type.character') }}</el-radio-button>
            <el-radio-button value="prop">{{ t('assets.type.prop') }}</el-radio-button>
            <el-radio-button value="scene">{{ t('assets.type.scene') }}</el-radio-button>
            <el-radio-button value="brand">{{ t('assets.type.brand') }}</el-radio-button>
          </el-radio-group>
          <div class="filter-right">
            <el-input
              v-model="searchKeyword"
              :placeholder="t('assets.searchPlaceholder')"
              class="search-input"
              clearable
            >
              <template #prefix>
                <el-icon><Search /></el-icon>
              </template>
            </el-input>
            <el-button
              v-permission="'pipeline:save_asset'"
              type="primary"
              @click="openCreate"
            >
              <el-icon><Plus /></el-icon>
              {{ t('assets.createAsset') }}
            </el-button>
          </div>
        </div>

        <div v-loading="standaloneLoading" class="assets-section">
          <div v-if="!standaloneLoading && filteredStandalone.length === 0" class="empty-state">
            <el-icon :size="48"><FolderOpened /></el-icon>
            <p class="empty-text">{{ t('assets.standaloneEmpty') }}</p>
          </div>
          <div v-else class="asset-grid">
            <AssetCard
              v-for="asset in filteredStandalone"
              :key="asset.id"
              :asset="asset"
              @click="openDetail(asset)"
              @use="useAsset"
            />
          </div>
        </div>
      </section>
    </template>

    <!-- 预览弹窗 -->
    <el-dialog
      v-model="previewVisible"
      :title="previewAsset?.name"
      width="min(90vw, 880px)"
      align-center
    >
      <div class="preview-body">
        <video
          v-if="previewAsset && previewAsset.kind === 'video' && coverUrl(previewAsset)"
          :src="coverUrl(previewAsset) || ''"
          class="preview-video"
          controls
          playsinline
        />
        <el-image
          v-else-if="previewAsset && coverUrl(previewAsset)"
          :src="coverUrl(previewAsset) || ''"
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
      @saved="onAssetSaved"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from '@/i18n'
import { ElMessage, ElMessageBox, ElImage } from 'element-plus'
import {
  Search, FolderOpened, Plus, Picture, ArrowLeft, View, Delete, MagicStick,
} from '@element-plus/icons-vue'
import { useAssetStore } from '@/stores/asset'
import AssetCard from '@/components/pipeline/AssetCard.vue'
import AssetDetailModal from '@/components/pipeline/AssetDetailModal.vue'
import ImageWithWatermark from '@/components/ImageWithWatermark.vue'
import type { Asset, AssetContainer, AssetContainerDetail } from '@/types'
import {
  getAssetContainers,
  getContainerAssets,
  updateAssetShare,
  deleteAsset,
} from '@/api/pipeline'

const { t } = useI18n()
const assetStore = useAssetStore()
const route = useRoute()
const router = useRouter()

// ---------- 状态 ----------
const containersLoading = ref(false)
const containers = ref<AssetContainer[]>([])
const standaloneLoading = ref(false)
const standaloneAssets = ref<Asset[]>([])
const searchKeyword = ref('')
const activeType = ref('')
const modalVisible = ref(false)
const currentAssetId = ref<number | null>(null)

const selectedKey = computed(() => (route.query.container as string) || '')
const selectedContainer = ref<AssetContainer | null>(null)
const containerAssets = ref<Asset[]>([])
const activeTypeTab = ref('')
const sharingIds = ref<Set<number>>(new Set())

const previewVisible = ref(false)
const previewAsset = ref<Asset | null>(null)

// ---------- 计算属性 ----------
const TYPE_TAB_LABELS: Record<string, string> = {
  character: '角色',
  scene: '场景',
  material: '分镜图',
  clip: '视频片段',
  final: '成片',
  prop: '道具',
  brand: '品牌',
}

function typeLabel(type: string): string {
  return TYPE_TAB_LABELS[type] || type
}

function coverUrl(a: Asset): string | null {
  return a.asset_url || (a.reference_images && a.reference_images[0]) || null
}

function containerKey(c: AssetContainer): string {
  return `${c.container_type}:${c.container_id}`
}

function parseContainerKey(key: string): { type: string; id: string } | null {
  const idx = key.indexOf(':')
  if (idx < 0) return null
  return { type: key.slice(0, idx), id: key.slice(idx + 1) }
}

// 单元详情：按容器内实际存在的类型分 Tab
const assetGroups = computed(() => {
  const map = new Map<string, Asset[]>()
  for (const a of containerAssets.value) {
    const arr = map.get(a.type) || []
    arr.push(a)
    map.set(a.type, arr)
  }
  return Array.from(map.entries()).map(([type, items]) => ({
    type,
    label: typeLabel(type),
    items,
  }))
})

watch(assetGroups, (groups) => {
  if (groups.length && !activeTypeTab.value) activeTypeTab.value = groups[0].type
})

// 深链：/assets?container=type:id
watch(
  selectedKey,
  async (key) => {
    if (!key) {
      selectedContainer.value = null
      containerAssets.value = []
      return
    }
    const parsed = parseContainerKey(key)
    if (!parsed) {
      selectedContainer.value = null
      return
    }
    const meta = containers.value.find((c) => containerKey(c) === key)
    selectedContainer.value = meta || {
      container_type: parsed.type,
      container_id: parsed.id,
      container_name: null,
    }
    await loadContainerDetail(parsed.type, parsed.id)
  },
  { immediate: true },
)

// ---------- 数据加载 ----------
async function loadContainers() {
  containersLoading.value = true
  try {
    const data = await getAssetContainers()
    containers.value = data.containers || []
  } catch (e: unknown) {
    const err = e as { message?: string }
    ElMessage.error(err.message || t('assets.loadFailed'))
  } finally {
    containersLoading.value = false
  }
}

async function loadStandalone() {
  standaloneLoading.value = true
  try {
    await assetStore.loadAssets({
      scope: 'my',
    } as Parameters<typeof assetStore.loadAssets>[0])
    standaloneAssets.value = assetStore.assets
  } catch (e: unknown) {
    const err = e as { message?: string }
    ElMessage.error(err.message || t('assets.loadFailed'))
  } finally {
    standaloneLoading.value = false
  }
}

// 我的资产：本地按类型 + 关键词过滤（避免每次输入打接口）
const filteredStandalone = computed(() => {
  const kw = searchKeyword.value.trim().toLowerCase()
  return standaloneAssets.value.filter((a) => {
    if (activeType.value && a.type !== activeType.value) return false
    if (!kw) return true
    return (
      a.name.toLowerCase().includes(kw) ||
      (a.description || '').toLowerCase().includes(kw) ||
      (a.visual_description || '').toLowerCase().includes(kw) ||
      (a.tags || []).some((tag) => tag.toLowerCase().includes(kw))
    )
  })
})

async function loadContainerDetail(type: string, id: string) {
  try {
    const detail: AssetContainerDetail = await getContainerAssets(type, id)
    containerAssets.value = detail.items || []
    selectedContainer.value = {
      container_type: type,
      container_id: id,
      container_name: detail.container_name,
      type_label: detail.type_label,
    }
    activeTypeTab.value = ''
  } catch (e: unknown) {
    const err = e as { message?: string }
    ElMessage.error(err.message || t('assets.loadFailed'))
  }
}

// ---------- 交互 ----------
function openContainer(c: AssetContainer) {
  router.push({ query: { ...route.query, container: containerKey(c) } })
}

function closeContainer() {
  const q = { ...route.query }
  delete q.container
  router.push({ query: q })
}

function openPreview(a: Asset) {
  previewAsset.value = a
  previewVisible.value = true
}

async function toggleShare(a: Asset, val: boolean) {
  sharingIds.value = new Set(sharingIds.value).add(a.id)
  try {
    const res = await updateAssetShare(a.id, val)
    a.is_public = res.is_public
    if (val) {
      a.moderation_status = 'pending'
      ElMessage.success(t('assets.shareSuccess'))
    } else {
      ElMessage.success(t('assets.unshareSuccess'))
    }
  } catch (e: unknown) {
    const err = e as { message?: string }
    ElMessage.error(err.message || t('assets.shareFailed'))
  } finally {
    const next = new Set(sharingIds.value)
    next.delete(a.id)
    sharingIds.value = next
  }
}

async function removeAsset(a: Asset) {
  const isArchive = !!a.container_type
  try {
    await ElMessageBox.confirm(
      isArchive ? t('assets.deleteArchiveConfirm') : t('assets.deleteConfirm'),
      t('common.confirm'),
      { type: 'warning' },
    )
  } catch {
    return
  }
  try {
    await deleteAsset(a.id)
    ElMessage.success(t('assets.deleteSuccess'))
    containerAssets.value = containerAssets.value.filter((x) => x.id !== a.id)
    await loadContainers()
  } catch (e: unknown) {
    const err = e as { message?: string }
    ElMessage.error(err.message || t('assets.deleteFailed'))
  }
}

// 我的资产区：类型筛选 / 搜索（本地过滤，无需重新请求）

function openCreate() {
  currentAssetId.value = null
  modalVisible.value = true
}

function openDetail(asset: Asset) {
  currentAssetId.value = asset.id
  modalVisible.value = true
}

function useAsset(asset: Asset) {
  useForGeneration(asset)
}

/** 「用于生成」：写入 pendingUse 并跳转生成页（image kind → 生图页，video kind → 视频页） */
function useForGeneration(a: Asset) {
  assetStore.setPendingUse(a)
  router.push(a.kind === 'video' ? '/videos' : '/images')
  ElMessage.success(t('assets.useForGenerationTip'))
}

function onAssetSaved() {
  loadStandalone()
  loadContainers()
}

// ---------- 生命周期 ----------
onMounted(() => {
  loadContainers()
  loadStandalone()
})
</script>

<style scoped>
.assets-view {
  padding: 24px 32px;
  max-width: 1280px;
  margin: 0 auto;
}

.page-title {
  font-size: 28px;
  font-weight: 600;
  margin: 0 0 8px 0;
  color: var(--agnes-text-primary);
}

/* 总览：分区 */
.zone {
  margin-bottom: 32px;
}
.zone-head {
  display: flex;
  align-items: baseline;
  gap: 12px;
  margin-bottom: 16px;
}
.zone-title {
  font-size: 18px;
  font-weight: 600;
  margin: 0;
  color: var(--agnes-text-primary);
}
.zone-desc {
  font-size: 13px;
  color: var(--agnes-text-secondary);
}
.zone-body {
  min-height: 120px;
}

/* 创作单元卡片网格 */
.unit-card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 20px;
}
.unit-card {
  border: 1px solid var(--agnes-border, #2a2a2a);
  border-radius: 10px;
  overflow: hidden;
  cursor: pointer;
  background: var(--agnes-bg-elevated, #1d1d1f);
  transition: transform 0.2s, border-color 0.2s;
}
.unit-card:hover {
  transform: translateY(-2px);
  border-color: var(--el-color-primary);
}
.unit-card-cover {
  aspect-ratio: 16 / 9;
  background: var(--agnes-bg-page);
  overflow: hidden;
}
.unit-card-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
}
.unit-card-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--agnes-text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
}
.unit-card-count {
  font-size: 12px;
  color: var(--agnes-text-placeholder);
  white-space: nowrap;
}

/* 我的资产筛选 */
.filter-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 24px;
  flex-wrap: wrap;
}
.filter-right {
  display: flex;
  align-items: center;
  gap: 12px;
}
.search-input {
  width: 240px;
}
.assets-section {
  min-height: 200px;
}
.asset-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 20px;
}
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 20px;
  color: var(--agnes-text-placeholder);
}
.empty-text {
  margin-top: 12px;
  font-size: 14px;
}

/* 单元详情 */
.detail-head {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 16px;
}
.detail-title {
  display: flex;
  align-items: center;
  gap: 10px;
}
.detail-name {
  font-size: 20px;
  font-weight: 600;
  color: var(--agnes-text-primary);
}
.detail-tabs {
  margin-top: 8px;
}
.unit-asset-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 20px;
  padding-top: 8px;
}
.unit-asset-card {
  border: 1px solid var(--agnes-border, #2a2a2a);
  border-radius: 10px;
  overflow: hidden;
  background: var(--agnes-bg-elevated, #1d1d1f);
}
.unit-asset-cover {
  aspect-ratio: 16 / 9;
  background: var(--agnes-bg-page);
  overflow: hidden;
  cursor: pointer;
}
.unit-asset-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px 4px;
}
.unit-asset-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--agnes-text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
}
.unit-asset-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  padding: 4px 12px 12px;
}
.share-switch {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

/* 封面/预览媒体 */
.cover-media {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.cover-placeholder {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--agnes-text-placeholder);
  font-size: 32px;
}
.preview-body {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 200px;
}
.preview-video {
  max-width: 100%;
  max-height: 70vh;
  border-radius: 6px;
}
.preview-image {
  max-width: 100%;
  max-height: 70vh;
}
</style>
