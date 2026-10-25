/* =====================================================
 * 3D 场景（导演台）类型定义 — SceneData v2（多机位 / 镜头序列）
 * 对齐后端 Scene Schema v2
 * ===================================================== */

/** 三维坐标 */
export interface Vec3 {
  x: number
  y: number
  z: number
}

/** 主体姿势（b2：预设起步，关节级编辑后置） */
export interface SubjectPose {
  preset: string
}

/** 主体（角色/物体）占位 */
export interface SubjectData {
  id: string
  label: string
  x: number
  y: number
  z: number
  rotation: Vec3
  pose?: SubjectPose
  visible?: boolean
  locked?: boolean
}

/** 机位（v2 多机位；active 机位=视口当前编辑对象，恒有一个 active） */
export interface CameraDevice {
  id: string
  name: string
  position: Vec3
  /** 注视点（v1 的 lookAt） */
  target: Vec3
  fov: number
  active?: boolean
  /** 镜头跟随主体 id（开启后 target 恒对准该主体） */
  followSubjectId?: string | null
  locked?: boolean
}

/** 灯光参数（方向光带 direction 控制照射方向） */
export interface LightData {
  id: string
  type: 'directional' | 'ambient'
  x: number
  y: number
  z: number
  intensity: number
  direction: Vec3
  visible?: boolean
  locked?: boolean
}

/** 道具占位（布景元素） */
export interface PropData {
  id: string
  type: 'box' | 'plane' | 'sphere' | 'cylinder'
  label: string
  x: number
  y: number
  z: number
  rotation: Vec3
  scale?: number
  visible?: boolean
  locked?: boolean
}

/** 环境布景描述 */
export interface EnvironmentData {
  type: 'studio' | 'indoor' | 'outdoor' | 'night' | 'custom'
  label: string
}

/** 舞台级设置 */
export interface StageData {
  environment: EnvironmentData
  /** 画幅取景框（'16:9' 等，空/缺省=无） */
  aspect_ratio?: string
}

/** 景别（6 档） */
export type ShotSize =
  | 'extreme_wide'
  | 'wide'
  | 'medium'
  | 'medium_close'
  | 'close_up'
  | 'extreme_close_up'

/** 运镜（9 种） */
export type CameraMove =
  | 'static'
  | 'push_in'
  | 'pull_out'
  | 'pan'
  | 'tilt'
  | 'orbit'
  | 'tracking'
  | 'crane'
  | 'handheld'

/** 关键帧过渡（描述「从上一帧到本帧」：linear 线性 / smooth 缓入缓出 / cut 硬切） */
export type KeyframeEasing = 'linear' | 'smooth' | 'cut'

/** 相机关键帧 */
export interface CameraKeyframe {
  /** 相对所在 shot 起始的秒数 */
  time: number
  position: Vec3
  target: Vec3
  fov: number
  easing: KeyframeEasing
}

/** 镜头（Shot）：机位 + 时长 + 景别/运镜 + 关键帧 */
export interface ShotData {
  id: string
  cameraId: string
  duration: number
  fps: 24 | 25 | 30
  shotSize: ShotSize
  cameraMove: CameraMove
  /** ≥1 帧（起始机位）；≥2 帧才有运镜 */
  keyframes: CameraKeyframe[]
  /** 镜头附加描述（编译进 prompt 后缀） */
  prompt?: string
  /** 预演截图封面 */
  coverUrl?: string | null
  /** 批量派生任务留痕 */
  derivedTaskIds?: string[]
}

/** 自定义分组（后置批占位） */
export interface SceneGroup {
  id: string
  name: string
  memberIds: string[]
  visible?: boolean
  locked?: boolean
}

/** 3D 场景布局数据 v2 */
export interface SceneData {
  stage: StageData
  subjects: SubjectData[]
  cameras: CameraDevice[]
  lights: LightData[]
  props: PropData[]
  shots: ShotData[]
  activeShotId?: string | null
  groups?: SceneGroup[]
}

/** 3D 场景记录 */
export interface Scene3D {
  id: number
  user_id: number | null
  name: string
  description?: string | null
  scene_data: SceneData | Record<string, never>
  is_public: boolean
  cover_url?: string | null
  created_at?: string | null
  updated_at?: string | null
}

/** 创建场景请求 */
export interface CreateSceneRequest {
  name: string
  description?: string
  scene_data: SceneData | Record<string, never>
  is_public?: boolean
}

/** 更新场景请求 */
export interface UpdateSceneRequest {
  name?: string
  description?: string
  scene_data?: SceneData | Record<string, never>
  is_public?: boolean
  cover_url?: string
}

/** 场景列表响应 */
export interface SceneListResponse {
  items: Scene3D[]
  total: number
}

/** prompt 预览请求（shot 可选：提供时按该镜头机位编译并追加景别/运镜） */
export interface ScenePromptPreviewRequest {
  scene_data: SceneData
  shot?: ShotData | null
}

/** prompt 预览响应 */
export interface ScenePromptPreviewResponse {
  prompt_suffix: string
  details: Record<string, unknown>
}
