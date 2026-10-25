// SceneData v2 纯函数测试：关键帧插值 / 归一化 / 派生参数 / 面板布局偏好
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { sampleCameraTrack, shotsTotalDuration } from '../camera-track'
import { buildShotDeriveParams } from '../derive'
import { activeCamera, defaultShot, newSceneData, normalizeSceneData } from '../normalize'
import { loadWorkbenchLayout, saveWorkbenchLayout } from '../workbench-layout'
import type { CameraDevice, CameraKeyframe, ShotData } from '@/types/scene'

const kf = (time: number, x: number, easing: CameraKeyframe['easing'] = 'linear'): CameraKeyframe => ({
  time,
  position: { x, y: 1.6, z: 5 },
  target: { x: 0, y: 0, z: 0 },
  fov: 50,
  easing,
})

describe('sampleCameraTrack', () => {
  it('空关键帧返回 null', () => {
    expect(sampleCameraTrack([], 0)).toBeNull()
  })

  it('t 越界取首/末帧', () => {
    const frames = [kf(0, 0), kf(4, 8)]
    expect(sampleCameraTrack(frames, -1)?.position.x).toBe(0)
    expect(sampleCameraTrack(frames, 99)?.position.x).toBe(8)
  })

  it('linear 线性插值 position/target/fov', () => {
    const frames: CameraKeyframe[] = [
      kf(0, 0),
      { ...kf(4, 8), fov: 70, target: { x: 2, y: 0, z: 0 } },
    ]
    const pose = sampleCameraTrack(frames, 2)!
    expect(pose.position.x).toBe(4)
    expect(pose.fov).toBe(60)
    expect(pose.target.x).toBe(1)
  })

  it('smooth 用 smoothstep（中点 p=0.5 结果仍是中值，1/4 处缓入）', () => {
    const frames = [kf(0, 0, 'smooth'), kf(4, 8, 'smooth')]
    expect(sampleCameraTrack(frames, 2)!.position.x).toBe(4)
    expect(sampleCameraTrack(frames, 1)!.position.x).toBeCloseTo(8 * 0.15625, 5)
  })

  it('cut 先保持上一帧姿态，到本帧时刻才切换', () => {
    const frames = [kf(0, 0), kf(4, 8, 'cut'), kf(8, 16)]
    expect(sampleCameraTrack(frames, 3.9)!.position.x).toBe(0)
    expect(sampleCameraTrack(frames, 4.5)!.position.x).toBeGreaterThan(8)
  })

  it('乱序输入按时间排序后采样', () => {
    const frames = [kf(4, 8), kf(0, 0)]
    expect(sampleCameraTrack(frames, 2)!.position.x).toBe(4)
  })
})

describe('shotsTotalDuration', () => {
  it('累加各镜头时长', () => {
    const shots = [{ duration: 2 }, { duration: 3.5 }, { duration: 4 }] as ShotData[]
    expect(shotsTotalDuration(shots)).toBe(9.5)
    expect(shotsTotalDuration([])).toBe(0)
  })
})

describe('normalizeSceneData', () => {
  it('空输入补全默认结构（含一台激活机位）', () => {
    const d = normalizeSceneData(null)
    expect(d.cameras).toHaveLength(1)
    expect(d.cameras[0].active).toBe(true)
    expect(d.stage.environment.type).toBe('studio')
    expect(d.subjects).toEqual([])
    expect(d.shots).toEqual([])
  })

  it('缺 id 补 id、v1 顶层 environment 与 camera 就位', () => {
    const d = normalizeSceneData({
      environment: { type: 'night', label: '夜景' },
      subjects: [{ x: 0, y: 0, z: 0, label: '主角', rotation: { x: 0, y: 0, z: 0 } }],
      camera: { position: { x: 1, y: 2, z: 3 }, lookAt: { x: 0, y: 1, z: 0 }, fov: 40 },
      lights: [{ type: 'directional', x: 5, y: 8, z: 5, intensity: 1, direction: { x: 0, y: -1, z: 0 } }],
      props: [],
    })
    expect(d.stage.environment.type).toBe('night')
    expect(d.subjects[0].id).toBeTruthy()
    expect(d.lights[0].id).toBeTruthy()
    expect(d.cameras[0].position).toEqual({ x: 1, y: 2, z: 3 })
    expect(d.cameras[0].target).toEqual({ x: 0, y: 1, z: 0 })
    expect(d.cameras[0].fov).toBe(40)
  })

  it('已有 v2 数据保持不变、多机位无 active 时第一个置 active', () => {
    const src = newSceneData({ subject: '主角', environment: '工作室' })
    src.cameras.push({ ...src.cameras[0], id: 'cam-b', name: 'B 机位', active: false })
    src.cameras[0].active = false
    const d = normalizeSceneData(JSON.parse(JSON.stringify(src)))
    expect(d.cameras).toHaveLength(2)
    expect(d.cameras[0].id).toBe(src.cameras[0].id)
    expect(d.cameras.find(c => c.active)?.id).toBe(d.cameras[0].id)
  })

  it('shots 缺省字段补默认值', () => {
    const d = normalizeSceneData({ shots: [{ id: 's1', cameraId: 'c1' }] })
    expect(d.shots[0].duration).toBe(4)
    expect(d.shots[0].fps).toBe(24)
    expect(d.shots[0].shotSize).toBe('medium')
    expect(d.shots[0].cameraMove).toBe('static')
    expect(d.shots[0].keyframes).toEqual([])
  })
})

describe('activeCamera / defaultShot', () => {
  it('active 标记优先，无标记回退第一个', () => {
    const d = newSceneData({ subject: '主角', environment: '工作室' })
    expect(activeCamera(d)?.id).toBe(d.cameras[0].id)
    expect(activeCamera(null)).toBeNull()
    d.cameras.push({ ...d.cameras[0], id: 'cam-b', name: 'B 机位', active: true })
    d.cameras[0].active = false
    expect(activeCamera(d)?.id).toBe('cam-b')
  })

  it('defaultShot 首帧快照自机位当前姿态', () => {
    const cam: CameraDevice = {
      id: 'c1', name: 'A', position: { x: 1, y: 2, z: 3 }, target: { x: 0, y: 1, z: 0 }, fov: 45,
    }
    const shot = defaultShot(cam)
    expect(shot.cameraId).toBe('c1')
    expect(shot.keyframes).toHaveLength(1)
    expect(shot.keyframes[0].position).toEqual({ x: 1, y: 2, z: 3 })
    expect(shot.keyframes[0].fov).toBe(45)
  })
})

describe('buildShotDeriveParams', () => {
  const cam: CameraDevice = {
    id: 'c1', name: 'A', position: { x: 0, y: 4, z: 8 }, target: { x: 0, y: 0, z: 0 }, fov: 50,
  }
  const shot: ShotData = {
    id: 's1', cameraId: 'c1', duration: 6, fps: 25, shotSize: 'close_up', cameraMove: 'push_in',
    keyframes: [], coverUrl: 'data:image/png;base64,xxx',
  }

  it('图片派生：拼场景设定后缀 + 机位 camera_params', () => {
    const params = buildShotDeriveParams({
      shot, camera: cam, suffix: '。中景，特写，推镜。', userPrompt: '雨夜巷战',
      model: 'm1', kind: 'image', aspectRatio: '16:9',
    })
    expect(params.model).toBe('m1')
    expect(params.prompt).toBe('雨夜巷战\n场景设定：中景，特写，推镜。')
    expect(params.aspect_ratio).toBe('16:9')
    expect(params.camera_params).toEqual({ enabled: true, camera_angle: '俯视', focal_length: '24mm' })
    expect(params.seconds).toBeUndefined()
  })

  it('视频派生：duration→seconds、fps→frame_rate，截图作首帧切 image2video', () => {
    const params = buildShotDeriveParams({
      shot, camera: cam, suffix: '', userPrompt: '', model: 'v1', kind: 'video',
      useCoverAsFirstFrame: true,
    })
    expect(params.seconds).toBe(6)
    expect(params.frame_rate).toBe(25)
    expect(params.mode).toBe('image2video')
    expect(params.images).toEqual(['data:image/png;base64,xxx'])
  })

  it('无截图时视频保持文生视频', () => {
    const params = buildShotDeriveParams({
      shot: { ...shot, coverUrl: null }, camera: cam, suffix: '', userPrompt: 'p',
      model: 'v1', kind: 'video', useCoverAsFirstFrame: true,
    })
    expect(params.mode).toBeUndefined()
    expect(params.images).toBeUndefined()
  })
})

describe('workbench-layout', () => {
  beforeEach(() => {
    const store: Record<string, string> = {}
    vi.stubGlobal('localStorage', {
      getItem: (k: string) => store[k] ?? null,
      setItem: (k: string, v: string) => { store[k] = v },
      removeItem: (k: string) => { delete store[k] },
      clear: () => { for (const k of Object.keys(store)) delete store[k] },
    })
  })

  it('默认布局 + 保存回读', () => {
    const def = loadWorkbenchLayout()
    expect(def.leftWidth).toBe(260)
    expect(def.dockOpen).toBe(true)
    saveWorkbenchLayout({ ...def, leftWidth: 999, rightOpen: false })
    const loaded = loadWorkbenchLayout()
    expect(loaded.leftWidth).toBe(480)  // 越界钳到 max
    expect(loaded.rightOpen).toBe(false)
  })

  it('损坏数据回退默认', () => {
    localStorage.setItem('scene-workbench-layout', '{broken')
    expect(loadWorkbenchLayout().leftWidth).toBe(260)
  })
})
