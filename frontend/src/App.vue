<!-- =====================================================
     Agnes AI Platform 根组件
     - 火山引擎风格布局：顶部大类导航 + 左上角可展开侧边栏
     - 顶部放高频核心功能（AI对话/图片/视频），支持下拉展开子项
     - 左上角菜单按钮点击展开完整侧边栏，展示全部功能
     - 通过 <el-config-provider> 响应式切换 Element Plus 语言
     - 管理员菜单在侧边栏分组显示
     - 登录页 / 首页等独立全屏页面不显示标题栏
     - 顶部栏右侧提供全局深色/浅色主题切换按钮
     ===================================================== -->

<template>
  <el-config-provider :locale="epLocale">
    <div class="app-root" :class="{ 'no-header': isStandaloneRoute, 'sidebar-open': sidebarOpen }">
      <!-- 侧边栏遮罩层 -->
      <div v-if="!isStandaloneRoute && sidebarOpen" class="sidebar-overlay" @click="sidebarOpen = false"></div>

      <!-- 左侧可展开侧边栏（全部功能菜单） -->
      <aside v-if="!isStandaloneRoute" class="app-sidebar" :class="{ open: sidebarOpen }">
        <div class="sidebar-header">
          <div class="sidebar-brand">
            <el-icon class="brand-icon"><MagicStick /></el-icon>
            <span class="brand-text">Agnes AI</span>
          </div>
        </div>

        <div class="sidebar-content">
          <!-- 动态渲染侧边栏：一级分组可收缩，二级是菜单项 -->
          <el-menu
            :default-active="route.path"
            class="sidebar-menu"
            background-color="transparent"
            text-color="var(--agnes-text-secondary)"
            active-text-color="var(--agnes-text-primary)"
            :unique-opened="false"
            router
          >
            <el-sub-menu
              v-for="groupData in menuStore.sidebarGroups"
              :key="groupData.key"
              :index="`group-${groupData.key}`"
              v-show="groupData.items.length > 0"
            >
              <template #title>
                <el-icon><component :is="getIcon(groupData.icon)" /></el-icon>
                <span>{{ groupData.label }}</span>
              </template>
              <el-menu-item
                v-for="item in groupData.items"
                :key="item.key"
                :index="item.path"
                @click="sidebarOpen = false"
              >
                <el-icon v-if="getIcon(item.icon)"><component :is="getIcon(item.icon)" /></el-icon>
                <template #title>{{ item.label }}</template>
              </el-menu-item>
            </el-sub-menu>
          </el-menu>
        </div>
      </aside>

      <!-- 顶部栏（登录页 / 首页等独立全屏页面不显示） -->
      <header v-if="!isStandaloneRoute" class="app-header">
        <!-- 左上角：菜单按钮 + 品牌 -->
        <div class="app-header-left">
          <button class="menu-toggle-btn" @click="sidebarOpen = !sidebarOpen">
            <el-icon><Fold v-if="sidebarOpen" /><Expand v-else /></el-icon>
          </button>
          <div class="app-brand" @click="router.push('/')" style="cursor: pointer">
            <el-icon class="brand-icon"><MagicStick /></el-icon>
            <h1>Agnes AI</h1>
          </div>
        </div>

        <!-- 中间：顶部大类导航（高频核心功能） -->
        <nav class="app-nav">
          <router-link
            v-for="item in menuStore.topNav"
            :key="item.key"
            :to="item.path"
            class="nav-item"
            active-class="active"
          >
            <el-icon v-if="getIcon(item.icon)"><component :is="getIcon(item.icon)" /></el-icon>
            <span>{{ item.label }}</span>
          </router-link>
        </nav>

        <!-- 右上角：全局操作区 -->
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
            <button class="icon-btn" @click="themeStore.toggle()">
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
      <main class="app-main" :class="{ 'canvas-mode': isCanvasRoute, 'standalone': isStandaloneRoute, 'sidebar-shift': !isStandaloneRoute && sidebarOpen }">
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
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'
import {
  Picture, VideoPlay, Clock, ChatDotRound, Grid, Setting,
  User, UserFilled, Coin, CaretBottom, SwitchButton, Sunny, Moon, StarFilled, Histogram,
  MagicStick, Fold, Expand, ArrowDown, Message, EditPen, Connection,
} from '@element-plus/icons-vue'
import TaskQueuePanel from './components/TaskQueuePanel.vue'
import LanguageSwitcher from './components/LanguageSwitcher.vue'
import { useI18n, getElementPlusLocale } from '@/i18n'
import { useModelsStore } from '@/stores/models'
import { useUserStore } from '@/stores/user'
import { useThemeStore } from '@/stores/theme'
import { useCanvasStore } from '@/stores/canvas'
import { usePermissionStore } from '@/stores/permission'
import { useMenuStore } from '@/stores/menu'

const { t, locale } = useI18n()
const route = useRoute()
const router = useRouter()

const modelsStore = useModelsStore()
const userStore = useUserStore()
const themeStore = useThemeStore()
const canvasStore = useCanvasStore()
const permissionStore = usePermissionStore()
const menuStore = useMenuStore()

// 侧边栏展开状态
const sidebarOpen = ref(false)

// =====================================================
// 图标组件映射（字符串 → 组件）
// =====================================================
const iconMap: Record<string, any> = {
  ChatDotRound,
  Picture,
  VideoPlay,
  Clock,
  Grid,
  Setting,
  Coin,
  Histogram,
  User,
  UserFilled,
  StarFilled,
  Message,
  EditPen,
  Connection,
}

/** 根据图标名称获取组件 */
function getIcon(iconName: string | null | undefined) {
  if (!iconName) return null
  // 优先使用本地映射，找不到则从全部图标中取
  return iconMap[iconName] || (ElementPlusIconsVue as any)[iconName] || null
}

// 应用启动时加载模型配置和菜单
onMounted(async () => {
  modelsStore.fetchConfig()
  await menuStore.fetchMenus()
})

// 用户登录状态变化时刷新菜单（确保管理员菜单正确显示）
watch(() => userStore.isAuthenticated, async (isAuth) => {
  if (isAuth) {
    menuStore.clearCache()
    await menuStore.fetchMenus(false)
  } else {
    menuStore.clearCache()
    await menuStore.fetchMenus(false)
  }
})

// 全局主题变化时同步到画布（标题栏切换主题 → 画布跟着变）
// 使用 syncFromGlobalTheme 避免循环调用（canvas.setThemeMode 会反向调用 theme.setMode）
// immediate: true 让应用启动时（themeStore.init 恢复 localStorage 主题后）立即同步一次到画布，
// 否则 watch 默认 lazy，首次进入 canvas 页面前画布主题不会跟随全局主题
watch(() => themeStore.mode, (newMode) => {
  canvasStore.syncFromGlobalTheme(newMode)
}, { immediate: true })

// 路由变化时自动关闭侧边栏（移动端体验）
watch(() => route.path, () => {
  if (window.innerWidth < 768) {
    sidebarOpen.value = false
  }
})

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
const cachedViews = ['ChatView', 'ImageView', 'VideoView', 'HistoryView', 'PlazaView', 'CanvasView', 'SettingsView', 'UsersAdminView', 'CreditRulesView', 'ProfileView', 'PreferencesView', 'CreditsView']

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

// 每当 locale 变化时返回对应的 Element Plus 语言对象
const epLocale = computed(() => {
  const _ = locale.value // eslint-disable-line no-unused-vars
  return getElementPlusLocale()
})
</script>

<style scoped>
/* =====================================================
 * 全局布局样式（火山引擎风格：顶部大类导航 + 可展开侧边栏）
 * 依赖 CSS 变量，自动响应深色/浅色主题
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

/* ---- 侧边栏遮罩 ---- */
.sidebar-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.4);
  z-index: 998;
  opacity: 0;
  animation: fadeIn 0.2s ease forwards;
}

@keyframes fadeIn {
  to {
    opacity: 1;
  }
}

/* ---- 左侧侧边栏 ---- */
.app-sidebar {
  position: fixed;
  top: 0;
  left: 0;
  bottom: 0;
  width: 260px;
  background: var(--agnes-bg-elevated);
  border-right: 1px solid var(--agnes-border-strong);
  z-index: 999;
  transform: translateX(-100%);
  transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  display: flex;
  flex-direction: column;
  backdrop-filter: blur(12px);
}

.app-sidebar.open {
  transform: translateX(0);
  box-shadow: 4px 0 24px rgba(0, 0, 0, 0.12);
}

.sidebar-header {
  padding: 16px 20px;
  border-bottom: 1px solid var(--agnes-border-faint);
}

.sidebar-brand {
  display: flex;
  align-items: center;
  gap: 10px;
}

.sidebar-brand .brand-icon {
  font-size: 22px;
  color: var(--agnes-accent);
  filter: drop-shadow(0 0 10px var(--agnes-brand-glow));
}

.sidebar-brand .brand-text {
  font-size: 17px;
  font-weight: 700;
  background: var(--agnes-brand-gradient);
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
  letter-spacing: 0.3px;
}

.sidebar-content {
  flex: 1;
  overflow-y: auto;
  padding: 8px 8px;
}

/* 侧边栏菜单样式（覆盖 Element Plus 默认样式适配主题） */
.sidebar-menu {
  border-right: none !important;
}

.sidebar-menu :deep(.el-sub-menu__title) {
  height: 40px;
  line-height: 40px;
  border-radius: 8px;
  margin-bottom: 2px;
  color: var(--agnes-text-secondary);
  font-weight: 500;
}

.sidebar-menu :deep(.el-sub-menu__title:hover) {
  background: var(--agnes-nav-hover-bg) !important;
  color: var(--agnes-text-primary) !important;
}

.sidebar-menu :deep(.el-sub-menu.is-active > .el-sub-menu__title) {
  color: var(--agnes-text-primary) !important;
}

.sidebar-menu :deep(.el-menu-item) {
  height: 38px;
  line-height: 38px;
  border-radius: 8px;
  margin: 0 4px 2px 4px;
  color: var(--agnes-text-secondary);
  font-size: 14px;
}

.sidebar-menu :deep(.el-menu-item:hover) {
  background: var(--agnes-nav-hover-bg) !important;
  color: var(--agnes-text-primary) !important;
}

.sidebar-menu :deep(.el-menu-item.is-active) {
  background: var(--agnes-nav-active-bg) !important;
  color: var(--agnes-text-primary) !important;
  font-weight: 500;
}

.sidebar-menu :deep(.el-sub-menu .el-menu) {
  background: transparent !important;
}

.sidebar-menu :deep(.el-menu-item .el-icon),
.sidebar-menu :deep(.el-sub-menu__title .el-icon) {
  font-size: 18px;
  margin-right: 10px;
  color: inherit;
}

.sidebar-menu :deep(.el-sub-menu__icon-arrow) {
  font-size: 12px;
  color: var(--agnes-text-muted);
}

/* ---- 顶部栏 ---- */
.app-header {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 10px 20px;
  background: var(--agnes-bg-elevated);
  border-bottom: 1px solid var(--agnes-border-strong);
  backdrop-filter: blur(12px);
  position: sticky;
  top: 0;
  z-index: 100;
  transition: background 0.3s ease, border-color 0.3s ease;
}

.app-header-left {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-shrink: 0;
}

/* 菜单展开按钮 */
.menu-toggle-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border-radius: 8px;
  background: transparent;
  border: none;
  color: var(--agnes-text-secondary);
  cursor: pointer;
  transition: all 0.2s ease;
  font-size: 18px;
}

.menu-toggle-btn:hover {
  background: var(--agnes-bg-hover);
  color: var(--agnes-text-primary);
}

.app-brand {
  display: flex;
  align-items: center;
  gap: 10px;
}

.app-brand .brand-icon {
  font-size: 22px;
  color: var(--agnes-accent);
  filter: drop-shadow(0 0 10px var(--agnes-brand-glow));
}

.app-brand h1 {
  margin: 0;
  font-size: 17px;
  font-weight: 700;
  background: var(--agnes-brand-gradient);
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
  letter-spacing: 0.3px;
  white-space: nowrap;
}

/* ---- 顶部导航（大类） ---- */
.app-nav {
  display: flex;
  gap: 2px;
  flex: 1;
  justify-content: center;
  min-width: 0;
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
  transition: all 0.15s ease;
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
  font-weight: 500;
}

.nav-item.has-dropdown {
  padding-right: 10px;
}

.dropdown-arrow {
  font-size: 12px;
  margin-left: 2px;
  transition: transform 0.2s ease;
}

/* 顶部导航下拉菜单样式 */
:deep(.nav-dropdown-popper) {
  padding: 6px !important;
  border-radius: 10px !important;
  border: 1px solid var(--agnes-border) !important;
  background: var(--agnes-bg-elevated) !important;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.12) !important;
}

:deep(.nav-dropdown-menu) {
  padding: 0;
  background: transparent;
  border: none;
}

.nav-dropdown-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  color: var(--agnes-text-secondary);
  text-decoration: none;
  border-radius: 6px;
  font-size: 14px;
  transition: all 0.15s ease;
  cursor: pointer;
}

.nav-dropdown-item:hover {
  color: var(--agnes-text-primary);
  background: var(--agnes-nav-hover-bg);
}

.nav-dropdown-item .el-icon {
  font-size: 16px;
}

.app-header-right {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

/* ---- 通用图标按钮 ---- */
.icon-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border-radius: 8px;
  background: transparent;
  border: none;
  color: var(--agnes-text-secondary);
  cursor: pointer;
  transition: all 0.2s ease;
  font-size: 18px;
}
.icon-btn:hover {
  background: var(--agnes-bg-hover);
  color: var(--agnes-text-primary);
}

/* ---- 积分显示 chip（可点击跳转到积分明细） ---- */
.credits-chip {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 7px 12px;
  background: var(--agnes-credits-bg);
  border: 1px solid var(--agnes-credits-border);
  border-radius: 8px;
  color: var(--agnes-credits-text);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s ease;
  flex-shrink: 0;
  white-space: nowrap;
}
.credits-chip:hover {
  background: var(--agnes-credits-bg-hover);
  box-shadow: 0 0 12px rgba(255, 190, 120, 0.2);
}
.credits-chip .el-icon {
  font-size: 15px;
}
.credits-value {
  font-weight: 700;
  font-size: 14px;
  color: var(--agnes-credits-value);
  font-variant-numeric: tabular-nums;
  letter-spacing: 0.3px;
}
.credits-label {
  font-size: 11px;
  color: var(--agnes-credits-label);
  margin-left: 2px;
}

/* ---- 用户头像 chip ---- */
.user-chip {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 10px 4px 4px;
  background: var(--agnes-bg-chip);
  border: 1px solid var(--agnes-border-faint);
  border-radius: 8px;
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
  max-width: 100px;
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
  padding: 24px 28px;
  max-width: 1600px;
  width: 100%;
  margin: 0 auto;
  box-sizing: border-box;
  transition: padding 0.3s ease;
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
  padding: 16px 32px;
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
/* 中等屏幕：压缩间距 */
@media (max-width: 1200px) {
  .app-brand h1 {
    display: none;
  }
  .nav-item {
    padding: 8px 10px;
    font-size: 13px;
  }
  .credits-label {
    display: none;
  }
}

/* 较小屏幕：顶部导航只显示图标 */
@media (max-width: 900px) {
  .app-header {
    padding: 10px 12px;
    gap: 8px;
  }
  .nav-item span:not(.dropdown-arrow) {
    display: none;
  }
  .nav-item {
    padding: 8px;
  }
  .user-name {
    display: none;
  }
  .app-main {
    padding: 16px;
  }
}

/* 小屏幕：侧边栏全宽 */
@media (max-width: 600px) {
  .app-sidebar {
    width: 85vw;
  }
  .app-header-right .el-button span {
    display: none;
  }
}
</style>
