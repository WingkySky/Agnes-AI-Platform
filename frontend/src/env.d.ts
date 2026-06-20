/* =====================================================
 * 全局类型声明
 * ===================================================== */

/// <reference types="vite/client" />

/* Vue 组件类型声明 */
declare module '*.vue' {
  import type { DefineComponent } from 'vue'
  const component: DefineComponent<object, object, unknown>
  export default component
}

/* CSS 模块声明 */
declare module '*.css' {
  const css: string
  export default css
}

/* axios 自定义配置项扩展（silent 静默模式） */
import 'axios'

declare module 'axios' {
  interface AxiosRequestConfig {
    /** 静默模式：请求失败时不弹错误提示 */
    silent?: boolean
  }
}
