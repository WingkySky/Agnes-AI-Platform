<!-- =====================================================
     角色管理页
     - 管理系统角色与权限配置
     - 支持创建、编辑、删除角色，分配权限
     ===================================================== -->

<template>
  <div class="roles-admin-wrap">
    <header class="page-head">
      <div>
        <h2>{{ t('admin.roles.title') }}</h2>
        <p class="muted">{{ t('admin.roles.desc') }}</p>
      </div>
      <el-button type="primary" :icon="Plus" @click="openCreateDialog">{{ t('admin.roles.createRole') }}</el-button>
    </header>

    <el-card class="table-card" shadow="never">
      <el-table :data="roles" style="width: 100%" stripe v-loading="loading">
        <el-table-column prop="name" :label="t('admin.roles.colRoleName')" min-width="140">
          <template #default="{ row }">
            <span class="role-name">{{ row.name }}</span>
            <el-tag v-if="row.is_system" type="info" size="small" effect="light" style="margin-left: 8px">
              {{ t('admin.roles.systemRoleTag') }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="display_name" :label="t('admin.roles.colDisplayName')" min-width="140" />
        <el-table-column prop="description" :label="t('admin.roles.colDescription')" min-width="200">
          <template #default="{ row }">
            <span class="muted">{{ row.description || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column :label="t('admin.roles.colPermissionCount')" width="120" align="center">
          <template #default="{ row }">
            <el-tag type="primary" size="small">{{ row.permissions?.length || 0 }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column :label="t('admin.roles.colSystemRole')" width="100" align="center">
          <template #default="{ row }">
            <el-tag :type="row.is_system ? 'warning' : 'info'" size="small">
              {{ row.is_system ? t('admin.roles.yes') : t('admin.roles.no') }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" :label="t('admin.roles.colCreatedAt')" width="190" align="center">
          <template #default="{ row }">
            <span class="muted">{{ formatTime(row.created_at) }}</span>
          </template>
        </el-table-column>
        <el-table-column :label="t('admin.roles.colActions')" width="180" align="center" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" size="small" link @click="openEditDialog(row)">{{ t('admin.roles.edit') }}</el-button>
            <el-button
              type="danger"
              size="small"
              link
              :disabled="row.is_system"
              @click="onDelete(row)"
            >
              {{ t('admin.roles.delete') }}
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 新建/编辑角色弹窗 -->
    <el-dialog
      v-model="dialogVisible"
      :title="isEdit ? t('admin.roles.dialogEditTitle') : t('admin.roles.dialogCreateTitle')"
      width="680px"
      :close-on-click-modal="false"
    >
      <el-form :model="form" label-width="100px" label-position="right">
        <el-form-item :label="t('admin.roles.formRoleName')" prop="name">
          <el-input
            v-model="form.name"
            :placeholder="t('admin.roles.formRoleNamePlaceholder')"
            :disabled="isEdit && currentRole?.is_system"
          />
          <div v-if="isEdit && currentRole?.is_system" class="form-tip">
            {{ t('admin.roles.formRoleNameTip') }}
          </div>
        </el-form-item>

        <el-form-item :label="t('admin.roles.formDisplayName')" prop="display_name">
          <el-input v-model="form.display_name" :placeholder="t('admin.roles.formDisplayNamePlaceholder')" />
        </el-form-item>

        <el-form-item :label="t('admin.roles.formDescription')" prop="description">
          <el-input
            v-model="form.description"
            type="textarea"
            :rows="3"
            :placeholder="t('admin.roles.formDescriptionPlaceholder')"
            maxlength="200"
            show-word-limit
          />
        </el-form-item>

        <el-form-item :label="t('admin.roles.formPermissionConfig')">
          <div class="permissions-wrap">
            <div v-for="group in permissionGroups" :key="group.key" class="permission-group">
              <div class="group-header">
                <el-checkbox
                  :model-value="isGroupAllChecked(group.key)"
                  :indeterminate="isGroupIndeterminate(group.key)"
                  @change="(val: boolean) => onGroupCheckAll(group.key, val)"
                >
                  {{ group.name }}
                </el-checkbox>
                <span class="group-count">
                  {{ getGroupCheckedCount(group.key) }}/{{ group.permissions.length }}
                </span>
              </div>
              <div class="group-permissions">
                <el-checkbox
                  v-for="perm in group.permissions"
                  :key="perm.key"
                  :model-value="form.permissions.includes(perm.key)"
                  @change="(val: boolean) => onPermissionChange(perm.key, val)"
                >
                  {{ perm.name }}
                </el-checkbox>
              </div>
            </div>
          </div>
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="dialogVisible = false">{{ t('admin.roles.cancel') }}</el-button>
        <el-button type="primary" :loading="saving" @click="onSubmit">{{ t('admin.roles.confirm') }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import { getRoles, createRole, updateRole, deleteRole } from '@/api/admin'
import type { RoleItem } from '@/api/admin'

const { t } = useI18n()

const loading = ref(false)
const saving = ref(false)
const roles = ref<RoleItem[]>([])

const dialogVisible = ref(false)
const isEdit = ref(false)
const currentRole = ref<RoleItem | null>(null)

const form = reactive({
  name: '',
  display_name: '',
  description: '',
  permissions: [] as string[]
})

/** 内置权限列表（前端硬编码，后续从接口获取） */
const builtinPermissions = [
  { key: 'content:generate', group: 'content' },
  { key: 'plaza:view', group: 'plaza' },
  { key: 'plaza:share', group: 'plaza' },
  { key: 'plaza:moderate', group: 'plaza' },
  { key: 'moderation:config', group: 'moderation' },
  { key: 'user:manage', group: 'user' },
  { key: 'role:manage', group: 'role' },
  { key: 'watermark:manage', group: 'watermark' },
  { key: 'system:config', group: 'system' }
]

interface PermissionGroup {
  key: string
  name: string
  permissions: { key: string; name: string }[]
}

const permissionGroups = computed<PermissionGroup[]>(() => {
  const groups: Record<string, PermissionGroup> = {}
  builtinPermissions.forEach(perm => {
    if (!groups[perm.group]) {
      groups[perm.group] = {
        key: perm.group,
        name: t(`admin.roles.permissionGroups.${perm.group}` as any),
        permissions: []
      }
    }
    groups[perm.group].permissions.push({
      key: perm.key,
      name: t(`admin.roles.permissions.${perm.key}` as any)
    })
  })
  return Object.values(groups)
})

function formatTime(val?: string | null) {
  if (!val) return ''
  try {
    return new Date(val).toLocaleString()
  } catch {
    return val
  }
}

async function fetchRoles() {
  loading.value = true
  try {
    const data = await getRoles()
    roles.value = data
  } catch (e) {
    console.warn(e)
  } finally {
    loading.value = false
  }
}

/** 检查某组是否全选 */
function isGroupAllChecked(groupKey: string) {
  const group = permissionGroups.value.find(g => g.key === groupKey)
  if (!group) return false
  return group.permissions.every(p => form.permissions.includes(p.key))
}

/** 检查某组是否半选 */
function isGroupIndeterminate(groupKey: string) {
  const group = permissionGroups.value.find(g => g.key === groupKey)
  if (!group) return false
  const checkedCount = group.permissions.filter(p => form.permissions.includes(p.key)).length
  return checkedCount > 0 && checkedCount < group.permissions.length
}

/** 获取某组已选数量 */
function getGroupCheckedCount(groupKey: string) {
  const group = permissionGroups.value.find(g => g.key === groupKey)
  if (!group) return 0
  return group.permissions.filter(p => form.permissions.includes(p.key)).length
}

/** 组全选/取消全选 */
function onGroupCheckAll(groupKey: string, checked: boolean) {
  const group = permissionGroups.value.find(g => g.key === groupKey)
  if (!group) return
  if (checked) {
    group.permissions.forEach(p => {
      if (!form.permissions.includes(p.key)) {
        form.permissions.push(p.key)
      }
    })
  } else {
    form.permissions = form.permissions.filter(
      key => !group.permissions.some(p => p.key === key)
    )
  }
}

/** 单个权限切换 */
function onPermissionChange(permKey: string, checked: boolean) {
  if (checked) {
    if (!form.permissions.includes(permKey)) {
      form.permissions.push(permKey)
    }
  } else {
    form.permissions = form.permissions.filter(k => k !== permKey)
  }
}

/** 打开新建弹窗 */
function openCreateDialog() {
  isEdit.value = false
  currentRole.value = null
  form.name = ''
  form.display_name = ''
  form.description = ''
  form.permissions = []
  dialogVisible.value = true
}

/** 打开编辑弹窗 */
function openEditDialog(row: RoleItem) {
  isEdit.value = true
  currentRole.value = row
  form.name = row.name
  form.display_name = row.display_name
  form.description = row.description
  form.permissions = [...(row.permissions || [])]
  dialogVisible.value = true
}

/** 提交表单 */
async function onSubmit() {
  if (!form.name.trim()) {
    ElMessage.warning(t('admin.roles.validationRoleNameRequired'))
    return
  }
  if (!form.display_name.trim()) {
    ElMessage.warning(t('admin.roles.validationDisplayNameRequired'))
    return
  }

  saving.value = true
  try {
    if (isEdit.value && currentRole.value) {
      await updateRole(currentRole.value.name, {
        display_name: form.display_name,
        description: form.description,
        permissions: form.permissions
      })
      ElMessage.success(t('admin.roles.roleUpdateSuccess'))
    } else {
      await createRole({
        name: form.name.trim(),
        display_name: form.display_name.trim(),
        description: form.description,
        permissions: form.permissions
      })
      ElMessage.success(t('admin.roles.roleCreateSuccess'))
    }
    dialogVisible.value = false
    fetchRoles()
  } catch (e: any) {
    console.warn(e)
    ElMessage.error(e?.message || t('admin.roles.operationFailed'))
  } finally {
    saving.value = false
  }
}

/** 删除角色 */
async function onDelete(row: RoleItem) {
  if (row.is_system) return
  try {
    await ElMessageBox.confirm(
      t('admin.roles.deleteConfirmMessage', { name: row.display_name }),
      t('admin.roles.deleteConfirmTitle'),
      {
        confirmButtonText: t('admin.roles.confirmDelete'),
        cancelButtonText: t('admin.roles.cancel'),
        type: 'warning'
      }
    )
  } catch {
    return
  }
  try {
    await deleteRole(row.name)
    ElMessage.success(t('admin.roles.roleDeleteSuccess'))
    fetchRoles()
  } catch (e: any) {
    console.warn(e)
    ElMessage.error(e?.message || t('admin.roles.deleteFailed'))
  }
}

onMounted(fetchRoles)
</script>

<style scoped>
.roles-admin-wrap {
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

.role-name {
  color: var(--agnes-text-primary);
  font-weight: 500;
}

.permissions-wrap {
  display: flex;
  flex-direction: column;
  gap: 16px;
  width: 100%;
  max-height: 400px;
  overflow-y: auto;
  padding-right: 8px;
}

.permission-group {
  background: var(--agnes-bg-hover);
  border-radius: 8px;
  padding: 12px 16px;
}

.group-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--agnes-border);
  margin-bottom: 12px;
}

.group-count {
  color: var(--agnes-text-muted);
  font-size: 12px;
}

.group-permissions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 20px;
}

:deep(.group-permissions .el-checkbox) {
  margin-right: 0;
}

.form-tip {
  color: var(--agnes-text-muted);
  font-size: 12px;
  margin-top: 6px;
}
</style>
