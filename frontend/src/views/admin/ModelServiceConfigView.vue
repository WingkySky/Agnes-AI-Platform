<!-- =====================================================
     模型服务配置（管理员）
     - 系统级对话模型配置：审核 / 会话标题总结 / 系统默认对话模型
     - 创作类对话模型由用户偏好设置，不在此页
     ===================================================== -->

<template>
  <div class="model-service-config">
    <h2 class="page-title">{{ t('admin.modelService.title') }}</h2>
    <p class="page-desc">{{ t('admin.modelService.desc') }}</p>

    <div class="config-section" v-loading="loading">
      <div class="config-row">
        <div class="config-info">
          <span class="config-label">{{ t('admin.modelService.chatDefault') }}</span>
          <span class="config-hint">{{ t('admin.modelService.chatDefaultHint') }}</span>
        </div>
        <el-select
          v-model="form.model_chat_default"
          style="width: 260px"
          @change="dirty = true"
          clearable
          placeholder=" "
          :loading="loading">
          <el-option v-for="m in options" :key="m.id" :label="`${m.name} (${m.id})`" :value="m.id" />
        </el-select>
      </div>

      <div class="config-row">
        <div class="config-info">
          <span class="config-label">{{ t('admin.modelService.moderation') }}</span>
          <span class="config-hint">{{ t('admin.modelService.moderationHint') }}</span>
        </div>
        <el-select
          v-model="form.model_moderation_chat"
          style="width: 260px"
          @change="dirty = true"
          clearable
          placeholder=" "
          :loading="loading">
          <el-option v-for="m in options" :key="m.id" :label="`${m.name} (${m.id})`" :value="m.id" />
        </el-select>
      </div>

      <div class="config-row">
        <div class="config-info">
          <span class="config-label">{{ t('admin.modelService.titleSummary') }}</span>
          <span class="config-hint">{{ t('admin.modelService.titleSummaryHint') }}</span>
        </div>
        <el-select
          v-model="form.model_title_summary_chat"
          style="width: 260px"
          @change="dirty = true"
          clearable
          placeholder=" "
          :loading="loading">
          <el-option v-for="m in options" :key="m.id" :label="`${m.name} (${m.id})`" :value="m.id" />
        </el-select>
      </div>

      <div class="config-footer">
        <el-button type="primary" :loading="saving" :disabled="!dirty" @click="handleSave">
          {{ t('common.save') }}
        </el-button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { useI18n } from '@/i18n'
import { getModelServiceConfig, updateModelServiceConfig } from '@/api/admin'

const { t } = useI18n()
const loading = ref(false)
const saving = ref(false)
const dirty = ref(false)
const options = ref<{ id: string; name: string }[]>([])

// key 与后端 SYSTEM_CHAT_MODEL_KEYS 对齐
const form = reactive({
  model_chat_default: '',
  model_moderation_chat: '',
  model_title_summary_chat: '',
})

onMounted(async () => {
  loading.value = true
  try {
    const resp = await getModelServiceConfig()
    options.value = resp.options || []
    form.model_chat_default = resp.configs['model.chat_default'] || ''
    form.model_moderation_chat = resp.configs['model.moderation_chat'] || ''
    form.model_title_summary_chat = resp.configs['model.title_summary_chat'] || ''
  } finally {
    loading.value = false
  }
})

async function handleSave() {
  saving.value = true
  try {
    await updateModelServiceConfig({
      'model.chat_default': form.model_chat_default || '',
      'model.moderation_chat': form.model_moderation_chat || '',
      'model.title_summary_chat': form.model_title_summary_chat || '',
    })
    dirty.value = false
    ElMessage.success(t('admin.modelService.saved'))
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.model-service-config {
  max-width: 760px;
}

.page-title {
  margin: 0 0 8px;
  font-size: 22px;
  font-weight: 700;
  color: var(--agnes-text-primary);
}

.page-desc {
  margin: 0 0 20px;
  font-size: 13px;
  color: var(--agnes-text-muted);
  line-height: 1.6;
}

.config-section {
  background: var(--agnes-bg-input);
  border: 1px solid var(--agnes-border-faint);
  border-radius: 12px;
  padding: 20px 24px;
}

.config-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: 12px 0;
  border-bottom: 1px solid var(--agnes-border-faint);
}

.config-row:last-of-type {
  border-bottom: none;
}

.config-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
  flex: 1;
}

.config-label {
  font-size: 14px;
  font-weight: 500;
  color: var(--agnes-text-primary);
}

.config-hint {
  font-size: 12px;
  color: var(--agnes-text-muted);
  line-height: 1.5;
}

.config-footer {
  display: flex;
  justify-content: flex-end;
  padding-top: 16px;
}
</style>
