<!-- =====================================================
     实体编辑对话框 EntityEditDialog
     - 通用编辑：根据 entityType 动态展示字段
     - character: name / description / appearance_desc / role_type
     - scene: name / description / location / time_of_day / atmosphere
     - prop: name / description / visual_desc
     - 保存后通知父组件
     ===================================================== -->

<template>
  <el-dialog
    v-model="visible"
    :title="dialogTitle"
    width="640px"
    :close-on-click-modal="false"
    destroy-on-close
    @closed="resetForm"
  >
    <el-form :model="formData" label-position="top">
      <!-- 通用：名称 -->
      <el-form-item :label="nameFieldLabel">
        <el-input v-model="formData.name" :placeholder="`请输入${nameFieldLabel}`" maxlength="100" />
      </el-form-item>

      <!-- 通用：描述 -->
      <el-form-item label="描述">
        <el-input
          v-model="formData.description"
          type="textarea"
          :rows="3"
          placeholder="该实体的简短描述"
        />
      </el-form-item>

      <!-- 角色专属字段 -->
      <template v-if="entityType === 'character'">
        <el-form-item label="角色类型">
          <el-select v-model="formData.role_type" placeholder="选择角色类型" clearable style="width: 100%">
            <el-option label="主角" value="protagonist" />
            <el-option label="配角" value="supporting" />
            <el-option label="反派" value="antagonist" />
            <el-option label="群演" value="extra" />
          </el-select>
        </el-form-item>
        <el-form-item label="外貌描述">
          <el-input
            v-model="formData.appearance_desc"
            type="textarea"
            :rows="4"
            placeholder="用于图像生成的外貌关键词，如：长发、红衣、年轻女性..."
          />
        </el-form-item>
      </template>

      <!-- 场景专属字段 -->
      <template v-if="entityType === 'scene'">
        <el-form-item label="地点">
          <el-input v-model="formData.location" placeholder="场景发生的地点" />
        </el-form-item>
        <el-form-item label="时间">
          <el-select v-model="formData.time_of_day" placeholder="选择时间" clearable style="width: 100%">
            <el-option label="清晨" value="dawn" />
            <el-option label="白天" value="day" />
            <el-option label="黄昏" value="dusk" />
            <el-option label="夜晚" value="night" />
          </el-select>
        </el-form-item>
        <el-form-item label="氛围">
          <el-input v-model="formData.atmosphere" placeholder="场景氛围，如：温馨 / 紧张 / 神秘" />
        </el-form-item>
      </template>

      <!-- 道具专属字段 -->
      <template v-if="entityType === 'prop'">
        <el-form-item label="视觉描述">
          <el-input
            v-model="formData.visual_desc"
            type="textarea"
            :rows="4"
            placeholder="用于图像生成的视觉关键词，如：金色、长剑、古朴..."
          />
        </el-form-item>
      </template>
    </el-form>

    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" :loading="saving" @click="onSave">保存</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useProjectStore } from '@/stores/project'
import type { EntityType } from '@/types/project'

const props = defineProps<{
  modelValue: boolean
  entityType: EntityType
  /** 传入编辑的实体对象（null 表示新建） */
  entity: any | null
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', val: boolean): void
  (e: 'saved', entity: any): void
}>()

const projectStore = useProjectStore()

const visible = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val),
})

const dialogTitle = computed(() => {
  const typeName = props.entityType === 'character' ? '角色'
    : props.entityType === 'scene' ? '场景'
    : '道具'
  return props.entity ? `编辑${typeName}` : `新建${typeName}`
})

const nameFieldLabel = computed(() => {
  if (props.entityType === 'character') return '角色名称'
  if (props.entityType === 'scene') return '场景名称'
  return '道具名称'
})

// 表单数据
const formData = ref<Record<string, any>>({})
const saving = ref(false)

function buildInitialForm() {
  const e = props.entity || {}
  formData.value = {
    name: e.name || '',
    description: e.description || '',
    // 角色
    role_type: e.role_type || '',
    appearance_desc: e.appearance_desc || '',
    // 场景
    location: e.location || '',
    time_of_day: e.time_of_day || '',
    atmosphere: e.atmosphere || '',
    // 道具
    visual_desc: e.visual_desc || '',
  }
}

function resetForm() {
  formData.value = {}
}

function buildPayload(): Record<string, any> {
  const data: Record<string, any> = { name: formData.value.name }
  if (formData.value.description) data.description = formData.value.description
  // 角色专属
  if (props.entityType === 'character') {
    if (formData.value.role_type) data.role_type = formData.value.role_type
    if (formData.value.appearance_desc) data.appearance_desc = formData.value.appearance_desc
  }
  // 场景专属
  if (props.entityType === 'scene') {
    if (formData.value.location) data.location = formData.value.location
    if (formData.value.time_of_day) data.time_of_day = formData.value.time_of_day
    if (formData.value.atmosphere) data.atmosphere = formData.value.atmosphere
  }
  // 道具专属
  if (props.entityType === 'prop') {
    if (formData.value.visual_desc) data.visual_desc = formData.value.visual_desc
  }
  return data
}

async function onSave() {
  if (!formData.value.name?.trim()) {
    ElMessage.warning('名称不能为空')
    return
  }
  saving.value = true
  try {
    const payload = buildPayload()
    let result: any
    if (props.entity?.id) {
      result = await projectStore.updateEntity(props.entityType, props.entity.id, payload)
    } else {
      result = await projectStore.createEntity(props.entityType, payload)
    }
    ElMessage.success(props.entity ? '已保存' : '已创建')
    emit('saved', result)
    visible.value = false
  } catch (e: any) {
    ElMessage.error(e?.message || '保存失败')
  } finally {
    saving.value = false
  }
}

// 打开时初始化表单
watch(visible, (val) => {
  if (val) buildInitialForm()
})
</script>

<style scoped>
/* 通用 form 样式继承自 Element Plus 默认 */
</style>
