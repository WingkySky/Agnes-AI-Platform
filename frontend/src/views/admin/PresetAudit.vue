<!-- =====================================================
     管理员预设审核页 PresetAudit
     - 待审核预设列表（el-table）
     - 预览弹窗（el-dialog 展示预设详情）
     - 通过 / 驳回按钮
     ===================================================== -->

<template>
  <div class="preset-audit">
    <div class="audit-header">
      <h2 class="audit-title">{{ t('presets.auditTitle') }}</h2>
      <el-button :loading="loading" @click="refresh">{{ t('common.refresh') }}</el-button>
    </div>

    <!-- 待审核列表 -->
    <el-table
      :data="pendingList"
      v-loading="loading"
      stripe
      :empty-text="t('presets.audit.emptyText')"
      class="audit-table">
      <el-table-column prop="name" :label="t('presets.name')" min-width="160" />
      <el-table-column prop="preset_type" :label="t('presets.type')" width="100">
        <template #default="{ row }">
          <el-tag size="small" :type="typeTagType(row.preset_type)">
            {{ row.preset_type }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="category" :label="t('presets.category')" width="100" />
      <el-table-column prop="user_id" :label="t('presets.creator')" width="100" />
      <el-table-column prop="created_at" :label="t('presets.submitTime')" width="180">
        <template #default="{ row }">
          {{ formatTime(row.created_at) }}
        </template>
      </el-table-column>
      <el-table-column :label="t('common.actions')" width="280" fixed="right">
        <template #default="{ row }">
          <el-button size="small" @click="previewPreset(row)">{{ t('common.preview') }}</el-button>
          <el-button size="small" type="success" @click="handleApprove(row)">
            {{ t('presets.approve') }}
          </el-button>
          <el-button size="small" type="danger" @click="handleReject(row)">
            {{ t('presets.reject') }}
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 预览弹窗 -->
    <el-dialog
      v-model="previewVisible"
      :title="previewPresetData?.name"
      width="600px"
      destroy-on-close>
      <template v-if="previewPresetData">
        <el-descriptions :column="2" border>
          <el-descriptions-item :label="t('presets.type')">
            <el-tag size="small">{{ previewPresetData.preset_type }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item :label="t('presets.category')">
            {{ previewPresetData.category }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('presets.creator')">
            {{ previewPresetData.user_id }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('presets.submitTime')">
            {{ formatTime(previewPresetData.created_at) }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('presets.description')" :span="2">
            {{ previewPresetData.description || '-' }}
          </el-descriptions-item>
        </el-descriptions>
      </template>
      <template #footer>
        <el-button @click="previewVisible = false">{{ t('common.close') }}</el-button>
        <el-button type="success" @click="previewVisible = false; handleApprove(previewPresetData!)">
          {{ t('presets.approve') }}
        </el-button>
        <el-button type="danger" @click="previewVisible = false; handleReject(previewPresetData!)">
          {{ t('presets.reject') }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import client from '@/api/client'
import { useI18n } from '@/i18n'

const { t } = useI18n()

interface PendingPreset {
  id: number
  preset_type: string
  preset_id: number
  user_id: number
  name: string
  description?: string
  category: string
  created_at?: string
}

const loading = ref(false)
const pendingList = ref<PendingPreset[]>([])
const previewVisible = ref(false)
const previewPresetData = ref<PendingPreset | null>(null)

/* ---- 加载待审核列表 ---- */
async function refresh() {
  loading.value = true
  try {
    const res = await client.get('/api/admin/presets/pending')
    pendingList.value = res.data.items
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.message || t('presets.audit.loadFailed'))
  } finally {
    loading.value = false
  }
}

/* ---- 预览 ---- */
function previewPreset(row: PendingPreset) {
  previewPresetData.value = row
  previewVisible.value = true
}

/* ---- 审核通过 ---- */
async function handleApprove(row: PendingPreset) {
  try {
    await ElMessageBox.confirm(
      t('presets.audit.approveConfirm', { name: row.name }),
      t('presets.approve'),
      { type: 'warning' }
    )
  } catch {
    return
  }

  try {
    await client.post(`/api/admin/presets/${row.id}/approve`)
    ElMessage.success(t('presets.audit.approveSuccess', { name: row.name }))
    pendingList.value = pendingList.value.filter((i) => i.id !== row.id)
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.message || t('presets.audit.operateFailed'))
  }
}

/* ---- 驳回 ---- */
async function handleReject(row: PendingPreset) {
  try {
    await ElMessageBox.confirm(
      t('presets.audit.rejectConfirm', { name: row.name }),
      t('presets.reject'),
      { type: 'warning' }
    )
  } catch {
    return
  }

  try {
    await client.post(`/api/admin/presets/${row.id}/reject`)
    ElMessage.success(t('presets.audit.rejectSuccess', { name: row.name }))
    pendingList.value = pendingList.value.filter((i) => i.id !== row.id)
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.message || t('presets.audit.operateFailed'))
  }
}

/* ---- 工具函数 ---- */
function typeTagType(type: string): 'success' | 'warning' | 'info' | 'danger' | '' {
  const map: Record<string, any> = {
    camera: '',
    prompt: 'success',
    style: 'warning',
    script: 'info',
    pipeline: 'danger',
  }
  return map[type] || 'info'
}

function formatTime(isoStr?: string): string {
  if (!isoStr) return '-'
  const d = new Date(isoStr)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

onMounted(refresh)
</script>

<style scoped>
.preset-audit {
  padding: 0;
}

.audit-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
}

.audit-title {
  font-size: 18px;
  font-weight: 600;
  color: var(--agnes-text-primary);
  margin: 0;
}

.audit-table {
  background: var(--agnes-bg-elevated);
  border-radius: 8px;
}
</style>
