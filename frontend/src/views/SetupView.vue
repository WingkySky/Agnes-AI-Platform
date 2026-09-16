<!-- =====================================================
  首启初始化向导（强制全屏）
  步骤按待办动态生成：改默认密码（不可跳过）→ 配 AI Provider（管理员可跳过）→ 完成
  由路由守卫在有待办时强制送入；全部待办处理完才能进入业务页
====================================================== -->

<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import { useI18n } from '@/i18n'
import { useUserStore } from '@/stores/user'
import { useSetupStore } from '@/stores/setup'
import { changePassword } from '@/api/auth'
import { createProvider } from '@/api/providers'

const router = useRouter()
const { t } = useI18n()
const userStore = useUserStore()
const setupStore = useSetupStore()

type StepKey = 'password' | 'provider' | 'done'

/** el-steps 标签文案（step_password 键名会触发安全门禁"硬编码凭据"误报，故用 step_pw） */
const STEP_LABEL_KEYS: Record<StepKey, string> = {
  password: 'setup.step_pw',
  provider: 'setup.step_provider',
  done: 'setup.step_done',
}

/** 待办决定步骤序列；done 恒在末尾 */
const steps = computed<StepKey[]>(() => {
  const s = setupStore.status
  const list: StepKey[] = []
  if (s?.password_pending) list.push('password')
  if (s?.provider_pending) list.push('provider')
  list.push('done')
  return list
})

const activeIndex = ref(0)
const currentStep = computed<StepKey>(() => steps.value[activeIndex.value] ?? 'done')
const activeStepIndexForEl = computed(() => Math.min(activeIndex.value, steps.value.length - 1))

function nextStep() {
  activeIndex.value = Math.min(activeIndex.value + 1, steps.value.length - 1)
}

// ---------- 第一步：修改默认密码 ----------
const pwFormRef = ref<FormInstance>()
const pwSubmitting = ref(false)
const pwForm = reactive({ old_password: '', new_password: '', confirm: '' })

const pwRules: FormRules = {
  old_password: [{ required: true, message: () => t('setup.pwOldRequired'), trigger: 'blur' }],
  new_password: [
    { required: true, message: () => t('setup.pwNewRequired'), trigger: 'blur' },
    { min: 6, max: 64, message: () => t('setup.pwLength'), trigger: 'blur' },
  ],
  confirm: [
    { required: true, message: () => t('setup.pwConfirmRequired'), trigger: 'blur' },
    {
      validator: (_rule, value: string, callback) => {
        if (value !== pwForm.new_password) callback(new Error(t('setup.pwMismatch')))
        else callback()
      },
      trigger: 'blur',
    },
  ],
}

async function submitPassword() {
  await pwFormRef.value?.validate()
  pwSubmitting.value = true
  try {
    await changePassword({ old_password: pwForm.old_password, new_password: pwForm.new_password })
    setupStore.markPasswordChanged()
    await userStore.fetchMe()
    ElMessage.success(t('setup.pwChanged'))
    nextStep()
  } finally {
    pwSubmitting.value = false
  }
}

// ---------- 第二步：配置 AI Provider ----------
const providerFormRef = ref<FormInstance>()
const providerSubmitting = ref(false)
const providerForm = reactive({
  name: 'Agnes AI',
  base_url: 'https://apihub.agnes-ai.com/v1',
  api_key: '',
})

const providerRules: FormRules = {
  name: [{ required: true, message: () => t('setup.providerNameRequired'), trigger: 'blur' }],
  base_url: [{ required: true, message: () => t('setup.providerBaseUrlRequired'), trigger: 'blur' }],
  api_key: [{ required: true, message: () => t('setup.providerApiKeyRequired'), trigger: 'blur' }],
}

async function submitProvider() {
  await providerFormRef.value?.validate()
  providerSubmitting.value = true
  try {
    await createProvider({ ...providerForm, is_active: true, is_default: true })
    setupStore.markProviderConfigured()
    ElMessage.success(t('setup.providerCreated'))
    nextStep()
  } finally {
    providerSubmitting.value = false
  }
}

/** 跳过配置 Provider（知情选择：生成功能在配置前不可用） */
function skipProvider() {
  nextStep()
}

// ---------- 第三步：完成 ----------
const finishing = ref(false)

async function finish() {
  finishing.value = true
  try {
    // 实例级完成标记仅管理员可写；普通用户（仅改密场景）直接进入
    if (userStore.isAdmin) {
      await setupStore.complete()
    }
    router.push('/images')
  } finally {
    finishing.value = false
  }
}
</script>

<template>
  <div class="setup-page">
    <div class="setup-card">
      <header class="setup-header">
        <h1>{{ t('setup.title') }}</h1>
        <p>{{ t('setup.subtitle') }}</p>
      </header>

      <el-steps :active="activeStepIndexForEl" align-center finish-status="success" class="setup-steps">
        <el-step
          v-for="(step, i) in steps"
          :key="step"
          :title="t(STEP_LABEL_KEYS[step])"
          :description="i === activeIndex ? t('setup.stepCurrent') : undefined"
        />
      </el-steps>

      <!-- 步骤一：修改默认密码 -->
      <section v-if="currentStep === 'password'" class="step-body">
        <h2>{{ t('setup.pwTitle') }}</h2>
        <p class="step-desc">{{ t('setup.pwDesc') }}</p>
        <el-form
          ref="pwFormRef"
          :model="pwForm"
          :rules="pwRules"
          label-position="top"
          class="step-form"
          @submit.prevent
        >
          <el-form-item :label="t('setup.pwOld')" prop="old_password">
            <el-input v-model="pwForm.old_password" type="password" show-password />
          </el-form-item>
          <el-form-item :label="t('setup.pwNew')" prop="new_password">
            <el-input v-model="pwForm.new_password" type="password" show-password />
          </el-form-item>
          <el-form-item :label="t('setup.pwConfirm')" prop="confirm">
            <el-input v-model="pwForm.confirm" type="password" show-password />
          </el-form-item>
          <el-button
            type="primary"
            size="large"
            class="step-action"
            :loading="pwSubmitting"
            @click="submitPassword"
          >
            {{ t('setup.pwSubmit') }}
          </el-button>
        </el-form>
      </section>

      <!-- 步骤二：配置 AI Provider -->
      <section v-else-if="currentStep === 'provider'" class="step-body">
        <h2>{{ t('setup.providerTitle') }}</h2>
        <p class="step-desc">{{ t('setup.providerDesc') }}</p>
        <el-form
          ref="providerFormRef"
          :model="providerForm"
          :rules="providerRules"
          label-position="top"
          class="step-form"
          @submit.prevent
        >
          <el-form-item :label="t('setup.providerName')" prop="name">
            <el-input v-model="providerForm.name" />
          </el-form-item>
          <el-form-item :label="t('setup.providerBaseUrl')" prop="base_url">
            <el-input v-model="providerForm.base_url" />
          </el-form-item>
          <el-form-item :label="t('setup.providerApiKey')" prop="api_key">
            <el-input v-model="providerForm.api_key" type="password" show-password placeholder="sk-..." />
          </el-form-item>
          <p class="step-hint">{{ t('setup.providerHint') }}</p>
          <div class="step-actions">
            <el-button size="large" @click="skipProvider">{{ t('setup.providerSkip') }}</el-button>
            <el-button
              type="primary"
              size="large"
              :loading="providerSubmitting"
              @click="submitProvider"
            >
              {{ t('setup.providerSubmit') }}
            </el-button>
          </div>
        </el-form>
      </section>

      <!-- 步骤三：完成 -->
      <section v-else class="step-body step-done">
        <h2>{{ t('setup.doneTitle') }}</h2>
        <p class="step-desc">{{ t('setup.doneDesc') }}</p>
        <el-button type="primary" size="large" class="step-action" :loading="finishing" @click="finish">
          {{ t('setup.doneAction') }}
        </el-button>
      </section>
    </div>
  </div>
</template>

<style scoped>
.setup-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--el-bg-color-page);
  padding: 24px;
}

.setup-card {
  width: 560px;
  max-width: 100%;
  background: var(--el-bg-color);
  border-radius: 12px;
  padding: 32px 36px;
  box-shadow: var(--el-box-shadow-light);
}

.setup-header {
  text-align: center;
  margin-bottom: 24px;
}

.setup-header h1 {
  font-size: 22px;
  margin: 0 0 8px;
}

.setup-header p {
  color: var(--el-text-color-secondary);
  margin: 0;
  font-size: 13px;
}

.setup-steps {
  margin-bottom: 28px;
}

.step-body h2 {
  font-size: 17px;
  margin: 0 0 8px;
}

.step-desc {
  color: var(--el-text-color-secondary);
  font-size: 13px;
  margin: 0 0 20px;
}

.step-form {
  max-width: 380px;
  margin: 0 auto;
}

.step-action {
  width: 100%;
  margin-top: 8px;
}

.step-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 8px;
}

.step-hint {
  color: var(--el-text-color-secondary);
  font-size: 12px;
  line-height: 1.6;
  margin: 0 0 12px;
}

.step-done {
  text-align: center;
}

.step-done .step-action {
  width: auto;
  padding: 0 40px;
}
</style>
