<template>
  <el-dialog
    :model-value="modelValue"
    :title="assetId ? t('assets.editAsset') : t('assets.createAsset')"
    width="600px"
    @update:model-value="$emit('update:modelValue', $event)"
  >
    <el-form v-if="form" :model="form" label-width="100px">
      <el-form-item :label="t('assets.fields.name')">
        <el-input v-model="form.name" />
      </el-form-item>
      <el-form-item :label="t('assets.fields.type')">
        <el-select v-model="form.type" :placeholder="t('assets.type.all')">
          <el-option :label="t('assets.type.character')" value="character" />
          <el-option :label="t('assets.type.prop')" value="prop" />
          <el-option :label="t('assets.type.scene')" value="scene" />
          <el-option :label="t('assets.type.brand')" value="brand" />
        </el-select>
      </el-form-item>
      <el-form-item :label="t('assets.fields.description')">
        <el-input v-model="form.description" type="textarea" :rows="2" />
      </el-form-item>
      <el-form-item :label="t('assets.fields.visualDescription')">
        <el-input v-model="form.visual_description" type="textarea" :rows="3" />
      </el-form-item>
      <el-form-item :label="t('assets.fields.referenceImages')">
        <ImageUploader v-model="form.reference_images" :max="5" />
      </el-form-item>
      <el-form-item :label="t('assets.fields.tags')">
        <el-input v-model="tagsInput" :placeholder="t('assets.fields.tags')" />
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
import ImageUploader from '@/components/ImageUploader.vue'
import { useAssetStore } from '@/stores/asset'
import type { Asset, AssetType } from '@/types'

// 资产详情弹窗：通过 v-model 控制显示/隐藏，assetId 存在时编辑，否则新建
const props = defineProps<{
  modelValue: boolean
  assetId?: number | null
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  saved: [asset: Asset]
}>()

const { t } = useI18n()
const assetStore = useAssetStore()

const form = ref<any>(null)
const tagsInput = ref('')
const saving = ref(false)

watch(
  () => [props.modelValue, props.assetId],
  async ([visible, id]) => {
    if (visible) {
      if (id) {
        // 编辑现有资产
        const { getAssetDetail } = await import('@/api/pipeline')
        const detail = await getAssetDetail(id as number)
        form.value = { ...detail }
        tagsInput.value = (detail.tags || []).join(', ')
      } else {
        // 新建
        form.value = {
          name: '',
          type: 'character' as AssetType,
          description: '',
          visual_description: '',
          reference_images: [],
          tags: [],
        }
        tagsInput.value = ''
      }
    }
  },
  { immediate: true }
)

async function handleSave() {
  if (!form.value.name) {
    ElMessage.warning(t('assets.fields.name') + t('common.required'))
    return
  }
  saving.value = true
  try {
    form.value.tags = tagsInput.value.split(',').map(s => s.trim()).filter(Boolean)
    // 调用 store 保存（store 内部调 API）
    // 注意：如果后端有 createAsset 接口，需在 api/pipeline.ts 补充
    emit('saved', form.value)
    emit('update:modelValue', false)
  } catch (e) {
    console.error('保存资产失败:', e)
  } finally {
    saving.value = false
  }
}
</script>
