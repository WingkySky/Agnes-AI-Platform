/* =====================================================
 * 用户认证相关 API 封装
 * - register / login    : 注册 / 登录
 * - getMe / getCredits  : 获取当前用户信息 / 积分余额
 * - 管理员 API（前缀 /api/auth/users + /api/admin/credit-rules）
 *   - listUsers         : 用户列表
 *   - updateUserRole    : 修改用户角色
 *   - updateUserCredits : 修改用户积分
 *   - updateUserActive  : 启用 / 禁用用户
 *   - listCreditRules   : 积分规则列表
 *   - updateCreditRule  : 修改积分规则
 *   - resetCreditRules  : 恢复默认积分规则
 *
 * 说明：JWT access token 由 api client 自动注入 Authorization 头。
 * ===================================================== */

import client from './client'
import type {
  AuthLoginRequest,
  AuthRegisterRequest,
  AuthTokenResponse,
  UserInfoResponse,
  UserListResponse,
  UpdateRoleRequest,
  UpdateCreditsRequest,
  UpdateActiveRequest,
  UpdateProfileRequest,
  CreditRuleResponse,
  CreditRuleUpdateRequest,
  CaptchaResponse,
  SendEmailCodeRequest,
  ResetPasswordRequest,
} from '@/types'

/** 用户注册 */
export function register(params: AuthRegisterRequest): Promise<AuthTokenResponse> {
  return client.post('/api/auth/register', params)
}

/** 用户登录 */
export function login(params: AuthLoginRequest): Promise<AuthTokenResponse> {
  return client.post('/api/auth/login', params)
}

/** 获取图片验证码 */
export function getCaptcha(): Promise<CaptchaResponse> {
  return client.get('/api/auth/captcha')
}

/** 发送邮箱验证码（重置密码用） */
export function sendEmailCode(params: SendEmailCodeRequest): Promise<{ ok: boolean; message: string }> {
  return client.post('/api/auth/send-email-code', params)
}

/** 重置密码 */
export function resetPassword(params: ResetPasswordRequest): Promise<{ ok: boolean; message: string }> {
  return client.post('/api/auth/reset-password', params)
}

/** 获取当前登录用户信息 */
export function getMe(): Promise<UserInfoResponse> {
  return client.get('/api/auth/me', { silent: true })
}

/** 获取当前积分余额 */
export function getCredits(): Promise<{ credits: number }> {
  return client.get('/api/auth/credits', { silent: true })
}

/** 更新当前用户个人资料（邮箱） */
export function updateMyProfile(params: UpdateProfileRequest): Promise<UserInfoResponse> {
  return client.put('/api/auth/me', params)
}

/** 上传/更新当前用户头像（multipart/form-data） */
export function uploadAvatar(file: File): Promise<UserInfoResponse> {
  const form = new FormData()
  form.append('file', file)
  return client.post('/api/auth/avatar', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

// ---------- 管理员：用户与角色管理 ----------

/** 用户列表（仅管理员） */
export function listUsers(): Promise<UserListResponse> {
  return client.get('/api/auth/users')
}

/** 修改用户角色（仅管理员） */
export function updateUserRole(userId: number, params: UpdateRoleRequest): Promise<{ id: number; role: string; is_admin: boolean; ok: boolean }> {
  return client.put(`/api/auth/users/${userId}/role`, params)
}

/** 修改用户积分余额（仅管理员） */
export function updateUserCredits(userId: number, params: UpdateCreditsRequest): Promise<{ id: number; credits: number; ok: boolean }> {
  return client.put(`/api/auth/users/${userId}/credits`, params)
}

/** 启用/禁用用户（仅管理员） */
export function updateUserActive(userId: number, params: UpdateActiveRequest): Promise<{ id: number; is_active: boolean; ok: boolean }> {
  return client.put(`/api/auth/users/${userId}/active`, params)
}

// ---------- 管理员：积分规则管理 ----------

/** 积分规则列表（仅管理员） */
export function listCreditRules(): Promise<CreditRuleResponse[]> {
  return client.get('/api/admin/credit-rules')
}

/** 修改积分规则（仅管理员） */
export function updateCreditRule(ruleKey: string, params: CreditRuleUpdateRequest): Promise<CreditRuleResponse> {
  return client.put(`/api/admin/credit-rules/${ruleKey}`, params)
}

/** 恢复默认积分规则（仅管理员） */
export function resetCreditRules(): Promise<CreditRuleResponse[]> {
  return client.post('/api/admin/credit-rules/reset')
}
