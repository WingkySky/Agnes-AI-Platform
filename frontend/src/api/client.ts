/* =====================================================
 * axios 通用请求客户端封装
 * - 统一 baseURL
 * - 统一超时
 * - 统一错误处理（将后端消息转发给用户）
 * - 自动注入 JWT Authorization 头（若登录）
 * - 401 自动清理 token 并跳转到登录页
 * ===================================================== */

import axios from 'axios'
import { ElMessage } from 'element-plus'
import { useUserStore } from '@/stores/user'

// 使用 Vite 代理（开发环境）或 VITE_API_BASE_URL（生产环境）
const baseURL: string = import.meta.env.VITE_API_BASE_URL || ''

const client = axios.create({
  baseURL,
  timeout: 300000, // 5 分钟超时（图片生成可能需要较长时间）
  headers: {
    'Content-Type': 'application/json'
  }
})

// ---------- 请求拦截：自动注入 JWT ----------
client.interceptors.request.use(
  (config) => {
    // 从 user store 取 token；注意 init 可能还未调用，
    // 这里做惰性读取以保证最新值
    let accessToken: string | null = null
    try {
      const userStore = useUserStore()
      accessToken = userStore.token || null
    } catch (e) {
      // Pinia 尚未初始化时，回退到 localStorage
      try {
        accessToken = localStorage.getItem('agnes.platform.auth.token')
      } catch (_) { /* ignore */ }
    }
    if (accessToken) {
      config.headers = config.headers || {}
      ;(config.headers as any).Authorization = `Bearer ${accessToken}`
    }
    return config
  },
  (error: unknown) => Promise.reject(error)
)

// ---------- 响应拦截 ----------
client.interceptors.response.use(
  (response) => {
    // 直接返回 data，简化组件写法
    return response.data
  },
  (error: any) => {
    // 401：未认证或 token 已过期 — 清理本地状态并提示
    if (error?.response?.status === 401) {
      try {
        const userStore = useUserStore()
        userStore.clearAll()
      } catch (_) { /* ignore */ }
      // 触发用户登出事件，让所有 store（chat / taskQueue / canvas / asset）清理各自状态
      // 避免切换用户或 token 过期后残留上一个用户的数据
      if (typeof window !== 'undefined') {
        window.dispatchEvent(new CustomEvent('agnes:user-logout'))
      }
      // 仅在非静默模式下提示
      if (!error.config?.silent) {
        ElMessage({ type: 'warning', message: '登录已过期，请重新登录', duration: 3000 })
      }
      // 自动跳转到 /login（通过 hash 路由）
      if (typeof window !== 'undefined' && !window.location.hash.startsWith('#/login')) {
        window.location.hash = '#/login'
      }
      return Promise.reject(new Error('unauthorized'))
    }

    // 403 账号已被停用：清理登录态并跳登录页，给出明确提示
    // 区别于普通 403（权限不足），这里只处理 detail 含「停用」字样的情况
    if (error?.response?.status === 403) {
      const detail = error.response?.data?.detail || error.response?.data?.message || ''
      if (typeof detail === 'string' && detail.includes('停用')) {
        try {
          const userStore = useUserStore()
          userStore.clearAll()
        } catch (_) { /* ignore */ }
        if (typeof window !== 'undefined') {
          window.dispatchEvent(new CustomEvent('agnes:user-logout'))
        }
        if (!error.config?.silent) {
          ElMessage({ type: 'error', message: detail, duration: 5000, showClose: true })
        }
        if (typeof window !== 'undefined' && !window.location.hash.startsWith('#/login')) {
          window.location.hash = '#/login'
        }
        return Promise.reject(new Error(detail))
      }
    }

    // 统一错误提示（非静默失败时）
    let message = '请求失败，请稍后重试'
    if (error.code === 'ECONNABORTED') {
      message = '请求超时，请检查网络或稍后重试'
    } else if (error.response) {
      const data = error.response.data
      message =
        (data && (data.detail || data.message || data.error)) ||
        `请求失败（HTTP ${error.response.status}）`
    } else if (error.message) {
      message = error.message
    }

    if (!error.config?.silent) {
      ElMessage({
        type: 'error',
        message,
        duration: 4000,
        showClose: true
      })
    }

    return Promise.reject(new Error(message))
  }
)

export default client
