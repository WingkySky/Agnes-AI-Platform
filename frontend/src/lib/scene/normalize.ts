/* =====================================================
 * SceneData v2 归一与工厂（纯函数）
 * - normalizeSceneData：null 安全 + 缺 id 补 id + 空机位建默认
 *   （id 寻址体系的前提：部分更新/外部编辑不会破坏结构）
 * - activeCamera：取激活机位（无 active 标记回退第一个）
 * ===================================================== */

import { v4 as uuidv4 } from 'uuid'
import type {
  CameraDevice,
  CameraKeyframe,
  LightData,
  PropData,
  SceneData,
  ShotData,
  SubjectData,
} from '@/types/scene'

const DEFAULT_ENV_LABEL = '工作室'

function withId<T extends { id?: string }>(item: T): T & { id: string } {
  return { ...item, id: item.id || uuidv4() }
}

export function defaultCamera(name = 'A 机位'): CameraDevice {
  return {
    id: uuidv4(),
    name,
    position: { x: 0, y: 1.6, z: 5 },
    target: { x: 0, y: 0, z: 0 },
    fov: 50,
    active: true,
    followSubjectId: null,
  }
}

export function defaultKeyframe(cam: CameraDevice): CameraKeyframe {
  return {
    time: 0,
    position: { ...cam.position },
    target: { ...cam.target },
    fov: cam.fov,
    easing: 'smooth',
  }
}

export function defaultShot(cam: CameraDevice): ShotData {
  return {
    id: uuidv4(),
    cameraId: cam.id,
    duration: 4,
    fps: 24,
    shotSize: 'medium',
    cameraMove: 'static',
    keyframes: [defaultKeyframe(cam)],
    prompt: '',
    coverUrl: null,
    derivedTaskIds: [],
  }
}

/** 新建场景默认数据（标签走 i18n 由调用方传入） */
export function newSceneData(labels: {
  subject: string
  environment: string
}): SceneData {
  return {
    stage: { environment: { type: 'studio', label: labels.environment } },
    subjects: [
      {
        id: uuidv4(),
        label: labels.subject,
        x: 0,
        y: 0,
        z: 0,
        rotation: { x: 0, y: 0, z: 0 },
      },
    ],
    cameras: [defaultCamera()],
    lights: [
      {
        id: uuidv4(),
        type: 'directional',
        x: 5,
        y: 8,
        z: 5,
        intensity: 1.0,
        direction: { x: -0.47, y: -0.75, z: -0.47 },
      },
    ],
    props: [],
    shots: [],
    activeShotId: null,
  }
}

/** 激活机位：active 标记优先，无标记回退第一个，无机位返回 null */
export function activeCamera(data: SceneData | null | undefined): CameraDevice | null {
  const cameras = data?.cameras || []
  return cameras.find(c => c.active) || cameras[0] || null
}

/**
 * 归一化任意来源的 scene_data：
 * - 数组缺省补空数组；stage/environment 缺省补默认
 * - 所有实体缺 id 补 id；机位空时从 v1 camera 字段或默认值建一台
 * - v1 顶层 environment 就位到 stage（开发库旧数据就位，非迁移兜底）
 */
export function normalizeSceneData(raw: unknown): SceneData {
  const d = (raw && typeof raw === 'object' ? raw : {}) as Record<string, any>
  const legacyEnv = d.environment || {}
  const stage = d.stage || {}
  const environment = stage.environment?.type
    ? stage.environment
    : {
        type: (legacyEnv.type || 'studio') as SceneData['stage']['environment']['type'],
        label: legacyEnv.label || DEFAULT_ENV_LABEL,
      }

  let cameras: CameraDevice[] = (d.cameras || []).map(withId)
  if (!cameras.length) {
    const legacyCam = d.camera
    cameras = [
      legacyCam?.position
        ? {
            id: uuidv4(),
            name: 'A 机位',
            position: legacyCam.position,
            target: legacyCam.lookAt || { x: 0, y: 0, z: 0 },
            fov: legacyCam.fov ?? 50,
            active: true,
            followSubjectId: null,
          }
        : defaultCamera(),
    ]
  }
  if (!cameras.some(c => c.active)) cameras[0].active = true

  const subjects: SubjectData[] = (d.subjects || []).map(withId)
  const lights: LightData[] = (d.lights || []).map(withId)
  const props: PropData[] = (d.props || []).map(withId)
  const shots: ShotData[] = (d.shots || []).map((s: any) => ({
    ...withId(s),
    keyframes: (s.keyframes || []).map((k: any) => ({
      ...k,
      easing: k.easing || 'smooth',
    })),
    duration: s.duration || 4,
    fps: s.fps || 24,
    shotSize: s.shotSize || 'medium',
    cameraMove: s.cameraMove || 'static',
  }))

  return {
    stage: { ...stage, environment, aspect_ratio: stage.aspect_ratio || d.aspect_ratio || '' },
    subjects,
    cameras,
    lights,
    props,
    shots,
    activeShotId: d.activeShotId ?? null,
  }
}
