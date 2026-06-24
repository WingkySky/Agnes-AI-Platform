<!-- =====================================================
     水印配置页
     - 配置图片生成的水印效果
     - 支持文字水印、图片水印，位置、透明度等
     ===================================================== -->

<template>
  <div class="watermark-config-wrap">
    <header class="page-head">
      <div>
        <h2>{{ t('admin.watermark.title') }}</h2>
        <p class="muted">{{ t('admin.watermark.desc') }}</p>
      </div>
    </header>

    <el-card class="config-card" shadow="never">
      <div class="config-layout">
        <!-- 左侧配置区 -->
        <div class="config-left">
          <el-form :model="form" label-width="100px" label-position="right" size="default">
            <el-form-item :label="t('admin.watermark.type')">
              <el-radio-group v-model="form.type">
                <el-radio value="text">{{ t('admin.watermark.typeText') }}</el-radio>
                <el-radio value="image">{{ t('admin.watermark.typeImage') }}</el-radio>
              </el-radio-group>
            </el-form-item>

            <!-- 文字水印配置 -->
            <template v-if="form.type === 'text'">
              <el-form-item :label="t('admin.watermark.text')">
                <el-input v-model="form.text" :placeholder="t('admin.watermark.textPlaceholder')" maxlength="50" show-word-limit style="max-width: 320px" />
              </el-form-item>

              <el-form-item :label="t('admin.watermark.fontSize')">
                <div class="field-with-unit">
                  <el-input-number v-model="form.font_size" :min="12" :max="120" :step="1" controls-position="right" />
                  <span class="unit">px</span>
                </div>
              </el-form-item>

              <el-form-item :label="t('admin.watermark.fontColor')">
                <el-color-picker v-model="form.color" show-alpha size="default" />
              </el-form-item>
            </template>

            <!-- 图片水印配置 -->
            <template v-if="form.type === 'image'">
              <el-form-item :label="t('admin.watermark.image')">
                <div class="image-upload-field">
                  <el-upload
                    class="image-uploader"
                    :action="uploadUrl"
                    :headers="uploadHeaders"
                    :show-file-list="false"
                    :on-success="onUploadSuccess"
                    :on-error="onUploadError"
                    accept="image/*"
                  >
                    <div v-if="form.image_url" class="image-preview">
                      <img :src="form.image_url" :alt="t('admin.watermark.image')" />
                    </div>
                    <el-button v-else type="primary" :icon="Upload">{{ t('admin.watermark.upload') }}</el-button>
                  </el-upload>
                  <div class="url-input-row">
                    <span class="url-label">{{ t('admin.watermark.imageUrl') }}</span>
                    <el-input v-model="form.image_url" placeholder="https://..." />
                  </div>
                </div>
              </el-form-item>

              <el-form-item :label="t('admin.watermark.imageWidth')">
                <div class="field-with-unit">
                  <el-input-number v-model="form.image_width" :min="20" :max="500" :step="1" controls-position="right" />
                  <span class="unit">px</span>
                </div>
              </el-form-item>
            </template>

            <el-form-item :label="t('admin.watermark.opacity')">
              <div class="slider-field">
                <el-slider v-model="form.opacity" :min="0" :max="100" :step="1" class="slider-control" />
                <span class="slider-value">{{ form.opacity }}%</span>
              </div>
            </el-form-item>

            <el-form-item :label="t('admin.watermark.position')">
              <div class="position-picker">
                <div
                  v-for="pos in positionOptions"
                  :key="pos.value"
                  class="position-btn"
                  :class="{ active: form.position === pos.value }"
                  :title="pos.label"
                  @click="form.position = pos.value"
                >
                  <span class="position-dot"></span>
                </div>
              </div>
            </el-form-item>

            <el-form-item :label="t('admin.watermark.margin')">
              <div class="field-with-unit">
                <el-input-number v-model="form.margin" :min="0" :max="200" :step="1" controls-position="right" />
                <span class="unit">px</span>
              </div>
            </el-form-item>

            <el-form-item :label="t('admin.watermark.forceAll')">
              <div class="switch-field">
                <el-switch
                  v-model="form.force_all"
                  :active-text="t('admin.watermark.enabled')"
                  :inactive-text="t('admin.watermark.disabled')"
                />
                <div class="form-tip">{{ t('admin.watermark.forceAllTip') }}</div>
              </div>
            </el-form-item>
          </el-form>
        </div>

        <!-- 右侧预览区 -->
        <div class="config-right">
          <div class="preview-card">
            <div class="preview-header">
              <span class="preview-title">{{ t('admin.watermark.preview') }}</span>
            </div>
            <div class="preview-body">
              <div class="preview-image">
                <div class="placeholder-bg">
                  <el-icon :size="48" color="rgba(255,255,255,0.3)"><Picture /></el-icon>
                  <span class="placeholder-text">{{ t('admin.watermark.placeholder') }}</span>
                </div>
                <!-- 文字水印预览 -->
                <div
                  v-if="form.type === 'text' && form.text"
                  class="watermark-preview text-watermark"
                  :style="textWatermarkStyle"
                >
                  {{ form.text }}
                </div>
                <!-- 图片水印预览 -->
                <div
                  v-if="form.type === 'image' && form.image_url"
                  class="watermark-preview image-watermark"
                  :style="imageWatermarkStyle"
                >
                  <img :src="form.image_url" :alt="t('admin.watermark.image')" />
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="form-actions">
        <el-button @click="fetchConfig">{{ t('admin.watermark.reset') }}</el-button>
        <el-button type="primary" :loading="saving" @click="onSave">{{ t('admin.watermark.save') }}</el-button>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import { Upload, Picture } from '@element-plus/icons-vue'
import { getWatermarkConfig, updateWatermarkConfig } from '@/api/admin'
import type { WatermarkConfig } from '@/api/admin'

const { t } = useI18n()

const uploadUrl = '/api/admin/upload'
const uploadHeaders = {
  Authorization: `Bearer ${localStorage.getItem('access_token') || ''}`
}

const saving = ref(false)

const form = reactive<Partial<WatermarkConfig>>({
  type: 'text',
  text: 'Agnes AI',
  font_size: 24,
  color: '#ffffff',
  opacity: 30,
  position: 'bottom-right',
  margin: 20,
  image_url: '',
  image_width: 100,
  force_all: false
})

const positionOptions = [
  { value: 'top-left', label: computed(() => t('admin.watermark.positions.topLeft')) },
  { value: 'top-center', label: computed(() => t('admin.watermark.positions.topCenter')) },
  { value: 'top-right', label: computed(() => t('admin.watermark.positions.topRight')) },
  { value: 'center-left', label: computed(() => t('admin.watermark.positions.centerLeft')) },
  { value: 'center', label: computed(() => t('admin.watermark.positions.center')) },
  { value: 'center-right', label: computed(() => t('admin.watermark.positions.centerRight')) },
  { value: 'bottom-left', label: computed(() => t('admin.watermark.positions.bottomLeft')) },
  { value: 'bottom-center', label: computed(() => t('admin.watermark.positions.bottomCenter')) },
  { value: 'bottom-right', label: computed(() => t('admin.watermark.positions.bottomRight')) }
]

/** 根据位置计算样式 */
function getPositionStyle(position: string, margin: number) {
  const style: Record<string, string> = {}
  switch (position) {
    case 'top-left':
      style.top = `${margin}px`
      style.left = `${margin}px`
      break
    case 'top-center':
      style.top = `${margin}px`
      style.left = '50%'
      style.transform = 'translateX(-50%)'
      break
    case 'top-right':
      style.top = `${margin}px`
      style.right = `${margin}px`
      break
    case 'center-left':
      style.top = '50%'
      style.left = `${margin}px`
      style.transform = 'translateY(-50%)'
      break
    case 'center':
      style.top = '50%'
      style.left = '50%'
      style.transform = 'translate(-50%, -50%)'
      break
    case 'center-right':
      style.top = '50%'
      style.right = `${margin}px`
      style.transform = 'translateY(-50%)'
      break
    case 'bottom-left':
      style.bottom = `${margin}px`
      style.left = `${margin}px`
      break
    case 'bottom-center':
      style.bottom = `${margin}px`
      style.left = '50%'
      style.transform = 'translateX(-50%)'
      break
    case 'bottom-right':
      style.bottom = `${margin}px`
      style.right = `${margin}px`
      break
  }
  return style
}

const textWatermarkStyle = computed(() => {
  const posStyle = getPositionStyle(form.position || 'bottom-right', form.margin || 20)
  return {
    ...posStyle,
    fontSize: `${form.font_size}px`,
    color: form.color,
    opacity: (form.opacity || 30) / 100
  }
})

const imageWatermarkStyle = computed(() => {
  const posStyle = getPositionStyle(form.position || 'bottom-right', form.margin || 20)
  return {
    ...posStyle,
    width: `${form.image_width}px`,
    opacity: (form.opacity || 30) / 100
  }
})

async function fetchConfig() {
  try {
    const config = await getWatermarkConfig()
    Object.assign(form, config)
  } catch (e) {
    console.warn(e)
  }
}

function onUploadSuccess(response: any) {
  if (response?.url) {
    form.image_url = response.url
    ElMessage.success(t('admin.watermark.uploadSuccess'))
  } else {
    ElMessage.error(t('admin.watermark.uploadFailed'))
  }
}

function onUploadError() {
  ElMessage.error(t('admin.watermark.imageUploadFailed'))
}

async function onSave() {
  saving.value = true
  try {
    await updateWatermarkConfig(form)
    ElMessage.success(t('admin.watermark.saveSuccess'))
  } catch (e) {
    console.warn(e)
    ElMessage.error(t('admin.watermark.saveFailed'))
  } finally {
    saving.value = false
  }
}

onMounted(fetchConfig)
</script>

<style scoped>
.watermark-config-wrap {
  max-width: 1200px;
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
  font-weight: 600;
}

.muted {
  color: var(--agnes-text-muted);
  font-size: 13px;
  margin: 0;
}

.config-card {
  background: var(--agnes-bg-elevated);
  border: 1px solid var(--agnes-border);
  border-radius: 10px;
  padding: 28px 32px;
}

.config-layout {
  display: flex;
  gap: 40px;
  align-items: flex-start;
}

.config-left {
  flex: 1;
  min-width: 0;
}

.config-right {
  width: 340px;
  flex-shrink: 0;
}

/* ---------- 表单字段通用样式 ---------- */
.field-with-unit {
  display: flex;
  align-items: center;
  gap: 8px;
}

.unit {
  color: var(--agnes-text-muted);
  font-size: 13px;
  line-height: 1;
}

/* ---------- 滑块字段 ---------- */
.slider-field {
  display: flex;
  align-items: center;
  gap: 16px;
  width: 100%;
  max-width: 360px;
}

.slider-control {
  flex: 1;
  margin: 0;
}

.slider-value {
  color: var(--agnes-text-primary);
  font-size: 14px;
  font-weight: 500;
  min-width: 52px;
  text-align: right;
  font-variant-numeric: tabular-nums;
}

/* ---------- 位置选择器 ---------- */
.position-picker {
  display: grid;
  grid-template-columns: repeat(3, 40px);
  grid-template-rows: repeat(3, 40px);
  gap: 6px;
  padding: 8px;
  background: var(--agnes-bg-hover);
  border-radius: 8px;
  width: fit-content;
}

.position-btn {
  position: relative;
  width: 40px;
  height: 40px;
  border-radius: 6px;
  background: var(--agnes-bg-elevated);
  border: 1px solid var(--agnes-border);
  cursor: pointer;
  transition: all 0.2s ease;
  display: flex;
  align-items: center;
  justify-content: center;
}

.position-btn:hover {
  border-color: var(--el-color-primary-light-5);
  background: var(--el-color-primary-light-9);
}

.position-btn.active {
  background: var(--el-color-primary);
  border-color: var(--el-color-primary);
}

.position-btn.active .position-dot {
  background: #fff;
}

.position-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--agnes-text-muted);
  transition: all 0.2s ease;
}

/* ---------- 图片上传字段 ---------- */
.image-upload-field {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.image-uploader {
  display: inline-block;
}

.image-preview {
  width: 96px;
  height: 96px;
  border: 1px solid var(--agnes-border);
  border-radius: 8px;
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--agnes-bg-hover);
  cursor: pointer;
  transition: border-color 0.2s ease;
}

.image-preview:hover {
  border-color: var(--el-color-primary-light-5);
}

.image-preview img {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
}

.url-input-row {
  display: flex;
  align-items: center;
  gap: 10px;
  max-width: 360px;
}

.url-label {
  color: var(--agnes-text-secondary);
  font-size: 13px;
  white-space: nowrap;
  flex-shrink: 0;
}

/* ---------- 开关字段 ---------- */
.switch-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.form-tip {
  color: var(--agnes-text-muted);
  font-size: 12px;
  line-height: 1.5;
  margin: 0;
}

/* ---------- 预览卡片 ---------- */
.preview-card {
  background: var(--agnes-bg-hover);
  border-radius: 10px;
  overflow: hidden;
}

.preview-header {
  padding: 14px 16px;
  border-bottom: 1px solid var(--agnes-border);
  background: var(--agnes-bg-elevated);
}

.preview-title {
  color: var(--agnes-text-primary);
  font-size: 14px;
  font-weight: 600;
}

.preview-body {
  padding: 20px;
}

.preview-image {
  position: relative;
  width: 100%;
  aspect-ratio: 4 / 3;
  border-radius: 8px;
  overflow: hidden;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
}

.placeholder-bg {
  width: 100%;
  height: 100%;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
}

.placeholder-text {
  color: rgba(255, 255, 255, 0.5);
  font-size: 13px;
}

.watermark-preview {
  position: absolute;
  pointer-events: none;
}

.text-watermark {
  font-weight: 600;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.3);
  white-space: nowrap;
}

.image-watermark img {
  width: 100%;
  height: auto;
  display: block;
}

/* ---------- 操作区 ---------- */
.form-actions {
  display: flex;
  gap: 12px;
  justify-content: flex-end;
  padding-top: 24px;
  margin-top: 28px;
  border-top: 1px solid var(--agnes-border);
}

/* ---------- Element Plus 覆盖 ---------- */
:deep(.el-form-item) {
  margin-bottom: 22px;
}

:deep(.el-form-item:last-child) {
  margin-bottom: 0;
}

:deep(.el-form-item__label) {
  color: var(--agnes-text-secondary);
  font-weight: 500;
}

:deep(.el-input-number) {
  width: 140px;
}

:deep(.el-color-picker) {
  height: 32px;
}

:deep(.el-color-picker__trigger) {
  width: 40px;
  height: 32px;
  padding: 3px;
}
</style>
