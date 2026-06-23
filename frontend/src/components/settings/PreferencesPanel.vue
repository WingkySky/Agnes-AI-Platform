<!-- =====================================================
     偏好设置面板 PreferencesPanel
     - 通过 Pinia store 读取/更新用户偏好
     - 本地表单编辑，点击保存才同步到后端
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
          v-model="form.download.auto_download"
          @change="markDirty"
        />
      </div>

      <!-- 下载目录（开启自动下载后显示） -->
      <div v-if="form.download.auto_download" class="pref-row sub">
        <div class="pref-info">
          <span class="pref-label">{{ t('prefs.download.directory') }}</span>
          <span class="pref-hint">
            <span v-if="prefsStore.hasDirectoryHandle">
              ✓ {{ t('prefs.download.directorySelected') }}: <code>{{ form.download.download_directory }}</code>
            </span>
            <span v-else-if="!form.download.download_directory">
              {{ t('prefs.download.browserDefaultHint') }}
            </span>
            <span v-else>
              {{ t('prefs.download.directorySelected') }}: <code>{{ form.download.download_directory }}</code>
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
      <div v-if="form.download.auto_download && !prefsStore.hasDirectoryHandle" class="pref-tip">
        <el-icon><InfoFilled /></el-icon>
        <span>{{ t('prefs.download.directoryTip') }}</span>
      </div>

      <!-- 分类方式 -->
      <div v-if="form.download.auto_download" class="pref-row sub">
        <div class="pref-info">
          <span class="pref-label">{{ t('prefs.download.classifyBy') }}</span>
          <span class="pref-hint">{{ t('prefs.download.classifyByHint') }}</span>
        </div>
        <el-select
          v-model="form.download.classify_by"
          size="small"
          style="width: 180px"
          @change="markDirty">
          <el-option :label="t('prefs.download.classifyType')" value="type" />
          <el-option :label="t('prefs.download.classifyDate')" value="date" />
          <el-option :label="t('prefs.download.classifyNone')" value="none" />
        </el-select>
      </div>

      <!-- 命名规则：预设方案 -->
      <div v-if="form.download.auto_download" class="pref-row sub">
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
          <el-option :label="t('prefs.download.namingPresetTypeTimestamp')" value="type_timestamp" />
          <el-option :label="t('prefs.download.namingPresetCustom')" value="custom" />
        </el-select>
      </div>

      <!-- 命名规则：自定义构建器（仅 custom 模式显示） -->
      <div v-if="form.download.auto_download && namingPreset === 'custom'" class="naming-custom">
        <!-- 可拖拽的命名块列表 -->
        <div class="naming-builder">
          <transition-group name="token-move" tag="div" class="naming-tokens">
            <div
              v-for="(token, index) in namingTokens"
              :key="token.id"
              class="naming-token"
              :class="{ 'is-dragging': dragIndex === index, 'is-separator': token.type === 'sep' }"
              draggable="true"
              @dragstart="handleDragStart(index, $event)"
              @dragenter.prevent="handleDragEnter(index)"
              @dragover.prevent
              @drop="handleDrop(index)">
              <span class="token-label">{{ token.label }}</span>
              <el-icon class="token-close" @click="removeNamingToken(index)"><Close /></el-icon>
            </div>
            <div v-if="namingTokens.length === 0" key="empty" class="naming-token-empty">
              {{ t('prefs.download.namingEmpty') }}
            </div>
          </transition-group>
        </div>

        <!-- 添加变量 / 分隔符 -->
        <div class="naming-toolbar">
          <el-select
            :model-value="''"
            size="small"
            style="width: 130px"
            :placeholder="t('prefs.download.namingAddVariable')"
            @change="handleAddVariable">
            <el-option
              v-for="tag in namingTags"
              :key="tag.token"
              :label="t(tag.label)"
              :value="tag.token" />
          </el-select>
          <div class="sep-buttons">
            <el-button
              v-for="sep in namingSeparators"
              :key="sep.value"
              size="small"
              @click="addNamingSeparator(sep.value)">
              {{ sep.label }}
            </el-button>
          </div>
          <el-button
            v-if="namingTokens.length > 0"
            size="small"
            text
            type="danger"
            @click="clearNamingPattern">
            {{ t('prefs.download.namingClear') }}
          </el-button>
        </div>

        <!-- 实时预览 -->
        <div class="naming-preview standalone">
          <span class="preview-label">{{ t('prefs.download.namingPreview') }}:</span>
          <code>{{ namingPreview }}</code>
        </div>
        <p class="naming-hint">{{ t('prefs.download.namingCustomHint') }}</p>
      </div>

      <!-- 非自定义模式也显示预览 -->
      <div v-else-if="form.download.auto_download" class="naming-preview standalone">
        <span class="preview-label">{{ t('prefs.download.namingPreview') }}:</span>
        <code>{{ namingPreview }}</code>
      </div>

      <!-- 默认格式 -->
      <div v-if="form.download.auto_download" class="pref-row sub">
        <div class="pref-info">
          <span class="pref-label">{{ t('prefs.download.defaultFormat') }}</span>
          <span class="pref-hint">{{ t('prefs.download.defaultFormatHint') }}</span>
        </div>
        <el-select
          v-model="form.download.default_format"
          size="small"
          style="width: 140px"
          @change="markDirty">
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
          v-model="form.generation.default_aspect_ratio"
          size="small"
          style="width: 140px"
          @change="markDirty">
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
          v-model="form.generation.auto_copy_prompt"
          @change="markDirty"
        />
      </div>

      <!-- 默认生成数量 -->
      <div class="pref-row">
        <div class="pref-info">
          <span class="pref-label">{{ t('prefs.generation.defaultImageCount') }}</span>
          <span class="pref-hint">{{ t('prefs.generation.defaultImageCountHint') }}</span>
        </div>
        <el-input-number
          v-model="form.generation.default_image_count"
          :min="1"
          :max="16"
          size="small"
          @change="markDirty"
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
          v-model="form.ui.theme"
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
          v-model="form.ui.canvas_grid_visible"
          @change="markDirty"
        />
      </div>

      <!-- 吸附到网格 -->
      <div class="pref-row">
        <div class="pref-info">
          <span class="pref-label">{{ t('prefs.ui.canvasSnapToGrid') }}</span>
          <span class="pref-hint">{{ t('prefs.ui.canvasSnapToGridHint') }}</span>
        </div>
        <el-switch
          v-model="form.ui.canvas_snap_to_grid"
          @change="markDirty"
        />
      </div>

      <!-- 网格大小 -->
      <div v-if="form.ui.canvas_grid_visible" class="pref-row sub">
        <div class="pref-info">
          <span class="pref-label">{{ t('prefs.ui.canvasGridSize') }}</span>
          <span class="pref-hint">{{ t('prefs.ui.canvasGridSizeHint') }}</span>
        </div>
        <el-slider
          v-model="form.ui.canvas_grid_size"
          :min="5"
          :max="100"
          :step="5"
          style="width: 180px"
          @change="markDirty"
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
          v-model="form.notification.sound_on_complete"
          @change="markDirty"
        />
      </div>

      <!-- 浏览器通知 -->
      <div class="pref-row">
        <div class="pref-info">
          <span class="pref-label">{{ t('prefs.notification.browserNotification') }}</span>
          <span class="pref-hint">{{ t('prefs.notification.browserNotificationHint') }}</span>
        </div>
        <el-switch
          v-model="form.notification.browser_notification"
          @change="handleBrowserNotificationChange"
        />
      </div>
    </section>

    <!-- ========== 底部：操作按钮 ========== -->
    <div class="pref-footer">
      <el-button size="small" @click="handleReset">
        {{ t('prefs.resetToDefault') }}
      </el-button>
      <el-button
        size="small"
        @click="handleDiscard"
        v-if="dirty">
        {{ t('prefs.discard') }}
      </el-button>
      <el-button
        type="primary"
        size="small"
        :loading="saving"
        :disabled="!dirty"
        @click="handleSave">
        {{ t('prefs.save') }}
      </el-button>
      <span v-if="lastSaved" class="save-time">
        {{ t('prefs.lastSaved') }}: {{ lastSaved }}
      </span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { FolderOpened, InfoFilled, Close } from '@element-plus/icons-vue'
import { useI18n } from '@/i18n'
import { usePreferencesStore } from '@/stores/preferences'

const { t } = useI18n()
const prefsStore = usePreferencesStore()

const lastSaved = ref<string | null>(null)
const dirty = ref(false)
const saving = ref(false)

// ================ 本地表单状态（点击保存才同步到后端） ================

const form = reactive({
  download: {
    auto_download: false,
    download_directory: '',
    file_naming_pattern: '{type}_{timestamp}',
    classify_by: 'type' as 'type' | 'date' | 'none',
    default_format: 'original' as 'original' | 'png' | 'jpg' | 'webp',
  },
  generation: {
    default_model_id: '',
    default_aspect_ratio: '1:1',
    auto_copy_prompt: true,
    default_image_count: 1,
  },
  ui: {
    theme: 'dark' as 'dark' | 'light' | 'system',
    canvas_grid_visible: true,
    canvas_grid_size: 20,
    canvas_snap_to_grid: false,
  },
  notification: {
    sound_on_complete: true,
    browser_notification: false,
  },
})

// ================ 命名规则预设 ================

/** 命名构建器中的单个元素（变量或分隔符） */
interface NamingToken {
  id: string
  type: 'var' | 'sep'
  value: string
  label: string
}

/** 预设方案对应的模板（与后端 DEFAULT_PREFERENCES.download.file_naming_pattern 对应） */
const NAMING_PRESETS: Record<string, string> = {
  type_date: '{type}_{date}',
  date_seq: '{date}_{seq}',
  type_seq: '{type}_{seq}',
  seq: '{seq}',
  type_timestamp: '{type}_{timestamp}',
}

/** 可插入的命名变量标签（与 buildFilePath / namingPreview 支持的 token 对齐） */
const namingTags = [
  { token: '{type}', label: 'prefs.download.namingTagType', hint: 'prefs.download.namingTagTypeHint', type: 'primary' as const },
  { token: '{date}', label: 'prefs.download.namingTagDate', hint: 'prefs.download.namingTagDateHint', type: 'success' as const },
  { token: '{time}', label: 'prefs.download.namingTagTime', hint: 'prefs.download.namingTagTimeHint', type: 'success' as const },
  { token: '{timestamp}', label: 'prefs.download.namingTagTimestamp', hint: 'prefs.download.namingTagTimestampHint', type: 'success' as const },
  { token: '{seq}', label: 'prefs.download.namingTagSeq', hint: 'prefs.download.namingTagSeqHint', type: 'warning' as const },
  { token: '{model}', label: 'prefs.download.namingTagModel', hint: 'prefs.download.namingTagModelHint', type: 'info' as const },
  { token: '{uuid}', label: 'prefs.download.namingTagUuid', hint: 'prefs.download.namingTagUuidHint', type: 'info' as const },
]

/** 常用分隔符 */
const namingSeparators = [
  { value: '_', label: '_' },
  { value: '-', label: '-' },
  { value: '.', label: '.' },
  { value: ' ', label: '空格' },
]

/** 拖拽状态 */
const dragIndex = ref<number>(-1)
let _dragSourceIndex = -1

/** 命名 token 列表（本地 ref，操作时直接修改，保证拖拽 key 稳定） */
const namingTokens = ref<NamingToken[]>([])

/** 当前选中的预设方案（根据 file_naming_pattern 反推） */
const namingPreset = computed<string>(() => {
  const pattern = form.download.file_naming_pattern
  for (const [key, val] of Object.entries(NAMING_PRESETS)) {
    if (pattern === val) return key
  }
  return 'custom'
})

/** 命名预览（用示例数据渲染模板） */
const namingPreview = computed<string>(() => {
  const pattern = form.download.file_naming_pattern || '{type}_{date}'
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

// ================ 表单同步 ================

/** 从 pattern 字符串解析为 token 列表 */
function parseNamingTokens(pattern: string): NamingToken[] {
  const tokens: NamingToken[] = []
  let id = 0
  let i = 0
  while (i < pattern.length) {
    if (pattern[i] === '{') {
      const close = pattern.indexOf('}', i)
      if (close !== -1) {
        const token = pattern.slice(i, close + 1)
        const tag = namingTags.find((t) => t.token === token)
        if (tag) {
          tokens.push({ id: `t-${id++}`, type: 'var', value: token, label: t(tag.label) })
          i = close + 1
          continue
        }
      }
    }
    tokens.push({ id: `s-${id++}`, type: 'sep', value: pattern[i], label: pattern[i] === ' ' ? '空格' : pattern[i] })
    i++
  }
  return tokens
}

/** 把 token 列表序列化为 pattern 字符串并写入 form */
function syncNamingPattern() {
  form.download.file_naming_pattern = namingTokens.value.map((token) => token.value).join('')
}

/** 从 store 同步到本地表单（store 变化时自动调用） */
function syncFormFromStore() {
  const d = prefsStore.download
  form.download.auto_download = d.auto_download
  form.download.download_directory = d.download_directory
  form.download.file_naming_pattern = d.file_naming_pattern
  form.download.classify_by = d.classify_by
  form.download.default_format = d.default_format

  const g = prefsStore.generation
  form.generation.default_model_id = g.default_model_id
  form.generation.default_aspect_ratio = g.default_aspect_ratio
  form.generation.auto_copy_prompt = g.auto_copy_prompt
  form.generation.default_image_count = g.default_image_count

  const u = prefsStore.ui
  form.ui.theme = u.theme
  form.ui.canvas_grid_visible = u.canvas_grid_visible
  form.ui.canvas_grid_size = u.canvas_grid_size
  form.ui.canvas_snap_to_grid = u.canvas_snap_to_grid

  const n = prefsStore.notification
  form.notification.sound_on_complete = n.sound_on_complete
  form.notification.browser_notification = n.browser_notification

  namingTokens.value = parseNamingTokens(form.download.file_naming_pattern || '')
  dirty.value = false
}

/** 监听 store 变化，自动同步到本地表单 */
watch(() => prefsStore.data, () => {
  syncFormFromStore()
}, { deep: true })

/** 标记表单为已修改 */
function markDirty() {
  dirty.value = true
}

onMounted(async () => {
  if (!prefsStore.initialized) {
    await prefsStore.fetchPreferences()
  }
  syncFormFromStore()
  if (prefsStore.data?.updated_at) {
    lastSaved.value = new Date(prefsStore.data.updated_at).toLocaleString()
  }
})

// ================ 保存 / 重置 / 丢弃 ================

/** 保存所有偏好到后端 */
async function handleSave() {
  saving.value = true
  try {
    await prefsStore.updatePreferences({
      download: { ...form.download },
      generation: { ...form.generation },
      ui: { ...form.ui },
      notification: { ...form.notification },
    })
    dirty.value = false
    lastSaved.value = new Date().toLocaleString()
    ElMessage.success({ message: t('prefs.saveSuccess'), duration: 1500 })
  } catch {
    ElMessage.error(t('prefs.saveFailed'))
  } finally {
    saving.value = false
  }
}

/** 丢弃未保存的改动，恢复到 store 中的值 */
function handleDiscard() {
  syncFormFromStore()
}

/** 重置为默认 */
async function handleReset() {
  try {
    await ElMessageBox.confirm(t('prefs.resetConfirm'), t('prefs.resetToDefault'), { type: 'warning' })
    await prefsStore.resetToDefault()
    // watch store 会自动同步 form
    lastSaved.value = null
  } catch {
    // 用户取消
  }
}

// ================ 下载目录（File System Access API，需即时授权） ================

/** 选择下载目录 */
async function handlePickDirectory() {
  const result = await prefsStore.pickDirectory()
  if (result === 'ok') {
    form.download.download_directory = prefsStore.download.download_directory
    markDirty()
    ElMessage.success(t('prefs.download.directorySelected') + ': ' + form.download.download_directory)
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

/** 切换回浏览器默认下载（仅清除本地 handle，数据点击保存才同步） */
function handleUseBrowserDefault() {
  prefsStore.clearDirectoryHandle()
  form.download.download_directory = ''
  markDirty()
  ElMessage.success(t('prefs.download.useBrowserDefault'))
}

// ================ 命名构建器操作（仅修改本地状态） ================

/** 命名预设切换
 * - 切到预设方案：写入对应模板
 * - 切到 custom：保留当前模板，不做强制覆盖
 */
function handleNamingPresetChange(preset: string) {
  if (preset === 'custom') {
    return
  }
  const pattern = NAMING_PRESETS[preset]
  if (pattern) {
    form.download.file_naming_pattern = pattern
    namingTokens.value = parseNamingTokens(pattern)
    markDirty()
  }
}

/** 开始拖拽 token */
function handleDragStart(index: number, event: DragEvent) {
  _dragSourceIndex = index
  dragIndex.value = index
  if (event.dataTransfer) {
    event.dataTransfer.effectAllowed = 'move'
    event.dataTransfer.setData('text/plain', String(index))
  }
}

/** 拖拽经过某个 token（仅用于视觉反馈） */
function handleDragEnter(index: number) {
  dragIndex.value = index
}

/** 放置 token，完成排序 */
function handleDrop(index: number) {
  const source = _dragSourceIndex
  dragIndex.value = -1
  _dragSourceIndex = -1
  if (source === -1 || source === index) return
  const tokens = [...namingTokens.value]
  const [moved] = tokens.splice(source, 1)
  tokens.splice(index, 0, moved)
  namingTokens.value = tokens
  syncNamingPattern()
  markDirty()
}

/** 添加变量到末尾 */
function handleAddVariable(token: string) {
  if (!token) return
  const tag = namingTags.find((t) => t.token === token)
  if (!tag) return
  namingTokens.value.push({ id: `t-${Date.now()}`, type: 'var', value: token, label: t(tag.label) })
  syncNamingPattern()
  markDirty()
}

/** 添加分隔符到末尾 */
function addNamingSeparator(sep: string) {
  namingTokens.value.push({ id: `s-${Date.now()}`, type: 'sep', value: sep, label: sep === ' ' ? '空格' : sep })
  syncNamingPattern()
  markDirty()
}

/** 删除指定 token */
function removeNamingToken(index: number) {
  namingTokens.value.splice(index, 1)
  syncNamingPattern()
  markDirty()
}

/** 清空自定义命名模板 */
function clearNamingPattern() {
  namingTokens.value = []
  form.download.file_naming_pattern = ''
  markDirty()
}

// ================ 主题 & 通知（视觉/权限即时处理，数据延迟保存） ================

/** 主题变更（视觉立即应用，数据点击保存才同步） */
function handleThemeChange(theme: 'dark' | 'light' | 'system') {
  applyTheme(theme)
  markDirty()
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

/** 浏览器通知权限请求（权限即时处理，数据点击保存才同步） */
async function handleBrowserNotificationChange(enabled: boolean) {
  if (enabled && 'Notification' in window && Notification.permission === 'default') {
    const perm = await Notification.requestPermission()
    if (perm !== 'granted') {
      form.notification.browser_notification = false
      ElMessage.warning(t('prefs.notification.notificationDenied'))
      return
    }
  }
  markDirty()
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

/* 可拖拽命名构建器 */
.naming-builder {
  min-height: 40px;
  padding: 8px 10px;
  background: var(--agnes-bg-hover);
  border: 1px dashed var(--agnes-border-faint);
  border-radius: 8px;
}

.naming-tokens {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  min-height: 24px;
}

.naming-token {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 8px;
  background: var(--agnes-bg-input);
  border: 1px solid var(--agnes-border-faint);
  border-radius: 6px;
  font-size: 13px;
  color: var(--agnes-text-primary);
  cursor: grab;
  user-select: none;
  transition: transform 0.15s, box-shadow 0.15s, opacity 0.15s;
}

.naming-token:active {
  cursor: grabbing;
}

.naming-token.is-dragging {
  opacity: 0.6;
  transform: scale(1.05);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
}

.naming-token.is-separator {
  padding: 4px 6px;
  color: var(--agnes-text-muted);
  background: transparent;
  border-style: dashed;
}

.naming-token .token-close {
  width: 14px;
  height: 14px;
  font-size: 12px;
  color: var(--agnes-text-muted);
  cursor: pointer;
  border-radius: 50%;
  transition: all 0.2s;
}

.naming-token .token-close:hover {
  color: var(--agnes-danger);
  background: rgba(245, 108, 108, 0.12);
}

.naming-token-empty {
  font-size: 13px;
  color: var(--agnes-text-muted);
  padding: 4px 0;
}

/* token 排序动画 */
.token-move-move {
  transition: transform 0.2s;
}

/* 构建器工具栏 */
.naming-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-top: 10px;
}

.naming-toolbar .sep-buttons {
  display: flex;
  gap: 6px;
}

.naming-toolbar .sep-buttons .el-button {
  padding: 4px 10px;
  min-height: 24px;
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
  gap: 12px;
  margin-top: 8px;
}

.save-time {
  font-size: 12px;
  color: var(--agnes-text-muted);
}
</style>
