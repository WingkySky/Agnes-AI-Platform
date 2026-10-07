<!-- =====================================================
     字幕工作区弹窗：whisper 转写（音频/视频轨）+ SRT 导入 → 可编辑草稿
     → 替换/追加落轨（rebuildSubtitleClips）；导出 SRT 从目标轨取
     ===================================================== -->

<template>
  <el-dialog v-model="visible" :title="t('editor.subtitleWorkspaceTitle')" width="640px" @open="onOpen">
    <div class="sub-toolbar">
      <span class="sub-label">{{ t('editor.subGenSource') }}</span>
      <el-select v-model="sourceTrackId" size="small" class="src-select">
        <el-option v-for="tr in sourceTracks" :key="tr.id" :label="trackLabels[tr.id]" :value="tr.id" />
      </el-select>
      <el-button size="small" type="primary" :loading="transcribing" :disabled="!sourceTrackId" @click="transcribe">
        {{ t('editor.subGenRun') }}
      </el-button>
      <span class="sub-toolbar-spacer" />
      <span class="sub-label">{{ t('editor.subTargetTrack') }}</span>
      <el-select v-model="targetTrackId" size="small" class="tgt-select">
        <el-option v-for="tr in subtitleTracks" :key="tr.id" :label="trackLabels[tr.id]" :value="tr.id" />
        <el-option :label="t('editor.subNewTrack')" :value="NEW_TRACK" />
      </el-select>
    </div>

    <div class="draft-list">
      <div v-if="!draft.length" class="draft-empty">{{ t('editor.subDraftEmpty') }}</div>
      <div v-for="(row, i) in draft" :key="i" class="draft-row">
        <span class="draft-time">{{ formatTimecode(row.start) }}</span>
        <el-input v-model="row.text" size="small" />
        <el-button size="small" text :icon="Delete" :title="t('common.delete')" @click="draft.splice(i, 1)" />
      </div>
    </div>

    <template #footer>
      <div class="sub-footer">
        <el-button size="small" @click="fileInput?.click()">{{ t('editor.subImportSrt') }}</el-button>
        <el-button size="small" :disabled="targetTrackId === NEW_TRACK" @click="exportSrt">
          {{ t('editor.subExportSrt') }}
        </el-button>
        <input ref="fileInput" type="file" accept=".srt,text/plain" hidden @change="onPickFile">
        <span class="sub-footer-spacer" />
        <el-button size="small" @click="visible = false">{{ t('common.cancel') }}</el-button>
        <el-button size="small" :disabled="!draft.length" @click="land('append')">{{ t('editor.subAppend') }}</el-button>
        <el-button size="small" type="primary" :disabled="!draft.length" @click="land('replace')">
          {{ t('editor.subReplace') }}
        </el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Delete } from '@element-plus/icons-vue'

import { useEditorStore } from '@/stores/editor'
import { useI18n } from '@/i18n'
import { previewSubtitleSegments } from '@/api/editor'
import { formatSrtCues, parseSrt } from '@/lib/canvas-media'
import { draftToCues, mergeSubtitleCues, type SubtitleDraftRow } from '@/lib/editor-subtitles'
import { formatTimecode } from '@/lib/editor-timecode'
import { useDownload } from '@/composables/useDownload'

const props = defineProps<{ modelValue: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [boolean] }>()
const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const store = useEditorStore()
const { t } = useI18n()

const NEW_TRACK = '__new__'
const sourceTrackId = ref('')
const targetTrackId = ref<string>(NEW_TRACK)
const draft = ref<SubtitleDraftRow[]>([])
const transcribing = ref(false)
const fileInput = ref<HTMLInputElement | null>(null)

const sourceTracks = computed(() =>
  (store.doc?.tracks ?? [])
    .filter((tr) => tr.kind === 'audio' || tr.kind === 'video')
    .sort((a, b) => a.order - b.order),
)
const subtitleTracks = computed(() =>
  (store.doc?.tracks ?? []).filter((tr) => tr.kind === 'subtitle').sort((a, b) => a.order - b.order),
)

const trackLabels = computed(() => {
  const labels: Record<string, string> = {}
  for (const kind of ['video', 'audio', 'subtitle'] as const) {
    (store.doc?.tracks ?? [])
      .filter((tr) => tr.kind === kind)
      .sort((a, b) => a.order - b.order)
      .forEach((tr, i) => { labels[tr.id] = `${t(`editor.trackKinds.${kind}`)} ${i + 1}` })
  }
  return labels
})

function onOpen(): void {
  draft.value = []
  sourceTrackId.value = sourceTracks.value[0]?.id ?? ''
  targetTrackId.value = subtitleTracks.value[0]?.id ?? NEW_TRACK
}

async function transcribe(): Promise<void> {
  if (!sourceTrackId.value || !store.uid) return
  transcribing.value = true
  try {
    const { segments } = await previewSubtitleSegments(store.uid, sourceTrackId.value)
    if (!segments.length) {
      ElMessage.info(t('editor.subtitleEmpty'))
      return
    }
    draft.value = segments.map((s) => ({ start: s.start, end: s.end, text: s.text }))
  } catch (err) {
    const detail = (err as { detail?: { message?: string } | string }).detail
    const msg = typeof detail === 'string' ? detail : detail?.message
    ElMessage.error(msg || t('editor.errors.transcribe'))
  } finally {
    transcribing.value = false
  }
}

async function onPickFile(e: Event): Promise<void> {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  const segments = parseSrt(await file.text())
  if (!segments.length) {
    ElMessage.warning(t('editor.srtEmpty'))
    return
  }
  draft.value = segments.map((s) => ({ start: s.start_time, end: s.start_time + s.duration, text: s.text }))
  input.value = ''
}

/** 目标轨落点：选「新建」时先 addTrack（独立撤销步），返回可用轨 id */
function resolveTargetTrackId(): string | null {
  if (targetTrackId.value !== NEW_TRACK) return targetTrackId.value
  const id = store.newId('track')
  const ok = store.applyOrToast(
    { op: 'addTrack', payload: { track: { id, kind: 'subtitle' } } },
    t('editor.ops.addTrack'),
  )
  if (!ok) return null
  targetTrackId.value = id
  return id
}

function land(mode: 'replace' | 'append'): void {
  if (!draft.value.length) return
  const trackId = resolveTargetTrackId()
  if (!trackId) return
  const cues = draftToCues(draft.value, () => store.newId('sub'))
  const clips = mode === 'replace'
    ? cues
    : mergeSubtitleCues((store.doc?.clips ?? []).filter((c) => c.trackId === trackId), cues)
  const ok = store.applyOrToast(
    { op: 'rebuildSubtitleClips', payload: { trackId, clips } },
    t('editor.ops.rebuildSubtitleClips'),
  )
  if (ok) {
    ElMessage.success(t('editor.subLanded', { n: clips.length }))
    visible.value = false
  }
}

function exportSrt(): void {
  if (targetTrackId.value === NEW_TRACK) return
  const clips = (store.doc?.clips ?? [])
    .filter((c) => c.trackId === targetTrackId.value)
    .sort((a, b) => a.start - b.start)
    .map((c) => ({ start_time: c.start, duration: c.duration, text: c.text ?? '' }))
  const srt = formatSrtCues(clips)
  void useDownload().triggerDownload(
    new Blob([srt], { type: 'application/x-subrip' }),
    `${store.title || 'subtitles'}.srt`,
  )
}
</script>

<style scoped>
.sub-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}
.sub-label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  white-space: nowrap;
}
.src-select { width: 150px; }
.tgt-select { width: 160px; }
.sub-toolbar-spacer { flex: 1; }

.draft-list {
  max-height: 320px;
  overflow-y: auto;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  padding: 8px;
}
.draft-empty {
  text-align: center;
  color: var(--el-text-color-placeholder);
  font-size: 13px;
  padding: 24px 0;
}
.draft-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 3px 0;
}
.draft-time {
  font-variant-numeric: tabular-nums;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  width: 92px;
  flex-shrink: 0;
}

.sub-footer {
  display: flex;
  align-items: center;
  gap: 8px;
}
.sub-footer-spacer { flex: 1; }
</style>
