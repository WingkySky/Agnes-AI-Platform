<!-- =====================================================
     图片预览面板
     - 展示 Agnes 生成的图片
     - 支持点击放大预览（Element Plus el-image viewer）
     - 任务 7：当父节点自身无图、且有 batchChildIds 时，回退到第一张子图
     ===================================================== -->

<template>
  <div class="image-panel">
    <img
      v-if="imageUrl"
      :src="imageUrl"
      alt="预览图片"
      @click="handlePreview"
    />
    <div v-else class="image-placeholder">
      <el-icon :size="32"><PictureFilled /></el-icon>
      <p>等待图片...</p>
    </div>

    <!-- 点击图片时弹出 Element Plus 图片预览器（带遮罩 + 缩放/旋转/翻页） -->
    <el-image-viewer
      v-if="previewVisible"
      :url-list="[imageUrl]"
      @close="previewVisible = false"
    />
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { PictureFilled } from '@element-plus/icons-vue'
import { useCanvasStore } from '@/stores/canvas'

const props = defineProps({
  panel: { type: Object, required: true },
})
const store = useCanvasStore()

/** 图片 URL：父节点自身 imageUrl > 第一张批量子图 > null */
const imageUrl = computed(() => {
  if (props.panel.task_id || props.panel.taskId) return null
  const own = props.panel.content?.imageUrl
  if (own) return own
  // 任务 7：父图无图时回退到第一张子图
  const children = store.batchChildPanels?.(props.panel.id) ?? []
  const first = children[0]
  return first?.content?.imageUrl ?? first?.content?.image ?? null
})

const previewVisible = ref(false)

/** 点击图片 → 弹出全屏预览（前提是图片已经加载完成） */
function handlePreview() {
  if (imageUrl.value) {
    previewVisible.value = true
  }
}
</script>

<style scoped>
.image-panel {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  border-radius: 6px;
  overflow: hidden;
}

.image-panel img {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
  border-radius: 6px;
  transition: transform 0.2s ease;
}

.image-panel img:hover {
  transform: scale(1.02);
}

.image-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  color: #6b84aa;
  font-size: 12px;
}
</style>
