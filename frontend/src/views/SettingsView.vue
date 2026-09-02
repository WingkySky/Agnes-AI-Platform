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
        <el-table-column :label="t('settings.colDefault')" width="100" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.is_default" type="warning" size="small">{{ t('settings.isDefault') }}</el-tag>
            <el-button v-else link type="primary" size="small" @click="handleSetDefault(row)">
              {{ t('settings.setDefault') }}
            </el-button>
          </template>
        </el-table-column>
        <el-table-column :label="t('settings.colActions')" width="380" fixed="right">
          <template #default="{ row }">
            <el-button
              size="small"
              :icon="Refresh"
              :loading="syncingProviderId === row.id"
              :disabled="!row.is_active"
              @click="handleSyncProvider(row)">
              {{ t('settings.syncModels') }}
            </el-button>
            <el-button size="small" :icon="Plus" @click="openModelDialog(undefined, row.id)">
              {{ t('settings.addModelShort') }}
            </el-button>
            <el-button size="small" :icon="Edit" @click="openProviderDialog(row)">
              {{ t('common.edit') }}
            </el-button>
            <el-button size="small" type="danger" plain :icon="Delete" @click="handleDeleteProvider(row)">
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
          <el-select
            v-model="filterModelType"
            size="small"
            style="width: 110px"
            :placeholder="t('settings.filterAllTypes')">
            <el-option :label="t('settings.filterAllTypes')" value="" />
            <el-option :label="t('settings.typeImage')" value="image" />
            <el-option :label="t('settings.typeVideo')" value="video" />
            <el-option :label="t('settings.typeChat')" value="chat" />
          </el-select>
          <div class="show-disabled-toggle">
            <el-switch v-model="showDisabled" size="small" />
            <span>{{ t('settings.showDisabled') }}</span>
          </div>
          <el-button type="primary" :icon="Plus" @click="openModelDialog()">
            {{ t('settings.addModel') }}
          </el-button>
        </div>
      </div>

      <!-- Provider 分组切换 Tabs -->
      <div v-if="modelProviderGroups.length > 0" class="model-provider-tabs">
        <el-tabs v-model="selectedModelProvider" type="card" @tab-click="handleModelProviderChange">
          <el-tab-pane
            v-for="group in modelProviderGroups"
            :key="group.provider"
            :label="`${group.provider} (${group.count})`"
            :name="group.provider">
          </el-tab-pane>
        </el-tabs>
      </div>

      <!-- 批量操作条（选中行后显示） -->
      <div v-if="selectedModels.length > 0" class="batch-bar">
        <span class="batch-count">{{ t('settings.selectedCount').replace('{count}', String(selectedModels.length)) }}</span>
        <el-button size="small" type="warning" plain @click="handleBatchDisabled(true)">
          {{ t('settings.batchDisable') }}
        </el-button>
        <el-button size="small" type="success" plain @click="handleBatchDisabled(false)">
          {{ t('settings.batchEnable') }}
        </el-button>
        <el-button size="small" type="danger" plain @click="handleBatchDelete">
          {{ t('settings.batchDelete') }}
        </el-button>
      </div>

      <el-table
        ref="modelTableRef"
        :data="filteredModelDefinitions"
        v-loading="providersStore.loading"
        stripe
        row-key="model_id"
        :row-class-name="modelRowClassName"
        @selection-change="handleSelectionChange"
        class="settings-table">
        <el-table-column type="selection" width="42" />
        <el-table-column :label="t('settings.colModelId')" prop="model_id" min-width="200" show-overflow-tooltip sortable />
        <el-table-column :label="t('settings.colDisplayName')" prop="display_name" min-width="180" sortable />
        <el-table-column :label="t('settings.colType')" prop="type" width="100" align="center" sortable>
          <template #default="{ row }">
            <el-tag :type="typeTagType(row.type)" size="small">{{ typeLabel(row.type) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column :label="t('settings.colOwner')" prop="provider_id" min-width="150" sortable>
          <template #default="{ row }">
            {{ providerNameById.get(row.provider_id) || `#${row.provider_id}` }}
          </template>
        </el-table-column>
        <el-table-column :label="t('settings.colProvider')" prop="provider_name" min-width="120" sortable />
        <el-table-column :label="t('settings.colCustom')" width="100" align="center">
          <template #default="{ row }">
            <el-tag :type="row.is_custom ? 'warning' : 'info'" size="small">
              {{ row.is_custom ? t('settings.customYes') : t('settings.customNo') }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column :label="t('settings.colStatus')" width="90" align="center">
          <template #default="{ row }">
            <el-tag :type="modelStatusTagType(row)" size="small">{{ modelStatusLabel(row) }}</el-tag>
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
        <el-table-column :label="t('settings.colActions')" width="280" fixed="right">
          <template #default="{ row }">
            <el-button
              v-if="!row.is_disabled"
              size="small"
              type="warning"
              plain
              :icon="TurnOff"
              @click="handleToggleModel(row)">
              {{ t('settings.disableModel') }}
            </el-button>
            <el-button v-else size="small" type="success" plain :icon="Open" @click="handleToggleModel(row)">
              {{ t('settings.enableModel') }}
            </el-button>
            <el-button size="small" :icon="Edit" @click="openModelDialog(row)">
              {{ t('common.edit') }}
            </el-button>
            <el-button size="small" type="danger" plain :icon="Delete" @click="handleDeleteModel(row)">
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
            <el-option-group
              v-for="group in PROVIDER_TYPE_GROUPS"
              :key="group.label"
              :label="group.label">
              <el-option
                v-for="opt in group.options"
                :key="opt.value"
                :label="opt.label"
                :value="opt.value" />
            </el-option-group>
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
          <div v-if="editingProvider?.api_key" class="form-item-hint">
            {{ t('settings.formApiKeySaved').replace('{key}', editingProvider.api_key) }}
          </div>
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
            <el-option label="video2video" value="video2video" />
            <el-option label="text" value="text" />
          </el-select>
        </el-form-item>
        <!-- 生成能力配置：按模型差异化的约束（留空=自动，按模型名识别同族特例） -->
        <el-form-item :label="t('settings.formMaxRefImages')">
          <el-input-number v-model="modelForm.max_ref_images" :min="1" :max="99" :placeholder="t('settings.genParamsAuto')" controls-position="right" style="width: 100%" />
          <div class="form-item-hint">{{ t('settings.formMaxRefImagesHint') }}</div>
        </el-form-item>
        <el-form-item :label="t('settings.formWatermarkOff')">
          <el-select v-model="modelForm.watermark_param_off" clearable :placeholder="t('settings.genParamsAuto')">
            <el-option :label="t('settings.genWatermarkOff')" :value="true" />
            <el-option :label="t('settings.genWatermarkKeep')" :value="false" />
          </el-select>
        </el-form-item>
        <el-form-item :label="t('settings.formSizeRule')">
          <el-select v-model="modelForm.size_rule" clearable :placeholder="t('settings.genParamsAuto')">
            <el-option label="Seedream" value="seedream" />
          </el-select>
        </el-form-item>
        <el-form-item :label="t('settings.formDefaultSize')">
          <el-input v-model="modelForm.default_size" clearable :placeholder="t('settings.genParamsAuto')" />
        </el-form-item>
        <el-form-item v-if="editingModel" :label="t('settings.formModelEnabled')">
          <el-switch v-model="modelEnabled" />
          <div class="form-item-hint">{{ t('settings.formModelEnabledHint') }}</div>
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
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox, type FormInstance, type FormRules, type TableInstance } from 'element-plus'
import { Plus, Edit, Delete, Refresh, Setting, Open, TurnOff } from '@element-plus/icons-vue'
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

// ---------- 模型按 Provider 分组 ----------
const selectedModelProvider = ref('')
// 是否在列表中显示已手动停用的模型（默认隐藏，保持列表干净）
const showDisabled = ref(false)
// 模型类型筛选（'' = 全部类型）
const filterModelType = ref('')
// 表格多选状态（批量操作用）
const selectedModels = ref<ModelDefinition[]>([])
const modelTableRef = ref<TableInstance>()

// 按 provider_name 分组的模型列表
const modelProviderGroups = computed(() => {
  const groups: { provider: string; count: number }[] = []
  const providerMap = new Map<string, number>()
  for (const m of providersStore.modelDefinitions) {
    const p = m.provider_name || '其他'
    providerMap.set(p, (providerMap.get(p) || 0) + 1)
  }
  providerMap.forEach((count, provider) => {
    groups.push({ provider, count })
  })
  return groups
})

// 按类型 + Provider 过滤模型（默认隐藏手动停用的模型）
const filteredModelDefinitions = computed(() => {
  let list = providersStore.modelDefinitions
  if (!showDisabled.value) {
    list = list.filter((m) => !m.is_disabled)
  }
  if (filterModelType.value) {
    list = list.filter((m) => m.type === filterModelType.value)
  }
  if (!selectedModelProvider.value) {
    return list
  }
  return list.filter((m) => m.provider_name === selectedModelProvider.value)
})

function handleModelProviderChange(tab: { name: string }) {
  selectedModelProvider.value = tab.name
}

// ---------- Provider Type 选项（对齐 aibridge 已注册的 adapter） ----------
// 分两组：协议兼容接入（任意 OpenAI / Anthropic 协议的中转端点）+ 厂商适配器；
// 其他 adapter 可通过 allow-create 自由输入
const PROVIDER_TYPE_GROUPS: { label: string; options: { value: string; label: string }[] }[] = [
  {
    label: t('settings.protocolGroup'),
    options: [
      { value: 'openai', label: t('settings.providerTypeOpenaiCompat') },
      { value: 'anthropic', label: t('settings.providerTypeAnthropicCompat') },
    ],
  },
  {
    label: t('settings.vendorGroup'),
    options: [
      { value: 'agnes', label: 'Agnes AI（默认）' },
      { value: 'volcengine_cv', label: '火山引擎（Seedance / Seedream）' },
      { value: 'seedance', label: 'Seedance（火山引擎视频）' },
      { value: 'seedream', label: 'Seedream（火山引擎图像）' },
      { value: 'doubao', label: '豆包（字节跳动）' },
      { value: 'kling', label: '可灵 AI（Kling）' },
      { value: 'runway', label: 'Runway' },
      { value: 'pika', label: 'Pika' },
      { value: 'luma', label: 'Luma AI' },
      { value: 'azure', label: 'Azure OpenAI' },
      { value: 'gemini', label: 'Google Gemini' },
      { value: 'deepseek', label: 'DeepSeek' },
      { value: 'qwen', label: '阿里云通义千问' },
      { value: 'glm', label: '智谱 GLM' },
      { value: 'hunyuan', label: '腾讯混元' },
      { value: 'ernie', label: '百度文心一言' },
      { value: 'minimax', label: 'MiniMax' },
      { value: 'stability', label: 'Stability AI' },
      { value: 'ideogram', label: 'Ideogram' },
    ],
  },
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
  // 用户手动停用标记（同步永不修改；与同步管理的 is_active 区分）
  is_disabled: false,
  // 资源存储策略：auto(按 provider_type 自动判断) / keep(保留原始 URL) / migrate(强制转存对象存储)
  asset_storage_mode: 'auto',
  // ── 生成能力配置（gen_params；空值=自动，按模型名画像判断）──
  max_ref_images: null as number | null,
  watermark_param_off: null as boolean | null,
  size_rule: '',
  default_size: '',
})

// 弹窗中的"启用"开关（与 is_disabled 互为取反）
const modelEnabled = computed({
  get: () => !modelForm.is_disabled,
  set: (v: boolean) => {
    modelForm.is_disabled = !v
  },
})
const modelRules: FormRules = {
  provider_id: [{ required: true, message: t('settings.formModelProvider'), trigger: 'change' }],
  model_id: [{ required: true, message: t('settings.formModelId'), trigger: 'blur' }],
}

/** 从表单收集生成能力配置（空值不下发=null=自动；全部为空时下发空对象=清空显式配置回退自动画像） */
function collectGenParams(): Record<string, unknown> {
  const gp: Record<string, unknown> = {}
  if (modelForm.max_ref_images != null) gp.max_ref_images = modelForm.max_ref_images
  if (modelForm.watermark_param_off != null) gp.watermark_param_off = modelForm.watermark_param_off
  if (modelForm.size_rule) gp.size_rule = modelForm.size_rule
  if (modelForm.default_size) gp.default_size = modelForm.default_size
  return gp
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

/** Adapter 类型表格标签文案：优先匹配预置选项（含协议分组），未匹配则原样返回 */
function providerTypeLabel(type: string): string {
  for (const group of PROVIDER_TYPE_GROUPS) {
    const opt = group.options.find((o) => o.value === type)
    if (opt) return opt.label
  }
  return type
}

/** Adapter 类型表格标签颜色：agnes/协议兼容=primary，国内主流=success，视频类=warning，其他=info */
function providerTypeTagType(type: string): 'primary' | 'success' | 'warning' | 'info' {
  if (type === 'agnes' || type === 'openai' || type === 'anthropic') return 'primary'
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

// 模型归属的 Provider 名称反查表（provider_id → 配置的 Provider 名称）
const providerNameById = computed(() => {
  return new Map(providersStore.providers.map((p) => [p.id, p.name]))
})

function openModelDialog(model?: ModelDefinition, presetProviderId?: number) {
  editingModel.value = model || null
  if (model) {
    Object.assign(modelForm, {
      provider_id: model.provider_id,
      model_id: model.model_id,
      display_name: model.display_name,
      model_type: model.type,
      provider_name: model.provider_name,
      capabilities: [...(model.capabilities || [])],
      is_disabled: !!model.is_disabled,
      // 回填资源存储策略，旧数据缺字段时回退到默认 auto
      asset_storage_mode: model.asset_storage_mode || 'auto',
      // 回填生成能力配置（gen_params；缺省=自动）
      max_ref_images: model.gen_params?.max_ref_images ?? null,
      watermark_param_off: model.gen_params?.watermark_param_off ?? null,
      size_rule: model.gen_params?.size_rule ?? '',
      default_size: model.gen_params?.default_size ?? '',
    })
  } else {
    Object.assign(modelForm, {
      // 从 Provider 行「添加模型」进入时预选该 Provider
      provider_id: presetProviderId || providersStore.providers[0]?.id || 0,
      model_id: '',
      display_name: '',
      model_type: '',
      provider_name: '',
      capabilities: [],
      is_disabled: false,
      asset_storage_mode: 'auto',
      max_ref_images: null,
      watermark_param_off: null,
      size_rule: '',
      default_size: '',
    })
  }
  modelDialogVisible.value = true
}

/** 模型状态三态：已停用（用户手动停用）/ 未激活（同步标记 API 已下线）/ 已激活 */
function modelStatusLabel(model: ModelDefinition): string {
  if (model.is_disabled) return t('settings.disabled')
  if (!model.is_active) return t('settings.modelInactive')
  return t('settings.active')
}

function modelStatusTagType(model: ModelDefinition): 'success' | 'info' | 'warning' {
  if (model.is_disabled) return 'info'
  if (!model.is_active) return 'warning'
  return 'success'
}

/** 已停用模型整行弱化显示 */
function modelRowClassName({ row }: { row: ModelDefinition }): string {
  return row.is_disabled ? 'model-row-disabled' : ''
}

/** 停用 / 启用模型（不删除，停用后不出现在生成页模型列表，同步也不会自动恢复） */
async function handleToggleModel(model: ModelDefinition) {
  const nextDisabled = !model.is_disabled
  await providersStore.editModel(model.model_id, { is_disabled: nextDisabled })
  ElMessage.success(nextDisabled ? t('settings.modelDisabled') : t('settings.modelEnabled'))
  modelsStore.loaded = false
  await modelsStore.fetchConfig()
}

// ---------- 模型批量操作 ----------
function handleSelectionChange(rows: ModelDefinition[]) {
  selectedModels.value = rows
}

/** 批量操作后清空多选（fetchModelDefinitions 换了数据，需手动清） */
function clearModelSelection() {
  selectedModels.value = []
  modelTableRef.value?.clearSelection()
}

async function handleBatchDisabled(disabled: boolean) {
  const ids = selectedModels.value.map((m) => m.model_id)
  const count = await providersStore.batchSetModelsDisabled(ids, disabled)
  ElMessage.success(t(disabled ? 'settings.batchDisabled' : 'settings.batchEnabled').replace('{count}', String(count)))
  clearModelSelection()
  modelsStore.loaded = false
  await modelsStore.fetchConfig()
}

async function handleBatchDelete() {
  const ids = selectedModels.value.map((m) => m.model_id)
  try {
    await ElMessageBox.confirm(
      t('settings.confirmBatchDelete').replace('{count}', String(ids.length)),
      t('common.delete'),
      { type: 'warning' }
    )
  } catch {
    // 用户取消
    return
  }
  const count = await providersStore.batchRemoveModels(ids)
  ElMessage.success(t('settings.batchDeleted').replace('{count}', String(count)))
  clearModelSelection()
  modelsStore.loaded = false
  await modelsStore.fetchConfig()
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
          is_disabled: modelForm.is_disabled,
          asset_storage_mode: modelForm.asset_storage_mode,
          gen_params: collectGenParams(),
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
          gen_params: collectGenParams(),
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

/* 显示已停用模型开关 */
.show-disabled-toggle {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: var(--agnes-text-muted);
}

/* 批量操作条 */
.batch-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  margin-bottom: 12px;
  background: var(--agnes-bg-hover);
  border: 1px solid var(--agnes-border-faint);
  border-radius: 8px;
}

.batch-count {
  font-size: 13px;
  color: var(--agnes-text-primary);
  margin-right: 4px;
}

/* 已停用模型整行弱化显示 */
:deep(.el-table .model-row-disabled) {
  opacity: 0.55;
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

/* 模型 Provider 分组 Tabs */
.model-provider-tabs {
  margin-bottom: 16px;
}

:deep(.model-provider-tabs .el-tabs--card) {
  --el-tabs-card-border-color: var(--agnes-border);
}

:deep(.model-provider-tabs .el-tabs__header) {
  margin: 0;
}

:deep(.model-provider-tabs .el-tabs__nav-wrap::after) {
  background: transparent;
}

:deep(.model-provider-tabs .el-tabs__item) {
  border-radius: 8px 8px 0 0;
  margin-right: 4px;
  color: var(--agnes-text-secondary);
  font-size: 13px;
}

:deep(.model-provider-tabs .el-tabs__item.is-active) {
  background: var(--agnes-bg-hover);
  color: var(--agnes-text-primary);
  border-color: var(--agnes-border);
}

:deep(.model-provider-tabs .el-tabs__item:hover) {
  color: var(--agnes-text-primary);
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

/* 固定列不透明化：主题表格底色均为半透明色，sticky 固定列会透出滚动到其下方的内容。
   用「半透明主题色叠层 + 实色底 --agnes-bg-base」在固定列上合成与普通单元格一致的观感 */
:deep(.el-table .el-table-fixed-column--left.el-table__cell),
:deep(.el-table .el-table-fixed-column--right.el-table__cell) {
  background-color: var(--agnes-bg-base);
  background-image: linear-gradient(var(--agnes-bg-input), var(--agnes-bg-input));
}

:deep(.el-table th.el-table-fixed-column--left.el-table__cell),
:deep(.el-table th.el-table-fixed-column--right.el-table__cell) {
  background-color: var(--agnes-bg-base) !important;
  background-image: linear-gradient(var(--agnes-bg-hover), var(--agnes-bg-hover)),
    linear-gradient(var(--agnes-bg-input), var(--agnes-bg-input)) !important;
}

:deep(.el-table--striped .el-table__body tr.el-table__row--striped .el-table-fixed-column--left.el-table__cell),
:deep(.el-table--striped .el-table__body tr.el-table__row--striped .el-table-fixed-column--right.el-table__cell) {
  background-image: linear-gradient(var(--agnes-bg-hover), var(--agnes-bg-hover)),
    linear-gradient(var(--agnes-bg-input), var(--agnes-bg-input));
}

:deep(.el-table__body tr.hover-row > td.el-table-fixed-column--left.el-table__cell),
:deep(.el-table__body tr.hover-row > td.el-table-fixed-column--right.el-table__cell) {
  background-image: linear-gradient(var(--el-table-row-hover-bg-color), var(--el-table-row-hover-bg-color)),
    linear-gradient(var(--agnes-bg-input), var(--agnes-bg-input));
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
