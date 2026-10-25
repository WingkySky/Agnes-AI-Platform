<!-- =====================================================
     SceneTreePanel —— 场景树 + 我的场景库（工作台左栏）
     按类型分组平铺（机位/主体/灯光/道具），点击选中联动视口，
     眼睛=可见、锁=锁定（不可选中/删除）；下半为场景库列表。
     ===================================================== -->
<template>
  <div class="scene-tree-panel">
    <div class="tree-section">
      <div class="section-title">{{ t('scene3d.treeTitle') }}</div>

      <div v-for="group in groups" :key="group.type" class="tree-group">
        <div class="group-label">{{ group.label }}</div>
        <div
          v-for="(item, i) in group.items"
          :key="item.id"
          :class="['tree-item', { selected: selected?.type === group.type && selected?.index === i, dim: item.visible === false }]"
          @click="$emit('select', { type: group.type, index: i })"
        >
          <el-icon v-if="group.type === 'camera' && item.active" class="active-mark"><Star /></el-icon>
          <span class="item-name" :title="item.locked ? t('scene3d.lockedHint') : ''">
            {{ item.name }}
          </span>
          <span class="item-ops">
            <el-icon
              :class="['op', { off: item.visible === false }]"
              :title="item.visible === false ? t('scene3d.showItem') : t('scene3d.hideItem')"
              @click.stop="toggleVisible(group.type, i)"
            >
              <View v-if="item.visible !== false" />
              <Hide v-else />
            </el-icon>
            <el-icon
              :class="['op', { on: item.locked }]"
              :title="item.locked ? t('scene3d.unlockItem') : t('scene3d.lockItem')"
              @click.stop="toggleLocked(group.type, i)"
            >
              <Lock v-if="item.locked" />
              <Unlock v-else />
            </el-icon>
          </span>
        </div>
        <div v-if="!group.items.length" class="group-empty">—</div>
      </div>
    </div>

    <div class="scenes-section">
      <div class="section-title row">
        {{ t('scene3d.treeMyScenes') }}
        <el-input
          :model-value="search"
          size="small"
          style="width: 120px"
          clearable
          :placeholder="t('common.search')"
          @update:model-value="$emit('update:search', $event)"
          @change="$emit('search-scenes')"
          @clear="$emit('search-scenes')"
        />
      </div>
      <div v-loading="loading" class="scene-list">
        <div
          v-for="s in scenes"
          :key="s.id"
          :class="['scene-item', { active: s.id === currentSceneId }]"
          @click="$emit('select-scene', s)"
        >
          <img v-if="s.cover_url" :src="s.cover_url" class="scene-item-cover" />
          <div v-else class="scene-item-cover placeholder"><el-icon><Film /></el-icon></div>
          <div class="scene-item-body">
            <div class="scene-item-name">
              {{ s.name }}
              <el-tag v-if="s.is_public" size="small" type="success">{{ t('scene3d.publicTag') }}</el-tag>
            </div>
            <div class="scene-item-desc">{{ s.description || '—' }}</div>
          </div>
        </div>
        <el-empty v-if="!loading && !scenes.length" :description="t('common.empty')" :image-size="48" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * SceneTreePanel —— 左栏：场景树（类型分组）+ 场景库。
 * 数据编辑经 update:modelValue 上抛，选中/加载场景经事件上抛，组件不自持业务状态。
 */
import { computed } from 'vue'
import { View, Hide, Lock, Unlock, Star, Film } from '@element-plus/icons-vue'
import { useI18n } from '@/i18n'
import type { Scene3D, SceneData } from '@/types/scene'

type TreeType = 'camera' | 'subject' | 'light' | 'prop'
interface TreeItem { id: string; name: string; active?: boolean; visible?: boolean; locked?: boolean }

const props = defineProps<{
  modelValue: SceneData
  selected?: { type: TreeType; index: number } | null
  scenes: Scene3D[]
  currentSceneId?: number | null
  loading?: boolean
  search?: string
}>()

const emit = defineEmits<{
  'update:modelValue': [value: SceneData]
  select: [payload: { type: TreeType; index: number }]
  'select-scene': [scene: Scene3D]
  'update:search': [value: string]
  'search-scenes': []
}>()

const { t } = useI18n()

const groups = computed<{ type: TreeType; label: string; items: TreeItem[] }[]>(() => {
  const d = props.modelValue
  return [
    {
      type: 'camera',
      label: t('scene3d.targetCamera'),
      items: (d.cameras || []).map(c => ({ id: c.id, name: c.name, active: c.active, visible: true, locked: c.locked })),
    },
    {
      type: 'subject',
      label: t('scene3d.targetSubject'),
      items: (d.subjects || []).map(s => ({ id: s.id, name: s.label, visible: s.visible, locked: s.locked })),
    },
    {
      type: 'light',
      label: t('scene3d.targetLight'),
      items: (d.lights || []).map(l => ({ id: l.id, name: `${t('scene3d.targetLight')} ${l.id.slice(0, 4)}`, visible: l.visible, locked: l.locked })),
    },
    {
      type: 'prop',
      label: t('scene3d.targetProp'),
      items: (d.props || []).map(p => ({ id: p.id, name: p.label, visible: p.visible, locked: p.locked })),
    },
  ]
})

function patchItem(type: TreeType, index: number, patch: Record<string, unknown>) {
  const d = props.modelValue
  const key = type === 'camera' ? 'cameras' : type === 'subject' ? 'subjects' : type === 'light' ? 'lights' : 'props'
  const list = (d[key] as Record<string, any>[]).map((it, i) => (i === index ? { ...it, ...patch } : it))
  emit('update:modelValue', { ...d, [key]: list } as SceneData)
}

function toggleVisible(type: TreeType, index: number) {
  const key = type === 'camera' ? 'cameras' : type === 'subject' ? 'subjects' : type === 'light' ? 'lights' : 'props'
  const cur = (props.modelValue[key] as { visible?: boolean }[])[index]
  patchItem(type, index, { visible: !(cur?.visible !== false) })
}

function toggleLocked(type: TreeType, index: number) {
  const key = type === 'camera' ? 'cameras' : type === 'subject' ? 'subjects' : type === 'light' ? 'lights' : 'props'
  const cur = (props.modelValue[key] as { locked?: boolean }[])[index]
  patchItem(type, index, { locked: !cur?.locked })
}
</script>

<style scoped>
.scene-tree-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}

.tree-section {
  flex: 1;
  overflow-y: auto;
  min-height: 120px;
  padding-bottom: 8px;
}

.scenes-section {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 140px;
  border-top: 1px solid var(--agnes-border-faint);
}

.section-title {
  font-size: 12px;
  color: var(--agnes-text-secondary);
  padding: 8px 10px 6px;
  letter-spacing: 0.04em;
}

.section-title.row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.tree-group {
  margin-bottom: 6px;
}

.group-label {
  font-size: 11px;
  color: var(--agnes-text-faint);
  padding: 4px 10px;
}

.tree-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  font-size: 13px;
  cursor: pointer;
  border-radius: 4px;
  color: var(--agnes-text-primary);
}

.tree-item:hover { background: var(--agnes-bg-hover); }
.tree-item.selected { background: var(--agnes-nav-hover-bg); }
.tree-item.dim .item-name { opacity: 0.45; }

.active-mark { color: var(--el-color-warning); font-size: 12px; }

.item-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.item-ops {
  display: none;
  gap: 6px;
}

.tree-item:hover .item-ops { display: inline-flex; }

.op { font-size: 14px; color: var(--agnes-text-secondary); }
.op:hover { color: var(--agnes-text-primary); }
.op.off { color: var(--agnes-text-faint); }
.op.on { color: var(--el-color-warning); }

.group-empty {
  padding: 2px 10px;
  font-size: 12px;
  color: var(--agnes-text-faint);
}

.scene-list {
  flex: 1;
  overflow-y: auto;
  padding: 0 6px 6px;
}

.scene-item {
  padding: 6px 8px;
  border-radius: 6px;
  cursor: pointer;
  display: flex;
  gap: 8px;
  align-items: flex-start;
}

.scene-item:hover { background: var(--agnes-bg-hover); }
.scene-item.active { background: var(--agnes-nav-hover-bg); }

.scene-item-cover {
  width: 56px;
  height: 34px;
  object-fit: cover;
  border-radius: 4px;
  flex-shrink: 0;
  border: 1px solid var(--agnes-border-light, rgba(255, 255, 255, 0.12));
}

.scene-item-cover.placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--agnes-text-faint);
  background: var(--agnes-bg-inset);
}

.scene-item-body { flex: 1; min-width: 0; }

.scene-item-name {
  font-size: 13px;
  color: var(--agnes-text-primary);
  display: flex;
  align-items: center;
  gap: 6px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.scene-item-desc {
  font-size: 12px;
  color: var(--agnes-text-secondary);
  margin-top: 2px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
