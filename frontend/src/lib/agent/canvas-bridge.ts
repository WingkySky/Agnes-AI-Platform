/* =====================================================
 * 画布 ↔ Agent 节点引用桥
 *
 * - 画布页挂载时注册（提供节点索引与引用构造），卸载时注销（editor-bridge 同款注册表）
 * - 引用卡作为 MessageAttachment.canvas_ref 随消息落库；chat store 发送时经
 *   buildCanvasRefBlock 把编号映射追加进给 LLM 的文本（用户原文不动）
 * - 本模块不接触 Vue 组件与 store，只面向纯数据
 * ===================================================== */

/** 画布节点引用载荷（附件 canvas_ref 字段与消息 canvasRefs 数组共用形状） */
export interface CanvasRefPayload {
  kind: 'node'
  workspaceId: string
  nodeId: string
  /** 面板类型：image / video / text / compose / … */
  nodeType: string
  name: string
  /** 人类可读短标签（引用卡/编号行共用） */
  label: string
  /** 媒体 URL（image/video 节点；文本节点缺省） */
  mediaUrl?: string
}

/** 节点摘要（弹层列表用，@ 触发展示） */
export interface CanvasNodeSummary {
  id: string
  type: string
  name: string
  mediaUrl?: string
}

/** 画布页提供的实时上下文 */
export interface CanvasRefContext {
  workspaceId: string
  /** 实时节点摘要（含未保存态） */
  listNodes(): CanvasNodeSummary[]
  buildNodeRef(nodeId: string): CanvasRefPayload | null
  /** 当前选中节点（「引用选中」按钮用） */
  getSelectedNodeId(): string | null
}

export interface CanvasBridgeApi {
  workspaceId: string
  getRefContext(): CanvasRefContext | null
}

let bridge: CanvasBridgeApi | null = null

export function registerCanvasBridge(api: CanvasBridgeApi): void {
  bridge = api
}

export function unregisterCanvasBridge(): void {
  bridge = null
}

export function getCanvasBridge(): CanvasBridgeApi | null {
  return bridge
}

const NODE_TYPE_LABELS: Record<string, string> = {
  image: '图片',
  video: '视频',
  text: '文本',
  compose: '合成',
}

export function canvasNodeTypeLabel(type: string): string {
  return NODE_TYPE_LABELS[type] ?? type
}

/** 引用载荷 → 编号行（LLM 上下文用；中文即可，系统提示同为中文） */
export function canvasRefLine(ref: CanvasRefPayload, n: number): string {
  const type = canvasNodeTypeLabel(ref.nodeType)
  const name = ref.name ? `「${ref.name}」` : ''
  let hint = ''
  if (ref.nodeType === 'text') hint = ' — 正文在 content.content'
  else if (ref.mediaUrl) hint = ' — 媒体已就绪，可 agent_read_image 读取画面'
  return `[${n}] 节点 ${ref.nodeId}（${type}）${name}${hint}`
}

/** 动态上下文块：编号引用（无内容返回空串，调用方不发） */
export function buildCanvasRefBlock(
  refs: CanvasRefPayload[],
  ctx?: { workspaceId?: string },
): string {
  if (!refs.length) return ''
  const head = `[画布节点引用]（编号 ↔ 节点 id，可直接用作 canvas/agent_* 工具的寻址参数${ctx?.workspaceId || refs[0]?.workspaceId ? `；工作区 ${ctx?.workspaceId || refs[0].workspaceId}` : ''}）`
  return [head, ...refs.map((r, i) => canvasRefLine(r, i + 1))].join('\n')
}
