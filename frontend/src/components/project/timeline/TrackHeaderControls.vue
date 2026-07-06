<!-- =====================================================
     轨道头部控制按钮 TrackHeaderControls
     - M（Mute）：静音，激活时蓝色
     - L（Lock）：锁定，激活时橙色
     ===================================================== -->

<template>
  <div class="track-header-controls">
    <button
      class="track-btn"
      :class="{ active: muted }"
      :title="muted ? '取消静音' : '静音'"
      @click.stop="$emit('toggle-mute')"
    >M</button>
    <button
      class="track-btn"
      :class="{ active: locked, 'lock-active': locked }"
      :title="locked ? '解锁' : '锁定'"
      @click.stop="$emit('toggle-lock')"
    >L</button>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  muted: boolean
  locked: boolean
}>()

defineEmits<{
  (e: 'toggle-mute'): void
  (e: 'toggle-lock'): void
}>()
</script>

<style scoped>
.track-header-controls {
  display: inline-flex;
  gap: 2px;
  margin-right: 6px;
}

.track-btn {
  width: 18px;
  height: 18px;
  border: 1px solid var(--el-border-color, #3a3d44);
  background: var(--el-fill-color, #2a2d34);
  color: var(--el-text-color-secondary, #888);
  border-radius: 3px;
  font-size: 10px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0;
}

.track-btn:hover {
  border-color: var(--el-color-primary, #4a9eff);
  color: var(--el-color-primary, #4a9eff);
}

.track-btn.active {
  background: var(--el-color-primary, #4a9eff);
  color: #fff;
  border-color: var(--el-color-primary, #4a9eff);
}

.track-btn.lock-active {
  background: var(--el-color-warning, #e6a23c);
  border-color: var(--el-color-warning, #e6a23c);
}
</style>
