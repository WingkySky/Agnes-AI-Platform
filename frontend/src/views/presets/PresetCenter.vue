<!-- =====================================================
     PresetCenter — 预设中心完整页面（统一入口）
     - 左侧：category 筛选栏 + 标签搜索 + 快捷筛选
     - 右侧：卡片网格布局
     - 顶部：type Tab 切换 + 搜索框 + 排序下拉
     - 详情：点击卡片名称/菜单项打开右侧详情抽屉
     ===================================================== -->

<template>
  <div class="preset-center">
    <!-- ====== 页面头部 ====== -->
    <header class="page-head">
      <div>
        <h2>{{ t('presets.center.title') }}</h2>
        <p class="muted">{{ t('presets.center.desc') }}</p>
      </div>
    </header>

    <!-- ====== 主视图 Tab：预设 / 作品展示 ====== -->
    <el-tabs v-model="viewMode" class="main-tabs" @tab-change="onMainTabChange">
      <el-tab-pane :label="t('presets.center.tabPresets')" name="presets" />
      <el-tab-pane :label="t('presets.center.tabWorks')" name="works" />
    </el-tabs>

    <!-- ====== 视图 1：预设列表 ====== -->
    <template v-if="viewMode === 'presets'">
    <!-- ====== 类型 Tab + 社区库 + 搜索 + 排序 ====== -->
    <div class="toolbar">
      <div class="toolbar-left">
        <el-radio-group v-model="currentType" size="default" @change="onTypeChange">
          <el-radio-button value="">{{ t('presets.center.typeAll') }}</el-radio-button>
          <el-radio-button value="camera">{{ t('presets.center.typeCamera') }}</el-radio-button>
          <el-radio-button value="prompt">{{ t('presets.center.typePrompt') }}</el-radio-button>
          <el-radio-button value="style">{{ t('presets.center.typeStyle') }}</el-radio-button>
          <el-radio-button value="script">{{ t('presets.center.typeScript') }}</el-radio-button>
          <el-radio-button value="pipeline">{{ t('presets.center.typePipeline') }}</el-radio-button>
        </el-radio-group>
        <el-button
          :type="isCommunity ? 'primary' : 'default'"
          size="default"
          style="margin-left: 12px"
          @click="toggleCommunity"
        >
          {{ t('presets.center.community') }}
        </el-button>
      </div>
      <div class="toolbar-right">
        <el-input
          v-model="searchText"
          :placeholder="t('presets.center.searchPlaceholder')"
          clearable
          style="width: 240px"
          :prefix-icon="Search"
          @keyup.enter="onSearch"
          @clear="onSearch"
        />
        <el-select
          v-model="sortMode"
          style="width: 140px; margin-left: 8px"
          @change="fetchData"
        >
          <el-option :label="t('presets.center.sortNew')" value="new" />
          <el-option :label="t('presets.center.sortUsage')" value="usage" />
          <el-option :label="t('presets.center.sortName')" value="name" />
        </el-select>
        <!-- 导入/导出按钮（非社区库模式下显示） -->
        <ImportExport
          v-if="!isCommunity"
          :preset-type="currentType"
          style="margin-left: 8px"
          @imported="fetchData"
        />
        <el-button type="primary" :icon="Plus" @click="openCreateDialog" style="margin-left: 8px">
          {{ t('presets.center.createBtn') }}
        </el-button>
      </div>
    </div>

    <!-- ====== 主内容：左侧筛选 + 右侧卡片 ====== -->
    <div class="content-row">
      <!-- 左侧筛选侧边栏 -->
      <aside class="filter-aside">
        <el-card shadow="never" class="filter-card">
          <PresetFilterSidebar @filter="onFilterChange" />
        </el-card>
      </aside>

      <!-- 右侧卡片网格 -->
      <main class="card-main">
        <el-card shadow="never" class="list-card" v-loading="loading">
          <!-- 卡片网格 -->
          <div class="card-grid" v-if="presets.length > 0">
            <PresetCard
              v-for="preset in presets"
              :key="preset.id"
              :preset="preset"
              :show-fork="isCommunity"
              @detail="openDetailDrawer"
              @edit="openEditDialog"
              @delete="handleDeletePreset"
              @toggle-public="handleTogglePublic"
              @use="onUsePreset"
              @fork="handleForkPreset"
            />
          </div>

          <!-- 空状态 -->
          <div class="empty-state" v-else>
            <p class="empty-text">{{ t('presets.center.empty') }}</p>
            <el-button type="primary" @click="openCreateDialog">
              {{ t('presets.center.createFirst') }}
            </el-button>
          </div>

          <!-- 分页 -->
          <div class="pagination-wrap" v-if="total > filters.limit">
            <el-pagination
              v-model:current-page="currentPage"
              :page-size="filters.limit"
              :total="total"
              layout="total, prev, pager, next"
              @current-change="onPageChange"
            />
          </div>
        </el-card>
      </main>
    </div>
    </template>

    <!-- ====== 视图 2：作品展示（按预设浏览） ====== -->
    <template v-else>
      <div class="works-view">
        <!-- 顶部工具栏：预设选择器 + 类型筛选 + 排序 -->
        <div class="works-toolbar">
          <el-select
            v-model="worksSelectedPresetId"
            filterable
            remote
            clearable
            reserve-keyword
            :remote-method="searchPresetsForWorks"
            :loading="presetSearchLoading"
            :placeholder="t('presets.works.selectPresetPlaceholder')"
            style="width: 320px"
            @change="onWorksPresetChange"
          >
            <el-option
              v-for="p in presetOptions"
              :key="p.id"
              :label="`${p.name} (${typeLabel(p.type)})`"
              :value="p.id"
            />
          </el-select>

          <el-radio-group v-model="worksType" size="default" @change="onWorksFilterChange">
            <el-radio-button value="">{{ t('presets.works.typeAll') }}</el-radio-button>
            <el-radio-button value="image">{{ t('presets.works.typeImage') }}</el-radio-button>
            <el-radio-button value="video">{{ t('presets.works.typeVideo') }}</el-radio-button>
          </el-radio-group>

          <el-select v-model="worksSort" style="width: 140px" @change="onWorksFilterChange">
            <el-option :label="t('presets.works.sortLatest')" value="latest" />
            <el-option :label="t('presets.works.sortPopular')" value="popular" />
          </el-select>
        </div>

        <!-- 作品网格 -->
        <el-card shadow="never" class="works-list-card" v-loading="worksLoading">
          <div class="works-big-grid" v-if="worksList.length > 0">
            <div
              v-for="work in worksList"
              :key="work.id"
              class="work-big-item"
              @click="openWorkDetail(work)"
            >
              <img
                v-if="work.type === 'image'"
                :src="work.result_url"
                :alt="work.prompt"
                loading="lazy"
              />
              <template v-else>
                <video
                  :src="work.result_url"
                  :poster="work.result_url"
                  muted
                  preload="metadata"
                  controls
                  @click.stop
                />
                <span class="work-type-badge">{{ t('presets.detail.workTypeVideo') }}</span>
              </template>
              <div class="work-big-meta">
                <div class="work-big-author">
                  <el-avatar :size="20" :src="work.author_avatar_url" />
                  <span>{{ work.author_nickname || 'Anonymous' }}</span>
                </div>
                <div class="work-big-stats">
                  <span>❤ {{ work.likes_count || 0 }}</span>
                  <span>👁 {{ work.views_count || 0 }}</span>
                </div>
              </div>
            </div>
          </div>
          <div class="empty-state" v-else>
            <p class="empty-text">{{ t('presets.works.empty') }}</p>
          </div>
          <div class="pagination-wrap" v-if="worksTotal > worksPageSize">
            <el-pagination
              v-model:current-page="worksPage"
              :page-size="worksPageSize"
              :total="worksTotal"
              layout="total, prev, pager, next"
              @current-change="onWorksPageChange"
            />
          </div>
        </el-card>
      </div>
    </template>

    <!-- ====== PresetEditorDialog ====== -->
    <PresetEditorDialog
      v-model="dialogVisible"
      :preset="editingPreset"
      @submit="onSubmitPreset"
    />

    <!-- ====== 预设详情抽屉 ====== -->
    <el-drawer
      v-model="detailDrawerVisible"
      :title="t('presets.detail.title')"
      direction="rtl"
      size="480px"
      destroy-on-close
    >
      <div class="detail-content" v-if="detailPreset">
        <!-- 基本信息 -->
        <div class="detail-section">
          <h4 class="detail-section-title">{{ t('presets.detail.basicSection') }}</h4>
          <div class="detail-row">
            <span class="detail-label">{{ t('presets.detail.typeLabel') }}</span>
            <el-tag size="small" effect="plain">{{ typeLabel(detailPreset.type) }}</el-tag>
          </div>
          <div class="detail-row">
            <span class="detail-label">{{ t('presets.detail.categoryLabel') }}</span>
            <span class="detail-value">{{ detailPreset.category || t('presets.card.defaultCategory') }}</span>
          </div>
          <div class="detail-row">
            <span class="detail-label">{{ t('presets.detail.usageLabel') }}</span>
            <span class="detail-value">{{ detailPreset.usage_count || 0 }}</span>
          </div>
          <div class="detail-row">
            <span class="detail-label">{{ t('presets.detail.publicStatus') }}</span>
            <el-tag v-if="detailPreset.is_public" size="small" type="success">
              {{ t('presets.detail.public') }}
            </el-tag>
            <el-tag v-else size="small" type="info">{{ t('presets.detail.private') }}</el-tag>
            <el-tag
              v-if="detailPreset.is_approved"
              size="small"
              type="success"
              effect="plain"
              style="margin-left: 6px"
            >
              {{ t('presets.detail.approved') }}
            </el-tag>
            <el-tag
              v-else-if="detailPreset.is_public"
              size="small"
              type="warning"
              effect="plain"
              style="margin-left: 6px"
            >
              {{ t('presets.detail.pending') }}
            </el-tag>
          </div>
          <div class="detail-row" v-if="detailPreset.tags && detailPreset.tags.length > 0">
            <span class="detail-label">{{ t('presets.detail.tagsLabel') }}</span>
            <div class="detail-tags">
              <el-tag
                v-for="tag in detailPreset.tags"
                :key="tag"
                size="small"
                type="info"
                effect="plain"
              >
                {{ tag }}
              </el-tag>
            </div>
          </div>
          <div class="detail-row" v-if="detailPreset.description">
            <span class="detail-label">{{ t('presets.description') }}</span>
            <span class="detail-value">{{ detailPreset.description }}</span>
          </div>
        </div>

        <!-- 提示词内容 -->
        <div class="detail-section" v-if="detailPreset.prompt_text">
          <h4 class="detail-section-title">{{ t('presets.detail.promptSection') }}</h4>
          <pre class="detail-pre">{{ detailPreset.prompt_text }}</pre>
        </div>

        <!-- 摄像机参数 -->
        <div class="detail-section" v-if="detailPreset.camera_params">
          <h4 class="detail-section-title">{{ t('presets.detail.cameraSection') }}</h4>
          <div class="detail-row" v-if="detailPreset.camera_params.camera_model">
            <span class="detail-label">{{ t('presets.detail.cameraModel') }}</span>
            <span class="detail-value">{{ detailPreset.camera_params.camera_model }}</span>
          </div>
          <div class="detail-row" v-if="detailPreset.camera_params.focal_length">
            <span class="detail-label">{{ t('presets.detail.focalLength') }}</span>
            <span class="detail-value">{{ detailPreset.camera_params.focal_length }}</span>
          </div>
          <div class="detail-row" v-if="detailPreset.camera_params.aperture">
            <span class="detail-label">{{ t('presets.detail.aperture') }}</span>
            <span class="detail-value">{{ detailPreset.camera_params.aperture }}</span>
          </div>
          <div class="detail-row" v-if="detailPreset.camera_params.depth_of_field">
            <span class="detail-label">{{ t('presets.detail.depthOfField') }}</span>
            <span class="detail-value">{{ detailPreset.camera_params.depth_of_field }}</span>
          </div>
          <div class="detail-row" v-if="detailPreset.camera_params.shutter_speed">
            <span class="detail-label">{{ t('presets.detail.shutterSpeed') }}</span>
            <span class="detail-value">{{ detailPreset.camera_params.shutter_speed }}</span>
          </div>
          <div class="detail-row" v-if="detailPreset.camera_params.shutter_angle">
            <span class="detail-label">{{ t('presets.detail.shutterAngle') }}</span>
            <span class="detail-value">{{ detailPreset.camera_params.shutter_angle }}°</span>
          </div>
          <div class="detail-row" v-if="detailPreset.camera_params.camera_movement">
            <span class="detail-label">{{ t('presets.detail.cameraMovement') }}</span>
            <span class="detail-value">{{ detailPreset.camera_params.camera_movement }}</span>
          </div>
          <div class="detail-row" v-if="detailPreset.camera_params.camera_angle">
            <span class="detail-label">{{ t('presets.detail.cameraAngle') }}</span>
            <span class="detail-value">{{ detailPreset.camera_params.camera_angle }}</span>
          </div>
          <div class="detail-row" v-if="detailPreset.camera_params.aspect_ratio">
            <span class="detail-label">{{ t('presets.detail.aspectRatio') }}</span>
            <span class="detail-value">{{ detailPreset.camera_params.aspect_ratio }}</span>
          </div>
          <div class="detail-row" v-if="detailPreset.camera_params.visual_style">
            <span class="detail-label">{{ t('presets.detail.visualStyle') }}</span>
            <span class="detail-value">{{ detailPreset.camera_params.visual_style }}</span>
          </div>
        </div>

        <!-- 脚本文本 -->
        <div class="detail-section" v-if="detailPreset.script_text">
          <h4 class="detail-section-title">{{ t('presets.detail.scriptSection') }}</h4>
          <pre class="detail-pre">{{ detailPreset.script_text }}</pre>
        </div>

        <!-- 流水线配置 -->
        <div class="detail-section" v-if="detailPreset.pipeline_config">
          <h4 class="detail-section-title">{{ t('presets.detail.pipelineSection') }}</h4>
          <pre class="detail-pre">{{ formatPipelineConfig(detailPreset.pipeline_config) }}</pre>
        </div>

        <!-- 作品效果：使用该预设生成的公开作品 -->
        <div class="detail-section">
          <h4 class="detail-section-title">
            {{ t('presets.detail.worksSection') }}
            <span class="works-count" v-if="detailWorksTotal > 0">({{ detailWorksTotal }})</span>
          </h4>
          <div v-loading="detailWorksLoading">
            <!-- 作品网格 -->
            <div class="works-grid" v-if="detailWorks.length > 0">
              <div
                v-for="work in detailWorks"
                :key="work.id"
                class="work-item"
                @click="openWorkDetail(work)"
              >
                <img
                  v-if="work.type === 'image'"
                  :src="work.result_url"
                  :alt="work.prompt"
                  loading="lazy"
                />
                <template v-else>
                  <video
                    :src="work.result_url"
                    :poster="work.result_url"
                    muted
                    preload="metadata"
                    @click.stop
                  />
                  <span class="work-type-badge">{{ t('presets.detail.workTypeVideo') }}</span>
                </template>
                <div class="work-meta">
                  <span class="work-likes">❤ {{ work.likes_count || 0 }}</span>
                  <span class="work-views">👁 {{ work.views_count || 0 }}</span>
                </div>
              </div>
            </div>
            <!-- 空状态 -->
            <p class="works-empty" v-else-if="!detailWorksLoading">
              {{ t('presets.detail.worksEmpty') }}
            </p>
            <!-- 加载更多 -->
            <div class="works-more" v-if="detailWorks.length < detailWorksTotal">
              <el-button text type="primary" @click="loadMoreWorks">
                {{ t('presets.detail.worksLoadMore') }}
              </el-button>
            </div>
          </div>
        </div>
      </div>

      <!-- 抽屉底部操作按钮 -->
      <template #footer>
        <div class="detail-footer">
          <el-button @click="detailDrawerVisible = false">
            {{ t('presets.detail.close') }}
          </el-button>
          <el-button v-if="isCommunity" type="primary" plain @click="forkFromDetail">
            {{ t('presets.detail.fork') }}
          </el-button>
          <el-button v-else type="primary" @click="editFromDetail">
            {{ t('presets.detail.edit') }}
          </el-button>
        </div>
      </template>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
/**
 * PresetCenter — 预设中心（侧边栏 + 卡片网格 + 详情抽屉）
 * 统一入口，覆盖 camera/prompt/style/script/pipeline 全类型预设。
 */
import { ref, onMounted, computed } from 'vue'
import { Plus, Search } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useI18n } from '@/i18n'
import { usePresetStore } from '@/stores/presets'
import PresetCard from '@/components/presets/PresetCard.vue'
import PresetFilterSidebar from '@/components/presets/PresetFilterSidebar.vue'
import PresetEditorDialog from '@/components/presets/PresetEditorDialog.vue'
import ImportExport from '@/components/presets/ImportExport.vue'
import type { PromptPreset, PresetCreate, PresetUpdate, PresetType } from '@/types/preset'
import { updatePreset } from '@/api/presets'
import client from '@/api/client'

const { t } = useI18n()
const store = usePresetStore()

// loading 用 ref（社区库模式下需要本地写入）；预设/总数等只读用 computed
const loading = ref(false)
const presets = computed(() => store.presets)
const total = computed(() => store.total)
const filters = computed(() => store.filters)

const currentType = ref<string>('')
const searchText = ref('')
const sortMode = ref('new')
const currentPage = ref(1)
const isCommunity = ref(false)

// 主视图 Tab：'presets'（预设列表） | 'works'（作品展示）
const viewMode = ref<'presets' | 'works'>('presets')

// 作品展示视图状态
const worksSelectedPresetId = ref<number | null>(null)
const worksType = ref<string>('')
const worksSort = ref<string>('latest')
const worksList = ref<any[]>([])
const worksTotal = ref(0)
const worksPage = ref(1)
const worksPageSize = 24
const worksLoading = ref(false)
// 预设选择器远程搜索
const presetOptions = ref<PromptPreset[]>([])
const presetSearchLoading = ref(false)

// 侧边栏筛选状态
const sidebarFilters = ref({
  categories: [] as string[],
  tags: [] as string[],
  scope: 'all',
})

// 编辑弹窗状态
const dialogVisible = ref(false)
const editingPreset = ref<PromptPreset | null>(null)

// 详情抽屉状态
const detailDrawerVisible = ref(false)
const detailPreset = ref<PromptPreset | null>(null)

// 详情抽屉：作品效果数据
const detailWorks = ref<any[]>([])
const detailWorksTotal = ref(0)
const detailWorksLoading = ref(false)
const detailWorksPage = ref(1)
const detailWorksPageSize = 12

// ================ 数据加载 ================
async function fetchData() {
  const typeVal = currentType.value || undefined
  const categoryVal = sidebarFilters.value.categories.length > 0
    ? sidebarFilters.value.categories
    : undefined

  // 社区库模式：只展示已审核公开预设，绕过 store 直调 API
  if (isCommunity.value) {
    loading.value = true
    try {
      const params: Record<string, any> = {
        sort: sortMode.value,
        offset: (currentPage.value - 1) * 24,
        limit: 24,
      }
      if (typeVal) params.type = typeVal
      if (categoryVal) params.category = categoryVal
      if (searchText.value) params.search = searchText.value
      const res = await client.get('/api/presets', { params })
      // 过滤仅 is_public=true & is_approved=true
      const filtered = (res.data.items || []).filter(
        (item: PromptPreset) => item.is_public && item.is_approved
      )
      store.$patch({ presets: filtered, total: filtered.length })
    } catch (e: any) {
      ElMessage.error(t('presets.center.loadCommunityFailed'))
    } finally {
      loading.value = false
    }
    return
  }

  // 普通模式：复用 store 的 loading 状态
  loading.value = true
  try {
    await store.fetchPresets({
      type: typeVal as PresetType | undefined,
      category: categoryVal,
      search: searchText.value || undefined,
      tags: sidebarFilters.value.tags.length > 0 ? sidebarFilters.value.tags : undefined,
      sort: sortMode.value as any,
      limit: 24,
      offset: (currentPage.value - 1) * 24,
    })
  } finally {
    loading.value = false
  }
}

function onTypeChange() {
  currentPage.value = 1
  fetchData()
}

function onSearch() {
  currentPage.value = 1
  fetchData()
}

function onPageChange(page: number) {
  currentPage.value = page
  fetchData()
}

function onFilterChange(params: { categories: string[]; tags: string[]; scope: string }) {
  sidebarFilters.value = params
  currentPage.value = 1
  fetchData()
}

// ================ 创建 / 编辑 ================
function openCreateDialog() {
  editingPreset.value = null
  dialogVisible.value = true
}

function openEditDialog(preset: PromptPreset) {
  editingPreset.value = preset
  dialogVisible.value = true
}

async function onSubmitPreset(data: PresetCreate | PresetUpdate) {
  try {
    if (editingPreset.value) {
      await store.updatePreset(editingPreset.value.id, data as PresetUpdate)
      ElMessage.success(t('presets.center.updateSuccess'))
    } else {
      await store.createPreset(data as PresetCreate)
      ElMessage.success(t('presets.center.createSuccess'))
    }
  } catch (e: any) {
    ElMessage.error(e?.message || t('presets.center.operateFailed'))
  }
}

// ================ 删除 ================
async function handleDeletePreset(preset: PromptPreset) {
  try {
    await store.deletePreset(preset.id)
    ElMessage.success(t('presets.center.deleteSuccess'))
  } catch (e: any) {
    ElMessage.error(e?.message || t('presets.center.deleteFailed'))
  }
}

// ================ 切换公开/私有 ================
async function handleTogglePublic(preset: PromptPreset) {
  try {
    await updatePreset(preset.id, { is_public: true } as any)
    ElMessage.success(t('presets.center.setPublicSuccess'))
    await fetchData()
  } catch (e: any) {
    ElMessage.error(e?.message || t('presets.center.operateFailed'))
  }
}

// ================ 详情抽屉 ================
function openDetailDrawer(preset: PromptPreset) {
  detailPreset.value = preset
  detailDrawerVisible.value = true
  // 重置作品效果数据并加载
  detailWorks.value = []
  detailWorksTotal.value = 0
  detailWorksPage.value = 1
  loadPresetWorks()
}

// 加载该预设的公开作品（用于抽屉"作品效果" section）
async function loadPresetWorks() {
  if (!detailPreset.value) return
  detailWorksLoading.value = true
  try {
    const res = await client.get(`/api/presets/${detailPreset.value.id}/works`, {
      params: {
        page: detailWorksPage.value,
        page_size: detailWorksPageSize,
      },
    })
    // 返回结构：{ total, page, page_size, items }
    const items = res.data?.items || []
    if (detailWorksPage.value === 1) {
      detailWorks.value = items
    } else {
      detailWorks.value.push(...items)
    }
    detailWorksTotal.value = res.data?.total || 0
  } catch (e: any) {
    // 接口失败时静默处理（不阻塞抽屉打开）
    detailWorks.value = []
    detailWorksTotal.value = 0
  } finally {
    detailWorksLoading.value = false
  }
}

// 加载更多作品
function loadMoreWorks() {
  detailWorksPage.value += 1
  loadPresetWorks()
}

// 点击作品跳转到广场详情
function openWorkDetail(work: any) {
  if (!work?.id) return
  // 在新窗口打开广场作品详情页
  const url = `${window.location.origin}/plaza?work_id=${work.id}`
  window.open(url, '_blank')
}

// 从详情抽屉跳转到编辑
function editFromDetail() {
  if (!detailPreset.value) return
  openEditDialog(detailPreset.value)
  detailDrawerVisible.value = false
}

// 从详情抽屉 Fork（社区库模式）
async function forkFromDetail() {
  if (!detailPreset.value) return
  await handleForkPreset(detailPreset.value)
  detailDrawerVisible.value = false
}

// ================ 使用预设（点击卡片） ================
function onUsePreset(_preset: PromptPreset) {
  // 供嵌入 PresetQuickPanel 等场景复用
}

// ================ 社区库切换 ================
function toggleCommunity() {
  isCommunity.value = !isCommunity.value
  currentPage.value = 1
  if (isCommunity.value) {
    currentType.value = ''
  }
  fetchData()
}

// ================ 主 Tab 切换：预设 / 作品展示 ================
function onMainTabChange(name: string | number) {
  if (name === 'works') {
    // 首次进入作品展示视图：加载预设选项 + 作品列表
    if (presetOptions.value.length === 0) {
      searchPresetsForWorks('')
    }
    if (worksList.value.length === 0) {
      loadWorksList()
    }
  }
}

// 远程搜索预设（用于作品展示视图的预设选择器）
async function searchPresetsForWorks(query: string) {
  presetSearchLoading.value = true
  try {
    const params: Record<string, any> = {
      sort: 'usage',
      limit: 50,
      offset: 0,
    }
    if (query) params.search = query
    const res = await client.get('/api/presets', { params })
    // 只展示公开审核通过的预设（社区可见）
    presetOptions.value = (res.data.items || []).filter(
      (item: PromptPreset) => item.is_public && item.is_approved
    )
  } catch (e) {
    presetOptions.value = []
  } finally {
    presetSearchLoading.value = false
  }
}

// 作品展示视图：加载作品列表
async function loadWorksList() {
  worksLoading.value = true
  try {
    const params: Record<string, any> = {
      sort: worksSort.value,
      page: worksPage.value,
      page_size: worksPageSize,
    }
    if (worksType.value) params.type = worksType.value
    if (worksSelectedPresetId.value) params.preset_id = worksSelectedPresetId.value
    const res = await client.get('/api/plaza/works', { params })
    worksList.value = res.data.items || []
    worksTotal.value = res.data.total || 0
  } catch (e) {
    worksList.value = []
    worksTotal.value = 0
  } finally {
    worksLoading.value = false
  }
}

function onWorksPresetChange() {
  worksPage.value = 1
  loadWorksList()
}

function onWorksFilterChange() {
  worksPage.value = 1
  loadWorksList()
}

function onWorksPageChange(page: number) {
  worksPage.value = page
  loadWorksList()
}

// ================ Fork 预设 ================
async function handleForkPreset(preset: PromptPreset) {
  try {
    const res = await client.post(`/api/presets/${preset.id}/fork`)
    ElMessage.success(t('presets.center.forkSuccess', { name: res.data.name }))
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.message || t('presets.center.forkFailed'))
  }
}

// ================ 工具函数 ================
// 类型显示名（走 i18n）
function typeLabel(type: string): string {
  const keyMap: Record<string, string> = {
    camera: 'presets.card.typeCamera',
    prompt: 'presets.card.typePrompt',
    style: 'presets.card.typeStyle',
    script: 'presets.card.typeScript',
    pipeline: 'presets.card.typePipeline',
  }
  return keyMap[type] ? t(keyMap[type]) : type
}

// 流水线配置 JSON 格式化
function formatPipelineConfig(config: any): string {
  try {
    return typeof config === 'string' ? JSON.stringify(JSON.parse(config), null, 2) : JSON.stringify(config, null, 2)
  } catch {
    return String(config)
  }
}

onMounted(() => {
  fetchData()
})
</script>

<style scoped>
.preset-center {
  padding: 24px;
  max-width: 1400px;
  margin: 0 auto;
}

.page-head {
  margin-bottom: 20px;
}

.page-head h2 {
  font-size: 22px;
  font-weight: 600;
  margin: 0 0 4px;
  color: var(--agnes-text-primary);
}

.muted {
  color: var(--agnes-text-tertiary);
  font-size: 13px;
  margin: 0;
}

.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
  flex-wrap: wrap;
  gap: 12px;
}

.toolbar-right {
  display: flex;
  align-items: center;
}

.content-row {
  display: flex;
  gap: 20px;
  align-items: flex-start;
}

.filter-aside {
  width: 220px;
  flex-shrink: 0;
  position: sticky;
  top: 24px;
}

.filter-card {
  min-height: 300px;
}

.card-main {
  flex: 1;
  min-width: 0;
}

.list-card {
  min-height: 400px;
}

.card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 16px;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 80px 0;
  gap: 16px;
}

.empty-text {
  font-size: 14px;
  color: var(--agnes-text-tertiary);
  margin: 0;
}

.pagination-wrap {
  display: flex;
  justify-content: flex-end;
  margin-top: 20px;
}

/* ====== 详情抽屉样式 ====== */
.detail-content {
  padding: 0 4px;
}

.detail-section {
  margin-bottom: 24px;
}

.detail-section-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--agnes-text-primary);
  margin: 0 0 12px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--agnes-border-faint);
}

.detail-row {
  display: flex;
  align-items: flex-start;
  margin-bottom: 10px;
  font-size: 13px;
}

.detail-label {
  flex-shrink: 0;
  width: 80px;
  color: var(--agnes-text-tertiary);
}

.detail-value {
  flex: 1;
  color: var(--agnes-text-primary);
  word-break: break-word;
}

.detail-tags {
  flex: 1;
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.detail-pre {
  background: var(--agnes-bg-elevated);
  border: 1px solid var(--agnes-border-faint);
  border-radius: 4px;
  padding: 12px;
  font-size: 12px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  color: var(--agnes-text-primary);
  white-space: pre-wrap;
  word-break: break-word;
  margin: 0;
  max-height: 320px;
  overflow-y: auto;
}

.detail-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

/* ====== 作品效果 section 样式 ====== */
.works-count {
  font-size: 12px;
  color: var(--agnes-text-tertiary);
  font-weight: 400;
  margin-left: 6px;
}

.works-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
}

.work-item {
  position: relative;
  aspect-ratio: 1 / 1;
  border-radius: 6px;
  overflow: hidden;
  background: var(--agnes-bg-elevated);
  cursor: pointer;
  border: 1px solid var(--agnes-border-faint);
  transition: transform 0.2s ease;
}

.work-item:hover {
  transform: translateY(-2px);
  border-color: var(--agnes-primary);
}

.work-item img,
.work-item video {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.work-type-badge {
  position: absolute;
  top: 4px;
  right: 4px;
  background: rgba(0, 0, 0, 0.6);
  color: #fff;
  font-size: 10px;
  padding: 2px 6px;
  border-radius: 3px;
  pointer-events: none;
}

.work-meta {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  background: linear-gradient(transparent, rgba(0, 0, 0, 0.7));
  color: #fff;
  font-size: 11px;
  padding: 12px 6px 4px;
  display: flex;
  justify-content: space-between;
  pointer-events: none;
}

.works-empty {
  font-size: 13px;
  color: var(--agnes-text-tertiary);
  text-align: center;
  padding: 24px 0;
  margin: 0;
}

.works-more {
  text-align: center;
  margin-top: 12px;
}

/* ====== 主 Tab 样式 ====== */
.main-tabs {
  margin-bottom: 16px;
}

.main-tabs :deep(.el-tabs__header) {
  margin-bottom: 0;
}

/* ====== 作品展示视图样式 ====== */
.works-view {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.works-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.works-list-card {
  min-height: 400px;
}

.works-big-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 16px;
}

.work-big-item {
  position: relative;
  aspect-ratio: 1 / 1;
  border-radius: 8px;
  overflow: hidden;
  background: var(--agnes-bg-elevated);
  cursor: pointer;
  border: 1px solid var(--agnes-border-faint);
  transition: transform 0.2s ease, box-shadow 0.2s ease;
}

.work-big-item:hover {
  transform: translateY(-3px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
  border-color: var(--agnes-primary);
}

.work-big-item img,
.work-big-item video {
  width: 100%;
  height: calc(100% - 36px);
  object-fit: cover;
  display: block;
}

.work-big-meta {
  height: 36px;
  padding: 6px 10px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 12px;
  color: var(--agnes-text-secondary);
  background: var(--agnes-bg-elevated);
}

.work-big-author {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}

.work-big-author span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.work-big-stats {
  display: flex;
  gap: 8px;
  color: var(--agnes-text-tertiary);
  flex-shrink: 0;
}
</style>
