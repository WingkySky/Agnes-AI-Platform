<!-- =====================================================
     CanvasContextMenu 画布右键上下文菜单
     - 固定定位在右键位置（由父组件传入 x, y）
     - 节点右键：成组（多选）、移出分组、复制、删除
     - 分组右键：解散组、删除组与节点
     - 连线右键：删除
     - min-w-44（176px）、rounded-xl（12px）、边框 + 阴影 + backdrop-blur
     - 点击外部或菜单项后关闭
     ===================================================== -->

<template>
  <div
    class="canvas-context-menu"
    :style="menuStyle"
    @pointerdown.stop
    @click.stop
  >
    <!-- 节点右键：成组（多选）/ 移出分组 / 复制 / 删除 -->
    <template v-if="targetType === 'node'">
      <button
        v-if="selectionCount > 1"
        type="button"
        class="menu-item"
        :style="itemStyle"
        @click="handleEmit('group-create')"
      >
        <Boxes :size="16" />
        <span>{{ t('canvas.group.create') }}</span>
      </button>
      <button
        v-if="canRemoveFromGroup"
        type="button"
        class="menu-item"
        :style="itemStyle"
        @click="handleEmit('group-remove-panel')"
      >
        <Ungroup :size="16" />
        <span>{{ t('canvas.group.removeFromGroup') }}</span>
      </button>
      <button
        type="button"
        class="menu-item"
        :style="itemStyle"
        @click="handleEmit('duplicate')"
      >
        <Plus :size="16" />
        <span>{{ t('canvas.contextMenu.duplicate') }}</span>
      </button>
      <button
        type="button"
        class="menu-item is-danger"
        :style="dangerItemStyle"
        @click="handleEmit('delete')"
      >
        <Trash2 :size="16" />
        <span>{{ t('canvas.contextMenu.delete') }}</span>
      </button>
    </template>

    <!-- 分组右键：解散组（保留节点）/ 删除组与节点 -->
    <template v-else-if="targetType === 'group'">
      <button
        type="button"
        class="menu-item"
        :style="itemStyle"
        @click="handleEmit('group-dissolve')"
      >
        <Ungroup :size="16" />
        <span>{{ t('canvas.group.ungroup') }}</span>
      </button>
      <button
        type="button"
        class="menu-item is-danger"
        :style="dangerItemStyle"
        @click="handleEmit('group-delete-with-nodes')"
      >
        <Trash2 :size="16" />
        <span>{{ t('canvas.group.deleteGroupWithNodes') }}</span>
      </button>
    </template>

    <!-- 连线右键：删除 -->
    <template v-else-if="targetType === 'connection'">
      <button
        type="button"
        class="menu-item is-danger"
        :style="dangerItemStyle"
        @click="handleEmit('delete')"
      >
        <Trash2 :size="16" />
        <span>{{ t('canvas.contextMenu.delete') }}</span>
      </button>
    </template>
  </div>
</template>

<script setup lang="ts">
/* =====================================================
 * CanvasContextMenu 画布右键上下文菜单
 *
 * 数据约定：
 *   - x, y：菜单显示位置（屏幕坐标）
 *   - targetType：'node' | 'connection' | 'group'
 *   - selectionCount：多选节点数（>1 显示"成组"）
 *   - canRemoveFromGroup：目标节点已在分组中（显示"移出分组"）
 *   - theme：主题 token 对象
 * ===================================================== */

import { onMounted, onUnmounted, computed } from 'vue'
import { Boxes, Plus, Trash2, Ungroup } from 'lucide-vue-next'
import { useI18n } from '@/i18n'

const { t } = useI18n()

/* ---------- Props 定义 ---------- */
const props = defineProps({
  x: { type: Number, required: true },
  y: { type: Number, required: true },
  targetType: { type: String, required: true }, // 'node' | 'connection' | 'group'
  theme: { type: Object, required: true },
  // 多选节点数（>1 时节点菜单显示"成组"）
  selectionCount: { type: Number, default: 1 },
  // 目标节点是否属于某个分组（显示"移出分组"）
  canRemoveFromGroup: { type: Boolean, default: false },
})

/* ---------- Emits 定义 ---------- */
const emit = defineEmits([
  'duplicate',
  'delete',
  'group-create',
  'group-remove-panel',
  'group-dissolve',
  'group-delete-with-nodes',
  'close',
])

/* ---------- 菜单容器样式 ---------- */

/** 菜单容器样式：定位 + 背景 + 边框 + hover 变量 */
const menuStyle = computed(() => ({
  left: props.x + 'px',
  top: props.y + 'px',
  background: props.theme.toolbar.panel,
  borderColor: props.theme.toolbar.border,
  color: props.theme.node.text,
  '--hover-bg': props.theme.toolbar.itemHover,
}))

/* ---------- 菜单项样式 ---------- */

/** 普通菜单项样式 */
const itemStyle = computed(() => ({}))

/** 危险菜单项样式（红色） */
const dangerItemStyle = computed(() => ({
  color: 'var(--agnes-error)',
}))

/* ---------- 菜单项点击处理 ---------- */

/** 触发菜单动作并关闭菜单 */
function handleEmit(action: 'duplicate' | 'delete' | 'group-create' | 'group-remove-panel' | 'group-dissolve' | 'group-delete-with-nodes') {
  emit(action)
  emit('close')
}

/* ---------- 外部点击 / Esc 关闭菜单 ---------- */

/** 外部点击：关闭菜单 */
function handleOutsideClick(event: PointerEvent) {
  const menu = document.querySelector('.canvas-context-menu')
  if (menu && !menu.contains(event.target as Node)) {
    emit('close')
  }
}

/** Esc 键：关闭菜单 */
function handleEsc(event: KeyboardEvent) {
  if (event.key === 'Escape') {
    emit('close')
  }
}

onMounted(() => {
  window.addEventListener('pointerdown', handleOutsideClick)
  window.addEventListener('keydown', handleEsc)
})

onUnmounted(() => {
  window.removeEventListener('pointerdown', handleOutsideClick)
  window.removeEventListener('keydown', handleEsc)
})
</script>

<style scoped>
/* ===== 菜单容器：min-w-44（176px）+ rounded-xl（12px）+ 边框 + 阴影 + backdrop-blur ===== */
.canvas-context-menu {
  position: fixed;
  z-index: 80;
  min-width: 176px;
  padding: 4px 0;
  border-radius: 12px;
  border: 1px solid;
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.2);
  backdrop-filter: blur(12px);
  overflow: hidden;
}

/* ===== 菜单项 ===== */
.menu-item {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 8px 12px;
  border: none;
  background: transparent;
  font-size: 12px;
  text-align: left;
  cursor: pointer;
  transition: background-color 150ms ease, opacity 150ms ease;
}

.menu-item:hover {
  background-color: var(--hover-bg, var(--agnes-bg-hover));
}

.menu-item.is-danger {
  color: var(--agnes-error);
}
</style>
