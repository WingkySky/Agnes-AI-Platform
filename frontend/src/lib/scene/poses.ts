/* =====================================================
 * 主体姿势预设（b2）：preset → 各关节欧拉角（度）
 * 只旋转关节，不动根节点（位置/朝向仍由主体拖拽控制）。
 * 每个预设只写非零关节，未列出的关节归零。
 * ===================================================== */

import type { JointName } from './mannequin'

/** 关节旋转（度）：[x, y, z] */
export type JointRotations = Partial<Record<JointName, [number, number, number]>>

export const POSE_PRESET_IDS = [
  'stand', 'walk', 'run', 'sit', 'sit_crossed',
  'arms_crossed', 'hands_up', 'point_ahead', 'wave',
  'look_back', 'head_down', 'talk_gesture',
] as const

export type PosePresetId = (typeof POSE_PRESET_IDS)[number]

export const POSE_PRESETS: Record<PosePresetId, JointRotations> = {
  // 自然站立（全零）
  stand: {},
  // 行走：左腿前右腿后，双臂反向摆动
  walk: {
    leftHip: [30, 0, 0],
    leftKnee: [10, 0, 0],
    rightHip: [-25, 0, 0],
    rightKnee: [30, 0, 0],
    leftShoulder: [-30, 0, 8],
    rightShoulder: [30, 0, -8],
    leftElbow: [15, 0, 0],
    spine: [4, 0, 0],
  },
  // 奔跑：大幅度摆臂屈肘，前倾
  run: {
    leftHip: [55, 0, 0],
    leftKnee: [70, 0, 0],
    rightHip: [-40, 0, 0],
    rightKnee: [95, 0, 0],
    leftShoulder: [-70, 0, 10],
    rightShoulder: [70, 0, -10],
    leftElbow: [80, 0, 0],
    rightElbow: [85, 0, 0],
    spine: [14, 0, 0],
  },
  // 坐（隐形椅）：大腿前平、小腿垂直
  sit: {
    leftHip: [-85, 0, 0],
    leftKnee: [85, 0, 0],
    rightHip: [-85, 0, 0],
    rightKnee: [85, 0, 0],
    leftShoulder: [10, 0, 6],
    rightShoulder: [10, 0, -6],
    spine: [6, 0, 0],
  },
  // 翘腿坐：坐姿 + 右腿搭左腿
  sit_crossed: {
    leftHip: [-85, 15, 0],
    leftKnee: [85, 0, 0],
    rightHip: [-80, -35, 40],
    rightKnee: [100, 0, 0],
    leftShoulder: [15, 0, 8],
    rightShoulder: [15, 0, -8],
    spine: [8, 0, 0],
  },
  // 抱臂：双臂交叉胸前
  arms_crossed: {
    leftShoulder: [15, 35, 45],
    leftElbow: [0, 0, 115],
    rightShoulder: [15, -35, -45],
    rightElbow: [0, 0, -115],
    spine: [3, 0, 0],
  },
  // 双手举高
  hands_up: {
    leftShoulder: [0, 0, 155],
    rightShoulder: [0, 0, -155],
    leftElbow: [10, 0, 0],
    rightElbow: [10, 0, 0],
  },
  // 右手指向前方
  point_ahead: {
    rightShoulder: [-88, 0, -6],
    leftShoulder: [8, 0, 7],
    spine: [2, -4, 0],
  },
  // 挥手致意：右臂高举弯曲摆动
  wave: {
    rightShoulder: [0, 0, -140],
    rightElbow: [35, 0, -25],
    leftShoulder: [8, 0, 6],
    head: [0, -8, 8],
  },
  // 回头：头部大幅回转
  look_back: {
    head: [0, 150, 0],
    neck: [0, 20, 0],
    spine: [0, 15, 0],
  },
  // 垂头丧气
  head_down: {
    head: [32, 0, 0],
    neck: [12, 0, 0],
    spine: [16, 0, 0],
    leftShoulder: [6, 0, 5],
    rightShoulder: [6, 0, -5],
  },
  // 交谈手势：右臂半抬肘弯
  talk_gesture: {
    rightShoulder: [-35, 0, -18],
    rightElbow: [55, 0, -20],
    leftShoulder: [10, 0, 6],
    spine: [2, -5, 0],
    head: [0, -10, 0],
  },
}

/** 取某预设的关节角度（未知预设回站立=空表） */
export function poseForPreset(preset?: string | null): JointRotations {
  if (preset && preset in POSE_PRESETS) return POSE_PRESETS[preset as PosePresetId]
  return {}
}
