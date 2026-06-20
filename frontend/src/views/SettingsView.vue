<!-- =====================================================
     配置管理视图 SettingsView
     - Provider 增删改查（API Key 加密存储）
     - 模型定义增删改查（支持自定义模型）
     - 模型同步（调用 Provider 的 /models API）
     ===================================================== -->

<template>
  <div class="settings-view">
    <h2 class="page-title">⚙️ {{ t('settings.title') }}</h2>
    <p class="page-desc">{{ t('settings.desc') }}</p>

    <!-- ========== Provider 管理区 ========== -->
    <section class="settings-section">
      <div class="section-header">
        <div>
          <h3 class="section-title">{{ t('settings.providerSection') }}</h3>
          <p class="section-desc">{{ t('settings.providerDesc') }}</p>
        </div>
        <div class="section-actions">
          <el-button
            type="warning"
            :icon="Refresh"
            :loading="providersStore.syncing"
            @click="handleSyncAll">
            {{ t('settings.syncAll') }}
          </el-button>
          <el-button type="primary" :icon="Plus" @click="openProviderDialog()">
            {{ t('settings.addProvider') }}
          </el-button>
        </div>
      </div>

      <el-table
        :data="providersStore.providers"
        v-loading="providersStore.loading"
        stripe
        class="settings-table">
        <el-table-column :label="t('settings.colName')" prop="name" min-width="140" />
        <el-table-column :label="t('settings.colBaseUrl')" prop="base_url" min-width="240" show-overflow-tooltip />
        <el-table-column :label="t('settings.colApiKey')" prop="api_key" min-width="160" show-overflow-tooltip />
        <el-table-column :label="t('settings.colPollUrl')" prop="poll_url" min-width="200" show-overflow-tooltip>
          <template #default="{ row }">
            <span>{{ row.poll_url || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column :label="t('settings.colStatus')" width="100" align="center">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'info'" size="small">
              {{ row.is_active ? t('settings.active') : t('settings.inactive') }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column :label="t('settings.colDefault')" width="90" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.is_default" type="warning" size="small">{{ t('settings.isDefault') }}</el-tag>
            <span v-else>—</span>
          </template>
        </el-table-column>
        <el-table-column :label="t('settings.colActions')" width="280" fixed="right">
          <template #default="{ row }">
            <el-button
              size="small"
              :icon="Refresh"
              :loading="syncingProviderId === row.id"
              :disabled="!row.is_active"
              @click="handleSyncProvider(row)">
              {{ t('settings.syncModels') }}
            </el-button>
            <el-button
              v-if="!row.is_default"
              size="small"
              @click="handleSetDefault(row)">
              {{ t('settings.setDefault') }}
            </el-button>
            <el-button size="small" :icon="Edit" @click="openProviderDialog(row)">
              {{ t('common.edit') }}
            </el-button>
            <el-button size="small" type="danger" :icon="Delete" @click="handleDeleteProvider(row)">
              {{ t('common.delete') }}
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </section>

    <!-- ========== 模型定义管理区 ========== -->
    <section class="settings-section">
      <div class="section-header">
        <div>
          <h3 class="section-title">{{ t('settings.modelSection') }}</h3>
          <p class="section-desc">{{ t('settings.modelDesc') }}</p>
        </div>
        <div class="section-actions">
          <el-button type="primary" :icon="Plus" @click="openModelDialog()">
            {{ t('settings.addModel') }}
          </el-button>
        </div>
      </div>

      <el-table
        :data="providersStore.modelDefinitions"
        v-loading="providersStore.loading"
        stripe
        class="settings-table">
        <el-table-column :label="t('settings.colModelId')" prop="model_id" min-width="200" show-overflow-tooltip />
        <el-table-column :label="t('settings.colDisplayName')" prop="display_name" min-width="180" />
        <el-table-column :label="t('settings.colType')" width="90" align="center">
          <template #default="{ row }">
            <el-tag :type="typeTagType(row.type)" size="small">{{ typeLabel(row.type) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column :label="t('settings.colProvider')" prop="provider_name" min-width="120" />
        <el-table-column :label="t('settings.colCustom')" width="100" align="center">
          <template #default="{ row }">
            <el-tag :type="row.is_custom ? 'warning' : 'info'" size="small">
              {{ row.is_custom ? t('settings.customYes') : t('settings.customNo') }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column :label="t('settings.colStatus')" width="90" align="center">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'info'" size="small">
              {{ row.is_active ? t('settings.active') : t('settings.inactive') }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column :label="t('settings.colCapabilities')" min-width="200">
          <template #default="{ row }">
            <el-tag
              v-for="cap in row.capabilities"
              :key="cap"
              size="small"
              class="cap-tag">
              {{ cap }}
            </el-tag>
            <span v-if="!row.capabilities || row.capabilities.length === 0">—</span>
          </template>
        </el-table-column>
        <el-table-column :label="t('settings.colActions')" width="180" fixed="right">
          <template #default="{ row }">
            <el-button size="small" :icon="Edit" @click="openModelDialog(row)">
              {{ t('common.edit') }}
            </el-button>
            <el-button size="small" type="danger" :icon="Delete" @click="handleDeleteModel(row)">
              {{ t('common.delete') }}
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </section>

    <!-- ========== Provider 编辑弹窗 ========== -->
    <el-dialog
      v-model="providerDialogVisible"
      :title="editingProvider ? t('common.edit') : t('settings.addProvider')"
      width="560px"
      :close-on-click-modal="false">
      <el-form ref="providerFormRef" :model="providerForm" :rules="providerRules" label-width="120px">
        <el-form-item :label="t('settings.formName')" prop="name">
          <el-input v-model="providerForm.name" :placeholder="t('settings.formNamePlaceholder')" />
        </el-form-item>
        <el-form-item :label="t('settings.formBaseUrl')" prop="base_url">
          <el-input v-model="providerForm.base_url" :placeholder="t('settings.formBaseUrlPlaceholder')" />
        </el-form-item>
        <el-form-item :label="t('settings.formApiKey')" prop="api_key">
          <el-input
            v-model="providerForm.api_key"
            type="password"
            show-password
            :placeholder="editingProvider ? t('settings.formApiKeyHint') : t('settings.formApiKeyPlaceholder')" />
        </el-form-item>
        <el-form-item :label="t('settings.formPollUrl')">
          <el-input v-model="providerForm.poll_url" :placeholder="t('settings.formPollUrlPlaceholder')" />
        </el-form-item>
        <el-form-item :label="t('settings.formSortOrder')">
          <el-input-number v-model="providerForm.sort_order" :min="0" :max="9999" />
        </el-form-item>
        <el-form-item :label="t('settings.formIsActive')">
          <el-switch v-model="providerForm.is_active" />
        </el-form-item>
        <el-form-item :label="t('settings.formIsDefault')">
          <el-switch v-model="providerForm.is_default" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="providerDialogVisible = false">{{ t('common.cancel') }}</el-button>
        <el-button type="primary" :loading="submitting" @click="submitProvider">{{ t('common.save') }}</el-button>
      </template>
    </el-dialog>

    <!-- ========== 模型编辑弹窗 ========== -->
    <el-dialog
      v-model="modelDialogVisible"
      :title="editingModel ? t('common.edit') : t('settings.addModel')"
      width="560px"
      :close-on-click-modal="false">
      <el-form ref="modelFormRef" :model="modelForm" :rules="modelRules" label-width="120px">
        <el-form-item :label="t('settings.formModelProvider')" prop="provider_id">
          <el-select v-model="modelForm.provider_id" :placeholder="t('settings.formModelProvider')" :disabled="!!editingModel">
            <el-option
              v-for="p in providersStore.providers"
              :key="p.id"
              :label="p.name"
              :value="p.id" />
          </el-select>
        </el-form-item>
        <el-form-item :label="t('settings.formModelId')" prop="model_id">
          <el-input v-model="modelForm.model_id" :placeholder="t('settings.formModelIdPlaceholder')" :disabled="!!editingModel" />
        </el-form-item>
        <el-form-item :label="t('settings.formDisplayName')">
          <el-input v-model="modelForm.display_name" />
        </el-form-item>
        <el-form-item :label="t('settings.formModelType')">
          <el-select v-model="modelForm.model_type" clearable>
            <el-option :label="t('settings.typeImage')" value="image" />
            <el-option :label="t('settings.typeVideo')" value="video" />
            <el-option :label="t('settings.typeChat')" value="chat" />
          </el-select>
        </el-form-item>
        <el-form-item :label="t('settings.formModelProviderName')">
          <el-input v-model="modelForm.provider_name" />
        </el-form-item>
        <el-form-item :label="t('settings.formCapabilities')">
          <el-select v-model="modelForm.capabilities" multiple filterable allow-create default-first-option>
            <el-option label="text2image" value="text2image" />
            <el-option label="image2image" value="image2image" />
            <el-option label="text2video" value="text2video" />
            <el-option label="image2video" value="image2video" />
            <el-option label="keyframes" value="keyframes" />
            <el-option label="text" value="text" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="editingModel" :label="t('settings.formIsActive')">
          <el-switch v-model="modelForm.is_active" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="modelDialogVisible = false">{{ t('common.cancel') }}</el-button>
        <el-button type="primary" :loading="submitting" @click="submitModel">{{ t('common.save') }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox, type FormInstance, type FormRules } from 'element-plus'
import { Plus, Edit, Delete, Refresh } from '@element-plus/icons-vue'
import { useI18n } from '@/i18n'
import { useProvidersStore } from '@/stores/providers'
import { useModelsStore } from '@/stores/models'
import type { ApiProvider, ModelDefinition } from '@/types'

const { t } = useI18n()
const providersStore = useProvidersStore()
const modelsStore = useModelsStore()

// ---------- 同步状态 ----------
const syncingProviderId = ref<number | null>(null)
const submitting = ref(false)

// ---------- Provider 弹窗 ----------
const providerDialogVisible = ref(false)
const providerFormRef = ref<FormInstance>()
const editingProvider = ref<ApiProvider | null>(null)
const providerForm = reactive({
  name: '',
  base_url: '',
  api_key: '',
  poll_url: '',
  is_active: true,
  is_default: false,
  sort_order: 0,
})
const providerRules: FormRules = {
  name: [{ required: true, message: t('settings.formName'), trigger: 'blur' }],
  base_url: [{ required: true, message: t('settings.formBaseUrl'), trigger: 'blur' }],
}

// ---------- 模型弹窗 ----------
const modelDialogVisible = ref(false)
const modelFormRef = ref<FormInstance>()
const editingModel = ref<ModelDefinition | null>(null)
const modelForm = reactive({
  provider_id: 0,
  model_id: '',
  display_name: '',
  model_type: '',
  provider_name: '',
  capabilities: [] as string[],
  is_active: true,
})
const modelRules: FormRules = {
  provider_id: [{ required: true, message: t('settings.formModelProvider'), trigger: 'change' }],
  model_id: [{ required: true, message: t('settings.formModelId'), trigger: 'blur' }],
}

// ---------- 初始化 ----------
onMounted(async () => {
  await providersStore.fetchAll()
})

// ---------- 类型标签 ----------
function typeTagType(type: string): 'primary' | 'success' | 'warning' {
  if (type === 'image') return 'success'
  if (type === 'video') return 'warning'
  return 'primary'
}

function typeLabel(type: string): string {
  if (type === 'image') return t('settings.typeImage')
  if (type === 'video') return t('settings.typeVideo')
  if (type === 'chat') return t('settings.typeChat')
  return type
}

// ---------- Provider 操作 ----------
function openProviderDialog(provider?: ApiProvider) {
  editingProvider.value = provider || null
  if (provider) {
    Object.assign(providerForm, {
      name: provider.name,
      base_url: provider.base_url,
      api_key: '',
      poll_url: provider.poll_url || '',
      is_active: provider.is_active,
      is_default: provider.is_default,
      sort_order: provider.sort_order,
    })
  } else {
    Object.assign(providerForm, {
      name: '',
      base_url: '',
      api_key: '',
      poll_url: '',
      is_active: true,
      is_default: false,
      sort_order: 0,
    })
  }
  providerDialogVisible.value = true
}

async function submitProvider() {
  if (!providerFormRef.value) return
  await providerFormRef.value.validate(async (valid) => {
    if (!valid) return
    submitting.value = true
    try {
      if (editingProvider.value) {
        // 编辑：api_key 留空表示不修改
        const data: Record<string, unknown> = {
          name: providerForm.name,
          base_url: providerForm.base_url,
          poll_url: providerForm.poll_url,
          is_active: providerForm.is_active,
          is_default: providerForm.is_default,
          sort_order: providerForm.sort_order,
        }
        if (providerForm.api_key) {
          data.api_key = providerForm.api_key
        }
        await providersStore.editProvider(editingProvider.value.id, data)
        ElMessage.success(t('settings.providerUpdated'))
      } else {
        // 新增：api_key 必填
        if (!providerForm.api_key) {
          ElMessage.warning(t('settings.formApiKeyPlaceholder'))
          return
        }
        await providersStore.addProvider({
          name: providerForm.name,
          base_url: providerForm.base_url,
          api_key: providerForm.api_key,
          poll_url: providerForm.poll_url,
          is_active: providerForm.is_active,
          is_default: providerForm.is_default,
          sort_order: providerForm.sort_order,
        })
        ElMessage.success(t('settings.providerCreated'))
      }
      providerDialogVisible.value = false
      // 刷新前端模型配置缓存
      modelsStore.loaded = false
      await modelsStore.fetchConfig()
    } finally {
      submitting.value = false
    }
  })
}

async function handleDeleteProvider(provider: ApiProvider) {
  try {
    await ElMessageBox.confirm(
      t('settings.confirmDeleteProvider').replace('{name}', provider.name),
      t('common.delete'),
      { type: 'warning' }
    )
    await providersStore.removeProvider(provider.id)
    ElMessage.success(t('settings.providerDeleted'))
    modelsStore.loaded = false
    await modelsStore.fetchConfig()
  } catch {
    // 用户取消
  }
}

async function handleSetDefault(provider: ApiProvider) {
  await providersStore.editProvider(provider.id, { is_default: true })
  ElMessage.success(t('settings.providerUpdated'))
}

async function handleSyncProvider(provider: ApiProvider) {
  syncingProviderId.value = provider.id
  try {
    const result = await providersStore.syncProvider(provider.id)
    ElMessage.success(
      t('settings.syncSuccess')
        .replace('{added}', String(result.added))
        .replace('{updated}', String(result.updated))
        .replace('{deactivated}', String(result.deactivated))
        .replace('{total}', String(result.total))
    )
    modelsStore.loaded = false
    await modelsStore.fetchConfig()
  } finally {
    syncingProviderId.value = null
  }
}

async function handleSyncAll() {
  try {
    await ElMessageBox.confirm(t('settings.confirmSyncAll'), t('settings.syncAll'), { type: 'warning' })
  } catch {
    return
  }
  ElMessage.info(t('settings.syncStarted'))
  const results = await providersStore.syncAll()
  const totalAdded = results.reduce((s, r) => s + (r.added || 0), 0)
  const totalUpdated = results.reduce((s, r) => s + (r.updated || 0), 0)
  const totalDeactivated = results.reduce((s, r) => s + (r.deactivated || 0), 0)
  ElMessage.success(
    `${t('settings.syncCompleted')}：+${totalAdded} ~${totalUpdated} -${totalDeactivated}`
  )
  modelsStore.loaded = false
  await modelsStore.fetchConfig()
}

// ---------- 模型操作 ----------
function openModelDialog(model?: ModelDefinition) {
  editingModel.value = model || null
  if (model) {
    Object.assign(modelForm, {
      provider_id: model.provider_id,
      model_id: model.model_id,
      display_name: model.display_name,
      model_type: model.type,
      provider_name: model.provider_name,
      capabilities: [...(model.capabilities || [])],
      is_active: model.is_active,
    })
  } else {
    Object.assign(modelForm, {
      provider_id: providersStore.providers[0]?.id || 0,
      model_id: '',
      display_name: '',
      model_type: '',
      provider_name: '',
      capabilities: [],
      is_active: true,
    })
  }
  modelDialogVisible.value = true
}

async function submitModel() {
  if (!modelFormRef.value) return
  await modelFormRef.value.validate(async (valid) => {
    if (!valid) return
    submitting.value = true
    try {
      if (editingModel.value) {
        await providersStore.editModel(editingModel.value.model_id, {
          display_name: modelForm.display_name,
          model_type: modelForm.model_type,
          provider_name: modelForm.provider_name,
          capabilities: modelForm.capabilities,
          is_active: modelForm.is_active,
        })
        ElMessage.success(t('settings.modelUpdated'))
      } else {
        await providersStore.addModel({
          provider_id: modelForm.provider_id,
          model_id: modelForm.model_id,
          display_name: modelForm.display_name,
          model_type: modelForm.model_type,
          provider_name: modelForm.provider_name,
          capabilities: modelForm.capabilities,
        })
        ElMessage.success(t('settings.modelCreated'))
      }
      modelDialogVisible.value = false
      modelsStore.loaded = false
      await modelsStore.fetchConfig()
    } finally {
      submitting.value = false
    }
  })
}

async function handleDeleteModel(model: ModelDefinition) {
  try {
    await ElMessageBox.confirm(
      t('settings.confirmDeleteModel').replace('{modelId}', model.model_id),
      t('common.delete'),
      { type: 'warning' }
    )
    await providersStore.removeModel(model.model_id)
    ElMessage.success(t('settings.modelDeleted'))
    modelsStore.loaded = false
    await modelsStore.fetchConfig()
  } catch {
    // 用户取消
  }
}
</script>

<style scoped>
/* =====================================================
 * 配置管理页面样式（沿用项目深色主题）
 * ===================================================== */
.settings-view {
  max-width: 1400px;
  margin: 0 auto;
}

.page-title {
  margin: 0 0 8px;
  font-size: 24px;
  font-weight: 700;
  color: #e8eef7;
}

.page-desc {
  margin: 0 0 24px;
  font-size: 14px;
  color: #8ba3c9;
  line-height: 1.6;
}

.settings-section {
  background: rgba(20, 30, 50, 0.55);
  border: 1px solid rgba(100, 150, 220, 0.12);
  border-radius: 12px;
  padding: 20px 24px;
  margin-bottom: 24px;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 16px;
  gap: 16px;
  flex-wrap: wrap;
}

.section-title {
  margin: 0 0 6px;
  font-size: 16px;
  font-weight: 600;
  color: #e8eef7;
}

.section-desc {
  margin: 0;
  font-size: 13px;
  color: #8ba3c9;
  line-height: 1.5;
  max-width: 700px;
}

.section-actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}

.settings-table {
  width: 100%;
}

.cap-tag {
  margin-right: 4px;
  margin-bottom: 4px;
}

/* 深色主题表格覆盖 */
:deep(.el-table) {
  background: transparent;
  --el-table-bg-color: transparent;
  --el-table-tr-bg-color: transparent;
  --el-table-header-bg-color: rgba(30, 45, 70, 0.6);
  --el-table-border-color: rgba(100, 150, 220, 0.12);
  --el-table-header-text-color: #a0b4d6;
  --el-table-text-color: #e8eef7;
  --el-table-row-hover-bg-color: rgba(80, 140, 255, 0.08);
}

:deep(.el-table th.el-table__cell) {
  background: rgba(30, 45, 70, 0.6) !important;
}

:deep(.el-table--striped .el-table__body tr.el-table__row--striped td.el-table__cell) {
  background: rgba(20, 30, 50, 0.4);
}

/* 弹窗深色主题覆盖 */
:deep(.el-dialog) {
  background: #1a2438;
  border: 1px solid rgba(100, 150, 220, 0.18);
}

:deep(.el-dialog__title) {
  color: #e8eef7;
}

:deep(.el-dialog__body) {
  color: #e8eef7;
}

:deep(.el-form-item__label) {
  color: #a0b4d6;
}

@media (max-width: 900px) {
  .section-header {
    flex-direction: column;
  }
}
</style>
