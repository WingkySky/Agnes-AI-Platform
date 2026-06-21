<!-- =====================================================
     Agnes AI Platform 根组件
     - 提供主布局（左侧导航 + 右侧内容）
     - 通过 <el-config-provider> 响应式切换 Element Plus 语言
     - 右上角 LanguageSwitcher 切换界面语言
     ===================================================== -->

<template>
  <el-config-provider :locale="epLocale">
    <div class="app-root">
      <!-- 顶部栏 -->
      <header class="app-header">
        <div class="app-brand">
          <span class="brand-icon">✨</span>
          <div class="brand-text">
            <h1>Agnes AI Platform</h1>
            <p class="brand-sub">{{ t('app.title') }}</p>
          </div>
        </div>

        <nav class="app-nav">
          <router-link to="/chat" class="nav-item" active-class="active">
            <el-icon><ChatDotRound /></el-icon>
            <span>{{ t('nav.chat') }}</span>
          </router-link>
          <router-link to="/images" class="nav-item" active-class="active">
            <el-icon><Picture /></el-icon>
            <span>{{ t('nav.images') }}</span>
          </router-link>
          <router-link to="/videos" class="nav-item" active-class="active">
            <el-icon><VideoPlay /></el-icon>
            <span>{{ t('nav.videos') }}</span>
          </router-link>
          <router-link to="/history" class="nav-item" active-class="active">
            <el-icon><Clock /></el-icon>
            <span>{{ t('nav.history') }}</span>
          </router-link>
          <router-link to="/canvas" class="nav-item" active-class="active">
            <el-icon><Grid /></el-icon>
            <span>{{ t('nav.canvas') }}</span>
          </router-link>
          <router-link to="/settings" class="nav-item" active-class="active">
            <el-icon><Setting /></el-icon>
            <span>{{ t('nav.settings') }}</span>
          </router-link>
          <!-- 管理员菜单（仅管理员可见） -->
          <template v-if="userStore.isAuthenticated && userStore.isAdmin">
            <router-link to="/admin/users" class="nav-item" active-class="active">
              <el-icon><UserFilled /></el-icon>
              <span>{{ t('nav.usersAdmin') }}</span>
            </router-link>
            <router-link to="/admin/credit-rules" class="nav-item" active-class="active">
              <el-icon><Coin /></el-icon>
              <span>{{ t('nav.creditRules') }}</span>
            </router-link>
          </template>
        </nav>

        <div class="app-header-right">
          <!-- 积分显示（仅登录后） -->
          <div v-if="userStore.isAuthenticated" class="credits-chip" :title="t('userMenu.creditsTitle')">
            <el-icon><Coin /></el-icon>
            <span class="credits-value">{{ creditsText }}</span>
            <span class="credits-label">{{ t('userMenu.creditsLabel') }}</span>
          </div>

          <!-- 登录入口 / 用户菜单 -->
          <template v-if="userStore.isAuthenticated">
            <el-dropdown trigger="click" @command="handleUserCommand">
              <div class="user-chip">
                <el-avatar :size="32" :icon="UserFilled" />
                <div class="user-info">
                  <span class="user-name">{{ userStore.username || t('userMenu.unnamed') }}</span>
                  <span class="user-role">{{ userStore.isAdmin ? t('userMenu.roleAdmin') : t('userMenu.roleUser') }}</span>
                </div>
                <el-icon><CaretBottom /></el-icon>
              </div>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item disabled>
                    <span>{{ userStore.username }}</span>
                  </el-dropdown-item>
                  <el-dropdown-item divided disabled>
                    <el-icon><Coin /></el-icon>
                    <span>{{ t('userMenu.creditsText') }}{{ creditsText }}</span>
                  </el-dropdown-item>
                  <el-dropdown-item divided command="logout">
                    <el-icon><SwitchButton /></el-icon>
                    <span>{{ t('userMenu.logout') }}</span>
                  </el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </template>
          <template v-else>
            <el-button type="primary" @click="router.push('/login')">
              <el-icon><User /></el-icon>
              <span>{{ t('userMenu.loginRegister') }}</span>
            </el-button>
          </template>

          <LanguageSwitcher />
        </div>
      </header>

      <!-- 主内容区（keep-alive 保持组件状态，切换标签页时不丢失流式输出等内容） -->
      <!-- canvas 路由时去掉 padding/max-width，让画布全屏工作 -->
      <main class="app-main" :class="{ 'canvas-mode': isCanvasRoute }">
        <router-view v-slot="{ Component }">
          <keep-alive :include="cachedViews">
            <component :is="Component" />
          </keep-alive>
        </router-view>
      </main>

      <!-- 全局任务队列悬浮面板（路由切换时不销毁） -->
      <TaskQueuePanel />

      <!-- 页脚 -->
      <footer class="app-footer">
        <span>{{ t('app.footer') }}</span>
      </footer>
    </div>
  </el-config-provider>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  Picture, VideoPlay, Clock, ChatDotRound, Grid, Setting,
  User, UserFilled, Coin, CaretBottom, SwitchButton
} from '@element-plus/icons-vue'
import TaskQueuePanel from './components/TaskQueuePanel.vue'
import LanguageSwitcher from './components/LanguageSwitcher.vue'
import { useI18n, getElementPlusLocale } from '@/i18n'
import { useModelsStore } from '@/stores/models'
import { useUserStore } from '@/stores/user'

const { t, locale } = useI18n()
const route = useRoute()
const router = useRouter()

const modelsStore = useModelsStore()
const userStore = useUserStore()

// 应用启动时加载模型配置
onMounted(() => {
  modelsStore.fetchConfig()
})

// canvas 路由时 app-main 全屏无边距
const isCanvasRoute = computed(() => route.name === 'canvas')

// keep-alive 缓存的路由组件名称（切换标签页时保持状态不销毁）
const cachedViews = ['ChatView', 'ImageView', 'VideoView', 'HistoryView', 'CanvasView', 'SettingsView', 'UsersAdminView', 'CreditRulesView']

// 积分显示：数字千分位格式化
const creditsText = computed(() => {
  const value = userStore.credits
  if (value === null || value === undefined) return '—'
  return value.toLocaleString('en-US')
})

// 用户下拉菜单操作
function handleUserCommand(cmd: string) {
  if (cmd === 'logout') {
    userStore.logout()
    router.push('/login')
  }
}

// 每当 locale 变化时返回对应的 Element Plus 语言对象
const epLocale = computed(() => {
  const _ = locale.value // eslint-disable-line no-unused-vars
  return getElementPlusLocale()
})
</script>

<style scoped>
/* =====================================================
 * 全局布局样式（沿用原项目深色主题设计风格）
 * ===================================================== */
.app-root {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  background: linear-gradient(135deg, #0b0f1a 0%, #101827 50%, #0b0f1a 100%);
  color: #e8eef7;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC",
    "Microsoft YaHei", sans-serif;
}

/* ---- 顶部栏 ---- */
.app-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 18px 32px;
  background: rgba(15, 22, 38, 0.75);
  border-bottom: 1px solid rgba(100, 150, 220, 0.18);
  backdrop-filter: blur(12px);
  position: sticky;
  top: 0;
  z-index: 100;
}

.app-brand {
  display: flex;
  align-items: center;
  gap: 14px;
}

.brand-icon {
  font-size: 36px;
  filter: drop-shadow(0 0 12px rgba(120, 180, 255, 0.45));
}

.brand-text h1 {
  margin: 0;
  font-size: 20px;
  font-weight: 700;
  background: linear-gradient(90deg, #a0d4ff 0%, #c9b3ff 100%);
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
  letter-spacing: 0.5px;
}

.brand-sub {
  margin: 4px 0 0;
  font-size: 12px;
  color: #8ba3c9;
}

/* ---- 导航 ---- */
.app-nav {
  display: flex;
  gap: 8px;
  background: rgba(20, 30, 50, 0.55);
  padding: 6px;
  border-radius: 12px;
  border: 1px solid rgba(100, 150, 220, 0.12);
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  color: #a0b4d6;
  text-decoration: none;
  border-radius: 8px;
  font-size: 14px;
  transition: all 0.2s ease;
}

.nav-item:hover {
  color: #fff;
  background: rgba(120, 170, 255, 0.08);
}

.nav-item.active {
  color: #fff;
  background: linear-gradient(135deg, rgba(80, 140, 255, 0.3) 0%, rgba(160, 120, 255, 0.3) 100%);
  box-shadow: 0 0 20px rgba(100, 150, 255, 0.18);
}

.app-header-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

/* ---- 积分显示 chip ---- */
.credits-chip {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  background: linear-gradient(135deg, rgba(255, 188, 90, 0.18) 0%, rgba(255, 152, 200, 0.12) 100%);
  border: 1px solid rgba(255, 190, 120, 0.3);
  border-radius: 10px;
  color: #ffd28a;
  font-size: 14px;
}
.credits-chip .el-icon {
  font-size: 16px;
}
.credits-value {
  font-weight: 700;
  color: #fff2cf;
}
.credits-label {
  font-size: 12px;
  color: rgba(255, 220, 160, 0.7);
  margin-left: 2px;
}

/* ---- 用户头像 chip ---- */
.user-chip {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 12px 6px 6px;
  background: rgba(20, 30, 50, 0.7);
  border: 1px solid rgba(100, 150, 220, 0.15);
  border-radius: 10px;
  cursor: pointer;
  transition: all 0.2s ease;
}
.user-chip:hover {
  background: rgba(30, 45, 75, 0.8);
  border-color: rgba(100, 150, 220, 0.3);
}
.user-info {
  display: flex;
  flex-direction: column;
  line-height: 1.2;
}
.user-name {
  font-size: 14px;
  font-weight: 600;
  color: #e8eef7;
}
.user-role {
  font-size: 11px;
  color: #8ba3c9;
}
.user-chip .el-icon:last-child {
  color: #8ba3c9;
  font-size: 12px;
}

/* ---- 主内容 ---- */
.app-main {
  flex: 1;
  padding: 28px 32px;
  max-width: 1600px;
  width: 100%;
  margin: 0 auto;
  box-sizing: border-box;
}

/* canvas 路由：全屏工作区，去掉 padding 和 max-width */
.app-main.canvas-mode {
  padding: 0;
  max-width: none;
  position: relative;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

/* ---- 页脚 ---- */
.app-footer {
  padding: 20px 32px;
  text-align: center;
  font-size: 12px;
  color: #6b84aa;
  border-top: 1px solid rgba(120, 150, 225, 0.1);
}

/* ---- 过渡动画 ---- */
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

/* ---- 响应式 ---- */
@media (max-width: 900px) {
  .app-header {
    flex-direction: column;
    gap: 16px;
    padding: 16px;
  }
  .app-main {
    padding: 16px;
  }
}
</style>
