<!-- =====================================================
     CanvasContextMenu 画布右键上下文菜单
     - 1:1 复刻参考项目 infinite-canvas 的 canvas-context-menu
     - 固定定位在右键位置（由父组件传入 x, y）
     - 节点右键：复制、删除
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
    <!-- 节点右键：复制 + 删除 -->
    <template v-if="targetType === 'node'">
      <button
        type="button"
        class="menu-item"
        :style="itemStyle"
        @click="handleDuplicate"
      >
        <Plus :size="16" />
        <span>复制</span>
      </button>
      <button
        type="button"
        class="menu-item is-danger"
        :style="dangerItemStyle"
        @click="handleDelete"
      >
        <Trash2 :size="16" />
        <span>删除</span>
      </button>
    </template>

    <!-- 连线右键：删除 -->
    <template v-else-if="targetType === 'connection'">
      <button
        type="button"
        class="menu-item is-danger"
        :style="dangerItemStyle"
        @click="handleDelete"
      >
        <Trash2 :size="16" />
        <span>删除</span>
      </button>
    </template>
  </div>
</template>

<script setup>
/* =====================================================
 * CanvasContextMenu 画布右键上下文菜单
 * 1:1 复刻参考项目 infinite-canvas 的右键菜单设计
 *
 * 数据约定：
 *   - x, y：菜单显示位置（屏幕坐标）
 *   - targetType：'node' | 'connection'
 *   - theme：主题 token 对象
 * ===================================================== */

import { onMounted, onUnmounted, computed } from 'vue'
import { Plus, Trash2 } from 'lucide-vue-next'

/* ---------- Props 定义 ---------- */
const props = defineProps({
  x: { type: Number, required: true },
  y: { type: Number, required: true },
  targetType: { type: String, required: true }, // 'node' | 'connection'
  theme: { type: Object, required: true },
})

/* ---------- Emits 定义 ---------- */
const emit = defineEmits(['duplicate', 'delete', 'close'])

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
  color: '#f87171',
}))

/* ---------- 菜单项点击处理 ---------- */

/** 复制：触发 duplicate 并关闭菜单 */
function handleDuplicate() {
  emit('duplicate')
  emit('close')
}

/** 删除：触发 delete 并关闭菜单 */
function handleDelete() {
  emit('delete')
  emit('close')
}

/* ---------- 外部点击 / Esc 关闭菜单 ---------- */

/** 外部点击：关闭菜单 */
function handleOutsideClick(event) {
  const menu = document.querySelector('.canvas-context-menu')
  if (menu && !menu.contains(event.target)) {
    emit('close')
  }
}

/** Esc 键：关闭菜单 */
function handleEsc(event) {
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
  background-color: var(--hover-bg, #e7e5df);
}

.menu-item.is-danger {
  color: #f87171;
}
</style>
