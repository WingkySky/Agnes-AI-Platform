<!--
  ChatSkillMenu.vue — "/" 技能快速清单（components/chat，两宿主共用）
  数据经 useSlashSkills 提供；配色走 --cb-* 变量（默认 --agnes-*，画布面板注入 theme token）
-->
<template>
  <div class="cb-skill-menu">
    <div class="cb-skill-menu-title">{{ t('agent.skillMenuTitle') }}</div>
    <div
      v-for="(s, i) in items"
      :key="s.name"
      class="cb-skill-menu-item"
      :class="{ active: i === highlight }"
      @click="emit('pick', s)"
      @mouseenter="emit('hover', i)"
    >
      <span class="cb-skill-menu-slash">/{{ s.tag || s.name }}</span>
      <span class="cb-skill-menu-desc">{{ s.description || s.name }}</span>
    </div>
    <div v-if="items.length === 0" class="cb-skill-menu-empty">{{ t('agent.skillMenuEmpty') }}</div>
    <div class="cb-skill-menu-hint">
      <Search :size="12" /><span>{{ t('agent.skillMenuHint') }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Search } from 'lucide-vue-next'
import { useI18n } from '@/i18n'
import type { AgentSkill } from '@/lib/agent/skills'

defineProps<{
  items: AgentSkill[]
  highlight: number
}>()

const emit = defineEmits<{
  (e: 'pick', skill: AgentSkill): void
  (e: 'hover', index: number): void
}>()

const { t } = useI18n()
</script>

<style scoped>
.cb-skill-menu {
  display: flex;
  flex-direction: column;
  max-height: 200px;
  overflow: hidden;
  margin: 0 0 6px;
  padding: 4px 0 2px;
  border: 1px solid var(--cb-menu-border, var(--agnes-border, rgba(100, 150, 220, 0.18)));
  border-radius: 10px;
  background: var(--cb-menu-bg, var(--agnes-bg-elevated, #171a26));
}

.cb-skill-menu-title {
  padding: 6px 12px 4px;
  font-size: 11px;
  color: var(--cb-muted, var(--agnes-text-faint, #5c6478));
}

.cb-skill-menu-item {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  padding: 7px 12px;
  cursor: pointer;
  white-space: nowrap;
  overflow: hidden;
}

.cb-skill-menu-item.active {
  background: var(--cb-item-hover, var(--agnes-nav-hover-bg, #1e2334));
}

.cb-skill-menu-slash {
  display: block;
  font-size: 13px;
  font-weight: 700;
  color: var(--cb-text, var(--agnes-text-primary, #e6e9f2));
  flex: none;
  max-width: 32%;
  overflow: hidden;
  text-overflow: ellipsis;
}

.cb-skill-menu-desc {
  display: block;
  font-size: 11px;
  color: var(--cb-muted, var(--agnes-text-faint, #5c6478));
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
}

.cb-skill-menu-empty {
  padding: 8px 12px;
  font-size: 12px;
  text-align: center;
  color: var(--cb-muted, var(--agnes-text-faint, #5c6478));
}

.cb-skill-menu-hint {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  border-top: 1px solid var(--cb-menu-border, var(--agnes-border-faint, rgba(100, 150, 220, 0.1)));
  font-size: 11px;
  color: var(--cb-muted, var(--agnes-text-faint, #5c6478));
}

.cb-skill-menu-hint span {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
