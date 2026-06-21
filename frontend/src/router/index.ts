/* =====================================================
 * Vue Router 路由配置
 * 页面：登录、图片生成 / 视频生成 / 聊天 / 画布 / 历史 / 设置
 * 管理员页：用户与角色管理 / 积分规则配置
 * - requiresAuth 路由：未登录时自动跳转到登录页
 * - requiresAdmin 路由：非管理员访问时 403 并跳转首页
 * - 所有业务页（chat/images/videos/history/canvas/settings）均需登录
 * ===================================================== */

import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import { useI18n } from '@/i18n'
import { useUserStore } from '@/stores/user'

// ---------- 路由列表 ----------
const routes: RouteRecordRaw[] = [
  {
    path: '/',
    redirect: '/chat'
  },
  // 登录 / 注册页 — 未登录时可达，已登录访问则直接跳转到业务页
  {
    path: '/login',
    name: 'login',
    component: () => import('@/views/LoginView.vue'),
    meta: { titleKey: 'router.login', requiresAuth: false }
  },
  {
    path: '/chat',
    name: 'chat',
    component: () => import('@/views/ChatView.vue'),
    meta: { titleKey: 'router.chat', requiresAuth: true }
  },
  {
    path: '/images',
    name: 'images',
    component: () => import('@/views/ImageView.vue'),
    meta: { titleKey: 'router.images', requiresAuth: true }
  },
  {
    path: '/videos',
    name: 'videos',
    component: () => import('@/views/VideoView.vue'),
    meta: { titleKey: 'router.videos', requiresAuth: true }
  },
  {
    path: '/history',
    name: 'history',
    component: () => import('@/views/HistoryView.vue'),
    meta: { titleKey: 'router.history', requiresAuth: true }
  },
  {
    path: '/canvas',
    name: 'canvas',
    component: () => import('@/views/CanvasView.vue'),
    meta: { titleKey: 'router.canvas', requiresAuth: true }
  },
  {
    path: '/credits',
    name: 'credits',
    component: () => import('@/views/CreditsView.vue'),
    meta: { titleKey: 'router.credits', requiresAuth: true }
  },
  {
    path: '/settings',
    name: 'settings',
    component: () => import('@/views/SettingsView.vue'),
    meta: { titleKey: 'router.settings', requiresAuth: true, requiresAdmin: true }
  },
  // ---------- 管理员页（需登录 + 管理员角色） ----------
  {
    path: '/admin/users',
    name: 'admin-users',
    component: () => import('@/views/UsersAdminView.vue'),
    meta: { title: '用户与角色管理', requiresAuth: true, requiresAdmin: true }
  },
  {
    path: '/admin/credit-rules',
    name: 'admin-credit-rules',
    component: () => import('@/views/CreditRulesView.vue'),
    meta: { title: '积分规则配置', requiresAuth: true, requiresAdmin: true }
  },
  // 兜底路由
  {
    path: '/:pathMatch(.*)*',
    redirect: '/chat'
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

// ---------- 全局前置守卫：登录 / 角色权限判断 ----------
// 异步守卫：等待 userStore.init() 完成后再判断登录状态
// 否则刷新页面时 token/user 还没从 localStorage 恢复，会被误判为未登录
router.beforeEach(async (to, _from, next) => {
  const userStore = useUserStore()
  // 等待 init() 完成（首次刷新页面时关键）
  await userStore.ready()
  const requiresAuth = to.meta?.requiresAuth === true
  const requiresAdmin = to.meta?.requiresAdmin === true

  // 已登录用户访问登录页 — 直接进入业务页
  if (to.name === 'login' && userStore.isAuthenticated) {
    return next('/images')
  }

  // 需要登录但未登录 — 跳转到登录页，带上 redirect
  if (requiresAuth && !userStore.isAuthenticated) {
    const query = to.fullPath !== '/login' && to.fullPath !== '/'
      ? { redirect: to.fullPath }
      : undefined
    return next({ path: '/login', query })
  }

  // 需要管理员角色但当前用户不是管理员 — 跳转首页
  if (requiresAdmin && !userStore.isAdmin) {
    return next('/chat')
  }

  next()
})

// ---------- 全局后置守卫：动态设置 document.title ----------
router.afterEach((to) => {
  const key = to.meta?.titleKey as string | undefined
  if (key) {
    const { t } = useI18n()
    const title = t(key)
    document.title = `${title} · Agnes AI Platform`
  } else if (to.meta?.title) {
    document.title = `${to.meta.title} · Agnes AI Platform`
  }
})

export default router
