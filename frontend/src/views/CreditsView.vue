<!-- =====================================================
     积分明细视图 CreditsView
     - 展示当前用户的积分变动流水（充值/消费/退还/调整）
     - 管理员可切换到「管理员视图」，查看所有用户的流水并按用户 ID 筛选
     - 支持按类型筛选 + 分页
     - 金额按正负显示不同颜色；状态用 Tag 标识
     ===================================================== -->

<template>
  <div class="credits-view">
    <header class="page-head">
      <div>
        <h2>🪙 {{ t('credits.title') }}</h2>
        <p class="muted">{{ t('credits.desc') }}</p>
      </div>
      <div class="head-actions">
        <!-- 管理员视图切换 -->
        <el-switch
          v-if="userStore.isAdmin"
          v-model="adminMode"
          :active-text="t('credits.adminMode')"
          inline-prompt
          @change="onAdminModeChange"
        />
        <el-button :icon="Refresh" :loading="loading" @click="loadList(true)">
          {{ t('common.refresh') }}
        </el-button>
      </div>
    </header>

    <!-- 筛选条件 -->
    <div class="filter-bar">
      <el-select
        v-model="filterType"
        :placeholder="t('credits.typeLabel')"
        clearable
        style="width: 160px"
        @change="loadList(true)"
      >
        <el-option :label="t('credits.all')" value="" />
        <el-option :label="t('credits.recharge')" value="recharge" />
        <el-option :label="t('credits.consume')" value="consume" />
        <el-option :label="t('credits.refund')" value="refund" />
        <el-option :label="t('credits.adjust')" value="adjust" />
      </el-select>

      <!-- 管理员视图：按用户 ID 筛选 -->
      <el-input-number
        v-if="adminMode"
        v-model="filterUserId"
        :min="1"
        :placeholder="t('credits.userFilterPlaceholder')"
        :controls="false"
        style="width: 200px"
        @change="loadList(true)"
      />

      <span class="total-text">
        {{ t('credits.totalLabel').replace('{n}', String(total)) }}
      </span>
    </div>

    <!-- 流水表格 -->
    <el-card class="table-card" shadow="never">
      <el-table :data="list" style="width: 100%" stripe v-loading="loading">
        <!-- 管理员视图：显示用户列 -->
        <el-table-column
          v-if="adminMode"
          :label="t('credits.userLabel')"
          min-width="140"
        >
          <template #default="{ row }">
            <span class="user-cell">
              <span class="user-id">#{{ row.user_id }}</span>
              <span v-if="row.username" class="user-name">{{ row.username }}</span>
            </span>
          </template>
        </el-table-column>

        <!-- 时间 -->
        <el-table-column :label="t('credits.timeLabel')" min-width="170">
          <template #default="{ row }">
            <span class="muted">{{ formatTime(row.created_at) }}</span>
          </template>
        </el-table-column>

        <!-- 类型 -->
        <el-table-column :label="t('credits.typeLabel')" width="110" align="center">
          <template #default="{ row }">
            <el-tag :type="typeTagType(row.type)" effect="dark" size="small">
              {{ typeLabel(row.type) }}
            </el-tag>
          </template>
        </el-table-column>

        <!-- 变动数量 -->
        <el-table-column :label="t('credits.amountLabel')" width="120" align="right">
          <template #default="{ row }">
            <span :class="['amount', row.amount >= 0 ? 'positive' : 'negative']">
              {{ row.amount >= 0 ? '+' : '' }}{{ row.amount }}
            </span>
          </template>
        </el-table-column>

        <!-- 变动后余额 -->
        <el-table-column :label="t('credits.balanceLabel')" width="130" align="right">
          <template #default="{ row }">
            <span class="balance">{{ row.balance_after }}</span>
          </template>
        </el-table-column>

        <!-- 状态 -->
        <el-table-column :label="t('credits.statusLabel')" width="110" align="center">
          <template #default="{ row }">
            <el-tag :type="statusTagType(row.status)" size="small" effect="plain">
              {{ statusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>

        <!-- 说明 -->
        <el-table-column :label="t('credits.descLabel')" min-width="240">
          <template #default="{ row }">
            <div class="desc-cell">
              <span>{{ row.description || '—' }}</span>
              <!-- 关联任务：点击跳转到历史记录页对应记录 -->
              <span
                v-if="row.ref_id && (row.type === 'consume' || row.type === 'refund')"
                class="ref-link"
                @click="goToHistory(row.ref_id)">
                <span class="ref-icon">{{ refTypeIcon(row.ref_type) }}</span>
                <span class="ref-text">{{ t('credits.viewHistory') }}</span>
              </span>
            </div>
          </template>
        </el-table-column>
      </el-table>

      <!-- 空状态 -->
      <div v-if="!loading && list.length === 0" class="empty-state">
        <el-icon :size="40"><Coin /></el-icon>
        <p class="muted">{{ t('credits.emptyTip') }}</p>
      </div>

      <!-- 分页 -->
      <div v-if="total > pageSize" class="pagination-wrap">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :total="total"
          :page-sizes="[10, 20, 50, 100]"
          layout="prev, pager, next, sizes, total"
          background
          @current-change="loadList(false)"
          @size-change="loadList(true)"
        />
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Refresh, Coin } from '@element-plus/icons-vue'
import { useI18n } from '@/i18n'
import { useUserStore } from '@/stores/user'
import {
  listMyTransactions,
  listAllTransactions,
  type CreditTransactionItem,
} from '@/api/credits'

const { t } = useI18n()
const userStore = useUserStore()
const router = useRouter()

// ================ 列表状态 ================
const list = ref<CreditTransactionItem[]>([])
const loading = ref(false)
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)

// ================ 筛选条件 ================
const filterType = ref<string>('')         // 类型筛选（空字符串=全部）
const adminMode = ref(false)               // 管理员视图开关
const filterUserId = ref<number | undefined>(undefined) // 管理员视图：按用户 ID 筛选

// ================ 工具函数 ================

/** 格式化时间 */
function formatTime(val?: string | null) {
  if (!val) return '—'
  try {
    return new Date(val).toLocaleString()
  } catch {
    return val
  }
}

/** 关联任务的图标（按 ref_type 区分图片/视频） */
function refTypeIcon(refType?: string | null): string {
  if (refType === 'image') return '🖼️'
  if (refType === 'video') return '🎬'
  return '🔗'
}

/** 跳转到历史记录页，并通过 task_id 定位对应记录 */
function goToHistory(taskId: string) {
  router.push({ path: '/history', query: { task_id: taskId } })
}

/** 类型显示文案 */
function typeLabel(type: string): string {
  const map: Record<string, string> = {
    recharge: t('credits.recharge'),
    consume: t('credits.consume'),
    refund: t('credits.refund'),
    adjust: t('credits.adjust'),
  }
  return map[type] || type
}

/** 类型对应的 Tag 颜色 */
function typeTagType(type: string): 'success' | 'warning' | 'info' | 'primary' | 'danger' {
  const map: Record<string, 'success' | 'warning' | 'info' | 'primary' | 'danger'> = {
    recharge: 'success',
    consume: 'warning',
    refund: 'primary',
    adjust: 'info',
  }
  return map[type] || 'info'
}

/** 状态显示文案 */
function statusLabel(status: string): string {
  const map: Record<string, string> = {
    pending: t('credits.pending'),
    confirmed: t('credits.confirmed'),
    refunded: t('credits.refunded'),
  }
  return map[status] || status
}

/** 状态对应的 Tag 颜色 */
function statusTagType(status: string): 'success' | 'warning' | 'info' | 'danger' {
  const map: Record<string, 'success' | 'warning' | 'info' | 'danger'> = {
    pending: 'warning',
    confirmed: 'success',
    refunded: 'info',
  }
  return map[status] || 'info'
}

// ================ 数据加载 ================

/** 加载积分明细列表
 * @param reset 是否重置到第 1 页（切换筛选条件时使用）
 */
async function loadList(reset = false) {
  if (reset) page.value = 1
  loading.value = true
  try {
    const params = {
      page: page.value,
      page_size: pageSize.value,
      type: filterType.value || undefined,
    }
    const data = adminMode.value
      ? await listAllTransactions({ ...params, user_id: filterUserId.value })
      : await listMyTransactions(params)
    list.value = data.items || []
    total.value = data.total || 0
  } catch (e) {
    console.warn('[Credits] load failed:', e)
    list.value = []
    total.value = 0
  } finally {
    loading.value = false
  }
}

/** 切换管理员视图时重新加载 */
function onAdminModeChange() {
  // 切换视图时清空用户筛选
  filterUserId.value = undefined
  loadList(true)
}

onMounted(() => loadList(true))
</script>

<style scoped>
.credits-view {
  max-width: 1200px;
  margin: 0 auto;
}

/* ================ 页头 ================ */
.page-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  margin-bottom: 16px;
  gap: 12px;
  flex-wrap: wrap;
}
.page-head h2 {
  margin: 0 0 4px;
  color: #e8eef7;
  font-size: 20px;
}
.muted {
  color: #8ba3c9;
  font-size: 13px;
  margin: 0;
}
.head-actions {
  display: flex;
  gap: 12px;
  align-items: center;
}

/* ================ 筛选栏 ================ */
.filter-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}
.total-text {
  color: #8ba3c9;
  font-size: 13px;
  margin-left: auto;
}

/* ================ 表格卡片 ================ */
.table-card {
  background: rgba(15, 22, 38, 0.6);
  border: 1px solid rgba(100, 150, 220, 0.15);
  border-radius: 10px;
}
:deep(.el-table) {
  background: transparent;
}
:deep(.el-table th.el-table__cell) {
  background-color: rgba(25, 35, 55, 0.8);
  color: #a0b4d6;
}
:deep(.el-table--striped .el-table__body tr.el-table__row--striped td.el-table__cell) {
  background: rgba(20, 30, 50, 0.4);
}

/* ================ 单元格样式 ================ */
.user-cell {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.user-id {
  color: #a5b4fc;
  font-family: 'SFMono-Regular', Consolas, Menlo, monospace;
  font-size: 12px;
}
.user-name {
  color: #cdd9ec;
  font-size: 13px;
}
.amount {
  font-weight: 600;
  font-family: 'SFMono-Regular', Consolas, Menlo, monospace;
}
.amount.positive {
  color: #67c23a;
}
.amount.negative {
  color: #f56c6c;
}
.balance {
  color: #cdd9ec;
  font-family: 'SFMono-Regular', Consolas, Menlo, monospace;
}
.desc-cell {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.desc-cell .ref-link {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: #a5b4fc;
  font-size: 12px;
  cursor: pointer;
  transition: color 0.2s ease;
  width: fit-content;
}
.desc-cell .ref-link:hover {
  color: #c9b3ff;
  text-decoration: underline;
}
.desc-cell .ref-link .ref-icon {
  font-size: 13px;
}

/* ================ 空状态 ================ */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 48px 0;
  color: #6b7a99;
}

/* ================ 分页 ================ */
.pagination-wrap {
  display: flex;
  justify-content: center;
  margin-top: 16px;
}
</style>
