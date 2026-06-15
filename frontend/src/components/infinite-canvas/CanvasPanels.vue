/* =====================================================
 * 面板容器
 * - 使用 visiblePanels getter 仅渲染可见面板
 * - 按 z-index 排序
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

// 仅渲染视口内的可见面板（性能优化）
const visiblePanels = computed(() => store.visiblePanels)

// 按 zIndex 排序
const sortedPanels = computed(() =>
  [...visiblePanels.value].sort((a, b) => (a.zIndex || 0) - (b.zIndex || 0)),
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
