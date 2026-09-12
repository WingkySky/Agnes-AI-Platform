/* =====================================================
 * 能力库消费层（lib/storyboard）
 * - prompt_presets 唯一库：风格（type=style 的 prompt_config）与运镜词表（type=camera）
 * - 独立于广场 UI 的轻缓存读取，所有入口（Agent/向导/派生链）统一从这里取
 * - 库条目加 source 字段后，外部导入包与本地条目此处无差别消费
 * ===================================================== */

import { getPresets } from '@/api/presets'
import type { PromptPreset } from '@/types/preset'
import type { StyleConfig } from './schemas'
import { parseStyleConfig } from './schemas'

const PAGE_SIZE = 100

interface LibraryCache {
  styles: PromptPreset[]
  cameras: PromptPreset[]
}

let cache: LibraryCache | null = null
let inflight: Promise<LibraryCache> | null = null

async function fetchByType(type: 'style' | 'camera'): Promise<PromptPreset[]> {
  const result = await getPresets({ tab: 'plaza', type, sort: 'hot', page: 1, page_size: PAGE_SIZE })
  return result.items
}

/** 拉取并缓存库条目（风格 + 运镜）；force=true 强制刷新
 *  库不可用时降级为空列表且不缓存（风格=无风格段、运镜=模板回退自由描述），下次调用自动重试 */
export async function ensureLibrary(force = false): Promise<LibraryCache> {
  if (cache && !force) return cache
  if (!inflight || force) {
    inflight = (async () => {
      try {
        const [styles, cameras] = await Promise.all([fetchByType('style'), fetchByType('camera')])
        cache = { styles, cameras }
        return cache
      } catch (e) {
        // 库拉取失败：本次返回空库（不缓存），库恢复后下次调用自动拿到真数据
        console.warn('[storyboard/library] 预设库拉取失败，本次降级为空库:', e)
        return { styles: [], cameras: [] }
      } finally {
        inflight = null
      }
    })()
  }
  return inflight
}

/** 库内风格条目（选择器/Agent 卡片用）：cover 供可视化卡片，description 供 LLM 语义推荐 */
export interface StyleEntry {
  id: number
  name: string
  description: string
  cover: string
  config: StyleConfig
}

export async function listStyleEntries(): Promise<StyleEntry[]> {
  const lib = await ensureLibrary()
  return lib.styles.map((p) => ({
    id: p.id,
    name: p.name,
    description: typeof p.description === 'string' ? p.description : '',
    cover: typeof p.cover_image === 'string' ? p.cover_image : '',
    config: parseStyleConfig(p.prompt_config),
  }))
}

/** 运镜词表：库 camera 条目名（分镜拆分 LLM 只能取词表值；库为空时模板回退自由描述） */
export async function listCameraVocabulary(): Promise<string[]> {
  const lib = await ensureLibrary()
  return lib.cameras.map((p) => p.name).filter(Boolean)
}

/** 按库条目 id 解析风格配置；未命中返回 null（调用方回退自定义文本/空风格） */
export async function resolveStyleConfig(presetId: number | null): Promise<StyleConfig | null> {
  if (presetId == null) return null
  const lib = await ensureLibrary()
  const hit = lib.styles.find((p) => p.id === presetId)
  return hit ? parseStyleConfig(hit.prompt_config) : null
}
