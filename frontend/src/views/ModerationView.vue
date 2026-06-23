<!-- =====================================================
     内容审核页
     - 展示待审核的广场作品列表
     - 支持通过 / 驳回 / 批量操作
     ===================================================== -->

<template>
  <div class="moderation-wrap">
    <header class="page-head">
      <div>
        <h2>内容审核</h2>
        <p class="muted">审核广场公开作品</p>
      </div>
      <el-button :icon="Refresh" @click="fetchList" :loading="loading">刷新</el-button>
    </header>

    <el-card class="filter-card" shadow="never">
      <div class="filter-row">
        <el-select v-model="filterStatus" placeholder="全部状态" style="width: 140px" @change="onFilterChange">
          <el-option label="全部" value="" />
          <el-option label="待审核" value="pending" />
          <el-option label="已通过" value="approved" />
          <el-option label="已屏蔽" value="rejected" />
        </el-select>

        <el-select v-model="filterType" placeholder="全部类型" style="width: 120px" @change="onFilterChange">
          <el-option label="全部" value="" />
          <el-option label="图片" value="image" />
          <el-option label="视频" value="video" />
        </el-select>

        <el-input
          v-model="keyword"
          placeholder="搜索 prompt 或用户 ID"
          style="width: 260px"
          clearable
          @keyup.enter="onSearch"
          @clear="onSearch"
        >
          <template #prefix>
            <el-icon><Search /></el-icon>
          </template>
        </el-input>

        <el-button type="primary" @click="onSearch">搜索</el-button>
      </div>

      <div v-if="selectedIds.length > 0" class="batch-bar">
        <span class="batch-tip">已选择 {{ selectedIds.length }} 项</span>
        <el-button type="success" size="small" @click="onBatchApprove">批量通过</el-button>
        <el-button type="danger" size="small" @click="onBatchReject">批量屏蔽</el-button>
        <el-button size="small" @click="clearSelection">取消选择</el-button>
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
        <el-table-column prop="id" label="ID" width="70" align="center" />
        <el-table-column label="预览" width="100" align="center">
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
        <el-table-column label="类型" width="80" align="center">
          <template #default="{ row }">
            <el-tag :type="row.type === 'image' ? 'primary' : 'warning'" size="small">
              {{ row.type === 'image' ? '图片' : '视频' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="内容" min-width="200">
          <template #default="{ row }">
            <el-tooltip :content="row.prompt" placement="top" :show-after="300">
              <span class="prompt-text">{{ truncatePrompt(row.prompt) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="作者" width="120" align="center">
          <template #default="{ row }">
            <span>{{ row.user_id }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审核状态" width="110" align="center">
          <template #default="{ row }">
            <el-tag :type="statusTagType(row.moderation_status)" size="small">
              {{ statusText(row.moderation_status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="命中敏感词" min-width="150">
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
        <el-table-column label="点赞/浏览" width="120" align="center">
          <template #default="{ row }">
            <div class="stats-text">
              <span>{{ row.likes_count }} 赞</span>
              <span class="muted">/</span>
              <span>{{ row.views_count }} 览</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="发布时间" width="170" align="center">
          <template #default="{ row }">
            <span class="muted">{{ formatTime(row.created_at) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="200" align="center" fixed="right">
          <template #default="{ row }">
            <el-button
              v-if="row.moderation_status !== 'approved'"
              type="success"
              size="small"
              link
              @click="onApprove(row)"
            >
              通过
            </el-button>
            <el-button
              v-if="row.moderation_status !== 'rejected'"
              type="danger"
              size="small"
              link
              @click="onReject(row)"
            >
              屏蔽
            </el-button>
            <el-button type="primary" size="small" link @click="openPreview(row)">
              详情
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

    <el-dialog v-model="rejectDialogVisible" title="驳回原因" width="420px">
      <el-input
        v-model="rejectReason"
        type="textarea"
        :rows="4"
        placeholder="请输入驳回原因（可选）"
        maxlength="200"
        show-word-limit
      />
      <template #footer>
        <el-button @click="rejectDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="rejectLoading" @click="confirmReject">
          确认屏蔽
        </el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="previewVisible" title="作品详情" width="640px">
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
            <span class="info-label">ID：</span>
            <span>{{ currentWork.id }}</span>
          </div>
          <div class="info-row">
            <span class="info-label">类型：</span>
            <el-tag :type="currentWork.type === 'image' ? 'primary' : 'warning'" size="small">
              {{ currentWork.type === 'image' ? '图片' : '视频' }}
            </el-tag>
          </div>
          <div class="info-row">
            <span class="info-label">状态：</span>
            <el-tag :type="statusTagType(currentWork.moderation_status)" size="small">
              {{ statusText(currentWork.moderation_status) }}
            </el-tag>
          </div>
          <div class="info-row">
            <span class="info-label">作者：</span>
            <span>{{ currentWork.user_id }}</span>
          </div>
          <div class="info-row">
            <span class="info-label">模型：</span>
            <span>{{ currentWork.model }}</span>
          </div>
          <div class="info-row">
            <span class="info-label">点赞/浏览：</span>
            <span>{{ currentWork.likes_count }} / {{ currentWork.views_count }}</span>
          </div>
          <div class="info-row">
            <span class="info-label">发布时间：</span>
            <span>{{ formatTime(currentWork.created_at) }}</span>
          </div>
          <div v-if="currentWork.moderation_reason" class="info-row">
            <span class="info-label">驳回原因：</span>
            <span>{{ currentWork.moderation_reason }}</span>
          </div>
          <div v-if="currentWork.moderation_flags && currentWork.moderation_flags.length > 0" class="info-row">
            <span class="info-label">命中敏感词：</span>
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
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh, Search, VideoPlay } from '@element-plus/icons-vue'
import {
  getModerationWorks,
  approveWork,
  rejectWork,
  batchApprove,
  batchReject
} from '@/api/admin'
import type { ModerationWork } from '@/api/admin'

const loading = ref(false)
const list = ref<ModerationWork[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)

const filterStatus = ref<string>('')
const filterType = ref<string>('')
const keyword = ref('')

const selectedIds = ref<number[]>([])

const rejectDialogVisible = ref(false)
const rejectReason = ref('')
const rejectLoading = ref(false)
const rejectTargetId = ref<number | null>(null)
const isBatchReject = ref(false)

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
      return '待审核'
    case 'approved':
      return '已通过'
    case 'rejected':
      return '已屏蔽'
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
    if (filterType.value) params.type = filterType.value
    if (keyword.value.trim()) params.keyword = keyword.value.trim()

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
    await ElMessageBox.confirm('确认通过该作品的审核？', '通过审核', {
      confirmButtonText: '确认',
      cancelButtonText: '取消',
      type: 'success'
    })
  } catch {
    return
  }
  try {
    await approveWork(row.id)
    ElMessage.success('已通过')
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
    if (isBatchReject.value) {
      await batchReject(selectedIds.value, rejectReason.value || undefined)
      ElMessage.success(`已批量屏蔽 ${selectedIds.value.length} 项`)
      clearSelection()
    } else if (rejectTargetId.value !== null) {
      await rejectWork(rejectTargetId.value, rejectReason.value || undefined)
      ElMessage.success('已屏蔽')
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
      `确认通过选中的 ${selectedIds.value.length} 项作品？`,
      '批量通过',
      { confirmButtonText: '确认', cancelButtonText: '取消', type: 'success' }
    )
  } catch {
    return
  }
  try {
    await batchApprove(selectedIds.value)
    ElMessage.success(`已批量通过 ${selectedIds.value.length} 项`)
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
