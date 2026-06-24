<!-- =====================================================
     内容审核页
     - 展示待审核的广场作品列表
     - 支持通过 / 驳回 / 批量操作
     ===================================================== -->

<template>
  <div class="moderation-wrap">
    <header class="page-head">
      <div>
        <h2>{{ t('admin.moderation.title') }}</h2>
        <p class="muted">{{ t('admin.moderation.desc') }}</p>
      </div>
      <el-button :icon="Refresh" @click="fetchList" :loading="loading">{{ t('common.refresh') }}</el-button>
    </header>

    <!-- 状态 Tab 切换 -->
    <el-tabs v-model="filterStatus" class="status-tabs" @tab-change="onStatusTabChange">
      <el-tab-pane :label="t('admin.moderation.tabPending')" name="pending" />
      <el-tab-pane :label="t('admin.moderation.tabApproved')" name="approved" />
      <el-tab-pane :label="t('admin.moderation.tabRejected')" name="rejected" />
      <el-tab-pane :label="t('admin.moderation.tabAll')" name="all" />
    </el-tabs>

    <el-card class="filter-card" shadow="never">
      <!-- 待审核 Tab 下的一键审核快捷操作 -->
      <div v-if="filterStatus === 'pending'" class="quick-actions">
        <span class="quick-label">
          <el-icon size="14" color="#e6a23c"><Warning /></el-icon>
          {{ t('admin.moderation.pendingTip', { count: total }) }}
        </span>
        <el-button type="success" size="small" @click="onQuickApproveAll" :disabled="total === 0 || loading">
          <el-icon><Check /></el-icon>
          {{ t('admin.moderation.quickApprove') }}
        </el-button>
        <el-button type="danger" size="small" @click="onQuickRejectAll" :disabled="total === 0 || loading">
          <el-icon><Close /></el-icon>
          {{ t('admin.moderation.quickReject') }}
        </el-button>
      </div>

      <div class="filter-row">
        <el-select v-model="filterType" :placeholder="t('admin.moderation.filterAll')" style="width: 100px" @change="onFilterChange">
          <el-option :label="t('admin.moderation.filterAll')" value="" />
          <el-option :label="t('admin.moderation.filterImage')" value="image" />
          <el-option :label="t('admin.moderation.filterVideo')" value="video" />
        </el-select>

        <el-input
          v-model="searchWorkId"
          :placeholder="t('admin.moderation.contentId')"
          style="width: 110px"
          clearable
          @keyup.enter="onSearch"
          @clear="onSearch"
        />

        <el-input
          v-model="searchUsername"
          :placeholder="t('admin.moderation.creator')"
          style="width: 140px"
          clearable
          @keyup.enter="onSearch"
          @clear="onSearch"
        />

        <el-input
          v-model="keyword"
          :placeholder="t('admin.moderation.searchPrompt')"
          style="width: 220px"
          clearable
          @keyup.enter="onSearch"
          @clear="onSearch"
        >
          <template #prefix>
            <el-icon><Search /></el-icon>
          </template>
        </el-input>

        <el-button type="primary" @click="onSearch">{{ t('common.search') }}</el-button>
      </div>

      <div v-if="selectedIds.length > 0" class="batch-bar">
        <span class="batch-tip">{{ t('admin.moderation.selected', { count: selectedIds.length }) }}</span>
        <el-button type="success" size="small" @click="onBatchApprove">{{ t('admin.moderation.batchApprove') }}</el-button>
        <el-button type="danger" size="small" @click="onBatchReject">{{ t('admin.moderation.batchReject') }}</el-button>
        <el-button size="small" @click="clearSelection">{{ t('admin.moderation.clearSelection') }}</el-button>
      </div>
    </el-card>

    <el-card class="table-card" shadow="never">
      <el-table
        :data="list"
        style="width: 100%"
        stripe
        v-loading="loading"
        @selection-change="onSelectionChange"
      >
        <el-table-column type="selection" width="50" align="center" />
        <el-table-column prop="id" :label="t('admin.moderation.id')" width="70" align="center" />
        <el-table-column :label="t('admin.moderation.preview')" width="100" align="center">
          <template #default="{ row }">
            <div class="preview-cell" @click="openPreview(row)">
              <el-image
                v-if="row.type === 'image'"
                :src="row.result_url"
                :preview-src-list="[row.result_url]"
                fit="cover"
                style="width: 60px; height: 60px; border-radius: 6px; cursor: pointer"
                :initial-index="0"
              />
              <div v-else class="video-preview">
                <el-image
                  :src="row.result_url"
                  fit="cover"
                  style="width: 60px; height: 60px; border-radius: 6px"
                />
                <el-icon class="play-icon"><VideoPlay /></el-icon>
              </div>
            </div>
          </template>
        </el-table-column>
        <el-table-column :label="t('admin.moderation.type')" width="80" align="center">
          <template #default="{ row }">
            <el-tag :type="row.type === 'image' ? 'primary' : 'warning'" size="small">
              {{ row.type === 'image' ? t('admin.moderation.filterImage') : t('admin.moderation.filterVideo') }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column :label="t('admin.moderation.prompt')" min-width="200">
          <template #default="{ row }">
            <el-tooltip :content="row.prompt" placement="top" :show-after="300">
              <span class="prompt-text">{{ truncatePrompt(row.prompt) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column :label="t('admin.moderation.author')" width="140" align="center">
          <template #default="{ row }">
            <div class="author-cell">
              <span class="author-name">{{ row.nickname || row.username || t('admin.moderation.anonymous') }}</span>
              <span class="author-id muted">ID: {{ row.user_id }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column :label="t('admin.moderation.status')" width="110" align="center">
          <template #default="{ row }">
            <el-tag :type="statusTagType(row.moderation_status)" size="small">
              {{ statusText(row.moderation_status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column :label="t('admin.moderation.hitWords')" min-width="150">
          <template #default="{ row }">
            <div v-if="row.moderation_flags && row.moderation_flags.length > 0" class="flags-wrap">
              <el-tag
                v-for="flag in row.moderation_flags"
                :key="flag"
                type="danger"
                size="small"
                effect="light"
                style="margin-right: 4px; margin-bottom: 4px"
              >
                {{ flag }}
              </el-tag>
            </div>
            <span v-else class="muted">-</span>
          </template>
        </el-table-column>
        <el-table-column :label="t('admin.moderation.likesViews')" width="120" align="center">
          <template #default="{ row }">
            <div class="stats-text">
              <span>{{ row.likes_count }} {{ t('admin.moderation.likes') }}</span>
              <span class="muted">/</span>
              <span>{{ row.views_count }} {{ t('admin.moderation.views') }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" :label="t('admin.moderation.createTime')" width="170" align="center">
          <template #default="{ row }">
            <span class="muted">{{ formatTime(row.created_at) }}</span>
          </template>
        </el-table-column>
        <el-table-column :label="t('admin.moderation.actions')" width="200" align="center" fixed="right">
          <template #default="{ row }">
            <el-button
              v-if="row.moderation_status !== 'approved'"
              type="success"
              size="small"
              link
              @click="onApprove(row)"
            >
              {{ t('admin.moderation.approve') }}
            </el-button>
            <el-button
              v-if="row.moderation_status !== 'rejected'"
              type="danger"
              size="small"
              link
              @click="onReject(row)"
            >
              {{ t('admin.moderation.reject') }}
            </el-button>
            <el-button type="primary" size="small" link @click="openPreview(row)">
              {{ t('admin.moderation.detail') }}
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-wrap">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :page-sizes="[10, 20, 50, 100]"
          :total="total"
          layout="total, sizes, prev, pager, next, jumper"
          background
          @size-change="fetchList"
          @current-change="fetchList"
        />
      </div>
    </el-card>

    <el-dialog v-model="rejectDialogVisible" :title="rejectDialogTitle" width="420px">
      <el-input
        v-model="rejectReason"
        type="textarea"
        :rows="4"
        :placeholder="t('admin.moderation.rejectReasonPlaceholder')"
        maxlength="200"
        show-word-limit
      />
      <template #footer>
        <el-button @click="rejectDialogVisible = false">{{ t('common.cancel') }}</el-button>
        <el-button type="primary" :loading="rejectLoading" @click="confirmReject">
          {{ t('admin.moderation.confirmReject') }}
        </el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="previewVisible" :title="t('admin.moderation.workDetail')" width="640px">
      <div v-if="currentWork" class="preview-detail">
        <div class="preview-media">
          <el-image
            v-if="currentWork.type === 'image'"
            :src="currentWork.result_url"
            fit="contain"
            style="width: 100%; max-height: 400px"
          />
          <video v-else :src="currentWork.result_url" controls style="width: 100%; max-height: 400px" />
        </div>
        <div class="preview-info">
          <div class="info-row">
            <span class="info-label">{{ t('admin.moderation.id') }}：</span>
            <span>{{ currentWork.id }}</span>
          </div>
          <div class="info-row">
            <span class="info-label">{{ t('admin.moderation.type') }}：</span>
            <el-tag :type="currentWork.type === 'image' ? 'primary' : 'warning'" size="small">
              {{ currentWork.type === 'image' ? t('admin.moderation.filterImage') : t('admin.moderation.filterVideo') }}
            </el-tag>
          </div>
          <div class="info-row">
            <span class="info-label">{{ t('admin.moderation.status') }}：</span>
            <el-tag :type="statusTagType(currentWork.moderation_status)" size="small">
              {{ statusText(currentWork.moderation_status) }}
            </el-tag>
          </div>
          <div class="info-row">
            <span class="info-label">{{ t('admin.moderation.author') }}：</span>
            <span>{{ currentWork.nickname || currentWork.username || t('admin.moderation.anonymous') }} (ID: {{ currentWork.user_id }})</span>
          </div>
          <div class="info-row">
            <span class="info-label">{{ t('admin.moderation.model') }}：</span>
            <span>{{ currentWork.model }}</span>
          </div>
          <div class="info-row">
            <span class="info-label">{{ t('admin.moderation.likesViews') }}：</span>
            <span>{{ currentWork.likes_count }} / {{ currentWork.views_count }}</span>
          </div>
          <div class="info-row">
            <span class="info-label">{{ t('admin.moderation.createTime') }}：</span>
            <span>{{ formatTime(currentWork.created_at) }}</span>
          </div>
          <div v-if="currentWork.moderation_reason" class="info-row">
            <span class="info-label">{{ t('admin.moderation.rejectReason') }}：</span>
            <span>{{ currentWork.moderation_reason }}</span>
          </div>
          <div v-if="currentWork.moderation_flags && currentWork.moderation_flags.length > 0" class="info-row">
            <span class="info-label">{{ t('admin.moderation.hitWords') }}：</span>
            <div class="flags-wrap">
              <el-tag
                v-for="flag in currentWork.moderation_flags"
                :key="flag"
                type="danger"
                size="small"
                effect="light"
                style="margin-right: 4px"
              >
                {{ flag }}
              </el-tag>
            </div>
          </div>
          <div class="info-row prompt-row">
            <span class="info-label">Prompt：</span>
            <span class="prompt-full">{{ currentWork.prompt }}</span>
          </div>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh, Search, VideoPlay, Warning, Check, Close } from '@element-plus/icons-vue'
import { useI18n } from '@/i18n'
import {
  getModerationWorks,
  approveWork,
  rejectWork,
  batchApprove,
  batchReject
} from '@/api/admin'
import type { ModerationWork } from '@/api/admin'

const { t } = useI18n()

const loading = ref(false)
const list = ref<ModerationWork[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)

const filterStatus = ref<string>('pending')
const filterType = ref<string>('')
const keyword = ref('')
const searchWorkId = ref<string>('')
const searchUsername = ref('')

const selectedIds = ref<number[]>([])

const rejectDialogVisible = ref(false)
const rejectReason = ref('')
const rejectLoading = ref(false)
const rejectTargetId = ref<number | null>(null)
const isBatchReject = ref(false)

const rejectDialogTitle = computed(() => {
  if (rejectTargetId.value === -1) return t('admin.moderation.quickReject')
  if (isBatchReject.value) return t('admin.moderation.batchReject')
  return t('admin.moderation.rejectReason')
})

const previewVisible = ref(false)
const currentWork = ref<ModerationWork | null>(null)

function formatTime(val?: string | null) {
  if (!val) return ''
  try {
    return new Date(val).toLocaleString()
  } catch {
    return val
  }
}

function truncatePrompt(prompt: string) {
  if (!prompt) return ''
  return prompt.length > 60 ? prompt.slice(0, 60) + '...' : prompt
}

function statusTagType(status: string) {
  switch (status) {
    case 'pending':
      return 'warning'
    case 'approved':
      return 'success'
    case 'rejected':
      return 'danger'
    default:
      return 'info'
  }
}

function statusText(status: string) {
  switch (status) {
    case 'pending':
      return t('admin.moderation.tabPending')
    case 'approved':
      return t('admin.moderation.tabApproved')
    case 'rejected':
      return t('admin.moderation.tabRejected')
    default:
      return status
  }
}

async function fetchList() {
  loading.value = true
  try {
    const params: any = {
      page: page.value,
      page_size: pageSize.value
    }
    if (filterStatus.value) params.status = filterStatus.value
    if (filterType.value) params.work_type = filterType.value
    if (keyword.value.trim()) params.keyword = keyword.value.trim()
    if (searchWorkId.value.trim()) {
      const id = parseInt(searchWorkId.value.trim())
      if (!isNaN(id)) params.work_id = id
    }
    if (searchUsername.value.trim()) params.username = searchUsername.value.trim()

    const resp = await getModerationWorks(params)
    list.value = resp.items || []
    total.value = resp.total || 0
  } catch (e) {
    console.warn(e)
  } finally {
    loading.value = false
  }
}

function onFilterChange() {
  page.value = 1
  fetchList()
}

function onStatusTabChange() {
  page.value = 1
  selectedIds.value = []
  fetchList()
}

function onSearch() {
  page.value = 1
  fetchList()
}

function onSelectionChange(selection: ModerationWork[]) {
  selectedIds.value = selection.map(item => item.id)
}

function clearSelection() {
  selectedIds.value = []
}

async function onApprove(row: ModerationWork) {
  try {
    await ElMessageBox.confirm(t('admin.moderation.approveConfirm'), t('admin.moderation.approveTitle'), {
      confirmButtonText: t('common.confirm'),
      cancelButtonText: t('common.cancel'),
      type: 'success'
    })
  } catch {
    return
  }
  try {
    await approveWork(row.id)
    ElMessage.success(t('admin.moderation.approveSuccess'))
    fetchList()
  } catch (e) {
    console.warn(e)
  }
}

function onReject(row: ModerationWork) {
  rejectTargetId.value = row.id
  isBatchReject.value = false
  rejectReason.value = ''
  rejectDialogVisible.value = true
}

async function confirmReject() {
  rejectLoading.value = true
  try {
    if (rejectTargetId.value === -1) {
      const ids = await fetchAllPendingIds()
      if (ids.length === 0) {
        ElMessage.info(t('admin.moderation.noPending'))
        rejectDialogVisible.value = false
        return
      }
      await batchReject(ids, rejectReason.value || undefined)
      ElMessage.success(t('admin.moderation.quickRejectSuccess', { count: ids.length }))
    } else if (isBatchReject.value) {
      await batchReject(selectedIds.value, rejectReason.value || undefined)
      ElMessage.success(t('admin.moderation.batchRejectSuccess', { count: selectedIds.value.length }))
      clearSelection()
    } else if (rejectTargetId.value !== null) {
      await rejectWork(rejectTargetId.value, rejectReason.value || undefined)
      ElMessage.success(t('admin.moderation.rejectSuccess'))
    }
    rejectDialogVisible.value = false
    fetchList()
  } catch (e) {
    console.warn(e)
  } finally {
    rejectLoading.value = false
  }
}

async function onBatchApprove() {
  if (selectedIds.value.length === 0) return
  try {
    await ElMessageBox.confirm(
      t('admin.moderation.batchApproveConfirm', { count: selectedIds.value.length }),
      t('admin.moderation.batchApproveTitle'),
      { confirmButtonText: t('common.confirm'), cancelButtonText: t('common.cancel'), type: 'success' }
    )
  } catch {
    return
  }
  try {
    await batchApprove(selectedIds.value)
    ElMessage.success(t('admin.moderation.batchApproveSuccess', { count: selectedIds.value.length }))
    clearSelection()
    fetchList()
  } catch (e) {
    console.warn(e)
  }
}

function onBatchReject() {
  if (selectedIds.value.length === 0) return
  isBatchReject.value = true
  rejectTargetId.value = null
  rejectReason.value = ''
  rejectDialogVisible.value = true
}

async function fetchAllPendingIds(): Promise<number[]> {
  const allIds: number[] = []
  let currentPage = 1
  const size = 100
  while (true) {
    const res = await getModerationWorks({
      status: filterStatus.value as any,
      work_type: filterType.value || undefined,
      keyword: keyword.value || undefined,
      work_id: searchWorkId.value || undefined,
      username: searchUsername.value || undefined,
      page: currentPage,
      page_size: size,
    })
    const items = (res as any).items || []
    allIds.push(...items.map((it: ModerationWork) => it.id))
    if (items.length < size) break
    currentPage++
  }
  return allIds
}

async function onQuickApproveAll() {
  try {
    await ElMessageBox.confirm(
      t('admin.moderation.quickApproveConfirm', { count: total.value }),
      t('admin.moderation.quickApproveTitle'),
      { confirmButtonText: t('common.confirm'), cancelButtonText: t('common.cancel'), type: 'success' }
    )
  } catch {
    return
  }
  try {
    const ids = await fetchAllPendingIds()
    if (ids.length === 0) {
      ElMessage.info(t('admin.moderation.noPending'))
      return
    }
    await batchApprove(ids)
    ElMessage.success(t('admin.moderation.quickApproveSuccess', { count: ids.length }))
    fetchList()
  } catch (e) {
    console.warn(e)
  }
}

function onQuickRejectAll() {
  isBatchReject.value = true
  rejectTargetId.value = -1
  rejectReason.value = ''
  rejectDialogVisible.value = true
}

function openPreview(row: ModerationWork) {
  currentWork.value = row
  previewVisible.value = true
}

onMounted(fetchList)
</script>

<style scoped>
.moderation-wrap {
  max-width: 1600px;
  margin: 0 auto;
}

.page-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  margin-bottom: 16px;
}

.page-head h2 {
  margin: 0 0 4px;
  color: var(--agnes-text-primary);
  font-size: 20px;
}

.status-tabs {
  margin-bottom: 12px;
}

.status-tabs :deep(.el-tabs__item) {
  font-size: 15px;
  padding: 0 20px;
  height: 44px;
  line-height: 44px;
}

.status-tabs :deep(.el-tabs__active-bar) {
  height: 3px;
}

.status-tabs :deep(.el-tabs__nav-wrap::after) {
  height: 1px;
}

.muted {
  color: var(--agnes-text-muted);
  font-size: 13px;
  margin: 0;
}

.filter-card,
.table-card {
  background: var(--agnes-bg-elevated);
  border: 1px solid var(--agnes-border);
  border-radius: 10px;
}

.filter-card {
  margin-bottom: 16px;
}

.quick-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  margin-bottom: 14px;
  background: linear-gradient(90deg, #fff7e6 0%, #fffbe6 100%);
  border: 1px solid #ffe58f;
  border-radius: 8px;
}

.quick-label {
  font-size: 13px;
  color: #ad6800;
  display: flex;
  align-items: center;
  gap: 6px;
}

.quick-label b {
  color: #d46b08;
  font-weight: 600;
  margin: 0 2px;
}

.filter-row {
  display: flex;
  gap: 12px;
  align-items: center;
  flex-wrap: wrap;
}

.batch-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--agnes-border);
}

.batch-tip {
  color: var(--agnes-text-secondary);
  font-size: 13px;
}

:deep(.el-table) {
  background: transparent;
  color: var(--agnes-text-secondary);
}

:deep(.el-table th.el-table__cell) {
  background: var(--agnes-bg-hover);
  color: var(--agnes-text-secondary);
}

:deep(.el-table--striped .el-table__body tr.el-table__row--striped td.el-table__cell) {
  background: var(--agnes-bg-hover);
}

.preview-cell {
  display: flex;
  justify-content: center;
}

.video-preview {
  position: relative;
  width: 60px;
  height: 60px;
}

.play-icon {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  font-size: 24px;
  color: #fff;
  text-shadow: 0 0 4px rgba(0, 0, 0, 0.5);
}

.prompt-text {
  color: var(--agnes-text-primary);
  cursor: default;
}

.stats-text {
  font-size: 13px;
  color: var(--agnes-text-secondary);
}

.stats-text .muted {
  margin: 0 4px;
}

.flags-wrap {
  display: flex;
  flex-wrap: wrap;
}

.author-cell {
  display: flex;
  flex-direction: column;
  gap: 2px;
  align-items: center;
}

.author-name {
  color: var(--agnes-text-primary);
  font-size: 13px;
  font-weight: 500;
}

.author-id {
  font-size: 11px;
}

.pagination-wrap {
  display: flex;
  justify-content: flex-end;
  padding-top: 16px;
}

.preview-detail {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.preview-media {
  display: flex;
  justify-content: center;
  background: var(--agnes-bg-hover);
  border-radius: 8px;
  padding: 12px;
}

.preview-info {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.info-row {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  font-size: 14px;
  color: var(--agnes-text-secondary);
}

.info-label {
  color: var(--agnes-text-muted);
  min-width: 80px;
  flex-shrink: 0;
}

.prompt-row {
  align-items: flex-start;
}

.prompt-full {
  color: var(--agnes-text-primary);
  line-height: 1.6;
  word-break: break-all;
}
</style>
