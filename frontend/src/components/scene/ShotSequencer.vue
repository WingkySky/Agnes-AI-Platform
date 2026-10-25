<!-- =====================================================
     ShotSequencer —— 镜头序列器（工作台底部 dock）
     Shot 卡片时间轴：封面/景别/运镜/时长/机位；新增/删除/排序/
     预演连播（可逐镜头截封面）/批量派生。
     ===================================================== -->
<template>
  <div class="shot-sequencer">
    <div class="seq-header">
      <span class="seq-title">{{ t('scene3d.sequencerTitle') }}</span>
      <span class="seq-total">{{ totalLabel }}</span>
      <el-checkbox v-model="captureCovers" size="small">{{ t('scene3d.captureCovers') }}</el-checkbox>
      <div class="seq-actions">
        <el-button size="small" type="primary" plain :icon="VideoPlay" @click="$emit('play-all', captureCovers)">
          {{ t('scene3d.playAll') }}
        </el-button>
        <el-button size="small" plain :icon="Plus" @click="$emit('add-shot')">
          {{ t('scene3d.addShot') }}
        </el-button>
        <el-button
          size="small"
          plain
          type="success"
          :icon="Promotion"
          :disabled="!modelValue.shots.length"
          @click="$emit('derive')"
        >
          {{ t('scene3d.derive') }}
        </el-button>
      </div>
    </div>

    <div class="seq-cards">
      <div
        v-for="(shot, i) in modelValue.shots"
        :key="shot.id"
        :class="['shot-card', { active: shot.id === modelValue.activeShotId, playing: shot.id === playingShotId }]"
        @click="$emit('select-shot', shot.id)"
        @dblclick="$emit('focus-shot', shot.id)"
      >
        <div class="shot-cover">
          <img v-if="shot.coverUrl" :src="shot.coverUrl" />
          <span v-else class="cover-empty">{{ t('scene3d.size_' + shot.shotSize) }}</span>
        </div>
        <div class="shot-body">
          <div class="shot-name">
            {{ t('scene3d.shotN', { n: i + 1 }) }}
            <span class="shot-camera">{{ cameraName(shot) }}</span>
          </div>
          <div class="shot-meta">
            <el-tag size="small" effect="plain">{{ t('scene3d.size_' + shot.shotSize) }}</el-tag>
            <el-tag size="small" type="warning" effect="plain">{{ t('scene3d.move_' + shot.cameraMove) }}</el-tag>
            <span class="shot-duration">{{ shot.duration }}s · {{ shot.fps }}fps</span>
          </div>
          <div class="shot-meta">
            <span class="kf-count">{{ t('scene3d.keyframeCount', { n: shot.keyframes.length }) }}</span>
          </div>
        </div>
        <div class="shot-ops">
          <el-button size="small" link :icon="ArrowLeft" :disabled="i === 0" @click.stop="moveShot(i, -1)" />
          <el-button size="small" link :icon="ArrowRight" :disabled="i === modelValue.shots.length - 1" @click.stop="moveShot(i, 1)" />
          <el-button size="small" link type="danger" :icon="Close" @click.stop="removeShot(i)" />
        </div>
      </div>
      <div v-if="!modelValue.shots.length" class="seq-empty">
        {{ t('scene3d.noShots') }}
        <el-button size="small" type="primary" link @click="$emit('add-shot')">{{ t('scene3d.addShot') }}</el-button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * ShotSequencer —— 底部序列器。数据编辑经 update:modelValue 上抛；
 * 播放/派生/聚焦经事件上抛，由视图协调视口内核。
 */
import { computed, ref } from 'vue'
import { VideoPlay, Plus, Promotion, ArrowLeft, ArrowRight, Close } from '@element-plus/icons-vue'
import { useI18n } from '@/i18n'
import type { SceneData } from '@/types/scene'

const props = defineProps<{
  modelValue: SceneData
  playingShotId?: string | null
}>()

const emit = defineEmits<{
  'update:modelValue': [value: SceneData]
  'select-shot': [shotId: string]
  'add-shot': []
  'play-all': [captureCovers: boolean]
  'derive': []
  'focus-shot': [shotId: string]
}>()

const { t } = useI18n()
const captureCovers = ref(true)

const totalLabel = computed(() => {
  const total = props.modelValue.shots.reduce((s, x) => s + (x.duration || 0), 0)
  return `${props.modelValue.shots.length} · ${total.toFixed(1)}s`
})

function cameraName(shot: SceneData['shots'][number]): string {
  return props.modelValue.cameras.find(c => c.id === shot.cameraId)?.name || '—'
}

function moveShot(index: number, dir: -1 | 1) {
  const shots = [...props.modelValue.shots]
  const target = index + dir
  if (target < 0 || target >= shots.length) return
  ;[shots[index], shots[target]] = [shots[target], shots[index]]
  emit('update:modelValue', { ...props.modelValue, shots })
}

function removeShot(index: number) {
  const shots = props.modelValue.shots.filter((_, i) => i !== index)
  const activeShotId = shots.some(s => s.id === props.modelValue.activeShotId)
    ? props.modelValue.activeShotId
    : null
  emit('update:modelValue', { ...props.modelValue, shots, activeShotId })
}
</script>

<style scoped>
.shot-sequencer {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}

.seq-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 6px 12px;
  border-bottom: 1px solid var(--agnes-border-faint);
}

.seq-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--agnes-text-primary);
}

.seq-total {
  font-size: 12px;
  color: var(--agnes-text-secondary);
}

.seq-actions {
  margin-left: auto;
  display: flex;
  gap: 4px;
}

.seq-cards {
  flex: 1;
  display: flex;
  gap: 10px;
  padding: 10px 12px;
  overflow-x: auto;
  overflow-y: hidden;
  align-items: stretch;
}

.shot-card {
  display: flex;
  gap: 8px;
  min-width: 220px;
  max-width: 280px;
  padding: 8px;
  border: 1px solid var(--agnes-border);
  border-radius: 8px;
  cursor: pointer;
  background: var(--agnes-bg-base);
  flex-shrink: 0;
}

.shot-card:hover { border-color: var(--el-color-primary-light-5); }
.shot-card.active { border-color: var(--el-color-primary); }
.shot-card.playing { box-shadow: 0 0 0 2px var(--el-color-warning-light-5); }

.shot-cover {
  width: 88px;
  border-radius: 6px;
  overflow: hidden;
  flex-shrink: 0;
  background: var(--agnes-bg-inset);
  display: flex;
  align-items: center;
  justify-content: center;
}

.shot-cover img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.cover-empty {
  font-size: 11px;
  color: var(--agnes-text-faint);
  padding: 4px;
  text-align: center;
}

.shot-body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.shot-name {
  font-size: 13px;
  color: var(--agnes-text-primary);
  display: flex;
  align-items: center;
  gap: 6px;
  overflow: hidden;
  white-space: nowrap;
}

.shot-camera {
  font-size: 11px;
  color: var(--agnes-text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
}

.shot-meta {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-wrap: wrap;
}

.shot-duration,
.kf-count {
  font-size: 11px;
  color: var(--agnes-text-faint);
}

.shot-ops {
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 0;
}

.shot-ops .el-button + .el-button { margin-left: 0; }

.seq-empty {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: var(--agnes-text-faint);
}
</style>
