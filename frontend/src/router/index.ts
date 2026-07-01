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
import { usePermissionStore } from '@/stores/permission'

// ---------- 路由列表 ----------
const routes: RouteRecordRaw[] = [
  {
    path: '/',
    name: 'home',
    component: () => import('@/views/HomeView.vue'),
    meta: { titleKey: 'router.home', requiresAuth: false }
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
    path: '/plaza',
    name: 'plaza',
    component: () => import('@/views/PlazaView.vue'),
    meta: { titleKey: 'router.plaza', requiresAuth: false }
  },
  {
    path: '/canvas',
    name: 'canvas',
    component: () => import('@/views/CanvasView.vue'),
    meta: { titleKey: 'router.canvas', requiresAuth: true }
  },
  {
    path: '/workshop',
    name: 'workshop',
    component: () => import('@/views/WorkshopView.vue'),
    meta: { titleKey: 'router.workshop', requiresAuth: true, permission: 'pipeline:run' }
  },
  // ---------- 3D 场景导演台：用 3D 空间布局生成可控的镜头语言 prompt ----------
  {
    path: '/scene-editor',
    name: 'scene-editor',
    component: () => import('@/views/SceneEditorView.vue'),
    meta: { titleKey: 'router.sceneEditor', requiresAuth: true }
  },
  {
    path: '/workshop/run/:templateId',
    name: 'pipeline-run',
    component: () => import('@/views/PipelineRunView.vue'),
    meta: { titleKey: 'router.pipelineRun', requiresAuth: true, permission: 'pipeline:run' }
  },
  {
    path: '/workshop/result/:runId',
    name: 'pipeline-result',
    component: () => import('@/views/PipelineResultView.vue'),
    meta: { titleKey: 'router.pipelineResult', requiresAuth: true, permission: 'pipeline:run' }
  },
  {
    path: '/workshop/template/create',
    name: 'template-create',
    component: () => import('@/views/TemplateEditorView.vue'),
    meta: { titleKey: 'router.templateCreate', requiresAuth: true, permission: 'pipeline:run' }
  },
  {
    path: '/workshop/template/:id/edit',
    name: 'template-edit',
    component: () => import('@/views/TemplateEditorView.vue'),
    meta: { titleKey: 'router.templateEdit', requiresAuth: true, permission: 'pipeline:run' }
  },
  {
    path: '/workshop/wizard',
    name: 'template-wizard',
    component: () => import('@/views/TemplateWizardView.vue'),
    meta: { titleKey: 'router.templateWizard', requiresAuth: true, permission: 'pipeline:run' }
  },
  {
    path: '/workshop/history',
    name: 'pipeline-history',
    component: () => import('@/views/PipelineHistoryView.vue'),
    meta: { titleKey: 'router.pipelineHistory', requiresAuth: true, permission: 'pipeline:run' }
  },
  {
    path: '/assets',
    name: 'assets',
    component: () => import('@/views/AssetsView.vue'),
    meta: { titleKey: 'router.assets', requiresAuth: true, permission: 'pipeline:save_asset' }
  },
  // ---------- 提示词预设中心（统一入口，覆盖 camera/prompt/style/script/pipeline 全类型） ----------
  {
    path: '/presets',
    name: 'presets',
    component: () => import('@/views/presets/PresetCenter.vue'),
    meta: { titleKey: 'router.presets', requiresAuth: true }
  },
  {
    path: '/credits',
    name: 'credits',
    component: () => import('@/views/CreditsView.vue'),
    meta: { titleKey: 'router.credits', requiresAuth: true }
  },
  {
    path: '/profile',
    name: 'profile',
    component: () => import('@/views/ProfileView.vue'),
    meta: { titleKey: 'router.profile', requiresAuth: true }
  },
  {
    path: '/preferences',
    name: 'preferences',
    component: () => import('@/views/PreferencesView.vue'),
    meta: { titleKey: 'router.preferences', requiresAuth: true }
  },
  {
    path: '/settings',
    name: 'settings',
    redirect: '/admin/models'
  },
  // ---------- 管理员页（需登录 + 对应权限） ----------
  // 统一使用 /admin 前缀，通过 AdminLayout 布局（左侧边栏 + 右侧内容）
  {
    path: '/admin',
    component: () => import('@/views/AdminLayout.vue'),
    meta: { requiresAuth: true },
    children: [
      {
        path: 'review',
        name: 'admin-review',
        component: () => import('@/views/admin/UnifiedReview.vue'),
        meta: { titleKey: 'nav.unifiedReview', requiresAdmin: true }
      },
      {
        path: 'sensitive-words',
        name: 'admin-sensitive-words',
        component: () => import('@/views/SensitiveWordsView.vue'),
        meta: { titleKey: 'nav.sensitiveWords', permission: 'moderation:config' }
      },
      {
        path: 'roles',
        name: 'admin-roles',
        component: () => import('@/views/RolesAdminView.vue'),
        meta: { titleKey: 'nav.roleManage', permission: 'role:manage' }
      },
      {
        path: 'users',
        name: 'admin-users',
        component: () => import('@/views/UsersAdminView.vue'),
        meta: { titleKey: 'nav.usersAdmin', requiresAdmin: true }
      },
      {
        path: 'watermark',
        name: 'admin-watermark',
        component: () => import('@/views/WatermarkConfigView.vue'),
        meta: { titleKey: 'nav.watermarkConfig', permission: 'watermark:manage' }
      },
      {
        path: 'credit-rules',
        name: 'admin-credit-rules',
        component: () => import('@/views/CreditRulesView.vue'),
        meta: { titleKey: 'nav.creditRules', requiresAdmin: true }
      },
      {
        path: 'models',
        name: 'admin-models',
        component: () => import('@/views/SettingsView.vue'),
        meta: { titleKey: 'admin.modelConfig', requiresAdmin: true }
      },
      {
        path: 'email',
        name: 'admin-email',
        component: () => import('@/views/EmailConfigView.vue'),
        meta: { titleKey: 'admin.smtp.title', requiresAdmin: true }
      },
      {
        path: 'menus',
        name: 'admin-menus',
        component: () => import('@/views/MenuAdminView.vue'),
        meta: { titleKey: 'nav.menuAdmin', requiresAdmin: true }
      },
      {
        path: 'presets',
        name: 'admin-presets',
        component: () => import('@/views/presets/PresetCenter.vue'),
        meta: { titleKey: 'nav.presetsAdmin', requiresAdmin: true }
      },
    ]
  },
  // 兜底路由
  {
    path: '/:pathMatch(.*)*',
    redirect: '/'
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
  const permissionStore = usePermissionStore()
  // 等待 init() 完成（首次刷新页面时关键）
  await userStore.ready()
  const requiresAuth = to.meta?.requiresAuth === true
  const requiresAdmin = to.meta?.requiresAdmin === true
  const requiredPermission = to.meta?.permission as string | undefined

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

  // 需要特定权限但当前用户没有 — 跳转首页
  if (requiredPermission && !permissionStore.hasPermission(requiredPermission)) {
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
