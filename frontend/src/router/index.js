/* =====================================================
 * Vue Router 路由配置
 * 三个页面：图片生成 / 视频生成 / 生成历史
 * ===================================================== */

import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  {
    path: '/',
    redirect: '/images'
  },
  {
    path: '/images',
    name: 'images',
    component: () => import('@/views/ImageView.vue'),
    meta: { title: '图片生成' }
  },
  {
    path: '/videos',
    name: 'videos',
    component: () => import('@/views/VideoView.vue'),
    meta: { title: '视频生成' }
  },
  {
    path: '/history',
    name: 'history',
    component: () => import('@/views/HistoryView.vue'),
    meta: { title: '生成历史' }
  },
  // 兜底路由
  {
    path: '/:pathMatch(.*)*',
    redirect: '/images'
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

// 动态设置页面标题
router.afterEach((to) => {
  const title = to.meta?.title
  if (title) {
    document.title = `${title} · Agnes AI Platform`
  }
})

export default router
