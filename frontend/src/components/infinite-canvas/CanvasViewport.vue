/* =====================================================
 * 变换容器
 * - CSS transform 应用平移/缩放
 * - will-change 性能优化
 * ===================================================== */

<template>
  <div
    class="canvas-viewport"
    :style="{
      transform: `translate(${store.viewport.x}px, ${store.viewport.y}px) scale(${store.viewport.zoom})`,
      transformOrigin: '0 0',
    }"
  >
    <slot />
  </div>
</template>

<script setup>
import { useCanvasStore } from '@/stores/canvas'

const store = useCanvasStore()
</script>

<style scoped>
.canvas-viewport {
  width: 100%;
  height: 100%;
  position: relative;
  will-change: transform;
  transform-style: preserve-3d;
}
</style>
