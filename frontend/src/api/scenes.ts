/* =====================================================
 * 3D 场景（导演台）API 封装
 * - 场景 CRUD：list / get / create / update / delete
 * - prompt 预览：previewPrompt
 * 对齐后端 REST API：/api/scenes
 * ===================================================== */

import client from './client'
import type {
  Scene3D,
  CreateSceneRequest,
  UpdateSceneRequest,
  SceneListResponse,
  SceneData,
  ScenePromptPreviewResponse,
} from '@/types/scene'

/** 列表查询参数 */
export interface SceneListParams {
  page?: number
  page_size?: number
  search?: string
  is_public?: boolean
}

/** 获取场景列表（当前用户的 + 公开的） */
export function getScenes(params: SceneListParams = {}): Promise<SceneListResponse> {
  return client.get('/api/scenes', { params })
}

/** 获取单个场景详情 */
export function getScene(id: number): Promise<Scene3D> {
  return client.get(`/api/scenes/${id}`)
}

/** 创建场景 */
export function createScene(data: CreateSceneRequest): Promise<Scene3D> {
  return client.post('/api/scenes', data)
}

/** 更新场景 */
export function updateScene(id: number, data: UpdateSceneRequest): Promise<Scene3D> {
  return client.put(`/api/scenes/${id}`, data)
}

/** 删除场景 */
export function deleteScene(id: number): Promise<{ message: string }> {
  return client.delete(`/api/scenes/${id}`)
}

/** 预览 3D 场景翻译后的 prompt 后缀 */
export function previewScenePrompt(sceneData: SceneData): Promise<ScenePromptPreviewResponse> {
  return client.post('/api/scenes/preview-prompt', { scene_data: sceneData }, { silent: true })
}
