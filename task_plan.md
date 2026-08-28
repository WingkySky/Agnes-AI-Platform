# Task Plan: LibTV P0 短剧主链路复刻

## Goal
按已批准设计 docs/superpowers/specs/2026-08-27-libtv-p0-storyboard-canvas-design.md 实现 P0：
脚本节点 → 批量分镜图 → 批量图生视频 → 片段重拍。数据本地优先（画布 JSON/localforage），后端只加无状态 /api/storyboard。

## Constraints（来自 AGENTS.md 与设计文档）
- 最少行数，不引入复杂抽象；不改无关文件；不回滚用户改动
- import 统一文件顶部；不做类型断言；i18n：新文案走 t()，zh-CN + en-US 都要加
- 后端统一响应结构 status/message/data 或 HTTPException；全异步（AsyncSession/httpx）
- 分镜上限 30；批量生成前积分预估确认
- 验证：前端 vue-tsc 类型检查 + 手动冒烟六场景（项目无测试基建）
- 文档：接口写 API.md；新表无需（无表）

## Phases

### Phase 0: 代码调研，确定集成点 — status: done
> 2026-08-28 复核：集成点已全部落地并验证（见 findings.md 验证结论）。
- stores/canvas.ts：节点类型定义、连线校验（19-45 行附近）、addPanel action、分组 action
- CanvasNode.vue：按类型渲染分支，script 类型挂子组件方式
- CanvasView.vue：生成 handler 模式（1054/1150/1261/2016/2246 附近）、taskQueue 注册回填
- lib/canvas-generation.ts：buildGenerationContext / createImageTask / createVideoTask 签名
- CanvasToolbar.vue / CanvasNodeHoverToolbar.vue / CanvasContextMenu.vue：入口扩展点
- 后端：main.py 路由注册、agnes_client.chat 用法、一个现有 route/service/schema 范例
- i18n：canvas 命名空间结构
- StepGroup：创建分组的 action 与数据结构

### Phase M1: script 节点 + /api/storyboard + 分镜列表编辑 — status: done
后端：schemas/storyboard.py、services/storyboard_service.py、routes/storyboard.py、main.py 注册
前端：类型注册、ScriptNodeContent.vue、CanvasToolbar 入口、api/storyboard.ts、i18n、连线校验

### Phase M2: 批量派生分镜图 — status: done
lib/canvas-storyboard.ts（纯逻辑：prompt 拼装/派生结构/网格布局/lineage）
stores/canvas.ts 批量创建 action（布局+连线+StepGroup）
积分预估确认（复用 useCreditEstimate 逻辑）

### Phase M3: 批量图生视频 + 片段重拍 — status: done
分镜图节点派生 video 节点（HoverToolbar/右键入口）
lineage 记录 + 单节点改 prompt 重生成

### Phase V: 验证与文档 — status: in_progress
> 2026-08-28 复核：脚本相关文件已 type-clean、后端路由已注册。余下为 35 个历史遗留类型错误（非脚本范围）与手动冒烟六场景。
vue-tsc 类型检查、后端语法检查、冒烟六场景清单核对
API.md 补 /api/storyboard；docs 更新

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|

## Decisions Log
- 2026-08-27: 范围 P0 生成侧；本地优先；方案 A（详见 spec）
- 2026-08-27: 角色参考图快照写入派生节点 referenceImages，不运行时上溯
