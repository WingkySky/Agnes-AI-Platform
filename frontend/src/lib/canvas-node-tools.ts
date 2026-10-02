/* =====================================================
 * canvas-node-tools 画布节点工具栏注册表
 *
 * 节点工具栏的唯一数据源：所有工具以声明式条目收敛于此，
 * 组件按 resolveToolbarTools 输出渲染（一级平铺 + 分类下拉）。
 * 新增工具 = 本文件加一条 + CanvasView 分发表加一行，不动渲染。
 * ===================================================== */

import type { Component } from 'vue'
import {
  Info, Trash2, RefreshCw, FolderPlus, Download, MessageSquare,
  Image as ImageIcon, ImagePlus, Minus, Plus, Upload, Video, Music2, Play,
  Copy, FileText, Lock, LockOpen, Brush, Scissors, Grid2x2,
  ZoomIn, Sparkles, Camera, Maximize2, History, Film, SkipBack, SkipForward, Sun, ScanFace,
} from 'lucide-vue-next'

/* ---------- 类型定义 ---------- */

/** 分类下拉的分组键（展示顺序固定：生成 → 编辑 → 管理） */
export type ToolGroup = 'generate' | 'edit' | 'manage'

/** 组装工具条目可见性/归属判断所需的节点上下文（由组件按 panel 现状计算） */
export interface ToolContext {
  type: string
  hasContent: boolean
  isError: boolean
  isLoading: boolean
  hasPrompt: boolean
  freeResize: boolean
  /** 分镜派生节点（getShotLineageInfo 命中） */
  isLineage: boolean
  /** 派生出处为图片链（kind === 'image'） */
  lineageIsImage: boolean
  /** 首帧节点（role 缺省或 first） */
  lineageIsFirst: boolean
  /** 已存在尾帧节点 */
  hasTailFrame: boolean
  /** 已存在前段帧节点 */
  hasPrevFrame: boolean
  /** 剧本分段数（>0 才提供生成分段视频） */
  chainSegments: number
}

/** 单个工具条目：id 即 CanvasView 分发表的路由键 */
export interface ToolDef {
  id: string
  icon?: Component
  /** 动态图标（随 ctx 切换，如锁比例↔自由比例），与 icon 二选一 */
  iconFn?: (ctx: ToolContext) => Component
  /** i18n key（canvas.hoverToolbar.*），动态文案（上传↔替换等）用函数分支 */
  labelKey: string | ((ctx: ToolContext) => string)
  danger?: boolean
  /** 归属分类下拉；不设 = 一级平铺。跨形态共享工具用函数按 ctx 定归属 */
  group?: ToolGroup | ((ctx: ToolContext) => ToolGroup | undefined)
  visible: (ctx: ToolContext) => boolean
  /** 点击时附带的动作参数（quick-generate 的 mode / capture-frame 的 position） */
  payload?: (ctx: ToolContext) => Record<string, unknown>
}

/** 解析结果：一级平铺条目 + 非空分类分组（固定 生成→编辑→管理 序） */
export interface ToolbarModel {
  primary: ToolDef[]
  groups: Array<{ key: ToolGroup; labelKey: string; tools: ToolDef[] }>
}

/* ---------- 条件简写 ---------- */

const isImage = (c: ToolContext) => c.type === 'image'
const isVideo = (c: ToolContext) => c.type === 'video'
const isText = (c: ToolContext) => c.type === 'text'
/** 图片/视频的共享工具归管理组，文本/音频等简单形态保持平铺 */
const mediaManage: (c: ToolContext) => ToolGroup | undefined = (c) =>
  isImage(c) || isVideo(c) ? 'manage' : undefined

/* ---------- 注册表（数组顺序即展示顺序：重试最前、删除最后） ---------- */

export const TOOL_DEFS: ToolDef[] = [
  // —— 状态与执行 ——
  { id: 'retry', icon: RefreshCw, labelKey: 'regenerate', visible: (c) => c.isError },
  {
    id: 'run-node', icon: Play, labelKey: 'runNode',
    visible: (c) => ['tts', 'subtitle', 'compose'].includes(c.type) && !c.isLoading,
  },

  // —— 快捷生成（文本节点平铺；图片节点平铺；分镜派生图片节点归生成组） ——
  {
    id: 'quick-generate-image',
    icon: ImageIcon,
    labelKey: (c) => (isText(c) ? 'generateImage' : 'quickImage'),
    group: (c) => (c.isLineage ? 'generate' : undefined),
    visible: (c) => (isText(c) ? true : isImage(c) && c.hasContent),
    payload: (c) => ({ mode: isText(c) ? 'text2image' : 'image2image' }),
  },
  {
    id: 'quick-generate-video',
    icon: Video,
    labelKey: (c) => (isText(c) ? 'generateVideo' : 'quickVideo'),
    // 分镜派生图片节点由 derive-video（生成视频）承担图生视频，不重复提供
    visible: (c) => (isText(c) ? true : isImage(c) && c.hasContent && !c.isLineage),
    payload: (c) => ({ mode: isText(c) ? 'text2video' : 'image2video' }),
  },

  // —— 分镜派生（生成组）：仅图片链的图片节点；图生视频对全部派生图开放，尾帧/前段/分段仅首帧 ——
  {
    id: 'derive-video', icon: Video, labelKey: 'deriveVideo', group: 'generate',
    visible: (c) => c.isLineage && c.lineageIsImage && isImage(c) && c.hasContent,
  },
  {
    id: 'derive-tail', icon: ImagePlus, labelKey: 'deriveTail', group: 'generate',
    visible: (c) => c.isLineage && c.lineageIsImage && isImage(c) && c.lineageIsFirst && !c.hasTailFrame && c.hasContent,
  },
  {
    id: 'derive-prev', icon: History, labelKey: 'derivePrev', group: 'generate',
    visible: (c) => c.isLineage && c.lineageIsImage && isImage(c) && c.lineageIsFirst && !c.hasPrevFrame && c.hasContent,
  },
  {
    id: 'derive-chain', icon: Film, labelKey: 'deriveChain', group: 'generate',
    visible: (c) => c.isLineage && c.lineageIsImage && isImage(c) && c.lineageIsFirst && c.chainSegments > 0 && c.hasContent,
  },
  {
    id: 'reshoot', icon: RefreshCw, labelKey: 'reshoot', group: 'generate',
    visible: (c) => c.isLineage && c.hasContent,
  },

  // —— 媒体再生成与理解（生成组） ——
  {
    id: 'regenerate', icon: RefreshCw, labelKey: 'regenerate', group: 'generate',
    visible: (c) => (isImage(c) || isVideo(c)) && !c.isError && !c.isLineage && c.hasPrompt && !c.isLoading,
  },
  {
    id: 'describe', icon: FileText, labelKey: 'describe', group: 'generate',
    visible: (c) => isImage(c) && c.hasContent,
  },

  // —— 视频截帧（生成组，产物为新图片节点） ——
  {
    id: 'capture-frame-first', icon: SkipBack, labelKey: 'captureFrameFirst', group: 'generate',
    visible: (c) => isVideo(c) && c.hasContent,
    payload: () => ({ position: 'first' }),
  },
  {
    id: 'capture-frame', icon: Film, labelKey: 'captureFrame', group: 'generate',
    visible: (c) => isVideo(c) && c.hasContent,
    payload: () => ({ position: 'current' }),
  },
  {
    id: 'capture-frame-last', icon: SkipForward, labelKey: 'captureFrameLast', group: 'generate',
    visible: (c) => isVideo(c) && c.hasContent,
    payload: () => ({ position: 'last' }),
  },

  // —— 文本排版 ——
  { id: 'font-size-down', icon: Minus, labelKey: 'fontSizeDown', visible: isText },
  { id: 'font-size-up', icon: Plus, labelKey: 'fontSizeUp', visible: isText },

  // —— 媒体源替换（一级；原「编辑」钮对媒体节点即替换文件，去重后直接明示） ——
  {
    id: 'replace-image', icon: Upload, labelKey: 'replaceImage',
    visible: (c) => isImage(c) && c.hasContent,
  },

  // —— 对话编辑（配置节点的聚焦编辑入口；媒体节点替换走上方替换钮） ——
  { id: 'edit', icon: MessageSquare, labelKey: 'edit', visible: (c) => c.type === 'config' && c.hasContent },

  // —— 素材上传 / 替换 ——
  {
    id: 'upload-image', icon: Upload, labelKey: 'uploadImage',
    visible: (c) => isImage(c) && !c.hasContent,
  },
  {
    id: 'upload-video', icon: Video,
    labelKey: (c) => (c.hasContent ? 'replaceVideo' : 'uploadVideo'),
    visible: isVideo,
  },
  {
    id: 'upload-audio', icon: Music2,
    labelKey: (c) => (c.hasContent ? 'replaceAudio' : 'uploadAudio'),
    visible: (c) => c.type === 'audio',
  },

  // —— 图片编辑（编辑组） ——
  { id: 'mask-edit', icon: Brush, labelKey: 'maskEdit', group: 'edit', visible: (c) => isImage(c) && c.hasContent },
  { id: 'crop', icon: Scissors, labelKey: 'crop', group: 'edit', visible: (c) => isImage(c) && c.hasContent },
  { id: 'split', icon: Grid2x2, labelKey: 'split', group: 'edit', visible: (c) => isImage(c) && c.hasContent },
  { id: 'upscale', icon: ZoomIn, labelKey: 'upscale', group: 'edit', visible: (c) => isImage(c) && c.hasContent },
  { id: 'super-resolution', icon: Sparkles, labelKey: 'superResolution', group: 'edit', visible: (c) => isImage(c) && c.hasContent },
  { id: 'angle', icon: Camera, labelKey: 'angle', group: 'edit', visible: (c) => isImage(c) && c.hasContent },
  { id: 'lighting', icon: Sun, labelKey: 'lighting', group: 'edit', visible: (c) => isImage(c) && c.hasContent },
  { id: 'emotion', icon: ScanFace, labelKey: 'emotion', group: 'edit', visible: (c) => isImage(c) && c.hasContent },
  {
    id: 'toggle-ratio',
    iconFn: (c) => (c.freeResize ? Lock : LockOpen),
    labelKey: (c) => (c.freeResize ? 'lockRatio' : 'unlockRatio'),
    group: 'edit',
    visible: (c) => isImage(c) && c.hasContent,
  },

  // —— 管理（管理组 / 简单形态平铺） ——
  { id: 'save-asset', icon: FolderPlus, labelKey: 'saveAsset', group: mediaManage, visible: (c) => c.hasContent },
  { id: 'download', icon: Download, labelKey: 'download', group: mediaManage, visible: (c) => c.hasContent && !isText(c) },
  { id: 'view-large', icon: Maximize2, labelKey: 'viewLarge', group: 'manage', visible: (c) => isImage(c) && c.hasContent },
  { id: 'copy-prompt', icon: Copy, labelKey: 'copyPrompt', group: 'manage', visible: (c) => isImage(c) && c.hasContent },
  { id: 'info', icon: Info, labelKey: 'viewNodeInfo', group: (c) => (c.hasContent ? mediaManage(c) : undefined), visible: () => true },
  { id: 'delete', icon: Trash2, labelKey: 'deleteNode', danger: true, visible: () => true },
]

/* ---------- 解析 ---------- */

const GROUP_ORDER: ToolGroup[] = ['generate', 'edit', 'manage']
const GROUP_LABEL_KEYS: Record<ToolGroup, string> = {
  generate: 'groupGenerate',
  edit: 'groupEdit',
  manage: 'groupManage',
}

function resolveGroup(def: ToolDef, ctx: ToolContext): ToolGroup | undefined {
  return typeof def.group === 'function' ? def.group(ctx) : def.group
}

/** 按上下文解析工具栏模型：过滤 visible → 一级按注册表序、分组固定 生成→编辑→管理 序，空组不输出 */
export function resolveToolbarTools(ctx: ToolContext): ToolbarModel {
  const visible = TOOL_DEFS.filter((def) => def.visible(ctx))
  const primary = visible.filter((def) => !resolveGroup(def, ctx))
  const groups = GROUP_ORDER.map((key) => ({
    key,
    labelKey: GROUP_LABEL_KEYS[key],
    tools: visible.filter((def) => resolveGroup(def, ctx) === key),
  })).filter((g) => g.tools.length > 0)
  return { primary, groups }
}

/** 读取条目图标（动态图标按 ctx 求值） */
export function toolIcon(def: ToolDef, ctx: ToolContext): Component | undefined {
  return def.iconFn ? def.iconFn(ctx) : def.icon
}

/** 读取条目的动态 i18n key */
export function toolLabelKey(def: ToolDef, ctx: ToolContext): string {
  return typeof def.labelKey === 'function' ? def.labelKey(ctx) : def.labelKey
}
