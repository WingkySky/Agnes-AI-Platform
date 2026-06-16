/* =====================================================
 * 画布持久化层（localforage 封装）
 * - 持久化 key: agnes_canvas_v2（IndexedDB / WebSQL / localStorage 自动降级）
 * - 写入做 400ms 防抖，避免拖拽等高频操作反复序列化
 * - 提供 v1 → v2 一次性迁移：读取 localStorage 'agnes_canvas_v1' 写入 localforage 后删除 v1 key
 * - 暴露 isStorageReady() 用于 store 状态指示
 * ===================================================== */

import localforage from 'localforage'

const STORAGE_KEY = 'agnes_canvas_v2'
const V1_KEY = 'agnes_canvas_v1'
const SAVE_DEBOUNCE_MS = 400

// 单独 instance，避免污染项目中其他 localforage 调用
const canvasStore = localforage.createInstance({
  name: 'agnes-canvas',
  storeName: 'canvas_v2',
})

let ready = false
let initPromise = null
let saveTimer = null

/** 等待 localforage 就绪；幂等 */
function ensureReady() {
  if (initPromise) return initPromise
  initPromise = canvasStore
    .ready()
    .then(() => {
      ready = true
    })
    .catch(() => {
      ready = false
    })
  return initPromise
}

// 启动时立即触发一次 ready 探测
ensureReady()

/**
 * 从 localforage 读取画布状态
 * @returns {Promise<object|null>} v2 数据；不存在或解析失败返回 null
 */
export async function loadCanvas() {
  await ensureReady()
  try {
    const data = await canvasStore.getItem(STORAGE_KEY)
    return data || null
  } catch {
    return null
  }
}

/**
 * 防抖保存画布状态到 localforage
 * - 400ms 内多次调用会合并为一次写入
 * - 不阻塞调用方，返回 undefined
 * @param {object} state 画布 store 状态（部分字段会被写入）
 */
export function saveCanvas(state) {
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(async () => {
    saveTimer = null
    await ensureReady()
    try {
      await canvasStore.setItem(STORAGE_KEY, {
        workspaces: state.workspaces,
        activeWorkspaceId: state.activeWorkspaceId,
        themeMode: state.themeMode,
        viewport: state.viewport,
        panels: state.panels,
        connections: state.connections,
      })
    } catch {
      // 静默失败：持久化失败不应阻塞画布交互
    }
  }, SAVE_DEBOUNCE_MS)
}

/**
 * 从 localStorage 'agnes_canvas_v1' 一次性迁移到 v2
 * - 成功迁移后删除 v1 key
 * @returns {Promise<boolean>} 是否真的发生了迁移
 */
export async function migrateFromV1() {
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
export function isStorageReady() {
  return ready
}
