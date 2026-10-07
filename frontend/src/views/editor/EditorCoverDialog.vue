<!-- =====================================================
     封面设置弹窗（剪映式）：大图预览 + 时间滑杆选帧 + 候选帧条 + 上传自定义
     保存 = 当前帧抽帧上传（或直接用上传图 URL）→ PATCH editing_projects.cover_url
     ===================================================== -->

<template>
  <el-dialog v-model="visible" :title="t('editor.coverTitle')" width="560px" @open="onOpen">
    <div v-loading="loading" class="cover-preview">
      <img v-if="previewSrc" :src="previewSrc" alt="">
      <div v-else class="cover-empty">{{ t('editor.coverNoFrame') }}</div>
    </div>

    <div class="cover-slider">
      <el-slider
        v-model="draftT"
        :min="0"
        :max="duration"
        :step="0.05"
        :format-tooltip="formatTooltip"
        @change="onSeek"
      />
      <span class="cover-time">{{ draftT.toFixed(2) }}s / {{ duration.toFixed(2) }}s</span>
    </div>

    <p class="cover-hint">{{ t('editor.coverCandidates') }}</p>
    <div class="candidate-row">
      <button
        v-for="c in candidateThumbs"
        :key="c.t"
        type="button"
        class="candidate"
        :class="{ active: Math.abs(c.t - appliedT) < 0.03 }"
        :title="`${c.t.toFixed(2)}s`"
        @click="seekTo(c.t)"
      >
        <img v-if="c.src" :src="c.src" alt="">
        <span v-else class="cand-empty">…</span>
      </button>
    </div>

    <template #footer>
      <div class="cover-footer">
        <el-button size="small" :loading="uploading" @click="fileInput?.click()">{{ t('editor.coverUpload') }}</el-button>
        <input ref="fileInput" type="file" accept="image/jpeg,image/png,image/webp" hidden @change="onPickFile">
        <span class="footer-spacer" />
        <el-button size="small" @click="visible = false">{{ t('common.cancel') }}</el-button>
        <el-button size="small" type="primary" :loading="saving" :disabled="!previewSrc && !customUrl" @click="save">
          {{ t('common.confirm') }}
        </el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'

import { useEditorStore } from '@/stores/editor'
import { useI18n } from '@/i18n'
import { uploadEditorCover } from '@/api/editor'
import { createVideoSink } from '@/lib/editor-media'
import {
  coverCandidates, coverClipAt, coverDocDuration, coverSourceTime,
} from '@/lib/editor-cover'
const visible = defineModel<boolean>({ default: false })
const store = useEditorStore()
const { t } = useI18n()

const loading = ref(false)
const saving = ref(false)
const uploading = ref(false)
const draftT = ref(0)          // 滑杆拖动值（实时）
const appliedT = ref(0)        // 已抽帧时刻（防抖后的取帧点）
const previewDataUrl = ref('') // 当前帧 dataURL
const customUrl = ref('')      // 上传的自定义封面（优先于帧）
const fileInput = ref<HTMLInputElement | null>(null)

const duration = computed(() => (store.doc ? coverDocDuration(store.doc) : 0.1))
const previewSrc = computed(() => customUrl.value || previewDataUrl.value)

interface Candidate { t: number; src: string }
const candidateThumbs = ref<Candidate[]>([])

function formatTooltip(v: number): string {
  return `${v.toFixed(2)}s`
}

async function onOpen(): Promise<void> {
  customUrl.value = ''
  draftT.value = Math.min(store.playhead, duration.value)
  appliedT.value = draftT.value
  previewDataUrl.value = ''
  candidateThumbs.value = []
  void buildCandidates() // 候选条后台抓帧，不阻塞首预览
  await refreshFrame()
  // 播放头落在片段间空隙/文档末尾（无画面可取）：自动跳到第一个候选帧，避免开窗即空预览
  if (!previewDataUrl.value) {
    const times = store.doc ? coverCandidates(store.doc) : []
    if (times.length > 0) await seekTo(times[0])
  }
}

function seekTo(t: number): void {
  draftT.value = t
  void onSeek(t)
}

/** 滑杆松手/候选点击：抽帧刷新预览（拖动中不抽，防解码风暴） */
async function onSeek(t?: number): Promise<void> {
  const target = t ?? draftT.value
  appliedT.value = target
  await refreshFrame()
}

async function grabFrame(t: number): Promise<string> {
  const doc = store.doc
  if (!doc) return ''
  const clip = coverClipAt(doc, t)
  if (!clip || clip.assetId == null) return '' // gap 黑场：返回空（预览显示黑块占位）
  let asset = store.assetCache.get(clip.assetId)
  if (!asset?.asset_url) {
    asset = (await store.fetchAsset(clip.assetId)) ?? asset // 未缓存先加载再取
  }
  if (!asset?.asset_url) return ''
  const sink = await createVideoSink(asset.asset_url)
  if (!sink) return ''
  try {
    const frame = await sink.getCanvas(coverSourceTime(clip, t))
    if (!frame) return ''
    const out = document.createElement('canvas')
    out.width = frame.canvas.width
    out.height = frame.canvas.height
    out.getContext('2d')?.drawImage(frame.canvas, 0, 0)
    return out.toDataURL('image/jpeg', 0.85)
  } catch {
    return ''
  }
}

async function refreshFrame(): Promise<void> {
  loading.value = true
  try {
    previewDataUrl.value = await grabFrame(appliedT.value)
  } finally {
    loading.value = false
  }
}

async function buildCandidates(): Promise<void> {
  const doc = store.doc
  if (!doc) return
  const times = coverCandidates(doc)
  candidateThumbs.value = times.map((t) => ({ t, src: '' }))
  for (const c of candidateThumbs.value) {
    c.src = await grabFrame(c.t)
  }
}

async function onPickFile(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  uploading.value = true
  try {
    const { url } = await uploadEditorCover(file)
    customUrl.value = url
  } catch (err) {
    ElMessage.error(String(err))
  } finally {
    uploading.value = false
  }
}

async function save(): Promise<void> {
  saving.value = true
  try {
    let url = customUrl.value
    if (!url) {
      // 当前帧 → Blob → 上传
      const blob = await (async (): Promise<Blob | null> => {
        const src = previewDataUrl.value
        if (!src) return null
        const resp = await fetch(src)
        return resp.blob()
      })()
      if (!blob) {
        ElMessage.warning(t('editor.coverNoFrame'))
        return
      }
      const file = new File([blob], 'cover.jpg', { type: 'image/jpeg' })
      const uploaded = await uploadEditorCover(file)
      url = uploaded.url
    }
    await store.setCoverUrl(url)
    ElMessage.success(t('editor.coverSaved'))
    visible.value = false
  } catch (err) {
    ElMessage.error(String(err))
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.cover-preview {
  aspect-ratio: 16 / 9;
  background: #000;
  border-radius: 8px;
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
}
.cover-preview img {
  width: 100%;
  height: 100%;
  object-fit: contain;
  display: block;
}
.cover-empty {
  color: var(--el-text-color-secondary);
  font-size: 13px;
}
.cover-slider {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 12px;
}
.cover-slider .el-slider {
  flex: 1;
}
.cover-time {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}
.cover-hint {
  margin: 10px 0 6px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.candidate-row {
  display: flex;
  gap: 6px;
  overflow-x: auto;
  padding-bottom: 4px;
}
.candidate {
  width: 72px;
  aspect-ratio: 16 / 9;
  flex-shrink: 0;
  border: 2px solid transparent;
  border-radius: 6px;
  overflow: hidden;
  cursor: pointer;
  background: #000;
  padding: 0;
}
.candidate.active {
  border-color: var(--el-color-primary);
}
.candidate img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.cand-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: var(--el-text-color-placeholder);
  font-size: 12px;
}
.cover-footer {
  display: flex;
  align-items: center;
  gap: 8px;
}
.footer-spacer {
  flex: 1;
}
</style>
