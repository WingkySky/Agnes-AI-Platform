/* =====================================================
 * 画布实体库 → 分镜资产上下文桥接
 *
 * work_entities 为唯一事实源：分镜链路（向导/编排器）从实体库取数，
 * 映射成 ScriptAssets 形状喂既有纯函数（buildShotContexts 签名不变）；
 * LLM 抽取/存量 content.assets 按名 upsert 进实体库一次性收敛。
 * ===================================================== */

import { createWorkEntity, listWorkEntities, type EntityKind, type WorkEntityItem } from '@/api/workEntities'
import type { ScriptAssets, ShotAsset } from '@/lib/canvas-storyboard'

function toShotAsset(e: WorkEntityItem): ShotAsset {
  return { id: `entity_${e.id}`, name: e.name, description: e.description || '', imageUrl: e.active_image_url || '' }
}

/** 拉实体库并映射成分镜资产形状（挂作品画布用；自由画布走 readAssets 存量路径） */
export async function loadEntityScriptAssets(workId: number): Promise<ScriptAssets> {
  const items = (await listWorkEntities(workId)).items
  return {
    characters: items.filter((e) => e.kind === 'character').map(toShotAsset),
    scenes: items.filter((e) => e.kind === 'scene').map(toShotAsset),
    props: items.filter((e) => e.kind === 'prop').map(toShotAsset),
  }
}

/** 按名（work+kind+name）upsert 实体：LLM 抽取清单与存量资产卡收敛入口；命中跳过不覆盖 */
export async function upsertEntitiesToLibrary(
  workId: number,
  candidates: Array<{ kind: EntityKind; name: string; description?: string }>,
): Promise<number> {
  const existing = (await listWorkEntities(workId)).items
  let created = 0
  for (const c of candidates) {
    const name = (c.name || '').trim()
    if (!name) continue
    if (existing.some((e) => e.kind === c.kind && e.name === name)) continue
    await createWorkEntity(workId, { kind: c.kind, name, description: c.description?.trim() || undefined })
    created++
  }
  return created
}
