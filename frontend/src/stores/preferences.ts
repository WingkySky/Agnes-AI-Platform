/* =====================================================
 * 用户偏好设置 Store
 *
 * 负责：
 *   - 从后端拉取/更新用户偏好设置
 *   - 本地缓存偏好（避免每次访问都请求后端）
 *   - 自动下载核心逻辑（检测 auto_download 并触发下载）
 *   - 生成文件命名（含分类目录支持）
 *   - File System Access API 支持（用户指定下载目录）
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

/** File System Access API 的目录句柄（用户授权后持有） */
let _directoryHandle: FileSystemDirectoryHandle | null = null

/**
 * 获取用户授权的下载目录句柄（File System Access API）
 * - 浏览器安全限制：不允许选择系统敏感目录（如 macOS 的 Downloads/Documents/Desktop 根目录）
 * - 返回 { handle, error } 让调用方区分失败原因
 */
async function pickDownloadDirectory(): Promise<{
  handle: FileSystemDirectoryHandle | null
  error?: 'security' | 'unsupported' | 'abort' | 'unknown'
}> {
  if (!('showDirectoryPicker' in window)) {
    return { handle: null, error: 'unsupported' }
  }
  try {
    const handle = await (window as any).showDirectoryPicker({ mode: 'readwrite' })
    _directoryHandle = handle
    return { handle }
  } catch (e: any) {
    if (e.name === 'AbortError') {
      return { handle: null, error: 'abort' }
    }
    // SecurityError / NotAllowedError：用户选了系统敏感目录
    if (e.name === 'SecurityError' || e.name === 'NotAllowedError') {
      console.warn('[Preferences] 目录被浏览器拒绝（可能是系统敏感目录）:', e)
      return { handle: null, error: 'security' }
    }
    console.warn('[Preferences] showDirectoryPicker failed:', e)
    return { handle: null, error: 'unknown' }
  }
}

/** 释放已持有的目录句柄 */
function releaseDirectoryHandle(): void {
  _directoryHandle = null
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

/** 根据 classify_by 生成文件路径（含子目录） */
function buildFilePath(
  filename: string,
  fileType: 'image' | 'video',
  pattern: DownloadPreferences,
  metadata?: { modelId?: string },
): string {
  const now = new Date()
  const dateStr = now.toISOString().slice(0, 10) // YYYY-MM-DD

  // 生成子目录路径
  let subDir = ''
  if (pattern.classify_by === 'type') {
    subDir = fileType === 'image' ? 'images' : 'videos'
  } else if (pattern.classify_by === 'date') {
    subDir = dateStr
  }

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

/** 自动下载单个文件（支持 File System Access API 指定目录） */
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
  const filename = buildFilePath('', fileType, pattern, { modelId: metadata.modelId })
  const mimeType = metadata.mimeType || (fileType === 'image' ? 'image/png' : 'video/mp4')

  try {
    const resp = await fetch(url)
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
    const blob = await resp.blob()

    if (_directoryHandle && 'getFileHandle' in _directoryHandle) {
      // File System Access API：写入用户指定目录（支持创建子目录）
      const pathParts = filename.split('/')
      let dir = _directoryHandle as FileSystemDirectoryHandle
      for (let i = 0; i < pathParts.length - 1; i++) {
        dir = await dir.getDirectoryHandle(pathParts[i], { create: true })
      }
      const fileHandle = await dir.getFileHandle(pathParts[pathParts.length - 1], { create: true })
      const writable = await fileHandle.createWritable()
      await writable.write(blob)
      await writable.close()
      console.info(`[AutoDownload] Saved to user directory: ${filename}`)
    } else {
      // 兜底：浏览器默认下载目录（文件名含子目录会被展平）
      const blobUrl = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = blobUrl
      a.download = filename.replace(/\//g, '_') // 子目录用下划线替代
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(blobUrl)
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

  /** 是否已持有用户授权的下载目录 */
  const hasDirectoryHandle = computed(() => _directoryHandle !== null)

  // ================ actions ================

  /** 从后端拉取偏好（用户登录后自动调用）*/
  async function fetchPreferences() {
    loading.value = true
    try {
      data.value = await getPreferences()
      initialized.value = true
    } catch (e) {
      console.warn('[Preferences] fetch failed:', e)
      // 拉取失败不阻塞，useDefault 兜底
      initialized.value = true
    } finally {
      loading.value = false
    }
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
   * @returns 'ok' | 'security' | 'unsupported' | 'abort' | 'unknown'
   */
  async function pickDirectory(): Promise<'ok' | 'security' | 'unsupported' | 'abort' | 'unknown'> {
    const { handle, error } = await pickDownloadDirectory()
    if (handle) {
      await updatePreferences({ download: { download_directory: handle.name } })
      return 'ok'
    }
    return error || 'unknown'
  }

  /**
   * 使用浏览器默认下载（不指定目录，用 <a download> 触发）
   * 适用于 File System Access API 不可用或用户不愿授权的场景
   */
  async function useBrowserDefaultDownload(): Promise<void> {
    _directoryHandle = null
    await updatePreferences({ download: { download_directory: '' } })
  }

  /** 释放已持有的下载目录 */
  function clearDirectoryHandle() {
    releaseDirectoryHandle()
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
