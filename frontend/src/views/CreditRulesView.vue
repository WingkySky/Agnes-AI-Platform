<!-- =====================================================
     积分规则配置页（仅管理员可见）
     - 展示与编辑所有积分规则（图文生图、视频生成等基础积分）
     - 支持 "恢复默认值" 一键还原
     ===================================================== -->

<template>
  <div class="credit-rules-wrap">
    <header class="page-head">
      <div>
        <h2>积分规则配置</h2>
        <p class="muted">调整每次生成任务消耗的基础积分。生效后，新的生成任务将以此为计算标准。</p>
      </div>
      <el-button :icon="RefreshLeft" @click="onReset" :loading="loading">恢复默认值</el-button>
    </header>

    <el-card class="rules-card" shadow="never">
      <el-table :data="rules" style="width: 100%" stripe v-loading="loading">
        <el-table-column prop="rule_key" label="规则 Key" min-width="260">
          <template #default="{ row }">
            <div>
              <div class="rule-key">{{ row.rule_key }}</div>
              <div class="rule-desc muted">{{ row.description || '' }}</div>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="名称" min-width="180">
          <template #default="{ row }">
            <el-input
              v-model="row.name"
              size="small"
              placeholder="规则名称"
            />
          </template>
        </el-table-column>
        <el-table-column label="当前值（积分）" width="220" align="center">
          <template #default="{ row }">
            <el-input-number
              v-model="row.value"
              :min="0"
              :max="100000"
              controls-position="right"
              size="small"
            />
          </template>
        </el-table-column>
        <el-table-column label="更新时间" width="200" align="center">
          <template #default="{ row }">
            <span class="muted">{{ formatTime(row.updated_at) || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="160" align="center" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" size="small" @click="onSave(row)" :loading="row._saving">保存</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { RefreshLeft } from '@element-plus/icons-vue'
import { listCreditRules, updateCreditRule, resetCreditRules } from '@/api/auth'
import type { CreditRuleResponse } from '@/types'

/** 本地扩展字段：_saving（是否正在保存） */
interface LocalRuleRow extends CreditRuleResponse {
  _saving?: boolean
}

const rules = ref<LocalRuleRow[]>([])
const loading = ref(false)

function formatTime(val?: string | null) {
  if (!val) return ''
  try {
    return new Date(val).toLocaleString()
  } catch {
    return val
  }
}

/** 拉取积分规则 */
async function fetchRules() {
  loading.value = true
  try {
    const data = await listCreditRules()
    rules.value = Array.isArray(data) ? data : []
  } catch (e) {
    console.warn(e)
  } finally {
    loading.value = false
  }
}

/** 保存单条规则 */
async function onSave(row: LocalRuleRow) {
  row._saving = true
  try {
    await updateCreditRule(row.rule_key, {
      value: row.value,
      name: row.name,
      description: row.description || '',
    })
    ElMessage.success(`规则 "${row.name || row.rule_key}" 已更新`)
    await fetchRules()
  } catch (e) {
    console.warn(e)
  } finally {
    row._saving = false
  }
}

/** 恢复默认值 */
async function onReset() {
  try {
    await ElMessageBox.confirm(
      '确认恢复所有积分规则到默认值吗？',
      '恢复默认值',
      { confirmButtonText: '确认', cancelButtonText: '取消', type: 'warning' }
    )
  } catch {
    return
  }
  try {
    await resetCreditRules()
    ElMessage.success('已恢复为默认积分规则')
    await fetchRules()
  } catch (e) {
    console.warn(e)
  }
}

onMounted(fetchRules)
</script>

<style scoped>
.credit-rules-wrap {
  max-width: 1200px;
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
  color: #e8eef7;
  font-size: 20px;
}
.muted {
  color: #8ba3c9;
  font-size: 13px;
  margin: 0;
}
.rules-card {
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
.rule-key {
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
  color: #a5b4fc;
  font-size: 13px;
  word-break: break-all;
}
.rule-desc {
  margin-top: 4px;
}
:deep(.el-table th.el-table__cell) {
  background: rgba(25, 35, 55, 0.8);
}
:deep(.el-table--striped .el-table__body tr.el-table__row--striped td.el-table__cell) {
  background: rgba(20, 30, 50, 0.4);
}
</style>
