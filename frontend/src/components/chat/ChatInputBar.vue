<!--
  ChatInputBar.vue — 共享输入区（components/chat）

  - v-model 草稿；Enter 发送 / Shift+Enter 换行（IME 组合期不触发）
  - 附件按钮（accept 由宿主给）；粘贴图片/拖拽文件经事件交宿主处理
  - sending 态：stoppable（画布 Agent）显示停止键；否则显示加载禁用（对话页行为不变）
  - 待发附件预览条、输入提示行由宿主经插槽注入
-->
<template>
  <div class="cb-input" @dragover.prevent @drop.prevent="onDrop">
    <slot name="attachments" />

    <!-- 输入框独占整行（全宽），胶囊与按钮放下一行 -->
    <textarea
      :value="modelValue"
      class="cb-draft"
      rows="2"
      :placeholder="placeholder"
      :disabled="disabled"
      @input="onInput"
      @keydown="onKeydown"
      @paste="onPaste"
    ></textarea>

    <div class="cb-input-row">
      <button
        type="button"
        class="cb-attach"
        :disabled="sending || disabled"
        :title="t('chat.uploadImage')"
        :aria-label="t('chat.uploadImage')"
        @click="fileInputRef?.click()"
      >
        <el-icon :size="18"><Plus /></el-icon>
      </button>
      <input
        ref="fileInputRef"
        type="file"
        multiple
        class="cb-file-input"
        :accept="accept"
        @change="onFilePick"
      >
      <!-- 宿主扩展位：模式胶囊等（画布 Agent 用） -->
      <slot name="leading" />
      <div class="cb-row-spacer" />
      <!-- 宿主扩展位：模型胶囊等 -->
      <slot name="trail" />
      <button
        type="button"
        class="cb-send"
        :class="{ 'is-stop': stoppable && sending }"
        :disabled="sendDisabled"
        :title="sendTitle"
        :aria-label="sendTitle"
        @click="onSendClick"
      >
        <el-icon v-if="stoppable && sending" :size="14"><VideoPause /></el-icon>
        <el-icon v-else-if="sending" class="is-loading" :size="16"><Loading /></el-icon>
        <el-icon v-else :size="16"><Promotion /></el-icon>
      </button>
    </div>

    <slot name="hint" />
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { Plus, Promotion, Loading, VideoPause } from '@element-plus/icons-vue'
import { useI18n } from '@/i18n'

const props = withDefaults(defineProps<{
  sending?: boolean
  /** sending 时显示停止键（画布 Agent 有停止语义；对话页保持原行为关闭） */
  stoppable?: boolean
  disabled?: boolean
  placeholder?: string
  /** 附件按钮 accept（如 'image/*' 或画布的多类型） */
  accept?: string
  /** 宿主有待发附件时允许空文本发送 */
  hasAttachments?: boolean
  /** 输入框内粘贴图片是否拦截为附件（对话页走全局粘贴监听，关掉避免重复） */
  pasteImages?: boolean
}>(), {
  sending: false,
  stoppable: false,
  disabled: false,
  placeholder: '',
  accept: 'image/*',
  hasAttachments: false,
  pasteImages: true,
})

const emit = defineEmits<{
  (e: 'update:modelValue', value: string): void
  (e: 'send'): void
  (e: 'stop'): void
  (e: 'pick-files', files: File[]): void
  (e: 'paste-image', file: File): void
  (e: 'drop-files', files: File[]): void
  /** 键盘事件先交宿主（画布 "/" 技能菜单拦截），被 preventDefault 后组件不再处理 */
  (e: 'keydown', event: KeyboardEvent): void
}>()

const modelValue = defineModel<string>({ default: '' })
const { t } = useI18n()
const fileInputRef = ref<HTMLInputElement | null>(null)

const canSend = computed(() => modelValue.value.trim().length > 0 || props.hasAttachments)
const sendDisabled = computed(() =>
  props.stoppable ? (!props.sending && !canSend.value) : (props.sending || props.disabled || !canSend.value),
)
const sendTitle = computed(() => (props.stoppable && props.sending ? t('chat.stop') : t('chat.send')))

function onInput(e: Event): void {
  if (!(e.target instanceof HTMLTextAreaElement)) return
  modelValue.value = e.target.value
}

function onKeydown(e: KeyboardEvent): void {
  emit('keydown', e)
  if (e.defaultPrevented || e.isComposing) return
  if (e.key === 'Enter' && !e.shiftKey && !e.ctrlKey && !e.metaKey) {
    e.preventDefault()
    emit('send')
  }
}

function onSendClick(): void {
  if (props.stoppable && props.sending) emit('stop')
  else if (!sendDisabled.value) emit('send')
}

function onPaste(e: ClipboardEvent): void {
  if (!props.pasteImages) return
  for (const item of e.clipboardData?.items ?? []) {
    if (item.type.startsWith('image/')) {
      const file = item.getAsFile()
      if (file) {
        e.preventDefault()
        emit('paste-image', file)
        return
      }
    }
  }
}

function onFilePick(e: Event): void {
  if (!(e.target instanceof HTMLInputElement)) return
  const files = Array.from(e.target.files ?? [])
  e.target.value = ''
  if (files.length) emit('pick-files', files)
}

function onDrop(e: DragEvent): void {
  const files = Array.from(e.dataTransfer?.files ?? [])
  if (files.length) emit('drop-files', files)
}
</script>

<style scoped>
.cb-input {
  padding: 12px 24px;
  border-top: 1px solid var(--cb-input-border, var(--agnes-border-faint, rgba(100, 150, 220, 0.1)));
  background: var(--cb-input-bg, var(--agnes-bg-inset, #12141d));
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.cb-input-row {
  display: flex;
  gap: 8px;
  align-items: center;
}

.cb-row-spacer {
  flex: 1;
}

.cb-attach,
.cb-send {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  flex: none;
  border: none;
  border-radius: 10px;
  cursor: pointer;
  background: transparent;
  color: var(--cb-muted, var(--agnes-text-muted, #8b93a8));
  transition: all 0.2s ease;
}

.cb-attach:hover:not(:disabled) {
  background: var(--agnes-nav-hover-bg, #1e2334);
  color: var(--agnes-primary, #4d80f0);
}

.cb-attach:disabled {
  cursor: not-allowed;
  opacity: 0.4;
}

.cb-file-input {
  display: none;
}

.cb-draft {
  display: block;
  width: 100%;
  box-sizing: border-box;
  resize: none;
  border: 1px solid var(--cb-input-field-border, rgba(100, 150, 220, 0.2));
  outline: none;
  border-radius: 10px;
  padding: 9px 12px;
  font-size: 13px;
  line-height: 1.5;
  font-family: inherit;
  background: var(--cb-input-field-bg, var(--agnes-bg-hover, #1c2030));
  color: var(--cb-text, var(--agnes-text-primary, #e6e9f2));
}

.cb-draft::placeholder {
  color: var(--cb-placeholder, var(--agnes-text-faint, #5c6478));
}

.cb-draft:focus {
  border-color: var(--cb-input-focus, var(--agnes-primary-border, rgba(80, 140, 255, 0.5)));
}

.cb-draft:disabled {
  opacity: 0.6;
}

.cb-send {
  background: var(--cb-send-bg, var(--agnes-primary, #4d80f0));
  color: var(--cb-send-text, #fff);
}

.cb-send:hover:not(:disabled) {
  opacity: 0.9;
}

.cb-send:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.cb-send.is-stop {
  background: var(--cb-stop-bg, #ef4444);
  color: #fff;
}
</style>
