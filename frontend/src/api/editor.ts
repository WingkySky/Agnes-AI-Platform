/* =====================================================
 * 剪辑器 API（/api/editor/projects）
 * 剪辑工程独立实体：document JSON + revision 乐观锁 + 渲染状态
 * ===================================================== */

import client from './client'

import type { EditorDocument } from '@/lib/editor-types'

/** 剪辑工程（列表项，不含 document） */
export interface EditingProjectBrief {
  id: number
  uid: string
  user_id: number
  work_id: number | null
  title: string
  revision: number
  final_url: string | null
  cover_url: string | null
  render_status: 'idle' | 'rendering' | 'succeeded' | 'failed'
  render_error: string | null
  render_progress: string | null
  source_workspace_id: string | null
  created_at: string | null
  updated_at: string | null
}

/** 剪辑工程详情（含 document） */
export interface EditingProjectDetail extends EditingProjectBrief {
  document: EditorDocument
}

/** 新建剪辑工程（document / asset_ids 二选一或都缺省=空工程） */
export function createEditorProject(body: {
  title: string
  work_id?: number | null
  source_workspace_id?: string | null
  document?: EditorDocument
  asset_ids?: number[]
}): Promise<EditingProjectDetail> {
  return client.post('/api/editor/projects', body)
}

/** 剪辑工程列表（可按作品筛） */
export function listEditorProjects(workId?: number): Promise<{ total: number; items: EditingProjectBrief[] }> {
  return client.get('/api/editor/projects', { params: workId != null ? { work_id: workId } : {} })
}

/** 剪辑工程详情 */
export function getEditorProject(uid: string): Promise<EditingProjectDetail> {
  return client.get(`/api/editor/projects/${uid}`)
}

/** 编辑工程元数据（标题/挂靠作品） */
/** 更新工程元数据（标题/挂靠/封面） */
export function updateEditorProject(uid: string, body: { title?: string; work_id?: number | null; cover_url?: string }): Promise<EditingProjectDetail> {
  return client.patch(`/api/editor/projects/${uid}`, body)
}

/** 删除剪辑工程 */
/** 上传剪辑工程封面原图（复用 /api/uploads/image）→ { url } */
export function uploadEditorCover(file: File): Promise<{ url: string }> {
  const form = new FormData()
  form.append('file', file)
  return client.post('/api/uploads/image', form)
}

export function deleteEditorProject(uid: string): Promise<unknown> {
  return client.delete(`/api/editor/projects/${uid}`)
}

/** 保存时间线文档（revision 乐观锁，409 冲突由调用方处理）；snapshotReason 仅 agent 工具层携带，触发服务端写前快照 */
export function saveEditorDocument(uid: string, document: EditorDocument, baseRevision: number, snapshotReason?: string): Promise<{ revision: number; saved_at: string }> {
  const body: Record<string, unknown> = { document, base_revision: baseRevision }
  if (snapshotReason) body.snapshot_reason = snapshotReason
  return client.put(`/api/editor/projects/${uid}/document`, body)
}

/** 远端 revision 轻查询（编辑器页轮询感知外部写入） */
export function getEditorRevision(uid: string): Promise<{ revision: number; render_status: string; updated_at: string | null }> {
  return client.get(`/api/editor/projects/${uid}/revision`)
}

/** agent 写前快照（列表不含 data） */
export interface EditorSnapshotBrief {
  id: number
  kind: string
  reason: string | null
  revision: number
  created_at: string | null
}

export function listEditorSnapshots(uid: string): Promise<{ items: EditorSnapshotBrief[] }> {
  return client.get(`/api/editor/projects/${uid}/snapshots`)
}

/** 快照全量（还原=拉 data 走正常保存链路） */
export function getEditorSnapshot(uid: string, snapshotId: number): Promise<EditorSnapshotBrief & { data: EditorDocument }> {
  return client.get(`/api/editor/projects/${uid}/snapshots/${snapshotId}`)
}

/** whisper 转写字幕草稿（指定音频轨） */
export function previewSubtitleSegments(uid: string, trackId: string): Promise<{ segments: { start: number; end: number; text: string }[] }> {
  return client.post(`/api/editor/projects/${uid}/subtitles/preview`, { track_id: trackId })
}

// ---------- 渲染 ----------

export interface RenderStatus {
  render_status: EditingProjectBrief['render_status']
  render_progress: string | null
  final_url: string | null
  render_error: string | null
}

/** 提交渲染（提交时快照 + clientOperationId 幂等） */
export function submitEditorRender(uid: string, clientOperationId?: string): Promise<RenderStatus> {
  return client.post(`/api/editor/projects/${uid}/render`, clientOperationId ? { client_operation_id: clientOperationId } : {})
}

/** 轮询渲染状态 */
export function getEditorRenderStatus(uid: string): Promise<RenderStatus> {
  return client.get(`/api/editor/projects/${uid}/render`)
}
