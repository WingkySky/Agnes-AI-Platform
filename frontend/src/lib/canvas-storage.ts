/* =====================================================
 * 画布持久化层（localforage 封装）
 * - 持久化 key: agnes_canvas_v2（IndexedDB / WebSQL / localStorage 自动降级）
 * - 写入做 400ms 防抖，避免拖拽等高频操作反复序列化
 * - 提供 v1 → v2 一次性迁移：读取 localStorage 'agnes_canvas_v1' 写入 localforage 后删除 v1 key
 * - 暴露 isStorageReady() 用于 store 状态指示
 * ===================================================== */

import localforage from 'localforage'

/** 画布持久化数据结构 */
interface CanvasStorageData {
  workspaces?: any[]
  activeWorkspaceId?: string | null
  themeMode?: string
  backgroundMode?: string
  showImageInfo?: boolean
  viewport?: Record<string, any>
  panels?: any[]
  connections?: any[]
}

const STORAGE_KEY = 'agnes_canvas_v2'
const V1_KEY = 'agnes_canvas_v1'
const SAVE_DEBOUNCE_MS = 400

// 单独 instance，避免污染项目中其他 localforage 调用
const canvasStore = localforage.createInstance({
  name: 'agnes-canvas',
  storeName: 'canvas_v2',
})

let ready = false
let initPromise: Promise<void> | null = null
let saveTimer: ReturnType<typeof setTimeout> | null = null

/** 等待 localforage 就绪；幂等 */
function ensureReady(): Promise<void> {
  if (initPromise) return initPromise
  initPromise = canvasStore
    .ready()
    .then(() => {
      ready = true
    })
    .catch(() => {
      ready = false
    }) as Promise<void>
  return initPromise
}

// 启动时立即触发一次 ready 探测
ensureReady()

/**
 * 从 localforage 读取画布状态
 * @returns v2 数据；不存在或解析失败返回 null
 */
export async function loadCanvas(): Promise<CanvasStorageData | null> {
  await ensureReady()
  try {
    const data = await canvasStore.getItem(STORAGE_KEY)
    return (data as CanvasStorageData) || null
  } catch {
    return null
  }
}

/**
 * 防抖保存画布状态到 localforage
 * - 400ms 内多次调用会合并为一次写入
 * - 不阻塞调用方，返回 undefined
 * @param state 画布 store 状态（部分字段会被写入）
 */
export function saveCanvas(state: CanvasStorageData): void {
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(async () => {
    saveTimer = null
    await ensureReady()
    try {
      // 关键：Pinia state 是 Proxy 响应式对象，IndexedDB 无法结构化克隆 Proxy。
      // 必须先 JSON 序列化剥离 Proxy，转成纯对象后再写入，否则会抛 DataCloneError。
      const plain = JSON.parse(JSON.stringify({
        workspaces: state.workspaces,
        activeWorkspaceId: state.activeWorkspaceId,
        themeMode: state.themeMode,
        backgroundMode: state.backgroundMode,
        showImageInfo: state.showImageInfo,
        viewport: state.viewport,
        panels: state.panels,
        connections: state.connections,
      }))
      await canvasStore.setItem(STORAGE_KEY, plain)
    } catch (err) {
      // 持久化失败不应阻塞画布交互，仅打印警告便于排查
      // eslint-disable-next-line no-console
      console.warn('[canvas-storage] saveCanvas failed:', err)
    }
  }, SAVE_DEBOUNCE_MS)
}

/**
 * 从 localStorage 'agnes_canvas_v1' 一次性迁移到 v2
 * - 成功迁移后删除 v1 key
 * @returns 是否真的发生了迁移
 */
export async function migrateFromV1(): Promise<boolean> {
  await ensureReady()
  try {
    const raw = localStorage.getItem(V1_KEY)
    if (!raw) return false
    const data = JSON.parse(raw)
    await canvasStore.setItem(STORAGE_KEY, data)
    localStorage.removeItem(V1_KEY)
    return true
  } catch {
    return false
  }
}

/** localforage 是否就绪（用于 store 状态指示） */
export function isStorageReady(): boolean {
  return ready
}
