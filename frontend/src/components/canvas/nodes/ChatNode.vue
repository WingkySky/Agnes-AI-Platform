<!-- =====================================================
     ChatNode —— 对话节点内容组件
     - 轻量级聊天：提示词输入 + AI 回复展示
     - 不依赖复杂的 chat store 会话机制，节点内部维护简单状态
     - status 徽章：idle / waiting / done / error
     ===================================================== -->

<template>
  <div class="chat-node">
    <!-- 用户提示词输入 -->
    <div class="node-field">
      <label class="node-field-label">当前提示词</label>
      <textarea
        class="node-field-textarea"
        :value="lastUserText"
        placeholder="与 AI 对话的提示词"
        rows="2"
        @input="handlePromptInput"
      />
    </div>

    <!-- 发送按钮 -->
    <div class="chat-node-actions">
      <button
        v-if="hasUpstream"
        class="node-btn node-btn-ghost"
        @click="handleApplyUpstream"
        title="把上游节点的文本/提示词作为对话上下文"
      >
        <el-icon :size="14"><Link /></el-icon>
        <span>应用上游数据</span>
      </button>
      <button
        class="node-btn node-btn-primary"
        :disabled="!canSend"
        @click="handleSend"
      >
        <el-icon :size="14"><Promotion /></el-icon>
        <span>{{ isWaiting ? 'AI 思考中...' : '发送' }}</span>
      </button>
    </div>

    <!-- AI 回复展示区 -->
    <div class="chat-node-reply">
      <label class="node-field-label">AI 回复</label>
      <div class="chat-node-reply-box">
        <span v-if="panel.content?.lastReply">{{ panel.content.lastReply }}</span>
        <span v-else-if="isWaiting" class="chat-node-empty">AI 正在思考...</span>
        <span v-else class="chat-node-empty">尚未生成回复</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { Promotion, Link } from '@element-plus/icons-vue'
import { useCanvasStore } from '@/stores/canvas'

const props = defineProps({ panel: { type: Object, required: true } })
const emit = defineEmits(['update-content', 'update-status'])
const store = useCanvasStore()

/* =====================================================
 * 上游节点数据：
 * - text/image/video 节点的文本/图片/视频 URL 可作为上下文发送给 AI
 * - 提供"应用上游数据"按钮
 * ===================================================== */
const upstreamOutput = computed(() => store.getUpstreamOutput(props.panel.id))
const hasUpstream = computed(() => upstreamOutput.value.length > 0)

function handleApplyUpstream() {
  const merged = store.resolveInputs(props.panel.id)
  if (!merged) return
  // 把上游数据转为对话式文本，拼到 prompt 中
  const contextLines = []
  for (const item of upstreamOutput.value) {
    if (item.output.prompt) contextLines.push('参考提示词：' + item.output.prompt)
    if (item.output.resultUrl) contextLines.push('参考媒体：' + item.output.resultUrl)
    if (item.output.lastReply) contextLines.push('参考对话：' + item.output.lastReply)
  }
  const currentPrompt = merged.prompt || ''
  // 把上游上下文加到 prompt（如果还没加）
  let newPrompt = currentPrompt
  if (contextLines.length > 0) {
    const prefix = contextLines.join('\n') + '\n你的回复：'
    if (!currentPrompt.includes('参考提示词') && !currentPrompt.includes('参考媒体')) {
      newPrompt = prefix + (currentPrompt ? '\n' + currentPrompt : '')
    }
  }
  emit('update-content', { ...merged, prompt: newPrompt })
}

/* 最后一条用户消息的文本 */
const lastUserText = computed(() => {
  const messages = props.panel.content?.messages
  if (Array.isArray(messages) && messages.length > 0) {
    const last = messages[messages.length - 1]
    if (last && last.text) return last.text
  }
  return props.panel.content?.prompt || ''
})

const isWaiting = ref(false)
const canSend = computed(() => {
  const text = lastUserText.value
  return text && text.trim().length > 0 && !isWaiting.value
})

/* 用户输入提示词 → 更新 messages 的最后一条（或新建一条） */
function handlePromptInput(e) {
  const text = e.target.value
  const messages = Array.isArray(props.panel.content?.messages)
    ? [...props.panel.content.messages]
    : []
  if (messages.length === 0) {
    messages.push({ role: 'user', text: text })
  } else {
    messages[messages.length - 1] = { ...messages[messages.length - 1], text: text }
  }
  emit('update-content', { messages: messages, prompt: text })
}

/* 发送按钮：占位实现 —— 正式接入 chat store 后需替换
 * 如果你已经接入 chat store，可替换此处为流式回复方法调用 */
function handleSend() {
  isWaiting.value = true
  emit('update-status', 'waiting')
  /* 预留接入点：
   *   const chatStore = useChatStore()
   *   const reply = await chatStore.sendPrompt(panel.content.prompt)
   *   emit('update-content', { lastReply: reply })
   *   emit('update-status', 'done')
   */
  setTimeout(() => {
    const text = (props.panel.content?.prompt || '').trim()
    if (!text) {
      isWaiting.value = false
      emit('update-status', 'idle')
      return
    }
    // 简易占位回复 —— 实际应由 Agnes AI chat 接口返回
    emit('update-content', {
      lastReply: '（示例回复）你说："' + text + '"。请在正式接入 chat store 后替换此占位逻辑。',
    })
    isWaiting.value = false
    emit('update-status', 'done')
  }, 600)
}
</script>

<style scoped>
.chat-node {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.node-field {
  display: flex;
  flex-direction: column;
}

.node-field-label {
  font-size: 11px;
  color: #8ba3c9;
  margin-bottom: 4px;
}

.node-field-textarea {
  width: 100%;
  background: rgba(15, 24, 42, 0.7);
  border: 1px solid rgba(120, 170, 230, 0.2);
  border-radius: 6px;
  color: #e8eef7;
  padding: 6px 8px;
  font-size: 12px;
  outline: none;
  box-sizing: border-box;
  font-family: inherit;
  resize: vertical;
  min-height: 50px;
}

.chat-node-actions {
  display: flex;
}

.node-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  border-radius: 6px;
  font-size: 12px;
  cursor: pointer;
  border: 1px solid transparent;
  margin-right: 8px;
}

.node-btn-ghost {
  background: rgba(120, 170, 230, 0.08);
  border-color: rgba(120, 170, 230, 0.3);
  color: #9ac7ff;
}

.node-btn-ghost:hover {
  background: rgba(120, 170, 230, 0.18);
  border-color: rgba(120, 170, 230, 0.5);
}

.node-btn-primary {
  background: rgba(86, 156, 214, 0.2);
  border-color: rgba(86, 156, 214, 0.5);
  color: #9ac7ff;
}

.node-btn-primary:hover:not(:disabled) {
  background: rgba(86, 156, 214, 0.35);
}

.node-btn-primary:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.chat-node-reply {
  margin-top: 4px;
}

.chat-node-reply-box {
  padding: 10px 12px;
  background: rgba(0, 0, 0, 0.25);
  border-radius: 6px;
  font-size: 12px;
  line-height: 1.6;
  min-height: 48px;
  color: #d5e3f7;
}

.chat-node-empty {
  color: #8ba3c9;
  font-style: italic;
}
</style>
