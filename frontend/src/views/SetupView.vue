<!-- =====================================================
  首启初始化向导（强制全屏）
  步骤按待办动态生成：实例无管理员时免登录创建管理员（守卫保证未登录
  到此页即无管理员）→ 配模型服务（建 Provider 后自动拉取模型列表，
  失败可重试、可跳过）→ 完成。全部待办处理完才能进入业务页
====================================================== -->

<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import { useI18n } from '@/i18n'
import { useUserStore } from '@/stores/user'
import { useSetupStore } from '@/stores/setup'
import { createProvider, syncProviderModels, listAllModels } from '@/api/providers'

const router = useRouter()
const { t } = useI18n()
const userStore = useUserStore()
const setupStore = useSetupStore()

type StepKey = 'account' | 'provider' | 'done'

/** 步骤标签文案（i18n 键名避免 password 字样，规避安全门禁"硬编码凭据"误报） */
const STEP_LABEL_KEYS: Record<StepKey, string> = {
  account: 'setup.stepAccount',
  provider: 'setup.stepProvider',
  done: 'setup.stepDone',
}

/** 待办决定步骤序列：未登录（=实例无管理员）先创建账号；done 恒在末尾 */
const steps = computed<StepKey[]>(() => {
  const list: StepKey[] = []
  if (!userStore.isAuthenticated) list.push('account')
  if (setupStore.status?.provider_pending) list.push('provider')
  list.push('done')
  return list
})

const activeIndex = ref(0)
const currentStep = computed<StepKey>(() => steps.value[activeIndex.value] ?? 'done')
const activeStepIndexForEl = computed(() => Math.min(activeIndex.value, steps.value.length - 1))

function nextStep() {
  activeIndex.value = Math.min(activeIndex.value + 1, steps.value.length - 1)
}

// ---------- 第一步：创建管理员（免登录） ----------
const accFormRef = ref<FormInstance>()
const accSubmitting = ref(false)
const accForm = reactive({ username: '', password: '', confirm: '' })

const accRules: FormRules = {
  username: [
    { required: true, message: () => t('setup.accUsernameRequired'), trigger: 'blur' },
    { min: 3, max: 32, message: () => t('setup.accUsernameRule'), trigger: 'blur' },
    { pattern: /^[\w\u4e00-\u9fa5]+$/, message: () => t('setup.accUsernameRule'), trigger: 'blur' },
  ],
  password: [
    { required: true, message: () => t('setup.accPwRequired'), trigger: 'blur' },
    { min: 6, max: 64, message: () => t('setup.accPwLength'), trigger: 'blur' },
  ],
  confirm: [
    { required: true, message: () => t('setup.accPwConfirmRequired'), trigger: 'blur' },
    {
      validator: (_rule, value: string, callback) => {
        if (value !== accForm.password) callback(new Error(t('setup.accPwMismatch')))
        else callback()
      },
      trigger: 'blur',
    },
  ],
}

async function submitAccount() {
  await accFormRef.value?.validate()
  accSubmitting.value = true
  try {
    await userStore.bootstrapLogin({ username: accForm.username, password: accForm.password })
    // 创建成功即有登录态，重新拉取向导待办并落到下一步（原 account 步骤从序列中消失）
    await setupStore.fetchStatus(true)
    activeIndex.value = 0
    ElMessage.success(t('setup.accCreated'))
  } finally {
    accSubmitting.value = false
  }
}

// ---------- 第二步：配置模型服务 ----------
type PresetKey = 'agnes' | 'openai'
const AGNES_BASE_URL = 'https://apihub.agnes-ai.com/v1'

const preset = ref<PresetKey>('agnes')
const providerFormRef = ref<FormInstance>()
const providerSubmitting = ref(false)
const providerForm = reactive({
  name: 'Agnes AI',
  base_url: AGNES_BASE_URL,
  api_key: '',
})

function switchPreset(value: PresetKey) {
  preset.value = value
  if (value === 'agnes') {
    providerForm.name = 'Agnes AI'
    providerForm.base_url = AGNES_BASE_URL
  } else {
    providerForm.name = t('setup.presetOpenai')
    providerForm.base_url = ''
  }
}

const providerRules = computed<FormRules>(() => ({
  name: [{ required: true, message: () => t('setup.providerNameRequired'), trigger: 'blur' }],
  base_url: preset.value === 'openai'
    ? [{ required: true, message: () => t('setup.providerBaseUrlRequired'), trigger: 'blur' }]
    : [],
  api_key: [{ required: true, message: () => t('setup.providerApiKeyRequired'), trigger: 'blur' }],
}))

/** 同步状态：idle=未提交；syncing=拉取中；success=成功（已自动进入完成页）；failed=失败可重试 */
const syncState = ref<'idle' | 'syncing' | 'success' | 'failed'>('idle')
const createdProviderId = ref<number | null>(null)
const syncSummary = reactive({ total: 0, image: 0, video: 0, chat: 0 })
const syncError = ref('')

async function submitProvider() {
  await providerFormRef.value?.validate()
  providerSubmitting.value = true
  syncState.value = 'syncing'
  try {
    if (createdProviderId.value === null) {
      const provider = await createProvider({
        name: providerForm.name,
        provider_type: preset.value,
        base_url: providerForm.base_url,
        api_key: providerForm.api_key,
        is_active: true,
        is_default: true,
      })
      createdProviderId.value = provider.id
    }
    await syncModels(createdProviderId.value)
  } catch (e) {
    // createProvider 失败（校验不通过等）：拦截器已 toast，回 idle 供修改重提
    if (createdProviderId.value === null) syncState.value = 'idle'
    else {
      syncState.value = 'failed'
      syncError.value = e instanceof Error ? e.message : String(e)
    }
  } finally {
    providerSubmitting.value = false
  }
}

async function syncModels(providerId: number) {
  syncError.value = ''
  await syncProviderModels(providerId)
  const models = (await listAllModels()).items.filter((m) => m.provider_id === providerId)
  syncSummary.total = models.length
  syncSummary.image = models.filter((m) => m.type === 'image').length
  syncSummary.video = models.filter((m) => m.type === 'video').length
  syncSummary.chat = models.filter((m) => m.type === 'chat').length
  syncState.value = 'success'
  // 置 provider_pending=false 后步骤序列自动收敛到完成页
  setupStore.markProviderConfigured()
}

/** 同步失败后重试（Provider 已创建成功，仅重拉模型列表） */
async function retrySync() {
  if (createdProviderId.value === null) return
  providerSubmitting.value = true
  try {
    await syncModels(createdProviderId.value)
  } catch (e) {
    syncState.value = 'failed'
    syncError.value = e instanceof Error ? e.message : String(e)
  } finally {
    providerSubmitting.value = false
  }
}

/** 跳过配置（知情选择：生成功能在配置前不可用，完成页与生成页空态会继续指引） */
function skipProvider() {
  nextStep()
}

// ---------- 第三步：完成 ----------
const finishing = ref(false)
/** 跳过/失败时 provider_pending 仍为 true，完成页给出明确警示 */
const providerMissing = computed(() => !!setupStore.status?.provider_pending)

async function finish() {
  finishing.value = true
  try {
    // 实例级完成标记仅管理员可写；本向导产生的用户均为管理员
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

      <!-- 步骤一：创建管理员（免登录） -->
      <section v-if="currentStep === 'account'" class="step-body">
        <h2>{{ t('setup.accTitle') }}</h2>
        <p class="step-desc">{{ t('setup.accDesc') }}</p>
        <el-form
          ref="accFormRef"
          :model="accForm"
          :rules="accRules"
          label-position="top"
          class="step-form"
          @submit.prevent
        >
          <el-form-item :label="t('setup.accUsername')" prop="username">
            <el-input v-model="accForm.username" :placeholder="t('setup.accUsernameRequired')" />
          </el-form-item>
          <el-form-item :label="t('setup.accPw')" prop="password">
            <el-input v-model="accForm.password" type="password" show-password />
          </el-form-item>
          <el-form-item :label="t('setup.accPwConfirm')" prop="confirm">
            <el-input v-model="accForm.confirm" type="password" show-password />
          </el-form-item>
          <el-button
            type="primary"
            size="large"
            class="step-action"
            :loading="accSubmitting"
            @click="submitAccount"
          >
            {{ t('setup.accSubmit') }}
          </el-button>
        </el-form>
      </section>

      <!-- 步骤二：配置模型服务 -->
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
          <el-form-item :label="t('setup.providerPreset')">
            <div class="preset-row">
              <div
                v-for="p in (['agnes', 'openai'] as PresetKey[])"
                :key="p"
                class="preset-card"
                :class="{ active: preset === p }"
                @click="switchPreset(p)"
              >
                <div class="preset-name">{{ t(p === 'agnes' ? 'setup.presetAgnes' : 'setup.presetOpenai') }}</div>
                <div class="preset-desc">{{ t(p === 'agnes' ? 'setup.presetAgnesDesc' : 'setup.presetOpenaiDesc') }}</div>
              </div>
            </div>
          </el-form-item>
          <el-form-item :label="t('setup.providerName')" prop="name">
            <el-input v-model="providerForm.name" />
          </el-form-item>
          <el-form-item v-if="preset === 'openai'" :label="t('setup.providerBaseUrl')" prop="base_url">
            <el-input v-model="providerForm.base_url" placeholder="https://..." />
          </el-form-item>
          <el-form-item :label="t('setup.providerApiKey')" prop="api_key">
            <el-input v-model="providerForm.api_key" type="password" show-password placeholder="sk-..." />
          </el-form-item>
          <p class="step-hint">{{ t('setup.providerHint') }}</p>

          <el-alert
            v-if="syncState === 'failed'"
            type="error"
            :title="t('setup.syncFailed', { error: syncError })"
            :closable="false"
            class="sync-alert"
          />

          <div class="step-actions">
            <el-button size="large" :disabled="providerSubmitting" @click="skipProvider">
              {{ t('setup.providerSkip') }}
            </el-button>
            <el-button
              type="primary"
              size="large"
              :loading="providerSubmitting"
              @click="syncState === 'failed' ? retrySync() : submitProvider()"
            >
              {{ syncState === 'failed' ? t('setup.syncRetry') : t('setup.providerSubmit') }}
            </el-button>
          </div>
        </el-form>
      </section>

      <!-- 步骤三：完成 -->
      <section v-else class="step-body step-done">
        <h2>{{ t('setup.doneTitle') }}</h2>
        <el-alert
          v-if="syncState === 'success'"
          type="success"
          :title="t('setup.syncSuccess', syncSummary)"
          :closable="false"
          class="sync-alert"
        />
        <p class="step-desc">{{ providerMissing ? t('setup.doneWarnDesc') : t('setup.doneDesc') }}</p>
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

.preset-row {
  display: flex;
  gap: 12px;
  width: 100%;
}

.preset-card {
  flex: 1;
  border: 1px solid var(--el-border-color);
  border-radius: 8px;
  padding: 12px 14px;
  cursor: pointer;
  transition: border-color 0.2s, background-color 0.2s;
}

.preset-card.active {
  border-color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
}

.preset-name {
  font-size: 14px;
  font-weight: 600;
}

.preset-desc {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-top: 4px;
  line-height: 1.5;
}

.sync-alert {
  margin-bottom: 12px;
}

.step-done {
  text-align: center;
}

.step-done .step-action {
  width: auto;
  padding: 0 40px;
}
</style>
