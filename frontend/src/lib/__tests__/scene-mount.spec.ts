// 场景挂载生成纯函数 + store 测试（导演台第一批）
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('@/api/scenes', () => ({
  previewScenePrompt: vi.fn(async () => ({ prompt_suffix: '平视视角，中景构图。三点布光。' })),
  getScenes: vi.fn(async () => ({ items: [] })),
}))

import { composeSceneSuffix, sceneCameraParams } from '../scene-mount'
import { useScenesStore } from '../../stores/scenes'
import type { Scene3D } from '../../types/scene'

describe('sceneCameraParams', () => {
  const cam = (y: number, px = 0, pz = 5, lx = 0, lz = 0) => ({
    position: { x: px, y, z: pz },
    lookAt: { x: lx, y: 0, z: lz },
    fov: 50,
  })

  it('相机高度映射视角（俯/仰/平，阈值对齐后端翻译器）', () => {
    expect(sceneCameraParams(cam(4))?.camera_angle).toBe('俯视')
    expect(sceneCameraParams(cam(0.1))?.camera_angle).toBe('仰视')
    expect(sceneCameraParams(cam(1.6))?.camera_angle).toBe('平视')
  })

  it('xz 距离映射焦段五档', () => {
    expect(sceneCameraParams(cam(1.6, 0, 5, 0, 4.8))?.focal_length).toBe('85mm')  // 距离≈1.2
    expect(sceneCameraParams(cam(1.6, 0, 5, 0, 2.5))?.focal_length).toBe('50mm')  // 距离 2.5
    expect(sceneCameraParams(cam(1.6, 0, 5, 0, 0))?.focal_length).toBe('35mm')    // 距离 5
    expect(sceneCameraParams(cam(1.6, 0, 11, 0, 0))?.focal_length).toBe('16mm')   // 距离 11
  })

  it('无相机数据返回 null', () => {
    expect(sceneCameraParams(null)).toBeNull()
    expect(sceneCameraParams(undefined)).toBeNull()
  })
})

describe('composeSceneSuffix', () => {
  it('空挂载返回空串', () => {
    expect(composeSceneSuffix(null)).toBe('')
    expect(composeSceneSuffix(undefined)).toBe('')
  })

  it('有挂载返回带前缀的后缀', () => {
    expect(composeSceneSuffix({ scene_id: 1, name: 's', suffix: '平视视角。', camera: null }))
      .toBe('场景设定：平视视角。')
  })
})

describe('scenes store 挂载', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  const scene = { id: 7, name: '雨夜天台', scene_data: { camera: { position: { x: 0, y: 1.6, z: 5 }, lookAt: { x: 0, y: 0, z: 0 }, fov: 50 } } } as unknown as Scene3D

  it('挂载后缓存后缀与相机，再点同场景取消', async () => {
    const store = useScenesStore()
    const mounted = await store.mountScene(scene, 'image')
    expect(mounted).toBe(true)
    expect(store.mountedFor('image')?.scene_id).toBe(7)
    expect(store.mountedFor('image')?.suffix).toContain('平视视角')
    expect(store.mountedFor('image')?.camera?.position.y).toBe(1.6)
    expect(store.isMountedIn('image', 7)).toBe(true)

    const again = await store.mountScene(scene, 'image')
    expect(again).toBe(false)
    expect(store.mountedFor('image')).toBeNull()
  })

  it('图片与视频上下文互不影响', async () => {
    const store = useScenesStore()
    await store.mountScene(scene, 'image')
    expect(store.mountedFor('video')).toBeNull()
    await store.mountScene(scene, 'video')
    expect(store.mountedFor('image')?.scene_id).toBe(7)
    expect(store.mountedFor('video')?.scene_id).toBe(7)
    store.unmountScene('video')
    expect(store.mountedFor('video')).toBeNull()
    expect(store.mountedFor('image')?.scene_id).toBe(7)
  })
})
