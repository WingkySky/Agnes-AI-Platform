/* =====================================================
 * 无限画布页面
 * - 左侧栏：多画布管理
 * - 中间：无限画布主体
 * - 顶部：工具栏
 * ===================================================== */

<template>
  <div class="canvas-view">
    <!-- 左侧栏 -->
    <CanvasSidebar />

    <!-- 主内容区 -->
    <div class="canvas-main">
      <!-- 顶部工具栏 -->
      <CanvasToolbar />

      <!-- 无限画布 -->
      <InfiniteCanvas />
    </div>
  </div>
</template>

<script setup>
import { onMounted, onUnmounted } from 'vue'
import CanvasSidebar from '@/components/infinite-canvas/CanvasSidebar.vue'
import CanvasToolbar from '@/components/infinite-canvas/CanvasToolbar.vue'
import InfiniteCanvas from '@/components/infinite-canvas/InfiniteCanvas.vue'
import { useI18n } from '@/i18n'

const { t } = useI18n()

onMounted(() => {
  document.title = `${t('router.canvas')} · Agnes AI Platform`
})

onUnmounted(() => {
  document.title = 'Agnes AI Platform'
})
</script>

<style scoped>
.canvas-view {
  display: flex;
  height: calc(100vh - 76px); /* 减去顶部栏高度 */
  background: linear-gradient(135deg, #0b0f1a 0%, #101827 50%, #0b0f1a 100%);
  overflow: hidden;
}

.canvas-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}
</style>
