/* =====================================================
 * 分镜脚本生成 API 封装（无限画布 script 节点）
 * - generateStoryboard: 剧情 + 角色 → 结构化分镜数组
 * ===================================================== */

import client from './client'

/** 单个分镜 */
export interface StoryboardShot {
  no: number
  shot_size: string
  camera: string
  description: string
  dialogue: string
}

/** 角色设定（来自画布上游文本/图片节点） */
export interface StoryboardCharacter {
  name: string
  description: string
  ref_image_url?: string | null
}

/** 分镜脚本生成请求参数 */
export interface StoryboardRequest {
  story: string
  characters: StoryboardCharacter[]
  shot_count_min: number
  shot_count_max: number
  style?: string
}

/** 生成分镜脚本（无状态，不存储） */
export function generateStoryboard(params: StoryboardRequest): Promise<{ status: string; message: string; data: { shots: StoryboardShot[] } }> {
  return client.post('/api/storyboard', params, { silent: true })
}
