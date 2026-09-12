/* =====================================================
 * 3D 场景（导演台）类型定义 — 对齐后端 Scene3D Schema
 * ===================================================== */

/** 三维坐标 */
export interface Vec3 {
  x: number
  y: number
  z: number
}

/** 主体（角色/物体）占位 */
export interface SubjectData {
  x: number
  y: number
  z: number
  label: string
  rotation: Vec3
}

/** 相机参数 */
export interface CameraData {
  position: Vec3
  lookAt: Vec3
  fov: number
}

/** 灯光参数（支持方向光/环境光，方向光带 direction 控制照射方向） */
export interface LightData {
  type: 'directional' | 'ambient'
  x: number
  y: number
  z: number
  intensity: number
  direction: Vec3
}

/** 道具占位（布景元素） */
export interface PropData {
  type: 'box' | 'plane' | 'sphere' | 'cylinder'
  x: number
  y: number
  z: number
  label: string
  rotation: Vec3
}

/** 环境布景描述 */
export interface EnvironmentData {
  type: 'studio' | 'indoor' | 'outdoor' | 'night' | 'custom'
  label: string
}

/** 3D 场景布局数据（支持多主体/多灯光/道具布景） */
export interface SceneData {
  subjects: SubjectData[]
  camera: CameraData
  lights: LightData[]
  props: PropData[]
  environment: EnvironmentData
}

/** 3D 场景记录 */
export interface Scene3D {
  id: number
  user_id: number | null
  name: string
  description?: string | null
  scene_data: SceneData | Record<string, never>
  is_public: boolean
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
}

/** 场景列表响应 */
export interface SceneListResponse {
  items: Scene3D[]
  total: number
}

/** prompt 预览响应 */
export interface ScenePromptPreviewResponse {
  prompt_suffix: string
  details: Record<string, unknown>
}
