/**
 * 认证相关 API
 * - 登录、注册、获取用户信息、积分查询
 */

import { get, post } from './client'

/**
 * 登录请求参数
 */
export interface LoginParams {
  username: string
  password: string
}

/**
 * 注册请求参数
 */
export interface RegisterParams {
  username: string
  password: string
  email?: string
}

/**
 * Token响应
 */
export interface TokenResponse {
  access_token: string
  token_type: string
  expires_in: number
}

/**
 * 用户信息响应
 */
export interface UserInfoResponse {
  id: number
  username: string
  email: string | null
  avatar_url: string | null
  credits: number
  role: string
  is_active: boolean
  is_admin: boolean
  created_at: string
  last_login_at: string
}

/**
 * 积分响应
 */
export interface CreditsResponse {
  credits: number
}

/**
 * 登录
 */
export function login(params: LoginParams): Promise<TokenResponse> {
  return post<TokenResponse>('/api/auth/login', params)
}

/**
 * 注册
 */
export function register(params: RegisterParams): Promise<TokenResponse> {
  return post<TokenResponse>('/api/auth/register', params)
}

/**
 * 获取当前用户信息
 */
export function getMe(): Promise<UserInfoResponse> {
  return get<UserInfoResponse>('/api/auth/me')
}

/**
 * 获取当前积分余额
 */
export function getCredits(): Promise<CreditsResponse> {
  return get<CreditsResponse>('/api/auth/credits')
}

export default {
  login,
  register,
  getMe,
  getCredits,
}
