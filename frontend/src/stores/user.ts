/* =====================================================
 * 用户认证 Store
 * 负责：
 *   - 登录/注册/登出
 *   - JWT 本地持久化（localStorage）
 *   - 当前用户信息缓存（username / credits / email ...）
 *   - 对外暴露 isAuthenticated、当前用户、积分
 *
 * 用法：
 *   const userStore = useUserStore()
 *   await userStore.login({ username, password })
 *   userStore.logout()
 *   userStore.fetchCredits()  // 在生成任务后刷新积分
 * ===================================================== */

import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { login as apiLogin, register as apiRegister, getMe, getCredits, updateMyProfile, uploadAvatar } from '@/api/auth'
import { usePreferencesStore } from '@/stores/preferences'
import type { AuthLoginRequest, AuthRegisterRequest, UserInfoResponse, UpdateProfileRequest } from '@/types'

/** JWT 在 localStorage 中的 key（前端仅保存，不可篡改） */
const TOKEN_STORAGE_KEY = 'agnes.platform.auth.token'

export const useUserStore = defineStore('user', () => {
  // ================ state ================
  const token = ref<string>('')
  const user = ref<UserInfoResponse | null>(null)
  const loading = ref(false)

  // ================ 初始化就绪 Promise ================
  // 路由守卫需要等待 init() 完成，否则刷新页面时 token/user 还没恢复就被判定为未登录
  let resolveReady: () => void = () => {}
  const readyPromise = new Promise<void>((resolve) => { resolveReady = resolve })

  // ================ getters ================
  const isAuthenticated = computed(() => !!token.value && !!user.value)
  const username = computed(() => user.value?.username || '')
  const nickname = computed(() => user.value?.nickname || '')
  const credits = computed(() => user.value?.credits ?? 0)
  const userId = computed(() => user.value?.id || null)
  const isAdmin = computed(() => !!user.value?.is_admin)
  const avatarUrl = computed(() => user.value?.avatar_url || '')

  // ================ actions ================

  /** 初始化：读取本地缓存 token，并尝试拉取用户信息（异步，需 await） */
  async function init() {
    const saved = localStorage.getItem(TOKEN_STORAGE_KEY)
    if (saved) {
      token.value = saved
      // 尝试拉取用户信息；失败（例如 token 过期）则清理
      try {
        await fetchMe()
      } catch {
        clearAll()
      }
    }
    // 无论是否登录，都标记初始化完成，路由守卫可以继续
    resolveReady()
  }

  /** 等待 init() 完成（路由守卫使用） */
  function ready() {
    return readyPromise
  }

  /** 从后端拉取当前用户信息，失败返回 undefined */
  async function fetchMe() {
    if (!token.value) return
    try {
      const data = await getMe()
      user.value = data
    } catch (e) {
      // 401 或其他错误，上层 api client 的拦截器已处理跳转/清除
      throw e
    }
  }

  /** 主动刷新积分（例如生成任务完成后调用） */
  async function fetchCredits() {
    if (!token.value) return
    try {
      const data = await getCredits()
      if (user.value) {
        user.value.credits = data.credits
      }
    } catch (e) {
      // 静默处理
    }
  }

  /** 更新个人资料（邮箱） */
  async function updateProfile(payload: UpdateProfileRequest) {
    if (!token.value) return
    const data = await updateMyProfile(payload)
    user.value = data
    return data
  }

  /** 上传/更新头像 */
  async function uploadUserAvatar(file: File) {
    if (!token.value) return
    const data = await uploadAvatar(file)
    user.value = data
    return data
  }

  /** 登录：提交用户名 + 密码，保存 JWT，并拉取用户信息 */
  async function login(payload: AuthLoginRequest) {
    loading.value = true
    try {
      const data = await apiLogin(payload)
      if (!data?.access_token) {
        throw new Error('登录失败：服务端未返回有效 token')
      }
      token.value = data.access_token
      localStorage.setItem(TOKEN_STORAGE_KEY, data.access_token)
      // 获取用户信息
      await fetchMe()
      // 加载用户偏好设置
      usePreferencesStore().fetchPreferences()
      if (typeof window !== 'undefined') {
        window.dispatchEvent(new CustomEvent('agnes:user-login', { detail: { id: user.value?.id, username: user.value?.username } }))
      }
      ElMessage.success(`欢迎回来，${user.value?.username}`)
      return user.value
    } finally {
      loading.value = false
    }
  }

  /** 注册：注册新用户并自动登录 */
  async function register(payload: AuthRegisterRequest) {
    loading.value = true
    try {
      const data = await apiRegister(payload)
      if (!data?.access_token) {
        throw new Error('注册失败：服务端未返回有效 token')
      }
      token.value = data.access_token
      localStorage.setItem(TOKEN_STORAGE_KEY, data.access_token)
      await fetchMe()
      // 加载用户偏好设置
      usePreferencesStore().fetchPreferences()
      if (typeof window !== 'undefined') {
        window.dispatchEvent(new CustomEvent('agnes:user-login', { detail: { id: user.value?.id, username: user.value?.username } }))
      }
      ElMessage.success(`注册成功，欢迎 ${user.value?.username}`)
      return user.value
    } finally {
      loading.value = false
    }
  }

  /** 登出：清空本地状态 + JWT，并跳转至登录页 */
  function logout(showMessage: boolean = true) {
    const wasLoggedIn = isAuthenticated.value
    clearAll()
    if (wasLoggedIn && showMessage) {
      ElMessage.info('已退出登录')
    }
    // 由路由守卫在进入登录页时做路由处理，这里不强制跳转
    // 但如果当前在需要登录的页面，路由守卫会自动跳登录页
    // 保险起见，手动触发一次 push 到 /login（通过 window 通知 router）
    if (typeof window !== 'undefined') {
      const hash = window.location.hash
      if (hash && hash.startsWith('#/login')) {
        // do nothing
      } else {
        // 触发自定义事件，由 router 监听并跳转
        window.dispatchEvent(new CustomEvent('agnes:user-logout'))
      }
    }
  }

  /** 清空用户相关的本地状态和存储 */
  function clearAll() {
    token.value = ''
    user.value = null
    try {
      localStorage.removeItem(TOKEN_STORAGE_KEY)
    } catch (e) {
      // ignore storage errors
    }
  }

  return {
    // state
    token,
    user,
    loading,
    // getters
    isAuthenticated,
    username,
    nickname,
    credits,
    userId,
    isAdmin,
    avatarUrl,
    // actions
    init,
    ready,
    fetchMe,
    fetchCredits,
    updateProfile,
    uploadUserAvatar,
    login,
    register,
    logout,
    clearAll,
  }
})
