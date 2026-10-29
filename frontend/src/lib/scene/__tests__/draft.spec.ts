// Agent 场景草稿应用引擎测试（b4）
import { describe, expect, it } from 'vitest'

import { applySceneDraft, sceneSummary } from '../draft'
import { newSceneData } from '../normalize'

const base = () => {
  const d = newSceneData({ subject: '主角', environment: '工作室' })
  d.cameras.push({ ...d.cameras[0], id: 'cam-b', name: 'B 机位', active: false, position: { x: 3, y: 1.6, z: 4 } })
  d.cameras[0].active = true
  d.shots = [{
    id: 'shot-1', cameraId: 'cam-b', duration: 4, fps: 24, shotSize: 'medium', cameraMove: 'static',
    keyframes: [], prompt: '', coverUrl: null, derivedTaskIds: [],
  }]
  return d
}

describe('applySceneDraft', () => {
  it('相机拉远：替换 cameras 集合（两台都传），其余集合不动', () => {
    const d = base()
    const r = applySceneDraft(d, {
      cameras: [
        { ...d.cameras[0], position: { x: 0, y: 4, z: 12 } },
        d.cameras[1],
      ],
    })
    expect(r.ok).toBe(true)
    if (!r.ok) return
    expect(r.scene.cameras[0].position).toEqual({ x: 0, y: 4, z: 12 })
    expect(r.scene.subjects).toHaveLength(1)
    expect(r.scene.shots[0].cameraId).toBe('cam-b')
  })

  it('主光左移：lights 分集合替换', () => {
    const d = base()
    const lights = [{ ...d.lights[0], x: -6 }]
    const r = applySceneDraft(d, { lights })
    expect(r.ok).toBe(true)
    if (!r.ok) return
    expect(r.scene.lights[0].x).toBe(-6)
  })

  it('新增主体/镜头：带 id 的实体可直接追加', () => {
    const d = base()
    const r = applySceneDraft(d, {
      subjects: [...d.subjects, { id: 'sub-2', label: '配角', x: 2, y: 0, z: 1 }],
      shots: [...d.shots, { id: 'shot-2', cameraId: 'cam-b', duration: 3, fps: 25, shotSize: 'close_up', cameraMove: 'push_in', keyframes: [] }],
    })
    expect(r.ok).toBe(true)
    if (!r.ok) return
    expect(r.scene.subjects).toHaveLength(2)
    expect(r.scene.shots).toHaveLength(2)
  })

  it('镜头引用不存在的机位 → 原子拒绝', () => {
    const d = base()
    const r = applySceneDraft(d, {
      shots: [{ ...d.shots[0], cameraId: 'ghost' }],
    })
    expect(r.ok).toBe(false)
    if (r.ok) return
    expect(r.errors.join()).toContain('ghost')
  })

  it('删机位 → 引用它的镜头自动改挂第一机位', () => {
    const d = base()
    const r = applySceneDraft(d, { cameras: [d.cameras[0]] })
    expect(r.ok).toBe(true)
    if (!r.ok) return
    expect(r.scene.cameras).toHaveLength(1)
    expect(r.scene.shots[0].cameraId).toBe(r.scene.cameras[0].id)
  })

  it('删被跟随主体 → 跟随机位自动解除跟随', () => {
    const d = base()
    d.cameras[0].followSubjectId = d.subjects[0].id
    const r = applySceneDraft(d, { subjects: [{ ...d.subjects[0], id: 'new-sub' }] })
    expect(r.ok).toBe(true)
    if (!r.ok) return
    expect(r.scene.cameras[0].followSubjectId).toBeNull()
  })

  it('枚举/数值越界逐一报错（fov/shotSize/fps/easing）', () => {
    const d = base()
    const r = applySceneDraft(d, {
      cameras: [{ ...d.cameras[0], fov: 500 }],
      shots: [{ ...d.shots[0], fps: 60, shotSize: 'bad', keyframes: [{ time: 0, position: { x: 0, y: 1, z: 0 }, target: { x: 0, y: 0, z: 0 }, fov: 50, easing: 'ease' }] }],
    })
    expect(r.ok).toBe(false)
    if (r.ok) return
    const all = r.errors.join()
    expect(all).toContain('fov')
    expect(all).toContain('fps')
    expect(all).toContain('shotSize')
    expect(all).toContain('easing')
  })

  it('缺 id / 重复 id 拒绝', () => {
    const d = base()
    const noId = applySceneDraft(d, { subjects: [{ label: '无id', x: 0, y: 0, z: 0 }] })
    expect(noId.ok).toBe(false)
    const dup = applySceneDraft(d, { subjects: [d.subjects[0], { ...d.subjects[0] }] })
    expect(dup.ok).toBe(false)
  })

  it('activeShotId 指向不存在镜头拒绝', () => {
    const d = base()
    const r = applySceneDraft(d, { activeShotId: 'nope' })
    expect(r.ok).toBe(false)
  })

  it('stage 环境替换 + 归一化补 id', () => {
    const d = base()
    const r = applySceneDraft(d, { stage: { environment: { type: 'night', label: '雨夜' } } })
    expect(r.ok).toBe(true)
    if (!r.ok) return
    expect(r.scene.stage.environment.type).toBe('night')
  })
})

describe('sceneSummary', () => {
  it('剥离 coverUrl/derivedTaskIds 重字段', () => {
    const d = base()
    d.shots[0].coverUrl = 'data:image/png;base64,xxx'
    d.shots[0].derivedTaskIds = ['t1']
    const s = sceneSummary(d) as { shots: Record<string, unknown>[] }
    expect(s.shots[0].coverUrl).toBe('<已截图>')
    expect(s.shots[0].derivedTaskIds).toBeUndefined()
  })
})
