<template>
  <el-dialog :model-value="open" :title="t('editor.subtitleStyleTitle')" width="440px" append-to-body @update:model-value="emit('close')">
    <div class="ss-row">
      <label>{{ t('editor.cueStyleFont') }}</label>
      <el-select
        v-model="form.font"
        size="small"
        filterable
        allow-create
        default-first-option
        :loading="fontsLoading"
      >
        <el-option v-for="f in fonts" :key="f" :value="f" :label="f" />
      </el-select>
    </div>
    <div class="ss-row">
      <label>{{ t('editor.cueStyleSize') }}</label>
      <el-input-number v-model="form.size" size="small" :min="8" :max="200" :step="2" controls-position="right" />
    </div>
    <div class="ss-row">
      <label>{{ t('editor.cueStyleColor') }}</label>
      <el-color-picker v-model="form.color" size="small" />
    </div>
    <div class="ss-row">
      <label>{{ t('editor.subtitleOutline') }}</label>
      <el-switch v-model="form.outline" size="small" />
    </div>
    <div class="ss-row">
      <label>{{ t('editor.cueStylePosition') }}</label>
      <el-radio-group v-model="form.position" size="small">
        <el-radio-button value="bottom">{{ t('editor.cuePosBottom') }}</el-radio-button>
        <el-radio-button value="center">{{ t('editor.cuePosCenter') }}</el-radio-button>
        <el-radio-button value="top">{{ t('editor.cuePosTop') }}</el-radio-button>
      </el-radio-group>
    </div>
    <p class="ss-hint">{{ t('editor.subtitleStyleHint') }}</p>
    <template #footer>
      <el-button @click="emit('close')">{{ t('common.cancel') }}</el-button>
      <el-button type="primary" @click="save">{{ t('common.confirm') }}</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
/* 工程级字幕样式编辑（setSubtitleStyle op 入撤销栈）：字体下拉=服务端 fc-list 可用族 */
import { reactive, ref, watch } from 'vue'
import { getEditorFonts } from '@/api/editor'
import { useEditorStore } from '@/stores/editor'
import { useI18n } from '@/i18n'

const props = defineProps<{ open: boolean }>()
const emit = defineEmits<{ (e: 'close'): void }>()

const { t } = useI18n()
const store = useEditorStore()

const fonts = ref<string[]>([])
const fontsLoading = ref(false)
const form = reactive({
  font: 'Noto Sans CJK SC',
  size: 48,
  color: '#FFFFFF',
  outline: true,
  position: 'bottom' as 'bottom' | 'center' | 'top',
})

watch(() => props.open, (open) => {
  if (!open) return
  const style = store.doc?.subtitleStyle
  form.font = style?.font ?? 'Noto Sans CJK SC'
  form.size = style?.size ?? 48
  form.color = style?.color ?? '#FFFFFF'
  form.outline = style?.outline ?? true
  form.position = style?.position ?? 'bottom'
  fontsLoading.value = true
  getEditorFonts()
    .then((list) => {
      fonts.value = list
      // 已设字体不在枚举里（枚举失败/异机工程）也保持可选
      if (form.font && !list.includes(form.font)) fonts.value = [form.font, ...list]
    })
    .finally(() => { fontsLoading.value = false })
})

function save(): void {
  const ok = store.applyOrToast(
    { op: 'setSubtitleStyle', payload: { style: { ...form } } },
    t('editor.ops.setSubtitleStyle'),
  )
  if (ok) emit('close')
}
</script>

<style scoped>
.ss-row { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; }
.ss-row > label { width: 48px; flex-shrink: 0; font-size: 12px; color: var(--el-text-color-secondary); }
.ss-row :deep(.el-select) { flex: 1; }
.ss-hint { margin: 0; font-size: 11px; color: var(--el-text-color-secondary); }
</style>
