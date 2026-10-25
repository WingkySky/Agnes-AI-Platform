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
        <el-input-number
          v-model="batchCostMultiplier"
          size="small"
          :min="0.1"
          :max="100"
          :step="0.1"
          :precision="2"
          :title="t('settings.costMultiplierTip')"
          class="batch-multiplier"
        />
        <el-button size="small" type="primary" plain @click="handleBatchCostMultiplier">
          {{ t('settings.batchMultiplier') }}
        </el-button>
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
        <el-form-item :label="t('settings.formBillingTier')">
          <el-radio-group v-model="providerForm.billing_tier">
            <el-radio value="paid">{{ t('settings.billingPaid') }}</el-radio>
            <el-radio value="free">{{ t('settings.billingFree') }}</el-radio>
          </el-radio-group>
          <div class="form-item-hint">{{ t('settings.billingTierHint') }}</div>
        </el-form-item>

        <!-- 声明式 HTTP 渠道模板（provider_type=http_custom） -->
        <template v-if="providerForm.provider_type === 'http_custom'">
          <el-divider content-position="left">{{ t('settings.httpSectionTitle') }}</el-divider>
          <el-form-item :label="t('settings.httpModelsMode')">
            <el-radio-group v-model="httpForm.models_mode">
              <el-radio value="openai">OpenAI /models</el-radio>
              <el-radio value="static">{{ t('settings.httpModelsStatic') }}</el-radio>
              <el-radio value="custom">{{ t('settings.httpModelsCustom') }}</el-radio>
            </el-radio-group>
          </el-form-item>
          <el-form-item v-if="httpForm.models_mode === 'static'" :label="t('settings.httpStaticModels')">
            <el-input v-model="httpForm.static_models" type="textarea" :rows="3" placeholder='[{"id": "model-id", "type": "image"}]' />
          </el-form-item>
          <el-form-item v-if="httpForm.models_mode === 'custom'" :label="t('settings.httpModelsEndpoint')">
            <el-input v-model="httpForm.models_path" placeholder="/models/list" />
          </el-form-item>

          <el-form-item :label="t('settings.httpAiGenerate')">
            <div class="http-ai-box">
              <el-input v-model="httpAiInput" type="textarea" :rows="3" :placeholder="t('settings.httpAiPlaceholder')" />
              <el-button :loading="httpAiLoading" @click="generateHttpConfigWithAI">{{ t('settings.httpAiGenerateBtn') }}</el-button>
            </div>
          </el-form-item>

          <div class="http-card">
            <div class="http-card-title">{{ t('settings.httpImageCard') }}</div>
            <div class="http-grid">
              <el-input v-model="httpForm.image_create.path" :placeholder="t('settings.httpFieldPath') + '，如 /v1/images/generations'" />
              <el-input v-model="httpForm.image_create.url_path" :placeholder="t('settings.httpFieldUrlPath') + '，如 data.0.url'" />
              <el-input v-model="httpForm.image_create.b64_path" :placeholder="t('settings.httpFieldB64Path')" />
              <el-input-number v-model="httpForm.image_create.timeout_sec" :min="1" :max="600" controls-position="right" style="width: 100%" />
            </div>
            <el-input v-model="httpForm.image_create.body" type="textarea" :rows="4" :placeholder="'{\n  &quot;model&quot;: &quot;{{model}}&quot;,\n  &quot;prompt&quot;: &quot;{{prompt}}&quot;\n}'"
                      class="http-body-input" />
            <el-input v-model="httpForm.image_create.headers" type="textarea" :rows="1" :placeholder="t('settings.httpFieldHeaders')" />
          </div>

          <div class="http-card">
            <div class="http-card-title">{{ t('settings.httpVideoCreateCard') }}</div>
            <div class="http-grid">
              <el-input v-model="httpForm.video_create.path" :placeholder="t('settings.httpFieldPath')" />
              <el-input v-model="httpForm.video_create.task_id_path" :placeholder="t('settings.httpFieldTaskIdPath') + '，如 data.task_id'" />
              <el-input v-model="httpForm.video_create.video_id_path" :placeholder="t('settings.httpFieldVideoIdPath')" />
              <el-input-number v-model="httpForm.video_create.timeout_sec" :min="1" :max="600" controls-position="right" style="width: 100%" />
            </div>
            <el-input v-model="httpForm.video_create.body" type="textarea" :rows="4" :placeholder="'{\n  &quot;prompt&quot;: &quot;{{prompt}}&quot;,\n  &quot;width&quot;: {{width}}\n}'"
                      class="http-body-input" />
            <el-input v-model="httpForm.video_create.headers" type="textarea" :rows="1" :placeholder="t('settings.httpFieldHeaders')" />
          </div>

          <div class="http-card">
            <div class="http-card-title">{{ t('settings.httpVideoPollCard') }}</div>
            <div class="http-grid">
              <el-input v-model="httpForm.video_poll.path" placeholder="/video/status?task_id={{task_id}}" />
              <el-input v-model="httpForm.video_poll.status_path" :placeholder="t('settings.httpFieldStatusPath') + '，如 data.status'" />
              <el-input v-model="httpForm.video_poll.video_url_path" :placeholder="t('settings.httpFieldVideoUrlPath')" />
              <el-input v-model="httpForm.video_poll.progress_path" :placeholder="t('settings.httpFieldProgressPath')" />
              <el-input v-model="httpForm.video_poll.error_path" :placeholder="t('settings.httpFieldErrorPath')" />
              <el-input-number v-model="httpForm.video_poll.timeout_sec" :min="1" :max="600" controls-position="right" style="width: 100%" />
            </div>
            <el-input v-model="httpForm.video_poll.status_map" type="textarea" :rows="3" :placeholder="'{&quot;SUCCESS&quot;: &quot;success&quot;, &quot;RUNNING&quot;: &quot;processing&quot;, &quot;FAILED&quot;: &quot;failed&quot;}'" />
            <el-input v-model="httpForm.video_poll.headers" type="textarea" :rows="1" :placeholder="t('settings.httpFieldHeaders')" />
            <div class="form-item-hint">{{ t('settings.httpStatusMapHint') }}</div>
          </div>
        </template>
      </el-form>
      <template #footer>
        <el-button
          v-if="providerForm.provider_type === 'http_custom' && editingProvider"
          :loading="testingHttp"
          @click="testHttpConnection">
          {{ t('settings.httpTestBtn') }}
        </el-button>
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
        <el-form-item :label="t('settings.formVideoDurations')">
          <el-input v-model="modelForm.video_durations" clearable :placeholder="t('settings.genParamsAuto')" />
          <div class="form-item-hint">{{ t('settings.formVideoDurationsHint') }}</div>
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
        <!-- 积分倍率（动态定价）：实扣 = credit_rules 基准价 × 倍率 -->
        <el-form-item :label="t('settings.formCostMultiplier')">
          <el-input-number v-model="modelForm.cost_multiplier" :min="0.1" :max="100" :step="0.1" :precision="2" />
          <div class="form-item-hint">{{ t('settings.costMultiplierTip') }}</div>
        </el-form-item>
        <!-- 备用路由（多渠道路由 failover）：仅已保存模型可配置（锚点须存在） -->
        <el-form-item v-if="editingModel" :label="t('settings.modelRoutes')">
          <div class="route-editor">
            <div v-for="(route, idx) in modelRoutes" :key="`${route.provider_id}-${route.model_id}`" class="route-row">
              <span class="route-order">{{ idx + 1 }}</span>
              <span class="route-name">{{ providerNameById.get(route.provider_id) || route.provider_id }}</span>
              <span class="route-model">{{ route.model_id }}</span>
              <el-tag
                v-if="providerTierById.get(route.provider_id) !== anchorBillingTier"
                size="small" type="warning">
                {{ tierLabel(providerTierById.get(route.provider_id)) }}
              </el-tag>
              <el-switch v-model="route.is_enabled" size="small" :title="t('settings.routeEnabled')" />
              <span class="route-actions">
                <el-button size="small" :disabled="idx === 0" @click="moveRoute(idx, -1)">↑</el-button>
                <el-button size="small" :disabled="idx === modelRoutes.length - 1" @click="moveRoute(idx, 1)">↓</el-button>
                <el-button size="small" type="danger" plain @click="modelRoutes.splice(idx, 1)">{{ t('common.delete') }}</el-button>
              </span>
            </div>
            <div v-if="modelRoutes.length === 0" class="route-empty">{{ t('settings.routeEmpty') }}</div>
            <div class="route-add">
              <el-select v-model="routeAddProviderId" filterable :placeholder="t('settings.routeProvider')" style="width: 150px">
                <el-option v-for="p in routeCandidateProviders" :key="p.id" :label="p.name" :value="p.id" />
              </el-select>
              <el-select
                v-model="routeAddModelId"
                filterable allow-create default-first-option
                :placeholder="t('settings.routeModel')"
                style="width: 220px">
                <el-option
                  v-for="m in routeCandidateModels"
                  :key="`${m.provider_id}-${m.model_id}`"
                  :label="m.display_name || m.model_id"
                  :value="m.model_id" />
              </el-select>
              <el-button @click="addRoute">{{ t('settings.routeAdd') }}</el-button>
              <el-button v-if="sameModelAlternatives.length" link type="primary" @click="addSameModelRoutes">
                {{ t('settings.routeSameModel') }}
              </el-button>
            </div>
            <div class="form-item-hint">{{ t('settings.modelRoutesHint') }}</div>
          </div>
        </el-form-item>
        <el-form-item v-else :label="t('settings.modelRoutes')">
          <div class="form-item-hint">{{ t('settings.routeNewModelHint') }}</div>
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
import { ElMessage, type FormInstance, type FormRules, type TableInstance } from 'element-plus'
import { useConfirm } from '@/composables/useConfirm'
import { Plus, Edit, Delete, Refresh, Setting, Open, TurnOff } from '@element-plus/icons-vue'
import { useI18n } from '@/i18n'
import { useProvidersStore } from '@/stores/providers'
import { useModelsStore } from '@/stores/models'
import { listModelRoutes, saveModelRoutes, testHttpProvider } from '@/api/providers'
import { appendModelRoute, buildRouteSavePayload, moveModelRoute, type EditableModelRoute } from '@/lib/model-routes'
import {
  HTTP_CONFIG_PROMPT_DOC,
  buildHttpConfigPayload,
  emptyHttpForm,
  formFromHttpConfig,
  parseHttpConfigFromAI,
  type HttpFormState,
} from '@/lib/provider-http-config'
import { sseChatComplete } from '@/lib/storyboard/transport'
import type { ApiProvider, ModelDefinition } from '@/types'

const { t } = useI18n()
const { confirm } = useConfirm()
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
const batchCostMultiplier = ref(1.0)
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
    label: t('settings.declarativeGroup'),
    options: [
      { value: 'http_custom', label: t('settings.providerTypeHttpCustom') },
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
  billing_tier: 'paid' as 'free' | 'paid',
})
const providerRules: FormRules = {
  name: [{ required: true, message: t('settings.formName'), trigger: 'blur' }],
  provider_type: [{ required: true, message: t('settings.formProviderType'), trigger: 'change' }],
  base_url: [{ required: true, message: t('settings.formBaseUrl'), trigger: 'blur' }],
}

// ---------- 声明式 HTTP 渠道（provider_type=http_custom） ----------
const httpForm = reactive<HttpFormState>(emptyHttpForm())
const httpAiInput = ref('')
const httpAiLoading = ref(false)
const testingHttp = ref(false)

/** AI 生成声明式配置：粘贴文档/cURL → LLM 透传生成 → 校验 → 填入表单 */
async function generateHttpConfigWithAI() {
  const docs = httpAiInput.value.trim()
  if (!docs) {
    ElMessage.warning(t('settings.httpAiPlaceholder'))
    return
  }
  httpAiLoading.value = true
  try {
    const text = await sseChatComplete([
      { role: 'system', content: `你是 API 接入配置专家。根据用户提供的渠道 API 文档片段或 cURL 示例，生成声明式 HTTP 渠道配置 JSON。只输出 JSON 本体，不要任何解释、注释或代码围栏。\n${HTTP_CONFIG_PROMPT_DOC}` },
      { role: 'user', content: docs },
    ], { temperature: 0.1 })
    const { config, error } = parseHttpConfigFromAI(text)
    if (error || !config) {
      ElMessage.error(`${t('settings.httpAiFailed')}：${error}`)
      return
    }
    Object.assign(httpForm, formFromHttpConfig(config))
    ElMessage.success(t('settings.httpAiFilled'))
  } catch (e) {
    ElMessage.error(`${t('settings.httpAiFailed')}：${e instanceof Error ? e.message : String(e)}`)
  } finally {
    httpAiLoading.value = false
  }
}

/** 测试声明式渠道连接（须先保存，按已存配置真实请求模型目录） */
async function testHttpConnection() {
  if (!editingProvider.value) {
    ElMessage.warning(t('settings.httpTestSaveFirst'))
    return
  }
  testingHttp.value = true
  try {
    const r = await testHttpProvider(editingProvider.value.id)
    if (r.ok) {
      ElMessage.success(t('settings.httpTestOk').replace('{count}', String(r.count)))
    } else {
      ElMessage.error(`${t('settings.httpAiFailed')}：${r.error || 'unknown'}`)
    }
  } finally {
    testingHttp.value = false
  }
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
  // 积分倍率（动态定价）：实扣 = credit_rules 基准价 × 倍率
  cost_multiplier: 1.0,
  // ── 生成能力配置（gen_params；空值=自动，按模型名画像判断）──
  max_ref_images: null as number | null,
  watermark_param_off: null as boolean | null,
  size_rule: '',
  default_size: '',
  // 时长档位（表单里是逗号分隔秒数字符串，保存时解析为数组；空=跟随全局）
  video_durations: '',
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
  // 时长档位：兼容中英文逗号/空格分隔，过滤非法项
  const durations = modelForm.video_durations
    .split(/[,，\s]+/)
    .map((s) => Number.parseInt(s.trim(), 10))
    .filter((n) => Number.isFinite(n) && n > 0)
  if (durations.length > 0) gp.video_durations = durations
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
  httpAiInput.value = ''
  Object.assign(httpForm, formFromHttpConfig(provider?.http_config))
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
      billing_tier: provider.billing_tier || 'paid',
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
      billing_tier: 'paid',
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
    // 声明式 HTTP 渠道：表单 → http_config 载荷（校验失败直接提示）
    let httpConfigPayload: Record<string, unknown> | undefined
    if (providerForm.provider_type === 'http_custom') {
      const { config, error } = buildHttpConfigPayload(httpForm)
      if (error || !config) {
        ElMessage.warning(error)
        return
      }
      httpConfigPayload = config
    }
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
          billing_tier: providerForm.billing_tier,
        }
        if (providerForm.provider_type === 'http_custom') {
          data.http_config = httpConfigPayload
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
          billing_tier: providerForm.billing_tier,
          http_config: httpConfigPayload,
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
    await confirm(t('settings.confirmDeleteProvider').replace('{name}', provider.name), t('common.delete'))
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
  await confirm(t('settings.confirmSyncAll'), t('settings.syncAll'))
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

// ---------- 模型备用路由（多渠道路由 failover） ----------
const modelRoutes = ref<EditableModelRoute[]>([])
const routeAddProviderId = ref<number | undefined>(undefined)
const routeAddModelId = ref('')

// 渠道档位反查表（跨档警示用）
const providerTierById = computed(() => {
  return new Map(providersStore.providers.map((p) => [p.id, (p.billing_tier || 'paid') as 'free' | 'paid']))
})
const anchorBillingTier = computed<'free' | 'paid'>(() => {
  const tier = editingModel.value ? providerTierById.value.get(editingModel.value.provider_id) : undefined
  return tier || 'paid'
})
// 备用渠道候选：排除锚点自身渠道
const routeCandidateProviders = computed(() => {
  return providersStore.providers.filter((p) => p.id !== editingModel.value?.provider_id)
})
// 备用模型候选：所选渠道下与锚点同类型的已同步模型（allow-create 支持手填未同步模型）
const routeCandidateModels = computed(() => {
  const anchorType = editingModel.value?.type || modelForm.model_type
  return providersStore.modelDefinitions.filter(
    (m) => m.provider_id === routeAddProviderId.value
      && m.type === anchorType
      && m.model_id !== editingModel.value?.model_id,
  )
})
// 同款其他渠道（一键加入）
const sameModelAlternatives = computed(() => {
  return providersStore.modelDefinitions.filter(
    (m) => m.model_id === editingModel.value?.model_id && m.provider_id !== editingModel.value?.provider_id,
  )
})

function tierLabel(tier?: string): string {
  return tier === 'free' ? t('settings.billingFree') : t('settings.billingPaid')
}

async function loadModelRoutes(modelId: string) {
  try {
    const resp = await listModelRoutes(modelId)
    modelRoutes.value = resp.items.map((i) => ({
      provider_id: i.provider_id,
      model_id: i.model_id,
      is_enabled: i.is_enabled,
    }))
  } catch {
    modelRoutes.value = []
  }
}

function moveRoute(idx: number, delta: number) {
  modelRoutes.value = moveModelRoute(modelRoutes.value, idx, delta)
}

function addRoute() {
  const providerId = routeAddProviderId.value
  if (!providerId) {
    ElMessage.warning(t('settings.routeProvider'))
    return
  }
  const result = appendModelRoute(modelRoutes.value, providerId, routeAddModelId.value)
  if (result.duplicate) {
    ElMessage.warning(t('settings.routeDuplicate'))
    return
  }
  modelRoutes.value = result.routes
  routeAddModelId.value = ''
}

/** 一键加入同款其他渠道（同 model_id 的其他 Provider 已同步定义） */
function addSameModelRoutes() {
  let next = modelRoutes.value
  for (const m of sameModelAlternatives.value) {
    next = appendModelRoute(next, m.provider_id, m.model_id).routes
  }
  modelRoutes.value = next
}

/** 备用路由整表保存（priority 由列表顺序决定） */
async function persistModelRoutes(modelId: string) {
  await saveModelRoutes(modelId, buildRouteSavePayload(modelRoutes.value))
}

function openModelDialog(model?: ModelDefinition, presetProviderId?: number) {
  editingModel.value = model || null
  routeAddProviderId.value = undefined
  routeAddModelId.value = ''
  modelRoutes.value = []
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
      // 回填积分倍率（旧数据缺字段回退 1.0）
      cost_multiplier: model.cost_multiplier ?? 1.0,
      // 回填生成能力配置（gen_params；缺省=自动）
      max_ref_images: model.gen_params?.max_ref_images ?? null,
      watermark_param_off: model.gen_params?.watermark_param_off ?? null,
      size_rule: model.gen_params?.size_rule ?? '',
      default_size: model.gen_params?.default_size ?? '',
      video_durations: model.gen_params?.video_durations?.join(',') ?? '',
    })
    // 已保存模型：加载备用路由（锚点已存在才可配置）
    void loadModelRoutes(model.model_id)
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
      cost_multiplier: 1.0,
      video_durations: '',
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

async function handleBatchCostMultiplier() {
  const ids = selectedModels.value.map((m) => m.model_id)
  const count = await providersStore.batchSetCostMultiplier(ids, batchCostMultiplier.value)
  ElMessage.success(t('settings.batchMultiplierDone').replace('{count}', String(count)))
  clearModelSelection()
}

async function handleBatchDelete() {
  const ids = selectedModels.value.map((m) => m.model_id)
  await confirm(t('settings.confirmBatchDelete').replace('{count}', String(ids.length)), t('common.delete'))
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
          cost_multiplier: modelForm.cost_multiplier,
          gen_params: collectGenParams(),
        })
        // 备用路由随模型保存一起提交（整表替换）
        await persistModelRoutes(editingModel.value.model_id)
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
    await confirm(t('settings.confirmDeleteModel').replace('{modelId}', model.model_id), t('common.delete'))
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

.batch-multiplier {
  width: 120px;
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

/* ---------- 模型备用路由编辑区 ---------- */
.route-editor {
  width: 100%;
}

.route-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 0;
}

.route-order {
  width: 18px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
  text-align: center;
}

.route-name {
  font-weight: 500;
}

.route-model {
  color: var(--el-text-color-secondary);
  font-size: 12px;
  word-break: break-all;
}

.route-actions {
  margin-left: auto;
  display: inline-flex;
  gap: 4px;
  flex-shrink: 0;
}

.route-empty {
  color: var(--el-text-color-secondary);
  font-size: 12px;
  padding: 4px 0;
}

.route-add {
  display: flex;
  gap: 8px;
  margin-top: 6px;
  align-items: center;
  flex-wrap: wrap;
}

/* ---------- 声明式 HTTP 渠道配置区 ---------- */
.http-card {
  width: 100%;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  padding: 10px 12px;
  margin-bottom: 8px;
}

.http-card-title {
  font-weight: 500;
  margin-bottom: 8px;
  color: var(--el-text-color-primary);
}

.http-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  margin-bottom: 8px;
}

.http-body-input {
  margin-bottom: 8px;
}

.http-body-input :deep(textarea) {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12px;
}

.http-ai-box {
  width: 100%;
  display: flex;
  gap: 8px;
  align-items: flex-start;
}
</style>
