/* =====================================================
 * canvas-quick-menu 画布快速创建菜单注册表
 *
 * 双击空白 / 空白右键「新建节点」/ 拖线松手落点菜单的唯一数据源：
 * 菜单分组、连线候选过滤（复用连线类型校验）、推荐动作均为纯函数。
 * 新增节点类型 = NODE_ITEMS 加一条，三类菜单自动收录。
 * ===================================================== */

import type { Component } from 'vue'
import {
  Image as ImageIcon, Video, Music2, FileText, Settings2, Mic, Captions,
  Clapperboard, ClipboardList, Upload,
} from 'lucide-vue-next'
import { t } from '@/i18n'
import { validateConnectionTypes } from '@/stores/canvas'

/* ---------- 类型定义 ---------- */

/** 菜单项：节点类型项 / 上传动作项；推荐动作通过 content 预填区分（如 config 的生成模式） */
export interface QuickMenuItem {
  id: string
  kind: 'node' | 'upload'
  /** kind='node' 时的节点类型 */
  type?: string
  icon: Component
  /** i18n key（canvas.quickMenu.* 或 canvas.nodeNames.*） */
  labelKey: string
  /** 选中时预填进新节点 content 的字段 */
  content?: Record<string, unknown>
}

/** 分组面板的一组（数组顺序即展示顺序） */
export interface QuickMenuGroup {
  key: string
  labelKey: string
  items: QuickMenuItem[]
}

/** connect 模式解析结果：推荐动作 + 按连线校验过滤并去重后的候选分组 */
export interface ConnectMenuModel {
  recommendations: QuickMenuItem[]
  groups: QuickMenuGroup[]
}

/* ---------- 节点类型注册表（组内顺序即展示顺序） ---------- */

const GROUP_KEYS = ['ai', 'media', 'assist', 'action'] as const

const GROUP_LABEL_KEYS: Record<string, string> = {
  ai: 'canvas.quickMenu.groupAi',
  media: 'canvas.quickMenu.groupMedia',
  assist: 'canvas.quickMenu.groupAssist',
  action: 'canvas.quickMenu.groupAction',
}

interface NodeEntry {
  type: string
  icon: Component
  group: Exclude<(typeof GROUP_KEYS)[number], 'action'>
}

const NODE_ITEMS: NodeEntry[] = [
  { type: 'config', icon: Settings2, group: 'ai' },
  { type: 'image', icon: ImageIcon, group: 'media' },
  { type: 'video', icon: Video, group: 'media' },
  { type: 'audio', icon: Music2, group: 'media' },
  { type: 'text', icon: FileText, group: 'assist' },
  { type: 'script', icon: ClipboardList, group: 'assist' },
  { type: 'tts', icon: Mic, group: 'assist' },
  { type: 'subtitle', icon: Captions, group: 'assist' },
  { type: 'compose', icon: Clapperboard, group: 'assist' },
]

const UPLOAD_ITEM: QuickMenuItem = {
  id: 'action:upload', kind: 'upload', icon: Upload, labelKey: 'canvas.quickMenu.uploadImage',
}

/** 按类型构造节点菜单项（节点名复用 canvas.nodeNames.*） */
function nodeMenuItem(entry: NodeEntry): QuickMenuItem {
  return {
    id: `node:${entry.type}`, kind: 'node', type: entry.type,
    icon: entry.icon, labelKey: `canvas.nodeNames.${entry.type}`,
  }
}

/* ---------- 推荐动作（connect 模式） ---------- */

const REC_CONFIG_IMAGE: QuickMenuItem = {
  id: 'rec:gen-image', kind: 'node', type: 'config', icon: ImageIcon,
  labelKey: 'canvas.quickMenu.recGenerateImage', content: { mode: 'text2image' },
}
const REC_CONFIG_VIDEO: QuickMenuItem = {
  id: 'rec:gen-video', kind: 'node', type: 'config', icon: Video,
  labelKey: 'canvas.quickMenu.recGenerateVideo', content: { mode: 'text2video' },
}
const REC_CONFIG_PLAIN: QuickMenuItem = {
  id: 'rec:config', kind: 'node', type: 'config', icon: Settings2, labelKey: 'canvas.quickMenu.recCreateConfig',
}
const REC_TEXT: QuickMenuItem = {
  id: 'rec:text', kind: 'node', type: 'text', icon: FileText, labelKey: 'canvas.quickMenu.recCreateText',
}
const REC_VIDEO: QuickMenuItem = {
  id: 'rec:video', kind: 'node', type: 'video', icon: Video, labelKey: 'canvas.quickMenu.recCreateVideo',
}

/** 推荐动作：右锚出按源类型给生成入口；左锚入按目标类型的接收规则给上游节点 */
function resolveRecommendations(sourceType: string, anchorType: 'source' | 'target'): QuickMenuItem[] {
  if (anchorType === 'target') {
    // 左锚（输入）拖出：新节点为上游。compose 只收视频/配音/字幕，推荐视频节点；其余推荐文本节点
    return sourceType === 'compose' ? [REC_VIDEO] : [REC_TEXT]
  }
  // 右锚（输出）拖出：新节点为接收方。script 出边只允许 config；其余可连源推荐生成图/视频配置
  if (sourceType === 'script') return [REC_CONFIG_PLAIN]
  if (['text', 'image', 'video', 'audio'].includes(sourceType)) return [REC_CONFIG_IMAGE, REC_CONFIG_VIDEO]
  return []
}

/* ---------- 解析 ---------- */

/** create 模式：全部分组（AI 生成 → 媒体 → 辅助 → 快捷操作） */
export function resolveCreateGroups(): QuickMenuGroup[] {
  const groups: QuickMenuGroup[] = GROUP_KEYS.map((key) => ({
    key, labelKey: GROUP_LABEL_KEYS[key], items: [],
  }))
  for (const entry of NODE_ITEMS) {
    groups.find((g) => g.key === entry.group)!.items.push(nodeMenuItem(entry))
  }
  groups[groups.length - 1].items.push(UPLOAD_ITEM)
  return groups
}

/** connect 模式：推荐动作 + 可连候选（经连线类型校验过滤，推荐已覆盖的类型去重，空组不输出） */
export function resolveConnectMenu(sourceType: string, anchorType: 'source' | 'target'): ConnectMenuModel {
  const recommendations = resolveRecommendations(sourceType, anchorType)
  const coveredTypes = new Set(recommendations.map((item) => item.type))
  const candidateTypes = new Set(
    NODE_ITEMS
      .map((entry) => entry.type)
      .filter((type) => {
        if (coveredTypes.has(type)) return false
        const [from, to] = anchorType === 'source' ? [sourceType, type] : [type, sourceType]
        return !validateConnectionTypes(from, to)
      }),
  )
  const groups = GROUP_KEYS
    .filter((key) => key !== 'action')
    .map((key) => ({
      key, labelKey: GROUP_LABEL_KEYS[key],
      items: NODE_ITEMS.filter((entry) => entry.group === key && candidateTypes.has(entry.type)).map(nodeMenuItem),
    }))
    .filter((group) => group.items.length > 0)
  return { recommendations, groups }
}

/** 搜索过滤：按译文与节点类型 id 不区分大小写匹配；空查询原样返回 */
export function filterQuickMenuGroups(groups: QuickMenuGroup[], query: string): QuickMenuGroup[] {
  const q = query.trim().toLowerCase()
  if (!q) return groups
  return groups
    .map((group) => ({
      ...group,
      items: group.items.filter((item) =>
        t(item.labelKey).toLowerCase().includes(q) || (item.type || '').toLowerCase().includes(q)),
    }))
    .filter((group) => group.items.length > 0)
}
