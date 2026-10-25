/* =====================================================
 * 工作台面板布局偏好（localStorage 持久化，极小配置）
 * ===================================================== */

export interface WorkbenchLayout {
  leftWidth: number
  rightWidth: number
  dockHeight: number
  leftOpen: boolean
  rightOpen: boolean
  dockOpen: boolean
}

const STORAGE_KEY = 'scene-workbench-layout'
const DEFAULTS: WorkbenchLayout = {
  leftWidth: 260,
  rightWidth: 340,
  dockHeight: 260,
  leftOpen: true,
  rightOpen: true,
  dockOpen: true,
}

export function loadWorkbenchLayout(): WorkbenchLayout {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return { ...DEFAULTS }
    const saved = JSON.parse(raw) as Partial<WorkbenchLayout>
    return {
      leftWidth: clamp(saved.leftWidth ?? DEFAULTS.leftWidth, 220, 480),
      rightWidth: clamp(saved.rightWidth ?? DEFAULTS.rightWidth, 220, 480),
      dockHeight: clamp(saved.dockHeight ?? DEFAULTS.dockHeight, 180, 520),
      leftOpen: saved.leftOpen ?? true,
      rightOpen: saved.rightOpen ?? true,
      dockOpen: saved.dockOpen ?? true,
    }
  } catch {
    return { ...DEFAULTS }
  }
}

export function saveWorkbenchLayout(layout: WorkbenchLayout): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(layout))
  } catch {
    // 存储不可用时静默降级（仅丢失偏好）
  }
}

function clamp(n: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, n))
}
