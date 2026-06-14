/* =====================================================
 * 网格背景
 * - CSS linear-gradient 生成网格
 * - 网格大小跟随缩放级别动态变化
 * ===================================================== */

<template>
  <div
    v-show="showGrid"
    class="canvas-grid"
    :style="gridStyle"
  />
</template>

<script setup>
import { computed } from 'vue'
import { useCanvasStore } from '@/stores/canvas'

const store = useCanvasStore()

// 是否显示网格（可由工具栏开关控制，这里默认显示）
const showGrid = true

// 动态计算网格大小
const gridStyle = computed(() => {
  const gridSize = 40
  const scaledSize = gridSize * store.viewport.zoom

  // 平移偏移（屏幕空间）
  const offsetX = store.viewport.x
  const offsetY = store.viewport.y

  return {
    backgroundImage: `
      linear-gradient(rgba(100, 150, 220, 0.06) 1px, transparent 1px),
      linear-gradient(90deg, rgba(100, 150, 220, 0.06) 1px, transparent 1px)
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
.canvas-grid {
  position: absolute;
  top: 0;
  left: 0;
  pointer-events: none;
}
</style>
