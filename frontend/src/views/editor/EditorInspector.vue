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
import type { ClipEffect, EffectType, TransitionType } from '@/lib/editor-types'
import { EFFECT_TYPES, TRANSITION_TYPES } from '@/lib/editor-fx-registry'

const store = useEditorStore()
const { t } = useI18n()

const selected = computed(() =>
  store.doc?.clips.find((c) => c.id === store.selectedClipId) ?? null,
)

const trackKind = computed(() => {
  if (!selected.value || !store.doc) return null
  return store.doc.tracks.find((tr) => tr.id === selected.value!.trackId)?.kind ?? null
})

/** 减速拉长会撞同轨后一片段：滑块下限钳到不撞车的最小倍率（命令层 overlap 拒绝兜底） */
const speedMin = computed(() => {
  const clip = selected.value
  if (!clip || !store.doc) return 0.25
  const next = store.doc.clips
    .filter((c) => c.trackId === clip.trackId && c.id !== clip.id && c.start >= clip.start)
    .sort((a, b) => a.start - b.start)[0]
  if (!next) return 0.25
  const bound = (clip.duration * (clip.props.speed ?? 1)) / (next.start - clip.start)
  return Math.max(0.25, Math.min(clip.props.speed ?? 1, Math.ceil(bound * 100) / 100))
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

/** 衔接点转场（轨级实体）：选中片段与其同轨紧随片段之间的过渡 */
const junctionTransition = computed(() => {
  const clip = selected.value
  if (!clip || !store.doc) return null
  const track = store.doc.tracks.find((tr) => tr.id === clip.trackId)
  return track?.transitions?.find((tr) => tr.afterClipId === clip.id) ?? null
})

const canEditTransition = computed(() => {
  const clip = selected.value
  if (!clip || !store.doc || trackKind.value !== 'video') return false
  return store.doc.clips.some((c) => c.trackId === clip.trackId && c.start > clip.start)
})

function setTransitionType(v: string): void {
  const clip = selected.value
  if (!clip) return
  if (!v) {
    if (junctionTransition.value) {
      store.applyOrToast({ op: 'removeTransition', payload: { trackId: clip.trackId, afterClipId: clip.id } }, t('editor.propTransition'))
    }
    return
  }
  store.applyOrToast({
    op: 'setTransition',
    payload: { trackId: clip.trackId, afterClipId: clip.id, transitionId: junctionTransition.value?.id ?? `tr_${Date.now().toString(36)}`, type: v as TransitionType, duration: junctionTransition.value?.duration ?? 0.5 },
  }, t('editor.propTransition'))
}

function setTransitionDuration(v: number | undefined): void {
  const clip = selected.value
  const current = junctionTransition.value
  if (!clip || !current) return
  store.applyOrToast({
    op: 'setTransition',
    payload: { trackId: clip.trackId, afterClipId: clip.id, transitionId: current.id, type: current.type, duration: v ?? 0.5 },
  }, t('editor.propTransition'))
}

// ---------- 效果器（整组替换走 setClipEffects，可撤销） ----------
const selectedEffects = computed<ClipEffect[]>(() => selected.value?.props.effects ?? [])

function setEffects(effects: ClipEffect[]): void {
  if (!selected.value) return
  store.applyOrToast({ op: 'setClipEffects', payload: { clipId: selected.value.id, effects } }, t('editor.propEffects'))
}

function addEffect(type: EffectType): void {
  setEffects([...selectedEffects.value, { id: `fx_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 5)}`, type, strength: type === 'blur' ? 0.4 : 1 }])
}

function updateEffect(id: string, strength: number): void {
  setEffects(selectedEffects.value.map((e) => (e.id === id ? { ...e, strength } : e)))
}

function removeEffect(id: string): void {
  setEffects(selectedEffects.value.filter((e) => e.id !== id))
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
          <div v-if="canEditTransition" class="row">
            <el-select
              size="small"
              :model-value="junctionTransition?.type ?? ''"
              clearable
              :placeholder="t('editor.none')"
              @change="setTransitionType"
            >
              <el-option v-for="tr in TRANSITION_TYPES" :key="tr" :label="t(`editor.transitions.${tr}`)" :value="tr" />
            </el-select>
            <el-input-number
              v-if="junctionTransition"
              size="small"
              :model-value="junctionTransition.duration"
              :min="0.1"
              :max="3"
              :step="0.1"
              @change="setTransitionDuration"
            />
          </div>
          <p v-else class="muted-hint">{{ t('editor.transitionNeedNext') }}</p>

          <label>{{ t('editor.propEffects') }}</label>
          <div v-for="e in selectedEffects" :key="e.id" class="row">
            <span class="effect-name">{{ t(`editor.effects.${e.type}`) }}</span>
            <el-input-number
              v-if="e.type === 'blur'"
              size="small"
              :model-value="e.strength"
              :min="0"
              :max="1"
              :step="0.05"
              @change="(v: number | undefined) => updateEffect(e.id, v ?? 0.4)"
            />
            <el-button size="small" text type="danger" @click="removeEffect(e.id)">{{ t('common.delete') }}</el-button>
          </div>
          <div class="row">
            <el-dropdown size="small" @command="(cmd: EffectType) => addEffect(cmd)">
              <el-button size="small">{{ t('editor.effectAdd') }}</el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item v-for="et in EFFECT_TYPES" :key="et" :command="et">{{ t(`editor.effects.${et}`) }}</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
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
          <p class="rect-hint">{{ t('editor.propRectHint') }}</p>
        </template>

        <div class="prop-row">
          <label>{{ t('editor.propSpeed') }}</label>
          <el-slider
            :model-value="sliderValue('speed', selected.props.speed ?? 1)"
            :min="speedMin"
            :max="4"
            :step="0.25"
            @input="(v: number) => onSliderInput('speed', v)"
            @change="(v: number) => onSliderChange('speed', v)"
          />
          <span class="prop-value">{{ sliderValue('speed', selected.props.speed ?? 1).toFixed(2) }}×</span>
        </div>

        <div class="prop-row">
          <label>{{ t('editor.propVolume') }}</label>
          <el-slider
            :model-value="sliderValue('volume', selected.props.volume ?? 1)"
            :min="0"
            :max="2"
            :step="0.05"
            @input="(v: number) => onSliderInput('volume', v)"
            @change="(v: number) => onSliderChange('volume', v)"
          />
          <span class="prop-value">{{ Math.round(sliderValue('volume', selected.props.volume ?? 1) * 100) }}%</span>
        </div>

        <div class="prop-row">
          <label>{{ t('editor.propMuted') }}</label>
          <el-checkbox
            size="small"
            :model-value="selected.props.muted === true"
            @change="setProp('muted', !selected.props.muted)"
          />
        </div>

        <div class="prop-row">
          <label>{{ t('editor.propFadeIn') }}</label>
          <el-slider
            :model-value="sliderValue('fadeIn', selected.props.fadeIn ?? 0)"
            :min="0"
            :max="5"
            :step="0.1"
            @input="(v: number) => onSliderInput('fadeIn', v)"
            @change="(v: number) => onSliderChange('fadeIn', v)"
          />
          <span class="prop-value">{{ sliderValue('fadeIn', selected.props.fadeIn ?? 0).toFixed(1) }}s</span>
        </div>

        <div class="prop-row">
          <label>{{ t('editor.propFadeOut') }}</label>
          <el-slider
            :model-value="sliderValue('fadeOut', selected.props.fadeOut ?? 0)"
            :min="0"
            :max="5"
            :step="0.1"
            @input="(v: number) => onSliderInput('fadeOut', v)"
            @change="(v: number) => onSliderChange('fadeOut', v)"
          />
          <span class="prop-value">{{ sliderValue('fadeOut', selected.props.fadeOut ?? 0).toFixed(1) }}s</span>
        </div>
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
/* 紧凑行式：标签左 / 控件中 / 数值右 */
.prop-row { display: flex; align-items: center; gap: 8px; }
.prop-row > label { width: 48px; flex-shrink: 0; margin: 0; }
.prop-row :deep(.el-slider) { flex: 1; }
.prop-row :deep(.el-slider__runway) { margin: 10px 0; }
.prop-value {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  min-width: 44px;
  text-align: right;
  font-variant-numeric: tabular-nums;
}
.rect-hint { margin: 0; font-size: 11px; color: var(--el-text-color-secondary); }
.actions { margin-top: 12px; display: flex; gap: 8px; }
.empty { color: var(--el-text-color-secondary); text-align: center; padding: 32px 0; }
</style>
