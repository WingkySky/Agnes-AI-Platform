/* =====================================================
 * 文本笔记面板
 * - 双击进入编辑模式
 * - contenteditable 内联编辑
 * ===================================================== */

<template>
  <div
    class="text-panel"
    @dblclick="enterEdit"
  >
    <div
      v-if="editing"
      ref="textareaRef"
      contenteditable
      class="text-editor"
      @blur="exitEdit"
      @keydown="handleKeydown"
    />
    <div v-else class="text-preview">
      {{ panel.content?.text || t('canvas.textPlaceholder') }}
    </div>
  </div>
</template>

<script setup>
import { ref, nextTick } from 'vue'
import { useI18n } from '@/i18n'

const { t } = useI18n()

const props = defineProps({
  panel: { type: Object, required: true },
})

const editing = ref(false)
const textareaRef = ref(null)
const emit = defineEmits(['update'])

function enterEdit() {
  editing.value = true
  nextTick(() => {
    textareaRef.value?.focus()
    // 将光标定位到文本末尾
    if (props.panel.content?.text) {
      const range = document.createRange()
      const sel = window.getSelection()
      range.selectNodeContents(textareaRef.value)
      range.collapse(false)
      sel?.removeAllRanges()
      sel?.addRange(range)
    }
  })
}

function exitEdit() {
  editing.value = false
  const text = textareaRef.value?.innerText ?? ''
  emit('update', { content: { text } })
}

function handleKeydown(e) {
  if (e.key === 'Escape') {
    textareaRef.value?.blur()
  }
  // Shift+Enter 换行，普通 Enter 不触发编辑（避免与快捷键冲突）
  if (e.key === 'Enter' && e.shiftKey) return // 允许
  if (e.key === 'Enter') {
    e.preventDefault()
    textareaRef.value?.blur()
  }
}
</script>

<style scoped>
.text-preview {
  width: 100%;
  height: 100%;
  overflow-y: auto;
  font-size: 13px;
  line-height: 1.6;
  color: #c0d4f6;
  word-break: break-word;
}

.text-editor {
  width: 100%;
  height: 100%;
  outline: none;
  font-size: 13px;
  line-height: 1.6;
  color: #e8eef7;
  background: rgba(15, 22, 38, 0.5);
  border: 1px solid rgba(100, 150, 220, 0.2);
  border-radius: 6px;
  padding: 8px;
  overflow-y: auto;
}
</style>
