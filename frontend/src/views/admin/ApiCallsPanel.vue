<!-- =====================================================
     上游调用记账面板（管理员，/admin/logs 第三 Tab）
     - 聚合卡：近 N 天调用数 / 失败数 / 失败率 + 按类目计数
     - 列表：时间/渠道/模型/类型/耗时/状态/类目/错误摘要，分页筛选
     - 与日志双 Tab 独立：自持加载状态，切到本 Tab 才拉数据
     ===================================================== -->

<template>
  <div class="calls-panel">
    <!-- 聚合卡 -->
    <div class="summary-cards">
      <div class="sum-card">
        <span class="sum-label">{{ t('logs.callsTotal', { days: summaryDays }) }}</span>
        <span class="sum-value">{{ summary?.total ?? '-' }}</span>
      </div>
      <div class="sum-card">
        <span class="sum-label">{{ t('logs.callsFailed') }}</span>
        <span class="sum-value failed">{{ summary?.failed ?? '-' }}</span>
      </div>
      <div class="sum-card">
        <span class="sum-label">{{ t('logs.callsFailureRate') }}</span>
        <span class="sum-value">{{ summary ? (summary.failure_rate * 100).toFixed(1) + '%' : '-' }}</span>
      </div>
      <div class="sum-card wide">
        <span class="sum-label">{{ t('logs.callsByCategory') }}</span>
        <div class="cat-tags">
          <el-tag v-for="c in summary?.by_category || []" :key="c.category" size="small" type="warning" class="cat-tag">
            {{ t(`errors.category_${c.category}`) }} × {{ c.count }}
          </el-tag>
          <span v-if="!summary?.by_category?.length" class="cat-empty">{{ t('logs.callsNoFailures') }}</span>
        </div>
      </div>
    </div>

    <!-- 全部概览：按渠道/按模型汇总（点击模型行可筛选下方列表） -->
    <div class="overview-row">
      <div class="overview-box">
        <div class="overview-title">{{ t('logs.callsByProvider') }}</div>
        <el-table :data="providerStats" size="small" max-height="200" class="overview-table">
          <el-table-column prop="name" :label="t('logs.callsColProvider')" min-width="110" show-overflow-tooltip />
          <el-table-column prop="success" :label="t('logs.callsColSuccess')" width="64" align="right" />
          <el-table-column prop="failed" :label="t('logs.callsColFailed')" width="64" align="right" />
        </el-table>
      </div>
      <div class="overview-box">
        <div class="overview-title">{{ t('logs.callsByModel') }}</div>
        <el-table :data="modelStats" size="small" max-height="200" class="overview-table" @row-click="filterByModel">
          <el-table-column prop="name" :label="t('logs.callsColModel')" min-width="150" show-overflow-tooltip />
          <el-table-column prop="success" :label="t('logs.callsColSuccess')" width="64" align="right" />
          <el-table-column prop="failed" :label="t('logs.callsColFailed')" width="64" align="right" />
        </el-table>
        <div class="overview-hint">{{ t('logs.callsClickToFilter') }}</div>
      </div>
    </div>

    <!-- 筛选行 -->
    <div class="filter-row">
      <el-select v-model="filters.status" size="small" clearable :placeholder="t('logs.callsFilterStatus')" class="f-item">
        <el-option label="success" value="success" />
        <el-option label="failed" value="failed" />
      </el-select>
      <el-select v-model="filters.callType" size="small" clearable :placeholder="t('logs.callsFilterType')" class="f-item">
        <el-option v-for="ct in CALL_TYPES" :key="ct" :label="ct" :value="ct" />
      </el-select>
      <el-input v-model="filters.model" size="small" clearable :placeholder="t('logs.callsFilterModel')" class="f-item model" />
      <el-button size="small" type="primary" @click="reload">{{ t('logs.refresh') }}</el-button>
    </div>

    <!-- 列表 -->
    <el-table :data="rows" v-loading="loading" size="small" class="calls-table">
      <el-table-column prop="created_at" :label="t('logs.callsColTime')" width="170">
        <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
      </el-table-column>
      <el-table-column prop="provider_name" :label="t('logs.callsColProvider')" width="120" show-overflow-tooltip />
      <el-table-column prop="model" :label="t('logs.callsColModel')" min-width="160" show-overflow-tooltip />
      <el-table-column prop="call_type" :label="t('logs.callsColType')" width="120" />
      <el-table-column prop="latency_ms" :label="t('logs.callsColLatency')" width="90">
        <template #default="{ row }">{{ row.latency_ms != null ? row.latency_ms + 'ms' : '-' }}</template>
      </el-table-column>
      <el-table-column prop="status" :label="t('logs.callsColStatus')" width="90">
        <template #default="{ row }">
          <el-tag :type="row.status === 'success' ? 'success' : 'danger'" size="small">{{ row.status }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="error_category" :label="t('logs.callsColCategory')" width="140" show-overflow-tooltip>
        <template #default="{ row }">{{ row.error_category ? t(`errors.category_${row.error_category}`) : '-' }}</template>
      </el-table-column>
      <el-table-column prop="error_message" :label="t('logs.callsColError')" min-width="200" show-overflow-tooltip />
    </el-table>

    <div class="pager">
      <el-pagination
        v-model:current-page="page"
        :page-size="pageSize"
        :total="total"
        layout="prev, pager, next"
        @current-change="load"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useI18n } from '@/i18n'
import { listApiCalls, getApiCallsSummary, type ApiCallRecord, type ApiCallSummary } from '@/api/apiCalls'

const CALL_TYPES = ['image_create', 'image_poll', 'video_create', 'video_poll', 'chat', 'prompt_optimize', 'other']

const { t } = useI18n()

const summaryDays = 7
const summary = ref<ApiCallSummary | null>(null)
const rows = ref<ApiCallRecord[]>([])
const loading = ref(false)
const page = ref(1)
const pageSize = 50
const total = ref(0)
const filters = reactive({ status: '', callType: '', model: '' })

/** 汇总字典 → 行数组（按调用量降序） */
function toStats(rec?: Record<string, { success: number; failed: number }>): Array<{ name: string; success: number; failed: number }> {
  return Object.entries(rec ?? {})
    .map(([name, v]) => ({ name, success: v.success, failed: v.failed }))
    .sort((a, b) => (b.success + b.failed) - (a.success + a.failed))
}

const providerStats = computed(() => toStats(summary.value?.by_provider))
const modelStats = computed(() => toStats(summary.value?.by_model))

/** 点击模型行 → 填入列表筛选并查询（unknown 为空值聚合，无精确值可筛） */
function filterByModel(row: { name: string }): void {
  if (row.name === 'unknown') return
  filters.model = row.name
  page.value = 1
  void load()
}

async function loadSummary(): Promise<void> {
  try {
    summary.value = await getApiCallsSummary(summaryDays)
  } catch (_) { /* 管理页统一错误提示 */ }
}

async function load(): Promise<void> {
  loading.value = true
  try {
    const data = await listApiCalls({
      page: page.value,
      page_size: pageSize,
      status: filters.status || undefined,
      call_type: filters.callType || undefined,
      model: filters.model.trim() || undefined,
    })
    rows.value = data.calls
    total.value = data.total
  } catch (_) { /* 管理页统一错误提示 */ } finally {
    loading.value = false
  }
}

function reload(): void {
  page.value = 1
  void load()
  void loadSummary()
}

function formatTime(value: string | null): string {
  if (!value) return '-'
  return value.replace('T', ' ').slice(0, 19)
}

onMounted(() => {
  void load()
  void loadSummary()
})
</script>

<style scoped>
.calls-panel {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.summary-cards {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.sum-card {
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  padding: 10px 14px;
  min-width: 120px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.sum-card.wide {
  flex: 1;
  min-width: 240px;
}

.sum-label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.sum-value {
  font-size: 20px;
  font-weight: 600;
}

.sum-value.failed {
  color: var(--el-color-danger);
}

.cat-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.cat-tag {
  max-width: 260px;
  overflow: hidden;
  text-overflow: ellipsis;
}

.cat-empty {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.filter-row {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}

.overview-row {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.overview-box {
  flex: 1;
  min-width: 300px;
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  padding: 10px 12px;
}

.overview-title {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-bottom: 6px;
}

.overview-hint {
  font-size: 11px;
  color: var(--el-text-color-secondary);
  margin-top: 4px;
}

.f-item {
  width: 150px;
}

.f-item.model {
  width: 220px;
}

.pager {
  display: flex;
  justify-content: flex-end;
}
</style>
