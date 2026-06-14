/* =====================================================
 * 面板容器
 * - 渲染所有面板（带 z-index 排序）
 * - 视口裁剪（visiblePanels getter 仅渲染可见面板）
 * ===================================================== */

<template>
  <div class="canvas-panels">
    <PanelWrapper
      v-for="panel in sortedPanels"
      :key="panel.id"
      :panel="panel"
    />
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useCanvasStore } from '@/stores/canvas'
import PanelWrapper from '@/components/infinite-canvas/PanelWrapper.vue'

const store = useCanvasStore()

// 按 zIndex 排序
const sortedPanels = computed(() =>
  [...store.panels].sort((a, b) => (a.zIndex || 0) - (b.zIndex || 0)),
)
</script>

<style scoped>
.canvas-panels {
  position: absolute;
  top: 0;
  left: 0;
  width: 0;
  height: 0;
}
</style>
