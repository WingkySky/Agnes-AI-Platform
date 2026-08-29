/* =====================================================
 * 分镜脚本生成 API 封装（无限画布 script 节点）
 * - generateStoryboard: 剧情 + 角色/场景 → 分镜数组 + 全剧资产清单
 * ===================================================== */

import client from './client'

/** 单个分镜（characters/location 与资产卡按名关联） */
export interface StoryboardShot {
  no: number
  shot_size: string
  camera: string
  characters: string[]
  location: string
  description: string
  dialogue: string
}

/** 角色设定（来自画布上游文本/图片节点） */
export interface StoryboardCharacter {
  name: string
  description: string
  ref_image_url?: string | null
}

/** 从剧情提取的资产卡 */
export interface StoryboardAsset {
  name: string
  description: string
}

/** 全剧资产清单 */
export interface StoryboardAssets {
  characters: StoryboardAsset[]
  scenes: StoryboardAsset[]
}

/** 分镜脚本生成请求参数 */
export interface StoryboardRequest {
  story: string
  characters: StoryboardCharacter[]
  scenes: StoryboardCharacter[]
  shot_count_min: number
  shot_count_max: number
  style?: string
}

/** 生成分镜脚本（无状态，不存储） */
export function generateStoryboard(params: StoryboardRequest): Promise<{ status: string; message: string; data: { shots: StoryboardShot[]; assets: StoryboardAssets } }> {
  return client.post('/api/storyboard', params, { silent: true })
}
