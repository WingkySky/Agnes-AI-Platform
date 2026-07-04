<!-- =====================================================
     创意工坊视图 WorkshopView
     - 模板市场 + 我的模板（Tab 切换）
     - 支持搜索和筛选
     - 点击模板跳转到 /projects 进入项目创建向导（L1：模板已改为向导模板）
     - 我的模板支持提交审核/取消公开/编辑/删除
     - 注意：旧的 PipelineRun 流程已废弃，运行历史已移除（K1）
     ===================================================== -->

<template>
  <div class="workshop-view">
    <!-- 头部：标题 + 描述 -->
    <h2 class="page-title">{{ t('workshop.title') }}</h2>
    <p class="page-desc">{{ t('workshop.desc') }}</p>

    <!-- Tab 切换：模板市场 / 我的模板 -->
    <div v-if="isLoggedIn" class="tab-switcher">
      <button
        class="tab-btn"
        :class="{ active: activeTab === 'market' }"
        @click="onTabChange('market')">
        {{ t('workshop.templateMarket') }}
      </button>
      <button
        class="tab-btn"
        :class="{ active: activeTab === 'my' }"
        @click="onTabChange('my')">
        {{ t('workshop.myTemplates') }}
      </button>
    </div>

    <!-- 搜索和筛选区 -->
    <div class="filter-bar">
      <el-input
        v-model="searchKeyword"
        :placeholder="t('workshop.searchPlaceholder')"
        class="search-input"
        clearable
        @input="onSearch">
        <template #prefix>
          <el-icon><Search /></el-icon>
        </template>
      </el-input>
      <el-radio-group v-model="activeCategory" class="category-tabs" @change="onCategoryChange">
        <el-radio-button value="all">{{ t('workshop.allTemplates') }}</el-radio-button>
        <el-radio-button
          v-for="cat in displayCategories"
          :key="cat"
          :value="cat">
          {{ t(`workshop.category.${cat}`) }}
        </el-radio-button>
      </el-radio-group>
      <!-- 模板导入/导出按钮 -->
      <div class="filter-actions">
        <el-button v-permission="'pipeline:run'" link size="small" @click="openImportDialog">
          <el-icon><Upload /></el-icon>
          {{ t('workshop.importExport.importButton') }}
        </el-button>
        <el-button v-permission="'pipeline:run'" link size="small" @click="openExportDialog">
          <el-icon><Download /></el-icon>
          {{ t('workshop.importExport.exportButton') }}
        </el-button>
      </div>
    </div>

    <!-- 模板网格 -->
    <div v-loading="currentLoading" class="templates-section">
      <div class="section-header">
        <h3 class="section-title">
          {{ activeTab === 'market' ? t('workshop.templateMarket') : t('workshop.myTemplates') }}
        </h3>
        <div class="section-actions">
          <!-- 快速创建按钮：打开场景化向导 -->
          <el-button
            v-if="isLoggedIn"
            type="primary"
            link
            size="small"
            @click="goToWizard">
            <el-icon><MagicStick /></el-icon>
            {{ t('workshop.quickCreate') }}
          </el-button>
          <el-button
            v-if="activeTab === 'my' && isLoggedIn"
            type="primary" link size="small" @click="goToCreateTemplate">
            <el-icon><Plus /></el-icon>
            {{ t('workshop.createTemplate') }}
          </el-button>
          <el-button
            v-if="activeTab === 'my' && isLoggedIn"
            link size="small" @click="refreshMyTemplates">
            <el-icon><Refresh /></el-icon>
            {{ t('common.refresh') }}
          </el-button>
        </div>
      </div>

      <!-- 空状态 -->
      <div v-if="!currentLoading && filteredTemplates.length === 0" class="empty-state">
        <el-icon :size="48"><MagicStick /></el-icon>
        <p class="empty-text">
          {{ activeTab === 'my' ? t('workshop.noMyTemplates') : t('workshop.noTemplates') }}
        </p>
        <el-button
          v-if="activeTab === 'my'"
          type="primary" size="small" @click="goToCreateTemplate">
          {{ t('workshop.createTemplate') }}
        </el-button>
      </div>

      <!-- 模板卡片网格 -->
      <div v-else class="template-grid">
        <div
          v-for="tpl in filteredTemplates"
          :key="tpl.id"
          class="template-card"
          @click="onCardClick(tpl)">
          <div class="card-thumb">
            <img v-if="tpl.thumbnail" :src="tpl.thumbnail" :alt="tpl.name" />
            <div v-else class="thumb-placeholder">
              <el-icon :size="40"><MagicStick /></el-icon>
            </div>
            <div v-if="tpl.is_builtin" class="badge-builtin">{{ t('workshop.builtin') }}</div>
            <!-- 审核状态标签：仅我的模板显示 -->
            <div v-if="activeTab === 'my'" class="badge-status" :class="`badge-${getTemplateStatus(tpl)}`">
              {{ t(`workshop.status.${getTemplateStatus(tpl)}`) }}
            </div>
            <!-- 修订中徽章：has_pending_revision 为 true 时显示 -->
            <div v-if="tpl.has_pending_revision" class="badge-revising">
              {{ t('workshop.revising') }}
            </div>
          </div>
          <div class="card-body">
            <h4 class="card-title">{{ tpl.name }}</h4>
            <p class="card-desc">{{ tpl.description }}</p>
            <div class="card-meta">
              <span class="meta-item">
                <el-icon><Coin /></el-icon>
                ~{{ tpl.estimated_credits }} {{ t('workshop.credits') }}
              </span>
              <span class="meta-item">
                <el-icon><Clock /></el-icon>
                {{ tpl.estimated_time }}
              </span>
            </div>
            <div v-if="tpl.tags && tpl.tags.length > 0" class="card-tags">
              <el-tag
                v-for="tag in tpl.tags.slice(0, 3)"
                :key="tag"
                size="small"
                type="info"
                effect="plain">
                {{ tag }}
              </el-tag>
            </div>
            <!-- 卡片底部操作按钮 -->
            <div class="card-footer">
              <el-button
                v-if="activeTab === 'market'"
                v-permission="'pipeline:run'"
                type="primary"
                link
                size="small"
                @click.stop="goToProjectsWithTemplate(tpl)">
                {{ t('workshop.useTemplate') }}
              </el-button>
              <!-- 市场模板：改进模板按钮（仅登录用户可见） -->
              <el-button
                v-if="activeTab === 'market' && isLoggedIn && !tpl.is_builtin"
                link
                size="small"
                @click.stop="goToImprove(tpl)">
                <el-icon><Edit /></el-icon>
                {{ t('workshop.improveTemplate') }}
              </el-button>
              <!-- 我的模板：操作菜单 -->
              <template v-if="activeTab === 'my'">
                <el-button
                  v-permission="'pipeline:run'"
                  type="primary"
                  link
                  size="small"
                  @click.stop="goToProjectsWithTemplate(tpl)">
                  {{ t('workshop.useTemplate') }}
                </el-button>
                <el-dropdown
                  trigger="click"
                  @command="(cmd: string) => onCardCommand(cmd, tpl)"
                  @click.stop>
                  <el-button link size="small" @click.stop>
                    <el-icon><MoreFilled /></el-icon>
                  </el-button>
                  <template #dropdown>
                    <el-dropdown-menu>
                      <el-dropdown-item command="edit" v-if="!tpl.is_builtin">
                        <el-icon><Edit /></el-icon>
                        {{ t('workshop.editTemplate') }}
                      </el-dropdown-item>
                      <el-dropdown-item
                        command="submit-public"
                        v-if="!tpl.is_builtin && canSubmitPublic(tpl)">
                        <el-icon><UploadFilled /></el-icon>
                        {{ t('workshop.submitPublic') }}
                      </el-dropdown-item>
                      <el-dropdown-item
                        command="cancel-public"
                        v-if="!tpl.is_builtin && (tpl.is_public || tpl.is_approved)">
                        <el-icon><RemoveFilled /></el-icon>
                        {{ t('workshop.cancelPublic') }}
                      </el-dropdown-item>
                      <el-dropdown-item command="export">
                        <el-icon><Download /></el-icon>
                        {{ t('workshop.importExport.exportThis') }}
                      </el-dropdown-item>
                      <el-dropdown-item
                        command="delete"
                        v-if="!tpl.is_builtin"
                        divided>
                        <el-icon><Delete /></el-icon>
                        {{ t('workshop.deleteTemplate') }}
                      </el-dropdown-item>
                    </el-dropdown-menu>
                  </template>
                </el-dropdown>
              </template>
              <!-- 市场里的非内置模板（公开模板）：导出按钮 -->
              <el-dropdown
                v-if="activeTab === 'market' && !tpl.is_builtin"
                trigger="click"
                @command="(cmd: string) => onCardCommand(cmd, tpl)"
                @click.stop>
                <el-button link size="small" @click.stop>
                  <el-icon><MoreFilled /></el-icon>
                </el-button>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item command="export">
                      <el-icon><Download /></el-icon>
                      {{ t('workshop.importExport.exportThis') }}
                    </el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 模板导入/导出对话框 -->
    <TemplateImportExportDialog
      v-model="ioDialogVisible"
      :preset-template-ids="presetExportIds"
      :initial-tab="ioDialogTab"
      @imported="onImported"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useI18n } from '@/i18n'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Search, MagicStick, Coin, Clock, Refresh, Delete, Plus,
  Upload, Download, MoreFilled, Edit, UploadFilled, RemoveFilled,
} from '@element-plus/icons-vue'
import { usePipelineStore } from '@/stores/pipeline'
import { useUserStore } from '@/stores/user'
import type { PipelineTemplate } from '@/api/pipeline'
import { submitTemplatePublic, cancelTemplatePublic, deleteTemplate } from '@/api/pipeline'
import TemplateImportExportDialog from '@/components/pipeline/TemplateImportExportDialog.vue'

const { t } = useI18n()
const router = useRouter()
const pipelineStore = usePipelineStore()
const userStore = useUserStore()

// ---------- 状态 ----------
const activeTab = ref<'market' | 'my'>('market')
const searchKeyword = ref('')
const activeCategory = ref('all')
const isLoggedIn = computed(() => userStore.isAuthenticated)

// ---------- 模板导入/导出 ----------
const ioDialogVisible = ref(false)
const ioDialogTab = ref<'export' | 'import'>('export')
const presetExportIds = ref<number[]>([])

function openExportDialog() {
  presetExportIds.value = []
  ioDialogTab.value = 'export'
  ioDialogVisible.value = true
}

function openImportDialog() {
  presetExportIds.value = []
  ioDialogTab.value = 'import'
  ioDialogVisible.value = true
}

// ---------- Tab 切换 ----------
function onTabChange(tab: string) {
  activeTab.value = tab as 'market' | 'my'
  activeCategory.value = 'all'
  searchKeyword.value = ''
  if (tab === 'my' && !pipelineStore.myTemplatesLoaded) {
    pipelineStore.loadMyTemplates()
  }
}

function onCategoryChange() {
  // 分类切换是前端过滤
}

function onSearch() {
  // 搜索是前端过滤
}

function onCardClick(tpl: PipelineTemplate) {
  goToProjectsWithTemplate(tpl)
}

function refreshMyTemplates() {
  pipelineStore.refreshMyTemplates()
}

// ---------- 计算属性 ----------
const templatesLoading = computed(() => pipelineStore.templatesLoading)

const currentLoading = computed(() => {
  return activeTab.value === 'market' ? templatesLoading.value : pipelineStore.myTemplatesLoading
})

const currentTemplates = computed(() => {
  return activeTab.value === 'market' ? pipelineStore.templates : pipelineStore.myTemplates
})

const displayCategories = computed(() => {
  const cats = new Set<string>()
  currentTemplates.value.forEach(tpl => {
    if (tpl.category) cats.add(tpl.category)
  })
  return Array.from(cats)
})

const filteredTemplates = computed(() => {
  let list = currentTemplates.value
  if (activeCategory.value !== 'all') {
    list = list.filter(t => t.category === activeCategory.value)
  }
  if (searchKeyword.value.trim()) {
    const kw = searchKeyword.value.toLowerCase()
    list = list.filter(t =>
      t.name.toLowerCase().includes(kw) ||
      t.description.toLowerCase().includes(kw) ||
      t.tags?.some((tag: string) => tag.toLowerCase().includes(kw))
    )
  }
  return list
})

// ---------- 模板状态辅助函数 ----------
function getTemplateStatus(tpl: PipelineTemplate): 'private' | 'pending' | 'approved' | 'rejected' | 'builtin' {
  if (tpl.is_builtin) return 'builtin'
  if (tpl.is_rejected) return 'rejected'
  if (tpl.is_public && tpl.is_approved) return 'approved'
  if (tpl.is_public && !tpl.is_approved) return 'pending'
  return 'private'
}

function canSubmitPublic(tpl: PipelineTemplate): boolean {
  if (tpl.is_builtin) return false
  if (tpl.is_rejected) return false
  if (tpl.is_public && tpl.is_approved) return false
  return true
}

// ---------- 卡片操作 ----------
async function onCardCommand(cmd: string, tpl: PipelineTemplate) {
  if (cmd === 'export') {
    presetExportIds.value = [tpl.id]
    ioDialogTab.value = 'export'
    ioDialogVisible.value = true
  } else if (cmd === 'edit') {
    router.push(`/workshop/template/${tpl.id}/edit`)
  } else if (cmd === 'submit-public') {
    await handleSubmitPublic(tpl)
  } else if (cmd === 'cancel-public') {
    await handleCancelPublic(tpl)
  } else if (cmd === 'delete') {
    await handleDeleteTemplate(tpl)
  }
}

async function handleSubmitPublic(tpl: PipelineTemplate) {
  try {
    const { value } = await ElMessageBox.prompt(
      t('workshop.submitPublicTip'),
      t('workshop.submitPublic'),
      {
        confirmButtonText: t('common.submit'),
        cancelButtonText: t('common.cancel'),
        inputPlaceholder: t('workshop.submitPublicPlaceholder'),
        inputType: 'textarea',
        inputValidator: (val) => val != null && val.trim().length <= 500 || t('workshop.submitPublicReasonTooLong'),
        type: 'info',
      }
    )
    const res = await submitTemplatePublic(tpl.id, (value || '').trim())
    if (res.rejected) {
      ElMessage.warning(t('workshop.submitPublicRejected', { words: res.hit_words?.slice(0, 3).join(', ') || '' }))
    } else {
      ElMessage.success(t('workshop.submitPublicSuccess'))
    }
    await pipelineStore.refreshMyTemplates()
  } catch (e: any) {
    if (e !== 'cancel') {
      ElMessage.error(e?.message || t('workshop.submitPublicFailed'))
    }
  }
}

async function handleCancelPublic(tpl: PipelineTemplate) {
  try {
    await ElMessageBox.confirm(
      t('workshop.cancelPublicConfirm'),
      t('workshop.cancelPublic'),
      { confirmButtonText: t('common.confirm'), cancelButtonText: t('common.cancel'), type: 'warning' }
    )
    await cancelTemplatePublic(tpl.id)
    ElMessage.success(t('workshop.cancelPublicSuccess'))
    await pipelineStore.refreshMyTemplates()
  } catch (e: any) {
    if (e !== 'cancel') {
      ElMessage.error(e?.message || t('workshop.cancelPublicFailed'))
    }
  }
}

async function handleDeleteTemplate(tpl: PipelineTemplate) {
  try {
    await ElMessageBox.confirm(
      t('workshop.deleteTemplateConfirm', { name: tpl.name }),
      t('workshop.deleteTemplate'),
      { confirmButtonText: t('common.delete'), cancelButtonText: t('common.cancel'), type: 'warning' }
    )
    await deleteTemplate(tpl.id)
    ElMessage.success(t('workshop.deleteSuccess'))
    await pipelineStore.refreshMyTemplates()
  } catch (e: any) {
    if (e !== 'cancel') {
      ElMessage.error(e?.message || t('workshop.deleteFailed'))
    }
  }
}

function onImported() {
  // 导入成功后刷新两个列表
  loadTemplates()
  if (isLoggedIn.value) {
    pipelineStore.refreshMyTemplates()
  }
}

// ---------- 方法 ----------
async function loadTemplates() {
  try {
    await pipelineStore.loadTemplates()
  } catch (e: any) {
    ElMessage.error(e?.message || t('workshop.loadTemplatesFailed'))
  }
}

/**
 * 跳转到项目列表页，并带上 template_id 参数
 * ProjectListView 接收后自动打开创建对话框
 */
function goToProjectsWithTemplate(tpl: PipelineTemplate) {
  router.push({ path: '/projects', query: { template_id: tpl.id, category: tpl.category } })
}

function goToCreateTemplate() {
  router.push('/workshop/template/create')
}

function goToWizard() {
  router.push('/workshop/wizard')
}

function goToImprove(tpl: PipelineTemplate) {
  router.push(`/workshop/template/${tpl.id}/edit`)
}

// ---------- 生命周期 ----------
onMounted(() => {
  // 模板列表只在未加载时拉取，避免重复请求
  if (!pipelineStore.templatesLoaded) {
    loadTemplates()
  }
})
</script>

<style scoped>
.workshop-view {
  padding: 24px 32px;
  max-width: 1280px;
  margin: 0 auto;
}

/* page-title / page-desc / section-title 沿用全局工具类（main.css），不再重复定义 */

/* Tab 切换按钮组 */
.tab-switcher {
  display: inline-flex;
  gap: 4px;
  margin-bottom: 20px;
  background: var(--el-fill-color-light);
  padding: 4px;
  border-radius: 8px;
}
.tab-btn {
  padding: 8px 24px;
  font-size: 14px;
  font-weight: 500;
  border: none;
  background: transparent;
  color: var(--el-text-color-regular);
  cursor: pointer;
  border-radius: 6px;
  transition: all 0.2s;
}
.tab-btn:hover {
  color: var(--el-color-primary);
}
.tab-btn.active {
  background: var(--el-color-primary);
  color: #fff;
  font-weight: 600;
}

.filter-bar {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 24px;
  flex-wrap: wrap;
}

.search-input {
  width: 280px;
}

.category-tabs {
  flex: 1;
}

.filter-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}

.card-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 8px;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

/* 标题旁的操作按钮统一为 link 风格，避免抢卡片视觉焦点 */
.section-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.templates-section {
  margin-bottom: 40px;
}

.template-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 20px;
}

.template-card {
  background: var(--agnes-bg-card);
  border: 1px solid var(--agnes-border);
  border-radius: 12px;
  overflow: hidden;
  cursor: pointer;
  transition: all 0.2s ease;
}

.template-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.1);
  border-color: var(--agnes-primary-border);
}

.card-thumb {
  position: relative;
  width: 100%;
  height: 160px;
  background: var(--agnes-bg-page);
  overflow: hidden;
}

.card-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.thumb-placeholder {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--agnes-text-placeholder);
}

.badge-builtin {
  position: absolute;
  top: 10px;
  left: 10px;
  background: var(--agnes-primary);
  color: #fff;
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 4px;
  font-weight: 500;
}

/* 模板审核状态标签（右上角） */
.badge-status {
  position: absolute;
  top: 10px;
  right: 10px;
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 4px;
  font-weight: 500;
}

.badge-private {
  background: var(--agnes-bg-tertiary);
  color: var(--agnes-text-secondary);
}

.badge-pending {
  background: #e6a23c20;
  color: var(--agnes-warning, #e6a23c);
}

.badge-approved {
  background: var(--agnes-success-light, #f0f9eb);
  color: var(--agnes-success, #67c23a);
}

.badge-rejected {
  background: #f56c6c20;
  color: var(--agnes-danger, #f56c6c);
}

.badge-builtin {
  background: var(--agnes-primary);
  color: #fff;
}

/* "修订中"徽章：放在缩略图左下角，使用 warning 色 */
.badge-revising {
  position: absolute;
  bottom: 10px;
  left: 10px;
  background: #e6a23c;
  color: #fff;
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 4px;
  font-weight: 500;
}

.card-body {
  padding: 16px;
}

.card-title {
  font-size: 16px;
  font-weight: 600;
  margin: 0 0 8px 0;
  color: var(--agnes-text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.card-desc {
  font-size: 13px;
  color: var(--agnes-text-secondary);
  margin: 0 0 12px 0;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  min-height: 38px;
}

.card-meta {
  display: flex;
  gap: 16px;
  margin-bottom: 12px;
}

.meta-item {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: var(--agnes-text-secondary);
}

.card-tags {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  margin-bottom: 12px;
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
</style>
