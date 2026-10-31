/* =====================================================
 * 剪辑器 ↔ Agent 选区引用桥
 *
 * - 编辑器页挂载时注册（提供选中态与引用构造），卸载时注销（scene-bridge 同款注册表）
 * - 引用卡作为 MessageAttachment.editor_ref 随消息落库；chat store 发送时经
 *   buildEditorRefBlock 把编号映射追加进给 LLM 的文本（用户原文不动）
 * - 本模块不接触 Vue 组件与 store，只面向纯数据
 * ===================================================== */

/** 编辑器引用载荷（附件 editor_ref 字段与消息 editorRefs 数组共用形状） */
export interface EditorRefPayload {
  kind: 'clip' | 'track'
  projectId: string
  clipId?: string
  trackId?: string
  assetId?: number | null
  assetName?: string
  trackKind?: 'video' | 'audio' | 'subtitle'
  /** 时间线域秒 */
  start?: number
  end?: number
  /** 人类可读短标签（引用卡/编号行共用） */
  label: string
  /** 片段缩略图（dataURL 小图；帧未就绪缺省） */
  thumb?: string
}

/** 编辑器页提供的实时上下文（选中态 + 引用构造器） */
export interface EditorRefContext {
  projectId: string
  selectedClipId: string | null
  selectedTrackId: string | null
  playhead: number
  buildClipRef(clipId: string): Promise<EditorRefPayload | null>
  buildTrackRef(trackId: string): Promise<EditorRefPayload | null>
}

export interface EditorBridgeApi {
  uid: string
  getRefContext(): EditorRefContext | null
}

let bridge: EditorBridgeApi | null = null

export function registerEditorBridge(api: EditorBridgeApi): void {
  bridge = api
}

export function unregisterEditorBridge(): void {
  bridge = null
}

export function getEditorBridge(): EditorBridgeApi | null {
  return bridge
}

const TRACK_KIND_LABELS: Record<string, string> = { video: '视频', audio: '音频', subtitle: '字幕' }

/** 秒 → m:ss.d 短时间码（引用行/标签共用） */
export function editorRefTimecode(sec: number | undefined): string {
  if (sec == null || !Number.isFinite(sec) || sec < 0) return '0:00.0'
  const m = Math.floor(sec / 60)
  const s = sec - m * 60
  return `${m}:${s < 10 ? '0' : ''}${s.toFixed(1)}`
}

/** 引用载荷 → 编号行（LLM 上下文用；中文即可，系统提示同为中文） */
export function editorRefLine(ref: EditorRefPayload, n: number): string {
  if (ref.kind === 'track') {
    return `[${n}] 轨道 ${ref.trackId}（${TRACK_KIND_LABELS[ref.trackKind ?? ''] ?? ref.trackKind ?? '未知'}）`
  }
  const span = ref.start != null ? ` ${editorRefTimecode(ref.start)}-${editorRefTimecode(ref.end)}` : ''
  const name = ref.assetName ? `「${ref.assetName}」` : ''
  const track = ref.trackId ? ` · ${TRACK_KIND_LABELS[ref.trackKind ?? ''] ?? ''}轨 ${ref.trackId}` : ''
  const asset = ref.assetId != null ? ` · assetId=${ref.assetId}` : ''
  return `[${n}] 片段 ${ref.clipId}${name}${span}${track}${asset}`
}

/** 动态上下文块：编号引用 + 当前选中/播放头（无内容返回空串，调用方不发） */
export function buildEditorRefBlock(
  refs: EditorRefPayload[],
  ctx?: { projectId?: string; selectedClipId?: string | null; selectedTrackId?: string | null; playhead?: number },
): string {
  const lines = refs.map((r, i) => editorRefLine(r, i + 1))
  const sel = ctx?.selectedClipId
    ? `片段 ${ctx.selectedClipId}`
    : ctx?.selectedTrackId ? `轨道 ${ctx.selectedTrackId}` : ''
  const playhead = ctx?.playhead ? editorRefTimecode(ctx.playhead) : ''
  if (!lines.length && !sel && !playhead) return ''
  const head = `[剪辑器引用]（编号 ↔ clipId/trackId，可直接用作 editor_apply_ops 等剪辑器工具的寻址参数${ctx?.projectId ? `；工程 uid=${ctx.projectId}` : ''}）`
  const tail = [sel ? `当前选中：${sel}` : '', playhead ? `播放头：${playhead}` : ''].filter(Boolean).join('；')
  return [head, ...lines, tail].filter(Boolean).join('\n')
}
