<!--
  ChatNodeMenu.vue — "@" 画布节点引用弹层（components/chat）
  数据经 useAtNodes 提供；样式语言与 ChatSkillMenu 一致（--cb-* 变量）
-->
<template>
  <div class="cb-node-menu">
    <div class="cb-node-menu-title">{{ t('agent.nodeMenuTitle') }}</div>
    <div
      v-for="(n, i) in items"
      :key="n.id"
      class="cb-node-menu-item"
      :class="{ active: i === highlight }"
      @click="emit('pick', n)"
      @mouseenter="emit('hover', i)"
    >
      <span class="cb-node-menu-type" :data-type="n.type">{{ typeLabel(n.type) }}</span>
      <span class="cb-node-menu-name">{{ n.name || n.id }}</span>
      <img v-if="n.mediaUrl" :src="n.mediaUrl" alt="" class="cb-node-menu-thumb" />
    </div>
    <div v-if="items.length === 0" class="cb-node-menu-empty">{{ t('agent.nodeMenuEmpty') }}</div>
    <div class="cb-node-menu-hint">
      <Search :size="12" /><span>{{ t('agent.nodeMenuHint') }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Search } from 'lucide-vue-next'
import { useI18n } from '@/i18n'
import { canvasNodeTypeLabel, type CanvasNodeSummary } from '@/lib/agent/canvas-bridge'

defineProps<{
  items: CanvasNodeSummary[]
  highlight: number
}>()

const emit = defineEmits<{
  (e: 'pick', node: CanvasNodeSummary): void
  (e: 'hover', index: number): void
}>()

const { t } = useI18n()
const typeLabel = (type: string) => canvasNodeTypeLabel(type)
</script>

<style scoped>
.cb-node-menu {
  display: flex;
  flex-direction: column;
  max-height: 220px;
  overflow-y: auto;
  margin: 0 0 6px;
  padding: 4px 0 2px;
  border: 1px solid var(--cb-menu-border, var(--agnes-border, rgba(100, 150, 220, 0.18)));
  border-radius: 10px;
  background: var(--cb-menu-bg, var(--agnes-bg-elevated, #171a26));
}

.cb-node-menu-title {
  padding: 6px 12px 4px;
  font-size: 11px;
  color: var(--cb-muted, var(--agnes-text-faint, #5c6478));
}

.cb-node-menu-item {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  padding: 6px 12px;
  cursor: pointer;
}

.cb-node-menu-item.active {
  background: var(--cb-item-hover, var(--agnes-nav-hover-bg, #1e2334));
}

.cb-node-menu-type {
  flex: none;
  padding: 1px 6px;
  border-radius: 4px;
  font-size: 10px;
  background: var(--cb-item-hover, rgba(128, 128, 128, 0.18));
  color: var(--cb-muted, var(--agnes-text-faint, #8b93a8));
}

.cb-node-menu-type[data-type='image'],
.cb-node-menu-type[data-type='video'] {
  color: var(--el-color-primary, #4d80f0);
}

.cb-node-menu-type[data-type='text'] {
  color: var(--el-color-warning, #e6a23c);
}

.cb-node-menu-name {
  flex: 1;
  min-width: 0;
  font-size: 12px;
  color: var(--cb-text, var(--agnes-text-primary, #e6e9f2));
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.cb-node-menu-thumb {
  flex: none;
  width: 34px;
  height: 22px;
  border-radius: 4px;
  object-fit: cover;
  display: block;
}

.cb-node-menu-empty {
  padding: 8px 12px;
  font-size: 12px;
  text-align: center;
  color: var(--cb-muted, var(--agnes-text-faint, #5c6478));
}

.cb-node-menu-hint {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  border-top: 1px solid var(--cb-menu-border, var(--agnes-border-faint, rgba(100, 150, 220, 0.1)));
  font-size: 11px;
  color: var(--cb-muted, var(--agnes-text-faint, #5c6478));
}

.cb-node-menu-hint span {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
