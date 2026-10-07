/* =====================================================
 * 运镜（摄像机）预设注册表（描述符模式，同 editor-fx-registry 范式）
 * - clip.props.camera = { type, strength(0~1) }；不设 = 无运镜
 * - 双端同源：cameraRectAt（预览裁剪窗）与后端 _camera_zoompan（ffmpeg 表达式）
 *   由同一套数值派生，保证预览与成片一致；新增运镜两处各加一行
 * ===================================================== */

export type CameraType = 'zoomIn' | 'zoomOut' | 'panLeft' | 'panRight' | 'panUp' | 'panDown'

export const CAMERA_TYPES: CameraType[] = ['zoomIn', 'zoomOut', 'panLeft', 'panRight', 'panUp', 'panDown']

export function isCameraType(v: unknown): v is CameraType {
  return typeof v === 'string' && (CAMERA_TYPES as string[]).includes(v)
}

export interface ClipCamera {
  type: CameraType
  strength: number
}

/** 归一化画面内的裁剪窗（宽高=1/zoom；x/y ∈ [0, 1−1/zoom]） */
export interface CameraRect {
  zoom: number
  x: number
  y: number
}

/** strength=1 时推进/拉远到 1.6；平移固定 1.3 留移动窗 */
const ZOOM_RANGE = 0.6
const PAN_ZOOM = 0.3

const clamp01 = (v: number): number => Math.min(1, Math.max(0, v))

interface CameraDef {
  zoomAt(strength: number, p: number): number
  /** 窗口左上角（未钳制，归一化） */
  posAt(strength: number, p: number, zoom: number): { x: number; y: number }
}

function centered(_strength: number, _p: number, zoom: number): { x: number; y: number } {
  const span = 1 - 1 / zoom
  return { x: span / 2, y: span / 2 }
}

/** 平移：窗口中心沿 (dx,dy) 从反侧端点滑到顺侧端点（贴边） */
function panDef(dx: number, dy: number): CameraDef {
  return {
    zoomAt: (s) => 1 + PAN_ZOOM * s,
    posAt: (_s, p, zoom) => {
      const span = 1 - 1 / zoom
      return { x: span / 2 + (p - 0.5) * span * dx, y: span / 2 + (p - 0.5) * span * dy }
    },
  }
}

const DEFS: Record<CameraType, CameraDef> = {
  zoomIn: { zoomAt: (s, p) => 1 + ZOOM_RANGE * s * p, posAt: centered },
  zoomOut: { zoomAt: (s, p) => 1 + ZOOM_RANGE * s * (1 - p), posAt: centered },
  panLeft: panDef(-1, 0),
  panRight: panDef(1, 0),
  panUp: panDef(0, -1),
  panDown: panDef(0, 1),
}

/** 片段运镜在 progress（0~1，时间线域）时刻的裁剪窗；无运镜返回 null */
export function cameraRectAt(
  camera: { type: string; strength: number } | null | undefined,
  progress: number,
): CameraRect | null {
  if (!camera || !isCameraType(camera.type)) return null
  const strength = clamp01(camera.strength)
  const p = clamp01(progress)
  const def = DEFS[camera.type]
  const zoom = def.zoomAt(strength, p)
  const { x, y } = def.posAt(strength, p, zoom)
  const span = 1 - 1 / zoom
  return {
    zoom,
    x: Math.min(span, Math.max(0, x)),
    y: Math.min(span, Math.max(0, y)),
  }
}
