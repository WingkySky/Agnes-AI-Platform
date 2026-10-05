<script setup lang="ts">
/* =====================================================
 * 属性面板：选中片段的 props 编辑（转场/变速/fade/音量/rect/字幕文本）
 * 全部经 setClipProperty 命令入栈，可撤销
 * 滑块：el-slider 的 change 事件发的是 model-value（v-model 模式假设），
 * 不回传拖拽终值——本地草稿承接 input 让滑块跟手，松手 change 才入命令栈
 * ===================================================== */

import { computed, ref, watch } from 'vue'

import { useEditorStore } from '@/stores/editor'
import { useI18n } from '@/i18n'
import { TRANSITION_TYPES, type TransitionType } from '@/lib/editor-types'

const store = useEditorStore()
const { t } = useI18n()

const selected = computed(() =>
  store.doc?.clips.find((c) => c.id === store.selectedClipId) ?? null,
)

const trackKind = computed(() => {
  if (!selected.value || !store.doc) return null
  return store.doc.tracks.find((tr) => tr.id === selected.value!.trackId)?.kind ?? null
})

const sliderDrafts = ref<Record<string, number>>({})
watch(() => selected.value?.id, () => { sliderDrafts.value = {} })

function sliderValue(key: string, fallback: number): number {
  return sliderDrafts.value[key] ?? fallback
}
function onSliderInput(key: string, v: number): void {
  sliderDrafts.value[key] = v
}
function onSliderChange(key: string, v: number): void {
  delete sliderDrafts.value[key]
  setProp(key, v)
}

function setProp(key: string, value: unknown): void {
  if (!selected.value) return
  store.applyOrToast({ op: 'setClipProperty', payload: { clipId: selected.value.id, props: { [key]: value } } }, t('editor.ops.setClipProperty'))
}

function detachSelectedAudio(): void {
  const clip = selected.value
  if (clip) void store.detachAudio(clip.id)
}

function onSubtitleText(e: Event): void {
  const text = (e.target as HTMLTextAreaElement).value
  if (!selected.value) return
  // 字幕文本微调高频且逐字符：直改文档（随保存落库），不入撤销栈
  const clip = selected.value
  const doc = store.doc
  if (!doc) return
  const next = doc.clips.map((c) => (c.id === clip.id ? { ...c, text } : c))
  store.doc = { ...doc, clips: next }
  store.dirty = true
  store.scheduleSave()
}

function splitAtPlayhead(): void {
  const clip = selected.value
  if (!clip || !store.doc) return
  if (store.playhead <= clip.start || store.playhead >= clip.start + clip.duration) return
  store.applyOrToast({ op: 'splitClip', payload: { clipId: clip.id, at: store.playhead, newId: store.newId('clip') } }, t('editor.ops.splitClip'))
}

function removeSelected(): void {
  if (!selected.value) return
  store.applyOrToast({ op: 'removeClip', payload: { clipId: selected.value.id } }, t('editor.ops.removeClip'))
}
</script>

<template>
  <div class="inspector">
    <template v-if="selected && trackKind">
      <h4>{{ t(`editor.trackKinds.${trackKind}`) }} · #{{ selected.assetId ?? selected.id }}</h4>

      <template v-if="trackKind === 'subtitle'">
        <label>{{ t('editor.subtitleText') }}</label>
        <el-input type="textarea" :rows="3" :model-value="selected.text" @change="onSubtitleText" />
      </template>

      <template v-else>
        <template v-if="trackKind === 'video'">
          <label>{{ t('editor.propTransition') }}</label>
          <div class="row">
            <el-select
              size="small"
              :model-value="selected.props.transition?.type ?? ''"
              clearable
              :placeholder="t('editor.none')"
              @change="(v: string) => setProp('transition', v ? { type: v as TransitionType, duration: selected!.props.transition?.duration ?? 0.5 } : null)"
            >
              <el-option v-for="tr in TRANSITION_TYPES" :key="tr" :label="t(`editor.transitions.${tr}`)" :value="tr" />
            </el-select>
            <el-input-number
              v-if="selected.props.transition"
              size="small"
              :model-value="selected.props.transition.duration"
              :min="0.1"
              :max="3"
              :step="0.1"
              @change="(v: number | undefined) => setProp('transition', { type: selected!.props.transition!.type, duration: v ?? 0.5 })"
            />
          </div>

          <label>{{ t('editor.propRect') }}（PIP）</label>
          <div class="row grid2">
            <el-input-number
              v-for="key in (['x', 'y', 'w', 'h'] as const)"
              :key="key"
              size="small"
              :model-value="selected.props.rect?.[key] ?? (key === 'w' || key === 'h' ? 1 : 0)"
              :min="0"
              :max="1"
              :step="0.05"
              :controls="false"
              @change="(v: number | undefined) => setProp('rect', { x: selected!.props.rect?.x ?? 0, y: selected!.props.rect?.y ?? 0, w: selected!.props.rect?.w ?? 1, h: selected!.props.rect?.h ?? 1, [key]: v ?? 0 })"
            />
          </div>
        </template>

        <label>{{ t('editor.propSpeed') }}</label>
        <el-slider
          :model-value="sliderValue('speed', selected.props.speed ?? 1)"
          :min="0.25"
          :max="4"
          :step="0.25"
          show-input
          :show-input-controls="false"
          @input="(v: number) => onSliderInput('speed', v)"
          @change="(v: number) => onSliderChange('speed', v)"
        />

        <label>{{ t('editor.propVolume') }}</label>
        <el-slider
          :model-value="sliderValue('volume', selected.props.volume ?? 1)"
          :min="0"
          :max="2"
          :step="0.05"
          @input="(v: number) => onSliderInput('volume', v)"
          @change="(v: number) => onSliderChange('volume', v)"
        />
        <el-checkbox
          size="small"
          :model-value="selected.props.muted === true"
          @change="setProp('muted', !selected.props.muted)"
        >{{ t('editor.propMuted') }}</el-checkbox>
        <label>{{ t('editor.propFadeIn') }}（s）</label>
        <el-slider
          :model-value="sliderValue('fadeIn', selected.props.fadeIn ?? 0)"
          :min="0"
          :max="5"
          :step="0.1"
          @input="(v: number) => onSliderInput('fadeIn', v)"
          @change="(v: number) => onSliderChange('fadeIn', v)"
        />
        <label>{{ t('editor.propFadeOut') }}（s）</label>
        <el-slider
          :model-value="sliderValue('fadeOut', selected.props.fadeOut ?? 0)"
          :min="0"
          :max="5"
          :step="0.1"
          @input="(v: number) => onSliderInput('fadeOut', v)"
          @change="(v: number) => onSliderChange('fadeOut', v)"
        />
      </template>

      <div class="actions">
        <el-button size="small" @click="splitAtPlayhead">{{ t('editor.split') }}</el-button>
        <el-button v-if="trackKind === 'video'" size="small" @click="detachSelectedAudio">
          {{ t('editor.ops.detachAudio') }}
        </el-button>
        <el-button size="small" type="danger" @click="removeSelected">{{ t('common.delete') }}</el-button>
      </div>
    </template>
    <div v-else class="empty">{{ t('editor.inspectorEmpty') }}</div>
  </div>
</template>

<style scoped>
.inspector {
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.inspector h4 { margin: 0 0 4px; font-size: 13px; }
.inspector label { font-size: 12px; color: var(--el-text-color-secondary); }
.row { display: flex; gap: 6px; align-items: center; }
.row.grid2 { display: grid; grid-template-columns: 1fr 1fr; }
.actions { margin-top: 12px; display: flex; gap: 8px; }
.empty { color: var(--el-text-color-secondary); text-align: center; padding: 32px 0; }
</style>
