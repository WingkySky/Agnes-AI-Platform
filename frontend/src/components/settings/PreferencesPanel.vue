<!-- =====================================================
     偏好设置面板 PreferencesPanel
     - 通过 Pinia store 读取/更新用户偏好（自动与后端同步）
     - 分为四个 Tab：生成 / 下载 / 界面 / 通知
     - 支持自动下载目录选择（File System Access API）
     ===================================================== -->

<template>
  <div class="preferences-panel">

    <!-- ========== 下载偏好（最受关注，放在最前面） ========== -->
    <section class="pref-section">
      <div class="section-header">
        <div>
          <h3 class="section-title">{{ t('prefs.download.title') }}</h3>
          <p class="section-desc">{{ t('prefs.download.desc') }}</p>
        </div>
      </div>

      <!-- 自动下载开关 -->
      <div class="pref-row">
        <div class="pref-info">
          <span class="pref-label">{{ t('prefs.download.autoDownload') }}</span>
          <span class="pref-hint">{{ t('prefs.download.autoDownloadHint') }}</span>
        </div>
        <el-switch
          :model-value="prefsStore.download.auto_download"
          @change="save({ download: { auto_download: $event } })"
        />
      </div>

      <!-- 下载目录（开启自动下载后显示） -->
      <div v-if="prefsStore.download.auto_download" class="pref-row sub">
        <div class="pref-info">
          <span class="pref-label">{{ t('prefs.download.directory') }}</span>
          <span class="pref-hint">
            <span v-if="prefsStore.hasDirectoryHandle">
              ✓ {{ t('prefs.download.directorySelected') }}: <code>{{ prefsStore.download.download_directory }}</code>
            </span>
            <span v-else-if="!prefsStore.download.download_directory">
              {{ t('prefs.download.browserDefaultHint') }}
            </span>
            <span v-else>
              {{ t('prefs.download.directorySelected') }}: <code>{{ prefsStore.download.download_directory }}</code>
            </span>
          </span>
        </div>
        <div class="pref-actions">
          <el-button
            size="small"
            :type="prefsStore.hasDirectoryHandle ? 'success' : 'primary'"
            @click="handlePickDirectory">
            <el-icon><FolderOpened /></el-icon>
            {{ prefsStore.hasDirectoryHandle ? t('prefs.download.changeDirectory') : t('prefs.download.selectDirectory') }}
          </el-button>
          <el-button
            v-if="prefsStore.hasDirectoryHandle"
            size="small"
            @click="handleUseBrowserDefault">
            {{ t('prefs.download.useBrowserDefault') }}
          </el-button>
        </div>
      </div>

      <!-- 目录选择提示 -->
      <div v-if="prefsStore.download.auto_download && !prefsStore.hasDirectoryHandle" class="pref-tip">
        <el-icon><InfoFilled /></el-icon>
        <span>{{ t('prefs.download.directoryTip') }}</span>
      </div>

      <!-- 分类方式 -->
      <div v-if="prefsStore.download.auto_download" class="pref-row sub">
        <div class="pref-info">
          <span class="pref-label">{{ t('prefs.download.classifyBy') }}</span>
          <span class="pref-hint">{{ t('prefs.download.classifyByHint') }}</span>
        </div>
        <el-select
          :model-value="prefsStore.download.classify_by"
          size="small"
          style="width: 180px"
          @change="save({ download: { classify_by: $event } })">
          <el-option :label="t('prefs.download.classifyType')" value="type" />
          <el-option :label="t('prefs.download.classifyDate')" value="date" />
          <el-option :label="t('prefs.download.classifyNone')" value="none" />
        </el-select>
      </div>

      <!-- 命名规则：预设方案 -->
      <div v-if="prefsStore.download.auto_download" class="pref-row sub">
        <div class="pref-info">
          <span class="pref-label">{{ t('prefs.download.namingPattern') }}</span>
          <span class="pref-hint">{{ t('prefs.download.namingPatternHint') }}</span>
        </div>
        <el-select
          :model-value="namingPreset"
          size="small"
          style="width: 160px"
          @change="handleNamingPresetChange">
          <el-option :label="t('prefs.download.namingPresetTypeDate')" value="type_date" />
          <el-option :label="t('prefs.download.namingPresetDateSeq')" value="date_seq" />
          <el-option :label="t('prefs.download.namingPresetTypeSeq')" value="type_seq" />
          <el-option :label="t('prefs.download.namingPresetSeq')" value="seq" />
          <el-option :label="t('prefs.download.namingPresetCustom')" value="custom" />
        </el-select>
      </div>

      <!-- 命名规则：自定义标签（仅 custom 模式显示） -->
      <div v-if="prefsStore.download.auto_download && namingPreset === 'custom'" class="naming-custom">
        <div class="naming-tags">
          <el-tag
            v-for="tag in namingTags"
            :key="tag.token"
            class="naming-tag"
            :type="tag.type"
            effect="plain"
            @click="insertNamingTag(tag.token)">
            {{ t(tag.label) }}
            <span class="tag-hint">{{ t(tag.hint) }}</span>
          </el-tag>
        </div>
        <el-input
          v-model="customNamingPattern"
          size="small"
          style="margin-top: 8px"
          :placeholder="t('prefs.download.namingPlaceholder')"
          @change="handleNamingPatternChange">
          <template #append>
            <span class="preview-label">{{ t('prefs.download.namingPreview') }}:</span>
          </template>
        </el-input>
        <p class="naming-hint">{{ t('prefs.download.namingCustomHint') }}</p>
      </div>

      <!-- 非自定义模式也显示预览 -->
      <div v-else-if="prefsStore.download.auto_download" class="naming-preview standalone">
        <span class="preview-label">{{ t('prefs.download.namingPreview') }}:</span>
        <code>{{ namingPreview }}</code>
      </div>

      <!-- 默认格式 -->
      <div v-if="prefsStore.download.auto_download" class="pref-row sub">
        <div class="pref-info">
          <span class="pref-label">{{ t('prefs.download.defaultFormat') }}</span>
          <span class="pref-hint">{{ t('prefs.download.defaultFormatHint') }}</span>
        </div>
        <el-select
          :model-value="prefsStore.download.default_format"
          size="small"
          style="width: 140px"
          @change="save({ download: { default_format: $event } })">
          <el-option :label="t('prefs.download.formatOriginal')" value="original" />
          <el-option label="PNG" value="png" />
          <el-option label="JPG" value="jpg" />
          <el-option label="WebP" value="webp" />
        </el-select>
      </div>
    </section>

    <!-- ========== 生成偏好 ========== -->
    <section class="pref-section">
      <div class="section-header">
        <div>
          <h3 class="section-title">{{ t('prefs.generation.title') }}</h3>
          <p class="section-desc">{{ t('prefs.generation.desc') }}</p>
        </div>
      </div>

      <!-- 默认比例 -->
      <div class="pref-row">
        <div class="pref-info">
          <span class="pref-label">{{ t('prefs.generation.defaultAspectRatio') }}</span>
          <span class="pref-hint">{{ t('prefs.generation.defaultAspectRatioHint') }}</span>
        </div>
        <el-select
          :model-value="prefsStore.generation.default_aspect_ratio"
          size="small"
          style="width: 140px"
          @change="save({ generation: { default_aspect_ratio: $event } })">
          <el-option label="1:1（正方形）" value="1:1" />
          <el-option label="4:3" value="4:3" />
          <el-option label="3:2" value="3:2" />
          <el-option label="16:9（横版）" value="16:9" />
          <el-option label="9:16（竖版）" value="9:16" />
          <el-option label="3:4（竖版）" value="3:4" />
          <el-option label="2:3（竖版）" value="2:3" />
        </el-select>
      </div>

      <!-- 自动复制提示词 -->
      <div class="pref-row">
        <div class="pref-info">
          <span class="pref-label">{{ t('prefs.generation.autoCopyPrompt') }}</span>
          <span class="pref-hint">{{ t('prefs.generation.autoCopyPromptHint') }}</span>
        </div>
        <el-switch
          :model-value="prefsStore.generation.auto_copy_prompt"
          @change="save({ generation: { auto_copy_prompt: $event } })"
        />
      </div>

      <!-- 默认生成数量 -->
      <div class="pref-row">
        <div class="pref-info">
          <span class="pref-label">{{ t('prefs.generation.defaultImageCount') }}</span>
          <span class="pref-hint">{{ t('prefs.generation.defaultImageCountHint') }}</span>
        </div>
        <el-input-number
          :model-value="prefsStore.generation.default_image_count"
          :min="1"
          :max="16"
          size="small"
          @change="save({ generation: { default_image_count: $event } })"
        />
      </div>
    </section>

    <!-- ========== 界面偏好 ========== -->
    <section class="pref-section">
      <div class="section-header">
        <div>
          <h3 class="section-title">{{ t('prefs.ui.title') }}</h3>
          <p class="section-desc">{{ t('prefs.ui.desc') }}</p>
        </div>
      </div>

      <!-- 主题 -->
      <div class="pref-row">
        <div class="pref-info">
          <span class="pref-label">{{ t('prefs.ui.theme') }}</span>
          <span class="pref-hint">{{ t('prefs.ui.themeHint') }}</span>
        </div>
        <el-select
          :model-value="prefsStore.ui.theme"
          size="small"
          style="width: 140px"
          @change="handleThemeChange">
          <el-option :label="t('prefs.ui.themeDark')" value="dark" />
          <el-option :label="t('prefs.ui.themeLight')" value="light" />
          <el-option :label="t('prefs.ui.themeSystem')" value="system" />
        </el-select>
      </div>

      <!-- 画布网格可见 -->
      <div class="pref-row">
        <div class="pref-info">
          <span class="pref-label">{{ t('prefs.ui.canvasGridVisible') }}</span>
          <span class="pref-hint">{{ t('prefs.ui.canvasGridVisibleHint') }}</span>
        </div>
        <el-switch
          :model-value="prefsStore.ui.canvas_grid_visible"
          @change="save({ ui: { canvas_grid_visible: $event } })"
        />
      </div>

      <!-- 吸附到网格 -->
      <div class="pref-row">
        <div class="pref-info">
          <span class="pref-label">{{ t('prefs.ui.canvasSnapToGrid') }}</span>
          <span class="pref-hint">{{ t('prefs.ui.canvasSnapToGridHint') }}</span>
        </div>
        <el-switch
          :model-value="prefsStore.ui.canvas_snap_to_grid"
          @change="save({ ui: { canvas_snap_to_grid: $event } })"
        />
      </div>

      <!-- 网格大小 -->
      <div v-if="prefsStore.ui.canvas_grid_visible" class="pref-row sub">
        <div class="pref-info">
          <span class="pref-label">{{ t('prefs.ui.canvasGridSize') }}</span>
          <span class="pref-hint">{{ t('prefs.ui.canvasGridSizeHint') }}</span>
        </div>
        <el-slider
          :model-value="prefsStore.ui.canvas_grid_size"
          :min="5"
          :max="100"
          :step="5"
          style="width: 180px"
          @change="save({ ui: { canvas_grid_size: $event } })"
        />
      </div>
    </section>

    <!-- ========== 通知偏好 ========== -->
    <section class="pref-section">
      <div class="section-header">
        <div>
          <h3 class="section-title">{{ t('prefs.notification.title') }}</h3>
          <p class="section-desc">{{ t('prefs.notification.desc') }}</p>
        </div>
      </div>

      <!-- 完成提示音 -->
      <div class="pref-row">
        <div class="pref-info">
          <span class="pref-label">{{ t('prefs.notification.soundOnComplete') }}</span>
          <span class="pref-hint">{{ t('prefs.notification.soundOnCompleteHint') }}</span>
        </div>
        <el-switch
          :model-value="prefsStore.notification.sound_on_complete"
          @change="save({ notification: { sound_on_complete: $event } })"
        />
      </div>

      <!-- 浏览器通知 -->
      <div class="pref-row">
        <div class="pref-info">
          <span class="pref-label">{{ t('prefs.notification.browserNotification') }}</span>
          <span class="pref-hint">{{ t('prefs.notification.browserNotificationHint') }}</span>
        </div>
        <el-switch
          :model-value="prefsStore.notification.browser_notification"
          @change="handleBrowserNotificationChange"
        />
      </div>
    </section>

    <!-- ========== 底部：重置按钮 ========== -->
    <div class="pref-footer">
      <el-button size="small" @click="handleReset">
        {{ t('prefs.resetToDefault') }}
      </el-button>
      <span v-if="lastSaved" class="save-time">
        {{ t('prefs.lastSaved') }}: {{ lastSaved }}
      </span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { FolderOpened, InfoFilled } from '@element-plus/icons-vue'
import { useI18n } from '@/i18n'
import { usePreferencesStore } from '@/stores/preferences'
import type { UserPreferencesUpdate } from '@/types'

const { t } = useI18n()
const prefsStore = usePreferencesStore()

const lastSaved = ref<string | null>(null)
const customNamingPattern = ref(prefsStore.download.file_naming_pattern)

// 同步 customNamingPattern 与 store 中的值（切换预设或外部更新时自动同步）
watch(() => prefsStore.download.file_naming_pattern, (val) => {
  if (val && val !== customNamingPattern.value) {
    customNamingPattern.value = val
  }
})

// ================ 命名规则预设 ================

/** 预设方案对应的模板 */
const NAMING_PRESETS: Record<string, string> = {
  type_date: '{type}_{date}',
  date_seq: '{date}_{seq}',
  type_seq: '{type}_{seq}',
  seq: '{seq}',
}

/** 可点击插入的命名标签 */
const namingTags = [
  { token: '{type}', label: 'prefs.download.namingTagType', hint: 'prefs.download.namingTagTypeHint', type: 'primary' as const },
  { token: '{date}', label: 'prefs.download.namingTagDate', hint: 'prefs.download.namingTagDateHint', type: 'success' as const },
  { token: '{time}', label: 'prefs.download.namingTagTime', hint: 'prefs.download.namingTagTimeHint', type: 'success' as const },
  { token: '{seq}', label: 'prefs.download.namingTagSeq', hint: 'prefs.download.namingTagSeqHint', type: 'warning' as const },
  { token: '{model}', label: 'prefs.download.namingTagModel', hint: 'prefs.download.namingTagModelHint', type: 'info' as const },
]

/** 当前选中的预设方案（根据 file_naming_pattern 反推） */
const namingPreset = computed<string>(() => {
  const pattern = prefsStore.download.file_naming_pattern
  for (const [key, val] of Object.entries(NAMING_PRESETS)) {
    if (pattern === val) return key
  }
  return 'custom'
})

/** 命名预览（用示例数据渲染模板） */
const namingPreview = computed<string>(() => {
  const pattern = prefsStore.download.file_naming_pattern || '{type}_{date}'
  return pattern
    .replace('{type}', 'image')
    .replace('{date}', '2024-01-15')
    .replace('{time}', '143052')
    .replace('{seq}', 'a1b2c3d4')
    .replace('{model}', 'flux')
    .replace('{timestamp}', '2024-01-15T14-30-52')
    .replace('{uuid}', 'a1b2c3d4')
    + '.png'
})

onMounted(async () => {
  if (!prefsStore.initialized) {
    await prefsStore.fetchPreferences()
  }
  if (prefsStore.data?.updated_at) {
    lastSaved.value = new Date(prefsStore.data.updated_at).toLocaleString()
  }
})

/** 保存偏好（部分更新，自动与后端同步）*/
async function save(patch: UserPreferencesUpdate) {
  try {
    await prefsStore.updatePreferences(patch)
    lastSaved.value = new Date().toLocaleString()
    ElMessage.success({ message: t('prefs.saveSuccess'), duration: 1500 })
  } catch {
    ElMessage.error(t('prefs.saveFailed'))
  }
}

/** 选择下载目录（File System Access API）*/
async function handlePickDirectory() {
  const result = await prefsStore.pickDirectory()
  if (result === 'ok') {
    ElMessage.success(t('prefs.download.directorySelected') + ': ' + prefsStore.download.download_directory)
  } else if (result === 'security') {
    ElMessage.warning(t('prefs.download.directorySecurityError'))
  } else if (result === 'unsupported') {
    ElMessage.info(t('prefs.download.directoryUnsupported'))
  } else if (result === 'abort') {
    // 用户取消，不提示
  } else {
    ElMessage.error(t('prefs.download.directoryUnknownError'))
  }
}

/** 切换回浏览器默认下载 */
async function handleUseBrowserDefault() {
  await prefsStore.useBrowserDefaultDownload()
  ElMessage.success(t('prefs.download.useBrowserDefault'))
}

/** 命名预设切换 */
async function handleNamingPresetChange(preset: string) {
  if (preset === 'custom') {
    // 切到自定义时保留当前模板
    return
  }
  const pattern = NAMING_PRESETS[preset]
  if (pattern) {
    await save({ download: { file_naming_pattern: pattern } })
  }
}

/** 点击标签插入到命名模板 */
async function insertNamingTag(token: string) {
  const current = prefsStore.download.file_naming_pattern || ''
  const newPattern = current + token
  customNamingPattern.value = newPattern
  await save({ download: { file_naming_pattern: newPattern } })
}

/** 自定义命名模板变更 */
async function handleNamingPatternChange() {
  await save({ download: { file_naming_pattern: customNamingPattern.value } })
}

/** 主题变更（需要同步更新 HTML class）*/
async function handleThemeChange(theme: 'dark' | 'light' | 'system') {
  await save({ ui: { theme } })
  applyTheme(theme)
}

function applyTheme(theme: 'dark' | 'light' | 'system') {
  const root = document.documentElement
  if (theme === 'system') {
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches
    root.setAttribute('data-theme', prefersDark ? 'dark' : 'light')
  } else {
    root.setAttribute('data-theme', theme)
  }
}

/** 浏览器通知权限请求 */
async function handleBrowserNotificationChange(enabled: boolean) {
  if (enabled && 'Notification' in window && Notification.permission === 'default') {
    const perm = await Notification.requestPermission()
    if (perm !== 'granted') {
      ElMessage.warning(t('prefs.notification.notificationDenied'))
      return
    }
  }
  await save({ notification: { browser_notification: enabled } })
}

/** 重置为默认 */
async function handleReset() {
  try {
    await ElMessageBox.confirm(t('prefs.resetConfirm'), t('prefs.resetToDefault'), { type: 'warning' })
    await prefsStore.resetToDefault()
    lastSaved.value = null
  } catch {
    // 用户取消
  }
}
</script>

<style scoped>
.preferences-panel {
  max-width: 760px;
}

.pref-section {
  background: var(--agnes-bg-input);
  border: 1px solid var(--agnes-border-faint);
  border-radius: 12px;
  padding: 20px 24px;
  margin-bottom: 20px;
}

.section-header {
  margin-bottom: 16px;
}

.section-title {
  margin: 0 0 4px;
  font-size: 16px;
  font-weight: 600;
  color: var(--agnes-text-primary);
}

.section-desc {
  margin: 0;
  font-size: 13px;
  color: var(--agnes-text-muted);
}

/* 单行偏好项 */
.pref-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: 12px 0;
  border-bottom: 1px solid var(--agnes-border-faint);
}

.pref-row:last-child {
  border-bottom: none;
  padding-bottom: 0;
}

.pref-row.sub {
  padding-left: 16px;
  font-size: 13px;
}

.pref-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
  flex: 1;
}

.pref-label {
  font-size: 14px;
  color: var(--agnes-text-primary);
  font-weight: 500;
}

.pref-hint {
  font-size: 12px;
  color: var(--agnes-text-muted);
  line-height: 1.5;
}

code.tag {
  background: var(--agnes-bg-hover);
  border-radius: 3px;
  padding: 0 4px;
  margin-right: 4px;
  font-size: 11px;
  color: var(--agnes-primary-color);
}

/* 操作按钮组 */
.pref-actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}

/* 目录选择提示 */
.pref-tip {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  padding: 8px 12px;
  margin: 4px 0 8px 16px;
  background: var(--agnes-bg-hover);
  border-radius: 8px;
  font-size: 12px;
  color: var(--agnes-text-muted);
  line-height: 1.5;
}

.pref-tip .el-icon {
  margin-top: 2px;
  flex-shrink: 0;
  color: var(--agnes-warning);
}

/* 命名规则自定义区域 */
.naming-custom {
  padding: 12px 0 8px 16px;
}

.naming-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.naming-tag {
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  transition: all 0.2s;
}

.naming-tag:hover {
  transform: translateY(-1px);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
}

.naming-tag .tag-hint {
  font-size: 10px;
  opacity: 0.6;
  font-weight: normal;
}

.naming-preview {
  margin-top: 8px;
  padding: 6px 10px;
  background: var(--agnes-bg-hover);
  border-radius: 6px;
  font-size: 12px;
}

.naming-preview code {
  color: var(--agnes-primary-color);
  font-size: 12px;
}

.naming-preview.standalone {
  margin: 4px 0 8px 16px;
}

.naming-preview .preview-label {
  color: var(--agnes-text-muted);
  margin-right: 6px;
}

.naming-hint {
  margin: 6px 0 0;
  font-size: 11px;
  color: var(--agnes-text-muted);
}

.preview-label {
  font-size: 12px;
  color: var(--agnes-text-muted);
}

/* 底部 */
.pref-footer {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-top: 8px;
}

.save-time {
  font-size: 12px;
  color: var(--agnes-text-muted);
}
</style>
