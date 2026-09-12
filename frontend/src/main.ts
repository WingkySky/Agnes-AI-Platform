/* =====================================================
 * Agnes AI Platform 前端入口
 * - 挂载 Vue 应用
 * - 初始化 Element Plus（语言随 i18n 响应式变化）
 * - 初始化 Vue Router 与 Pinia
 * ===================================================== */

import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import 'element-plus/theme-chalk/dark/css-vars.css'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'

import App from './App.vue'
import router from './router'
import './assets/main.css'
import { useTaskQueueStore } from './stores/taskQueue'
import { useUserStore } from './stores/user'
import { useThemeStore } from './stores/theme'

// 国际化（i18n）插件
import i18n from '@/i18n'
// 权限插件
import permissionPlugin from '@/plugins/permission'

// 创建 Vue 应用
const app = createApp(App)

// 全局注册所有 Element Plus 图标组件
for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(key, component)
}

// 注册插件
app.use(createPinia())
app.use(router)
// 使用 Element Plus（默认语言通过 <el-config-provider 覆盖）
app.use(ElementPlus)
// 挂载 i18n 插件：提供 $t 全局属性
app.use(i18n)
// 挂载权限插件：提供 v-permission 指令和 $hasPerm 全局方法
app.use(permissionPlugin)

// 初始化全局主题（从 localStorage 恢复深色/浅色，同步到 <html> class）
// 必须在 mount 之前完成，避免页面闪烁
const themeStore = useThemeStore()
themeStore.init()

// 初始化用户认证 Store（恢复本地 JWT + 尝试获取当前用户信息）
// 不需要 await：路由守卫会通过 userStore.ready() 等待 init 完成
// 这里只需在 mount 之前触发 init，让 ready promise 开始推进
const userStore = useUserStore()
userStore.init()

app.mount('#app')

// 初始化全局任务队列 Store（恢复历史任务 + 启动后台轮询）
const taskQueue = useTaskQueueStore()
taskQueue.init()
