<!--
  SubtitleEditor —— 字幕编辑器组件
  - 表格形式展示字幕条目（序号 / 场景 / 开始 / 结束 / 文本 / 操作）
  - 支持编辑文本、调整起止时间
  - 支持新增 / 删除条目
  - 保存：调用后端 POST /runs/{runId}/subtitles 重新生成 SRT 文件
  - 导出：本地拼接 SRT 格式下载
  - 重置：恢复到初始字幕
  - 时间校验：end > start，文本非空
-->
<template>
  <div class="subtitle-editor">
    <!-- 标题 + 操作按钮 -->
    <div class="editor-header">
      <div class="header-left">
        <span class="editor-title">{{ t('subtitleEditor.title') }}</span>
        <span class="editor-desc">{{ t('subtitleEditor.description') }}</span>
      </div>
      <div class="header-actions">
        <el-button size="small" @click="handleAdd" :icon="Plus">
          {{ t('subtitleEditor.add') }}
        </el-button>
        <el-button size="small" @click="handleExport" :icon="Download">
          {{ t('subtitleEditor.export') }}
        </el-button>
        <el-button size="small" @click="handleReset" :icon="RefreshLeft">
          {{ t('subtitleEditor.reset') }}
        </el-button>
        <el-button
          size="small"
          type="primary"
          :loading="saving"
          :disabled="!hasChange"
          @click="handleSave"
        >
          <el-icon v-if="!saving"><Check /></el-icon>
          {{ saving ? t('subtitleEditor.saving') : t('subtitleEditor.save') }}
        </el-button>
      </div>
    </div>

    <!-- 空状态 -->
    <el-empty
      v-if="!subtitles.length"
      :description="t('subtitleEditor.noSubtitles')"
      :image-size="60"
    />

    <!-- 字幕表格 -->
    <el-table v-else :data="subtitles" border size="small" class="subtitle-table">
      <!-- 序号 -->
      <el-table-column :label="t('subtitleEditor.indexCol')" width="60" align="center">
        <template #default="{ $index }">
          {{ $index + 1 }}
        </template>
      </el-table-column>

      <!-- 场景 -->
      <el-table-column :label="t('subtitleEditor.sceneCol')" width="70" align="center">
        <template #default="{ row }">
          {{ row.scene_index ?? '-' }}
        </template>
      </el-table-column>

      <!-- 开始时间 -->
      <el-table-column :label="t('subtitleEditor.startCol')" width="110">
        <template #default="{ row, $index }">
          <el-input-number
            v-model="row.start"
            :min="0"
            :step="0.1"
            :precision="2"
            size="small"
            controls-position="right"
            style="width: 100%"
            @change="markChanged"
          />
        </template>
      </el-table-column>

      <!-- 结束时间 -->
      <el-table-column :label="t('subtitleEditor.endCol')" width="110">
        <template #default="{ row }">
          <el-input-number
            v-model="row.end"
            :min="0"
            :step="0.1"
            :precision="2"
            size="small"
            controls-position="right"
            style="width: 100%"
            @change="markChanged"
          />
        </template>
      </el-table-column>

      <!-- 字幕文本 -->
      <el-table-column :label="t('subtitleEditor.textCol')" min-width="280">
        <template #default="{ row }">
          <el-input
            v-model="row.text"
            type="textarea"
            :rows="1"
            resize="vertical"
            size="small"
            @input="markChanged"
          />
        </template>
      </el-table-column>

      <!-- 操作 -->
      <el-table-column :label="t('subtitleEditor.actionsCol')" width="80" align="center">
        <template #default="{ $index }">
          <el-button
            size="small"
            type="danger"
            :icon="Delete"
            circle
            @click="handleDelete($index)"
          />
        </template>
      </el-table-column>
    </el-table>

    <!-- 字幕样式配置（折叠面板，默认折叠） -->
    <el-collapse v-model="styleCollapse" class="style-collapse">
      <el-collapse-item :title="t('subtitleEditor.styleSettings')" name="style">
        <el-form label-width="100px" size="small">
          <el-form-item :label="t('subtitleEditor.fontSize')">
            <el-input-number
              v-model="subtitleStyle.font_size"
              :min="12"
              :max="120"
              :step="2"
            />
          </el-form-item>
          <el-form-item :label="t('subtitleEditor.fontColor')">
            <el-color-picker v-model="subtitleStyle.font_color" show-alpha />
          </el-form-item>
          <el-form-item :label="t('subtitleEditor.boxColor')">
            <el-color-picker v-model="subtitleStyle.box_color" show-alpha />
          </el-form-item>
          <el-form-item :label="t('subtitleEditor.boxOpacity')">
            <el-slider
              v-model="subtitleStyle.box_opacity"
              :min="0"
              :max="1"
              :step="0.1"
              show-input
            />
          </el-form-item>
          <el-form-item :label="t('subtitleEditor.position')">
            <el-radio-group v-model="subtitleStyle.position">
              <el-radio-button value="top">{{ t('subtitleEditor.positionTop') }}</el-radio-button>
              <el-radio-button value="center">{{ t('subtitleEditor.positionCenter') }}</el-radio-button>
              <el-radio-button value="bottom">{{ t('subtitleEditor.positionBottom') }}</el-radio-button>
            </el-radio-group>
          </el-form-item>
          <el-form-item :label="t('subtitleEditor.margin')">
            <el-input-number
              v-model="subtitleStyle.margin"
              :min="0"
              :max="500"
              :step="10"
            />
          </el-form-item>
        </el-form>
      </el-collapse-item>
    </el-collapse>

    <!-- 底部操作区：保存并重新烧录 -->
    <div class="editor-actions">
      <el-button
        @click="handleSaveAndRecompose"
        :loading="recomposing"
        :disabled="recomposing || saving"
        type="success"
        size="small"
      >
        {{ recomposing ? t('subtitleEditor.recomposing') : t('subtitleEditor.saveAndRecompose') }}
      </el-button>
    </div>
    <p v-if="recomposing" class="recompose-tip">
      {{ t('subtitleEditor.recomposeTip') }}
    </p>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { ElMessage, ElMessageBox, ElEmpty, ElTable, ElTableColumn, ElInput, ElInputNumber, ElButton, ElIcon, ElCollapse, ElCollapseItem, ElColorPicker, ElSlider, ElRadioGroup, ElRadioButton, ElForm, ElFormItem } from 'element-plus'
import { Plus, Delete, Download, RefreshLeft, Check } from '@element-plus/icons-vue'
import { useI18n } from '@/i18n'
import { saveRunSubtitles, recomposeVideo, type SubtitleEntry, type SubtitleStyle } from '@/api/pipeline'

const props = defineProps<{
  /** 关联的流水线运行 ID */
  runId: number | string
  /** 原始字幕列表（来自 ffmpeg_composite 步骤输出） */
  subtitles: SubtitleEntry[]
  /** SRT 文件 URL（用于导出兜底） */
  srtUrl?: string
}>()

const emit = defineEmits<{
  (e: 'saved', result: { srt_url: string; subtitles: SubtitleEntry[]; recomposed?: boolean; final_video_url?: string; vtt_url?: string }): void
}>()

const { t } = useI18n()

// ================ 内部编辑状态 ================
// 深拷贝原始字幕，避免直接修改 props
const subtitles = ref<SubtitleEntry[]>([])
const originalSubtitles = ref<SubtitleEntry[]>([])
const hasChange = ref(false)
const saving = ref(false)

// ================ 字幕样式配置 ================
// 颜色字段用带 # 的 hex（el-color-picker 需要），提交时用 colorToHex 去掉 #
const defaultStyle: SubtitleStyle = {
  font_size: 36,
  font_color: '#FFFFFF',
  box_color: '#000000',
  box_opacity: 0.5,
  position: 'bottom',
  margin: 40,
}
const subtitleStyle = ref<SubtitleStyle>({ ...defaultStyle })

// 重新烧录状态
const recomposing = ref(false)
const recomposeProgress = ref(0)
const styleCollapse = ref<string[]>([])  // 默认折叠

// 辅助：rgba/hex 转 6 位 hex（不带 #），供后端使用
function colorToHex(color: string | undefined): string {
  if (!color) return 'FFFFFF'
  // 已是 #RRGGBB 或 RRGGBB
  const cleaned = color.replace('#', '').toUpperCase()
  if (/^[0-9A-F]{6}$/.test(cleaned)) return cleaned
  if (/^[0-9A-F]{3}$/.test(cleaned)) {
    return cleaned.split('').map(c => c + c).join('')
  }
  // rgba(r,g,b,a) 格式
  const m = color.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/)
  if (m) {
    return [m[1], m[2], m[3]].map(n => parseInt(n).toString(16).padStart(2, '0')).join('').toUpperCase()
  }
  return 'FFFFFF'
}

// 初始化 / 同步 props.subtitles 到内部状态
function syncFromProps() {
  subtitles.value = (props.subtitles || []).map(s => ({ ...s }))
  originalSubtitles.value = (props.subtitles || []).map(s => ({ ...s }))
  hasChange.value = false
}

watch(() => props.subtitles, syncFromProps, { immediate: true, deep: false })

function markChanged() {
  hasChange.value = true
}

// ================ 校验 ================
function validate(): boolean {
  for (const s of subtitles.value) {
    if (s.end <= s.start) {
      ElMessage.error(`${t('subtitleEditor.invalidTime')} (#${s.index}, start=${s.start}, end=${s.end})`)
      return false
    }
    if (!s.text || !s.text.trim()) {
      ElMessage.error(`${t('subtitleEditor.emptyText')} (#${s.index})`)
      return false
    }
  }
  return true
}

// ================ 操作 ================

// 新增条目（追加到末尾）
function handleAdd() {
  const lastEnd = subtitles.value.length
    ? subtitles.value[subtitles.value.length - 1].end
    : 0
  subtitles.value.push({
    index: subtitles.value.length,
    start: lastEnd,
    end: lastEnd + 3,
    text: '',
  })
  markChanged()
}

// 删除条目（保持 index 连续重排）
function handleDelete(idx: number) {
  subtitles.value.splice(idx, 1)
  // 重排 index
  subtitles.value.forEach((s, i) => { s.index = i })
  markChanged()
}

// 重置到原始字幕
async function handleReset() {
  try {
    await ElMessageBox.confirm(t('subtitleEditor.confirmReset'), '', {
      type: 'warning',
    })
    subtitles.value = originalSubtitles.value.map(s => ({ ...s }))
    hasChange.value = false
  } catch {
    // 用户取消
  }
}

// 保存：调用后端重新生成 SRT
async function handleSave() {
  if (!validate()) return
  saving.value = true
  try {
    const result = await saveRunSubtitles(Number(props.runId), subtitles.value)
    // 用后端返回的字幕覆盖本地（重新编号后可能和本地不一致）
    subtitles.value = result.subtitles.map(s => ({ ...s }))
    originalSubtitles.value = result.subtitles.map(s => ({ ...s }))
    hasChange.value = false
    ElMessage.success(t('subtitleEditor.saved'))
    emit('saved', result)
  } catch (e: any) {
    ElMessage.error(e?.message || t('subtitleEditor.saveFailed'))
  } finally {
    saving.value = false
  }
}

// ================ 保存并重新烧录 ================
// 调用后端 recompose 接口，用当前字幕+样式重新烧录视频（耗时约 1-2 分钟）
async function handleSaveAndRecompose() {
  if (!props.runId) return
  // 先校验字幕
  if (subtitles.value.length === 0) {
    ElMessage.warning(t('subtitleEditor.noSubtitles'))
    return
  }
  if (!validate()) return

  recomposing.value = true
  recomposeProgress.value = 0
  try {
    // 构造请求体：颜色字段从 #RRGGBB 转 6 位 hex（不带 #），与后端约定一致
    const styleForRequest: SubtitleStyle = {
      font_size: subtitleStyle.value.font_size,
      font_color: colorToHex(subtitleStyle.value.font_color),
      box_color: colorToHex(subtitleStyle.value.box_color),
      box_opacity: subtitleStyle.value.box_opacity,
      position: subtitleStyle.value.position as 'top' | 'center' | 'bottom',
      margin: subtitleStyle.value.margin,
    }

    // 调 recompose 接口（同步等待，约 30s-2min）
    const result = await recomposeVideo(Number(props.runId), {
      subtitles: subtitles.value,
      subtitle_style: styleForRequest,
    })

    // 用后端返回的字幕覆盖本地（start/end 可能按实际时长重新对齐）
    subtitles.value = result.data.subtitles.map(s => ({ ...s }))
    originalSubtitles.value = result.data.subtitles.map(s => ({ ...s }))
    hasChange.value = false

    ElMessage.success(t('subtitleEditor.recomposeSuccess'))
    // 通知父组件刷新产物 URL（额外字段标识 recompose 完成）
    emit('saved', {
      srt_url: result.data.srt_url,
      subtitles: result.data.subtitles,
      recomposed: true,
      final_video_url: result.data.final_video_url,
      vtt_url: result.data.vtt_url,
    })
  } catch (e: any) {
    ElMessage.error(e?.message || t('subtitleEditor.recomposeFailed'))
  } finally {
    recomposing.value = false
  }
}

// 导出 SRT（本地拼接下载）
function handleExport() {
  if (!validate()) return
  const srt = formatSrt(subtitles.value)
  const blob = new Blob([srt], { type: 'application/x-subrip;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `subtitles_run_${props.runId}.srt`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

// ================ SRT 格式化工具 ================

function formatSrt(entries: SubtitleEntry[]): string {
  const lines: string[] = []
  entries.forEach((entry, i) => {
    lines.push(String(i + 1))
    lines.push(`${secondsToSrtTime(entry.start)} --> ${secondsToSrtTime(entry.end)}`)
    lines.push(entry.text || '')
    lines.push('')
  })
  return lines.join('\n')
}

function secondsToSrtTime(seconds: number): string {
  if (seconds < 0) seconds = 0
  const hours = Math.floor(seconds / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  const secs = Math.floor(seconds % 60)
  const ms = Math.round((seconds - Math.floor(seconds)) * 1000)
  const pad = (n: number, l = 2) => n.toString().padStart(l, '0')
  return `${pad(hours)}:${pad(minutes)}:${pad(secs)},${pad(ms, 3)}`
}
</script>

<style scoped>
.subtitle-editor {
  width: 100%;
  background: var(--agnes-bg-card);
  border: 1px solid var(--agnes-border);
  border-radius: 8px;
  padding: 12px 16px;
}

.editor-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  gap: 12px;
  flex-wrap: wrap;
}
.header-left {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.editor-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--agnes-text-primary);
}
.editor-desc {
  font-size: 12px;
  color: var(--agnes-text-secondary);
}
.header-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.subtitle-table {
  width: 100%;
}

/* 字幕样式折叠面板 */
.style-collapse {
  margin: 12px 0;
}

/* 底部操作区 */
.editor-actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
  margin-top: 12px;
}

/* 重新烧录进度提示 */
.recompose-tip {
  margin-top: 8px;
  font-size: 12px;
  color: var(--el-color-warning);
  text-align: center;
}
</style>
