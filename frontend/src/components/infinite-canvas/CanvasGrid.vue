/* =====================================================
 * 网格背景
 * - 三种模式：dot（点阵，默认） / grid（网格线） / blank（空白）
 * - 网格大小 = store.gridSize（由用户在工具栏的吸附开关控制）
 * - 视觉间距 = store.gridSize * store.viewport.zoom，跟随缩放自适应
 * - 由 store.backgroundMode 控制切换
 * ===================================================== */

<template>
  <!-- 空白模式：保留一个全屏透明层，用于保持事件层与缩放计算一致 -->
  <div v-if="mode === 'blank'" class="canvas-bg canvas-bg--blank" />

  <!-- 点阵模式：默认背景 -->
  <div
    v-else-if="mode === 'dot'"
    class="canvas-bg canvas-bg--dot"
    :style="dotStyle"
  />

  <!-- 网格线模式：原 linear-gradient 网格 -->
  <div
    v-else
    class="canvas-bg canvas-bg--grid"
    :style="gridStyle"
  />
</template>

<script setup>
import { computed } from 'vue'
import { useCanvasStore } from '@/stores/canvas'

const store = useCanvasStore()

// 当前背景模式（'dot' | 'grid' | 'blank'）
const mode = computed(() => store.backgroundMode)

// 网格基础大小（跟随 store.gridSize，可在工具栏切换后实时变化）
const baseSize = computed(() => store.gridSize)

// 点阵样式：使用 radial-gradient 生成 1px 圆点 + baseSize 间距
const dotStyle = computed(() => {
  const scaledSize = baseSize.value * store.viewport.zoom

  // 平移偏移（屏幕空间）
  const offsetX = store.viewport.x
  const offsetY = store.viewport.y

  return {
    backgroundImage: `radial-gradient(circle, var(--canvas-grid-dot) 1px, transparent 1px)`,
    backgroundSize: `${scaledSize}px ${scaledSize}px`,
    backgroundPosition: `${offsetX}px ${offsetY}px`,
    position: 'absolute',
    width: '100000px',
    height: '100000px',
    transform: 'translate(-50000px, -50000px)',
    pointerEvents: 'none',
  }
})

// 动态计算网格大小（与点阵共用 baseSize，背景模式切换时风格统一）
const gridStyle = computed(() => {
  const scaledSize = baseSize.value * store.viewport.zoom

  // 平移偏移（屏幕空间）
  const offsetX = store.viewport.x
  const offsetY = store.viewport.y

  return {
    backgroundImage: `
      linear-gradient(var(--canvas-grid-line) 1px, transparent 1px),
      linear-gradient(90deg, var(--canvas-grid-line) 1px, transparent 1px)
    `,
    backgroundSize: `${scaledSize}px ${scaledSize}px`,
    backgroundPosition: `${offsetX}px ${offsetY}px`,
    position: 'absolute',
    width: '100000px',
    height: '100000px',
    transform: 'translate(-50000px, -50000px)',
    pointerEvents: 'none',
  }
})
</script>

<style scoped>
.canvas-bg {
  position: absolute;
  top: 0;
  left: 0;
  pointer-events: none;
}

/* 空白模式：仅作为事件穿透层，无任何视觉表现 */
.canvas-bg--blank {
  background: transparent;
}
</style>
