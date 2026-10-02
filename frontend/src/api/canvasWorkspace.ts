/* =====================================================
 * 画布工作区云端落库 API
 *
 * 接口：
 *   GET    /api/canvas/workspaces                        列表（不含 data）
 *   POST   /api/canvas/workspaces                        创建（id 可透传，重复创建幂等）
 *   GET    /api/canvas/workspaces/{id}                   全量（data + revision）
 *   PUT    /api/canvas/workspaces/{id}                   保存（乐观锁，冲突 409）
 *   DELETE /api/canvas/workspaces/{id}                   删除（连带删快照）
 *   POST   /api/canvas/workspaces/{id}/snapshots         建快照（manual/pre_danger）
 *   GET    /api/canvas/workspaces/{id}/snapshots         快照列表（不含 data）
 *   GET    /api/canvas/workspaces/{id}/snapshots/{sid}   快照全量
 * ===================================================== */

import client from './client'

/** 工作区列表项（不含 data） */
export interface WorkspaceBrief {
  id: string
  name: string
  revision: number
  created_at: string
  updated_at: string
}

/** 工作区全量 */
export interface WorkspaceDetail extends WorkspaceBrief {
  data: Record<string, unknown>
}

/** 快照列表项（不含 data） */
export interface SnapshotBrief {
  id: number
  kind: 'auto' | 'manual' | 'pre_danger'
  name: string | null
  revision: number
  created_at: string
}

/** 快照全量 */
export interface SnapshotDetail extends SnapshotBrief {
  data: Record<string, unknown>
}

export function listWorkspaces(): Promise<WorkspaceBrief[]> {
  return client.get('/api/canvas/workspaces')
}

export function createWorkspace(payload: { id?: string; name: string; data?: Record<string, unknown> }): Promise<WorkspaceDetail> {
  return client.post('/api/canvas/workspaces', payload)
}

export function getWorkspace(id: string): Promise<WorkspaceDetail> {
  return client.get(`/api/canvas/workspaces/${id}`)
}

/** 保存（乐观锁）；409 冲突由 canvas-storage 走冲突副本流程，silent 避免拦截器弹通用错误 toast */
export function saveWorkspace(id: string, payload: { data: Record<string, unknown>; base_revision: number; name?: string }): Promise<{ revision: number }> {
  return client.put(`/api/canvas/workspaces/${id}`, payload, { silent: true })
}

export function deleteWorkspace(id: string): Promise<void> {
  return client.delete(`/api/canvas/workspaces/${id}`)
}

export function createSnapshot(id: string, kind: 'manual' | 'pre_danger', name?: string): Promise<SnapshotBrief> {
  return client.post(`/api/canvas/workspaces/${id}/snapshots`, { kind, name })
}

export function listSnapshots(id: string): Promise<{ items: SnapshotBrief[] }> {
  return client.get(`/api/canvas/workspaces/${id}/snapshots`)
}

export function getSnapshot(id: string, snapshotId: number): Promise<SnapshotDetail> {
  return client.get(`/api/canvas/workspaces/${id}/snapshots/${snapshotId}`)
}

export function deleteSnapshot(id: string, snapshotId: number): Promise<void> {
  return client.delete(`/api/canvas/workspaces/${id}/snapshots/${snapshotId}`)
}

/** 上传画布素材（拖入/粘贴的本地图片/视频），返回可直接访问的 URL */
export function uploadCanvasAsset(file: Blob, name: string): Promise<{ url: string }> {
  const form = new FormData()
  form.append('file', file, name)
  return client.post('/api/uploads/canvas', form)
}

/** 批量画布操作结果（对齐后端 apply_canvas_ops 的 outcome） */
export interface CanvasOpsResult {
  results: { index: number; op: string; ok: boolean; panel_id?: string; connection_id?: string; error?: string }[]
  new_panel_ids: string[]
  failed: number
  revision: number
}

/** 批量应用画布操作（add_panel / add_connection，支持按节点名引用；对话 Agent / 外部宿主增量写入） */
export function applyCanvasOps(id: string, ops: Record<string, unknown>[]): Promise<CanvasOpsResult> {
  return client.post(`/api/canvas/workspaces/${id}/ops`, { ops })
}

/** 工作区当前版本号（轻轮询用，不拉 data） */
export function getWorkspaceRevision(id: string): Promise<{ revision: number; updated_at: string }> {
  return client.get(`/api/canvas/workspaces/${id}/revision`)
}
