<!-- =====================================================
     SceneInspector —— 属性检查器（工作台右栏）
     选中元素属性（机位/主体/灯光/道具）+ 环境布景 +
     Shot 检查器（activeShot 存在时）+ 翻译器实时预览。
     ===================================================== -->
<template>
  <div class="scene-inspector">
    <!-- 环境布景 -->
    <div class="insp-section">
      <div class="section-title">{{ t('scene3d.environmentTitle') }}</div>
      <el-select
        :model-value="modelValue.stage?.environment?.type || 'studio'"
        size="small"
        style="width: 100%"
        @change="onEnvironmentChange"
      >
        <el-option v-for="opt in environmentOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
      </el-select>
    </div>

    <!-- 选中元素属性 -->
    <div class="insp-section">
      <div class="section-title">{{ selectedLabel }}</div>
      <template v-if="selected?.type === 'camera' && camera">
        <label class="field">{{ t('scene3d.cameraName') }}</label>
        <el-input :model-value="camera.name" size="small" @update:model-value="(v: string) => patchCamera({ name: v })" />
        <label class="field">{{ t('scene3d.cameraFov') }}</label>
        <el-input-number
          :model-value="camera.fov"
          size="small"
          :min="15"
          :max="100"
          style="width: 100%"
          @change="(v?: number) => v != null && patchCamera({ fov: v })"
        />
        <label class="field">{{ t('scene3d.detailDistance') }}</label>
        <span class="field-value">{{ cameraDistance }}</span>
      </template>
      <template v-else-if="selected?.type === 'subject' && subject">
        <label class="field">{{ t('scene3d.customLabel') }}</label>
        <el-input :model-value="subject.label" size="small" @update:model-value="(v: string) => patchSubject({ label: v })" />
        <label class="field">{{ t('scene3d.pose') }}</label>
        <el-select
          :model-value="subject.pose?.preset || 'stand'"
          size="small"
          style="width: 100%"
          @change="(v: string) => patchSubject({ pose: { preset: v } })"
        >
          <el-option v-for="p in posePresetIds" :key="p" :label="t(`scene3d.pose_${p}`)" :value="p" />
        </el-select>
      </template>
      <template v-else-if="selected?.type === 'light' && light">
        <label class="field">{{ t('scene3d.lightIntensity') }}</label>
        <el-slider
          :model-value="light.intensity"
          :min="0"
          :max="5"
          :step="0.1"
          size="small"
          @change="(v?: number) => v != null && patchLight({ intensity: v })"
        />
      </template>
      <template v-else-if="selected?.type === 'prop' && prop">
        <label class="field">{{ t('scene3d.customLabel') }}</label>
        <el-input :model-value="prop.label" size="small" @update:model-value="(v: string) => patchProp({ label: v })" />
        <label class="field">{{ t('scene3d.propType') }}</label>
        <el-select :model-value="prop.type" size="small" style="width: 100%" @change="(v: PropData['type']) => patchProp({ type: v })">
          <el-option v-for="pt in propTypes" :key="pt" :label="t(`scene3d.prop_${pt}`)" :value="pt" />
        </el-select>
        <label class="field">{{ t('scene3d.propScale') }}</label>
        <el-input-number
          :model-value="prop.scale ?? 1"
          size="small"
          :min="0.1"
          :max="10"
          :step="0.1"
          style="width: 100%"
          @change="(v?: number) => v != null && patchProp({ scale: v })"
        />
      </template>
      <div v-else class="hint">{{ t('scene3d.inspectorHint') }}</div>
    </div>

    <!-- Shot 检查器 -->
    <div v-if="shot" class="insp-section">
      <div class="section-title">{{ t('scene3d.shotInspector') }}</div>
      <label class="field">{{ t('scene3d.shotSize') }}</label>
      <el-select :model-value="shot.shotSize" size="small" style="width: 100%" @change="(v: ShotSize) => patchShot({ shotSize: v })">
        <el-option v-for="s in shotSizes" :key="s" :label="t(`scene3d.size_${s}`)" :value="s" />
      </el-select>
      <label class="field">{{ t('scene3d.cameraMove') }}</label>
      <el-select :model-value="shot.cameraMove" size="small" style="width: 100%" @change="(v: CameraMove) => patchShot({ cameraMove: v })">
        <el-option v-for="m in cameraMoves" :key="m" :label="t(`scene3d.move_${m}`)" :value="m" />
      </el-select>
      <div class="field-row">
        <div class="field-col">
          <label class="field">{{ t('scene3d.duration') }}</label>
          <el-input-number
            :model-value="shot.duration"
            size="small"
            :min="0.5"
            :max="60"
            :step="0.5"
            @change="(v?: number) => v != null && patchShot({ duration: v })"
          />
        </div>
        <div class="field-col">
          <label class="field">FPS</label>
          <el-select :model-value="shot.fps" size="small" @change="(v: ShotData['fps']) => patchShot({ fps: v })">
            <el-option :value="24" label="24" />
            <el-option :value="25" label="25" />
            <el-option :value="30" label="30" />
          </el-select>
        </div>
      </div>
      <label class="field">{{ t('scene3d.shotPrompt') }}</label>
      <el-input
        :model-value="shot.prompt || ''"
        type="textarea"
        :rows="2"
        :placeholder="t('scene3d.shotPromptPlaceholder')"
        @update:model-value="(v: string) => patchShot({ prompt: v })"
      />

      <!-- 关键帧 -->
      <div class="section-title sub">
        {{ t('scene3d.keyframesTitle') }}
        <el-button size="small" type="primary" plain @click="$emit('add-keyframe')">
          {{ t('scene3d.addKeyframe') }}
        </el-button>
      </div>
      <div v-for="(k, i) in shot.keyframes" :key="i" class="keyframe-row">
        <span class="kf-index">#{{ i + 1 }}</span>
        <el-input-number
          :model-value="k.time"
          size="small"
          :min="0"
          :max="60"
          :step="0.5"
          style="width: 88px"
          @change="(v?: number) => v != null && patchKeyframe(i, { time: v })"
        />
        <el-select
          :model-value="k.easing"
          size="small"
          style="width: 86px"
          @change="(v: KeyframeEasing) => patchKeyframe(i, { easing: v })"
        >
          <el-option value="linear" :label="t('scene3d.ease_linear')" />
          <el-option value="smooth" :label="t('scene3d.ease_smooth')" />
          <el-option value="cut" :label="t('scene3d.ease_cut')" />
        </el-select>
        <el-button size="small" :icon="Delete" circle :disabled="shot.keyframes.length <= 1" @click="removeKeyframe(i)" />
      </div>
      <div v-if="!shot.keyframes.length" class="hint">{{ t('scene3d.noKeyframes') }}</div>
    </div>

    <!-- 翻译器实时预览 -->
    <div class="insp-section grow">
      <div class="section-title">{{ t('scene3d.promptPreview') }}</div>
      <div v-if="promptSuffix" class="prompt-suffix">{{ promptSuffix }}</div>
      <el-empty v-else :description="t('scene3d.noPrompt')" :image-size="48" />
      <div v-if="Object.keys(promptDetails || {}).length" class="details-list">
        <div v-for="(val, key) in promptDetails" :key="key" class="detail-item">
          <span class="detail-key">{{ detailLabel(String(key)) }}</span>
          <span class="detail-val">{{ val }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * SceneInspector —— 右栏属性面板：环境/元素属性/Shot 检查器/翻译器预览。
 * 全部编辑经 update:modelValue 上抛；关键帧记录经 add-keyframe 事件（视口取姿态）。
 */
import { computed } from 'vue'
import { Delete } from '@element-plus/icons-vue'
import { useI18n } from '@/i18n'
import { POSE_PRESET_IDS } from '@/lib/scene/poses'
import type {
  CameraDevice,
  CameraMove,
  KeyframeEasing,
  LightData,
  PropData,
  SceneData,
  ShotData,
  ShotSize,
  SubjectData,
} from '@/types/scene'

type TreeType = 'camera' | 'subject' | 'light' | 'prop'

const props = defineProps<{
  modelValue: SceneData
  selected?: { type: TreeType; index: number } | null
  shot?: ShotData | null
  promptSuffix?: string
  promptDetails?: Record<string, unknown>
}>()

const emit = defineEmits<{
  'update:modelValue': [value: SceneData]
  'add-keyframe': []
}>()

const { t } = useI18n()

const shotSizes: ShotSize[] = ['extreme_wide', 'wide', 'medium', 'medium_close', 'close_up', 'extreme_close_up']
const cameraMoves: CameraMove[] = ['static', 'push_in', 'pull_out', 'pan', 'tilt', 'orbit', 'tracking', 'crane', 'handheld']
const propTypes: PropData['type'][] = ['box', 'plane', 'sphere', 'cylinder']
const posePresetIds = POSE_PRESET_IDS

const camera = computed<CameraDevice | null>(() =>
  props.selected?.type === 'camera' ? props.modelValue.cameras[props.selected.index] ?? null : null,
)
const subject = computed<SubjectData | null>(() =>
  props.selected?.type === 'subject' ? props.modelValue.subjects[props.selected.index] ?? null : null,
)
const light = computed<LightData | null>(() =>
  props.selected?.type === 'light' ? props.modelValue.lights[props.selected.index] ?? null : null,
)
const prop = computed<PropData | null>(() =>
  props.selected?.type === 'prop' ? props.modelValue.props[props.selected.index] ?? null : null,
)

const selectedLabel = computed(() => {
  if (camera.value) return `${t('scene3d.targetCamera')} · ${camera.value.name}`
  if (subject.value) return `${t('scene3d.targetSubject')} · ${subject.value.label}`
  if (light.value) return t('scene3d.targetLight')
  if (prop.value) return `${t('scene3d.targetProp')} · ${prop.value.label}`
  return t('scene3d.inspectorTitle')
})

const cameraDistance = computed(() => {
  const c = camera.value
  if (!c) return '—'
  const dx = c.position.x - c.target.x
  const dz = c.position.z - c.target.z
  return `${Math.sqrt(dx * dx + dz * dz).toFixed(1)} m`
})

const environmentOptions = computed(() => [
  { value: 'studio', label: t('scene3d.envStudio') },
  { value: 'indoor', label: t('scene3d.envIndoor') },
  { value: 'outdoor', label: t('scene3d.envOutdoor') },
  { value: 'night', label: t('scene3d.envNight') },
  { value: 'custom', label: t('scene3d.envCustom') },
])

function emitData(patch: Partial<SceneData>) {
  emit('update:modelValue', { ...props.modelValue, ...patch } as SceneData)
}

function onEnvironmentChange(envType: string) {
  const opt = environmentOptions.value.find(o => o.value === envType)
  emitData({
    stage: {
      ...props.modelValue.stage,
      environment: { type: envType as SceneData['stage']['environment']['type'], label: opt?.label || '' },
    },
  })
}

function patchCamera(patch: Partial<CameraDevice>) {
  if (!props.selected || props.selected.type !== 'camera') return
  const cameras = props.modelValue.cameras.map((c, i) => (i === props.selected!.index ? { ...c, ...patch } : c))
  emitData({ cameras })
}

function patchSubject(patch: Partial<SubjectData>) {
  if (!props.selected || props.selected.type !== 'subject') return
  const subjects = props.modelValue.subjects.map((s, i) => (i === props.selected!.index ? { ...s, ...patch } : s))
  emitData({ subjects })
}

function patchLight(patch: Partial<LightData>) {
  if (!props.selected || props.selected.type !== 'light') return
  const lights = props.modelValue.lights.map((l, i) => (i === props.selected!.index ? { ...l, ...patch } : l))
  emitData({ lights })
}

function patchProp(patch: Partial<PropData>) {
  if (!props.selected || props.selected.type !== 'prop') return
  const list = props.modelValue.props.map((p, i) => (i === props.selected!.index ? { ...p, ...patch } : p))
  emitData({ props: list })
}

function patchShot(patch: Partial<ShotData>) {
  const shotId = props.shot?.id
  if (!shotId) return
  const shots = props.modelValue.shots.map(s => (s.id === shotId ? { ...s, ...patch } : s))
  emitData({ shots })
}

function patchKeyframe(index: number, patch: Partial<{ time: number; easing: KeyframeEasing }>) {
  const shotId = props.shot?.id
  if (!shotId) return
  const shots = props.modelValue.shots.map(s =>
    s.id === shotId
      ? { ...s, keyframes: s.keyframes.map((k, i) => (i === index ? { ...k, ...patch } : k)) }
      : s,
  )
  emitData({ shots })
}

function removeKeyframe(index: number) {
  const shotId = props.shot?.id
  if (!shotId) return
  const shots = props.modelValue.shots.map(s =>
    s.id === shotId ? { ...s, keyframes: s.keyframes.filter((_, i) => i !== index) } : s,
  )
  emitData({ shots })
}

function detailLabel(key: string): string {
  const map: Record<string, string> = {
    distance: t('scene3d.detailDistance'),
    angle: t('scene3d.detailAngle'),
    focal: t('scene3d.detailFocal'),
    fov_desc: t('scene3d.detailFov'),
    composition: t('scene3d.detailComposition'),
    camera_facing: t('scene3d.detailCameraFacing'),
    subjects: t('scene3d.detailSubjects'),
    orientation: t('scene3d.detailOrientation'),
    light: t('scene3d.detailLight'),
    props: t('scene3d.detailProps'),
    environment: t('scene3d.detailEnvironment'),
    shot_size: t('scene3d.shotSize'),
    camera_move: t('scene3d.cameraMove'),
  }
  return map[key] || key
}
</script>

<style scoped>
.scene-inspector {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow-y: auto;
  gap: 2px;
}

.insp-section {
  padding: 8px 10px;
  border-bottom: 1px solid var(--agnes-border-faint);
}

.insp-section.grow {
  flex: 1;
}

.section-title {
  font-size: 12px;
  color: var(--agnes-text-secondary);
  margin-bottom: 8px;
  letter-spacing: 0.04em;
}

.section-title.sub {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 12px;
}

.field {
  display: block;
  font-size: 12px;
  color: var(--agnes-text-secondary);
  margin: 8px 0 4px;
}

.field-value {
  font-size: 13px;
  color: var(--agnes-text-primary);
}

.field-row {
  display: flex;
  gap: 10px;
}

.field-col {
  flex: 1;
}

.hint {
  font-size: 12px;
  color: var(--agnes-text-faint);
  padding: 4px 0;
}

.keyframe-row {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 6px;
}

.kf-index {
  font-size: 12px;
  color: var(--agnes-text-secondary);
  width: 24px;
}

.prompt-suffix {
  padding: 10px;
  background: var(--agnes-bg-inset);
  border-radius: 6px;
  font-size: 13px;
  line-height: 1.6;
  color: var(--agnes-text-primary);
  word-break: break-all;
}

.details-list {
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px dashed var(--agnes-border);
}

.detail-item {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  font-size: 12px;
  padding: 3px 0;
}

.detail-key { color: var(--agnes-text-secondary); }
.detail-val {
  color: var(--agnes-text-primary);
  text-align: right;
}
</style>
