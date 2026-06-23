<!-- =====================================================
     Agnes AI Platform 根组件
     - 提供主布局（顶部精简导航 + 右侧内容）
     - 通过 <el-config-provider> 响应式切换 Element Plus 语言
     - 右上角 LanguageSwitcher 切换界面语言
     - 管理员菜单（用户管理 / 积分规则 / 配置管理）收起到「管理」下拉
     - 登录页 / 首页等独立全屏页面不显示标题栏
     - 顶部栏右侧提供全局深色/浅色主题切换按钮
     ===================================================== -->

<template>
  <el-config-provider :locale="epLocale">
    <div class="app-root" :class="{ 'no-header': isStandaloneRoute }">
      <!-- 顶部栏（登录页 / 首页等独立全屏页面不显示） -->
      <header v-if="!isStandaloneRoute" class="app-header">
        <div class="app-brand">
          <el-icon class="brand-icon"><MagicStick /></el-icon>
          <h1>Agnes AI Platform</h1>
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
          <router-link to="/plaza" class="nav-item" active-class="active">
            <el-icon><Histogram /></el-icon>
            <span>{{ t('nav.plaza') }}</span>
          </router-link>
          <router-link to="/canvas" class="nav-item" active-class="active">
            <el-icon><Grid /></el-icon>
            <span>{{ t('nav.canvas') }}</span>
          </router-link>
          <!-- 管理员菜单：收起到「管理」下拉 -->
          <el-dropdown
            v-if="userStore.isAuthenticated && (userStore.isAdmin || permissionStore.hasPermission('plaza:moderate') || permissionStore.hasPermission('role:manage') || permissionStore.hasPermission('moderation:config') || permissionStore.hasPermission('watermark:manage'))"
            trigger="click"
            @command="handleAdminCommand">
            <div class="nav-item nav-item-dropdown" :class="{ active: isAdminRouteActive }">
              <el-icon><Setting /></el-icon>
              <span>{{ t('nav.admin') }}</span>
              <el-icon class="caret"><CaretBottom /></el-icon>
            </div>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item v-if="permissionStore.hasPermission('plaza:moderate')" command="/admin/moderation">
                  <el-icon><View /></el-icon>
                  <span>{{ t('nav.moderation') }}</span>
                </el-dropdown-item>
                <el-dropdown-item v-if="permissionStore.hasPermission('moderation:config')" command="/admin/sensitive-words">
                  <el-icon><Warning /></el-icon>
                  <span>{{ t('nav.sensitiveWords') }}</span>
                </el-dropdown-item>
                <el-dropdown-item v-if="permissionStore.hasPermission('role:manage')" command="/admin/roles">
                  <el-icon><UserFilled /></el-icon>
                  <span>{{ t('nav.roleManage') }}</span>
                </el-dropdown-item>
                <el-dropdown-item v-if="userStore.isAdmin" command="/admin/users">
                  <el-icon><UserFilled /></el-icon>
                  <span>{{ t('nav.usersAdmin') }}</span>
                </el-dropdown-item>
                <el-dropdown-item v-if="permissionStore.hasPermission('watermark:manage')" command="/admin/watermark">
                  <el-icon><Picture /></el-icon>
                  <span>{{ t('nav.watermarkConfig') }}</span>
                </el-dropdown-item>
                <el-dropdown-item v-if="userStore.isAdmin" command="/admin/credit-rules">
                  <el-icon><Coin /></el-icon>
                  <span>{{ t('nav.creditRules') }}</span>
                </el-dropdown-item>
                <el-dropdown-item v-if="userStore.isAdmin" command="/settings" divided>
                  <el-icon><Setting /></el-icon>
                  <span>{{ t('nav.settings') }}</span>
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </nav>

        <div class="app-header-right">
          <!-- 积分显示（仅登录后）：点击跳转到积分明细页 -->
          <el-tooltip
            v-if="userStore.isAuthenticated"
            :content="t('userMenu.creditsViewTip')"
            placement="bottom"
          >
            <div class="credits-chip" @click="router.push('/credits')">
              <el-icon><Coin /></el-icon>
              <span class="credits-value">{{ creditsText }}</span>
              <span class="credits-label">{{ t('userMenu.creditsLabel') }}</span>
            </div>
          </el-tooltip>

          <!-- 全局主题切换按钮（深色 / 浅色） -->
          <el-tooltip :content="themeStore.isDark ? t('theme.switchToLight') : t('theme.switchToDark')" placement="bottom">
            <button class="theme-toggle-btn" @click="themeStore.toggle()">
              <el-icon v-if="themeStore.isDark"><Sunny /></el-icon>
              <el-icon v-else><Moon /></el-icon>
            </button>
          </el-tooltip>

          <!-- 登录入口 / 用户菜单 -->
          <template v-if="userStore.isAuthenticated">
            <el-dropdown trigger="click" @command="handleUserCommand">
              <div class="user-chip">
                <el-avatar :size="28" :src="userStore.avatarUrl || undefined" :icon="UserFilled" />
                <span class="user-name">{{ userStore.username || t('userMenu.unnamed') }}</span>
                <el-icon><CaretBottom /></el-icon>
              </div>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item disabled>
                    <span>{{ userStore.username }}</span>
                  </el-dropdown-item>
                  <el-dropdown-item divided command="profile">
                    <el-icon><UserFilled /></el-icon>
                    <span>{{ t('userMenu.profile') }}</span>
                  </el-dropdown-item>
                  <el-dropdown-item command="preferences">
                    <el-icon><StarFilled /></el-icon>
                    <span>{{ t('userMenu.preferences') }}</span>
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
      <main class="app-main" :class="{ 'canvas-mode': isCanvasRoute, 'standalone': isStandaloneRoute }">
        <router-view v-slot="{ Component }">
          <keep-alive :include="cachedViews">
            <component :is="Component" />
          </keep-alive>
        </router-view>
      </main>

      <!-- 全局任务队列悬浮面板（路由切换时不销毁） -->
      <TaskQueuePanel v-if="!isStandaloneRoute" />

      <!-- 页脚（独立全屏页面不显示） -->
      <footer v-if="!isStandaloneRoute" class="app-footer">
        <span>{{ t('app.footer') }}</span>
      </footer>
    </div>
  </el-config-provider>
</template>

<script setup lang="ts">
import { computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  Picture, VideoPlay, Clock, ChatDotRound, Grid, Setting,
  User, UserFilled, Coin, CaretBottom, SwitchButton, Sunny, Moon, StarFilled, Histogram,
  View, Warning,
} from '@element-plus/icons-vue'
import TaskQueuePanel from './components/TaskQueuePanel.vue'
import LanguageSwitcher from './components/LanguageSwitcher.vue'
import { useI18n, getElementPlusLocale } from '@/i18n'
import { useModelsStore } from '@/stores/models'
import { useUserStore } from '@/stores/user'
import { useThemeStore } from '@/stores/theme'
import { useCanvasStore } from '@/stores/canvas'
import { usePermissionStore } from '@/stores/permission'

const { t, locale } = useI18n()
const route = useRoute()
const router = useRouter()

const modelsStore = useModelsStore()
const userStore = useUserStore()
const themeStore = useThemeStore()
const canvasStore = useCanvasStore()
const permissionStore = usePermissionStore()

// 应用启动时加载模型配置
onMounted(() => {
  modelsStore.fetchConfig()
})

// 全局主题变化时同步到画布（标题栏切换主题 → 画布跟着变）
// 使用 syncFromGlobalTheme 避免循环调用（canvas.setThemeMode 会反向调用 theme.setMode）
// immediate: true 让应用启动时（themeStore.init 恢复 localStorage 主题后）立即同步一次到画布，
// 否则 watch 默认 lazy，首次进入 canvas 页面前画布主题不会跟随全局主题
watch(() => themeStore.mode, (newMode) => {
  canvasStore.syncFromGlobalTheme(newMode)
}, { immediate: true })

// canvas 路由时 app-main 全屏无边距
const isCanvasRoute = computed(() => route.name === 'canvas')

// 独立全屏页面（登录页 / 首页）：不显示标题栏、页脚、任务队列面板
const isStandaloneRoute = computed(() => {
  return route.name === 'login' || route.name === 'home'
})

// 管理员下拉是否高亮：当前路由命中任一管理类页面时高亮
const isAdminRouteActive = computed(() => {
  return route.path.startsWith('/admin/') || route.path === '/settings'
})

// keep-alive 缓存的路由组件名称（切换标签页时保持状态不销毁）
const cachedViews = ['ChatView', 'ImageView', 'VideoView', 'HistoryView', 'PlazaView', 'CanvasView', 'SettingsView', 'UsersAdminView', 'CreditRulesView', 'ProfileView', 'PreferencesView']

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
  } else if (cmd === 'profile') {
    router.push('/profile')
  } else if (cmd === 'preferences') {
    router.push('/preferences')
  }
}

// 管理员下拉菜单操作：跳转到对应管理页面
function handleAdminCommand(path: string) {
  router.push(path)
}

// 每当 locale 变化时返回对应的 Element Plus 语言对象
const epLocale = computed(() => {
  const _ = locale.value // eslint-disable-line no-unused-vars
  return getElementPlusLocale()
})
</script>

<style scoped>
/* =====================================================
 * 全局布局样式（依赖 CSS 变量，自动响应深色/浅色主题）
 * ===================================================== */
.app-root {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  background: linear-gradient(135deg, var(--agnes-bg-gradient-1) 0%, var(--agnes-bg-gradient-2) 50%, var(--agnes-bg-gradient-1) 100%);
  color: var(--agnes-text-primary);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC",
    "Microsoft YaHei", sans-serif;
  transition: background 0.3s ease, color 0.3s ease;
}

/* 独立全屏页面（登录页 / 首页）：去掉默认布局约束 */
.app-root.no-header {
  background: var(--agnes-bg-base);
}

/* ---- 顶部栏 ---- */
.app-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 12px 24px;
  background: var(--agnes-bg-elevated);
  border-bottom: 1px solid var(--agnes-border-strong);
  backdrop-filter: blur(12px);
  position: sticky;
  top: 0;
  z-index: 100;
  transition: background 0.3s ease, border-color 0.3s ease;
}

.app-brand {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-shrink: 0;
}

.brand-icon {
  font-size: 24px;
  color: var(--agnes-accent);
  filter: drop-shadow(0 0 12px var(--agnes-brand-glow));
}

.app-brand h1 {
  margin: 0;
  font-size: 18px;
  font-weight: 700;
  background: var(--agnes-brand-gradient);
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
  letter-spacing: 0.5px;
  white-space: nowrap;
}

/* ---- 导航 ---- */
.app-nav {
  display: flex;
  gap: 4px;
  background: var(--agnes-bg-inset);
  padding: 6px;
  border-radius: 12px;
  border: 1px solid var(--agnes-border-faint);
  transition: background 0.3s ease, border-color 0.3s ease;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  color: var(--agnes-text-secondary);
  text-decoration: none;
  border-radius: 8px;
  font-size: 14px;
  transition: all 0.2s ease;
  cursor: pointer;
  white-space: nowrap;
}

.nav-item:hover {
  color: var(--agnes-text-primary);
  background: var(--agnes-nav-hover-bg);
}

.nav-item.active {
  color: var(--agnes-text-primary);
  background: var(--agnes-nav-active-bg);
  box-shadow: var(--agnes-nav-active-shadow);
}

/* 管理员下拉触发器：复用 nav-item 样式，并加上小箭头 */
.nav-item-dropdown .caret {
  font-size: 11px;
  margin-left: 2px;
  color: var(--agnes-text-muted);
}

.app-header-right {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
}

/* ---- 全局主题切换按钮 ---- */
.theme-toggle-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  border-radius: 10px;
  background: var(--agnes-bg-chip);
  border: 1px solid var(--agnes-border);
  color: var(--agnes-text-secondary);
  cursor: pointer;
  transition: all 0.2s ease;
  font-size: 16px;
}
.theme-toggle-btn:hover {
  background: var(--agnes-bg-hover);
  border-color: var(--agnes-primary);
  color: var(--agnes-primary);
  transform: translateY(-1px);
}

/* ---- 积分显示 chip（可点击跳转到积分明细） ---- */
.credits-chip {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  background: var(--agnes-credits-bg);
  border: 1px solid var(--agnes-credits-border);
  border-radius: 10px;
  color: var(--agnes-credits-text);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s ease;
  /* 允许 chip 随数字位数自适应扩展，不被父容器挤压 */
  flex-shrink: 0;
  white-space: nowrap;
}
.credits-chip:hover {
  background: var(--agnes-credits-bg-hover);
  border-color: var(--agnes-credits-border);
  box-shadow: 0 0 12px rgba(255, 190, 120, 0.2);
}
.credits-chip .el-icon {
  font-size: 15px;
}
.credits-value {
  font-weight: 700;
  font-size: 14px;
  color: var(--agnes-credits-value);
  /* 等宽数字，避免位数变化时宽度跳动 */
  font-variant-numeric: tabular-nums;
  letter-spacing: 0.3px;
}
.credits-label {
  font-size: 11px;
  color: var(--agnes-credits-label);
  margin-left: 2px;
}

/* ---- 用户头像 chip（精简版：仅头像 + 用户名 + 下拉箭头） ---- */
.user-chip {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 10px 4px 4px;
  background: var(--agnes-bg-chip);
  border: 1px solid var(--agnes-border-faint);
  border-radius: 10px;
  cursor: pointer;
  transition: all 0.2s ease;
}
.user-chip:hover {
  background: var(--agnes-bg-hover);
  border-color: var(--agnes-border);
}
.user-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--agnes-text-primary);
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.user-chip .el-icon:last-child {
  color: var(--agnes-text-muted);
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

/* 独立全屏页面（登录页 / 首页）：去掉 padding 和 max-width */
.app-main.standalone {
  padding: 0;
  max-width: none;
}

/* ---- 页脚 ---- */
.app-footer {
  padding: 20px 32px;
  text-align: center;
  font-size: 12px;
  color: var(--agnes-text-faint);
  border-top: 1px solid var(--agnes-border-faint);
  transition: color 0.3s ease, border-color 0.3s ease;
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
