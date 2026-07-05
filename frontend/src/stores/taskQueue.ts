/* =====================================================
 * 全局 Task Queue Store（任务队列）
 * - 统一管理图片与视频的异步生成任务
 * - 按任务独立轮询状态
 * - localStorage 持久化（刷新页面后继续轮询）
 * - 页面可见性感知（后台降低轮询频率）
 * - 并发上限：每种类型最多 5 个同时生成
 * - 历史任务：最多保留 5 个已完成任务，20 分钟后清理
 * ===================================================== */

import { defineStore } from 'pinia'
import { useUserStore } from '@/stores/user'
import { usePreferencesStore } from '@/stores/preferences'
import {
  createVideoTask,
  getVideoStatus,
  cancelVideoTask,
} from '@/api/videos'
import {
  createImageTask,
  getImageTaskStatus,
  cancelImageTask,
} from '@/api/images'
import type {
  QueueTask,
  TaskType,
  TaskStatus,
  RegisterChatTaskParams,
  UpdateChatTaskParams,
  RegisterCanvasTaskParams,
  ImageTaskStatusResponse,
  VideoStatusResponse,
} from '@/types'

// ---------- 常量 ----------
const BASE_STORAGE_KEY = 'agnes_task_queue_v1'
/** 当前绑定的用户标识；空值为 "anon"（匿名） */
let _currentUserKey: string = 'anon'

/** 计算当前用户的存储 key */
function storageKey(): string {
  return `${BASE_STORAGE_KEY}_${_currentUserKey}`
}

/** 强制切换用户数据空间 */
function switchTaskUser(userId: number | string | null): void {
  _currentUserKey = userId ? 'u_' + String(userId) : 'anon'
}

const IMAGE_POLL_INTERVAL = 3000      // 图片轮询间隔（毫秒）
const VIDEO_POLL_INTERVAL = 5000      // 视频轮询间隔（毫秒）
const POLL_TIMEOUT = 10 * 60 * 1000  // 轮询超时保护（10 分钟）
const HISTORY_KEEP_COUNT = 5          // 已完成任务保留数量
const HISTORY_KEEP_MS = 20 * 60 * 1000  // 已完成任务保留时长（20 分钟）
const MAX_CONCURRENT = 5              // 每种类型最大并发数
const PROGRESS_DURATION_ESTIMATE = 60000  // 预估进度填充基准（毫秒）

// ---------- 自动重试常量 ----------
const RETRY_BASE_INTERVAL = 3000   // 重试基础间隔（3 秒）
const RETRY_MAX_ATTEMPTS = 3       // 最大重试次数（image/video 启用，其他类型为 0）

/**
 * 判断错误是否可自动重试
 * - 可重试：网络错误、超时、5xx 服务端错误、429 限流
 * - 不可重试：内容审核拒绝、400 参数错误、401/403 鉴权失败、其他 4xx
 *
 * @param error   错误对象（Error / AxiosError / { message, code, response }）
 * @param _taskType 任务类型（保留参数，便于未来按类型差异化策略）
 */
function isRetryableError(error: unknown, _taskType: TaskType): boolean {
  if (!error) return false

  // 兼容字符串错误（无 status / code，保守不重试）
  if (typeof error === 'string') {
    // 字符串中若含审核拒绝关键词，明确不可重试
    const lower = error.toLowerCase()
    if (MODERATION_KEYWORDS.some((kw) => lower.includes(kw.toLowerCase()))) return false
    return false
  }

  const err = error as {
    code?: string
    message?: string
    response?: { status?: number; data?: { detail?: string; message?: string } }
  }

  const code = err.code || ''
  const message = err.message || ''
  const status = err.response?.status
  const detail = err.response?.data?.detail || err.response?.data?.message || ''

  // 1. 内容审核拒绝：明确不可重试（message / detail 含审核关键词）
  const combinedMsg = `${message} ${detail}`.toLowerCase()
  if (MODERATION_KEYWORDS.some((kw) => combinedMsg.includes(kw.toLowerCase()))) {
    return false
  }

  // 2. 网络错误 / 超时 / 连接重置：可重试
  if (RETRYABLE_NETWORK_CODES.includes(code)) {
    return true
  }

  // 3. 5xx 服务端错误：可重试
  if (status && status >= 500 && status < 600) {
    return true
  }

  // 4. 429 限流：可重试
  if (status === 429) {
    return true
  }

  // 5. 400 / 401 / 403 / 其他 4xx：不可重试
  if (status && status >= 400 && status < 500) {
    return false
  }

  // 6. 未知错误（无 status、无 code）：保守不重试，避免无限循环
  return false
}

/** 可重试的网络错误码（axios / node http） */
const RETRYABLE_NETWORK_CODES = [
  'ERR_NETWORK',      // axios: 网络错误
  'ETIMEDOUT',        // 连接超时
  'ECONNABORTED',     // 请求被中断（含超时）
  'ECONNRESET',       // 连接被对端重置
  'ECONNREFUSED',     // 连接被拒绝
  'ENETUNREACH',      // 网络不可达
  'EHOSTUNREACH',     // 主机不可达
]

/** 内容审核拒绝关键词（小写匹配） */
const MODERATION_KEYWORDS = [
  'moderation',
  '审核',
  '违禁',
  '违规',
  'rejected',
  'inappropriate',
  '敏感词',
  'content policy',
  'safety',
]

// ---------- State 接口 ----------
interface TaskQueueState {
  // 所有任务（按 taskId 索引）
  tasks: Record<string, QueueTask>
  // 任务轮询定时器（taskId -> setInterval id）
  pollTimers: Record<string, ReturnType<typeof setInterval>>
  // 面板是否展开
  panelOpen: boolean
  // 当前选中的任务 ID（用于在视图中显示某任务的详情）
  activeTaskId: string | null
  // 时间戳标记（每秒递增，驱动耗时/时间显示的响应式刷新）
  _tick: number
  // 已初始化标志
  _initialized: boolean
  // 【历史刷新信号】—— 每当有任务（图片/视频）完成/取消/失败时递增
  // HistoryView 监听此信号，实现点击生成按钮后历史列表的自动刷新
  historyRefreshSignal: number
}

// ---------- 工具函数 ----------
function uid(): string {
  return 't_' + Date.now() + '_' + Math.random().toString(36).slice(2, 8)
}

function isFinalStatus(status: TaskStatus): boolean {
  return ['success', 'failed', 'cancelled'].includes(status)
}

export const useTaskQueueStore = defineStore('taskQueue', {
  state: (): TaskQueueState => ({
    // 所有任务（按 taskId 索引）
    tasks: {},
    // 任务轮询定时器（taskId -> setInterval id）
    pollTimers: {},
    // 面板是否展开
    panelOpen: false,
    // 当前选中的任务 ID（用于在视图中显示某任务的详情）
    activeTaskId: null,
    // 时间戳标记（每秒递增，驱动耗时/时间显示的响应式刷新）
    _tick: 0,
    // 已初始化标志
    _initialized: false,
    // 【历史刷新信号】—— 每当有任务（图片/视频）完成/取消/失败时递增
    // HistoryView 监听此信号，实现点击生成按钮后历史列表的自动刷新
    historyRefreshSignal: 0,
  }),

  getters: {
    // 所有任务列表（按创建时间倒序）
    taskList(state): QueueTask[] {
      return Object.values(state.tasks).sort(
        (a, b) => b.createdAt - a.createdAt,
      )
    },
    // 进行中的任务数
    runningCount(state): number {
      return Object.values(state.tasks).filter(
        (t) => !isFinalStatus(t.status),
      ).length
    },
    runningVideoCount(state): number {
      return Object.values(state.tasks).filter(
        (t) => t.type === 'video' && !isFinalStatus(t.status),
      ).length
    },
    runningImageCount(state): number {
      return Object.values(state.tasks).filter(
        (t) => t.type === 'image' && !isFinalStatus(t.status),
      ).length
    },
    videoTasks(): QueueTask[] {
      return this.taskList.filter((t) => t.type === 'video')
    },
    imageTasks(): QueueTask[] {
      return this.taskList.filter((t) => t.type === 'image')
    },
    getTaskById: (state) => (id: string): QueueTask | null => state.tasks[id] || null,
    activeTask(state): QueueTask | null {
      return state.activeTaskId ? state.tasks[state.activeTaskId] : null
    },
    // 根据任务 ID 计算已耗时（秒）— 通过 _tick 实现响应式刷新
    elapsedSec: (state) => (task: QueueTask | null): number => {
      // 读取 _tick 让此 getter 与它建立响应式关联
      state._tick
      if (!task) return 0
      return Math.floor((Date.now() - task.createdAt) / 1000)
    },
  },

  actions: {
    // =====================================================
    // 【初始化】—— 在应用启动时调用一次
    // =====================================================
    init(): void {
      if (this._initialized) return
      this._initialized = true

      // 1. 从 localStorage 恢复
      this._restoreFromStorage()

      // 2. 注册页面可见性监听
      if (typeof document !== 'undefined') {
        document.addEventListener('visibilitychange', () => {
          this._handleVisibilityChange()
        })
      }

      // 3. 启动所有未完成任务的轮询（跳过聊天/画布来源的任务，由各自 store 自己管理）
      for (const task of Object.values(this.tasks)) {
        if (!isFinalStatus(task.status) && task.source !== 'chat' && task.source !== 'canvas') {
          this._startPolling(task.taskId)
        }
      }

      // 4. 启动时清理一次历史
      this._cleanupOldHistory()

      // 5. 每分钟清理一次过期历史
      setInterval(() => this._cleanupOldHistory(), 60 * 1000)

      // 6. 每秒递增 tick，驱动耗时/时间显示的响应式刷新
      setInterval(() => { this._tick++ }, 1000)

      // 7. 监听用户登录/退出事件
      if (typeof window !== 'undefined') {
        window.addEventListener('agnes:user-login', (e: Event) => {
          const ce = e as CustomEvent
          const userId: number | null = (ce?.detail?.id as number) ?? null
          this._switchUserStorage(userId)
        })
        window.addEventListener('agnes:user-logout', () => {
          this._switchUserStorage(null)
        })
      }
    },

    // =====================================================
    // 【提交任务】
    // =====================================================

    // ------ 图片生成任务
    submitImageTask(params: Record<string, unknown>): string {
      if (this.runningImageCount >= MAX_CONCURRENT) {
        throw new Error(
          `Maximum ${MAX_CONCURRENT} concurrent image tasks — please wait for some tasks to complete`,
        )
      }
      const taskId = uid()
      const task: QueueTask = {
        taskId,
        type: 'image',
        status: 'queued',
        prompt: params.prompt as string || '',
        params: { ...params },
        resultUrl: null,
        posterUrl: null,
        progress: 0,
        errorMessage: '',
        createdAt: Date.now(),
        updatedAt: Date.now(),
        pollIntervalMs: IMAGE_POLL_INTERVAL,
        rawResponse: null,
        backendTaskId: null,
        // 自动重试：image 类型启用，最多 3 次
        retryCount: 0,
        maxRetries: RETRY_MAX_ATTEMPTS,
        retryScheduledAt: null,
      }
      this.tasks[taskId] = task
      // 自动选中为活跃任务（便于立即在预览区展示）
      this.setActiveTask(taskId)

      // 异步创建任务（不 await，立即返回 taskId）
      this._createImageTaskInBackground(taskId, params)
      return taskId
    },

    async _createImageTaskInBackground(taskId: string, params: Record<string, unknown>): Promise<void> {
      const task = this.tasks[taskId]
      if (!task) return
      try {
        task.status = 'pending'
        this._notifyTaskUpdate(taskId)
        const resp = await createImageTask(params as any)
        task.backendTaskId =
          (resp as any).task_id || (resp as any).id || (resp as any).image_task_id || taskId
        task.rawResponse = resp
        task.status = 'processing'
        this._notifyTaskUpdate(taskId)
        this._startPolling(taskId)
        // 【积分刷新】后端创建任务时已扣积分，立即刷新前端积分显示
        try {
          const userStore = useUserStore()
          if (userStore.isAuthenticated) userStore.fetchCredits()
        } catch (_) { /* 忽略 */ }
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : 'Failed to create task'
        // 【自动重试】检查是否可重试（autoRetry 开关 + 可重试错误 + 未达上限）
        if (this._scheduleRetry(taskId, err)) {
          // 已调度重试：保留错误信息供 UI 展示，status 暂保持为 'failed'，
          // TaskCard 通过 retryScheduledAt 字段判断显示"重试中 (n/3)"
          task.status = 'failed'
          task.errorMessage = message
          task.updatedAt = Date.now()
          this._notifyTaskUpdate(taskId)
          this._saveToStorage()
          return
        }
        task.status = 'failed'
        task.errorMessage = message
        task.updatedAt = Date.now()
        this._notifyTaskUpdate(taskId)
        this._saveToStorage()
      }
    },

    // ------ 视频生成任务
    submitVideoTask(params: Record<string, unknown>): string {
      if (this.runningVideoCount >= MAX_CONCURRENT) {
        throw new Error(
          `Maximum ${MAX_CONCURRENT} concurrent video tasks — please wait for some tasks to complete`,
        )
      }
      const taskId = uid()
      const task: QueueTask = {
        taskId,
        type: 'video',
        status: 'queued',
        prompt: params.prompt as string || '',
        params: { ...params },
        resultUrl: null,
        posterUrl: null,
        progress: 0,
        errorMessage: '',
        createdAt: Date.now(),
        updatedAt: Date.now(),
        pollIntervalMs: VIDEO_POLL_INTERVAL,
        rawResponse: null,
        backendTaskId: null,
        // 自动重试：video 类型启用，最多 3 次
        retryCount: 0,
        maxRetries: RETRY_MAX_ATTEMPTS,
        retryScheduledAt: null,
      }
      this.tasks[taskId] = task
      // 自动选中为活跃任务（便于立即在预览区展示）
      this.setActiveTask(taskId)

      this._createVideoTaskInBackground(taskId, params)
      return taskId
    },

    async _createVideoTaskInBackground(taskId: string, params: Record<string, unknown>): Promise<void> {
      const task = this.tasks[taskId]
      if (!task) return
      try {
        task.status = 'pending'
        this._notifyTaskUpdate(taskId)
        const resp = await createVideoTask(params as any)
        task.backendTaskId =
          (resp as any).task_id || (resp as any).video_id || (resp as any).id || taskId
        task.rawResponse = resp
        task.status = 'processing'
        this._notifyTaskUpdate(taskId)
        this._startPolling(taskId)
        // 【积分刷新】后端创建任务时已扣积分，立即刷新前端积分显示
        try {
          const userStore = useUserStore()
          if (userStore.isAuthenticated) userStore.fetchCredits()
        } catch (_) { /* 忽略 */ }
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : 'Failed to create task'
        // 【自动重试】检查是否可重试（autoRetry 开关 + 可重试错误 + 未达上限）
        if (this._scheduleRetry(taskId, err)) {
          task.status = 'failed'
          task.errorMessage = message
          task.updatedAt = Date.now()
          this._notifyTaskUpdate(taskId)
          this._saveToStorage()
          return
        }
        task.status = 'failed'
        task.errorMessage = message
        task.updatedAt = Date.now()
        this._notifyTaskUpdate(taskId)
        this._saveToStorage()
      }
    },

    // =====================================================
    // 【轮询】
    // =====================================================
    _startPolling(taskId: string): void {
      if (this.pollTimers[taskId]) return
      const task = this.tasks[taskId]
      if (!task) return
      const timerId = setInterval(() => {
        this._doPoll(taskId)
      }, task.pollIntervalMs)
      this.pollTimers[taskId] = timerId

      // 启动时立刻执行一次（提高响应速度）
      this._doPoll(taskId)
    },

    _stopPolling(taskId: string): void {
      const timer = this.pollTimers[taskId]
      if (timer) {
        clearInterval(timer)
        delete this.pollTimers[taskId]
      }
    },

    async _doPoll(taskId: string): Promise<void> {
      const task = this.tasks[taskId]
      if (!task) return
      // 已结束 → 停止
      if (isFinalStatus(task.status)) {
        this._stopPolling(taskId)
        return
      }
      // 超时保护
      if (Date.now() - task.createdAt > POLL_TIMEOUT) {
        this._markAsFailed(taskId, 'Task timeout (exceeded 10 minutes)')
        return
      }
      const backendId = task.backendTaskId || taskId
      try {
        let data: ImageTaskStatusResponse | VideoStatusResponse
        if (task.type === 'video') {
          data = await getVideoStatus(backendId) as VideoStatusResponse
        } else {
          data = await getImageTaskStatus(backendId) as ImageTaskStatusResponse
        }
        task.rawResponse = data
        task.updatedAt = Date.now()

        // 解析状态
        const rawStatus = String(
          data.status || 'processing',
        ).toLowerCase()
        const isSuccess = ['success', 'completed', 'done', 'succeeded', 'finished'].includes(rawStatus)
        const isFailed = ['failed', 'error', 'timeout'].includes(rawStatus)
        const isCancelled = rawStatus === 'cancelled'

        if (isSuccess) {
          task.status = 'success'
          // 提取结果 URL —— 兼容多种字段名
          const d = data as any
          const dData = d.data as Record<string, unknown> | undefined
          const url =
            (d.video_url as string) ||
            (d.url as string) ||
            (d.result_url as string) ||
            (d.image_url as string) ||
            (dData?.video_url as string) ||
            (dData?.url as string) ||
            (dData?.image_url as string) ||
            ''
          task.resultUrl = url
          task.progress = 100
          this._stopPolling(taskId)
          this._notifyTaskComplete(task)
          this._saveToStorage()
          // 【积分刷新】任务成功后刷新用户剩余积分
          try {
            const userStore = useUserStore()
            if (userStore.isAuthenticated) userStore.fetchCredits()
          } catch (_) {
            // 忽略刷新失败
          }
          // 【用户偏好】自动下载 + 完成通知（提示音 / 浏览器通知 / 自动复制提示词）
          try {
            const prefsStore = usePreferencesStore()
            if (url) {
              prefsStore.autoDownload(url, task.type === 'video' ? 'video' : 'image', { modelId: task.params?.model as string | undefined })
            }
            prefsStore.notifyComplete(task.type === 'video' ? 'video' : 'image', { prompt: task.prompt })
          } catch (_) {
            // 忽略偏好通知失败
          }
          // 【项目任务认领】source='project' 的任务完成后，调 claim 端点把结果写入项目实体
          if (task.source === 'project' && task.projectContext) {
            this._claimProjectResult(taskId).catch(() => {/* 忽略认领失败 */})
          }
        } else if (isCancelled) {
          task.status = 'cancelled'
          this._stopPolling(taskId)
          this._saveToStorage()
        } else if (isFailed) {
          // 后端返回失败状态，提取错误信息
          const failMsg = (data as any).message as string || (data as any).error as string || 'Generation failed'
          this._stopPolling(taskId)
          // 【自动重试】后端失败也尝试重试（如 5xx / 网络抖动导致后端任务失败）
          if (this._scheduleRetry(taskId, { message: failMsg })) {
            task.status = 'failed'
            task.errorMessage = failMsg
            task.updatedAt = Date.now()
            this._notifyTaskUpdate(taskId)
            this._saveToStorage()
            return
          }
          task.status = 'failed'
          task.errorMessage = failMsg
          this._saveToStorage()
        } else {
          task.status = 'processing'
          // 进度：优先取后端返回的 progress，否则按时间估算
          if (typeof data.progress === 'number') {
            task.progress = Math.min(data.progress, 99)
          } else if (data.progress != null && data.progress !== undefined) {
            const parsed = parseInt(String(data.progress), 10)
            task.progress = isNaN(parsed)
              ? this._estimateProgress(task)
              : Math.min(parsed, 99)
          } else {
            task.progress = this._estimateProgress(task)
          }
          this._saveToStorage()
        }
      } catch (err: unknown) {
        // 单次轮询失败，静默继续（不影响整体状态）
        const message = err instanceof Error ? err.message : String(err)
        console.warn('[TaskQueue] 轮询失败 taskId=', taskId, message)
      }
    },

    // 根据已耗时估算进度（后端不返回进度时的兜底方案）
    _estimateProgress(task: QueueTask): number {
      const elapsed = Date.now() - task.createdAt
      const expected = task.type === 'video' ? 3 * PROGRESS_DURATION_ESTIMATE : PROGRESS_DURATION_ESTIMATE
      return Math.min(Math.floor((elapsed / expected) * 100), 85)
    },

    // =====================================================
    // 【取消任务】
    // =====================================================
    async cancelTask(taskId: string): Promise<void> {
      const task = this.tasks[taskId]
      if (!task) return
      this._stopPolling(taskId)
      task.status = 'cancelled'
      task.updatedAt = Date.now()
      // 尝试通知后端（失败不影响前端状态）
      try {
        if (task.type === 'video' && task.backendTaskId) {
          await cancelVideoTask(task.backendTaskId)
        } else if (task.type === 'image' && task.backendTaskId) {
          await cancelImageTask(task.backendTaskId)
        }
      } catch (_) { /* 忽略后端取消失败 */ }
      // 【历史自动刷新】任务取消 → 触发刷新信号
      this.historyRefreshSignal++
      this._saveToStorage()
    },

    // =====================================================
    // 【移除任务】（仅移除 UI 显示，不影响历史记录）
    // =====================================================
    removeTask(taskId: string): void {
      this._stopPolling(taskId)
      if (this.activeTaskId === taskId) this.activeTaskId = null
      delete this.tasks[taskId]
      this._saveToStorage()
    },

    // =====================================================
    // 【用原参数重新提交】
    // =====================================================
    retryTask(taskId: string): string | null {
      const task = this.tasks[taskId]
      if (!task) return null
      if (task.type === 'video') {
        return this.submitVideoTask({ ...task.params })
      } else {
        return this.submitImageTask({ ...task.params })
      }
    },

    // =====================================================
    // 【聊天任务集成】— 供 chat store 调用，注册/更新聊天生成的媒体任务
    // =====================================================

    /** 注册聊天生成的媒体任务到队列（仅展示，不启动 taskQueue 自己的轮询） */
    registerChatTask({ taskId, type, prompt, resultUrl, backendTaskId }: RegisterChatTaskParams): void {
      if (!taskId) return
      // 避免重复注册
      if (this.tasks[taskId]) return

      const taskType: TaskType = type === 'video' ? 'video' : 'image'
      this.tasks[taskId] = {
        taskId,
        type: taskType,
        status: 'processing',
        prompt: prompt || '',
        params: {},
        resultUrl: resultUrl || null,
        posterUrl: null,
        progress: 0,
        errorMessage: '',
        createdAt: Date.now(),
        updatedAt: Date.now(),
        pollIntervalMs: taskType === 'video' ? VIDEO_POLL_INTERVAL : IMAGE_POLL_INTERVAL,
        rawResponse: null,
        backendTaskId: backendTaskId || taskId,
        // 标记来源为聊天 — taskQueue 恢复时跳过此类任务的轮询
        source: 'chat',
      }
      this._saveToStorage()
    },

    /** 更新聊天任务的状态（由 chat store 的媒体轮询回调） */
    updateChatTask(taskId: string, { status, resultUrl, progress }: UpdateChatTaskParams): void {
      const task = this.tasks[taskId]
      if (!task) return
      if (status) task.status = status
      if (resultUrl) task.resultUrl = resultUrl
      if (typeof progress === 'number') task.progress = progress
      task.updatedAt = Date.now()
      if (status === 'success') {
        task.progress = 100
        try { useUserStore().fetchCredits() } catch (_) { /* 忽略 */ }
        // 【用户偏好】自动下载 + 完成通知
        try {
          const prefsStore = usePreferencesStore()
          if (task.resultUrl) {
            prefsStore.autoDownload(task.resultUrl, task.type === 'video' ? 'video' : 'image', { modelId: task.params?.model as string | undefined })
          }
          prefsStore.notifyComplete(task.type === 'video' ? 'video' : 'image', { prompt: task.prompt })
        } catch (_) { /* 忽略 */ }
      }
      this._saveToStorage()
    },

    // =====================================================
    // 【画布任务集成】— 供画布调用，注册画布生成的媒体任务
    // =====================================================

    /** 注册画布生成的媒体任务到队列（仅展示，不启动 taskQueue 自己的轮询） */
    registerCanvasTask({ taskId, type, prompt, resultUrl, backendTaskId, panelId }: RegisterCanvasTaskParams): void {
      if (!taskId) return
      // 避免重复注册
      if (this.tasks[taskId]) return

      const taskType: TaskType = type === 'video' ? 'video' : 'image'
      this.tasks[taskId] = {
        taskId,
        type: taskType,
        status: 'processing',
        prompt: prompt || '',
        params: {},
        resultUrl: resultUrl || null,
        posterUrl: null,
        progress: 0,
        errorMessage: '',
        createdAt: Date.now(),
        updatedAt: Date.now(),
        pollIntervalMs: taskType === 'video' ? VIDEO_POLL_INTERVAL : IMAGE_POLL_INTERVAL,
        rawResponse: null,
        backendTaskId: backendTaskId || taskId,
        // 标记来源为画布 — taskQueue 恢复时跳过此类任务的轮询
        source: 'canvas',
        panelId: panelId || null,
      }
      this._saveToStorage()

      // 【积分刷新】画布任务创建时后端已预扣积分，立即刷新前端积分显示
      // 与常规 submitImageTask/submitVideoTask 保持一致（避免积分显示滞后，需刷新页面才更新）
      try {
        const userStore = useUserStore()
        if (userStore.isAuthenticated) userStore.fetchCredits()
      } catch (_) { /* 忽略 */ }
    },

    /** 更新画布任务的状态（由画布的轮询回调） */
    updateCanvasTask(taskId: string, { status, resultUrl, progress }: UpdateChatTaskParams): void {
      const task = this.tasks[taskId]
      if (!task) return
      if (status) task.status = status
      if (resultUrl) task.resultUrl = resultUrl
      if (typeof progress === 'number') task.progress = progress
      task.updatedAt = Date.now()
      if (status === 'success') {
        task.progress = 100
        try { useUserStore().fetchCredits() } catch (_) { /* 忽略 */ }
      }
      this._saveToStorage()
    },

    // =====================================================
    // 【项目任务集成】— 供 project store 调用
    // =====================================================

    /**
     * 注册项目生成任务到队列（复用 taskQueue 的轮询能力）。
     * 任务完成后自动调 claim 端点把结果写入项目实体。
     *
     * @param backendTaskId 后端返回的 task_id（image_poller / video_poller 的任务 ID）
     * @param params 任务参数
     * @param projectContext 项目上下文（含 claim 端点 URL）
     */
    registerProjectTask(
      backendTaskId: string,
      params: {
        type: 'image' | 'video'
        prompt?: string
        model?: string
      },
      projectContext: {
        projectId: number
        entityType?: 'character' | 'scene' | 'prop'
        entityId?: number
        shotId?: number
        claimUrl: string
      },
    ): string {
      const taskId = `project-${backendTaskId}`
      if (this.tasks[taskId]) return taskId

      this.tasks[taskId] = {
        taskId,
        type: params.type,
        status: 'processing',
        prompt: params.prompt || '',
        params: { ...params, model: params.model },
        resultUrl: null,
        posterUrl: null,
        progress: 0,
        errorMessage: '',
        createdAt: Date.now(),
        updatedAt: Date.now(),
        pollIntervalMs: params.type === 'video' ? VIDEO_POLL_INTERVAL : IMAGE_POLL_INTERVAL,
        rawResponse: null,
        backendTaskId,
        source: 'project',
        projectContext,
      }
      this._saveToStorage()
      this.setActiveTask(taskId)

      // 启动轮询（复用 taskQueue 的轮询机制，走 /api/images/tasks/{id} 或 /api/videos/{id}）
      this._startProjectPolling(taskId)

      // 积分刷新
      try {
        const userStore = useUserStore()
        if (userStore.isAuthenticated) userStore.fetchCredits()
      } catch (_) { /* 忽略 */ }

      return taskId
    },

    /**
     * 注册项目任务为 queued 状态（尚未拿到后端 task_id）。
     *
     * 用于批量提交场景：先在队列中占位显示 queued，让用户立即看到所有任务，
     * 后端按速率限制串行提交，拿到 backendTaskId 后再调
     * updateProjectTaskBackendId 切换为 processing 并启动轮询。
     *
     * @param params 任务参数
     * @param projectContext 项目上下文
     * @returns 临时 taskId（后续用它来更新 backendTaskId）
     */
    registerProjectTaskQueued(
      params: {
        type: 'image' | 'video'
        prompt?: string
        model?: string
      },
      projectContext: {
        projectId: number
        entityType?: 'character' | 'scene' | 'prop'
        entityId?: number
        shotId?: number
        claimUrl: string
      },
    ): string {
      // 临时 taskId 用 uuid，避免和真实 backendTaskId 冲突
      const taskId = `project-queued-${uid()}`
      this.tasks[taskId] = {
        taskId,
        type: params.type,
        status: 'queued',
        prompt: params.prompt || '',
        params: { ...params, model: params.model },
        resultUrl: null,
        posterUrl: null,
        progress: 0,
        errorMessage: '',
        createdAt: Date.now(),
        updatedAt: Date.now(),
        pollIntervalMs: params.type === 'video' ? VIDEO_POLL_INTERVAL : IMAGE_POLL_INTERVAL,
        rawResponse: null,
        backendTaskId: null,
        source: 'project',
        projectContext,
      }
      this._saveToStorage()
      this.setActiveTask(taskId)
      return taskId
    },

    /**
     * 更新项目任务的 backendTaskId，切换为 processing 并启动轮询。
     * 配合 registerProjectTaskQueued 使用：API 成功后调用。
     */
    updateProjectTaskBackendId(taskId: string, backendTaskId: string): void {
      const task = this.tasks[taskId]
      if (!task) return
      task.backendTaskId = backendTaskId
      task.status = 'processing'
      task.updatedAt = Date.now()
      this._notifyTaskUpdate(taskId)
      this._saveToStorage()
      // 启动轮询
      this._startProjectPolling(taskId)
      // 积分刷新
      try {
        const userStore = useUserStore()
        if (userStore.isAuthenticated) userStore.fetchCredits()
      } catch (_) { /* 忽略 */ }
    },

    /**
     * 标记项目任务为 failed（API 提交失败时使用）。
     */
    markProjectTaskFailed(taskId: string, errorMessage: string): void {
      const task = this.tasks[taskId]
      if (!task) return
      task.status = 'failed'
      task.errorMessage = errorMessage || '提交失败'
      task.updatedAt = Date.now()
      this._notifyTaskUpdate(taskId)
      this._saveToStorage()
      // 失败也刷新积分（后端可能已退积分）
      try {
        const userStore = useUserStore()
        if (userStore.isAuthenticated) userStore.fetchCredits()
      } catch (_) { /* 忽略 */ }
    },

    /**
     * 项目任务的轮询（走 /api/images/tasks/{id} 或 /api/videos/{id}）
     */
    _startProjectPolling(taskId: string): void {
      const task = this.tasks[taskId]
      if (!task) return

      const pollFn = async () => {
        if (!this.tasks[taskId]) return
        try {
          let data: any
          if (task.type === 'image') {
            data = await getImageTaskStatus(task.backendTaskId!)
          } else {
            data = await getVideoStatus(task.backendTaskId!)
          }
          // 复用现有的状态解析逻辑
          const rawStatus = String(data?.status || 'processing').toLowerCase()
          const isSuccess = ['success', 'completed', 'done', 'succeeded', 'finished'].includes(rawStatus)
          const isFailed = ['failed', 'error', 'timeout'].includes(rawStatus)

          if (isSuccess) {
            task.status = 'success'
            task.resultUrl = data?.result_url || data?.url || data?.video_url || data?.image_url || null
            task.progress = 100
            task.updatedAt = Date.now()
            this._stopPolling(taskId)
            this._notifyTaskComplete(task)
            this._saveToStorage()
            try { useUserStore().fetchCredits() } catch (_) {}
            // 认领结果到项目实体
            if (task.projectContext) {
              this._claimProjectResult(taskId).catch(() => {})
            }
          } else if (isFailed) {
            task.status = 'failed'
            task.errorMessage = data?.error_message || data?.message || '生成失败'
            task.updatedAt = Date.now()
            this._stopPolling(taskId)
            this._saveToStorage()
            try { useUserStore().fetchCredits() } catch (_) {}
          } else {
            // 处理中
            task.status = 'processing'
            task.progress = typeof data?.progress === 'number' ? data.progress : task.progress
            task.updatedAt = Date.now()
            this._notifyTaskUpdate(taskId)
          }
        } catch (err: any) {
          // 轮询失败，不中断，下次重试
          console.warn('[TaskQueue] 项目任务轮询失败:', taskId, err?.message)
        }
      }

      pollFn() // 立即执行一次
      this.pollTimers[taskId] = setInterval(pollFn, task.pollIntervalMs)
    },

    /**
     * 调用项目的 claim 端点，把生成结果认领到项目实体
     */
    async _claimProjectResult(taskId: string): Promise<void> {
      const task = this.tasks[taskId]
      if (!task?.projectContext) return

      const ctx = task.projectContext
      try {
        // claim 端点用 query 参数传 task_id
        const url = `${ctx.claimUrl}?task_id=${encodeURIComponent(task.backendTaskId || '')}`
        const resp = await (await import('@/api/client')).default.post(url)
        // 认领成功后，触发项目 store 刷新对应实体
        try {
          const { useProjectStore } = await import('@/stores/project')
          const projectStore = useProjectStore()
          if (ctx.entityType && ctx.entityId) {
            await projectStore.fetchEntities(ctx.entityType)
          } else if (ctx.shotId) {
            await projectStore.refreshShot(ctx.shotId)
          }
        } catch (_) { /* 忽略 store 刷新失败 */ }
        this.historyRefreshSignal++
      } catch (err: any) {
        console.warn('[TaskQueue] 项目认领失败:', taskId, err?.message)
      }
    },

    // =====================================================
    // 【面板/选中】
    // =====================================================
    setActiveTask(taskId: string): void {
      // 设置当前活跃任务（队列点击、提交任务后都会调用）
      this.activeTaskId = taskId
      // 持久化：刷新/切换页面后仍能记住选中的任务
      this._saveToStorage()
    },
    togglePanel(): void {
      this.panelOpen = !this.panelOpen
    },
    openPanel(): void {
      this.panelOpen = true
    },
    closePanel(): void {
      this.panelOpen = false
    },

    // =====================================================
    // 【内部工具】
    // =====================================================
    _markAsFailed(taskId: string, message: string): void {
      const task = this.tasks[taskId]
      if (!task) return
      this._stopPolling(taskId)
      task.status = 'failed'
      task.errorMessage = message
      task.updatedAt = Date.now()
      // 【历史自动刷新】任务失败 → 同样触发刷新信号
      this.historyRefreshSignal++
      this._saveToStorage()
    },

    // =====================================================
    // 【自动重试调度】—— 指数退避 3s → 9s → 27s，最多 3 次
    // =====================================================

    /**
     * 调度自动重试
     * 检查条件：autoRetry 开关 + 可重试错误 + retryCount < maxRetries
     * 满足则用 setTimeout 调度，并设置 retryScheduledAt 供 UI 展示与刷新恢复
     *
     * @returns true 表示已调度重试；false 表示不可重试，调用方应按最终失败处理
     */
    _scheduleRetry(taskId: string, error: unknown): boolean {
      const task = this.tasks[taskId]
      if (!task) return false

      // 1. 检查 autoRetry 开关（前端本地偏好）
      try {
        const prefsStore = usePreferencesStore()
        if (!prefsStore.autoRetry) return false
      } catch (_) {
        // preferences store 未初始化时保守不重试
        return false
      }

      // 2. 计算并缓存 maxRetries（image/video=3，其他类型=0）
      const maxRetries = task.maxRetries ??
        ((task.type === 'image' || task.type === 'video') ? RETRY_MAX_ATTEMPTS : 0)
      task.maxRetries = maxRetries
      if (maxRetries <= 0) return false

      // 3. 检查重试次数是否已达上限
      const currentRetry = task.retryCount ?? 0
      if (currentRetry >= maxRetries) return false

      // 4. 检查错误是否可重试
      if (!isRetryableError(error, task.type)) return false

      // 5. 计算指数退避间隔：3 * 3^currentRetry → 3s / 9s / 27s
      const delayMs = RETRY_BASE_INTERVAL * Math.pow(3, currentRetry)
      task.retryScheduledAt = Date.now() + delayMs
      task.updatedAt = Date.now()

      // 6. 调度重试执行
      setTimeout(() => {
        this._executeRetry(taskId)
      }, delayMs)

      return true
    },

    /**
     * 执行自动重试
     * - 递增 retryCount
     * - 清除 retryScheduledAt
     * - 重置任务状态为 queued，重新提交后端任务
     * - 重置 createdAt 避免 POLL_TIMEOUT 误杀重试任务
     */
    _executeRetry(taskId: string): void {
      const task = this.tasks[taskId]
      if (!task) return

      // 递增重试计数
      task.retryCount = (task.retryCount ?? 0) + 1
      task.retryScheduledAt = null

      // 重置任务状态，准备重新提交
      task.status = 'queued'
      task.errorMessage = ''
      task.progress = 0
      task.resultUrl = null
      task.posterUrl = null
      task.backendTaskId = null
      task.rawResponse = null
      // 重置 createdAt，避免轮询超时保护（POLL_TIMEOUT）误杀重试任务
      task.createdAt = Date.now()
      task.updatedAt = Date.now()

      this._notifyTaskUpdate(taskId)
      this._saveToStorage()

      // 根据任务类型重新提交后端任务
      if (task.type === 'video') {
        this._createVideoTaskInBackground(taskId, task.params)
      } else {
        this._createImageTaskInBackground(taskId, task.params)
      }
    },

    /**
     * 重置所有任务的 retryCount 与重试调度状态
     * - 由 preferences.setAutoRetry(false) 调用
     * - 清除所有任务的 retryCount / maxRetries / retryScheduledAt
     * - 已调度但未执行的 setTimeout 回调会被忽略（_executeRetry 内部检查 task.status）
     */
    resetAllRetryCounts(): void {
      for (const task of Object.values(this.tasks)) {
        task.retryCount = 0
        task.retryScheduledAt = null
      }
      this._saveToStorage()
    },

    _notifyTaskUpdate(_taskId: string): void {
      this._saveToStorage()
    },

    _notifyTaskComplete(_task: QueueTask): void {
      this._cleanupOldHistory()
      // 【历史自动刷新】任务完成 → 递增信号，通知 HistoryView 刷新列表
      this.historyRefreshSignal++
    },

    _handleVisibilityChange(): void {
      if (typeof document === 'undefined') return
      const hidden = document.hidden
      for (const task of Object.values(this.tasks)) {
        if (isFinalStatus(task.status)) continue
        this._stopPolling(task.taskId)
        if (hidden) {
          // 页面隐藏时使用更长间隔
          task.pollIntervalMs = task.type === 'video' ? 15000 : 10000
        } else {
          task.pollIntervalMs = task.type === 'video' ? VIDEO_POLL_INTERVAL : IMAGE_POLL_INTERVAL
        }
        this._startPolling(task.taskId)
      }
    },

    _cleanupOldHistory(): void {
      const done = Object.values(this.tasks)
        .filter((t) => isFinalStatus(t.status))
        .sort((a, b) => b.updatedAt - a.updatedAt)
      if (done.length <= HISTORY_KEEP_COUNT) {
        this._saveToStorage()
        return
      }
      const now = Date.now()
      // 超出保留数量的最旧任务，若已超过 20 分钟则清除
      const toRemove = done.slice(HISTORY_KEEP_COUNT)
      for (const task of toRemove) {
        if (now - task.updatedAt > HISTORY_KEEP_MS) {
          delete this.tasks[task.taskId]
        }
      }
      this._saveToStorage()
    },

    // =====================================================
    // 【持久化】
    // =====================================================
    _saveToStorage(): void {
      if (typeof localStorage === 'undefined') return
      try {
        const tasksToSave = Object.values(this.tasks).map((t) => ({
          taskId: t.taskId,
          type: t.type,
          status: t.status,
          prompt: t.prompt,
          params: t.params,
          resultUrl: t.resultUrl,
          posterUrl: t.posterUrl,
          progress: t.progress,
          errorMessage: t.errorMessage,
          createdAt: t.createdAt,
          updatedAt: t.updatedAt,
          pollIntervalMs: t.pollIntervalMs,
          backendTaskId: t.backendTaskId,
          source: t.source || null,
          panelId: t.panelId || null,
          // 自动重试相关字段（持久化以支持刷新页面后恢复重试状态）
          retryCount: t.retryCount ?? 0,
          maxRetries: t.maxRetries ?? 0,
          retryScheduledAt: t.retryScheduledAt ?? null,
        }))
        const data = {
          tasks: tasksToSave,
          // 持久化当前选中的任务 ID，刷新后可恢复选中状态
          activeTaskId: this.activeTaskId,
          savedAt: Date.now(),
        }
        localStorage.setItem(storageKey(), JSON.stringify(data))
      } catch (_) {
        // localStorage 写入失败（如隐私模式），静默忽略
      }
    },

    _restoreFromStorage(): void {
      if (typeof localStorage === 'undefined') return
      try {
        const raw = localStorage.getItem(storageKey())
        if (!raw) return
        const data = JSON.parse(raw) as { tasks: QueueTask[]; activeTaskId?: string }
        if (!data || !Array.isArray(data.tasks)) return
        const now = Date.now()
        for (const t of data.tasks) {
          // 超过 1 小时的任务丢弃
          if (now - (t.updatedAt || 0) > 60 * 60 * 1000) continue
          if (!isFinalStatus(t.status)) {
            // 进行中的任务重置为 processing，刷新后继续轮询
            t.status = 'processing'
          }
          this.tasks[t.taskId] = t

          // 【自动重试恢复】若任务处于失败且已调度重试，重新计算剩余等待时间并重新调度
          if (t.status === 'failed' && t.retryScheduledAt && (t.retryCount ?? 0) < (t.maxRetries ?? 0)) {
            const remainingMs = (t.retryScheduledAt as number) - now
            if (remainingMs > 0) {
              // 仍在等待重试窗口，重新设置 setTimeout
              setTimeout(() => this._executeRetry(t.taskId), remainingMs)
            } else {
              // 等待时间已过（刷新期间错过了重试时机），立即执行重试
              setTimeout(() => this._executeRetry(t.taskId), 0)
            }
          }
        }
        // 恢复 activeTaskId（如果该任务仍然存在）
        if (data.activeTaskId && this.tasks[data.activeTaskId]) {
          this.activeTaskId = data.activeTaskId
        }
      } catch (_) {
        // 解析失败不影响启动
      }
    },

    /**
     * 用户切换时切换任务队列数据空间
     * - 停止所有正在进行的轮询
     * - 清空当前任务
     * - 切换存储 key 并重载
     */
    _switchUserStorage(userId: number | string | null): void {
      // 停止所有轮询定时器
      for (const id of Object.keys(this.pollTimers)) {
        clearInterval(this.pollTimers[id])
      }
      this.pollTimers = {}
      this.tasks = {}
      this.activeTaskId = null
      switchTaskUser(userId)
      this._restoreFromStorage()
      // 用户切换后，重启对进行中任务的轮询
      for (const task of Object.values(this.tasks)) {
        if (!isFinalStatus(task.status) && task.source !== 'chat' && task.source !== 'canvas') {
          this._startPolling(task.taskId)
        }
      }
    },
  },
})
