/* =====================================================
 * AgentHostPanel 几何纯函数（小态 ⇄ 展开态双形态壳）
 *
 * 唯一几何驱动布局：宽度过阈值即展开态（带会话侧栏）；
 * 拖动/拉伸/双击预设共用同一 clamp。视口基准（fixed 浮层）。
 * ===================================================== */

export interface PanelGeom { left: number; top: number; width: number; height: number }

export const HOST_GEOM_KEY = 'agnes_agent_host_geom'
export const HOST_MIN_W = 320
export const HOST_MIN_H = 320
/** 大小形态的宽度分界（≥ 为展开态：带会话侧栏） */
export const HOST_EXPAND_MIN_W = 560

/** 形态由尺寸推导：没有显式几何（从未拖动/切换过）时是小面板态 */
export function isExpandedGeom(g: PanelGeom | null | undefined): boolean {
  return (g?.width ?? 0) >= HOST_EXPAND_MIN_W
}

export function readGeom(key: string): PanelGeom | null {
  try {
    const raw = localStorage.getItem(key)
    if (!raw) return null
    const g = JSON.parse(raw) as Partial<PanelGeom>
    const { left, top, width, height } = g
    if (typeof left !== 'number' || typeof top !== 'number' || typeof width !== 'number' || typeof height !== 'number') return null
    return { left, top, width, height }
  } catch {
    return null
  }
}

export function saveGeom(key: string, g: PanelGeom): void {
  try {
    localStorage.setItem(key, JSON.stringify(g))
  } catch {
    // 记忆失败不影响拖动
  }
}

/** 钳位（视口基准）：至少留 80px 在视口内，宽高不小于下限且不超出视口 */
export function clampGeom(g: PanelGeom, maxW: number, maxH: number): PanelGeom {
  const width = Math.min(Math.max(g.width, HOST_MIN_W), maxW)
  const height = Math.min(Math.max(g.height, HOST_MIN_H), maxH)
  return {
    width,
    height,
    left: Math.min(Math.max(g.left, -width + 80), maxW - 80),
    top: Math.min(Math.max(g.top, 0), maxH - 48),
  }
}

/** 尺寸预设：小面板（右停靠 360）⇄ 展开态（居中 86%×86%） */
export function presetGeom(kind: 'small' | 'expanded', maxW: number, maxH: number): PanelGeom {
  if (kind === 'expanded') {
    const width = Math.round(maxW * 0.86)
    const height = Math.round(maxH * 0.86)
    return clampGeom({
      left: Math.round((maxW - width) / 2),
      top: Math.round(maxH * 0.07),
      width,
      height,
    }, maxW, maxH)
  }
  return clampGeom({
    left: maxW - 360 - 16,
    top: 16,
    width: 360,
    height: Math.max(HOST_MIN_H, maxH - 112),
  }, maxW, maxH)
}

// =====================================================
// 三态模式（small 小态气泡 / float 展开浮窗 / dock 停靠侧栏）
// =====================================================

export const HOST_MODE_KEY = 'agnes_agent_host_mode'
export type HostMode = 'small' | 'float' | 'dock'
export const HOST_DOCK_MIN_W = 240
export const HOST_DOCK_MAX_W = 560

export interface HostModeState {
  mode: HostMode
  /** 仅 small 档生效：钉住后点外不收起 */
  pinned: boolean
  dockWidth: number
}

/** 读三态记忆（损坏/缺省回 small+未钉+420） */
export function readHostModeState(key = HOST_MODE_KEY): HostModeState {
  try {
    const raw = localStorage.getItem(key)
    if (!raw) return { mode: 'small', pinned: false, dockWidth: 420 }
    const g = JSON.parse(raw) as Partial<HostModeState>
    const mode: HostMode = g.mode === 'float' || g.mode === 'dock' ? g.mode : 'small'
    return {
      mode,
      pinned: g.pinned === true,
      dockWidth: typeof g.dockWidth === 'number' && Number.isFinite(g.dockWidth) ? g.dockWidth : 420,
    }
  } catch {
    return { mode: 'small', pinned: false, dockWidth: 420 }
  }
}

export function saveHostModeState(state: HostModeState, key = HOST_MODE_KEY): void {
  try {
    localStorage.setItem(key, JSON.stringify(state))
  } catch {
    // 记忆失败不影响切换
  }
}

/** 停靠宽度钳位：240~560，窄屏再钳到视口（至少留 56px 页面） */
export function clampDockWidth(w: number, vw: number): number {
  return Math.max(HOST_DOCK_MIN_W, Math.min(w, HOST_DOCK_MAX_W, Math.max(HOST_DOCK_MIN_W, vw - 56)))
}
