/* =====================================================
 * 用户偏好设置 API 封装
 *
 * 接口：
 *   GET    /api/preferences          获取当前用户全部偏好
 *   PUT    /api/preferences          全量更新偏好（覆盖）
 *   PATCH  /api/preferences          部分更新偏好（合并）
 *   DELETE /api/preferences          重置为默认偏好
 *
 * 偏好数据结构（与后端 DEFAULT_PREFERENCES 对齐）：
 *   generation    : { default_model_id, default_aspect_ratio, auto_copy_prompt, default_image_count }
 *   download      : { auto_download, download_directory, file_naming_pattern, classify_by, default_format }
 *   ui            : { theme, canvas_grid_visible, canvas_grid_size, canvas_snap_to_grid }
 *   notification  : { sound_on_complete, browser_notification }
 * ===================================================== */

import client from './client'
import type { UserPreferences, UserPreferencesUpdate } from '@/types'

/** 获取当前用户的全部偏好设置 */
export function getPreferences(): Promise<UserPreferences> {
  return client.get('/api/preferences')
}

/** 全量更新偏好设置（覆盖）*/
export function updatePreferences(preferences: UserPreferencesUpdate): Promise<UserPreferences> {
  return client.put('/api/preferences', { preferences })
}

/** 部分更新偏好设置（深度合并）*/
export function patchPreferences(preferences: Partial<UserPreferencesUpdate>): Promise<UserPreferences> {
  return client.patch('/api/preferences', { preferences })
}

/** 重置为默认偏好 */
export function resetPreferences(): Promise<UserPreferences> {
  return client.delete('/api/preferences')
}
