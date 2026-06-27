// =====================================================
// 风格元素 API — 分层风格组合接口
// 对应后端路由：/api/style-elements
// =====================================================

import client from './client'

/** 风格层级 */
export type StyleLayer = 'visual_style' | 'lighting' | 'color' | 'camera' | 'mood' | 'quality'

/** 风格元素 */
export interface StyleElement {
  id: number
  key: string
  name: string
  description?: string
  layer: StyleLayer
  category?: string
  content: string
  negative_content?: string
  preview_image?: string
  weight_default: number
  tags: string[]
  is_builtin: boolean
  is_public: boolean
  author_id?: number
  use_count: number
  sort_order: number
}

/** 用户选择的风格元素项（带权重） */
export interface ResolvedElementItem {
  element_id: number
  weight: number
}

/** 列表响应 */
export interface StyleElementListResponse {
  items: StyleElement[]
  total: number
}

/** 层级信息 */
export interface LayerInfo {
  key: string
  name: string
}

/** prompt 预览请求 */
export interface PromptPreviewRequest {
  base_prompt: string
  elements: ResolvedElementItem[]
}

/** prompt 预览响应 */
export interface PromptPreviewResponse {
  positive: string
  negative: string
  negative_suffix: string
  final_prompt: string
}

/** 创建风格元素请求 */
export interface StyleElementCreate {
  key?: string
  name: string
  description?: string
  layer: StyleLayer
  category?: string
  content: string
  negative_content?: string
  preview_image?: string
  weight_default?: number
  tags?: string[]
  is_public?: boolean
}

/** 更新风格元素请求 */
export interface StyleElementUpdate {
  name?: string
  description?: string
  content?: string
  negative_content?: string
  preview_image?: string
  weight_default?: number
  tags?: string[]
  is_public?: boolean
}

/** 列出风格元素（支持按层过滤） */
export function listStyleElements(params?: {
  layer?: StyleLayer
  category?: string
  is_builtin?: boolean
  is_public?: boolean
  search?: string
  limit?: number
  offset?: number
}): Promise<StyleElementListResponse> {
  return client.get('/api/style-elements', { params })
}

/** 获取所有风格层级 */
export function listLayers(): Promise<{ layers: LayerInfo[] }> {
  return client.get('/api/style-elements/layers')
}

/** 预览拼接后的 prompt */
export function previewPrompt(payload: PromptPreviewRequest): Promise<PromptPreviewResponse> {
  return client.post('/api/style-elements/preview-prompt', payload)
}

/** 创建风格元素（用户自建） */
export function createStyleElement(payload: StyleElementCreate): Promise<StyleElement> {
  return client.post('/api/style-elements', payload)
}

/** 更新风格元素 */
export function updateStyleElement(id: number, payload: StyleElementUpdate): Promise<StyleElement> {
  return client.put(`/api/style-elements/${id}`, payload)
}

/** 删除风格元素 */
export function deleteStyleElement(id: number): Promise<{ message: string }> {
  return client.delete(`/api/style-elements/${id}`)
}
