<template>
  <el-dialog
    :model-value="modelValue"
    :title="t('assets.editAsset')"
    width="600px"
    @update:model-value="$emit('update:modelValue', $event)"
  >
    <el-form v-if="form" :model="form" label-width="100px">
      <el-form-item :label="t('assets.fields.name')">
        <el-input v-model="form.name" />
      </el-form-item>
      <el-form-item :label="t('assets.fields.type')">
        <el-select v-model="form.type">
          <el-option v-for="tp in TYPE_OPTIONS" :key="tp" :label="t('assets.type.' + tp)" :value="tp" />
        </el-select>
      </el-form-item>
      <el-form-item :label="t('assets.fields.description')">
        <el-input v-model="form.description" type="textarea" :rows="2" />
      </el-form-item>
      <el-form-item :label="t('assets.fields.visualDescription')">
        <el-input v-model="form.visual_description" type="textarea" :rows="3" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="$emit('update:modelValue', false)">{{ t('common.cancel') }}</el-button>
      <el-button type="primary" :loading="saving" @click="handleSave">
        {{ t('common.save') }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { useI18n } from '@/i18n'
import { ElDialog, ElForm, ElFormItem, ElInput, ElSelect, ElOption, ElButton, ElMessage } from 'element-plus'
import { getAsset, updateAsset, type UnifiedAsset } from '@/api/assets'

// 资产编辑弹窗：v-model 控制显隐，assetId 为待编辑资产；统一资产层 GET/PATCH /api/assets/{id}
const props = defineProps<{
  modelValue: boolean
  assetId?: number | null
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  saved: [asset: UnifiedAsset]
}>()

const { t } = useI18n()

// 统一资产池七类（实体四类 + 影子归档行政三类），与后端 ASSET_TYPE_CHOICES 对齐
const TYPE_OPTIONS = ['character', 'prop', 'scene', 'brand', 'material', 'clip', 'final']

interface AssetEditForm {
  name: string
  type: string
  description: string
  visual_description: string
}

const form = ref<AssetEditForm | null>(null)
const savingId = ref<number | null>(null)
const saving = ref(false)

watch(
  () => props.modelValue,
  async (visible) => {
    if (!visible || props.assetId == null) return
    savingId.value = props.assetId
    try {
      const detail = await getAsset(props.assetId)
      form.value = {
        name: detail.name,
        type: detail.type,
        description: detail.description || '',
        visual_description: detail.visual_description || '',
      }
    } catch (e) {
      const err = e as { message?: string }
      ElMessage.error(err.message || t('assets.loadFailed'))
      emit('update:modelValue', false)
    }
  },
  { immediate: true }
)

async function handleSave() {
  if (!form.value || savingId.value == null) return
  if (!form.value.name.trim()) {
    ElMessage.warning(t('assets.fields.name') + t('common.required'))
    return
  }
  saving.value = true
  try {
    const saved = await updateAsset(savingId.value, {
      name: form.value.name.trim(),
      type: form.value.type,
      description: form.value.description,
      visual_description: form.value.visual_description,
    })
    ElMessage.success(t('assets.saveSuccess'))
    emit('saved', saved)
    emit('update:modelValue', false)
  } catch (e) {
    const err = e as { message?: string }
    ElMessage.error(err.message || t('assets.saveFailed'))
  } finally {
    saving.value = false
  }
}
</script>
