<!-- =====================================================
     日志查看（管理员）
     - 双 Tab：后端日志（agnes_platform.log / errors.jsonl / 轮转备份）与前端日志（frontend.jsonl）
     - 两个 Tab 各自独立记忆数据源与筛选条件
     - 筛选：级别 / 关键词 / request_id / 时间范围；倒序最新在前，before 游标「加载更多」
     - 行展开：完整堆栈、上下文、复制、按 request_id 追踪
     - 工具：手动刷新、10 秒自动刷新开关、下载当前文件、清空当前文件（二次确认）
     ===================================================== -->

<template>
  <div class="logs-view">
    <el-tabs v-model="activeTab" class="logs-tabs">
      <el-tab-pane :label="t('logs.backendTab')" name="backend" />
      <el-tab-pane :label="t('logs.frontendTab')" name="frontend" />
    </el-tabs>

    <!-- 筛选工具条（绑定当前激活 Tab 的独立状态） -->
    <div class="logs-toolbar">
      <el-select
        v-if="isBackend"
        v-model="state.file"
        class="w-file"
        :loading="statsLoading"
        @change="reload">
        <el-option v-for="opt in fileOptions" :key="opt.value" :label="opt.value" :value="opt.value">
          <span class="file-option">
            {{ opt.value }}
            <span v-if="opt.size" class="file-size">{{ opt.size }}</span>
          </span>
        </el-option>
      </el-select>
      <el-select v-model="state.level" class="w-level" clearable :placeholder="t('logs.level')" @change="reload">
        <el-option v-for="lv in LEVEL_OPTIONS" :key="lv" :label="lv" :value="lv" />
      </el-select>
      <el-input
        v-model="state.keyword"
        class="w-keyword"
        clearable
        :placeholder="t('logs.keywordPlaceholder')"
        @keyup.enter="reload"
        @clear="reload" />
      <el-input
        v-if="isBackend"
        v-model="state.requestId"
        class="w-req"
        clearable
        :placeholder="t('logs.requestIdPlaceholder')"
        @keyup.enter="reload"
        @clear="reload" />
      <el-select v-model="state.range" class="w-range" @change="reload">
        <el-option :label="t('logs.range1h')" value="1h" />
        <el-option :label="t('logs.range24h')" value="24h" />
        <el-option :label="t('logs.rangeAll')" value="all" />
      </el-select>
      <el-button type="primary" @click="reload">{{ t('logs.query') }}</el-button>

      <div class="toolbar-right">
        <el-button :icon="Refresh" :loading="state.loading" @click="reload">{{ t('logs.refresh') }}</el-button>
        <span class="auto-refresh">
          <span class="auto-refresh-label">{{ t('logs.autoRefresh') }}</span>
          <el-switch v-model="autoRefresh" />
        </span>
        <el-button :icon="Download" :disabled="!state.file" @click="download">{{ t('logs.download') }}</el-button>
        <el-button type="danger" plain :icon="Delete" :disabled="!state.file" @click="clear">
          {{ t('logs.clear') }}
        </el-button>
      </div>
    </div>

    <!-- 日志列表（倒序，最新在前） -->
    <el-table
      v-loading="state.loading"
      :data="state.entries"
      class="logs-table"
      size="small"
      height="560">
      <el-table-column type="expand">
        <template #default="{ row }">
          <div class="entry-detail">
            <div v-if="row.request_id && row.request_id !== '-'" class="detail-line">
              <span class="detail-label">request_id</span>
              <code>{{ row.request_id }}</code>
              <el-button size="small" text type="primary" @click="trackRequest(row)">
                {{ t('logs.track') }}
              </el-button>
            </div>
            <div v-if="row.module" class="detail-line">
              <span class="detail-label">{{ t('logs.colModule') }}</span>
              <code>{{ row.module }}<template v-if="row.func">.{{ row.func }}:{{ row.lineno }}</template></code>
            </div>
            <pre v-if="row.exception" class="detail-stack">{{ row.exception }}</pre>
            <div v-if="row.context" class="detail-line">
              <span class="detail-label">{{ t('logs.context') }}</span>
              <code class="detail-context">{{ JSON.stringify(row.context) }}</code>
            </div>
            <pre v-if="row.raw" class="detail-stack">{{ row.raw }}</pre>
            <el-button size="small" text @click="copyEntry(row)">{{ t('logs.copy') }}</el-button>
          </div>
        </template>
      </el-table-column>
      <el-table-column :label="t('logs.colTime')" width="180">
        <template #default="{ row }">{{ formatTime(row) }}</template>
      </el-table-column>
      <el-table-column :label="t('logs.colLevel')" width="100">
        <template #default="{ row }">
          <el-tag v-if="row.level" :type="levelTagType(row.level)" size="small">{{ row.level }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column :label="t('logs.colModule')" width="150" show-overflow-tooltip>
        <template #default="{ row }">{{ row.module || '—' }}</template>
      </el-table-column>
      <el-table-column :label="t('logs.colMessage')" min-width="420">
        <template #default="{ row }">
          <span class="msg-cell">{{ row.message || row.raw }}</span>
        </template>
      </el-table-column>
      <template #empty>
        <el-empty :description="t('logs.empty')" :image-size="80" />
      </template>
    </el-table>

    <div class="table-footer">
      <span class="total-text">{{ t('logs.total', { count: state.entries.length }) }}</span>
      <el-button v-if="hasMore" text type="primary" :loading="state.loading" @click="loadMore">
        {{ t('logs.loadMore') }}
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onUnmounted, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Delete, Download, Refresh } from '@element-plus/icons-vue'
import { useI18n } from '@/i18n'
import { clearLog, getLogStats, queryLogs } from '@/api/logs'
import type { LogEntry, LogQueryParams } from '@/api/logs'
import { useConfirm } from '@/composables/useConfirm'
import { useCopyText } from '@/composables/useCopyText'
import { useDownload } from '@/composables/useDownload'

defineOptions({ name: 'LogsView' })

const { t } = useI18n()
const { confirm } = useConfirm()
const { copyText } = useCopyText()
const { downloadViaProxy } = useDownload()

const PAGE_SIZE = 100
const AUTO_REFRESH_MS = 10_000
const LEVEL_OPTIONS = ['INFO', 'WARNING', 'ERROR', 'CRITICAL']
type TimeRange = '1h' | '24h' | 'all'

interface TabState {
  file: string
  level: string
  keyword: string
  requestId: string
  range: TimeRange
  entries: LogEntry[]
  lastCount: number
  loading: boolean
}

function emptyState(file: string): TabState {
  return { file, level: '', keyword: '', requestId: '', range: 'all', entries: [], lastCount: 0, loading: false }
}

// 两个 Tab 各自独立记忆数据源与筛选条件
const tabStates = reactive<Record<'backend' | 'frontend', TabState>>({
  backend: emptyState('agnes_platform.log'),
  frontend: emptyState('frontend.jsonl'),
})

const activeTab = ref<'backend' | 'frontend'>('backend')
const state = computed(() => tabStates[activeTab.value])
const isBackend = computed(() => activeTab.value === 'backend')
const hasMore = computed(() => state.value.lastCount >= PAGE_SIZE && state.value.entries.length > 0)

// ---------- 数据源下拉（后端 Tab：主日志 / 错误日志 / 轮转备份） ----------
const statsFiles = ref<Record<string, { size_mb?: number }>>({})
const statsLoading = ref(false)

const fileOptions = computed(() => {
  return Object.entries(statsFiles.value)
    .filter(([name]) => name === 'agnes_platform.log' || name === 'errors.jsonl' || /^agnes_platform\.log\.\d$/.test(name))
    .map(([name, info]) => ({
      value: name,
      // 大小只在下拉项里展示，选中态只显示文件名（避免拉宽选择框把工具条挤成两行）
      size: info.size_mb !== undefined ? `${info.size_mb} MB` : '',
    }))
})

async function loadStats(): Promise<void> {
  statsLoading.value = true
  try {
    const stats = await getLogStats()
    statsFiles.value = stats.files || {}
  } catch (_) {
    /* 统一错误提示 */
  } finally {
    statsLoading.value = false
  }
}

// ---------- 查询 ----------
function sinceOf(range: TimeRange): string | undefined {
  if (range === 'all') return undefined
  const delta = range === '1h' ? 3_600_000 : 86_400_000
  return new Date(Date.now() - delta).toISOString()
}

function lastTimestamp(): string | undefined {
  return state.value.entries.length ? state.value.entries[state.value.entries.length - 1].timestamp : undefined
}

async function fetchLogs(mode: 'reload' | 'more'): Promise<void> {
  const s = state.value
  s.loading = true
  try {
    const params: LogQueryParams = { file: s.file, limit: PAGE_SIZE }
    if (s.level) params.level = s.level
    if (s.keyword.trim()) params.keyword = s.keyword.trim()
    if (isBackend.value && s.requestId.trim()) params.request_id = s.requestId.trim()
    const since = sinceOf(s.range)
    if (since) params.since = since
    // before 游标翻页：文本行缺 timestamp 时无法定位，隐藏加载更多
    const before = mode === 'more' ? lastTimestamp() : undefined
    if (before) params.before = before

    const data = await queryLogs(params)
    s.entries = mode === 'more' ? [...s.entries, ...data.logs] : data.logs
    s.lastCount = data.logs.length
  } catch (_) {
    /* 统一错误提示 */
  } finally {
    s.loading = false
  }
}

function reload(): void {
  void fetchLogs('reload')
}

async function loadMore(): Promise<void> {
  await fetchLogs('more')
}

watch(activeTab, () => reload())

// ---------- 自动刷新（10 秒，作用于当前激活 Tab） ----------
const autoRefresh = ref(false)
let refreshTimer: ReturnType<typeof setInterval> | undefined

watch(autoRefresh, (on) => {
  if (on) {
    refreshTimer = setInterval(reload, AUTO_REFRESH_MS)
  } else if (refreshTimer) {
    clearInterval(refreshTimer)
    refreshTimer = undefined
  }
})

onUnmounted(() => {
  if (refreshTimer) clearInterval(refreshTimer)
})

// ---------- 展示辅助 ----------
function formatTime(row: LogEntry): string {
  const ts = row.timestamp
  if (!ts) return '—'
  // jsonl 为 UTC ISO 串，转本地时间；文本行为本地时间原样展示
  return ts.includes('T') ? new Date(ts).toLocaleString(undefined, { hour12: false }) : ts
}

function levelTagType(level: string): 'danger' | 'warning' | 'info' {
  if (level === 'ERROR' || level === 'CRITICAL') return 'danger'
  if (level === 'WARNING') return 'warning'
  return 'info'
}

function copyEntry(row: LogEntry): void {
  void copyText(JSON.stringify(row, null, 2), t('logs.copied'))
}

function trackRequest(row: LogEntry): void {
  state.value.requestId = row.request_id || ''
  reload()
}

// ---------- 下载与清空 ----------
async function download(): Promise<void> {
  const file = state.value.file
  try {
    await downloadViaProxy(`/api/logs/download?file=${encodeURIComponent(file)}`, file)
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : t('logs.downloadFailed'))
  }
}

async function clear(): Promise<void> {
  const file = state.value.file
  await confirm(t('logs.clearConfirmText', { file }), t('logs.clearConfirmTitle'))
  try {
    await clearLog(file)
    ElMessage.success(t('logs.clearDone'))
    void loadStats()
    reload()
  } catch (_) {
    /* 统一错误提示 */
  }
}

// 初始化：加载数据源统计 + 默认查询
void loadStats()
reload()
</script>

<style scoped>
.logs-view {
  display: flex;
  flex-direction: column;
  gap: 12px;
  height: 100%;
}

.logs-tabs :deep(.el-tabs__header) {
  margin-bottom: 0;
}

/* ---- 工具条 ---- */
.logs-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  padding: 10px 12px;
  background: var(--agnes-bg-elevated, #f5f7fa);
  border: 1px solid var(--agnes-border-faint, #ebeef5);
  border-radius: 8px;
}

/* 控件宽度收紧，保证常规窗口下工具条单行排布 */
.w-file { width: 185px; }
.w-level { width: 100px; }
.w-keyword { width: 165px; }
.w-req { width: 150px; }
.w-range { width: 110px; }

.file-option {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.file-size {
  color: var(--agnes-text-muted, #909399);
  font-size: 12px;
}

.toolbar-right {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-left: auto;
}

.auto-refresh {
  display: flex;
  align-items: center;
  gap: 6px;
  white-space: nowrap;
}

.auto-refresh-label {
  font-size: 13px;
  color: var(--agnes-text-secondary, #606266);
}

/* ---- 列表 ---- */
.logs-table {
  flex: 1;
  font-family: 'SF Mono', Menlo, Consolas, monospace;
  font-size: 12px;
}

.msg-cell {
  white-space: pre-wrap;
  word-break: break-all;
}

.entry-detail {
  padding: 8px 16px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.detail-line {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  font-size: 12px;
}

.detail-label {
  color: var(--agnes-text-muted, #909399);
  min-width: 80px;
}

.detail-line code,
.detail-context {
  word-break: break-all;
}

.detail-stack {
  margin: 0;
  padding: 8px 10px;
  background: var(--agnes-bg-base, #fafafa);
  border: 1px solid var(--agnes-border-faint, #ebeef5);
  border-radius: 6px;
  font-size: 12px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 260px;
  overflow: auto;
}

/* ---- 底部 ---- */
.table-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.total-text {
  font-size: 12px;
  color: var(--agnes-text-muted, #909399);
}
</style>
