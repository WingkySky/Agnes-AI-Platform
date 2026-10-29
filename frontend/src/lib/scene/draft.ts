/* =====================================================
 * 场景草稿应用（b4 Agent 调度引擎，纯函数）
 * 语义：draft 中提供的集合整体替换对应集合，未提供的保持不变；
 * 全部校验通过才产出新场景（任一失败返回 errors，原场景不动，原子）。
 * 引用规则与 UI 一致：删相机→其镜头改挂第一机位；删主体→跟随该主体的机位解除跟随。
 * ===================================================== */

import { normalizeSceneData } from './normalize'
import type {
  CameraDevice,
  CameraMove,
  LightData,
  PropData,
  SceneData,
  ShotData,
  ShotSize,
  SubjectData,
} from '@/types/scene'

const SHOT_SIZES: readonly ShotSize[] = ['extreme_wide', 'wide', 'medium', 'medium_close', 'close_up', 'extreme_close_up']
const CAMERA_MOVES: readonly CameraMove[] = ['static', 'push_in', 'pull_out', 'pan', 'tilt', 'orbit', 'tracking', 'crane', 'handheld']
const ENV_TYPES = ['studio', 'indoor', 'outdoor', 'night', 'custom']
const EASINGS = ['linear', 'smooth', 'cut']

export interface SceneDraft {
  stage?: Partial<SceneData['stage']>
  subjects?: Partial<SubjectData>[]
  cameras?: Partial<CameraDevice>[]
  lights?: Partial<LightData>[]
  props?: Partial<PropData>[]
  shots?: Partial<ShotData>[]
  activeShotId?: string | null
}

export type SceneDraftResult = { ok: true; scene: SceneData } | { ok: false; errors: string[] }

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null && !Array.isArray(v)
}

function numError(path: string, v: unknown, min: number, max: number): string | null {
  if (typeof v !== 'number' || !Number.isFinite(v) || v < min || v > max) {
    return `${path} 需为 ${min}~${max} 的数值`
  }
  return null
}

function validateVec3(path: string, v: unknown, errors: string[]) {
  if (!isRecord(v) || ['x', 'y', 'z'].some(k => typeof v[k] !== 'number')) {
    errors.push(`${path} 需为 {x,y,z} 三维坐标`)
  }
}

function validateKeyframe(path: string, k: unknown, errors: string[]) {
  if (!isRecord(k)) {
    errors.push(`${path} 需为关键帧对象`)
    return
  }
  const e = numError(`${path}.time`, k.time, 0, 600)
  if (e) errors.push(e)
  validateVec3(`${path}.position`, k.position, errors)
  validateVec3(`${path}.target`, k.target, errors)
  const ef = numError(`${path}.fov`, k.fov, 10, 120)
  if (ef) errors.push(ef)
  if (!EASINGS.includes(k.easing as string)) errors.push(`${path}. easing 需为 linear/smooth/cut`)
}

function validateShots(shots: unknown, cameraIds: Set<string>, errors: string[]) {
  if (!Array.isArray(shots)) {
    errors.push('shots 需为数组')
    return
  }
  shots.forEach((s, i) => {
    const path = `shots[${i}]`
    if (!isRecord(s)) {
      errors.push(`${path} 需为对象`)
      return
    }
    if (typeof s.id !== 'string' || !s.id) errors.push(`${path}.id 缺失`)
    if (typeof s.cameraId !== 'string' || !cameraIds.has(s.cameraId)) {
      errors.push(`${path}.cameraId「${String(s.cameraId)}」不存在于 cameras`)
    }
    const d = numError(`${path}.duration`, s.duration, 0.5, 60)
    if (d) errors.push(d)
    if (s.fps !== 24 && s.fps !== 25 && s.fps !== 30) errors.push(`${path}.fps 需为 24/25/30`)
    if (!SHOT_SIZES.includes(s.shotSize as ShotSize)) errors.push(`${path}.shotSize 枚举非法`)
    if (!CAMERA_MOVES.includes(s.cameraMove as CameraMove)) errors.push(`${path}.cameraMove 枚举非法`)
    const kfs = s.keyframes
    if (!Array.isArray(kfs)) errors.push(`${path}.keyframes 需为数组`)
    else kfs.forEach((k, j) => validateKeyframe(`${path}.keyframes[${j}]`, k, errors))
  })
}

/** 应用草稿（分集合替换，原子校验；通过后经 normalizeSceneData 补默认） */
export function applySceneDraft(current: SceneData, draft: unknown): SceneDraftResult {
  if (!isRecord(draft)) return { ok: false, errors: ['draft 需为对象'] }

  const errors: string[] = []
  const next: SceneData = JSON.parse(JSON.stringify(current))

  // 逐集合校验形状；全部通过后再替换（校验基于 draft 内引用 + 与当前集合的并集）
  const drafts: Partial<Record<keyof SceneDraft, unknown[]>> = {}
  for (const key of ['subjects', 'cameras', 'lights', 'props', 'shots'] as const) {
    const v = draft[key]
    if (v === undefined) continue
    if (!Array.isArray(v)) {
      errors.push(`${key} 需为数组`)
      continue
    }
    v.forEach((item, i) => {
      if (!isRecord(item)) errors.push(`${key}[${i}] 需为对象`)
      else if (typeof item.id !== 'string' || !item.id) errors.push(`${key}[${i}].id 缺失（id 寻址必需）`)
    })
    const ids = v.filter(isRecord).map(it => it.id as string)
    if (new Set(ids).size !== ids.length) errors.push(`${key} 存在重复 id`)
    drafts[key] = v
  }

  if (draft.stage !== undefined) {
    if (!isRecord(draft.stage)) errors.push('stage 需为对象')
    else if (draft.stage.environment !== undefined) {
      const env = draft.stage.environment
      if (!isRecord(env) || !ENV_TYPES.includes(env.type as string)) {
        errors.push('stage.environment.type 枚举非法')
      }
    }
  }

  // 引用校验基于「替换后的集合」：替换集合含全部新实体，未替换集合沿用当前
  const cameraIds = new Set<string>((drafts.cameras ?? (current.cameras as unknown[])).filter(isRecord).map(c => c.id as string))
  const subjectIds = new Set<string>((drafts.subjects ?? (current.subjects as unknown[])).filter(isRecord).map(s => s.id as string))
  if (drafts.cameras) {
    for (const c of drafts.cameras.filter(isRecord)) {
      const follow = (c as Partial<CameraDevice>).followSubjectId
      if (follow != null && !subjectIds.has(follow as string)) {
        errors.push(`cameras[${String(c.id)}].followSubjectId「${String(follow)}」不存在于 subjects`)
      }
      const ef = numError(`cameras[${String(c.id)}].fov`, (c as Partial<CameraDevice>).fov ?? 50, 10, 120)
      if (ef) errors.push(ef)
    }
  }
  if (drafts.shots) validateShots(drafts.shots, cameraIds, errors)
  if (draft.activeShotId != null && !drafts.shots) {
    const exists = current.shots.some(s => s.id === draft.activeShotId)
    if (!exists) errors.push(`activeShotId「${String(draft.activeShotId)}」不存在`)
  }

  if (errors.length) return { ok: false, errors: errors.slice(0, 20) }

  // ---- 应用：分集合替换 ----
  if (drafts.subjects) next.subjects = drafts.subjects as SubjectData[]
  if (drafts.cameras) next.cameras = drafts.cameras as CameraDevice[]
  if (drafts.lights) next.lights = drafts.lights as LightData[]
  if (drafts.props) next.props = drafts.props as PropData[]
  if (drafts.shots) next.shots = drafts.shots as ShotData[]
  if (draft.stage !== undefined) next.stage = { ...next.stage, ...(draft.stage as SceneData['stage']) }
  if (draft.activeShotId !== undefined) next.activeShotId = draft.activeShotId as string | null

  // 引用修复（与 UI 同规则）：删相机→镜头改挂第一机位；删主体→跟随解除
  if (drafts.cameras && next.cameras.length) {
    const first = next.cameras[0].id
    for (const s of next.shots) {
      if (!next.cameras.some(c => c.id === s.cameraId)) s.cameraId = first
    }
  }
  if (drafts.subjects) {
    for (const c of next.cameras) {
      if (c.followSubjectId && !next.subjects.some(s => s.id === c.followSubjectId)) {
        c.followSubjectId = null
      }
    }
  }

  return { ok: true, scene: normalizeSceneData(next) }
}

/** scene_read 摘要：剥掉封面/派生留痕等对模型无意义的重字段 */
export function sceneSummary(data: SceneData): Record<string, unknown> {
  return {
    stage: data.stage,
    subjects: data.subjects,
    cameras: data.cameras,
    lights: data.lights,
    props: data.props,
    shots: data.shots.map(s => ({
      ...s,
      coverUrl: s.coverUrl ? '<已截图>' : null,
      derivedTaskIds: undefined,
    })),
    activeShotId: data.activeShotId,
  }
}
