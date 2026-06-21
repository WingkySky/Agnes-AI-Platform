<!--
=====================================================
  登录 / 注册页
  - 采用 Tab 切换「登录」「注册」两种模式
  - 登录成功后：跳转到 redirect（若存在）或 /images
=====================================================
-->

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import { User, Lock, Coin, Message as MessageIcon } from '@element-plus/icons-vue'
import { useUserStore } from '@/stores/user'

// ========= 基础依赖 =========
const router = useRouter()
const route = useRoute()
const userStore = useUserStore()

// 登录 / 注册 Tab
const activeTab = ref<'login' | 'register'>('login')
const submitting = computed(() => userStore.loading)

// ========= 登录表单 =========
const loginForm = ref({
  username: '',
  password: ''
})
const loginRef = ref<FormInstance>()
const loginRules: FormRules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { min: 3, max: 32, message: '用户名长度 3-32 字符', trigger: 'blur' }
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, max: 64, message: '密码长度 6-64 字符', trigger: 'blur' }
  ]
}

async function handleLogin() {
  if (!loginRef.value) return
  const valid = await loginRef.value.validate().catch(() => false)
  if (!valid) return
  try {
    await userStore.login(loginForm.value)
    // 跳转：优先 redirect query，否则 /images
    const redirect = typeof route.query.redirect === 'string' && route.query.redirect
      ? route.query.redirect
      : '/images'
    router.push(redirect)
  } catch (e: any) {
    // 错误已在拦截器中提示，此处仅作为兜底
    if (!e?.message?.includes('unauthorized')) {
      ElMessage.warning('登录失败：用户名或密码错误')
    }
  }
}

// ========= 注册表单 =========
const registerForm = ref({
  username: '',
  email: '' as string | null,
  password: '',
  confirmPassword: ''
})
const registerRef = ref<FormInstance>()
const registerRules: FormRules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { min: 3, max: 32, message: '用户名长度 3-32 字符', trigger: 'blur' }
  ],
  email: [
    { type: 'email', message: '邮箱格式不正确', trigger: 'blur' }
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, max: 64, message: '密码长度 6-64 字符', trigger: 'blur' }
  ],
  confirmPassword: [
    { required: true, message: '请再次输入密码', trigger: 'blur' },
    {
      validator: (_rule, value, callback) => {
        if (value !== registerForm.value.password) {
          callback(new Error('两次输入的密码不一致'))
        } else {
          callback()
        }
      },
      trigger: 'blur'
    }
  ]
}

async function handleRegister() {
  if (!registerRef.value) return
  const valid = await registerRef.value.validate().catch(() => false)
  if (!valid) return
  try {
    await userStore.register({
      username: registerForm.value.username,
      email: registerForm.value.email || null,
      password: registerForm.value.password
    })
    router.push('/images')
  } catch (_e) {
    // 错误已通过拦截器提示
  }
}
</script>

<template>
  <div class="login-page">
    <!-- 左侧品牌区 -->
    <div class="brand-panel">
      <div class="brand-logo">
        <span class="brand-logo-emoji">✨</span>
      </div>
      <h1 class="brand-title">Agnes AI Platform</h1>
      <p class="brand-sub">图片 · 视频 · 多模态创作中心</p>
      <ul class="brand-feats">
        <li><el-icon><User /></el-icon>独立账号与作品管理</li>
        <li><el-icon><Coin /></el-icon>积分制：按需使用，按次消耗</li>
        <li><el-icon><Lock /></el-icon>后端统一鉴权，保障账户安全</li>
      </ul>
    </div>

    <!-- 右侧表单 -->
    <div class="form-panel">
      <div class="form-card">
        <div class="form-card__header">
          <h2 v-if="activeTab === 'login'">欢迎回来</h2>
          <h2 v-else>创建一个新账户</h2>
          <p class="sub">
            <template v-if="activeTab === 'login'">使用你的用户名和密码登录</template>
            <template v-else>注册后即可开始创作，默认赠送初始积分</template>
          </p>
        </div>

        <el-tabs v-model="activeTab" class="tabs" stretch>
          <!-- 登录 Tab -->
          <el-tab-pane label="登录" name="login">
            <el-form
              ref="loginRef"
              :model="loginForm"
              :rules="loginRules"
              label-position="top"
              @submit.prevent="handleLogin"
            >
              <el-form-item label="用户名" prop="username">
                <el-input
                  v-model="loginForm.username"
                  placeholder="请输入用户名"
                  clearable
                  :prefix-icon="User"
                  autocomplete="username"
                />
              </el-form-item>
              <el-form-item label="密码" prop="password">
                <el-input
                  v-model="loginForm.password"
                  type="password"
                  placeholder="请输入密码"
                  show-password
                  :prefix-icon="Lock"
                  autocomplete="current-password"
                  @keyup.enter="handleLogin"
                />
              </el-form-item>
              <el-form-item>
                <el-button
                  type="primary"
                  class="submit-btn"
                  :loading="submitting"
                  @click="handleLogin"
                >登录</el-button>
              </el-form-item>
            </el-form>
            <div class="switch-hint">
              还没有账号？
              <el-link type="primary" @click="activeTab = 'register'">去注册</el-link>
            </div>
          </el-tab-pane>

          <!-- 注册 Tab -->
          <el-tab-pane label="注册" name="register">
            <el-form
              ref="registerRef"
              :model="registerForm"
              :rules="registerRules"
              label-position="top"
              @submit.prevent="handleRegister"
            >
              <el-form-item label="用户名" prop="username">
                <el-input
                  v-model="registerForm.username"
                  placeholder="3-32 个字符"
                  clearable
                  :prefix-icon="User"
                  autocomplete="username"
                />
              </el-form-item>
              <el-form-item label="邮箱（可选）" prop="email">
                <el-input
                  v-model="registerForm.email"
                  placeholder="example@company.com"
                  clearable
                  :prefix-icon="MessageIcon"
                  autocomplete="email"
                />
              </el-form-item>
              <el-form-item label="密码" prop="password">
                <el-input
                  v-model="registerForm.password"
                  type="password"
                  placeholder="6-64 个字符"
                  show-password
                  :prefix-icon="Lock"
                  autocomplete="new-password"
                />
              </el-form-item>
              <el-form-item label="确认密码" prop="confirmPassword">
                <el-input
                  v-model="registerForm.confirmPassword"
                  type="password"
                  placeholder="再次输入密码"
                  show-password
                  :prefix-icon="Lock"
                  autocomplete="new-password"
                  @keyup.enter="handleRegister"
                />
              </el-form-item>
              <el-form-item>
                <el-button
                  type="primary"
                  class="submit-btn"
                  :loading="submitting"
                  @click="handleRegister"
                >注册并登录</el-button>
              </el-form-item>
            </el-form>
            <div class="switch-hint">
              已有账号？
              <el-link type="primary" @click="activeTab = 'login'">去登录</el-link>
            </div>
          </el-tab-pane>
        </el-tabs>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* 全屏双栏布局 */
.login-page {
  width: 100%;
  height: 100vh;
  display: flex;
  align-items: stretch;
  background: linear-gradient(135deg, #0b0f1a 0%, #11172a 100%);
  color: #e6ebf2;
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
  background: rgba(255, 255, 255, 0.08);
  display: flex;
  align-items: center;
  justify-content: center;
}
.brand-logo-emoji {
  font-size: 44px;
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
  color: rgba(230, 235, 242, 0.75);
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
  color: rgba(230, 235, 242, 0.85);
}
.brand-feats .el-icon {
  color: #8b5cf6;
  font-size: 18px;
}

/* 右侧表单面板 */
.form-panel {
  width: 520px;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px;
  background: rgba(255, 255, 255, 0.02);
  border-left: 1px solid rgba(255, 255, 255, 0.06);
}

.form-card {
  width: 100%;
  background: rgba(17, 23, 42, 0.75);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 20px;
  padding: 40px 40px 32px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.35);
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
  color: rgba(230, 235, 242, 0.6);
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
  color: rgba(230, 235, 242, 0.55);
  text-align: center;
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
