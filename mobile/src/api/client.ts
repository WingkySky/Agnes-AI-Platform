/**
 * API Client 封装
 * 统一处理请求配置、Token注入、错误处理
 */

// 后端API基础地址（开发环境使用空字符串通过Vite代理，生产环境需配置）
const BASE_URL = import.meta.env.VITE_API_BASE_URL || ''

// Token存储的key
const TOKEN_KEY = 'agnes_mobile_auth_token'

/**
 * 获取存储的Token
 */
export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

/**
 * 设置Token
 */
export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token)
}

/**
 * 清除Token
 */
export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY)
}

/**
 * 通用请求方法
 */
async function request<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const url = `${BASE_URL}${endpoint}`
  const token = getToken()

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string> || {}),
  }

  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }

  try {
    const response = await fetch(url, {
      ...options,
      headers,
    })

    // 处理401未授权
    if (response.status === 401) {
      clearToken()
      // 触发登出事件
      window.dispatchEvent(new CustomEvent('mobile:logout'))
      throw new Error('登录已过期，请重新登录')
    }

    const data = await response.json()

    if (!response.ok) {
      throw new Error(data.detail || data.message || `请求失败 (${response.status})`)
    }

    return data as T
  } catch (error) {
    if (error instanceof Error) {
      throw error
    }
    throw new Error('网络请求失败')
  }
}

/**
 * GET请求
 */
export function get<T>(endpoint: string): Promise<T> {
  return request<T>(endpoint, { method: 'GET' })
}

/**
 * POST请求
 */
export function post<T>(endpoint: string, body?: unknown): Promise<T> {
  return request<T>(endpoint, {
    method: 'POST',
    body: body ? JSON.stringify(body) : undefined,
  })
}

/**
 * PUT请求
 */
export function put<T>(endpoint: string, body?: unknown): Promise<T> {
  return request<T>(endpoint, {
    method: 'PUT',
    body: body ? JSON.stringify(body) : undefined,
  })
}

/**
 * DELETE请求
 */
export function del<T>(endpoint: string): Promise<T> {
  return request<T>(endpoint, { method: 'DELETE' })
}

export default {
  get,
  post,
  put,
  del,
  getToken,
  setToken,
  clearToken,
}
