<!-- =====================================================
     配置管理视图 SettingsView
     - Provider 增删改查（API Key 加密存储）
     - 模型定义增删改查（支持自定义模型）
     - 模型同步（调用 Provider 的 /models API）
     ===================================================== -->

<template>
  <div class="settings-view">
    <h2 class="page-title"><el-icon><Setting /></el-icon> {{ t('settings.title') }}</h2>
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
        <el-table-column :label="t('settings.colProviderType')" prop="provider_type" width="150" align="center">
          <template #default="{ row }">
            <el-tag :type="providerTypeTagType(row.provider_type)" size="small">
              {{ providerTypeLabel(row.provider_type) }}
            </el-tag>
          </template>
        </el-table-column>
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
        <el-form-item :label="t('settings.formProviderType')" prop="provider_type">
          <el-select
            v-model="providerForm.provider_type"
            :placeholder="t('settings.formProviderTypePlaceholder')"
            filterable
            allow-create
            default-first-option>
            <el-option
              v-for="opt in PROVIDER_TYPE_OPTIONS"
              :key="opt.value"
              :label="opt.label"
              :value="opt.value" />
          </el-select>
          <div class="form-item-hint">{{ t('settings.formProviderTypeHint') }}</div>
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
        <!-- 资源存储方式：决定生成结果（图片/视频）的转存策略 -->
        <el-form-item :label="t('settings.formAssetStorageMode')">
          <el-radio-group v-model="modelForm.asset_storage_mode">
            <el-radio value="auto">{{ t('settings.assetStorageModeAuto') }}</el-radio>
            <el-radio value="keep">{{ t('settings.assetStorageModeKeep') }}</el-radio>
            <el-radio value="migrate">{{ t('settings.assetStorageModeMigrate') }}</el-radio>
          </el-radio-group>
          <div class="form-item-hint">{{ t('settings.assetStorageModeTip') }}</div>
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
import { Plus, Edit, Delete, Refresh, Setting } from '@element-plus/icons-vue'
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

// ---------- Provider Type 选项（对齐 agn-sdk 已注册的 adapter） ----------
// 仅展示常见的视频/图像/对话类 Provider，其他可通过 allow-create 自由输入
const PROVIDER_TYPE_OPTIONS: { value: string; label: string }[] = [
  { value: 'agnes', label: 'Agnes AI（默认）' },
  { value: 'volcengine_cv', label: '火山引擎（Seedance / Seedream）' },
  { value: 'seedance', label: 'Seedance（火山引擎视频）' },
  { value: 'seedream', label: 'Seedream（火山引擎图像）' },
  { value: 'doubao', label: '豆包（字节跳动）' },
  { value: 'kling', label: '可灵 AI（Kling）' },
  { value: 'runway', label: 'Runway' },
  { value: 'pika', label: 'Pika' },
  { value: 'luma', label: 'Luma AI' },
  { value: 'openai', label: 'OpenAI' },
  { value: 'azure', label: 'Azure OpenAI' },
  { value: 'gemini', label: 'Google Gemini' },
  { value: 'anthropic', label: 'Anthropic Claude' },
  { value: 'deepseek', label: 'DeepSeek' },
  { value: 'qwen', label: '阿里云通义千问' },
  { value: 'glm', label: '智谱 GLM' },
  { value: 'hunyuan', label: '腾讯混元' },
  { value: 'ernie', label: '百度文心一言' },
  { value: 'minimax', label: 'MiniMax' },
  { value: 'stability', label: 'Stability AI' },
  { value: 'ideogram', label: 'Ideogram' },
]

// ---------- Provider 弹窗 ----------
const providerDialogVisible = ref(false)
const providerFormRef = ref<FormInstance>()
const editingProvider = ref<ApiProvider | null>(null)
const providerForm = reactive({
  name: '',
  provider_type: 'agnes',
  base_url: '',
  api_key: '',
  poll_url: '',
  is_active: true,
  is_default: false,
  sort_order: 0,
})
const providerRules: FormRules = {
  name: [{ required: true, message: t('settings.formName'), trigger: 'blur' }],
  provider_type: [{ required: true, message: t('settings.formProviderType'), trigger: 'change' }],
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
  // 资源存储策略：auto(按 provider_type 自动判断) / keep(保留原始 URL) / migrate(强制转存对象存储)
  asset_storage_mode: 'auto',
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
    // 编辑：回填 provider_type（数据库保证非空，此处兜底为 'agnes'）
    Object.assign(providerForm, {
      name: provider.name,
      provider_type: provider.provider_type || 'agnes',
      base_url: provider.base_url,
      api_key: '',
      poll_url: provider.poll_url || '',
      is_active: provider.is_active,
      is_default: provider.is_default,
      sort_order: provider.sort_order,
    })
  } else {
    // 新增：默认 agnes 类型，走业务适配层
    Object.assign(providerForm, {
      name: '',
      provider_type: 'agnes',
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

/** Adapter 类型表格标签文案：优先匹配预置选项，未匹配则原样返回 */
function providerTypeLabel(type: string): string {
  const opt = PROVIDER_TYPE_OPTIONS.find((o) => o.value === type)
  return opt ? opt.label : type
}

/** Adapter 类型表格标签颜色：agnes=primary，国内主流=success，视频类=warning，其他=info */
function providerTypeTagType(type: string): 'primary' | 'success' | 'warning' | 'info' {
  if (type === 'agnes') return 'primary'
  if (['kling', 'doubao', 'qwen', 'glm', 'hunyuan', 'ernie', 'minimax', 'seedance', 'seedream', 'volcengine_cv'].includes(type)) return 'success'
  if (['runway', 'pika', 'luma', 'stability', 'ideogram'].includes(type)) return 'warning'
  return 'info'
}

async function submitProvider() {
  if (!providerFormRef.value) return
  await providerFormRef.value.validate(async (valid) => {
    if (!valid) return
    submitting.value = true
    try {
      if (editingProvider.value) {
        // 编辑：api_key 留空表示不修改；provider_type 变更会触发后端重建 client
        const data: Record<string, unknown> = {
          name: providerForm.name,
          provider_type: providerForm.provider_type,
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
        // 新增：api_key 必填；provider_type 决定后端走哪个适配器
        if (!providerForm.api_key) {
          ElMessage.warning(t('settings.formApiKeyPlaceholder'))
          return
        }
        await providersStore.addProvider({
          name: providerForm.name,
          provider_type: providerForm.provider_type,
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
      // 回填资源存储策略，旧数据缺字段时回退到默认 auto
      asset_storage_mode: model.asset_storage_mode || 'auto',
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
      asset_storage_mode: 'auto',
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
          asset_storage_mode: modelForm.asset_storage_mode,
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
          asset_storage_mode: modelForm.asset_storage_mode,
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
  color: var(--agnes-text-primary);
}

.page-desc {
  margin: 0 0 24px;
  font-size: 14px;
  color: var(--agnes-text-muted);
  line-height: 1.6;
}

.settings-section {
  background: var(--agnes-bg-input);
  border: 1px solid var(--agnes-border-faint);
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
  color: var(--agnes-text-primary);
}

.section-desc {
  margin: 0;
  font-size: 13px;
  color: var(--agnes-text-muted);
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

/* 表单项提示文案：adapter 类型说明等 */
.form-item-hint {
  margin-top: 4px;
  font-size: 12px;
  color: var(--agnes-text-muted);
  line-height: 1.5;
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
  --el-table-header-bg-color: var(--agnes-bg-hover);
  --el-table-border-color: var(--agnes-border-faint);
  --el-table-header-text-color: var(--agnes-text-secondary);
  --el-table-text-color: var(--agnes-text-primary);
  --el-table-row-hover-bg-color: var(--agnes-primary-border-faint);
}

:deep(.el-table th.el-table__cell) {
  background: var(--agnes-bg-hover) !important;
}

:deep(.el-table--striped .el-table__body tr.el-table__row--striped td.el-table__cell) {
  background: var(--agnes-bg-hover);
}

/* 弹窗深色主题覆盖 */
:deep(.el-dialog) {
  background: var(--agnes-bg-base);
  border: 1px solid var(--agnes-border);
}

:deep(.el-dialog__title) {
  color: var(--agnes-text-primary);
}

:deep(.el-dialog__body) {
  color: var(--agnes-text-primary);
}

:deep(.el-form-item__label) {
  color: var(--agnes-text-secondary);
}

@media (max-width: 900px) {
  .section-header {
    flex-direction: column;
  }
}
</style>
