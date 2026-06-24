/* =====================================================
 * 菜单配置 API 封装
 * - 存储菜单配置（是否在顶部/侧边栏显示、分组、排序）
 * - 支持分组自定义名称和图标配置
 * - 菜单元数据（名称、图标、路径）在前端内置，不需要后端存储
 * ===================================================== */

import client from './client'

/** 分组自定义配置 */
export interface MenuGroupConfig {
  key: string
  type: 'top' | 'sidebar'
  label_zh: string | null
  label_en: string | null
  icon: string | null
}

/** 菜单项配置 */
export interface MenuItemConfig {
  key: string
  show_in_top: boolean
  show_in_sidebar: boolean
  top_group_key: string | null
  sidebar_group_key: string | null
  top_sort_order: number
  sidebar_sort_order: number
}

/** 保存菜单配置请求 */
export interface SaveMenuConfigsRequest {
  configs: MenuItemConfig[]
  groups: MenuGroupConfig[]
}

/** 获取菜单配置响应 */
export interface GetMenuConfigsResponse {
  configs: MenuItemConfig[]
  groups: MenuGroupConfig[]
}

// ---------- API 函数 ----------

/** 获取当前菜单配置 */
export function getMenuConfigs() {
  return client.get<GetMenuConfigsResponse>('/api/menu-configs')
}

/** 保存菜单配置 */
export function saveMenuConfigs(data: SaveMenuConfigsRequest) {
  return client.post('/api/admin/menu-configs', data)
}

/** 重置菜单为默认配置 */
export function resetMenuConfigs() {
  return client.post<{ message: string }>('/api/admin/menu-configs/reset')
}
