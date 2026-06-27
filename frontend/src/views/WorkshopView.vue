<!-- =====================================================
     创意工坊视图 WorkshopView
     - 展示流水线模板列表，按分类分组
     - 支持搜索和筛选
     - 点击模板进入配置运行页面
     - 展示我的运行历史记录（运行中/已完成）
     ===================================================== -->

<template>
  <div class="workshop-view">
    <!-- 头部：标题 + 描述 -->
    <h2 class="page-title">{{ t('workshop.title') }}</h2>
    <p class="page-desc">{{ t('workshop.desc') }}</p>

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
      <el-radio-group v-model="activeCategory" class="category-tabs" @change="loadTemplates">
        <el-radio-button value="all">{{ t('workshop.allTemplates') }}</el-radio-button>
        <el-radio-button
          v-for="cat in categories"
          :key="cat"
          :value="cat">
          {{ t(`workshop.category.${cat}`) }}
        </el-radio-button>
      </el-radio-group>
    </div>

    <!-- 模板网格 -->
    <div v-loading="templatesLoading" class="templates-section">
      <div class="section-header">
        <h3 class="section-title">{{ t('workshop.templateMarket') }}</h3>
        <div class="section-actions">
          <el-button type="primary" size="small" @click="goToHistory">
            <el-icon><PictureFilled /></el-icon>
            {{ t('workshop.creationHistory') }}
          </el-button>
          <el-button type="primary" size="small" @click="goToCreateTemplate">
            <el-icon><Plus /></el-icon>
            {{ t('workshop.createTemplate') }}
          </el-button>
        </div>
      </div>

      <!-- 空状态 -->
      <div v-if="!templatesLoading && filteredTemplates.length === 0" class="empty-state">
        <el-icon :size="48"><MagicStick /></el-icon>
        <p class="empty-text">{{ t('workshop.noTemplates') }}</p>
      </div>

      <!-- 模板卡片网格 -->
      <div v-else class="template-grid">
        <div
          v-for="tpl in filteredTemplates"
          :key="tpl.id"
          class="template-card"
          @click="goToRun(tpl)">
          <div class="card-thumb">
            <img v-if="tpl.thumbnail" :src="tpl.thumbnail" :alt="tpl.name" />
            <div v-else class="thumb-placeholder">
              <el-icon :size="40"><MagicStick /></el-icon>
            </div>
            <div v-if="tpl.is_builtin" class="badge-builtin">{{ t('workshop.builtin') }}</div>
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
            <!-- 使用此模板按钮（受 pipeline:run 权限控制） -->
            <div class="card-footer">
              <el-button
                v-permission="'pipeline:run'"
                type="primary"
                size="small"
                @click.stop="goToRun(tpl)">
                {{ t('workshop.useTemplate') }}
              </el-button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 我的流水线历史 -->
    <div v-loading="runHistoryLoading" class="history-section">
      <div class="section-header">
        <h3 class="section-title">{{ t('workshop.myRuns') }}</h3>
        <el-button type="primary" link @click="loadRunHistory">
          <el-icon><Refresh /></el-icon>
          {{ t('workshop.refresh') }}
        </el-button>
      </div>

      <!-- 空状态 -->
      <div v-if="!runHistoryLoading && runHistory.length === 0" class="empty-state small">
        <el-icon :size="36"><Clock /></el-icon>
        <p class="empty-text">{{ t('workshop.noRuns') }}</p>
      </div>

      <!-- 历史列表 -->
      <div v-else class="run-list">
        <div
          v-for="run in runHistory"
          :key="run.id"
          class="run-item"
          @click="goToResult(run)">
          <div class="run-status">
            <el-tag :type="getStatusType(run.status)" size="small">
              {{ t(`common.status.${run.status}`) }}
            </el-tag>
          </div>
          <div class="run-info">
            <div class="run-name">{{ run.name || run.template_name }}</div>
            <div class="run-meta">
              <span>{{ run.template_name }}</span>
              <span>·</span>
              <span>{{ formatTime(run.created_at) }}</span>
            </div>
          </div>
          <div class="run-progress">
            <el-progress
              :percentage="run.progress || 0"
              :stroke-width="6"
              :show-text="false" />
          </div>
          <div class="run-action">
            <el-button
              type="danger"
              link
              size="small"
              @click.stop="deleteRunConfirm(run)">
              <el-icon><Delete /></el-icon>
            </el-button>
            <el-icon class="go-icon"><ArrowRight /></el-icon>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useI18n } from '@/i18n'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Search, MagicStick, Coin, Clock, Refresh, ArrowRight, Delete, Plus, PictureFilled
} from '@element-plus/icons-vue'
import { usePipelineStore } from '@/stores/pipeline'
import type { PipelineTemplate, PipelineRun } from '@/api/pipeline'

const { t } = useI18n()
const router = useRouter()
const pipelineStore = usePipelineStore()

// ---------- 状态 ----------
const searchKeyword = ref('')
const activeCategory = ref('all')

// ---------- 计算属性 ----------
const templatesLoading = computed(() => pipelineStore.templatesLoading)
const runHistoryLoading = computed(() => pipelineStore.runHistoryLoading)
const runHistory = computed(() => pipelineStore.runHistory)

const templates = computed(() => pipelineStore.templates)

const categories = computed(() => {
  const cats = new Set<string>()
  templates.value.forEach(tpl => {
    if (tpl.category) cats.add(tpl.category)
  })
  return Array.from(cats)
})

const filteredTemplates = computed(() => {
  let list = templates.value
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

// ---------- 方法 ----------
function onSearch() {
  // 搜索是前端过滤，不需要重新加载
}

async function loadTemplates() {
  try {
    await pipelineStore.loadTemplates()
  } catch (e: any) {
    ElMessage.error(e?.message || t('workshop.loadTemplatesFailed'))
  }
}

async function loadRunHistory() {
  try {
    await pipelineStore.loadRunHistory()
  } catch (e: any) {
    ElMessage.error(e?.message || t('workshop.loadRunsFailed'))
  }
}

function goToRun(tpl: PipelineTemplate) {
  router.push(`/workshop/run/${tpl.id}`)
}

function goToResult(run: PipelineRun) {
  router.push(`/workshop/result/${run.id}`)
}

function goToCreateTemplate() {
  router.push('/workshop/template/create')
}

function goToHistory() {
  router.push('/workshop/history')
}

async function deleteRunConfirm(run: PipelineRun) {
  try {
    await ElMessageBox.confirm(
      `确定要删除运行记录「${run.name || run.template_name}」吗？此操作不可恢复。`,
      t('workshop.deleteRun'),
      { confirmButtonText: t('common.delete'), cancelButtonText: t('common.cancel'), type: 'warning' }
    )
    await pipelineStore.deleteRun(run.id)
    ElMessage.success(t('workshop.deleteSuccess'))
  } catch (e: any) {
    if (e !== 'cancel') {
      ElMessage.error(e?.message || t('workshop.deleteFailed'))
    }
  }
}

function getStatusType(status: string): 'success' | 'warning' | 'danger' | 'info' | 'primary' {
  switch (status) {
    case 'success': return 'success'
    case 'running': return 'primary'
    case 'pending': return 'warning'
    case 'failed': return 'danger'
    default: return 'info'
  }
}

function formatTime(timeStr: string): string {
  if (!timeStr) return ''
  const date = new Date(timeStr)
  const now = new Date()
  const diff = now.getTime() - date.getTime()
  if (diff < 60000) return '刚刚'
  if (diff < 3600000) return `${Math.floor(diff / 60000)} 分钟前`
  if (diff < 86400000) return `${Math.floor(diff / 3600000)} 小时前`
  return date.toLocaleDateString('zh-CN')
}

// ---------- 生命周期 ----------
onMounted(() => {
  // 模板列表只在未加载时拉取，避免重复请求
  if (!pipelineStore.templatesLoaded) {
    loadTemplates()
  }
  loadRunHistory()
})
</script>

<style scoped>
.workshop-view {
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

.section-title {
  font-size: 18px;
  font-weight: 600;
  margin: 0;
  color: var(--agnes-text-primary);
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
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

.card-footer {
  display: flex;
  justify-content: flex-end;
}

.history-section {
  margin-top: 32px;
}

.run-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.run-item {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 16px 20px;
  background: var(--agnes-bg-card);
  border: 1px solid var(--agnes-border);
  border-radius: 10px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.run-item:hover {
  border-color: var(--agnes-primary-border);
  background: var(--agnes-primary-light-9, rgba(64, 158, 255, 0.1));
}

.run-status {
  flex-shrink: 0;
}

.run-info {
  flex: 1;
  min-width: 0;
}

.run-name {
  font-size: 15px;
  font-weight: 500;
  color: var(--agnes-text-primary);
  margin-bottom: 4px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.run-meta {
  font-size: 12px;
  color: var(--agnes-text-secondary);
  display: flex;
  gap: 8px;
}

.run-progress {
  width: 120px;
  flex-shrink: 0;
}

.run-action {
  color: var(--agnes-text-placeholder);
  flex-shrink: 0;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 20px;
  color: var(--agnes-text-placeholder);
}

.empty-state.small {
  padding: 40px 20px;
}

.empty-text {
  margin-top: 12px;
  font-size: 14px;
}
</style>
