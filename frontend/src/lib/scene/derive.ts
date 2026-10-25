/* =====================================================
 * 序列批量派生参数构造（纯函数）
 * 逐 shot 生成 taskQueue 提交参数：用户前缀提示词 + 该镜头编译后缀 +
 * 镜头机位映射 camera_params；视频侧 duration/fps 透传，预演截图可作首帧参考。
 * ===================================================== */

import { sceneCameraParams } from '@/lib/scene-mount'
import type { CameraDevice, ShotData } from '@/types/scene'

export interface ShotDeriveInput {
  shot: ShotData
  camera: CameraDevice
  /** 后端按 (scene_data, shot) 编译出的后缀 */
  suffix: string
  /** 用户公共前缀提示词 */
  userPrompt: string
  model: string
  kind: 'image' | 'video'
  /** 视频派生：以预演截图作为首帧参考（image2video） */
  useCoverAsFirstFrame?: boolean
  aspectRatio?: string
}

/** 组装单个镜头的派生任务参数（对齐 ImageView/VideoView 提交形态） */
export function buildShotDeriveParams(input: ShotDeriveInput): Record<string, any> {
  const { shot, camera, suffix, userPrompt, model, kind } = input
  const cleaned = (suffix || '').trim().replace(/^。+/, '').trim()
  const sceneText = cleaned ? `场景设定：${cleaned}` : ''
  const prompt = [userPrompt.trim(), sceneText].filter(Boolean).join('\n')

  const params: Record<string, any> = { model, prompt }
  if (input.aspectRatio) params.aspect_ratio = input.aspectRatio
  const cam = sceneCameraParams(camera)
  if (cam) params.camera_params = cam

  if (kind === 'video') {
    params.seconds = Math.max(1, Math.round(shot.duration || 4))
    params.frame_rate = shot.fps || 24
    if (input.useCoverAsFirstFrame && shot.coverUrl) {
      params.mode = 'image2video'
      params.images = [shot.coverUrl]
      params.image_mime_types = ['image/png']
    }
  }
  return params
}
