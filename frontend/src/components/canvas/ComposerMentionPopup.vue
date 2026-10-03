<!-- =====================================================
  ComposerMentionPopup @ 提及候选弹窗
  - Composer（媒体节点就地生成）与 GenerationQuickPanel（快捷生成弹窗）共用
  - fixed 定位 + Teleport 到 body，坐标由 useNodeMention 计算后传入
===================================================== -->
<template>
  <Teleport to="body">
    <div
      v-if="visible && candidates.length > 0"
      class="mention-popup"
      :style="{ top: position.top + 'px', left: position.left + 'px' }"
      @mousedown="emit('shield-blur', $event)"
    >
      <div
        v-for="(candidate, idx) in candidates"
        :key="candidate.id"
        class="mention-item"
        :class="{ active: idx === activeIndex }"
        @mousedown.prevent.stop="emit('select', candidate)"
      >
        <span class="mention-index">{{ candidate.index }}</span>
        <span class="mention-name">{{ candidate.label }}</span>
        <span v-if="candidate.preview" class="mention-preview">{{ candidate.preview }}</span>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import type { MentionPanel } from '@/composables/useNodeMention'

defineProps<{
  visible: boolean
  candidates: MentionPanel[]
  activeIndex: number
  position: { top: number; left: number }
}>()

const emit = defineEmits<{
  (e: 'select', candidate: MentionPanel): void
  (e: 'shield-blur', event: MouseEvent): void
}>()
</script>

<style scoped>
.mention-popup {
  position: fixed;
  z-index: 99999;
  min-width: 220px;
  max-width: 320px;
  max-height: 260px;
  overflow-y: auto;
  background: rgba(15, 22, 38, 0.98);
  border: 1px solid rgba(120, 170, 230, 0.25);
  border-radius: 10px;
  padding: 4px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
}
.mention-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  border-radius: 6px;
  font-size: 12px;
  color: #e8eef7;
  cursor: pointer;
}
.mention-item:hover,
.mention-item.active {
  background: rgba(107, 156, 255, 0.15);
}
.mention-index {
  color: #8ba3c9;
  font-size: 11px;
  width: 16px;
  text-align: right;
  flex: none;
}
.mention-name {
  flex: none;
}
.mention-preview {
  color: #6b84aa;
  font-size: 11px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
