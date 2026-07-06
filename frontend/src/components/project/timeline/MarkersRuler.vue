<!-- =====================================================
     标记旗帜渲染 MarkersRuler
     - 渲染在时间线标尺上方
     - 点击旗帜跳转到标记时间
     - 右键删除标记
     ===================================================== -->

<template>
  <div class="markers-ruler" :style="{ width: totalWidth + 'px' }">
    <div
      v-for="marker in markers"
      :key="marker.id"
      class="marker-flag"
      :style="{
        left: (marker.time * pixelsPerSecond) + 'px',
        '--marker-color': marker.color,
      }"
      :title="marker.name || `标记 @ ${formatTime(marker.time)}`"
      @click="$emit('seek', marker.time)"
      @contextmenu.prevent="$emit('delete', marker.id)"
    >
      <el-icon><Flag /></el-icon>
      <span v-if="marker.name" class="marker-name">{{ marker.name }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Flag } from '@element-plus/icons-vue'
import type { ProjectMarker } from '@/types/project'

defineProps<{
  markers: ProjectMarker[]
  pixelsPerSecond: number
  totalWidth: number
}>()

defineEmits<{
  (e: 'seek', time: number): void
  (e: 'delete', markerId: number): void
}>()

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  const cs = Math.floor((seconds % 1) * 100)
  return `${m}:${s.toString().padStart(2, '0')}.${cs.toString().padStart(2, '0')}`
}
</script>

<style scoped>
.markers-ruler {
  position: relative;
  height: 18px;
  margin-bottom: 2px;
}

.marker-flag {
  position: absolute;
  top: 0;
  transform: translateX(-50%);
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 1px 4px;
  background: var(--marker-color, #4a9eff);
  color: #fff;
  border-radius: 2px;
  font-size: 9px;
  cursor: pointer;
  white-space: nowrap;
  transition: transform 0.15s;
}

.marker-flag:hover {
  transform: translateX(-50%) scale(1.1);
}

.marker-name {
  max-width: 60px;
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>
