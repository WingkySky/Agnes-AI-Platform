/* =====================================================
 * 画布持久化层（双通道：登录态走云端 API，匿名走 localforage）
 *
 * - 云端：每工作区一行（canvas_workspaces），400ms 防抖 + 串行单飞保存队列，
 *   PUT 带 base_revision 乐观锁，409 冲突走「冲突副本」流程（见 store 注入的 handler）
 * - 本地：持久化 key: agnes_canvas_v2_{userId}（userId 为空时用 "anon"），
 *   不同用户登录后自动切换到自己的数据空间；匿名用户共享 anon 空间
 * - 暴露 switchCanvasUser(userId) 用于登录/退出后切换数据空间
 * - 暴露 isStorageReady() / canvasSaveStatus（保存状态指示器）供 UI 消费
 * ===================================================== */

import { reactive } from 'vue'
import localforage from 'localforage'
import { useUserStore } from '@/stores/user'
import {
  createWorkspace as createWorkspaceApi,
  deleteWorkspace as deleteWorkspaceApi,
  getWorkspace,
  getWorkspaceRevision,
  listWorkspaces,
  saveWorkspace,
} from '@/api/canvasWorkspace'
import { patchPreferences, getPreferences } from '@/api/preferences'
import type { WorkspaceDetail } from '@/api/canvasWorkspace'

/** 画布持久化数据结构 */
interface CanvasStorageData {
  workspaces?: any[]
  activeWorkspaceId?: string | null
  themeMode?: string
  backgroundMode?: string
  showImageInfo?: boolean
  autoPlaceMedia?: boolean
  viewport?: Record<string, any>
  panels?: any[]
  connections?: any[]
  groups?: any[]
}

/** 保存状态（顶栏指示器消费；anon 通道不更新） */
export const canvasSaveStatus = reactive<{ saving: boolean; lastSavedAt: string | null; error: boolean }>({
  saving: false,
  lastSavedAt: null,
  error: false,
})

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

// =====================================================
// 云端通道（登录态）
// =====================================================

/** 每工作区的云端乐观锁版本号（hydrate 载入 / 保存响应更新） */
const cloudRevisions = new Map<string, number>()

/** 冲突副本处理器（由 canvas store 注入，避免本模块 ↔ store 循环依赖） */
type ConflictHandler = (cloud: {
  id: string
  name: string
  data: Record<string, unknown>
  revision: number
}) => void | Promise<void>
let conflictHandler: ConflictHandler | null = null

export function setCanvasConflictHandler(fn: ConflictHandler | null): void {
  conflictHandler = fn
}

/** 登录态走云端通道；Pinia 未初始化视为未登录（anon） */
export function isCloudChannel(): boolean {
  try {
    return !!useUserStore()?.isAuthenticated
  } catch {
    return false
  }
}

/** 工作区对象 → data JSON（panels/connections/groups/viewport/styleConfig） */
function workspaceToData(ws: Record<string, any>): Record<string, unknown> {
  return {
    panels: ws.panels ?? [],
    connections: ws.connections ?? [],
    groups: ws.groups ?? [],
    viewport: ws.viewport ?? {},
    styleConfig: ws.styleConfig ?? null,
  }
}

/** 云端 WorkspaceDetail → 本地工作区对象 */
function cloudDetailToLocal(d: WorkspaceDetail): Record<string, any> {
  const data = (d.data ?? {}) as Record<string, any>
  return {
    id: d.id,
    name: d.name,
    work_id: d.work_id ?? null,
    created_at: d.created_at,
    updated_at: d.updated_at,
    viewport: data.viewport ?? { x: 0, y: 0, zoom: 1 },
    panels: data.panels ?? [],
    connections: data.connections ?? [],
    groups: data.groups ?? [],
    styleConfig: data.styleConfig ?? null,
  }
}

/**
 * 云端加载：GET 列表 → 逐工作区取全量 → 读偏好小设置，组装为 CanvasStorageData
 * - 云端为空返回 null（调用方决定迁移/回退本地）
 * - 加载失败回退本地 localforage（避免白屏；状态置 error）
 */
export async function loadCanvasData(): Promise<CanvasStorageData | null> {
  if (!isCloudChannel()) return loadCanvas()
  try {
    const briefs = await listWorkspaces()
    if (!briefs.length) return null
    const workspaces: any[] = []
    for (const brief of briefs) {
      const detail = await getWorkspace(brief.id)
      cloudRevisions.set(detail.id, detail.revision)
      workspaces.push(cloudDetailToLocal(detail))
    }
    const data: CanvasStorageData = {
      workspaces,
      activeWorkspaceId: workspaces[0]?.id ?? null,
    }
    try {
      const prefs = await getPreferences()
      const ui = prefs?.preferences?.ui
      if (ui?.canvas_active_workspace_id) data.activeWorkspaceId = ui.canvas_active_workspace_id
      if (ui?.canvas_background_mode) data.backgroundMode = ui.canvas_background_mode
      if (typeof ui?.canvas_show_image_info === 'boolean') data.showImageInfo = ui.canvas_show_image_info
      if (typeof ui?.canvas_auto_place_media === 'boolean') data.autoPlaceMedia = ui.canvas_auto_place_media
    } catch {
      // 偏好读取失败不阻塞画布加载
    }
    return data
  } catch (err) {
    canvasSaveStatus.error = true
    // eslint-disable-next-line no-console
    console.warn('[canvas-storage] 云端加载失败，回退本地', err)
    return loadCanvas()
  }
}

/** 乐观锁保存单个工作区；404 懒创建（同 id 透传，数据随创建写入） */
async function saveWorkspaceWithLock(ws: Record<string, any>): Promise<void> {
  const base = cloudRevisions.get(String(ws.id)) ?? 0
  try {
    const resp = await saveWorkspace(String(ws.id), {
      data: workspaceToData(ws),
      base_revision: base,
      name: ws.name,
    })
    cloudRevisions.set(String(ws.id), resp.revision)
  } catch (err) {
    if ((err as Error & { status?: number }).status === 404) {
      const created = await createWorkspaceApi({
        id: String(ws.id),
        name: ws.name,
        work_id: ws.work_id ?? undefined,
        data: workspaceToData(ws),
      })
      cloudRevisions.set(String(ws.id), created.revision)
      return
    }
    throw err
  }
}

/** 保存单个工作区（含 409 冲突副本流程：拉云端 → 建副本 → 按新 revision 续推本地内容，仅重试一次） */
async function flushOneWorkspace(ws: Record<string, any>): Promise<void> {
  try {
    await saveWorkspaceWithLock(ws)
  } catch (err) {
    const status = (err as Error & { status?: number }).status
    if (status !== 409 || !conflictHandler) throw err
    const detail = await getWorkspace(String(ws.id))
    await conflictHandler({
      id: detail.id,
      name: detail.name,
      data: detail.data,
      revision: detail.revision,
    })
    cloudRevisions.set(String(ws.id), detail.revision)
    await saveWorkspaceWithLock(ws)
  }
}

/** 画布全局小设置 → user_preferences（ui 组，best effort） */
async function saveCanvasPrefsCloud(state: CanvasStorageData): Promise<void> {
  try {
    await patchPreferences({
      ui: {
        canvas_active_workspace_id: String(state.activeWorkspaceId ?? ''),
        canvas_background_mode: String(state.backgroundMode ?? ''),
        canvas_show_image_info: !!state.showImageInfo,
        canvas_auto_place_media: !!state.autoPlaceMedia,
      },
    })
  } catch (err) {
    // eslint-disable-next-line no-console
    console.warn('[canvas-storage] 偏好保存失败', err)
  }
}

// ---------- 云端保存队列（防抖 + 串行单飞） ----------

let cloudSaveTimer: ReturnType<typeof setTimeout> | null = null
let cloudPendingIds = new Set<string>()
let latestCloudState: CanvasStorageData | null = null
let cloudInFlight = false

async function runCloudQueue(): Promise<void> {
  if (cloudInFlight) return
  cloudInFlight = true
  canvasSaveStatus.saving = true
  try {
    while (cloudPendingIds.size > 0 && latestCloudState) {
      const ids = Array.from(cloudPendingIds)
      cloudPendingIds = new Set()
      const workspaces = latestCloudState.workspaces ?? []
      for (const id of ids) {
        const ws = workspaces.find((w) => String(w?.id) === id)
        if (!ws) continue
        await flushOneWorkspace(ws)
      }
      await saveCanvasPrefsCloud(latestCloudState)
      canvasSaveStatus.lastSavedAt = new Date().toLocaleTimeString()
      canvasSaveStatus.error = false
    }
  } catch (err) {
    canvasSaveStatus.error = true
    // eslint-disable-next-line no-console
    console.warn('[canvas-storage] 云端保存失败', err)
  } finally {
    cloudInFlight = false
    canvasSaveStatus.saving = false
  }
}

// =====================================================
// 工作区显式远端动作（rename/delete 无法经 active 保存覆盖）
// =====================================================

/** 新建/复制工作区后云端创建（懒创建兜底之外的显式入口，供冲突副本等场景使用） */
export async function createWorkspaceCloud(ws: Record<string, any>): Promise<void> {
  if (!isCloudChannel()) return
  try {
    const created = await createWorkspaceApi({
      id: String(ws.id),
      name: ws.name,
      work_id: ws.work_id ?? undefined,
      data: workspaceToData(ws),
    })
    cloudRevisions.set(String(ws.id), created.revision)
  } catch (err) {
    // eslint-disable-next-line no-console
    console.warn('[canvas-storage] 云端创建工作区失败', err)
  }
}

/** 删除工作区（云端连带删快照） */
export async function deleteWorkspaceCloud(id: string): Promise<void> {
  if (!isCloudChannel()) return
  try {
    await deleteWorkspaceApi(id)
    cloudRevisions.delete(String(id))
  } catch (err) {
    // eslint-disable-next-line no-console
    console.warn('[canvas-storage] 云端删除工作区失败', err)
  }
}

/** 重命名工作区（非激活工作区改名无法经 _save 覆盖，显式 PUT 数据+新名） */
export async function renameWorkspaceCloud(ws: Record<string, any>): Promise<void> {
  if (!isCloudChannel()) return
  try {
    const resp = await saveWorkspace(String(ws.id), {
      data: workspaceToData(ws),
      base_revision: cloudRevisions.get(String(ws.id)) ?? 0,
      name: ws.name,
    })
    cloudRevisions.set(String(ws.id), resp.revision)
  } catch (err) {
    // 404 由下次 _save 懒创建兜底；409 由下次 _save 冲突流程兜底
    // eslint-disable-next-line no-console
    console.warn('[canvas-storage] 云端重命名失败', err)
  }
}

// ---------- 远端变更感知（外部宿主增量写入的轻轮询） ----------

/** 云端保存队列是否空闲（无在途保存且无防抖挂起；空闲=本地无未保存内容） */
export function isCloudQueueIdle(): boolean {
  return !cloudInFlight && !cloudSaveTimer && cloudPendingIds.size === 0
}

/** 查询云端最新 revision 并与本地已知版本比对（未知版本/接口失败都视为无变化） */
export async function checkRemoteRevision(wsId: string): Promise<{ changed: boolean; revision: number } | null> {
  if (!isCloudChannel()) return null
  try {
    const remote = await getWorkspaceRevision(String(wsId))
    const known = cloudRevisions.get(String(wsId))
    return { changed: known !== undefined && remote.revision !== known, revision: remote.revision }
  } catch {
    return null
  }
}

/** 拉取云端工作区全量 data 并同步本地已知 revision（画布页合入远端变更用） */
export async function pullRemoteWorkspaceCloud(wsId: string): Promise<Record<string, unknown> | null> {
  if (!isCloudChannel()) return null
  try {
    const detail = await getWorkspace(String(wsId))
    cloudRevisions.set(String(wsId), detail.revision)
    return detail.data ?? {}
  } catch (err) {
    // eslint-disable-next-line no-console
    console.warn('[canvas-storage] 拉取云端工作区失败', err)
    return null
  }
}

// =====================================================
// 本地通道（anon，保持原有行为）
// =====================================================

/** 强制以指定 userId 切换画布数据空间；返回 true 表示发生了实际切换 */
export function switchCanvasUser(userId: number | string | null): string {
  const newKey = userId ? 'u_' + String(userId) : 'anon'
  const changed = newKey !== _currentUserKey
  _currentUserKey = newKey
  if (changed) {
    // 重置 ready 状态，确保下次 load 会使用新的 user key
    ready = false
    initPromise = null
    // 云端队列与版本号一并作废（换账号后旧版本号不再有效）
    cloudRevisions.clear()
    cloudPendingIds.clear()
    latestCloudState = null
    canvasSaveStatus.saving = false
    canvasSaveStatus.error = false
  }
  return _currentUserKey
}

/** 按当前用户计算存储 key */
function storageKey(): string {
  return BASE_STORAGE_KEY + '_' + getUserKey()
}

let ready = false
let initPromise: Promise<void> | null = null
let saveTimer: ReturnType<typeof setTimeout> | null = null
let latestLocalState: CanvasStorageData | null = null

/** 等待 localforage 就绪；幂等；超时时降级为不可用 */
const READY_TIMEOUT_MS = 3000

function ensureReady(): Promise<void> {
  if (initPromise) return initPromise
  initPromise = new Promise<void>((resolve) => {
    // 正常 ready 路径
    canvasStore
      .ready()
      .then(() => {
        ready = true
      })
      .catch(() => {
        ready = false
      })
      .finally(() => {
        resolve()
      })

    // 超时保护：3 秒后强制继续，避免 IndexedDB 不可用时整个页面白屏
    setTimeout(() => {
      if (!ready) {
        ready = false
        // 强制 resolve initPromise，避免外部 await 永远挂起
        resolve()
      }
    }, READY_TIMEOUT_MS)
  })
  return initPromise
}

// 启动时立即触发一次 ready 探测
ensureReady()

/**
 * 从 localforage 读取当前用户的画布状态（anon 通道；登录态走 loadCanvasData）
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
  if (cloudSaveTimer) {
    clearTimeout(cloudSaveTimer)
    cloudSaveTimer = null
  }
  cloudPendingIds.clear()
}

/**
 * 防抖保存画布状态（双通道分流）
 * - anon：整份状态写 localforage（原有行为）
 * - 登录：记录本次调用时的激活工作区（调用点即"刚被编辑同步"的工作区），防抖后走串行单飞队列
 *   逐个工作区 PUT（404 懒创建 / 409 冲突副本），最后同步偏好小设置
 * - 不阻塞调用方，返回 undefined
 * @param state 画布 store 状态（部分字段会被写入）
 */
export function saveCanvas(state: CanvasStorageData): void {
  if (isCloudChannel()) {
    latestCloudState = state
    const id = state.activeWorkspaceId != null ? String(state.activeWorkspaceId) : null
    if (id) cloudPendingIds.add(id)
    if (cloudSaveTimer) clearTimeout(cloudSaveTimer)
    cloudSaveTimer = setTimeout(() => {
      cloudSaveTimer = null
      void runCloudQueue()
    }, SAVE_DEBOUNCE_MS)
    return
  }
  latestLocalState = state
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(async () => {
    saveTimer = null
    await performLocalSave(state)
  }, SAVE_DEBOUNCE_MS)
}

/** anon 通道：整份状态写 localforage（剥 Pinia Proxy 后落盘） */
async function performLocalSave(state: CanvasStorageData): Promise<void> {
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
      autoPlaceMedia: state.autoPlaceMedia,
      viewport: state.viewport,
      panels: state.panels,
      connections: state.connections,
      groups: state.groups,
    }))
    const key = storageKey()
    await canvasStore.setItem(key, plain)
  } catch (err) {
    // 持久化失败不应阻塞画布交互，仅打印警告便于排查
    // eslint-disable-next-line no-console
    console.warn('[canvas-storage] saveCanvas failed:', err)
  }
}

/**
 * 立即强制保存（跳过防抖；Ctrl+S / 危险操作前调用）
 * - 云端：清掉防抖定时器直接跑队列（在途保存不受影响，队列幂等）
 * - anon：防抖挂起时立即落盘
 */
export function flushSaveCanvas(): void {
  if (cloudSaveTimer) {
    clearTimeout(cloudSaveTimer)
    cloudSaveTimer = null
  }
  if (isCloudChannel()) {
    void runCloudQueue()
    return
  }
  if (saveTimer) {
    clearTimeout(saveTimer)
    saveTimer = null
  }
  if (latestLocalState) void performLocalSave(latestLocalState)
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
