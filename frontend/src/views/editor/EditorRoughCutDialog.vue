<!-- =====================================================
     AI 粗剪弹窗：选素材（视频/音频）+ 模式（剔除静音/场景切分）+ 参数
     → 后端分析 → 段列表预览（保留占比）→ 确认落当前工程（同类型轨尾顺序排布）
     ===================================================== -->

<template>
  <el-dialog v-model="visible" :title="t('editor.roughCutTitle')" width="620px" @open="onOpen">
    <div class="rc-row">
      <span class="rc-label">{{ t('editor.roughCutAsset') }}</span>
      <el-select v-model="assetId" size="small" class="rc-asset-select" filterable>
        <el-option v-for="a in mediaAssets" :key="a.id" :label="`[${a.media_type}] ${a.name}`" :value="a.id" />
      </el-select>
      <el-button size="small" type="primary" :loading="analyzing" :disabled="!assetId" @click="analyze">
        {{ t('editor.roughCutRun') }}
      </el-button>
    </div>

    <div class="rc-row">
      <span class="rc-label">{{ t('editor.roughCutMode') }}</span>
      <el-radio-group v-model="mode" size="small">
        <el-radio-button value="silence">{{ t('editor.roughCutModeSilence') }}</el-radio-button>
        <el-radio-button value="scenes">{{ t('editor.roughCutModeScenes') }}</el-radio-button>
      </el-radio-group>
    </div>

    <div v-if="mode === 'silence'" class="rc-row">
      <span class="rc-label">{{ t('editor.roughCutThreshold') }}</span>
      <el-slider v-model="thresholdDb" :min="-60" :max="-10" :step="1" class="rc-slider" />
      <span class="rc-value">{{ thresholdDb }} dB</span>
    </div>
    <div v-else class="rc-row">
      <span class="rc-label">{{ t('editor.roughCutThreshold') }}</span>
      <el-slider v-model="sceneThreshold" :min="5" :max="40" :step="1" class="rc-slider" />
      <span class="rc-value">{{ sceneThreshold }}</span>
    </div>

    <!-- 分析结果预览 -->
    <template v-if="result">
      <div class="rc-summary">
        <span>{{ t('editor.roughCutSummary', { n: result.segments.length, sec: segmentsDuration(result.segments).toFixed(1) }) }}</span>
        <span v-if="result.kept_ratio != null" class="rc-ratio">{{ t('editor.roughCutRatio', { p: Math.round(result.kept_ratio * 100) }) }}</span>
      </div>
      <div class="rc-seg-list">
        <div v-for="(seg, i) in result.segments" :key="i" class="rc-seg-row">
          <span class="rc-seg-time">{{ formatTimecode(seg.start) }} → {{ formatTimecode(seg.end) }}</span>
          <span class="rc-seg-dur">{{ (seg.end - seg.start).toFixed(2) }}s</span>
        </div>
      </div>
    </template>

    <template #footer>
      <el-button size="small" @click="visible = false">{{ t('common.cancel') }}</el-button>
      <el-button
        size="small"
        type="primary"
        :disabled="!result || !result.segments.length"
        :loading="landing"
        @click="land"
      >
        {{ t('editor.roughCutLand') }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'

import { useEditorStore } from '@/stores/editor'
import { useI18n } from '@/i18n'
import { analyzeAsset, type RoughCutAnalysis } from '@/api/editor'
import { listAssets, type UnifiedAsset } from '@/api/assets'
import { segmentsDuration, segmentsToClips } from '@/lib/editor-rough-cut'
import { formatTimecode } from '@/lib/editor-timecode'

const props = defineProps<{ modelValue: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [boolean] }>()
const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const store = useEditorStore()
const { t } = useI18n()

const mediaAssets = ref<UnifiedAsset[]>([])
const assetId = ref<number | null>(null)
const mode = ref<'silence' | 'scenes'>('silence')
const thresholdDb = ref(-30)
const sceneThreshold = ref(14)
const analyzing = ref(false)
const landing = ref(false)
const result = ref<RoughCutAnalysis | null>(null)

async function onOpen() {
  result.value = null
  if (mediaAssets.value.length) return
  try {
    const resp = await listAssets({ page: 1, page_size: 100 })
    // media_type 是媒体种类（video/audio/image）；type 是容器类型（material/clip）
    mediaAssets.value = resp.items.filter((a) => a.media_type === 'video' || a.media_type === 'audio')
  } catch {
    // 列表失败不阻断：素材下拉为空，用户可从素材库先上传
  }
}

async function analyze() {
  if (!assetId.value) return
  analyzing.value = true
  result.value = null
  try {
    result.value = await analyzeAsset(
      assetId.value,
      mode.value,
      mode.value === 'silence' ? { threshold_db: thresholdDb.value } : { threshold: sceneThreshold.value },
    )
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : String(e))
  } finally {
    analyzing.value = false
  }
}

/** 落当前工程：找/建与素材同类型轨，从轨尾起顺序排布（每段一条 addClip，独立可撤销） */
async function land() {
  const analysis = result.value
  if (!analysis?.segments.length || !assetId.value) return
  const asset = mediaAssets.value.find((a) => a.id === assetId.value)
  const kind = asset?.media_type === 'audio' ? 'audio' : 'video'
  const doc = store.doc
  if (!doc) return
  const track = doc.tracks.find((tr) => tr.kind === kind && !tr.flags.locked)
    ?? doc.tracks.find((tr) => tr.kind === kind)
  if (!track) {
    ElMessage.warning(t('editor.errors.noTrack'))
    return
  }
  const tail = doc.clips
    .filter((c) => c.trackId === track.id)
    .reduce((end, c) => Math.max(end, c.start + c.duration), 0)
  const clips = segmentsToClips(analysis.segments, { trackId: track.id, assetId: assetId.value, offset: tail }, (p) => store.newId(p))
  landing.value = true
  try {
    let landed = 0
    for (const clip of clips) {
      const ok = store.applyOrToast({ op: 'addClip', payload: { clip } }, t('editor.ops.addClip'))
      if (!ok) break
      landed++
    }
    if (landed) {
      ElMessage.success(t('editor.roughCutLanded', { n: landed }))
      visible.value = false
    }
  } finally {
    landing.value = false
  }
}
</script>

<style scoped>
.rc-row { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; }
.rc-label { font-size: 13px; color: var(--el-text-color-secondary); flex-shrink: 0; }
.rc-asset-select { flex: 1; }
.rc-slider { flex: 1; }
.rc-value { font-size: 12px; color: var(--el-text-color-regular); width: 48px; text-align: right; }
.rc-summary { display: flex; gap: 12px; font-size: 13px; margin: 4px 0 8px; color: var(--el-text-color-primary); }
.rc-ratio { color: var(--el-color-primary); }
.rc-seg-list { max-height: 220px; overflow-y: auto; border: 1px solid var(--el-border-color-lighter); border-radius: 4px; }
.rc-seg-row { display: flex; justify-content: space-between; padding: 4px 10px; font-size: 12px; border-bottom: 1px solid var(--el-border-color-lighter); }
.rc-seg-row:last-child { border-bottom: none; }
.rc-seg-time { font-family: monospace; }
.rc-seg-dur { color: var(--el-text-color-secondary); }
</style>
