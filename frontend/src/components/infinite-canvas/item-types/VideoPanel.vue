/* =====================================================
 * 视频预览面板
 * - 支持播放控制
 * - 加载状态显示
 * ===================================================== */

<template>
  <div class="video-panel">
    <video
      v-if="videoUrl"
      controls
      preload="metadata"
      :src="videoUrl"
    />
    <div v-else class="video-placeholder">
      <el-icon :size="32"><VideoPlay /></el-icon>
      <p>等待视频...</p>
      <el-button v-if="panel.taskId" size="small" type="primary" link>
        从任务加载
      </el-button>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { VideoPlay } from '@element-plus/icons-vue'

const props = defineProps({
  panel: { type: Object, required: true },
})

const videoUrl = computed(() => {
  if (props.panel.taskId) return null
  return props.panel.content?.videoUrl ?? null
})
</script>

<style scoped>
.video-panel {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 6px;
  overflow: hidden;
}

.video-panel video {
  max-width: 100%;
  max-height: 100%;
  border-radius: 6px;
}

.video-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  color: #6b84aa;
  font-size: 12px;
}
</style>
