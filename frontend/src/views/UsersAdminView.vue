<!-- =====================================================
     用户与角色管理页（仅管理员可见）
     - 展示所有用户：用户名、邮箱、积分、角色、状态、创建时间
     - 支持修改角色、调整积分、启用/禁用
     - 支持水印开关、严格内容安全开关
     ===================================================== -->

<template>
  <div class="users-admin-wrap">
    <header class="page-head">
      <div>
        <h2>{{ t('users.title') }}</h2>
        <p class="muted">{{ t('admin.users.pageDesc') }}</p>
      </div>
      <el-button :icon="Refresh" @click="fetchUsers" :loading="loading">{{ t('common.refresh') }}</el-button>
    </header>

    <el-card class="table-card" shadow="never">
      <el-table :data="users" style="width: 100%" stripe v-loading="loading">
        <el-table-column prop="id" label="ID" width="70" align="center" />
        <el-table-column :label="t('users.colUsername')" min-width="180">
          <template #default="{ row }">
            <div class="user-cell">
              <el-avatar :size="32" :src="avatarFullUrl(row.avatar_url)" :icon="UserFilled" class="user-avatar" />
              <div class="user-cell-info">
                <div class="user-cell-name">{{ row.nickname || row.username }}</div>
                <div class="user-cell-sub muted">
                  <span v-if="row.nickname">@{{ row.username }}</span>
                  <span v-if="row.email">{{ row.nickname ? ' · ' : '' }}{{ row.email }}</span>
                  <span v-if="!row.email && !row.nickname">{{ t('users.noEmail') }}</span>
                </div>
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
        <el-table-column :label="t('users.colRole')" width="160" align="center">
          <template #default="{ row }">
            <el-dropdown
              trigger="click"
              :disabled="isSelf(row)"
              @command="(val: string) => onRoleChange(row, val)"
            >
              <span class="role-dropdown">
                <el-tag :type="roleTagType(row.role)" size="small" effect="light">
                  {{ roleDisplayName(row.role) }}
                </el-tag>
                <el-icon v-if="!isSelf(row)" class="arrow-icon"><ArrowDown /></el-icon>
              </span>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="user">
                    <el-tag type="info" size="small" effect="dark">{{ t('admin.users.roleUser') }}</el-tag>
                  </el-dropdown-item>
                  <el-dropdown-item command="moderator">
                    <el-tag type="warning" size="small" effect="dark">{{ t('admin.users.roleModerator') }}</el-tag>
                  </el-dropdown-item>
                  <el-dropdown-item command="admin">
                    <el-tag type="danger" size="small" effect="dark">{{ t('admin.users.roleAdmin') }}</el-tag>
                  </el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
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
        <el-table-column :label="t('admin.users.colWatermark')" width="120" align="center">
          <template #default="{ row }">
            <el-switch
              :model-value="row.watermark_enabled"
              :active-text="t('admin.users.switchOn')"
              :inactive-text="t('admin.users.switchOff')"
              @change="(val: boolean) => onWatermarkChange(row, val)"
            />
          </template>
        </el-table-column>
        <el-table-column :label="t('admin.users.colContentSafety')" width="140" align="center">
          <template #default="{ row }">
            <el-switch
              :model-value="row.content_safety_strict"
              :active-text="t('admin.users.switchOn')"
              :inactive-text="t('admin.users.switchOff')"
              @change="(val: boolean) => onContentSafetyChange(row, val)"
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
import { Refresh, UserFilled, ArrowDown } from '@element-plus/icons-vue'
import { listUsers, updateUserCredits, updateUserActive } from '@/api/auth'
import { updateUserRole, updateUserWatermark, updateUserContentSafety } from '@/api/admin'
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

/**
 * 归一化头像 URL
 * - 空值：返回空字符串（由 el-avatar 回退到 :icon 默认图标）
 * - 以 http(s):// 开头：直接使用
 * - 以 / 开头的相对路径（后端上传目录）：拼接 API 基础地址
 */
function avatarFullUrl(rawUrl: string | null | undefined): string {
  if (!rawUrl) return ''
  if (/^https?:\/\//i.test(rawUrl)) return rawUrl
  if (rawUrl.startsWith('/')) {
    const apiHost = (import.meta.env.VITE_API_BASE_URL as string) || ''
    return `${apiHost}${rawUrl}`
  }
  return rawUrl
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

/** 角色显示名称 */
function roleDisplayName(role: string) {
  switch (role) {
    case 'admin':
      return t('admin.users.roleAdmin')
    case 'moderator':
      return t('admin.users.roleModerator')
    case 'user':
      return t('admin.users.roleUser')
    default:
      return role
  }
}

/** 角色标签类型 */
function roleTagType(role: string) {
  switch (role) {
    case 'admin':
      return 'danger'
    case 'moderator':
      return 'warning'
    case 'user':
      return 'info'
    default:
      return 'info'
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
  if (row.role === newRole) return
  try {
    await ElMessageBox.confirm(
      t('admin.users.confirmChangeRole', { username: row.username, role: roleDisplayName(newRole) }),
      t('admin.users.changeRole'),
      { confirmButtonText: t('common.confirm'), cancelButtonText: t('common.cancel'), type: 'warning' }
    )
  } catch {
    return
  }
  try {
    await updateUserRole(row.id, newRole)
    row.role = newRole
    row.is_admin = newRole === 'admin'
    ElMessage.success(t('admin.users.changeRoleSuccess', { role: roleDisplayName(newRole) }))
  } catch (e: any) {
    console.warn(e)
    ElMessage.error(t('admin.users.changeRoleFailed', { error: e?.message || t('common.error') }))
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

/** 水印开关切换 */
async function onWatermarkChange(row: UserAdminRow, enabled: boolean) {
  try {
    await updateUserWatermark(row.id, enabled)
    row.watermark_enabled = enabled
    ElMessage.success(enabled ? t('admin.users.watermarkEnabled') : t('admin.users.watermarkDisabled'))
  } catch (e: any) {
    console.warn(e)
    ElMessage.error(t('admin.users.operationFailed', { error: e?.message || t('common.error') }))
    fetchUsers()
  }
}

/** 严格内容安全开关切换 */
async function onContentSafetyChange(row: UserAdminRow, enabled: boolean) {
  try {
    await updateUserContentSafety(row.id, enabled)
    row.content_safety_strict = enabled
    ElMessage.success(enabled ? t('admin.users.contentSafetyEnabled') : t('admin.users.contentSafetyDisabled'))
  } catch (e: any) {
    console.warn(e)
    ElMessage.error(t('admin.users.operationFailed', { error: e?.message || t('common.error') }))
    fetchUsers()
  }
}

onMounted(fetchUsers)
</script>

<style scoped>
.users-admin-wrap {
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

/* 用户列表统一头像样式，确保在斑马纹背景下都清晰可见 */
.user-avatar {
  background: var(--agnes-bg-chip);
  color: var(--agnes-text-muted);
  flex-shrink: 0;
  border: 1px solid var(--agnes-border-faint);
}

.user-cell-info {
  display: flex;
  flex-direction: column;
}

.user-cell-name {
  color: var(--agnes-text-primary);
  font-weight: 500;
  line-height: 1.4;
}

.user-cell-sub {
  font-size: 12px;
  line-height: 1.4;
}

.role-dropdown {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  cursor: pointer;
}

.role-dropdown:hover .arrow-icon {
  color: var(--agnes-text-primary);
}

.arrow-icon {
  font-size: 12px;
  color: var(--agnes-text-muted);
  transition: color 0.2s;
}

:deep(.el-dropdown-menu__item) {
  padding: 8px 16px;
}

:deep(.el-dropdown-menu__item .el-tag) {
  width: 100%;
  justify-content: center;
}
</style>
