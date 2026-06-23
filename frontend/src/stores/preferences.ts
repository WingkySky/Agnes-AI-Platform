/* =====================================================
 * 用户偏好设置 Store
 *
 * 负责：
 *   - 从后端拉取/更新用户偏好设置
 *   - 本地缓存偏好（避免每次访问都请求后端）
 *   - 自动下载核心逻辑（检测 auto_download 并触发下载）
 *   - 生成文件命名（含分类目录支持）
 *   - File System Access API 支持（用户指定下载目录，句柄持久化到 IndexedDB）
 *
 * 用法：
 *   const prefsStore = usePreferencesStore()
 *   await prefsStore.fetchPreferences()
 *   prefsStore.isAutoDownload        // 是否开启自动下载
 *   prefsStore.preferences.download  // 下载偏好
 *   prefsStore.autoDownload(url, type, metadata)  // 自动下载单个文件
 * ===================================================== */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import {
  getPreferences,
  patchPreferences,
  resetPreferences,
} from '@/api/preferences'
import type {
  UserPreferences,
  UserPreferencesUpdate,
  GenerationPreferences,
  DownloadPreferences,
  UIPreferences,
  NotificationPreferences,
} from '@/types'

// ================ IndexedDB：目录句柄持久化 ================
// FileSystemDirectoryHandle 支持 structured clone，可以存入 IndexedDB
// 这样用户授权一次后，刷新页面也能继续使用
const DB_NAME = 'agnes-downloads'
const DB_VERSION = 1
const STORE_NAME = 'directory-handle'
const HANDLE_KEY = 'download-dir'

let _db: IDBDatabase | null = null
let _directoryHandle: FileSystemDirectoryHandle | null = null
let _directoryHandleLoaded = false

/** 打开 IndexedDB */
function openDB(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    if (_db) { resolve(_db); return }
    const request = indexedDB.open(DB_NAME, DB_VERSION)
    request.onupgradeneeded = () => {
      const db = request.result
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        db.createObjectStore(STORE_NAME)
      }
    }
    request.onsuccess = () => {
      _db = request.result
      resolve(_db)
    }
    request.onerror = () => reject(request.error)
  })
}

/** 从 IndexedDB 加载目录句柄 */
async function loadDirectoryHandleFromDB(): Promise<FileSystemDirectoryHandle | null> {
  try {
    const db = await openDB()
    return new Promise((resolve) => {
      const tx = db.transaction(STORE_NAME, 'readonly')
      const store = tx.objectStore(STORE_NAME)
      const request = store.get(HANDLE_KEY)
      request.onsuccess = () => resolve(request.result || null)
      request.onerror = () => resolve(null)
    })
  } catch (e) {
    console.warn('[Preferences] IndexedDB 加载目录句柄失败:', e)
    return null
  }
}

/** 保存目录句柄到 IndexedDB */
async function saveDirectoryHandleToDB(handle: FileSystemDirectoryHandle | null): Promise<void> {
  try {
    const db = await openDB()
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE_NAME, 'readwrite')
      const store = tx.objectStore(STORE_NAME)
      if (handle) {
        store.put(handle, HANDLE_KEY)
      } else {
        store.delete(HANDLE_KEY)
      }
      tx.oncomplete = () => resolve()
      tx.onerror = () => reject(tx.error)
    })
  } catch (e) {
    console.warn('[Preferences] IndexedDB 保存目录句柄失败:', e)
  }
}

/**
 * 验证目录句柄的读写权限（可能因为浏览器安全策略需要用户重新确认）
 * @returns true 表示可以正常使用
 */
async function verifyDirectoryHandle(handle: FileSystemDirectoryHandle | null): Promise<boolean> {
  if (!handle) return false
  try {
    const opts: any = { mode: 'readwrite' }
    if ('queryPermission' in handle) {
      const status = await (handle as any).queryPermission(opts)
      if (status === 'granted') return true
      if (status === 'denied') return false
      const newStatus = await (handle as any).requestPermission(opts)
      return newStatus === 'granted'
    }
    return true
  } catch (e) {
    console.warn('[Preferences] 目录句柄权限验证失败:', e)
    return false
  }
}

/** 懒加载目录句柄（从 IndexedDB 恢复），确保仅初始化一次 */
async function getDirectoryHandle(): Promise<FileSystemDirectoryHandle | null> {
  if (_directoryHandleLoaded) return _directoryHandle
  _directoryHandleLoaded = true
  const handle = await loadDirectoryHandleFromDB()
  if (handle) {
    const valid = await verifyDirectoryHandle(handle)
    if (valid) {
      _directoryHandle = handle
      return handle
    } else {
      // 权限失效，清理掉
      await saveDirectoryHandleToDB(null)
      _directoryHandle = null
    }
  }
  return null
}

/** 设置目录句柄（同时写入 IndexedDB） */
async function setDirectoryHandle(handle: FileSystemDirectoryHandle | null): Promise<void> {
  _directoryHandle = handle
  await saveDirectoryHandleToDB(handle)
}

// ================ 目录选择（File System Access API） ================

/**
 * 选择下载目录并持久化
 * - 浏览器安全限制：不允许选择系统敏感目录（如 macOS 的 Downloads/Documents/Desktop 根目录）
 * - 返回详细的状态信息供 UI 层提示
 */
async function pickDownloadDirectory(): Promise<{
  handle: FileSystemDirectoryHandle | null
  error?: 'security' | 'unsupported' | 'abort' | 'unknown'
  errorMessage?: string
}> {
  if (!('showDirectoryPicker' in window)) {
    return { handle: null, error: 'unsupported' }
  }
  try {
    const handle = await (window as any).showDirectoryPicker({ mode: 'readwrite' })
    await setDirectoryHandle(handle)
    return { handle }
  } catch (e: any) {
    if (e.name === 'AbortError') {
      return { handle: null, error: 'abort' }
    }
    if (e.name === 'SecurityError' || e.name === 'NotAllowedError') {
      return { handle: null, error: 'security', errorMessage: e.message }
    }
    console.warn('[Preferences] showDirectoryPicker failed:', e)
    return { handle: null, error: 'unknown', errorMessage: e.message }
  }
}

/** 释放并清除目录句柄 */
async function releaseDirectoryHandle(): Promise<void> {
  await setDirectoryHandle(null)
}

/** 提示音播放器（Web Audio API 生成 beep，不依赖外部音频文件）*/
let _audioCtx: AudioContext | null = null
function getAudioContext(): AudioContext {
  if (!_audioCtx) {
    _audioCtx = new AudioContext()
  }
  return _audioCtx
}

/**
 * 播放完成提示音（短促 beep）
 * - 首选项 sound_on_complete = true 时调用
 * - 使用 Web Audio API 生成 800Hz 0.1s 正弦波
 */
function playCompletionBeep(): void {
  try {
    const ctx = getAudioContext()
    const oscillator = ctx.createOscillator()
    const gainNode = ctx.createGain()
    oscillator.connect(gainNode)
    gainNode.connect(ctx.destination)
    oscillator.frequency.value = 800
    oscillator.type = 'sine'
    gainNode.gain.setValueAtTime(0.3, ctx.currentTime)
    gainNode.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.2)
    oscillator.start(ctx.currentTime)
    oscillator.stop(ctx.currentTime + 0.2)
  } catch (e) {
    console.warn('[Preferences] playBeep failed:', e)
  }
}

/**
 * 发送浏览器通知
 * - 需用户授权（首次调用浏览器会自动弹窗请求）
 */
function sendBrowserNotification(title: string, body: string): void {
  if (!('Notification' in window)) return
  if (Notification.permission === 'granted') {
    try {
      new Notification(title, { body, icon: '/favicon.ico' })
    } catch (e) {
      console.warn('[Preferences] Notification failed:', e)
    }
  } else if (Notification.permission !== 'denied') {
    Notification.requestPermission().then((permission) => {
      if (permission === 'granted') {
        try {
          new Notification(title, { body, icon: '/favicon.ico' })
        } catch (e) {
          console.warn('[Preferences] Notification failed:', e)
        }
      }
    })
  }
}

/**
 * 生成完成时的综合通知（含提示音、浏览器通知、自动复制提示词）
 * - 在各生成流程的成功回调处调用
 * - 各行为受对应偏好开关控制
 *
 * @param fileType  image | video
 * @param metadata  prompt / modelId / url
 */
async function notifyComplete(
  fileType: 'image' | 'video',
  metadata: { prompt?: string; modelId?: string } = {},
): Promise<void> {
  const prefs = usePreferencesStore()
  const { prompt } = metadata

  // 1. 自动复制提示词
  if (prefs.generation.auto_copy_prompt && prompt) {
    try {
      await navigator.clipboard.writeText(prompt)
    } catch (_) {
      // 静默失败（用户可能未授权剪贴板）
    }
  }

  // 2. 提示音
  if (prefs.notification.sound_on_complete) {
    playCompletionBeep()
  }

  // 3. 浏览器通知
  if (prefs.notification.browser_notification) {
    const label = fileType === 'image' ? '图片' : '视频'
    sendBrowserNotification(`Agnes - ${label}生成完成`, prompt ? `提示词：${prompt.slice(0, 50)}…` : `${label}已生成完毕`)
  }
}

/** 根据 classify_by 生成文件路径（含子目录）
 *  - classify_by = 'type'：按类型分子目录（images/ 或 videos/）
 *  - classify_by = 'date'：按日期分子目录（YYYY-MM-DD/）
 *  - classify_by = 'none'：不分子目录，直接放在根目录
 *  返回值："subdir/filename" 或 "filename"
 */
function buildFilePath(
  filename: string,
  fileType: 'image' | 'video',
  pattern: DownloadPreferences,
  metadata?: { modelId?: string },
): string {
  const now = new Date()
  const dateStr = now.toISOString().slice(0, 10) // YYYY-MM-DD

  // 生成子目录路径（none 时不创建子目录）
  let subDir = ''
  if (pattern.classify_by === 'type') {
    subDir = fileType === 'image' ? 'images' : 'videos'
  } else if (pattern.classify_by === 'date') {
    subDir = dateStr
  }
  // 'none' 或未设置：subDir 保持空，不做分类

  // 处理文件命名（支持 {type}/{date}/{time}/{seq}/{model}/{timestamp}/{uuid}）
  const timeStr = now.toTimeString().slice(0, 8).replace(/:/g, '') // HHMMSS
  let name = pattern.file_naming_pattern
    .replace('{type}', fileType)
    .replace('{date}', dateStr)
    .replace('{time}', timeStr)
    .replace('{seq}', crypto.randomUUID().slice(0, 8))
    .replace('{model}', metadata?.modelId || 'agnes')
    .replace('{timestamp}', now.toISOString().replace(/[:.]/g, '-'))
    .replace('{uuid}', crypto.randomUUID().slice(0, 8))

  // 确保有扩展名
  if (!name.includes('.')) {
    name += fileType === 'image' ? '.png' : '.mp4'
  }

  return subDir ? `${subDir}/${name}` : name
}

/**
 * 从远程 URL 获取 blob（通过后端代理，避免 CORS 问题）
 * @param url 资源 URL
 * @param fileType image / video
 * @param filename 自定义文件名
 * @returns Blob
 */
async function fetchBlobViaProxy(
  url: string,
  fileType: 'image' | 'video',
  filename: string,
): Promise<Blob> {
  const baseURL = import.meta.env.VITE_API_BASE_URL || ''
  const proxyUrl = `${baseURL}/api/download?url=${encodeURIComponent(url)}&type=${fileType}&filename=${encodeURIComponent(filename)}`

  let token: string | null = null
  try {
    token = localStorage.getItem('agnes.platform.auth.token')
  } catch (_) { /* ignore */ }

  const headers: Record<string, string> = {}
  if (token) headers.Authorization = `Bearer ${token}`

  const resp = await fetch(proxyUrl, { headers })
  if (!resp.ok) {
    let msg = `下载失败（HTTP ${resp.status}）`
    try {
      const data = await resp.json()
      if (data?.detail) msg = data.detail
    } catch (_) { /* 响应不是 JSON */ }
    throw new Error(msg)
  }
  return await resp.blob()
}

/**
 * 自动下载单个文件
 * - 有目录句柄：写入子目录（通过 File System Access API）
 * - 无目录句柄：回退到浏览器默认下载（文件名带分类前缀）
 */
async function triggerAutoDownload(
  url: string,
  fileType: 'image' | 'video',
  metadata: {
    modelId?: string
    mimeType?: string
    namingPattern?: DownloadPreferences
  } = {},
): Promise<void> {
  const prefs = usePreferencesStore()
  const pattern = metadata.namingPattern || prefs.download
  const path = buildFilePath('', fileType, pattern, { modelId: metadata.modelId })
  const flatFilename = path.replace(/\//g, '_')  // 浏览器下载时的扁平文件名

  try {
    // 先尝试恢复目录句柄（首次自动下载时触发）
    const handle = await getDirectoryHandle()

    // 获取文件内容
    const blob = await fetchBlobViaProxy(url, fileType, flatFilename)

    if (handle) {
      // ========== 通道 A：File System Access API，写入用户指定目录 + 子目录 ==========
      const parts = path.split('/')
      let dir = handle as FileSystemDirectoryHandle
      // 逐级创建子目录
      for (let i = 0; i < parts.length - 1; i++) {
        dir = await dir.getDirectoryHandle(parts[i], { create: true })
      }
      const fileName = parts[parts.length - 1]
      const fileHandle = await dir.getFileHandle(fileName, { create: true })
      // @ts-ignore - createWritable 是 File System Access API 方法，TS 类型定义可能缺失
      const writable = await fileHandle.createWritable()
      await writable.write(blob)
      await writable.close()
      console.info(`[AutoDownload] Saved to ${handle.name}/${path}`)
    } else {
      // ========== 通道 B：浏览器默认下载目录，文件名带分类前缀 ==========
      const blobUrl = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = blobUrl
      a.download = flatFilename
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(blobUrl)
      console.info(`[AutoDownload] Saved (browser default): ${flatFilename}`)
    }
  } catch (e: any) {
    console.error('[AutoDownload] failed:', e)
    ElMessage.warning(`自动下载失败：${e.message}，请手动点击下载`)
  }
}

export const usePreferencesStore = defineStore('preferences', () => {
  // ================ state ================
  const data = ref<UserPreferences | null>(null)
  const loading = ref(false)
  const initialized = ref(false)

  // ================ getters ================
  /** 完整偏好对象（未加载时返回 undefined） */
  const preferences = computed(() => data.value?.preferences)

  const generation = computed<GenerationPreferences>(
    () => preferences.value?.generation || {
      default_model_id: '',
      default_aspect_ratio: '1:1',
      auto_copy_prompt: true,
      default_image_count: 1,
    },
  )

  const download = computed<DownloadPreferences>(
    () => preferences.value?.download || {
      auto_download: false,
      download_directory: '',
      file_naming_pattern: '{type}_{timestamp}',
      classify_by: 'type',
      default_format: 'original',
    },
  )

  const ui = computed<UIPreferences>(
    () => preferences.value?.ui || {
      theme: 'dark',
      canvas_grid_visible: true,
      canvas_grid_size: 20,
      canvas_snap_to_grid: false,
    },
  )

  const notification = computed<NotificationPreferences>(
    () => preferences.value?.notification || {
      sound_on_complete: true,
      browser_notification: false,
    },
  )

  /** 是否开启自动下载 */
  const isAutoDownload = computed(() => download.value.auto_download)

  /** 是否已持有用户授权的下载目录（响应式） */
  const directoryHandleRef = ref<{ name: string } | null>(null)

  /** 是否已持有用户授权的下载目录 */
  const hasDirectoryHandle = computed(() => directoryHandleRef.value !== null)

  /** 当前下载目录名称 */
  const directoryName = computed(() => directoryHandleRef.value?.name || '')

  /** 从后端偏好读取的 download_directory（字符串形式，已选目录时与 directoryName 一致） */
  const downloadDirectory = computed(() => download.value.download_directory || '')

  // ================ actions ================

  /**
   * 同步响应式状态（每次目录句柄变化时调用）
   */
  function syncDirectoryHandleState() {
    if (_directoryHandle) {
      // @ts-ignore - name 属性在 FileSystemDirectoryHandle 上存在
      directoryHandleRef.value = { name: _directoryHandle.name }
    } else {
      directoryHandleRef.value = null
    }
  }

  /** 从后端拉取偏好（用户登录后自动调用），同时尝试恢复目录句柄 */
  async function fetchPreferences() {
    loading.value = true
    try {
      data.value = await getPreferences()
      initialized.value = true
    } catch (e) {
      console.warn('[Preferences] fetch failed:', e)
      initialized.value = true
    } finally {
      loading.value = false
    }
    // 从 IndexedDB 恢复目录句柄（不阻塞主流程）
    getDirectoryHandle().then(() => syncDirectoryHandleState())
  }

  /**
   * 部分更新偏好（深度合并）
   * @param patch 只传需要修改的字段，例如 { download: { auto_download: true } }
   */
  async function updatePreferences(patch: UserPreferencesUpdate) {
    const updated = await patchPreferences(patch)
    data.value = updated
  }

  /** 重置为默认偏好 */
  async function resetToDefault() {
    const updated = await resetPreferences()
    data.value = updated
    ElMessage.success('已恢复默认设置')
  }

  /**
   * 选择下载目录（调用 File System Access API）
   * 成功后会持久化到 IndexedDB，刷新页面后仍可使用
   * @returns 'ok' | 'security' | 'unsupported' | 'abort' | 'unknown'
   */
  async function pickDirectory(): Promise<'ok' | 'security' | 'unsupported' | 'abort' | 'unknown'> {
    const { handle, error } = await pickDownloadDirectory()
    if (handle) {
      syncDirectoryHandleState()
      // @ts-ignore - name 属性存在
      await updatePreferences({ download: { download_directory: handle.name } })
      return 'ok'
    }
    return error || 'unknown'
  }

  /**
   * 切换回浏览器默认下载：清除目录句柄
   */
  async function useBrowserDefaultDownload(): Promise<void> {
    await releaseDirectoryHandle()
    syncDirectoryHandleState()
    await updatePreferences({ download: { download_directory: '' } })
  }

  /** 释放已持有的下载目录句柄 */
  function clearDirectoryHandle() {
    releaseDirectoryHandle()
    syncDirectoryHandleState()
  }

  /**
   * 自动下载生成结果（图片或视频）
   * 若未开启 auto_download 则什么都不做
   *
   * @param url       资源的 CDN URL / data URI
   * @param fileType  image | video
   * @param metadata  可选元数据（modelId / mimeType）
   */
  async function autoDownload(
    url: string,
    fileType: 'image' | 'video',
    metadata: { modelId?: string; mimeType?: string } = {},
  ) {
    if (!isAutoDownload.value || !url) return
    await triggerAutoDownload(url, fileType, metadata)
  }

  return {
    // state
    data,
    loading,
    initialized,
    // getters
    preferences,
    generation,
    download,
    ui,
    notification,
    isAutoDownload,
    hasDirectoryHandle,
    directoryName,
    downloadDirectory,
    // actions
    fetchPreferences,
    updatePreferences,
    resetToDefault,
    pickDirectory,
    useBrowserDefaultDownload,
    clearDirectoryHandle,
    autoDownload,
    notifyComplete,
  }
})
