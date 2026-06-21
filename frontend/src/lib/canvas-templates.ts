/* =====================================================
 * 画布模板管理（localforage 持久化，按用户隔离）
 *
 * 功能：
 *   - 预设工作流模板（系统内置，不可删除）
 *   - 用户自定义模板（用户从当前画布保存，可删除/重命名）
 *   - 从模板创建新画布（深拷贝模板数据到新 workspace）
 *   - 模板分类、搜索
 *
 * 存储结构：
 *   - 预设模板：硬编码在 PRESET_TEMPLATES 常量中，不持久化
 *   - 用户模板：localforage key = agnes_canvas_templates_{userKey}
 *     值为 CanvasTemplate[] 数组
 *
 * 模板数据包含：
 *   - workspace_data: { panels, connections, viewport }
 *   - 创建画布时深拷贝 workspace_data，重新生成 panel id
 *     （避免多个画布共用相同 id 导致状态混乱）
 * ===================================================== */

import localforage from 'localforage'
import { useUserStore } from '@/stores/user'
import { useI18n } from '@/i18n'

// ---------- 类型定义 ----------

/** 画布模板 */
export interface CanvasTemplate {
  id: string
  name: string
  description: string
  category: 'preset' | 'user'  // preset=系统预设, user=用户自定义
  icon?: string                 // 图标标识（用于 UI 显示）
  workspace_data: {
    panels: any[]
    connections: any[]
    viewport?: { x: number; y: number; zoom: number }
  }
  created_at?: string
  updated_at?: string
  user_id?: number | null       // 创建者 ID（预设为 null）
}

// ---------- localforage 实例 ----------

const templateStore = localforage.createInstance({
  name: 'agnes-canvas',
  storeName: 'canvas_templates',
})

const BASE_KEY = 'agnes_canvas_templates'

/** 获取当前用户的存储 key */
function getUserKey(): string {
  try {
    const userStore = useUserStore()
    const uid = userStore?.userId
    if (uid != null && uid !== undefined) {
      return 'u_' + String(uid)
    }
  } catch (_) {
    // Pinia 尚未初始化
  }
  return 'anon'
}

function storageKey(): string {
  return BASE_KEY + '_' + getUserKey()
}

// ---------- 工具函数 ----------

/** 生成唯一 ID */
function genId(prefix: string = 'tpl'): string {
  return `${prefix}_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`
}

/** 深拷贝（剥离 Proxy，避免 localforage 序列化失败） */
function deepClone<T>(obj: T): T {
  return JSON.parse(JSON.stringify(obj))
}

// ---------- 预设模板 ----------

/**
 * 系统预设工作流模板
 * - 每个模板预配置好节点、连线、提示词，用户只需替换图片即可使用
 * - 节点 id 使用固定占位符（如 'preset-text-1'），创建画布时会重新生成
 */
const PRESET_TEMPLATES: CanvasTemplate[] = [
  {
    id: 'preset-text2image',
    name: 'canvas.templates.presetItems.text2image.name',
    description: 'canvas.templates.presetItems.text2image.desc',
    category: 'preset',
    icon: 'EditPen',
    workspace_data: {
      viewport: { x: 0, y: 0, zoom: 1 },
      panels: [
        {
          id: 'preset-text-1',
          type: 'text',
          name: 'canvas.templates.nodeNames.prompt',
          x: 100, y: 200, width: 340, height: 240,
          content: { content: '一只可爱的橘猫，坐在窗台上，阳光明媚，写实风格，高清细节', status: 'idle', fontSize: 14 },
        },
        {
          id: 'preset-config-1',
          type: 'config',
          name: 'canvas.templates.nodeNames.generateConfig',
          x: 520, y: 200, width: 340, height: 240,
          content: {
            mode: 'text2image',
            model: '',
            size: '1024x1024',
            prompt: '',
            composerContent: '',
            generating: false,
            progress: 0,
          },
        },
      ],
      connections: [
        { id: 'preset-conn-1', source_panel_id: 'preset-text-1', target_panel_id: 'preset-config-1', type: 'auto' },
      ],
    },
  },
  {
    id: 'preset-image2image',
    name: 'canvas.templates.presetItems.image2image.name',
    description: 'canvas.templates.presetItems.image2image.desc',
    category: 'preset',
    icon: 'Picture',
    workspace_data: {
      viewport: { x: 0, y: 0, zoom: 1 },
      panels: [
        {
          id: 'preset-image-1',
          type: 'image',
          name: 'canvas.templates.nodeNames.referenceImage',
          x: 100, y: 200, width: 340, height: 240,
          content: { content: '', status: 'idle', prompt: '' },
        },
        {
          id: 'preset-text-1',
          type: 'text',
          name: 'canvas.templates.nodeNames.modifyPrompt',
          x: 100, y: 500, width: 340, height: 180,
          content: { content: '把这张图片转换为水彩画风格，保持构图不变', status: 'idle', fontSize: 14 },
        },
        {
          id: 'preset-config-1',
          type: 'config',
          name: 'canvas.templates.nodeNames.generateConfig',
          x: 520, y: 300, width: 340, height: 240,
          content: {
            mode: 'image2image',
            model: '',
            size: '1024x1024',
            prompt: '',
            composerContent: '',
            generating: false,
            progress: 0,
          },
        },
      ],
      connections: [
        { id: 'preset-conn-1', source_panel_id: 'preset-image-1', target_panel_id: 'preset-config-1', type: 'auto' },
        { id: 'preset-conn-2', source_panel_id: 'preset-text-1', target_panel_id: 'preset-config-1', type: 'auto' },
      ],
    },
  },
  {
    id: 'preset-image2video',
    name: 'canvas.templates.presetItems.image2video.name',
    description: 'canvas.templates.presetItems.image2video.desc',
    category: 'preset',
    icon: 'VideoCamera',
    workspace_data: {
      viewport: { x: 0, y: 0, zoom: 1 },
      panels: [
        {
          id: 'preset-image-1',
          type: 'image',
          name: 'canvas.templates.nodeNames.startImage',
          x: 100, y: 200, width: 340, height: 240,
          content: { content: '', status: 'idle', prompt: '' },
        },
        {
          id: 'preset-text-1',
          type: 'text',
          name: 'canvas.templates.nodeNames.motionDesc',
          x: 100, y: 500, width: 340, height: 180,
          content: { content: '镜头缓慢推进，画面中的元素随风轻轻摆动', status: 'idle', fontSize: 14 },
        },
        {
          id: 'preset-config-1',
          type: 'config',
          name: 'canvas.templates.nodeNames.videoConfig',
          x: 520, y: 300, width: 340, height: 240,
          content: {
            mode: 'image2video',
            model: '',
            aspect_ratio: '16:9',
            seconds: 5,
            prompt: '',
            composerContent: '',
            generating: false,
            progress: 0,
          },
        },
      ],
      connections: [
        { id: 'preset-conn-1', source_panel_id: 'preset-image-1', target_panel_id: 'preset-config-1', type: 'auto' },
        { id: 'preset-conn-2', source_panel_id: 'preset-text-1', target_panel_id: 'preset-config-1', type: 'auto' },
      ],
    },
  },
  {
    id: 'preset-multi-blend',
    name: 'canvas.templates.presetItems.multiBlend.name',
    description: 'canvas.templates.presetItems.multiBlend.desc',
    category: 'preset',
    icon: 'Connection',
    workspace_data: {
      viewport: { x: 0, y: 0, zoom: 1 },
      panels: [
        {
          id: 'preset-image-1',
          type: 'image',
          name: 'canvas.templates.nodeNames.referenceImage1',
          x: 100, y: 100, width: 300, height: 220,
          content: { content: '', status: 'idle', prompt: '' },
        },
        {
          id: 'preset-image-2',
          type: 'image',
          name: 'canvas.templates.nodeNames.referenceImage2',
          x: 100, y: 380, width: 300, height: 220,
          content: { content: '', status: 'idle', prompt: '' },
        },
        {
          id: 'preset-text-1',
          type: 'text',
          name: 'canvas.templates.nodeNames.blendPrompt',
          x: 100, y: 660, width: 300, height: 160,
          content: { content: '融合两张图片的风格，生成一张新图片', status: 'idle', fontSize: 14 },
        },
        {
          id: 'preset-config-1',
          type: 'config',
          name: 'canvas.templates.nodeNames.blendConfig',
          x: 480, y: 320, width: 340, height: 240,
          content: {
            mode: 'image2image',
            model: '',
            size: '1024x1024',
            prompt: '',
            composerContent: '',
            generating: false,
            progress: 0,
          },
        },
      ],
      connections: [
        { id: 'preset-conn-1', source_panel_id: 'preset-image-1', target_panel_id: 'preset-config-1', type: 'auto' },
        { id: 'preset-conn-2', source_panel_id: 'preset-image-2', target_panel_id: 'preset-config-1', type: 'auto' },
        { id: 'preset-conn-3', source_panel_id: 'preset-text-1', target_panel_id: 'preset-config-1', type: 'auto' },
      ],
    },
  },
  {
    id: 'preset-describe',
    name: 'canvas.templates.presetItems.describe.name',
    description: 'canvas.templates.presetItems.describe.desc',
    category: 'preset',
    icon: 'ChatDotRound',
    workspace_data: {
      viewport: { x: 0, y: 0, zoom: 1 },
      panels: [
        {
          id: 'preset-image-1',
          type: 'image',
          name: 'canvas.templates.nodeNames.originalImage',
          x: 100, y: 200, width: 340, height: 240,
          content: { content: '', status: 'idle', prompt: '' },
        },
        {
          id: 'preset-text-1',
          type: 'text',
          name: 'canvas.templates.nodeNames.reversePrompt',
          x: 520, y: 200, width: 340, height: 240,
          content: { content: '（点击图片工具栏的"反推"按钮，AI 会自动填充此处）', status: 'idle', fontSize: 14 },
        },
        {
          id: 'preset-config-1',
          type: 'config',
          name: 'canvas.templates.nodeNames.generateConfig',
          x: 940, y: 200, width: 340, height: 240,
          content: {
            mode: 'text2image',
            model: '',
            size: '1024x1024',
            prompt: '',
            composerContent: '',
            generating: false,
            progress: 0,
          },
        },
      ],
      connections: [
        // 图片节点连到 config：默认 text2image 模式下不使用图片，用户可切换为 image2image 模式把原图作为参考
        { id: 'preset-conn-1', source_panel_id: 'preset-image-1', target_panel_id: 'preset-config-1', type: 'auto' },
        // 文本节点连到 config：反推出的提示词作为生成输入
        { id: 'preset-conn-2', source_panel_id: 'preset-text-1', target_panel_id: 'preset-config-1', type: 'auto' },
      ],
    },
  },
]

// ---------- 用户模板 CRUD ----------

/** 加载当前用户的所有自定义模板 */
export async function loadUserTemplates(): Promise<CanvasTemplate[]> {
  try {
    await templateStore.ready()
    const data = await templateStore.getItem<CanvasTemplate[]>(storageKey())
    return data || []
  } catch (e) {
    console.warn('[canvas-templates] load user templates failed:', e)
    return []
  }
}

/** 保存用户模板列表到 localforage */
async function saveUserTemplates(templates: CanvasTemplate[]): Promise<void> {
  await templateStore.ready()
  // 剥离 Proxy，避免 localforage 序列化失败
  const plain = deepClone(templates)
  await templateStore.setItem(storageKey(), plain)
}

/** 获取所有模板（预设 + 用户自定义） */
export async function getAllTemplates(): Promise<CanvasTemplate[]> {
  const userTemplates = await loadUserTemplates()
  const { t } = useI18n()
  // 预设模板的 name/description/节点 name 存的是 i18n key，这里解析为当前语言文字
  const resolvedPresets = PRESET_TEMPLATES.map(tpl => {
    const resolved = deepClone(tpl)
    resolved.name = t(resolved.name)
    resolved.description = t(resolved.description)
    resolved.workspace_data.panels.forEach(p => {
      if (p.name) p.name = t(p.name)
    })
    return resolved
  })
  return [...resolvedPresets, ...userTemplates]
}

/**
 * 把当前画布保存为用户自定义模板
 * @param name 模板名称
 * @param description 模板描述
 * @param workspaceData 画布数据 { panels, connections, viewport }
 * @returns 新创建的模板
 */
export async function saveAsTemplate(
  name: string,
  description: string,
  workspaceData: { panels: any[]; connections: any[]; viewport?: any },
): Promise<CanvasTemplate> {
  const userTemplates = await loadUserTemplates()
  const now = new Date().toISOString()

  // 深拷贝画布数据，剥离 Proxy 和运行时状态
  const cleanPanels = workspaceData.panels.map(p => {
    const panel = deepClone(p)
    // 清除运行时状态（loading、error、generating 等）
    if (panel.content) {
      delete panel.content.status
      delete panel.content.errorDetails
      delete panel.content.generating
      delete panel.content.progress
      delete panel.content.describing
    }
    return panel
  })
  const cleanConnections = workspaceData.connections.map(c => deepClone(c))

  const template: CanvasTemplate = {
    id: genId('user'),
    name: name.trim() || '未命名模板',
    description: description.trim(),
    category: 'user',
    workspace_data: {
      panels: cleanPanels,
      connections: cleanConnections,
      viewport: deepClone(workspaceData.viewport || { x: 0, y: 0, zoom: 1 }),
    },
    created_at: now,
    updated_at: now,
    user_id: useUserStore().userId || null,
  }

  userTemplates.push(template)
  await saveUserTemplates(userTemplates)
  return template
}

/** 删除用户自定义模板（预设模板不可删除） */
export async function deleteUserTemplate(templateId: string): Promise<boolean> {
  const userTemplates = await loadUserTemplates()
  const idx = userTemplates.findIndex(t => t.id === templateId)
  if (idx === -1) return false
  userTemplates.splice(idx, 1)
  await saveUserTemplates(userTemplates)
  return true
}

/** 重命名用户自定义模板 */
export async function renameUserTemplate(templateId: string, newName: string): Promise<boolean> {
  const userTemplates = await loadUserTemplates()
  const tpl = userTemplates.find(t => t.id === templateId)
  if (!tpl) return false
  tpl.name = newName.trim() || tpl.name
  tpl.updated_at = new Date().toISOString()
  await saveUserTemplates(userTemplates)
  return true
}

// ---------- 从模板创建画布 ----------

/**
 * 从模板创建新画布数据
 * - 深拷贝模板的 panels/connections/viewport
 * - 重新生成所有 panel id 和 connection id（避免多画布 id 冲突）
 * - 同步更新 connections 中的 source_panel_id / target_panel_id 引用
 * - 同步更新 config 节点 composerContent 中的 @[node:xxx] 引用
 *
 * @param template 画布模板
 * @returns { panels, connections, viewport } 可直接用于创建新 workspace
 */
export function createWorkspaceFromTemplate(template: CanvasTemplate): {
  panels: any[]
  connections: any[]
  viewport: { x: number; y: number; zoom: number }
} {
  const idMap = new Map<string, string>()  // 旧 id → 新 id

  // 1. 深拷贝 panels，重新生成 id
  const newPanels = template.workspace_data.panels.map(p => {
    const newPanel = deepClone(p)
    const oldId = newPanel.id
    const newId = genId('panel')
    idMap.set(oldId, newId)
    newPanel.id = newId
    // 清除运行时状态
    if (newPanel.content) {
      newPanel.content.status = 'idle'
      delete newPanel.content.errorDetails
      delete newPanel.content.generating
      delete newPanel.content.progress
      delete newPanel.content.describing
    }
    return newPanel
  })

  // 2. 深拷贝 connections，更新 id 和引用
  const newConnections = template.workspace_data.connections.map(c => {
    const newConn = deepClone(c)
    newConn.id = genId('conn')
    newConn.source_panel_id = idMap.get(newConn.source_panel_id) || newConn.source_panel_id
    newConn.target_panel_id = idMap.get(newConn.target_panel_id) || newConn.target_panel_id
    return newConn
  })

  // 3. 更新 config 节点 composerContent / prompt 中的 @[node:xxx] 引用
  const nodeRefPattern = /@\[node:([^\]]+)\]/g
  newPanels.forEach(panel => {
    if (panel.type === 'config' && panel.content) {
      const updateRef = (text: string): string => {
        if (!text) return text
        return text.replace(nodeRefPattern, (match, oldNodeId) => {
          const newNodeId = idMap.get(oldNodeId)
          return newNodeId ? `@[node:${newNodeId}]` : match
        })
      }
      if (panel.content.composerContent) {
        panel.content.composerContent = updateRef(panel.content.composerContent)
      }
      if (panel.content.prompt) {
        panel.content.prompt = updateRef(panel.content.prompt)
      }
    }
  })

  // 4. 深拷贝 viewport
  const newViewport = deepClone(template.workspace_data.viewport || { x: 0, y: 0, zoom: 1 })

  return { panels: newPanels, connections: newConnections, viewport: newViewport }
}

// ---------- 切换用户时清理缓存 ----------

/**
 * 切换用户时调用（由 CanvasView 的 login/logout 事件触发）
 * - localforage 的 key 是动态计算的，无需额外操作
 * - 这里保留接口便于未来扩展（如内存缓存清理）
 */
export function onTemplateUserSwitch(): void {
  // localforage key 基于 getUserKey() 动态计算，无需额外处理
}
