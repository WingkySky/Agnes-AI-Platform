/* =====================================================
 * 图片预览面板
 * - 展示 Agnes 生成的图片
 * - 支持点击放大预览
 * ===================================================== */

<template>
  <div class="image-panel">
    <img
      v-if="imageUrl"
      :src="imageUrl"
      alt="预览图片"
      @click="$emit('preview', imageUrl)"
    />
    <div v-else class="image-placeholder">
      <el-icon :size="32"><PictureFilled /></el-icon>
      <p>等待图片...</p>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { PictureFilled } from '@element-plus/icons-vue'

const props = defineProps({
  panel: { type: Object, required: true },
})

const imageUrl = computed(() => {
  // 如果有 task_id，后续从 API 获取
  if (props.panel.taskId) return null
  return props.panel.content?.imageUrl ?? null
})

defineEmits(['preview'])
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
