/* =====================================================
 * 画布视频节点悬停预览（全画布单例）
 * - 同一时刻只允许一个预览播放：新预览启动前停掉旧的（互斥）
 * - 预览语义：muted 从 0 播到 PREVIEW_SECONDS 暂停复位；结束/移出/用户接管都走 stop
 * - 用户与原生 controls 交互（pointerdown）即交还播放权，不与预览打架
 * ===================================================== */

/** 预览播放时长（秒） */
export const PREVIEW_SECONDS = 3

let active: HTMLVideoElement | null = null
/** 预览接管前的 muted 原值：stop 时恢复，避免预览后用户点原生播放键变成静音播放 */
let activePrevMuted = false

/** 启动（或接管）预览：停掉当前预览的元素并让 el 从头静音播放；返回是否成功启动 */
export function startPreview(el: HTMLVideoElement): boolean {
  if (active === el) return true
  stopActive()
  active = el
  activePrevMuted = el.muted
  el.muted = true
  el.currentTime = 0
  const p = el.play()
  if (p) p.catch(() => stopPreview(el))
  return true
}

/** 停止 el 的预览（暂停并复位到 0，恢复原静音态）；仅当 el 是当前预览时生效 */
export function stopPreview(el: HTMLVideoElement): void {
  if (active !== el) return
  active = null
  el.pause()
  el.currentTime = 0
  el.muted = activePrevMuted
}

/** 停掉当前预览（无论属于哪个节点） */
export function stopActivePreview(): void {
  stopActive()
}

function stopActive(): void {
  if (!active) return
  const el = active
  const prevMuted = activePrevMuted
  active = null
  el.pause()
  el.currentTime = 0
  el.muted = prevMuted
}
