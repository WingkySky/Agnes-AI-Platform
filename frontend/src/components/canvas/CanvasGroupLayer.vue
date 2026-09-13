<!-- =====================================================
     CanvasGroupLayer 画布分组层组件（每组一个实例）
     - 展开态：半透明底 + 彩色边框包住成员（边界由成员实时包络）
     - 折叠态：标题胶囊（成员隐藏由父组件负责，外部连线锚到胶囊由连线层负责）
     - 标题栏：折叠箭头 / 组名（双击改名）/ 成员数 / 状态点
     - hover 操作：引用整组（+，选图片或视频）/ 整组重跑 / 锁定 / 换色 / 删除组与节点
     ===================================================== -->

<template>
  <div
    class="group-box"
    :class="{ 'is-collapsed': group.collapsed, 'is-selected': selected }"
    :style="boxStyle"
    :data-group-id="group.id"
    @pointerdown.stop="handleBoxPointerDown"
    @contextmenu.prevent.stop="emit('context-menu', $event)"
  >
    <!-- 标题栏（展开态横贯顶部；折叠态即胶囊本体） -->
    <div class="group-header" :style="headerStyle">
      <button
        class="g-btn"
        :title="group.collapsed ? t('canvas.group.expand') : t('canvas.group.collapse')"
        @click.stop="emit('toggle-collapse')"
      >
        <ChevronRight v-if="group.collapsed" :size="14" />
        <ChevronDown v-else :size="14" />
      </button>
      <input
        v-if="editing"
        ref="nameInputRef"
        v-model="nameDraft"
        class="g-name-input"
        maxlength="30"
        @pointerdown.stop
        @keydown.enter="saveName"
        @keydown.escape="cancelEdit"
        @blur="saveName"
      />
      <span v-else class="g-name" :title="group.name" @dblclick.stop="startEdit">{{ group.name }}</span>
      <span class="g-count">{{ group.panel_ids.length }}</span>
      <span class="g-status" :class="'st-' + status" :title="t('canvas.group.status.' + status)" />

      <div class="g-actions" @pointerdown.stop>
        <!-- 引用整组：弹出类型选择 -->
        <div v-if="refMenuOpen" class="g-ref-menu" :style="refMenuStyle">
          <button @click.stop="pickReference('image')">{{ t('canvas.createNodeImage') }}</button>
          <button @click.stop="pickReference('video')">{{ t('canvas.createNodeVideo') }}</button>
        </div>
        <button class="g-btn" :title="t('canvas.group.reference')" @click.stop="refMenuOpen = !refMenuOpen">
          <Plus :size="14" />
        </button>
        <button class="g-btn" :title="t('canvas.group.rerun')" @click.stop="emit('rerun')">
          <RotateCcw :size="14" />
        </button>
        <button class="g-btn" :title="group.locked ? t('canvas.group.unlock') : t('canvas.group.lock')" @click.stop="emit('toggle-lock')">
          <Lock v-if="group.locked" :size="14" />
          <Unlock v-else :size="14" />
        </button>
        <button
          class="g-btn g-color"
          :title="t('canvas.group.colorTitle')"
          :style="{ background: group.color }"
          @click.stop="emit('cycle-color')"
        />
        <button class="g-btn is-danger" :title="t('canvas.group.deleteGroupWithNodes')" @click.stop="emit('delete-group')">
          <Trash2 :size="14" />
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { ChevronDown, ChevronRight, Lock, Plus, RotateCcw, Trash2, Unlock } from 'lucide-vue-next'
import { useI18n } from '@/i18n'
import type { CanvasGroup, CanvasPanel } from '@/stores/canvas'
import { GROUP_PILL, calculateGroupBounds, groupStatus } from '@/lib/canvas-groups'

const { t } = useI18n()

const props = defineProps({
  group: { type: Object as () => CanvasGroup, required: true },
  panels: { type: Array as () => CanvasPanel[], required: true },
  selected: { type: Boolean, default: false },
})

const emit = defineEmits([
  'toggle-collapse',
  'toggle-lock',
  'cycle-color',
  'rename',
  'reference',
  'rerun',
  'delete-group',
  'drag-start',
  'context-menu',
])

// ---------- 几何 ----------
const boxStyle = computed(() => {
  const bounds = calculateGroupBounds(props.group, props.panels)
  if (!bounds) return { display: 'none' }
  const base = {
    left: bounds.left + 'px',
    top: bounds.top + 'px',
    borderColor: props.group.color,
  }
  if (props.group.collapsed) {
    return { ...base, width: GROUP_PILL.width + 'px', height: GROUP_PILL.height + 'px' }
  }
  return {
    ...base,
    width: bounds.width + 'px',
    height: bounds.height + 'px',
    background: props.group.color + '12',
  }
})

const headerStyle = computed(() => ({ '--group-color': props.group.color }))

// ---------- 状态点 ----------
const status = computed(() => groupStatus(props.group, props.panels))

// ---------- 改名 ----------
const editing = ref(false)
const nameDraft = ref('')
const nameInputRef = ref<HTMLInputElement | null>(null)

function startEdit() {
  nameDraft.value = props.group.name
  editing.value = true
  nextTick(() => nameInputRef.value?.select())
}

function saveName() {
  if (!editing.value) return
  editing.value = false
  const name = nameDraft.value.trim()
  if (name && name !== props.group.name) emit('rename', name)
}

function cancelEdit() {
  editing.value = false
}

// ---------- 引用类型选择 ----------
const refMenuOpen = ref(false)

function pickReference(type: 'image' | 'video') {
  refMenuOpen.value = false
  emit('reference', type)
}

const refMenuStyle = computed(() => ({ borderColor: props.group.color }))

// 点击外部关闭引用菜单
function handleGlobalPointerDown(event: PointerEvent) {
  if (refMenuOpen.value && !(event.target instanceof Element && event.target.closest('.g-ref-menu, .g-btn'))) {
    refMenuOpen.value = false
  }
}

onMounted(() => window.addEventListener('pointerdown', handleGlobalPointerDown))
onBeforeUnmount(() => window.removeEventListener('pointerdown', handleGlobalPointerDown))

// ---------- 整组拖动：按下组框空白处（标题栏/边框区域）触发 ----------
function handleBoxPointerDown(event: PointerEvent) {
  if (event.button !== 0) return
  // 折叠态整块可拖；展开态点标题栏/边框空白（节点自身事件不会冒泡到这）
  emit('drag-start', { event })
}
</script>

<style scoped>
.group-box {
  position: absolute;
  z-index: 0;
  border: 2px solid;
  border-radius: 14px;
  pointer-events: auto;
  transition: box-shadow 0.2s ease, background 0.2s ease;
}

.group-box.is-selected {
  box-shadow: 0 0 0 2px var(--group-color), 0 0 24px color-mix(in srgb, var(--group-color) 35%, transparent);
}

/* 折叠态：胶囊 */
.group-box.is-collapsed {
  border-radius: 18px;
  background: color-mix(in srgb, var(--group-color) 14%, transparent);
}

.group-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 8px;
  border-radius: 12px 12px 0 0;
  font-size: 12px;
  cursor: grab;
  min-width: 0;
}

.group-box.is-collapsed .group-header {
  border-radius: 16px;
  height: 100%;
}

.g-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: 600;
  color: var(--group-color);
  cursor: text;
}

.g-name-input {
  flex: 1;
  min-width: 0;
  border: none;
  border-radius: 4px;
  padding: 1px 4px;
  font-size: 12px;
  background: rgba(255, 255, 255, 0.9);
  color: #303133;
  outline: none;
}

.g-count {
  flex-shrink: 0;
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 8px;
  background: color-mix(in srgb, var(--group-color) 22%, transparent);
  color: var(--group-color);
}

.g-status {
  flex-shrink: 0;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.45);
}

.g-status.st-running { background: #e6a23c; animation: g-pulse 1.2s ease-in-out infinite; }
.g-status.st-failed { background: #f56c6c; }
.g-status.st-success { background: #67c23a; }

@keyframes g-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.35; }
}

.g-actions {
  display: none;
  align-items: center;
  gap: 2px;
  flex-shrink: 0;
}

.group-box:hover .g-actions {
  display: flex;
}

.g-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border: none;
  border-radius: 5px;
  background: color-mix(in srgb, var(--group-color) 18%, transparent);
  color: var(--group-color);
  cursor: pointer;
  padding: 0;
  transition: background 0.15s ease;
}

.g-btn:hover {
  background: color-mix(in srgb, var(--group-color) 36%, transparent);
}

.g-btn.is-danger:hover {
  background: var(--agnes-error, #f56c6c);
}

.g-color {
  border: 1.5px solid rgba(255, 255, 255, 0.7);
}

/* 引用类型选择小菜单 */
.g-ref-menu {
  position: absolute;
  top: 30px;
  right: 0;
  z-index: 5;
  display: flex;
  flex-direction: column;
  min-width: 110px;
  padding: 4px 0;
  background: var(--agnes-bg-color, #1f1f1f);
  border: 1px solid;
  border-radius: 8px;
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.25);
  overflow: hidden;
}

.g-ref-menu button {
  border: none;
  background: transparent;
  color: var(--agnes-text-primary, #eee);
  font-size: 12px;
  text-align: left;
  padding: 7px 12px;
  cursor: pointer;
}

.g-ref-menu button:hover {
  background: var(--agnes-bg-hover, rgba(255, 255, 255, 0.08));
}
</style>
