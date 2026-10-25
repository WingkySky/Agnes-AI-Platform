// 主体姿势预设表测试（b2）
import { describe, expect, it } from 'vitest'

import { MANNEQUIN_JOINTS } from '../mannequin'
import { POSE_PRESET_IDS, POSE_PRESETS, poseForPreset } from '../poses'

describe('POSE_PRESETS', () => {
  it('预设 id 列表与表一一对应', () => {
    expect(Object.keys(POSE_PRESETS).sort()).toEqual([...POSE_PRESET_IDS].sort())
  })

  it('每个预设只引用合法关节且角度为三元数字', () => {
    for (const [id, joints] of Object.entries(POSE_PRESETS)) {
      for (const [joint, rot] of Object.entries(joints)) {
        expect(MANNEQUIN_JOINTS).toContain(joint)
        expect(rot, `${id}.${joint}`).toHaveLength(3)
        for (const deg of rot) {
          expect(Number.isFinite(deg), `${id}.${joint}`).toBe(true)
        }
      }
    }
  })

  it('站立预设为空表（全关节归零）', () => {
    expect(POSE_PRESETS.stand).toEqual({})
  })

  it('坐姿双腿对称前平 + 膝盖回折', () => {
    expect(POSE_PRESETS.sit.leftHip![0]).toBeCloseTo(POSE_PRESETS.sit.rightHip![0])
    expect(POSE_PRESETS.sit.leftKnee![0]).toBeGreaterThan(60)
  })
})

describe('poseForPreset', () => {
  it('未知/空预设回退站立（空表）', () => {
    expect(poseForPreset(null)).toEqual({})
    expect(poseForPreset(undefined)).toEqual({})
    expect(poseForPreset('nonexistent')).toEqual({})
  })

  it('合法预设返回关节角度', () => {
    const pose = poseForPreset('point_ahead')
    expect(pose.rightShoulder).toBeDefined()
  })
})
