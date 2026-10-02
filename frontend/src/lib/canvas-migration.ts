/* =====================================================
 * 本地存量画布一次性迁移到云端
 *
 * - 触发条件：登录态 + 云端不可达不迁移 + 云端已有数据永不迁移（幂等，避免
 *   "另一台设备已删除的工作区"被本机旧数据复活）
 * - 流程：逐工作区把 blob: 引用的本地图素材上传云端 → 替换为远程 URL →
 *   以原 id 创建云端工作区（id 透传，服务端幂等）
 * - 失败策略：单个工作区失败跳过继续，末尾汇总；本地 localforage 保留不删（兜底）
 * ===================================================== */

import { loadCanvas, isCloudChannel } from './canvas-storage'
import { createWorkspace, listWorkspaces, uploadCanvasAsset } from '@/api/canvasWorkspace'
import { useAssetStore } from '@/stores/canvasAsset'

export interface MigrationResult {
  /** 参与迁移的工作区总数（0 = 未触发） */
  total: number
  /** 失败数 */
  failed: number
}

/** 工作区对象 → data JSON（与 canvas-storage 的 workspaceToData 同构） */
function workspaceToData(ws: Record<string, any>): Record<string, unknown> {
  return {
    panels: ws.panels ?? [],
    connections: ws.connections ?? [],
    groups: ws.groups ?? [],
    viewport: ws.viewport ?? {},
    styleConfig: ws.styleConfig ?? null,
  }
}

/** 上传单个面板引用的本地图素材并替换 URL（仅处理 assetId + blob: 引用） */
async function migratePanelAssets(assetStore: ReturnType<typeof useAssetStore>, panel: Record<string, any>): Promise<void> {
  const content = panel?.content as Record<string, any> | undefined
  if (!content || typeof content.assetId !== 'string') return
  if (typeof content.content !== 'string' || !content.content.startsWith('blob:')) return
  const blob = await assetStore.getAssetBlob(content.assetId)
  if (!blob) return
  const ext = blob.type.includes('video') ? (blob.type === 'video/webm' ? 'webm' : 'mp4') : 'png'
  const resp = await uploadCanvasAsset(blob, `${panel?.name || content.assetId}.${ext}`)
  content.content = resp.url
}

/**
 * 把 localforage 里的本地画布迁移到云端（幂等；anon 直接跳过）
 * - 返回迁移统计；total=0 表示本调用未发生迁移（云端非空 / 无本地数据 / 不可达）
 */
export async function migrateLocalToCloudIfNeeded(): Promise<MigrationResult> {
  const result: MigrationResult = { total: 0, failed: 0 }
  if (!isCloudChannel()) return result
  let briefs
  try {
    briefs = await listWorkspaces()
  } catch (err) {
    // eslint-disable-next-line no-console
    console.warn('[canvas-migration] 云端不可达，跳过迁移', err)
    return result
  }
  if (!briefs || briefs.length > 0) return result
  const local = await loadCanvas()
  const workspaces = Array.isArray(local?.workspaces) ? (local!.workspaces as Record<string, any>[]) : []
  if (!workspaces.length) return result

  result.total = workspaces.length
  const assetStore = useAssetStore()
  await assetStore.hydrate() // 查 blob 前必须 hydrate（项目既有约束）
  for (const ws of workspaces) {
    try {
      const panels = Array.isArray(ws.panels) ? ws.panels : []
      for (const panel of panels) {
        await migratePanelAssets(assetStore, panel)
      }
      await createWorkspace({
        id: String(ws.id),
        name: String(ws.name || '未命名工作区'),
        data: workspaceToData(ws),
      })
    } catch (err) {
      result.failed++
      // eslint-disable-next-line no-console
      console.warn('[canvas-migration] 工作区迁移失败', ws?.id, err)
    }
  }
  return result
}
