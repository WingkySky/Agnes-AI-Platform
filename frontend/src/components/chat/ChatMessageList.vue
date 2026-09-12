<!--
  ChatMessageList.vue — 共享消息滚动区（components/chat）

  - 渲染 ChatBubbleItem 列表（经 ChatMessageBubble）
  - 内容增长时自动锚定底部；用户主动上翻时不抢滚动
  - 空状态与尾部扩展（思考指示/确认卡/错误行/加载中）由宿主经插槽注入
-->
<template>
  <div ref="listRef" class="cb-list">
    <slot name="empty" v-if="items.length === 0 && !loading" />

    <ChatMessageBubble v-for="item in items" :key="item.id" :item="item" :dense="dense">
      <template v-if="$slots['step-extra']" #step-extra="slotProps">
        <slot name="step-extra" v-bind="slotProps" />
      </template>
    </ChatMessageBubble>

    <slot name="footer" />
  </div>
</template>

<script setup lang="ts">
import { nextTick, onMounted, ref, watch } from 'vue'
import ChatMessageBubble from './ChatMessageBubble.vue'
import type { ChatBubbleItem } from './types'

const props = withDefaults(defineProps<{
  items: ChatBubbleItem[]
  loading?: boolean
  /** 紧凑形态（透传给气泡） */
  dense?: boolean
}>(), { loading: false, dense: false })

const listRef = ref<HTMLElement | null>(null)

/** 距底部阈值内的内容增长才自动滚底（用户上翻回看不抢滚动） */
const NEAR_BOTTOM_PX = 120

function isNearBottom(): boolean {
  const el = listRef.value
  if (!el) return true
  return el.scrollHeight - el.scrollTop - el.clientHeight < NEAR_BOTTOM_PX
}

async function scrollToBottom(smooth = false): Promise<void> {
  await nextTick()
  const el = listRef.value
  if (!el) return
  el.scrollTo({ top: el.scrollHeight, behavior: smooth ? 'smooth' : 'auto' })
}

onMounted(() => {
  void scrollToBottom()
})

watch(
  () => props.items,
  () => {
    if (isNearBottom()) void scrollToBottom()
  },
  { deep: true },
)

defineExpose({ scrollToBottom })
</script>

<style scoped>
.cb-list {
  flex: 1;
  overflow-y: auto;
  min-height: 0;
  padding: 20px 24px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}
</style>
