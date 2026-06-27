<!-- =====================================================
     资产库页面 AssetsView
     - 展示用户保存的创作资产（角色、道具、场景、品牌）
     - 支持按类型筛选和关键词搜索
     - 复用 AssetCard 渲染卡片、AssetDetailModal 处理创建/编辑
     - 通过 useAssetStore 统一管理资产数据
     ===================================================== -->

<template>
  <div class="assets-view">
    <!-- 头部：标题 + 描述 -->
    <h2 class="page-title">{{ t('assets.title') }}</h2>
    <p class="page-desc">{{ t('assets.desc') }}</p>

    <!-- 筛选区 -->
    <div class="filter-bar">
      <!-- 类型 Tab：character/prop/scene/brand，"全部"用空串表示 -->
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
          clearable>
          <template #prefix>
            <el-icon><Search /></el-icon>
          </template>
        </el-input>
        <!-- 创建资产按钮（受 pipeline:save_asset 权限控制） -->
        <el-button
          v-permission="'pipeline:save_asset'"
          type="primary"
          @click="openCreate">
          <el-icon><Plus /></el-icon>
          {{ t('assets.createAsset') }}
        </el-button>
      </div>
    </div>

    <!-- 资产网格 -->
    <div v-loading="assetStore.loading" class="assets-section">
      <!-- 空状态 -->
      <div v-if="!assetStore.loading && filteredAssets.length === 0" class="empty-state">
        <el-icon :size="48"><FolderOpened /></el-icon>
        <p class="empty-text">{{ t('assets.emptyTip') }}</p>
      </div>

      <!-- 资产卡片网格：复用 AssetCard 组件 -->
      <div v-else class="asset-grid">
        <AssetCard
          v-for="asset in filteredAssets"
          :key="asset.id"
          :asset="asset"
          @click="openDetail(asset)"
          @use="useAsset"
        />
      </div>
    </div>

    <!-- 资产创建/编辑弹窗：复用 AssetDetailModal 组件（点击卡片进入编辑模式） -->
    <AssetDetailModal
      v-model="modalVisible"
      :asset-id="currentAssetId"
      @saved="onAssetSaved"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useI18n } from '@/i18n'
import { ElMessage } from 'element-plus'
import { Search, FolderOpened, Plus } from '@element-plus/icons-vue'
import { useAssetStore } from '@/stores/asset'
import AssetCard from '@/components/pipeline/AssetCard.vue'
import AssetDetailModal from '@/components/pipeline/AssetDetailModal.vue'
import type { Asset, AssetType } from '@/types'

const { t } = useI18n()
const assetStore = useAssetStore()

// ---------- 状态 ----------
const searchKeyword = ref('')
const modalVisible = ref(false)
const currentAssetId = ref<number | null>(null)

// ---------- 计算属性 ----------
// 类型 Tab 双向绑定到 store.filter.type，变更后自动重新加载
const activeType = computed<string>({
  get: () => assetStore.filter.type,
  set: (val: string) => {
    assetStore.setFilter({ type: val as '' | AssetType })
    reloadAssets()
  },
})

// 已加载资产基础上按关键词做本地过滤
const filteredAssets = computed(() => {
  const kw = searchKeyword.value.trim().toLowerCase()
  if (!kw) return assetStore.assets
  return assetStore.assets.filter(a =>
    a.name.toLowerCase().includes(kw) ||
    a.description?.toLowerCase().includes(kw) ||
    a.visual_description?.toLowerCase().includes(kw) ||
    a.tags?.some(tag => tag.toLowerCase().includes(kw))
  )
})

// ---------- 方法 ----------
// 重新加载资产列表（按当前 type 过滤；asset_type 字段由 getAssets 扩展支持）
async function reloadAssets() {
  try {
    await assetStore.loadAssets({
      asset_type: assetStore.filter.type || undefined,
    } as any)
  } catch (e: any) {
    ElMessage.error(e?.message || t('assets.loadFailed'))
  }
}

// 打开创建弹窗（无 assetId → AssetDetailModal 进入创建模式）
function openCreate() {
  currentAssetId.value = null
  modalVisible.value = true
}

// 打开编辑弹窗（带 assetId → AssetDetailModal 进入编辑模式）
function openDetail(asset: Asset) {
  currentAssetId.value = asset.id
  modalVisible.value = true
}

// 卡片"使用"按钮：暂未对接生成流程
function useAsset() {
  ElMessage.info(t('assets.useTip'))
}

// 保存成功后刷新列表
function onAssetSaved() {
  reloadAssets()
}

// ---------- 生命周期 ----------
onMounted(() => {
  reloadAssets()
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

.page-desc {
  font-size: 14px;
  color: var(--agnes-text-secondary);
  margin: 0 0 24px 0;
}

.filter-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 24px;
  flex-wrap: wrap;
}

.type-tabs {
  flex-shrink: 0;
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
  min-height: 400px;
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
  padding: 80px 20px;
  color: var(--agnes-text-placeholder);
}

.empty-text {
  margin-top: 12px;
  font-size: 14px;
}
</style>
