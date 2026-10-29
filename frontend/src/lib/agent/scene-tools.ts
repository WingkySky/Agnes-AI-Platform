/* =====================================================
 * scene_* 导演台工具组（b4 对话式调度，UI 无关）
 *
 * - 架构=前端工具层 + scene-bridge：导演台页挂载时注册 scope 与数据桥，
 *   工具经桥读写当前编辑态（只改内存不落库，保存仍由用户点击顶栏）
 * - scene_read：全量场景数据（id 寻址）+ 当前选中，供模型理解现场
 * - scene_edit：分集合替换草稿（未提供的集合不变），applySceneDraft
 *   原子校验（引用/枚举/数值），任一失败整批拒绝并把 errors 回给模型重试
 * - 仅导演台页可用：桥缺席时返回结构化错误（与其他页工具互不影响）
 * ===================================================== */

import { Type } from 'typebox'
import { applySceneDraft, sceneSummary } from '@/lib/scene/draft'
import { getSceneBridge } from './scene-bridge'
import type { AgentToolResult } from './tools'
import type { HostTool } from './kernel'

const SCENE_UNAVAILABLE = '导演台未打开（仅在「3D 场景导演台」页面可用；请让用户打开导演台后重试）'

const looseEntity = Type.Record(Type.String(), Type.Unknown())

export const sceneReadTool: HostTool = {
  name: 'scene_read',
  description:
    '读取 3D 导演台当前场景的全量数据（id 寻址）：舞台/主体（含姿势/走位路径）/机位（含跟随）/灯光/道具/镜头（景别/运镜/时长/关键帧）与当前选中元素。编辑前必读。',
  parameters: Type.Object({}),
  group: 'read',
  execute: (): AgentToolResult => {
    const bridge = getSceneBridge()
    if (!bridge) return { ok: false, error: SCENE_UNAVAILABLE }
    const data = bridge.getScene()
    return {
      ok: true,
      data: {
        sceneId: bridge.getSceneId(),
        sceneName: bridge.getSceneName(),
        saved: bridge.getSceneId() != null,
        selection: bridge.getSelection(),
        scene: sceneSummary(data),
      },
    }
  },
}

export const sceneEditTool: HostTool = {
  name: 'scene_edit',
  description:
    '编辑 3D 导演台场景（不落库，用户确认后自行保存）。传入 draft：subjects/cameras/lights/props/shots 任一集合提供时**整体替换**该集合（实体的其他集合不变），stage/activeShotId 增量合并。实体必须带 id（scene_read 可取）；改机位需保留所有未删机位、shot.cameraId 必须指向存在的机位、camera.followSubjectId 指向存在的主体。整批原子生效：任何校验失败都不会改动，按返回 errors 修正后重试。常用：相机拉远=改 position 远离 target、主光左移=改 lights[0].x 为负、加镜头=shots 追加（cameraId 用现有机位）、改姿势=subject.pose.preset（stand/walk/run/sit/sit_crossed/arms_crossed/hands_up/point_ahead/wave/look_back/head_down/talk_gesture）。',
  parameters: Type.Object({
    stage: Type.Optional(
      Type.Object({
        environment: Type.Optional(
          Type.Object({
            type: Type.Optional(Type.String()),
            label: Type.Optional(Type.String()),
          }),
        ),
        aspect_ratio: Type.Optional(Type.String()),
      }),
    ),
    subjects: Type.Optional(Type.Array(looseEntity)),
    cameras: Type.Optional(Type.Array(looseEntity)),
    lights: Type.Optional(Type.Array(looseEntity)),
    props: Type.Optional(Type.Array(looseEntity)),
    shots: Type.Optional(Type.Array(looseEntity)),
    activeShotId: Type.Optional(Type.Union([Type.String(), Type.Null()])),
  }),
  group: 'write',
  execute: (args): AgentToolResult => {
    const bridge = getSceneBridge()
    if (!bridge) return { ok: false, error: SCENE_UNAVAILABLE }
    const result = applySceneDraft(bridge.getScene(), args)
    if (!result.ok) return { ok: false, error: `校验失败（未做任何修改）：${result.errors.join('；')}` }
    bridge.applyScene(result.scene)
    const applied = Object.keys(args).filter(k => args[k] !== undefined)
    return { ok: true, data: { applied, hint: '已应用到编辑态，保存需用户在导演台顶栏确认' } }
  },
}

export const SCENE_TOOLS: HostTool[] = [sceneReadTool, sceneEditTool]
