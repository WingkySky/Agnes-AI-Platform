<!--
  ChatModelPill.vue — 对话模型胶囊（components/chat，两宿主共用）
  画布面板与对话页输入条 trail 插槽同款；数据外部传入（models + 当前 id），
  选择经 select 事件交宿主 store（内核 setModel 热更新，BFF 命中注册表真实生效）。
-->
<template>
  <div v-if="models.length" class="cb-model-pill">
    <button
      type="button"
      class="cb-pill-btn"
      :title="t('chat.modelTitle')"
      @click.stop="open = !open"
    >
      <span class="cb-pill-text">{{ currentName }}</span>
      <ChevronDown :size="12" class="cb-pill-chevron" :class="{ open }" />
    </button>
    <div v-if="open" class="cb-pill-menu cb-align-right">
      <div class="cb-pill-menu-title">{{ t('chat.modelTitle') }}</div>
      <button
        v-for="m in models"
        :key="m.id"
        type="button"
        class="cb-pill-menu-item"
        :class="{ active: m.id === modelId }"
        @click="onPick(m.id)"
      >
        <span class="cb-pill-menu-body">
          <span class="cb-pill-menu-name">{{ m.name }}</span>
          <span class="cb-pill-menu-desc">{{ m.provider }}</span>
        </span>
        <Check v-if="m.id === modelId" :size="14" class="cb-pill-menu-check" />
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, onMounted, onBeforeUnmount } from 'vue'
import { ChevronDown, Check } from 'lucide-vue-next'
import { useI18n } from '@/i18n'
import type { ModelInfo } from '@/types'

const props = defineProps<{
  /** 当前生效模型 id（宿主解析：用户选择 > 默认链） */
  modelId: string
  /** 可选 chat 模型列表 */
  models: ModelInfo[]
}>()

const emit = defineEmits<{
  (e: 'select', id: string): void
}>()

const { t } = useI18n()
const open = ref(false)

const currentName = computed(() => {
  const m = props.models.find((x) => x.id === props.modelId)
  return m?.name || props.modelId || t('chat.modelTitle')
})

function onPick(id: string): void {
  open.value = false
  emit('select', id)
}

/** 点胶囊外部关闭 */
function onPointerDown(e: PointerEvent): void {
  if (!open.value) return
  if (e.target instanceof Element && e.target.closest('.cb-model-pill')) return
  open.value = false
}

onMounted(() => window.addEventListener('pointerdown', onPointerDown))
onBeforeUnmount(() => window.removeEventListener('pointerdown', onPointerDown))
</script>

<style scoped>
.cb-model-pill {
  position: relative;
  flex: none;
}

.cb-pill-btn {
  display: flex;
  align-items: center;
  gap: 4px;
  height: 32px;
  padding: 0 8px;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: var(--cb-pill-text, var(--agnes-text-muted, #8b93a8));
  cursor: pointer;
  font-size: 12px;
  max-width: 130px;
}

.cb-pill-btn:hover {
  background: var(--cb-item-hover, var(--agnes-nav-hover-bg, #1e2334));
}

.cb-pill-text {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.cb-pill-chevron {
  flex: none;
  opacity: 0.7;
  transition: transform 0.15s ease;
}

.cb-pill-chevron.open {
  transform: rotate(180deg);
}

.cb-pill-menu {
  position: absolute;
  bottom: calc(100% + 8px);
  right: 0;
  min-width: 230px;
  max-width: 300px;
  max-height: 300px;
  overflow-y: auto;
  border: 1px solid var(--cb-menu-border, var(--agnes-border, rgba(100, 150, 220, 0.18)));
  border-radius: 10px;
  padding: 4px;
  display: flex;
  flex-direction: column;
  gap: 2px;
  z-index: 70;
  background: var(--cb-menu-bg, var(--agnes-bg-elevated, #171a26));
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.35);
}

.cb-pill-menu-title {
  padding: 6px 10px 4px;
  font-size: 11px;
  color: var(--cb-muted, var(--agnes-text-faint, #5c6478));
}

.cb-pill-menu-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 7px 10px;
  border: none;
  border-radius: 8px;
  background: transparent;
  cursor: pointer;
  text-align: left;
}

.cb-pill-menu-item:hover,
.cb-pill-menu-item.active {
  background: var(--cb-item-hover, var(--agnes-nav-hover-bg, #1e2334));
}

.cb-pill-menu-body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 1px;
}

.cb-pill-menu-name {
  font-size: 12px;
  color: var(--cb-text, var(--agnes-text-primary, #e6e9f2));
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.cb-pill-menu-desc {
  font-size: 11px;
  color: var(--cb-muted, var(--agnes-text-faint, #5c6478));
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.cb-pill-menu-check {
  flex: none;
  color: var(--cb-text, var(--agnes-text-primary, #e6e9f2));
}
</style>
