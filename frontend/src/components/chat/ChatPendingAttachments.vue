<template>
  <div v-if="attachments.length > 0" class="pending-attachments">
    <div
      v-for="(att, idx) in attachments"
      :key="'pending-' + idx"
      class="pending-attachment"
    >
      <img v-if="att.base64" :src="att.base64" :alt="att.name" class="pending-attachment-thumb" />
      <div v-else-if="att.url" class="pending-attachment-url">
        <el-icon :size="18"><Document /></el-icon>
        <span class="url-text" :title="att.url">{{ truncateUrl(att.url) }}</span>
      </div>
      <el-button
        type="danger"
        size="small"
        circle
        icon="Close"
        class="pending-attachment-remove"
        @click="emit('remove', idx)"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
/* 待发送附件预览条（对话页/全局抽屉共享） */
import { Document } from '@element-plus/icons-vue'
import type { MessageAttachment } from '@/types'
import { truncateUrl } from '@/composables/useChatComposer'

defineProps<{ attachments: MessageAttachment[] }>()
const emit = defineEmits<{ (e: 'remove', index: number): void }>()
</script>

<style scoped>
.pending-attachments {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.pending-attachment {
  position: relative;
  width: 72px;
  height: 72px;
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid var(--agnes-border);
  background: var(--agnes-bg-hover);
}

.pending-attachment-thumb {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.pending-attachment-url {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 6px;
  background: rgba(80, 140, 255, 0.1);
  border-radius: 4px;
  overflow: hidden;
}

.pending-attachment-url .url-text {
  font-size: 11px;
  color: var(--agnes-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.pending-attachment-remove {
  position: absolute;
  top: 2px;
  right: 2px;
  width: 20px !important;
  height: 20px !important;
  padding: 0 !important;
  font-size: 12px;
}
</style>
