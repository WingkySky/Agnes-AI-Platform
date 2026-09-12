<!-- =====================================================
     邮箱配置视图 EmailConfigView
     - SMTP 邮件服务器配置
     - 支持测试邮件发送验证配置
     ===================================================== -->

<template>
  <div class="email-config-wrap">
    <!-- 页面头部：标题+描述在左 -->
    <header class="page-head">
      <div>
        <h2>{{ t('admin.smtp.title') }}</h2>
        <p class="muted">{{ t('admin.smtp.desc') }}</p>
      </div>
    </header>

    <!-- 服务状态卡片 -->
    <div class="status-card" :class="{ enabled: smtpConfig.is_enabled }">
      <div class="status-left">
        <el-icon class="status-icon"><Message /></el-icon>
        <div>
          <div class="status-title">{{ t('admin.smtp.serviceStatus') }}</div>
          <div class="status-desc">
            {{ smtpConfig.is_enabled ? t('admin.smtp.enabled') : t('admin.smtp.disabled') }}
          </div>
        </div>
      </div>
      <el-tag :type="smtpConfig.is_enabled ? 'success' : 'info'" size="large">
        {{ smtpConfig.is_enabled ? t('admin.smtp.enabled') : t('admin.smtp.disabled') }}
      </el-tag>
    </div>

    <!-- 配置表单卡片 -->
    <el-card class="config-card" shadow="never">
      <h3 class="card-title">{{ t('admin.smtp.smtpSettings') }}</h3>
      <el-form :model="smtpConfig" label-width="140px" class="smtp-form">
        <el-row :gutter="24">
          <el-col :span="16">
            <el-form-item :label="t('admin.smtp.host')">
              <el-input v-model="smtpConfig.smtp_host" :placeholder="t('admin.smtp.hostPlaceholder')" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item :label="t('admin.smtp.port')">
              <el-input-number v-model="smtpConfig.smtp_port" :min="1" :max="65535" style="width: 100%;" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="24">
          <el-col :span="12">
            <el-form-item :label="t('admin.smtp.user')">
              <el-input v-model="smtpConfig.smtp_user" :placeholder="t('admin.smtp.userPlaceholder')" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('admin.smtp.password')">
              <el-input
                v-model="smtpConfig.smtp_password"
                type="password"
                show-password
                :placeholder="t('admin.smtp.passwordPlaceholder')" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="24">
          <el-col :span="12">
            <el-form-item :label="t('admin.smtp.fromEmail')">
              <el-input v-model="smtpConfig.smtp_from_email" :placeholder="t('admin.smtp.fromEmailPlaceholder')" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('admin.smtp.fromName')">
              <el-input v-model="smtpConfig.smtp_from_name" :placeholder="t('admin.smtp.fromNamePlaceholder')" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item :label="t('admin.smtp.useTls')">
          <el-switch v-model="smtpConfig.smtp_use_tls" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="saving" @click="saveConfig">
            <el-icon><Check /></el-icon>
            {{ t('admin.smtp.save') }}
          </el-button>
          <el-button :icon="Message" :loading="testing" @click="openTestDialog">
            {{ t('admin.smtp.test') }}
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 测试邮件弹窗 -->
    <el-dialog
      v-model="testDialogVisible"
      :title="t('admin.smtp.testTitle')"
      width="420px"
      :close-on-click-modal="false">
      <el-form label-width="100px">
        <el-form-item :label="t('admin.smtp.testEmail')">
          <el-input v-model="testEmail" :placeholder="t('admin.smtp.testEmailPlaceholder')" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="testDialogVisible = false">{{ t('common.cancel') }}</el-button>
        <el-button type="primary" :loading="testing" @click="sendTestEmail">
          {{ t('admin.smtp.test') }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Message, Check } from '@element-plus/icons-vue'
import { useI18n } from '@/i18n'
import { getSmtpConfig, updateSmtpConfig, testSmtpConfig, type SmtpConfig } from '@/api/admin'

const { t } = useI18n()

const saving = ref(false)
const testing = ref(false)
const testDialogVisible = ref(false)
const testEmail = ref('')

const smtpConfig = reactive<SmtpConfig>({
  smtp_host: '',
  smtp_port: 587,
  smtp_user: '',
  smtp_password: '',
  smtp_from_email: '',
  smtp_from_name: 'Agnes AI Platform',
  smtp_use_tls: true,
  is_enabled: false,
})

// 加载配置
async function fetchConfig() {
  try {
    const data = await getSmtpConfig()
    Object.assign(smtpConfig, data)
    smtpConfig.smtp_password = ''
  } catch (e) {
    // 忽略错误
  }
}

// 保存配置
async function saveConfig() {
  saving.value = true
  try {
    await updateSmtpConfig({
      smtp_host: smtpConfig.smtp_host,
      smtp_port: smtpConfig.smtp_port,
      smtp_user: smtpConfig.smtp_user,
      smtp_password: smtpConfig.smtp_password,
      smtp_from_email: smtpConfig.smtp_from_email,
      smtp_from_name: smtpConfig.smtp_from_name,
      smtp_use_tls: smtpConfig.smtp_use_tls,
    })
    ElMessage.success(t('admin.smtp.saveSuccess'))
    await fetchConfig()
  } finally {
    saving.value = false
  }
}

// 打开测试弹窗
function openTestDialog() {
  testDialogVisible.value = true
}

// 发送测试邮件
async function sendTestEmail() {
  if (!testEmail.value) {
    ElMessage.warning(t('admin.smtp.testEmailRequired'))
    return
  }
  testing.value = true
  try {
    await testSmtpConfig(testEmail.value)
    ElMessage.success(t('admin.smtp.testSuccess'))
    testDialogVisible.value = false
  } finally {
    testing.value = false
  }
}

onMounted(() => {
  fetchConfig()
})
</script>

<style scoped>
/* =====================================================
 * 邮箱配置页面样式
 * ===================================================== */
.email-config-wrap {
  max-width: 100%;
}

.page-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 16px;
}

.page-head h2 {
  margin: 0 0 6px 0;
  font-size: 22px;
  font-weight: 600;
  color: var(--agnes-text-primary);
}

.muted {
  margin: 0;
  color: var(--agnes-text-secondary);
  font-size: 14px;
}

/* 状态卡片 */
.status-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20px 24px;
  background: var(--agnes-bg-elevated);
  border: 1px solid var(--agnes-border-faint);
  border-radius: 10px;
  margin-bottom: 16px;
}

.status-card.enabled {
  border-color: var(--agnes-success-border);
  background: var(--agnes-success-bg-soft);
}

.status-left {
  display: flex;
  align-items: center;
  gap: 14px;
}

.status-icon {
  font-size: 28px;
  color: var(--agnes-text-secondary);
}

.status-card.enabled .status-icon {
  color: var(--agnes-success);
}

.status-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--agnes-text-primary);
  margin-bottom: 2px;
}

.status-desc {
  font-size: 13px;
  color: var(--agnes-text-muted);
}

/* 配置卡片 */
.config-card {
  border-radius: 10px;
}

.card-title {
  margin: 0 0 20px;
  font-size: 16px;
  font-weight: 600;
  color: var(--agnes-text-primary);
  padding-bottom: 12px;
  border-bottom: 1px solid var(--agnes-border-faint);
}

.smtp-form {
  max-width: 900px;
}
</style>
