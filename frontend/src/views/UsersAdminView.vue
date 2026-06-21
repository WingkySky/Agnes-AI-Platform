<!-- =====================================================
     用户与角色管理页（仅管理员可见）
     - 展示所有用户：用户名、邮箱、积分、角色、状态、创建时间
     - 支持修改角色（普通用户 / 超级管理员）、调整积分、启用/禁用
     ===================================================== -->

<template>
  <div class="users-admin-wrap">
    <header class="page-head">
      <div>
        <h2>用户与角色管理</h2>
        <p class="muted">管理平台所有用户的角色、积分与账号状态。</p>
      </div>
      <el-button :icon="Refresh" @click="fetchUsers" :loading="loading">刷新</el-button>
    </header>

    <el-card class="table-card" shadow="never">
      <el-table :data="users" style="width: 100%" stripe v-loading="loading">
        <el-table-column prop="id" label="ID" width="70" align="center" />
        <el-table-column label="用户名" min-width="140">
          <template #default="{ row }">
            <div class="user-cell">
              <el-avatar :size="30" :icon="UserFilled" />
              <div class="user-cell-info">
                <div class="user-cell-name">{{ row.username }}</div>
                <div class="user-cell-email muted">{{ row.email || '未绑定邮箱' }}</div>
              </div>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="积分" width="140" align="center">
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
        <el-table-column label="角色" width="170" align="center">
          <template #default="{ row }">
            <el-select
              :model-value="row.role"
              size="small"
              :disabled="isSelf(row)"
              @change="(val: string) => onRoleChange(row, val)"
            >
              <el-option label="普通用户" value="user" />
              <el-option label="超级管理员" value="admin" />
            </el-select>
            <div v-if="isSelf(row)" class="muted small">自己无法修改</div>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="140" align="center">
          <template #default="{ row }">
            <el-switch
              :model-value="row.is_active"
              :disabled="isSelf(row)"
              active-text="已启用"
              inactive-text="已禁用"
              @change="(val: boolean) => onActiveChange(row, val)"
            />
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" width="190" align="center">
          <template #default="{ row }">
            <span class="muted">{{ formatTime(row.created_at) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="last_login_at" label="最近登录" width="190" align="center">
          <template #default="{ row }">
            <span class="muted">{{ formatTime(row.last_login_at) || '从未登录' }}</span>
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
    // 错误由全局拦截器处理
    console.warn(e)
  } finally {
    loading.value = false
  }
}

/** 修改角色 */
async function onRoleChange(row: UserAdminRow, newRole: string) {
  if (isSelf(row)) return
  const roleName = newRole === 'admin' ? '超级管理员' : '普通用户'
  try {
    await ElMessageBox.confirm(
      `确认将用户 "${row.username}" 的角色修改为 ${roleName} 吗？`,
      '修改角色',
      { confirmButtonText: '确认', cancelButtonText: '取消', type: 'warning' }
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
    ElMessage.success(`已将 "${row.username}" 修改为 ${roleName}`)
  } catch (e) {
    console.warn(e)
    // 失败，刷新还原
    fetchUsers()
  }
}

/** 修改积分 */
async function onCreditsChange(row: UserAdminRow, newValue: number) {
  try {
    await updateUserCredits(row.id, { credits: newValue })
    row.credits = newValue
    ElMessage.success(`已将 "${row.username}" 的积分更新为 ${newValue}`)
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
    ElMessage.success(active ? `已启用 "${row.username}"` : `已禁用 "${row.username}"`)
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
  color: #e8eef7;
  font-size: 20px;
}
.muted {
  color: #8ba3c9;
  font-size: 13px;
  margin: 0;
}
.small {
  font-size: 12px;
  margin-top: 4px;
}
.table-card {
  background: rgba(15, 22, 38, 0.6);
  border: 1px solid rgba(100, 150, 220, 0.15);
  border-radius: 10px;
}
:deep(.el-table) {
  background: transparent;
  color: #cfd9e8;
}
:deep(.el-table th.el-table__cell) {
  background: rgba(25, 35, 55, 0.8);
  color: #a0b4d6;
}
:deep(.el-table--striped .el-table__body tr.el-table__row--striped td.el-table__cell) {
  background: rgba(20, 30, 50, 0.4);
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
  color: #e8eef7;
  font-weight: 500;
}
.user-cell-email {
  font-size: 12px;
}
</style>
