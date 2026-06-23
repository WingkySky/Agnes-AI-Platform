<!--
=====================================================
  登录 / 注册页
  - 采用 Tab 切换「登录」「注册」两种模式
  - 登录成功后：跳转到 redirect（若存在）或 /images
  - 新增：图片验证码、忘记密码弹窗、邮箱必填
=====================================================
-->

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import { User, Lock, Coin, Message as MessageIcon, MagicStick, RefreshRight, Key } from '@element-plus/icons-vue'
import { useUserStore } from '@/stores/user'
import { useI18n } from '@/i18n'
import { getCaptcha, sendEmailCode, resetPassword } from '@/api/auth'

// ========= 基础依赖 =========
const router = useRouter()
const route = useRoute()
const userStore = useUserStore()
const { t } = useI18n()

// 登录 / 注册 Tab
const activeTab = ref<'login' | 'register'>('login')
const submitting = computed(() => userStore.loading)

// ========= 图片验证码 =========
const loginCaptcha = ref({ captcha_id: '', image_base64: '' })
const registerCaptcha = ref({ captcha_id: '', image_base64: '' })

/** 加载登录页验证码 */
async function loadLoginCaptcha() {
  try {
    const res = await getCaptcha()
    loginCaptcha.value = res
  } catch (e) {
    console.error('加载登录验证码失败', e)
  }
}

/** 加载注册页验证码 */
async function loadRegisterCaptcha() {
  try {
    const res = await getCaptcha()
    registerCaptcha.value = res
  } catch (e) {
    console.error('加载注册验证码失败', e)
  }
}

// ========= 登录表单 =========
const loginForm = ref({
  username: '',
  password: '',
  captcha_code: ''
})
const loginRef = ref<FormInstance>()
const loginRules: FormRules = {
  username: [
    { required: true, message: t('login.usernameRequired'), trigger: 'blur' },
    { min: 3, max: 32, message: t('login.usernameLength'), trigger: 'blur' }
  ],
  password: [
    { required: true, message: t('login.passwordRequired'), trigger: 'blur' },
    { min: 6, max: 64, message: t('login.passwordLength'), trigger: 'blur' }
  ],
  captcha_code: [
    { required: true, message: t('login.captchaRequired'), trigger: 'blur' },
    { len: 4, message: t('login.captchaLength'), trigger: 'blur' }
  ]
}

async function handleLogin() {
  if (!loginRef.value) return
  const valid = await loginRef.value.validate().catch(() => false)
  if (!valid) return
  try {
    await userStore.login({
      username: loginForm.value.username,
      password: loginForm.value.password,
      captcha_id: loginCaptcha.value.captcha_id,
      captcha_code: loginForm.value.captcha_code
    })
    // 跳转：优先 redirect query，否则 /images
    const redirect = typeof route.query.redirect === 'string' && route.query.redirect
      ? route.query.redirect
      : '/images'
    router.push(redirect)
  } catch (e: any) {
    // 登录失败，刷新验证码
    loadLoginCaptcha()
    loginForm.value.captcha_code = ''
    // 错误已在 client.ts 拦截器中提示（401 用户名/密码错误、403 账号停用等），
    // 此处仅作为兜底：对未被拦截器处理的未知错误给一个通用提示
    const msg = e?.message || ''
    if (msg.includes('unauthorized') || msg.includes('停用') || msg.includes('用户名或密码错误') || msg.includes('验证码')) {
      // 拦截器已弹消息，跳过
      return
    }
    ElMessage.warning(t('login.loginFailed'))
  }
}

// ========= 注册表单 =========
const registerForm = ref({
  username: '',
  email: '',
  password: '',
  confirmPassword: '',
  captcha_code: ''
})
const registerRef = ref<FormInstance>()
const registerRules: FormRules = {
  username: [
    { required: true, message: t('login.usernameRequired'), trigger: 'blur' },
    { min: 3, max: 32, message: t('login.usernameLength'), trigger: 'blur' }
  ],
  email: [
    { required: true, message: t('login.emailRequired'), trigger: 'blur' },
    { type: 'email', message: t('login.emailInvalid'), trigger: 'blur' }
  ],
  password: [
    { required: true, message: t('login.passwordRequired'), trigger: 'blur' },
    { min: 6, max: 64, message: t('login.passwordLength'), trigger: 'blur' }
  ],
  confirmPassword: [
    { required: true, message: t('login.confirmPasswordRequired'), trigger: 'blur' },
    {
      validator: (_rule, value, callback) => {
        if (value !== registerForm.value.password) {
          callback(new Error(t('login.passwordMismatch')))
        } else {
          callback()
        }
      },
      trigger: 'blur'
    }
  ],
  captcha_code: [
    { required: true, message: t('login.captchaRequired'), trigger: 'blur' },
    { len: 4, message: t('login.captchaLength'), trigger: 'blur' }
  ]
}

async function handleRegister() {
  if (!registerRef.value) return
  const valid = await registerRef.value.validate().catch(() => false)
  if (!valid) return
  try {
    await userStore.register({
      username: registerForm.value.username,
      email: registerForm.value.email,
      password: registerForm.value.password,
      captcha_id: registerCaptcha.value.captcha_id,
      captcha_code: registerForm.value.captcha_code
    })
    router.push('/images')
  } catch (_e) {
    // 注册失败，刷新验证码
    loadRegisterCaptcha()
    registerForm.value.captcha_code = ''
    // 错误已通过拦截器提示
  }
}

// ========= 忘记密码弹窗 =========
const forgotPasswordVisible = ref(false)
const forgotPasswordStep = ref<'email' | 'reset'>('email') // 第一步：输入邮箱；第二步：重置密码
const forgotPasswordForm = ref({
  email: '',
  code: '',
  newPassword: '',
  confirmPassword: ''
})
const forgotPasswordRef = ref<FormInstance>()
const sendingCode = ref(false)
const codeCountdown = ref(0)
const resetting = ref(false)

const forgotPasswordRules: FormRules = {
  email: [
    { required: true, message: t('login.emailRequired'), trigger: 'blur' },
    { type: 'email', message: t('login.emailInvalid'), trigger: 'blur' }
  ],
  code: [
    { required: true, message: t('login.emailCodeRequired'), trigger: 'blur' },
    { len: 6, message: t('login.emailCodeLength'), trigger: 'blur' }
  ],
  newPassword: [
    { required: true, message: t('login.passwordRequired'), trigger: 'blur' },
    { min: 6, max: 64, message: t('login.passwordLength'), trigger: 'blur' }
  ],
  confirmPassword: [
    { required: true, message: t('login.confirmPasswordRequired'), trigger: 'blur' },
    {
      validator: (_rule, value, callback) => {
        if (value !== forgotPasswordForm.value.newPassword) {
          callback(new Error(t('login.passwordMismatch')))
        } else {
          callback()
        }
      },
      trigger: 'blur'
    }
  ]
}

/** 打开忘记密码弹窗 */
function openForgotPassword() {
  forgotPasswordVisible.value = true
  forgotPasswordStep.value = 'email'
  forgotPasswordForm.value = {
    email: '',
    code: '',
    newPassword: '',
    confirmPassword: ''
  }
  codeCountdown.value = 0
}

/** 发送邮箱验证码 */
async function handleSendEmailCode() {
  if (!forgotPasswordForm.value.email) {
    ElMessage.warning(t('login.emailRequired'))
    return
  }
  // 简单校验邮箱格式
  const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
  if (!emailRegex.test(forgotPasswordForm.value.email)) {
    ElMessage.warning(t('login.emailInvalid'))
    return
  }

  sendingCode.value = true
  try {
    await sendEmailCode({
      email: forgotPasswordForm.value.email,
      purpose: 'reset_password'
    })
    ElMessage.success(t('login.emailCodeSent'))
    // 开始倒计时
    codeCountdown.value = 60
    const timer = setInterval(() => {
      codeCountdown.value--
      if (codeCountdown.value <= 0) {
        clearInterval(timer)
      }
    }, 1000)
  } catch (_e) {
    // 错误已通过拦截器提示
  } finally {
    sendingCode.value = false
  }
}

/** 下一步（验证邮箱验证码，进入重置密码步骤） */
async function handleForgotNextStep() {
  if (!forgotPasswordRef.value) return
  // 只校验 email 和 code
  const valid = await forgotPasswordRef.value.validateFields(['email', 'code']).catch(() => false)
  if (!valid) return

  // 这里不直接验证验证码，而是进入下一步，等重置时一起验证
  forgotPasswordStep.value = 'reset'
}

/** 确认重置密码 */
async function handleResetPassword() {
  if (!forgotPasswordRef.value) return
  const valid = await forgotPasswordRef.value.validate().catch(() => false)
  if (!valid) return

  resetting.value = true
  try {
    await resetPassword({
      email: forgotPasswordForm.value.email,
      code: forgotPasswordForm.value.code,
      new_password: forgotPasswordForm.value.newPassword
    })
    ElMessage.success(t('login.resetPasswordSuccess'))
    forgotPasswordVisible.value = false
    // 切换到登录 tab
    activeTab.value = 'login'
    // 预填邮箱到登录表单的用户名（如果用户想用邮箱登录，但这里是用户名登录，所以不填）
  } catch (_e) {
    // 错误已通过拦截器提示
  } finally {
    resetting.value = false
  }
}

// ========= 初始化 =========
onMounted(() => {
  loadLoginCaptcha()
  loadRegisterCaptcha()
})

// 切换 tab 时刷新对应验证码
watch(activeTab, (newTab) => {
  if (newTab === 'login') {
    loadLoginCaptcha()
    loginForm.value.captcha_code = ''
  } else {
    loadRegisterCaptcha()
    registerForm.value.captcha_code = ''
  }
})
</script>

<template>
  <div class="login-page">
    <!-- 左侧品牌区 -->
    <div class="brand-panel">
      <div class="brand-logo">
        <el-icon class="brand-logo-emoji"><MagicStick /></el-icon>
      </div>
      <h1 class="brand-title">Agnes AI Platform</h1>
      <p class="brand-sub">{{ t('login.brandSub') }}</p>
      <ul class="brand-feats">
        <li><el-icon><User /></el-icon>{{ t('login.featAccount') }}</li>
        <li><el-icon><Coin /></el-icon>{{ t('login.featCredits') }}</li>
        <li><el-icon><Lock /></el-icon>{{ t('login.featSecurity') }}</li>
      </ul>
    </div>

    <!-- 右侧表单 -->
    <div class="form-panel">
      <div class="form-card">
        <div class="form-card__header">
          <h2 v-if="activeTab === 'login'">{{ t('login.welcome') }}</h2>
          <h2 v-else>{{ t('login.createAccount') }}</h2>
          <p class="sub">
            <template v-if="activeTab === 'login'">{{ t('login.loginHint') }}</template>
            <template v-else>{{ t('login.registerHint') }}</template>
          </p>
        </div>

        <el-tabs v-model="activeTab" class="tabs" stretch>
          <!-- 登录 Tab -->
          <el-tab-pane :label="t('login.login')" name="login">
            <el-form
              ref="loginRef"
              :model="loginForm"
              :rules="loginRules"
              label-position="top"
              @submit.prevent="handleLogin"
            >
              <el-form-item :label="t('login.username')" prop="username">
                <el-input
                  v-model="loginForm.username"
                  :placeholder="t('login.usernamePlaceholder')"
                  clearable
                  :prefix-icon="User"
                  autocomplete="username"
                />
              </el-form-item>
              <el-form-item :label="t('login.password')" prop="password">
                <el-input
                  v-model="loginForm.password"
                  type="password"
                  :placeholder="t('login.passwordPlaceholder')"
                  show-password
                  :prefix-icon="Lock"
                  autocomplete="current-password"
                  @keyup.enter="handleLogin"
                />
              </el-form-item>
              <!-- 图片验证码 -->
              <el-form-item :label="t('login.captcha')" prop="captcha_code">
                <div class="captcha-row">
                  <el-input
                    v-model="loginForm.captcha_code"
                    :placeholder="t('login.captchaPlaceholder')"
                    :prefix-icon="Key"
                    maxlength="4"
                    class="captcha-input"
                    @keyup.enter="handleLogin"
                  />
                  <div
                    class="captcha-image"
                    @click="loadLoginCaptcha"
                    :title="t('login.refreshCaptcha')"
                  >
                    <img
                      v-if="loginCaptcha.image_base64"
                      :src="'data:image/png;base64,' + loginCaptcha.image_base64"
                      alt="captcha"
                    />
                    <el-icon v-else class="captcha-refresh-icon"><RefreshRight /></el-icon>
                  </div>
                </div>
              </el-form-item>
              <el-form-item>
                <el-button
                  type="primary"
                  class="submit-btn"
                  :loading="submitting"
                  @click="handleLogin"
                >{{ t('login.login') }}</el-button>
              </el-form-item>
            </el-form>
            <div class="switch-hint">
              <el-link type="primary" class="forgot-link" @click="openForgotPassword">
                {{ t('login.forgotPassword') }}
              </el-link>
            </div>
            <div class="switch-hint">
              {{ t('login.noAccount') }}
              <el-link type="primary" @click="activeTab = 'register'">{{ t('login.goRegister') }}</el-link>
            </div>
          </el-tab-pane>

          <!-- 注册 Tab -->
          <el-tab-pane :label="t('login.register')" name="register">
            <el-form
              ref="registerRef"
              :model="registerForm"
              :rules="registerRules"
              label-position="top"
              @submit.prevent="handleRegister"
            >
              <el-form-item :label="t('login.username')" prop="username">
                <el-input
                  v-model="registerForm.username"
                  :placeholder="t('login.usernameHint')"
                  clearable
                  :prefix-icon="User"
                  autocomplete="username"
                />
              </el-form-item>
              <el-form-item :label="t('login.email')" prop="email">
                <el-input
                  v-model="registerForm.email"
                  placeholder="example@company.com"
                  clearable
                  :prefix-icon="MessageIcon"
                  autocomplete="email"
                />
              </el-form-item>
              <el-form-item :label="t('login.password')" prop="password">
                <el-input
                  v-model="registerForm.password"
                  type="password"
                  :placeholder="t('login.passwordHint')"
                  show-password
                  :prefix-icon="Lock"
                  autocomplete="new-password"
                />
              </el-form-item>
              <el-form-item :label="t('login.confirmPassword')" prop="confirmPassword">
                <el-input
                  v-model="registerForm.confirmPassword"
                  type="password"
                  :placeholder="t('login.confirmPasswordPlaceholder')"
                  show-password
                  :prefix-icon="Lock"
                  autocomplete="new-password"
                  @keyup.enter="handleRegister"
                />
              </el-form-item>
              <!-- 图片验证码 -->
              <el-form-item :label="t('login.captcha')" prop="captcha_code">
                <div class="captcha-row">
                  <el-input
                    v-model="registerForm.captcha_code"
                    :placeholder="t('login.captchaPlaceholder')"
                    :prefix-icon="Key"
                    maxlength="4"
                    class="captcha-input"
                    @keyup.enter="handleRegister"
                  />
                  <div
                    class="captcha-image"
                    @click="loadRegisterCaptcha"
                    :title="t('login.refreshCaptcha')"
                  >
                    <img
                      v-if="registerCaptcha.image_base64"
                      :src="'data:image/png;base64,' + registerCaptcha.image_base64"
                      alt="captcha"
                    />
                    <el-icon v-else class="captcha-refresh-icon"><RefreshRight /></el-icon>
                  </div>
                </div>
              </el-form-item>
              <el-form-item>
                <el-button
                  type="primary"
                  class="submit-btn"
                  :loading="submitting"
                  @click="handleRegister"
                >{{ t('login.register') }}</el-button>
              </el-form-item>
            </el-form>
            <div class="switch-hint">
              {{ t('login.hasAccount') }}
              <el-link type="primary" @click="activeTab = 'login'">{{ t('login.goLogin') }}</el-link>
            </div>
          </el-tab-pane>
        </el-tabs>
      </div>
    </div>

    <!-- 忘记密码弹窗 -->
    <el-dialog
      v-model="forgotPasswordVisible"
      :title="t('login.forgotPassword')"
      width="420px"
      :close-on-click-modal="false"
      destroy-on-close
    >
      <el-form
        ref="forgotPasswordRef"
        :model="forgotPasswordForm"
        :rules="forgotPasswordRules"
        label-position="top"
      >
        <!-- 第一步：输入邮箱 -->
        <template v-if="forgotPasswordStep === 'email'">
          <el-alert
            :title="t('login.forgotPasswordTip')"
            type="info"
            :closable="false"
            show-icon
            class="forgot-alert"
          />
          <el-form-item :label="t('login.email')" prop="email" style="margin-top: 16px;">
            <el-input
              v-model="forgotPasswordForm.email"
              :placeholder="t('login.emailPlaceholder')"
              clearable
              :prefix-icon="MessageIcon"
            />
          </el-form-item>
          <el-form-item :label="t('login.emailCode')" prop="code">
            <div class="captcha-row">
              <el-input
                v-model="forgotPasswordForm.code"
                :placeholder="t('login.emailCodePlaceholder')"
                :prefix-icon="Key"
                maxlength="6"
                class="captcha-input"
              />
              <el-button
                type="primary"
                plain
                class="send-code-btn"
                :disabled="codeCountdown > 0 || sendingCode"
                :loading="sendingCode"
                @click="handleSendEmailCode"
              >
                {{ codeCountdown > 0 ? `${codeCountdown}s` : t('login.sendCode') }}
              </el-button>
            </div>
          </el-form-item>
        </template>

        <!-- 第二步：重置密码 -->
        <template v-else>
          <el-alert
            :title="t('login.resetPasswordTip')"
            type="success"
            :closable="false"
            show-icon
            class="forgot-alert"
          />
          <el-form-item :label="t('login.newPassword')" prop="newPassword" style="margin-top: 16px;">
            <el-input
              v-model="forgotPasswordForm.newPassword"
              type="password"
              :placeholder="t('login.passwordHint')"
              show-password
              :prefix-icon="Lock"
            />
          </el-form-item>
          <el-form-item :label="t('login.confirmPassword')" prop="confirmPassword">
            <el-input
              v-model="forgotPasswordForm.confirmPassword"
              type="password"
              :placeholder="t('login.confirmPasswordPlaceholder')"
              show-password
              :prefix-icon="Lock"
              @keyup.enter="handleResetPassword"
            />
          </el-form-item>
        </template>
      </el-form>

      <template #footer>
        <el-button @click="forgotPasswordVisible = false">{{ t('common.cancel') }}</el-button>
        <el-button
          v-if="forgotPasswordStep === 'email'"
          type="primary"
          :disabled="sendingCode"
          @click="handleForgotNextStep"
        >{{ t('login.nextStep') }}</el-button>
        <el-button
          v-else
          type="primary"
          :loading="resetting"
          @click="handleResetPassword"
        >{{ t('login.confirmReset') }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
/* 全屏双栏布局 */
.login-page {
  width: 100%;
  height: 100vh;
  display: flex;
  align-items: stretch;
  background: var(--agnes-bg-base);
  color: var(--agnes-text-primary);
}

/* 左侧品牌面板 */
.brand-panel {
  flex: 1;
  padding: 60px 80px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 24px;
  background:
    radial-gradient(circle at 20% 30%, rgba(86, 122, 255, 0.22), transparent 50%),
    radial-gradient(circle at 80% 70%, rgba(139, 92, 246, 0.18), transparent 55%);
}

.brand-logo {
  width: 72px;
  height: 72px;
  border-radius: 18px;
  background: var(--agnes-bg-inset);
  display: flex;
  align-items: center;
  justify-content: center;
}
.brand-logo-emoji {
  font-size: 44px;
  color: #a78bff;
  line-height: 1;
  filter: drop-shadow(0 0 12px rgba(139, 92, 246, 0.5));
}

.brand-title {
  font-size: 32px;
  font-weight: 700;
  margin: 0;
  letter-spacing: 0.5px;
}

.brand-sub {
  font-size: 16px;
  margin: 0;
  color: var(--agnes-text-secondary);
}

.brand-feats {
  list-style: none;
  padding: 0;
  margin: 24px 0 0;
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.brand-feats li {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 15px;
  color: var(--agnes-text-primary);
}
.brand-feats .el-icon {
  color: var(--agnes-accent);
  font-size: 18px;
}

/* 右侧表单面板 */
.form-panel {
  width: 520px;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px;
  background: var(--agnes-bg-inset);
  border-left: 1px solid var(--agnes-border);
}

.form-card {
  width: 100%;
  background: var(--agnes-bg-card);
  border: 1px solid var(--agnes-border);
  border-radius: 20px;
  padding: 40px 40px 32px;
  box-shadow: var(--agnes-shadow-card);
  backdrop-filter: blur(12px);
}

.form-card__header h2 {
  margin: 0 0 6px;
  font-size: 26px;
  font-weight: 700;
}
.form-card__header .sub {
  margin: 0 0 20px;
  font-size: 14px;
  color: var(--agnes-text-muted);
}

.tabs {
  margin-bottom: 12px;
}

.submit-btn {
  width: 100%;
  height: 44px;
  font-size: 15px;
  font-weight: 600;
}

.switch-hint {
  margin-top: 12px;
  font-size: 13px;
  color: var(--agnes-text-muted);
  text-align: center;
}

.forgot-link {
  float: right;
}

/* 验证码行 */
.captcha-row {
  display: flex;
  gap: 12px;
  align-items: center;
}

.captcha-input {
  flex: 1;
}

.captcha-image {
  width: 120px;
  height: 40px;
  border-radius: 8px;
  background: var(--agnes-bg-inset);
  border: 1px solid var(--agnes-border);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  transition: border-color 0.2s;
  flex-shrink: 0;
}
.captcha-image:hover {
  border-color: var(--agnes-accent);
}
.captcha-image img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.captcha-refresh-icon {
  font-size: 18px;
  color: var(--agnes-text-muted);
}

/* 发送验证码按钮 */
.send-code-btn {
  height: 40px;
  flex-shrink: 0;
  min-width: 110px;
}

.forgot-alert {
  margin-bottom: 8px;
}

/* 响应式：小屏只显示表单 */
@media (max-width: 900px) {
  .login-page {
    flex-direction: column;
  }
  .brand-panel {
    display: none;
  }
  .form-panel {
    width: 100%;
    flex: 1;
    padding: 24px;
    border-left: none;
  }
}
</style>
