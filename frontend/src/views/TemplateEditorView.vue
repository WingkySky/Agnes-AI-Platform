<!-- =====================================================
     模板编辑器 - TemplateEditorView
     - 创建/编辑自定义流水线模板
     - 结构化表单（基础信息 / 缩略图 / 输入参数 / 步骤配置 / 高级设置）
     - 右上角"专家模式"开关：切换为 JSON 编辑
     - 右侧粘性预览侧栏（实时渲染 inputs_config + steps 流程图）
     - 编辑模式：作者/admin 可访问；公开已审核模板编辑会触发 revision 草稿
     - 进入编辑时若存在 pending revision，加载 revision 字段而非原模板字段
     ===================================================== -->

<template>
  <div class="template-editor">
    <!-- 头部：返回 + 标题 + 状态标签 + 操作按钮 -->
    <div class="editor-header">
      <el-page-header @back="goBack">
        <template #content>
          <span class="header-title">
            {{ isEdit ? t('templateEditor.editTitle') : t('templateEditor.createTitle') }}
          </span>
        </template>
        <!-- 编辑模式下提供导出、分享操作 + 专家模式开关 -->
        <template #extra>
          <!-- 专家模式开关 -->
          <el-tooltip :content="t('templateEditor.expertModeTip')" placement="top">
            <span class="expert-mode-wrap">
              <span class="expert-mode-label">{{ t('templateEditor.expertMode') }}</span>
              <el-switch v-model="expertMode" size="small" />
            </span>
          </el-tooltip>
          <template v-if="isEdit">
            <!-- 公开状态标签 -->
            <el-tag
              v-if="templateData"
              :type="getStatusTagType(templateData)"
              size="small"
              class="status-tag">
              {{ t(`workshop.status.${getTemplateStatus(templateData)}`) }}
            </el-tag>
            <!-- 分享/取消公开按钮 -->
            <el-button
              v-if="templateData && canSubmitPublic(templateData)"
              link
              type="success"
              size="small"
              @click="handleSubmitPublic">
              <el-icon><UploadFilled /></el-icon>
              {{ t('workshop.shareToMarket') }}
            </el-button>
            <el-button
              v-if="templateData && (templateData.is_public || templateData.is_approved)"
              link
              type="warning"
              size="small"
              @click="handleCancelPublic">
              <el-icon><RemoveFilled /></el-icon>
              {{ t('workshop.cancelPublic') }}
            </el-button>
            <el-button
              link
              type="primary"
              size="small"
              @click="openExportCurrent">
              <el-icon><Download /></el-icon>
              {{ t('workshop.importExport.exportThis') }}
            </el-button>
          </template>
        </template>
      </el-page-header>
    </div>

    <!-- pending revision 提示 -->
    <el-alert
      v-if="hasPendingRevision"
      :title="t('templateEditor.pendingRevisionAlert')"
      type="warning"
      :closable="false"
      show-icon
      class="revision-alert" />

    <div v-loading="loading" class="editor-body">
      <div class="editor-layout">
        <!-- ============ 左侧主表单 ============ -->
        <el-form
          ref="formRef"
          :model="form"
          :rules="rules"
          label-width="120px"
          class="editor-form">

          <!-- ====== 专家模式：JSON textarea ====== -->
          <template v-if="expertMode">
            <el-form-item :label="t('templateEditor.inputsConfig')">
              <el-input
                v-model="inputsConfigText"
                type="textarea"
                :rows="10"
                :placeholder="inputsConfigPlaceholder" />
              <div class="form-hint">{{ t('templateEditor.inputsConfigHint') }}</div>
            </el-form-item>
            <el-form-item :label="t('templateEditor.stepsConfig')">
              <el-input
                v-model="stepsConfigText"
                type="textarea"
                :rows="14"
                :placeholder="stepsConfigPlaceholder" />
              <div class="form-hint">{{ t('templateEditor.stepsConfigHint') }}</div>
            </el-form-item>
          </template>

          <!-- ====== 结构化模式：分块表单 ====== -->
          <template v-else>
            <!-- ===== 基础信息块 ===== -->
            <div class="form-section">
              <div class="section-title">{{ t('templateEditor.basicInfo') }}</div>
              <!-- 模板名称 -->
              <el-form-item :label="t('templateEditor.name')" prop="name">
                <el-input v-model="form.name" :placeholder="t('templateEditor.namePlaceholder')" />
              </el-form-item>
              <!-- 模板 Key -->
              <el-form-item :label="t('templateEditor.key')" prop="key">
                <el-input
                  v-model="form.key"
                  :placeholder="t('templateEditor.keyPlaceholder')"
                  :disabled="isEdit" />
                <div class="form-hint">{{ t('templateEditor.keyHint') }}</div>
              </el-form-item>
              <!-- 分类 -->
              <el-form-item :label="t('templateEditor.category')" prop="category">
                <el-select v-model="form.category" :placeholder="t('templateEditor.categoryPlaceholder')">
                  <el-option
                    v-for="cat in categoryOptions"
                    :key="cat.value"
                    :label="cat.label"
                    :value="cat.value" />
                </el-select>
              </el-form-item>
              <!-- 描述 -->
              <el-form-item :label="t('templateEditor.description')" prop="description">
                <el-input
                  v-model="form.description"
                  type="textarea"
                  :rows="2"
                  :placeholder="t('templateEditor.descriptionPlaceholder')" />
              </el-form-item>
              <!-- Tags -->
              <el-form-item :label="t('templateEditor.tags')">
                <el-select
                  v-model="form.tags"
                  multiple
                  filterable
                  allow-create
                  :placeholder="t('templateEditor.tagsPlaceholder')" />
              </el-form-item>
              <!-- 公开/私有 -->
              <el-form-item :label="t('templateEditor.visibility')">
                <el-switch
                  v-model="form.is_public"
                  :active-text="t('templateEditor.public')"
                  :inactive-text="t('templateEditor.private')" />
              </el-form-item>
            </div>

            <!-- ===== 缩略图块 ===== -->
            <div class="form-section">
              <div class="section-title">{{ t('templateEditor.thumbnailUrl') }}</div>
              <el-form-item :label="t('templateEditor.thumbnailUrl')">
                <div class="thumb-input-row">
                  <el-input
                    v-model="form.thumbnail_url"
                    :placeholder="t('templateEditor.thumbnailUrlPlaceholder')" />
                  <el-button
                    :loading="generatingThumb"
                    type="primary"
                    plain
                    size="default"
                    @click="handleAiGenerateThumb">
                    <el-icon><MagicStick /></el-icon>
                    {{ t('templateEditor.aiGenerateThumbnail') }}
                  </el-button>
                  <el-button
                    type="primary"
                    plain
                    size="default"
                    @click="historyPickerVisible = true">
                    <el-icon><PictureFilled /></el-icon>
                    {{ t('templateEditor.historyImage') }}
                  </el-button>
                </div>
                <div v-if="form.thumbnail_url" class="thumbnail-preview">
                  <img :src="form.thumbnail_url" alt="thumbnail" @error="onThumbError" />
                </div>
              </el-form-item>
            </div>

            <!-- ===== 输入参数块 ===== -->
            <div class="form-section">
              <div class="section-title">
                {{ t('templateEditor.inputParams') }}
                <el-button link type="primary" size="small" @click="addInputRow">
                  <el-icon><Plus /></el-icon>
                  {{ t('common.add') }}
                </el-button>
              </div>
              <div v-if="form.inputs_config.length === 0" class="empty-block">
                {{ t('templateEditor.inputsEmpty') }}
              </div>
              <div
                v-for="(item, idx) in form.inputs_config"
                :key="'in-' + idx"
                class="input-row">
                <el-input
                  v-model="item.key"
                  :placeholder="t('templateEditor.fieldKey')"
                  class="col-key" />
                <el-input
                  v-model="item.label"
                  :placeholder="t('templateEditor.fieldLabel')"
                  class="col-label" />
                <el-select
                  v-model="item.type"
                  :placeholder="t('templateEditor.fieldType')"
                  class="col-type"
                  @change="onInputTypeChange(item)">
                  <el-option label="text" value="text" />
                  <el-option label="number" value="number" />
                  <el-option label="style_select" value="style_select" />
                  <el-option label="boolean" value="boolean" />
                </el-select>
                <el-checkbox v-model="item.required" class="col-required">
                  {{ t('templateEditor.fieldRequired') }}
                </el-checkbox>
                <el-input
                  v-model="item.placeholder"
                  :placeholder="t('templateEditor.fieldPlaceholder')"
                  class="col-placeholder" />
                <!-- default 控件按 type 联动 -->
                <component
                  :is="getDefaultControl(item.type)"
                  v-model="item.default"
                  :placeholder="t('templateEditor.fieldDefault')"
                  :min="item.min"
                  :max="item.max"
                  class="col-default">
                </component>
                <!-- number 类型额外提供 min/max -->
                <template v-if="item.type === 'number'">
                  <el-input-number
                    v-model="item.min"
                    :placeholder="t('templateEditor.fieldMin')"
                    class="col-min"
                    controls-position="right" />
                  <el-input-number
                    v-model="item.max"
                    :placeholder="t('templateEditor.fieldMax')"
                    class="col-max"
                    controls-position="right" />
                </template>
                <el-button
                  link
                  type="danger"
                  size="small"
                  @click="removeInputRow(idx)">
                  <el-icon><Delete /></el-icon>
                </el-button>
              </div>
            </div>

            <!-- ===== 步骤配置块 ===== -->
            <div class="form-section">
              <div class="section-title">
                {{ t('templateEditor.stepsConfig') }}
                <el-button link type="primary" size="small" @click="addStep">
                  <el-icon><Plus /></el-icon>
                  {{ t('common.add') }}
                </el-button>
              </div>
              <div v-if="form.steps_config.length === 0" class="empty-block">
                {{ t('templateEditor.stepsEmpty') }}
              </div>
              <el-collapse v-model="activeStepKeys" class="steps-collapse">
                <el-collapse-item
                  v-for="(step, idx) in form.steps_config"
                  :key="'st-' + idx"
                  :name="idx">
                  <template #title>
                    <div class="step-card-header">
                      <span class="step-index">#{{ idx + 1 }}</span>
                      <span class="step-key">{{ step.key || t('templateEditor.untitledStep') }}</span>
                      <el-tag size="small" type="info" effect="plain">{{ step.type || '-' }}</el-tag>
                      <div class="step-header-actions" @click.stop>
                        <el-button
                          link
                          size="small"
                          :disabled="idx === 0"
                          @click="moveStep(idx, -1)">
                          <el-icon><Top /></el-icon>
                        </el-button>
                        <el-button
                          link
                          size="small"
                          :disabled="idx === form.steps_config.length - 1"
                          @click="moveStep(idx, 1)">
                          <el-icon><Bottom /></el-icon>
                        </el-button>
                        <el-button
                          link
                          type="danger"
                          size="small"
                          @click="removeStep(idx)">
                          <el-icon><Delete /></el-icon>
                        </el-button>
                      </div>
                    </div>
                  </template>
                  <div class="step-form">
                    <el-form-item :label="t('templateEditor.fieldKey')">
                      <el-input v-model="step.key" :placeholder="t('templateEditor.stepKeyPlaceholder')" />
                    </el-form-item>
                    <el-form-item :label="t('templateEditor.fieldLabel')">
                      <el-input v-model="step.name" :placeholder="t('templateEditor.stepNamePlaceholder')" />
                    </el-form-item>
                    <el-form-item :label="t('templateEditor.fieldType')">
                      <el-select v-model="step.type" :placeholder="t('templateEditor.fieldType')" @change="onStepTypeChange(step)">
                        <el-option label="llm_generate" value="llm_generate" />
                        <el-option label="image_batch" value="image_batch" />
                        <el-option label="tts_generate" value="tts_generate" />
                        <el-option label="video_batch" value="video_batch" />
                        <el-option label="ffmpeg_composite" value="ffmpeg_composite" />
                      </el-select>
                    </el-form-item>
                    <el-form-item :label="t('templateEditor.dependsOn')">
                      <el-select
                        v-model="step.depends_on"
                        multiple
                        :placeholder="t('templateEditor.dependsOnPlaceholder')">
                        <el-option
                          v-for="other in otherStepKeys(step)"
                          :key="other.key"
                          :label="other.key + (other.name ? ' / ' + other.name : '')"
                          :value="other.key" />
                      </el-select>
                    </el-form-item>

                    <!-- config 字段按 type 联动 -->
                    <!-- llm_generate: use_script_template / model / temperature / json_output / prompt_template -->
                    <template v-if="step.type === 'llm_generate'">
                      <el-form-item label="use_script_template">
                        <el-switch v-model="step.config.use_script_template" />
                      </el-form-item>
                      <el-form-item label="model">
                        <el-input v-model="step.config.model" placeholder="e.g. agnes-chat-1.1" />
                      </el-form-item>
                      <el-form-item label="temperature">
                        <el-input-number
                          v-model="step.config.temperature"
                          :min="0" :max="2" :step="0.1"
                          controls-position="right" />
                      </el-form-item>
                      <el-form-item label="json_output">
                        <el-switch v-model="step.config.json_output" />
                      </el-form-item>
                      <el-form-item label="prompt_template">
                        <el-input
                          v-model="step.config.prompt_template"
                          type="textarea"
                          :rows="4"
                          placeholder="Jinja2 / f-string 模板" />
                      </el-form-item>
                    </template>

                    <!-- image_batch: source / from_step / items_path / prompt_field / size -->
                    <template v-else-if="step.type === 'image_batch'">
                      <el-form-item label="source">
                        <el-radio-group v-model="step.config.source">
                          <el-radio value="from_step">from_step</el-radio>
                          <el-radio value="items_path">items_path</el-radio>
                        </el-radio-group>
                      </el-form-item>
                      <el-form-item v-if="step.config.source === 'from_step'" label="from_step">
                        <el-select v-model="step.config.from_step" :placeholder="t('templateEditor.dependsOnPlaceholder')">
                          <el-option
                            v-for="other in otherStepKeys(step)"
                            :key="other.key"
                            :label="other.key"
                            :value="other.key" />
                        </el-select>
                      </el-form-item>
                      <el-form-item v-if="step.config.source === 'items_path'" label="items_path">
                        <el-input v-model="step.config.items_path" placeholder="e.g. scenes" />
                      </el-form-item>
                      <el-form-item label="prompt_field">
                        <el-input v-model="step.config.prompt_field" placeholder="e.g. prompt" />
                      </el-form-item>
                      <el-form-item label="max_concurrent">
                        <el-input-number v-model="step.config.size" :min="1" :max="20" controls-position="right" />
                      </el-form-item>
                    </template>

                    <!-- tts_generate: voice / speed -->
                    <template v-else-if="step.type === 'tts_generate'">
                      <el-form-item label="voice">
                        <el-input v-model="step.config.voice" placeholder="e.g. female_gentle" />
                      </el-form-item>
                      <el-form-item label="speed">
                        <el-input-number v-model="step.config.speed" :min="0.5" :max="2" :step="0.1" controls-position="right" />
                      </el-form-item>
                    </template>

                    <!-- video_batch: source / from_step / items_path / size / max_concurrent -->
                    <template v-else-if="step.type === 'video_batch'">
                      <el-form-item label="source">
                        <el-radio-group v-model="step.config.source">
                          <el-radio value="from_step">from_step</el-radio>
                          <el-radio value="items_path">items_path</el-radio>
                        </el-radio-group>
                      </el-form-item>
                      <el-form-item v-if="step.config.source === 'from_step'" label="from_step">
                        <el-select v-model="step.config.from_step" :placeholder="t('templateEditor.dependsOnPlaceholder')">
                          <el-option
                            v-for="other in otherStepKeys(step)"
                            :key="other.key"
                            :label="other.key"
                            :value="other.key" />
                        </el-select>
                      </el-form-item>
                      <el-form-item v-if="step.config.source === 'items_path'" label="items_path">
                        <el-input v-model="step.config.items_path" placeholder="e.g. scenes" />
                      </el-form-item>
                      <el-form-item label="max_concurrent">
                        <el-input-number v-model="step.config.max_concurrent" :min="1" :max="20" controls-position="right" />
                      </el-form-item>
                    </template>

                    <!-- ffmpeg_composite: output_format / codec -->
                    <template v-else-if="step.type === 'ffmpeg_composite'">
                      <el-form-item label="output_format">
                        <el-input v-model="step.config.output_format" placeholder="e.g. mp4" />
                      </el-form-item>
                      <el-form-item label="codec">
                        <el-input v-model="step.config.codec" placeholder="e.g. libx264" />
                      </el-form-item>
                    </template>
                  </div>
                </el-collapse-item>
              </el-collapse>
            </div>

            <!-- ===== 高级设置块 ===== -->
            <div class="form-section">
              <div class="section-title">{{ t('templateEditor.advancedSettings') }}</div>
              <el-form-item :label="t('templateEditor.scriptTemplate')">
                <el-select
                  v-model="form.script_template_id"
                  clearable
                  :placeholder="t('templateEditor.scriptTemplatePlaceholder')">
                  <el-option
                    v-for="s in scriptTemplates"
                    :key="s.id"
                    :label="s.name"
                    :value="s.id" />
                </el-select>
              </el-form-item>
              <el-form-item :label="t('templateEditor.outputMapping')">
                <el-input
                  v-model="outputMappingText"
                  type="textarea"
                  :rows="4"
                  :placeholder="t('templateEditor.outputMappingPlaceholder')" />
                <div class="form-hint">{{ t('templateEditor.outputMappingHint') }}</div>
              </el-form-item>
              <el-form-item :label="t('templateEditor.estimatedCredits')">
                <el-input-number v-model="form.estimated_credits" :min="0" controls-position="right" />
              </el-form-item>
              <el-form-item :label="t('templateEditor.estimatedTime')">
                <el-input-number v-model="form.estimated_time_minutes" :min="1" controls-position="right" />
              </el-form-item>
            </div>
          </template>

          <!-- 操作按钮 -->
          <el-form-item>
            <el-button type="primary" @click="handleSave" :loading="saving">
              {{ t('common.save') }}
            </el-button>
            <el-button @click="goBack">{{ t('common.cancel') }}</el-button>
          </el-form-item>
        </el-form>

        <!-- ============ 右侧粘性预览侧栏 ============ -->
        <div class="preview-sidebar">
          <div class="preview-inner">
            <div class="preview-title">{{ t('templateEditor.previewTitle') }}</div>

            <!-- inputs_config 实时预览 -->
            <div v-if="previewInputs.length > 0" class="preview-section">
              <div class="preview-subtitle">{{ t('templateEditor.inputParams') }}</div>
              <div
                v-for="(item, idx) in previewInputs"
                :key="'pv-in-' + idx"
                class="preview-input">
                <label class="preview-label">
                  <span v-if="item.required" class="required-mark">*</span>
                  {{ item.label || item.key || '?' }}
                </label>
                <!-- 按 type 联动展示控件 -->
                <el-input
                  v-if="item.type === 'text'"
                  :placeholder="item.placeholder || ''"
                  size="small"
                  disabled />
                <el-input-number
                  v-else-if="item.type === 'number'"
                  :placeholder="item.placeholder || ''"
                  size="small"
                  :min="item.min" :max="item.max"
                  controls-position="right"
                  disabled />
                <el-select
                  v-else-if="item.type === 'style_select'"
                  size="small"
                  disabled
                  :placeholder="t('templateEditor.fieldDefault')">
                  <el-option
                    v-for="s in stylePresets"
                    :key="s.id"
                    :label="s.name"
                    :value="s.id" />
                </el-select>
                <el-switch
                  v-else-if="item.type === 'boolean'"
                  size="small"
                  disabled />
                <el-input
                  v-else
                  size="small"
                  disabled />
              </div>
            </div>

            <!-- steps 流程图 -->
            <div v-if="previewSteps.length > 0" class="preview-section">
              <div class="preview-subtitle">{{ t('templateEditor.stepsConfig') }}</div>
              <div class="preview-flow">
                <div
                  v-for="(step, idx) in previewSteps"
                  :key="'pv-st-' + idx"
                  class="flow-node">
                  <div class="flow-node-title">
                    <span class="flow-index">{{ idx + 1 }}</span>
                    <span class="flow-name">{{ step.name || step.key || '?' }}</span>
                  </div>
                  <div class="flow-type">{{ step.type }}</div>
                  <div v-if="step.depends_on && step.depends_on.length > 0" class="flow-deps">
                    ← {{ step.depends_on.join(', ') }}
                  </div>
                  <el-icon v-if="idx < previewSteps.length - 1" class="flow-arrow"><ArrowDown /></el-icon>
                </div>
              </div>
            </div>

            <!-- 空预览 -->
            <div v-if="previewInputs.length === 0 && previewSteps.length === 0" class="preview-empty">
              {{ t('templateEditor.previewEmpty') }}
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 模板导入/导出对话框（编辑模式下用于导出当前模板） -->
    <TemplateImportExportDialog
      v-model="ioDialogVisible"
      :preset-template-ids="presetExportIds"
      :initial-tab="ioDialogTab" />

    <!-- 从历史选图弹窗 -->
    <HistoryImagePicker
      v-model="historyPickerVisible"
      @select="onPickHistoryImage" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, reactive, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Download, UploadFilled, RemoveFilled, MagicStick, PictureFilled,
  Plus, Delete, Top, Bottom, ArrowDown,
} from '@element-plus/icons-vue'
import { useI18n } from '@/i18n'
import {
  createTemplate,
  updateTemplate,
  getPipelineTemplateDetail,
  submitTemplatePublic,
  cancelTemplatePublic,
  getTemplateRevision,
  generateTemplateThumbnail,
  getStylePresets,
  getScriptTemplates,
} from '@/api/pipeline'
import type { PipelineTemplate, PipelineTemplateRevision, StylePreset, ScriptTemplate } from '@/types'
import type { FormInstance, FormRules } from 'element-plus'
import TemplateImportExportDialog from '@/components/pipeline/TemplateImportExportDialog.vue'
import HistoryImagePicker from '@/components/pipeline/HistoryImagePicker.vue'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()

// 是否编辑模式
const templateId = computed(() => (route.params.id as string) || '')
const isEdit = computed(() => !!templateId.value)

const loading = ref(false)
const saving = ref(false)
const generatingThumb = ref(false)
const formRef = ref<FormInstance>()
const templateData = ref<PipelineTemplate | null>(null)

// 是否存在 pending revision（编辑器进入时拉取）
const hasPendingRevision = ref(false)

// ---------- 模板导入/导出 ----------
const ioDialogVisible = ref(false)
const ioDialogTab = ref<'export' | 'import'>('export')
const presetExportIds = ref<number[]>([])

// ---------- 历史选图 ----------
const historyPickerVisible = ref(false)

// ---------- 专家模式 ----------
const expertMode = ref(false)

// ---------- 关联资源（StylePreset / ScriptTemplate） ----------
const stylePresets = ref<StylePreset[]>([])
const scriptTemplates = ref<ScriptTemplate[]>([])

// 分类选项
const categoryOptions = [
  { value: 'comic', label: t('workshop.category.comic') },
  { value: 'commercial', label: t('workshop.category.commercial') },
  { value: 'education', label: t('workshop.category.education') },
  { value: 'entertainment', label: t('workshop.category.entertainment') },
]

// 专家模式 JSON 文本（仅专家模式使用）
const inputsConfigText = ref('[]')
const stepsConfigText = ref('[]')

// 旧 placeholder 文案保留作为专家模式参考
const inputsConfigPlaceholder = 'JSON 数组，每个元素为 {key, label, type, required, placeholder, default, min, max}'
const stepsConfigPlaceholder = 'JSON 数组，每个元素为 {key, name, type, config, depends_on}'

// 输出映射 JSON 文本
const outputMappingText = ref('{}')

// 折叠面板默认展开项
const activeStepKeys = ref<number[]>([0])

// 表单结构
const form = reactive({
  key: '',
  name: '',
  description: '',
  category: 'comic',
  thumbnail_url: '',
  tags: [] as string[],
  is_public: false,
  inputs_config: [] as any[],
  steps_config: [] as any[],
  script_template_id: undefined as number | undefined,
  estimated_credits: 0,
  estimated_time_minutes: 10,
})

const rules: FormRules = {
  name: [{ required: true, message: t('templateEditor.nameRequired'), trigger: 'blur' }],
  key: [
    { required: true, message: t('templateEditor.keyRequired'), trigger: 'blur' },
    { pattern: /^[a-z][a-z0-9_]*$/, message: t('templateEditor.keyHint'), trigger: 'blur' },
  ],
  category: [{ required: true, message: t('templateEditor.categoryRequired'), trigger: 'change' }],
}

function goBack() {
  router.push('/workshop')
}

// ---------- 模板审核状态 ----------
function getTemplateStatus(tpl: PipelineTemplate): 'private' | 'pending' | 'approved' | 'rejected' | 'builtin' {
  if (tpl.is_builtin) return 'builtin'
  if (tpl.is_rejected) return 'rejected'
  if (tpl.is_public && tpl.is_approved) return 'approved'
  if (tpl.is_public && !tpl.is_approved) return 'pending'
  return 'private'
}

function getStatusTagType(tpl: PipelineTemplate): 'success' | 'warning' | 'danger' | 'info' | 'primary' {
  const status = getTemplateStatus(tpl)
  switch (status) {
    case 'approved': return 'success'
    case 'pending': return 'warning'
    case 'rejected': return 'danger'
    case 'builtin': return 'primary'
    default: return 'info'
  }
}

function canSubmitPublic(tpl: PipelineTemplate): boolean {
  if (tpl.is_builtin) return false
  if (tpl.is_rejected) return false
  if (tpl.is_public && tpl.is_approved) return false
  return true
}

function openExportCurrent() {
  if (!templateId.value) return
  presetExportIds.value = [Number(templateId.value)]
  ioDialogTab.value = 'export'
  ioDialogVisible.value = true
}

/** 提交到模板市场 */
async function handleSubmitPublic() {
  if (!templateData.value) return
  try {
    const { value } = await ElMessageBox.prompt(
      t('workshop.submitPublicTip'),
      t('workshop.shareToMarket'),
      {
        confirmButtonText: t('common.submit'),
        cancelButtonText: t('common.cancel'),
        inputPlaceholder: t('workshop.submitPublicPlaceholder'),
        inputType: 'textarea',
        inputValidator: (val) => val != null && val.trim().length <= 500 || t('workshop.submitPublicReasonTooLong'),
        type: 'info',
      }
    )
    const res = await submitTemplatePublic(templateData.value.id, (value || '').trim())
    if (res.rejected) {
      ElMessage.warning(t('workshop.submitPublicRejected', { words: res.hit_words?.slice(0, 3).join(', ') || '' }))
    } else {
      ElMessage.success(t('workshop.submitPublicSuccess'))
    }
    const refreshed = await getPipelineTemplateDetail(templateData.value.id)
    templateData.value = refreshed
  } catch (e: any) {
    if (e !== 'cancel') {
      ElMessage.error(e?.message || t('workshop.submitPublicFailed'))
    }
  }
}

/** 取消公开 */
async function handleCancelPublic() {
  if (!templateData.value) return
  try {
    await ElMessageBox.confirm(
      t('workshop.cancelPublicConfirm'),
      t('workshop.cancelPublic'),
      { confirmButtonText: t('common.confirm'), cancelButtonText: t('common.cancel'), type: 'warning' }
    )
    await cancelTemplatePublic(templateData.value.id)
    ElMessage.success(t('workshop.cancelPublicSuccess'))
    const refreshed = await getPipelineTemplateDetail(templateData.value.id)
    templateData.value = refreshed
  } catch (e: any) {
    if (e !== 'cancel') {
      ElMessage.error(e?.message || t('workshop.cancelPublicFailed'))
    }
  }
}

function onThumbError(e: Event) {
  const img = e.target as HTMLImageElement
  img.style.display = 'none'
}

// ---------- 缩略图相关 ----------
/** AI 生图按钮 */
async function handleAiGenerateThumb() {
  if (!isEdit.value) {
    ElMessage.warning(t('templateEditor.aiGenAfterCreate'))
    return
  }
  generatingThumb.value = true
  try {
    const res = await generateTemplateThumbnail(Number(templateId.value))
    form.thumbnail_url = res.thumbnail_url
    ElMessage.success(t('templateEditor.aiGenSuccess'))
  } catch (e: any) {
    ElMessage.error(e?.message || t('templateEditor.aiGenFailed'))
  } finally {
    generatingThumb.value = false
  }
}

/** 历史选图回调 */
function onPickHistoryImage(url: string) {
  form.thumbnail_url = url
}

// ---------- 输入参数（inputs_config）操作 ----------
function addInputRow() {
  form.inputs_config.push({
    key: '',
    label: '',
    type: 'text',
    required: false,
    placeholder: '',
    default: '',
  })
}

function removeInputRow(idx: number) {
  form.inputs_config.splice(idx, 1)
}

/** type 切换时重置 default/min/max 字段 */
function onInputTypeChange(item: any) {
  switch (item.type) {
    case 'number':
      item.default = typeof item.default === 'number' ? item.default : 0
      if (item.min == null) item.min = 0
      if (item.max == null) item.max = 100
      break
    case 'boolean':
      item.default = !!item.default
      delete item.min
      delete item.max
      break
    case 'style_select':
      item.default = item.default ?? ''
      delete item.min
      delete item.max
      break
    default:
      item.default = item.default ?? ''
      delete item.min
      delete item.max
  }
}

/** 根据 type 返回 default 控件组件名（用于 <component :is>） */
function getDefaultControl(type: string) {
  switch (type) {
    case 'number': return 'el-input-number'
    case 'boolean': return 'el-switch'
    case 'style_select': return 'el-select'
    default: return 'el-input'
  }
}

// ---------- 步骤（steps_config）操作 ----------
function addStep() {
  form.steps_config.push({
    key: '',
    name: '',
    type: 'llm_generate',
    depends_on: [],
    config: {},
  })
  activeStepKeys.value.push(form.steps_config.length - 1)
}

function removeStep(idx: number) {
  form.steps_config.splice(idx, 1)
  // 重新计算折叠面板展开项索引
  activeStepKeys.value = activeStepKeys.value
    .filter((k) => k !== idx)
    .map((k) => (k > idx ? k - 1 : k))
}

/** 上移/下移 step：dir = -1 上移，dir = 1 下移 */
function moveStep(idx: number, dir: number) {
  const target = idx + dir
  if (target < 0 || target >= form.steps_config.length) return
  const arr = form.steps_config
  ;[arr[idx], arr[target]] = [arr[target], arr[idx]]
}

/** type 切换时初始化 config 默认值 */
function onStepTypeChange(step: any) {
  // 切换时重置 config
  step.config = {}
  switch (step.type) {
    case 'llm_generate':
      step.config = { use_script_template: false, model: '', temperature: 0.7, json_output: false, prompt_template: '' }
      break
    case 'image_batch':
      step.config = { source: 'from_step', from_step: '', items_path: '', prompt_field: 'prompt', size: 4 }
      break
    case 'tts_generate':
      step.config = { voice: '', speed: 1.0 }
      break
    case 'video_batch':
      step.config = { source: 'from_step', from_step: '', items_path: '', max_concurrent: 2 }
      break
    case 'ffmpeg_composite':
      step.config = { output_format: 'mp4', codec: 'libx264' }
      break
  }
}

/** 返回除当前 step 之外的其他 step（用于 depends_on 多选） */
function otherStepKeys(currentStep: any) {
  return form.steps_config.filter((s) => s !== currentStep && !!s.key)
}

// ---------- 专家模式：结构化 <-> JSON 双向切换 ----------
watch(expertMode, (newVal) => {
  if (newVal) {
    // 切换到专家模式：序列化结构化数据到 JSON textarea
    inputsConfigText.value = JSON.stringify(form.inputs_config, null, 2)
    stepsConfigText.value = JSON.stringify(form.steps_config, null, 2)
  } else {
    // 切回结构化模式：解析 JSON 回填表单；解析失败保留 textarea 模式
    try {
      const parsedInputs = JSON.parse(inputsConfigText.value)
      const parsedSteps = JSON.parse(stepsConfigText.value)
      if (!Array.isArray(parsedInputs) || !Array.isArray(parsedSteps)) {
        throw new Error('not array')
      }
      form.inputs_config = parsedInputs
      form.steps_config = parsedSteps
    } catch (e: any) {
      ElMessage.error(t('templateEditor.expertModeParseFailed'))
      expertMode.value = true
    }
  }
})

// ---------- 右侧预览计算属性 ----------
const previewInputs = computed(() => (expertMode.value ? [] : form.inputs_config))
const previewSteps = computed(() => (expertMode.value ? [] : form.steps_config))

// ---------- 加载关联资源（StylePreset / ScriptTemplate） ----------
async function loadRelatedResources() {
  try {
    const [styleRes, scriptRes] = await Promise.all([
      getStylePresets({ page: 1, page_size: 100 }),
      getScriptTemplates({ page: 1, page_size: 100 }),
    ])
    stylePresets.value = styleRes.items || []
    scriptTemplates.value = scriptRes.items || []
  } catch (e) {
    // 静默失败，不影响编辑器主流程
  }
}

// ---------- 从模板/Revision 数据填充表单 ----------
function fillFormFromTemplate(tpl: PipelineTemplate) {
  form.key = tpl.key
  form.name = tpl.name
  form.description = tpl.description || ''
  form.category = tpl.category || 'comic'
  form.thumbnail_url = tpl.thumbnail_url || ''
  form.tags = tpl.tags || []
  form.is_public = tpl.is_public || false
  form.inputs_config = (tpl.inputs_config || []).map((it: any) => ({ ...it }))
  form.steps_config = (tpl.steps_config || []).map((it: any) => ({ ...it, config: { ...(it.config || {}) } }))
  form.script_template_id = tpl.script_template_id ?? undefined
  form.estimated_credits = tpl.estimated_credits ?? 0
  form.estimated_time_minutes = tpl.estimated_time_minutes ?? 10
  outputMappingText.value = tpl.output_mapping ? JSON.stringify(tpl.output_mapping, null, 2) : '{}'
}

function fillFormFromRevision(rev: PipelineTemplateRevision) {
  form.name = rev.name
  form.description = rev.description || ''
  form.category = rev.category || 'comic'
  form.thumbnail_url = rev.thumbnail_url || ''
  form.tags = rev.tags || []
  form.inputs_config = (rev.inputs_config || []).map((it: any) => ({ ...it }))
  form.steps_config = (rev.steps_config || []).map((it: any) => ({ ...it, config: { ...(it.config || {}) } }))
  form.script_template_id = rev.script_template_id ?? undefined
  form.estimated_credits = rev.estimated_credits ?? 0
  form.estimated_time_minutes = rev.estimated_time_minutes ?? 10
  outputMappingText.value = rev.output_mapping ? JSON.stringify(rev.output_mapping, null, 2) : '{}'
  // 注意：revision 不含 is_public / key 字段，保留从原模板加载的值
}

// ---------- 生命周期 ----------
onMounted(async () => {
  // 加载关联资源（StylePreset / ScriptTemplate）
  loadRelatedResources()

  if (!isEdit.value) {
    // 新建模式：默认插入一行示例输入参数
    form.inputs_config = [{
      key: 'theme',
      label: t('templateEditor.defaultInputLabel'),
      type: 'text',
      required: true,
      placeholder: '',
      default: '',
    }]
    return
  }

  loading.value = true
  try {
    const tpl = await getPipelineTemplateDetail(Number(templateId.value))
    templateData.value = tpl

    // 内置模板不可编辑
    if (tpl.is_builtin) {
      ElMessage.warning(t('templateEditor.builtinNotEditable'))
      router.push('/workshop')
      return
    }

    fillFormFromTemplate(tpl)

    // 公开已审核模板：尝试拉取 pending revision
    if (tpl.is_public && tpl.is_approved && !tpl.is_builtin && tpl.has_pending_revision) {
      try {
        const rev = await getTemplateRevision(tpl.id)
        fillFormFromRevision(rev)
        hasPendingRevision.value = true
      } catch (e: any) {
        // 404 表示无 pending revision，忽略
      }
    } else if (tpl.has_pending_revision) {
      // 兜底：has_pending_revision 标记为 true 但前面分支没拉取
      try {
        const rev = await getTemplateRevision(tpl.id)
        fillFormFromRevision(rev)
        hasPendingRevision.value = true
      } catch (_) { /* ignore */ }
    }
  } catch (e: any) {
    ElMessage.error(e?.message || t('templateEditor.loadFailed'))
    router.push('/workshop')
  } finally {
    loading.value = false
  }
})

// ---------- 保存逻辑 ----------
/** 基础校验：name/key 必填、inputs_config key 唯一、steps_config key 唯一、depends_on 引用存在 */
function validateBeforeSave(): string | null {
  if (!form.name.trim()) return t('templateEditor.nameRequired')
  if (!form.key.trim()) return t('templateEditor.keyRequired')
  if (!isEdit.value && !/^[a-z][a-z0-9_]*$/.test(form.key)) return t('templateEditor.keyHint')

  // inputs_config key 唯一
  const inputKeys = new Set<string>()
  for (const item of form.inputs_config) {
    if (!item.key) return t('templateEditor.inputKeyRequired')
    if (inputKeys.has(item.key)) return t('templateEditor.inputKeyDuplicated', { key: item.key })
    inputKeys.add(item.key)
  }

  // steps_config key 唯一
  const stepKeys = new Set<string>()
  for (const step of form.steps_config) {
    if (!step.key) return t('templateEditor.stepKeyRequired')
    if (stepKeys.has(step.key)) return t('templateEditor.stepKeyDuplicated', { key: step.key })
    stepKeys.add(step.key)
  }

  // depends_on 引用的 step key 必须存在
  for (const step of form.steps_config) {
    const deps = step.depends_on || []
    for (const dep of deps) {
      if (!stepKeys.has(dep)) {
        return t('templateEditor.dependsOnNotFound', { dep, step: step.key })
      }
    }
  }

  // output_mapping JSON 解析校验
  if (outputMappingText.value.trim()) {
    try {
      JSON.parse(outputMappingText.value)
    } catch {
      return t('templateEditor.outputMappingInvalid')
    }
  }

  return null
}

async function handleSave() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return

  // 专家模式下需要先把 JSON 解析回结构化数据
  if (expertMode.value) {
    try {
      const parsedInputs = JSON.parse(inputsConfigText.value)
      const parsedSteps = JSON.parse(stepsConfigText.value)
      if (!Array.isArray(parsedInputs) || !Array.isArray(parsedSteps)) {
        throw new Error('not array')
      }
      form.inputs_config = parsedInputs
      form.steps_config = parsedSteps
    } catch {
      ElMessage.error(t('templateEditor.expertModeParseFailed'))
      return
    }
  }

  // 基础校验
  const errMsg = validateBeforeSave()
  if (errMsg) {
    ElMessage.error(errMsg)
    return
  }

  // 组装更新 payload
  let outputMapping: Record<string, any> | undefined
  if (outputMappingText.value.trim()) {
    try {
      outputMapping = JSON.parse(outputMappingText.value)
    } catch {
      // 校验阶段已拦截，这里不会触发
    }
  }

  saving.value = true
  try {
    if (isEdit.value) {
      await updateTemplate(Number(templateId.value), {
        name: form.name,
        description: form.description,
        category: form.category,
        thumbnail_url: form.thumbnail_url || undefined,
        inputs_config: form.inputs_config,
        steps_config: form.steps_config,
        tags: form.tags.length > 0 ? form.tags : undefined,
        is_public: form.is_public,
        script_template_id: form.script_template_id,
        output_mapping: outputMapping,
        estimated_credits: form.estimated_credits,
        estimated_time_minutes: form.estimated_time_minutes,
      })
      ElMessage.success(t('templateEditor.updateSuccess'))
    } else {
      await createTemplate({
        key: form.key,
        name: form.name,
        description: form.description || undefined,
        category: form.category,
        thumbnail_url: form.thumbnail_url || undefined,
        inputs_config: form.inputs_config,
        steps_config: form.steps_config,
        tags: form.tags.length > 0 ? form.tags : undefined,
        is_public: form.is_public,
      })
      ElMessage.success(t('templateEditor.createSuccess'))
    }
    router.push('/workshop')
  } catch (e: any) {
    ElMessage.error(e?.message || t('templateEditor.saveFailed'))
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.template-editor {
  max-width: 1280px;
  margin: 0 auto;
  padding: 24px;

  .editor-header {
    margin-bottom: 16px;
    .header-title {
      font-size: 18px;
      font-weight: 600;
    }
    .status-tag {
      margin-right: 12px;
    }
    .expert-mode-wrap {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      margin-right: 16px;
      padding: 0 8px;
      border: 1px solid var(--el-border-color);
      border-radius: 4px;
      height: 24px;
    }
    .expert-mode-label {
      font-size: 12px;
      color: var(--el-text-color-secondary);
    }
  }

  .revision-alert {
    margin-bottom: 16px;
  }

  .editor-body {
    background: var(--el-bg-color);
    border-radius: 8px;
    padding: 24px;
  }

  .editor-layout {
    display: flex;
    gap: 24px;
    align-items: flex-start;
  }

  .editor-form {
    flex: 1;
    min-width: 0;
    max-width: 820px;
  }

  .form-hint {
    font-size: 12px;
    color: var(--el-text-color-secondary);
    margin-top: 4px;
  }

  /* 分块表单 */
  .form-section {
    border: 1px solid var(--el-border-color-lighter);
    border-radius: 8px;
    padding: 16px 20px;
    margin-bottom: 20px;
    background: var(--el-fill-color-blank);
  }
  .section-title {
    font-size: 14px;
    font-weight: 600;
    color: var(--el-text-color-primary);
    margin-bottom: 16px;
    padding-bottom: 8px;
    border-bottom: 1px solid var(--el-border-color-lighter);
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  .thumbnail-preview {
    margin-top: 8px;
    max-width: 300px;
    img {
      width: 100%;
      height: auto;
      border-radius: 6px;
      border: 1px solid var(--el-border-color);
      object-fit: cover;
    }
  }

  .thumb-input-row {
    display: flex;
    gap: 8px;
    align-items: center;
    width: 100%;
  }
  .thumb-input-row .el-input {
    flex: 1;
  }

  /* 输入参数动态行 */
  .input-row {
    display: grid;
    grid-template-columns: 100px 120px 120px 80px 1fr 1fr auto;
    gap: 8px;
    align-items: center;
    margin-bottom: 10px;
    padding: 8px;
    background: var(--el-fill-color-light);
    border-radius: 6px;
  }
  .input-row .col-required {
    margin: 0;
  }
  /* number 类型的额外 min/max 在新行展示 */
  .input-row:has(.col-min) {
    grid-template-columns: 100px 120px 120px 80px 1fr 1fr 100px 100px auto;
  }

  .empty-block {
    padding: 20px;
    text-align: center;
    color: var(--el-text-color-placeholder);
    font-size: 13px;
    background: var(--el-fill-color-light);
    border-radius: 6px;
  }

  /* 步骤配置折叠卡片 */
  .steps-collapse {
    border: none;
  }
  .steps-collapse :deep(.el-collapse-item__header) {
    background: var(--el-fill-color-light);
    padding: 0 12px;
    border-radius: 6px;
    margin-bottom: 6px;
  }
  .steps-collapse :deep(.el-collapse-item__wrap) {
    border: none;
  }
  .steps-collapse :deep(.el-collapse-item__content) {
    padding: 12px 12px 16px 12px;
  }
  .step-card-header {
    display: flex;
    align-items: center;
    gap: 8px;
    width: 100%;
  }
  .step-index {
    color: var(--el-text-color-secondary);
    font-weight: 600;
    margin-right: 4px;
  }
  .step-key {
    flex: 1;
    font-weight: 500;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .step-header-actions {
    margin-left: auto;
    display: flex;
    gap: 4px;
  }
  .step-form {
    padding-top: 8px;
  }

  /* 右侧粘性预览侧栏 */
  .preview-sidebar {
    width: 320px;
    flex-shrink: 0;
  }
  .preview-inner {
    position: sticky;
    top: 16px;
    background: var(--el-fill-color-blank);
    border: 1px solid var(--el-border-color-lighter);
    border-radius: 8px;
    padding: 16px;
    max-height: calc(100vh - 32px);
    overflow-y: auto;
  }
  .preview-title {
    font-size: 14px;
    font-weight: 600;
    color: var(--el-text-color-primary);
    margin-bottom: 12px;
    padding-bottom: 8px;
    border-bottom: 1px solid var(--el-border-color-lighter);
  }
  .preview-section {
    margin-bottom: 16px;
  }
  .preview-subtitle {
    font-size: 12px;
    color: var(--el-text-color-secondary);
    margin-bottom: 8px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }
  .preview-input {
    margin-bottom: 10px;
  }
  .preview-label {
    display: block;
    font-size: 12px;
    color: var(--el-text-color-primary);
    margin-bottom: 4px;
  }
  .required-mark {
    color: var(--el-color-danger);
    margin-right: 2px;
  }
  .preview-flow {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .flow-node {
    position: relative;
    padding: 8px 10px;
    background: var(--el-fill-color-light);
    border-radius: 6px;
    border-left: 3px solid var(--el-color-primary);
  }
  .flow-node-title {
    display: flex;
    align-items: center;
    gap: 6px;
    margin-bottom: 4px;
  }
  .flow-index {
    background: var(--el-color-primary);
    color: #fff;
    font-size: 10px;
    width: 16px;
    height: 16px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-weight: 600;
  }
  .flow-name {
    font-size: 12px;
    font-weight: 500;
  }
  .flow-type {
    font-size: 11px;
    color: var(--el-text-color-secondary);
  }
  .flow-deps {
    font-size: 10px;
    color: var(--el-text-color-placeholder);
    margin-top: 2px;
  }
  .flow-arrow {
    position: absolute;
    left: 50%;
    bottom: -8px;
    transform: translateX(-50%);
    color: var(--el-text-color-placeholder);
  }
  .preview-empty {
    padding: 40px 0;
    text-align: center;
    color: var(--el-text-color-placeholder);
    font-size: 13px;
  }
}
</style>
