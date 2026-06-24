<!-- =====================================================
     邮箱配置视图 EmailConfigView
     - SMTP 邮件服务器配置
     - 支持测试邮件发送验证配置
     ===================================================== -->

<template>
  <div class="email-config-view">
    <h2 class="page-title">
      <el-icon><Message /></el-icon>
      {{ t('admin.emailConfig') }}
    </h2>
    <p class="page-desc">{{ t('settings.smtp.desc') }}</p>

    <!-- 状态卡片 -->
    <div class="status-card" :class="{ enabled: smtpConfig.is_enabled }">
      <div class="status-left">
        <el-icon class="status-icon"><Message /></el-icon>
        <div>
          <div class="status-title">{{ t('admin.emailService') }}</div>
          <div class="status-desc">
            {{ smtpConfig.is_enabled ? t('settings.smtp.enabled') : t('settings.smtp.disabled') }}
          </div>
        </div>
      </div>
      <el-tag :type="smtpConfig.is_enabled ? 'success' : 'info'" size="large">
        {{ smtpConfig.is_enabled ? t('settings.smtp.enabled') : t('settings.smtp.disabled') }}
      </el-tag>
    </div>

    <!-- 配置表单 -->
    <div class="config-card">
      <h3 class="card-title">{{ t('admin.smtpSettings') }}</h3>
      <el-form :model="smtpConfig" label-width="140px" class="smtp-form">
        <el-row :gutter="24">
          <el-col :span="16">
            <el-form-item :label="t('settings.smtp.host')">
              <el-input v-model="smtpConfig.smtp_host" :placeholder="t('settings.smtp.hostPlaceholder')" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item :label="t('settings.smtp.port')">
              <el-input-number v-model="smtpConfig.smtp_port" :min="1" :max="65535" style="width: 100%;" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="24">
          <el-col :span="12">
            <el-form-item :label="t('settings.smtp.user')">
              <el-input v-model="smtpConfig.smtp_user" :placeholder="t('settings.smtp.userPlaceholder')" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('settings.smtp.password')">
              <el-input
                v-model="smtpConfig.smtp_password"
                type="password"
                show-password
                :placeholder="t('settings.smtp.passwordPlaceholder')" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="24">
          <el-col :span="12">
            <el-form-item :label="t('settings.smtp.fromEmail')">
              <el-input v-model="smtpConfig.smtp_from_email" :placeholder="t('settings.smtp.fromEmailPlaceholder')" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('settings.smtp.fromName')">
              <el-input v-model="smtpConfig.smtp_from_name" :placeholder="t('settings.smtp.fromNamePlaceholder')" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item :label="t('settings.smtp.useTls')">
          <el-switch v-model="smtpConfig.smtp_use_tls" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="saving" @click="saveConfig">
            <el-icon><Check /></el-icon>
            {{ t('settings.smtp.save') }}
          </el-button>
          <el-button :icon="Message" :loading="testing" @click="openTestDialog">
            {{ t('settings.smtp.test') }}
          </el-button>
        </el-form-item>
      </el-form>
    </div>

    <!-- 测试邮件弹窗 -->
    <el-dialog
      v-model="testDialogVisible"
      :title="t('settings.smtp.test')"
      width="420px"
      :close-on-click-modal="false">
      <el-form label-width="100px">
        <el-form-item :label="t('settings.smtp.testEmail')">
          <el-input v-model="testEmail" :placeholder="t('settings.smtp.testEmailPlaceholder')" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="testDialogVisible = false">{{ t('common.cancel') }}</el-button>
        <el-button type="primary" :loading="testing" @click="sendTestEmail">
          {{ t('settings.smtp.test') }}
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
    smtpConfig.smtp_password = '' // 密码不回显
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
    ElMessage.success(t('settings.smtp.saveSuccess'))
    await fetchConfig() // 刷新状态
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
    ElMessage.warning(t('settings.smtp.testEmailPlaceholder'))
    return
  }
  testing.value = true
  try {
    await testSmtpConfig(testEmail.value)
    ElMessage.success(t('settings.smtp.testSuccess'))
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
.email-config-view {
  max-width: 1200px;
  margin: 0 auto;
}

.page-title {
  margin: 0 0 8px;
  font-size: 24px;
  font-weight: 700;
  color: var(--agnes-text-primary);
  display: flex;
  align-items: center;
  gap: 10px;
}

.page-title .el-icon {
  color: var(--agnes-accent);
}

.page-desc {
  margin: 0 0 24px;
  font-size: 14px;
  color: var(--agnes-text-muted);
  line-height: 1.6;
}

/* 状态卡片 */
.status-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20px 24px;
  background: var(--agnes-bg-input);
  border: 1px solid var(--agnes-border-faint);
  border-radius: 12px;
  margin-bottom: 24px;
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
  background: var(--agnes-bg-input);
  border: 1px solid var(--agnes-border-faint);
  border-radius: 12px;
  padding: 24px;
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
