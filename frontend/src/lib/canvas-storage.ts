/* =====================================================
 * 画布持久化层（localforage 封装，按用户隔离）
 * - 持久化 key: agnes_canvas_v2_{userId}（userId 为空时用 "anon"）
 * - 不同用户登录后自动切换到自己的数据空间；匿名用户（未登录）共享 anon 空间
 * - 写入做 400ms 防抖，避免拖拽等高频操作反复序列化
 * - 暴露 switchCanvasUser(userId) 用于登录/退出后切换数据空间
 * - 暴露 isStorageReady() 用于 store 状态指示
 * ===================================================== */

import localforage from 'localforage'
import { useUserStore } from '@/stores/user'

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

const BASE_STORAGE_KEY = 'agnes_canvas_v2'
const V1_KEY = 'agnes_canvas_v1'
const SAVE_DEBOUNCE_MS = 400

/** 当前绑定的用户标识（字符串，空值存为 "anon"） */
let _currentUserKey: string = 'anon'

/** 不同用户使用同一 localforage 实例（只是 key 不同），避免频繁建实例 */
const canvasStore = localforage.createInstance({
  name: 'agnes-canvas',
  storeName: 'canvas_v2',
})

/** 当前用户的 key（首次使用时根据 user store 自动判定） */
function getUserKey(): string {
  try {
    const userStore = useUserStore()
    const uid = userStore?.userId
    if (uid != null && uid !== undefined) {
      _currentUserKey = 'u_' + String(uid)
    } else {
      _currentUserKey = 'anon'
    }
  } catch (_e) {
    // Pinia 尚未初始化，退回到匿名空间
    _currentUserKey = 'anon'
  }
  return _currentUserKey
}

/** 强制以指定 userId 切换画布数据空间；返回 true 表示发生了实际切换 */
export function switchCanvasUser(userId: number | string | null): string {
  const newKey = userId ? 'u_' + String(userId) : 'anon'
  const changed = newKey !== _currentUserKey
  _currentUserKey = newKey
  if (changed) {
    // 重置 ready 状态，确保下次 load 会使用新的 user key
    ready = false
    initPromise = null
  }
  return _currentUserKey
}

/** 返回当前绑定的 user key（用于调试） */
export function currentCanvasUserKey(): string {
  return _currentUserKey
}

/** 按当前用户计算存储 key */
function storageKey(): string {
  return BASE_STORAGE_KEY + '_' + getUserKey()
}

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
 * 从 localforage 读取当前用户的画布状态
 * @returns 当前用户的数据；不存在或解析失败返回 null
 */
export async function loadCanvas(): Promise<CanvasStorageData | null> {
  await ensureReady()
  try {
    const key = storageKey()
    const data = await canvasStore.getItem(key)
    return (data as CanvasStorageData) || null
  } catch {
    return null
  }
}

/**
 * 取消待执行的防抖保存
 * - 切换用户/工作区等场景下调用，避免清空数据过程中误写入空状态
 */
export function cancelSaveCanvas(): void {
  if (saveTimer) {
    clearTimeout(saveTimer)
    saveTimer = null
  }
}

/**
 * 防抖保存当前用户的画布状态到 localforage
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
      const key = storageKey()
      await canvasStore.setItem(key, plain)
    } catch (err) {
      // 持久化失败不应阻塞画布交互，仅打印警告便于排查
      // eslint-disable-next-line no-console
      console.warn('[canvas-storage] saveCanvas failed:', err)
    }
  }, SAVE_DEBOUNCE_MS)
}

/** 保留原 v1 迁移：若存在 v1 数据，复制一份到当前用户的 v2 key */
export async function migrateFromV1(): Promise<boolean> {
  await ensureReady()
  try {
    const raw = localStorage.getItem(V1_KEY)
    if (!raw) return false
    const data = JSON.parse(raw)
    await canvasStore.setItem(storageKey(), data)
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
