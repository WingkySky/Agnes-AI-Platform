<!-- =====================================================
     用户与角色管理页（仅管理员可见）
     - 展示所有用户：用户名、邮箱、积分、角色、状态、创建时间
     - 支持修改角色（普通用户 / 超级管理员）、调整积分、启用/禁用
     ===================================================== -->

<template>
  <div class="users-admin-wrap">
    <header class="page-head">
      <div>
        <h2>{{ t('users.title') }}</h2>
        <p class="muted">{{ t('users.title') }}</p>
      </div>
      <el-button :icon="Refresh" @click="fetchUsers" :loading="loading">{{ t('common.refresh') }}</el-button>
    </header>

    <el-card class="table-card" shadow="never">
      <el-table :data="users" style="width: 100%" stripe v-loading="loading">
        <el-table-column prop="id" label="ID" width="70" align="center" />
        <el-table-column :label="t('users.colUsername')" min-width="140">
          <template #default="{ row }">
            <div class="user-cell">
              <el-avatar :size="30" :icon="UserFilled" />
              <div class="user-cell-info">
                <div class="user-cell-name">{{ row.username }}</div>
                <div class="user-cell-email muted">{{ row.email || t('users.noEmail') }}</div>
              </div>
            </div>
          </template>
        </el-table-column>
        <el-table-column :label="t('users.colCredits')" width="140" align="center">
          <template #default="{ row }">
            <el-input-number
              :model-value="row.credits"
              :min="0"
              :max="1000000"
              controls-position="right"
              size="small"
              @change="(val: number) => onCreditsChange(row, val)"
            />
          </template>
        </el-table-column>
        <el-table-column :label="t('users.colRole')" width="170" align="center">
          <template #default="{ row }">
            <el-select
              :model-value="row.role"
              size="small"
              :disabled="isSelf(row)"
              @change="(val: string) => onRoleChange(row, val)"
            >
              <el-option :label="t('users.roleUser')" value="user" />
              <el-option :label="t('users.roleAdmin')" value="admin" />
            </el-select>
            <div v-if="isSelf(row)" class="muted small">{{ t('users.cannotEditSelf') }}</div>
          </template>
        </el-table-column>
        <el-table-column :label="t('users.colStatus')" width="140" align="center">
          <template #default="{ row }">
            <el-switch
              :model-value="row.is_active"
              :disabled="isSelf(row)"
              :active-text="t('users.statusActive')"
              :inactive-text="t('users.statusInactive')"
              @change="(val: boolean) => onActiveChange(row, val)"
            />
          </template>
        </el-table-column>
        <el-table-column prop="created_at" :label="t('users.colCreated')" width="190" align="center">
          <template #default="{ row }">
            <span class="muted">{{ formatTime(row.created_at) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="last_login_at" :label="t('users.colLastLogin')" width="190" align="center">
          <template #default="{ row }">
            <span class="muted">{{ formatTime(row.last_login_at) || t('users.neverLogin') }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh, UserFilled } from '@element-plus/icons-vue'
import { listUsers, updateUserRole, updateUserCredits, updateUserActive } from '@/api/auth'
import { useUserStore } from '@/stores/user'
import type { UserAdminRow } from '@/types'
import { useI18n } from '@/i18n'

const { t } = useI18n()
const userStore = useUserStore()
const users = ref<UserAdminRow[]>([])
const loading = ref(false)

/** 是否是当前登录用户自己（自己禁止改角色/禁用自己） */
function isSelf(row: UserAdminRow) {
  return userStore.user?.id === row.id
}

/** 格式化时间（返回空字符串或格式化后的时间字符串） */
function formatTime(val?: string | null) {
  if (!val) return ''
  try {
    return new Date(val).toLocaleString()
  } catch {
    return val
  }
}

/** 拉取用户列表 */
async function fetchUsers() {
  loading.value = true
  try {
    const resp = await listUsers()
    users.value = resp.items || []
  } catch (e) {
    console.warn(e)
  } finally {
    loading.value = false
  }
}

/** 修改角色 */
async function onRoleChange(row: UserAdminRow, newRole: string) {
  if (isSelf(row)) return
  const roleName = newRole === 'admin' ? t('users.roleAdmin') : t('users.roleUser')
  try {
    await ElMessageBox.confirm(
      `${t('users.confirmChangeRole')} ${roleName} ?`,
      t('users.changeRole'),
      { confirmButtonText: t('common.confirm'), cancelButtonText: t('common.cancel'), type: 'warning' }
    )
  } catch {
    // 取消：恢复原值
    fetchUsers()
    return
  }
  try {
    await updateUserRole(row.id, { role: newRole })
    row.role = newRole
    row.is_admin = newRole === 'admin'
    ElMessage.success(t('users.changeRoleSuccess'))
  } catch (e) {
    console.warn(e)
    fetchUsers()
  }
}

/** 修改积分 */
async function onCreditsChange(row: UserAdminRow, newValue: number) {
  try {
    await updateUserCredits(row.id, { credits: newValue })
    row.credits = newValue
    ElMessage.success(`${newValue} ${t('users.creditsUpdated')}`)
  } catch (e) {
    console.warn(e)
    fetchUsers()
  }
}

/** 启用/禁用用户 */
async function onActiveChange(row: UserAdminRow, active: boolean) {
  if (isSelf(row)) return
  try {
    await updateUserActive(row.id, { is_active: active })
    row.is_active = active
    ElMessage.success(active ? t('users.statusActive') : t('users.statusInactive'))
  } catch (e) {
    console.warn(e)
    fetchUsers()
  }
}

onMounted(fetchUsers)
</script>

<style scoped>
.users-admin-wrap {
  max-width: 1400px;
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
.small {
  font-size: 12px;
  margin-top: 4px;
}
.table-card {
  background: var(--agnes-bg-elevated);
  border: 1px solid var(--agnes-border);
  border-radius: 10px;
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
.user-cell {
  display: flex;
  align-items: center;
  gap: 10px;
}
.user-cell-info {
  display: flex;
  flex-direction: column;
}
.user-cell-name {
  color: var(--agnes-text-primary);
  font-weight: 500;
}
.user-cell-email {
  font-size: 12px;
}
</style>
