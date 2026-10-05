/* =====================================================
 * 预览合成器（纯函数）
 * - planFrame：文档 + 播放头 → 自底向上的绘制清单（视频轨激活片段，归一化 rect
 *   换算为 stage 像素）；字幕走 DOM 层不进清单；执行层只做 drawImage
 * - 与渲染端语义对齐：轨 order 大 = 上层；hidden 轨跳过；无激活片段输出黑底
 * ===================================================== */

import { clipEnd, FULL_RECT, type EditorDocument } from './editor-types'

/** 绘制清单项：assetId 由执行层解析为视频帧（media sink）或图片位图；clipId 供执行层维护解码状态 */
export interface DrawItem {
  clipId: string
  assetId: number
  x: number
  y: number
  w: number
  h: number
}

/** 当前播放头一帧的绘制清单（自底向上；stage 尺寸为 CSS 像素，dpr 由执行层处理） */
export function planFrame(
  doc: EditorDocument,
  playhead: number,
  stageW: number,
  stageH: number,
): DrawItem[] {
  const videoTracks = doc.tracks
    .filter((tr) => tr.kind === 'video' && tr.flag !== 'hidden')
    .sort((a, b) => a.order - b.order)
  const items: DrawItem[] = []
  for (const track of videoTracks) {
    const clip = doc.clips.find(
      (c) => c.trackId === track.id && playhead >= c.start && playhead < clipEnd(c),
    )
    if (!clip || clip.assetId == null) continue
    const rect = clip.props.rect ?? FULL_RECT
    items.push({
      clipId: clip.id,
      assetId: clip.assetId,
      x: rect.x * stageW,
      y: rect.y * stageH,
      w: rect.w * stageW,
      h: rect.h * stageH,
    })
  }
  return items
}
