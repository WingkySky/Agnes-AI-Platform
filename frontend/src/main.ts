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

// 国际化（i18n）插件
import i18n from '@/i18n'

// 创建 Vue 应用
const app = createApp(App)

// 全局注册所有 Element Plus 图标组件
for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(key, component)
}

// 注册插件
app.use(createPinia())
app.use(router)
// 使用 Element Plus（默认语言通过 <el-config-provider> 覆盖）
app.use(ElementPlus)
// 挂载 i18n 插件：提供 $t 全局属性
app.use(i18n)

// 确保 body 使用深色主题类（Element Plus 会根据 class="dark" 应用深色变量）
document.documentElement.classList.add('dark')

app.mount('#app')

// 初始化全局任务队列 Store（恢复历史任务 + 启动后台轮询）
const taskQueue = useTaskQueueStore()
taskQueue.init()
