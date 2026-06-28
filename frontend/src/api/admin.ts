/* =====================================================
 * 管理员相关 API 封装
 * - 角色管理
 * - 敏感词管理
 * - 水印配置
 * - 用户扩展配置
 *
 * 注：作品/预设/模板审核统一走 /api/admin/review/*，
 *     审核页面前端直接使用 @/api/client，不再在此封装。
 * ===================================================== */

import client from './client'

// ---------- 类型定义 ----------

/** 角色项 */
export interface RoleItem {
  id: number
  name: string
  display_name: string
  description: string
  permissions: string[]
  is_system: boolean
  created_at: string
  updated_at: string
}

/** 权限项 */
export interface PermissionItem {
  key: string
  name: string
  description: string
  group: string
}

/** 敏感词项 */
export interface SensitiveWordItem {
  id: number
  word: string
  category: string
  description: string | null
  is_active: boolean
  created_at: string
  updated_at: string
}

/** 敏感词列表响应 */
export interface SensitiveWordListResponse {
  items: SensitiveWordItem[]
  total: number
  page: number
  page_size: number
  categories: Record<string, string>
}

/** 水印配置 */
export interface WatermarkConfig {
  id: number
  type: 'text' | 'image'
  text: string
  font_size: number
  color: string
  opacity: number
  position: string
  margin: number
  image_url: string | null
  image_width: number
  force_all: boolean
  updated_at: string
}

// ---------- API 函数 ----------

// ---------- 角色管理 ----------

/** 获取角色列表 */
export function getRoles(): Promise<RoleItem[]> {
  return client.get('/api/admin/roles') as any
}

/** 获取权限列表 */
export function getPermissions(): Promise<PermissionItem[]> {
  return client.get('/api/admin/roles/permissions') as any
}

/** 创建角色 */
export function createRole(data: Partial<RoleItem>): Promise<RoleItem> {
  return client.post('/api/admin/roles', data) as any
}

/** 更新角色 */
export function updateRole(name: string, data: Partial<RoleItem>): Promise<RoleItem> {
  return client.put(`/api/admin/roles/${name}`, data) as any
}

/** 删除角色 */
export function deleteRole(name: string): Promise<{ success: boolean }> {
  return client.delete(`/api/admin/roles/${name}`) as any
}

// ---------- 敏感词 ----------

/** 获取敏感词列表 */
export function getSensitiveWords(params: {
  category?: string
  keyword?: string
  page?: number
  page_size?: number
}): Promise<SensitiveWordListResponse> {
  return client.get('/api/admin/sensitive-words', { params }) as any
}

/** 创建敏感词 */
export function createSensitiveWord(
  word: string,
  category: string,
  description?: string
): Promise<SensitiveWordItem> {
  return client.post('/api/admin/sensitive-words', { word, category, description }) as any
}

/** 更新敏感词 */
export function updateSensitiveWord(
  id: number,
  data: Partial<Omit<SensitiveWordItem, 'id' | 'created_at' | 'updated_at'>>
): Promise<SensitiveWordItem> {
  return client.put(`/api/admin/sensitive-words/${id}`, data) as any
}

/** 删除敏感词 */
export function deleteSensitiveWord(id: number): Promise<{ success: boolean }> {
  return client.delete(`/api/admin/sensitive-words/${id}`) as any
}

/** 批量导入敏感词 */
export function batchImportSensitiveWords(data: {
  words: string
  category: string
  skip_existing?: boolean
}): Promise<{
  success: boolean
  inserted_count: number
  skipped_count: number
  total_count: number
}> {
  return client.post('/api/admin/sensitive-words/batch-import', data) as any
}

// ---------- 水印配置 ----------

/** 获取水印配置 */
export function getWatermarkConfig(): Promise<WatermarkConfig> {
  return client.get('/api/admin/watermark/config') as any
}

/** 更新水印配置 */
export function updateWatermarkConfig(data: Partial<WatermarkConfig>): Promise<WatermarkConfig> {
  return client.put('/api/admin/watermark/config', data) as any
}

// ---------- 用户扩展 ----------

/** 更新用户水印开关 */
export function updateUserWatermark(userId: number, enabled: boolean): Promise<{ success: boolean }> {
  return client.put(`/api/auth/users/${userId}/watermark`, { enabled }) as any
}

/** 更新用户内容安全开关 */
export function updateUserContentSafety(userId: number, enabled: boolean): Promise<{ success: boolean }> {
  return client.put(`/api/auth/users/${userId}/content-safety`, { enabled }) as any
}

/** 更新用户角色 */
export function updateUserRole(userId: number, role: string): Promise<{ success: boolean }> {
  return client.put(`/api/auth/users/${userId}/role`, { role }) as any
}

// ---------- 系统配置 - SMTP ----------

/** SMTP 配置 */
export interface SmtpConfig {
  smtp_host: string
  smtp_port: number
  smtp_user: string
  smtp_password: string
  smtp_from_email: string
  smtp_from_name: string
  smtp_use_tls: boolean
  is_enabled: boolean
}

/** 获取 SMTP 配置 */
export function getSmtpConfig(): Promise<SmtpConfig> {
  return client.get('/api/admin/system-config/smtp') as any
}

/** 更新 SMTP 配置 */
export function updateSmtpConfig(data: Partial<SmtpConfig>): Promise<{ message: string }> {
  return client.put('/api/admin/system-config/smtp', data) as any
}

/** 测试 SMTP 邮件发送 */
export function testSmtpConfig(testEmail: string): Promise<{ message: string }> {
  return client.post('/api/admin/system-config/smtp/test', { test_email: testEmail }) as any
}
