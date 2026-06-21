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
const STORAGE_KEY = 'agnes_task_queue_v1'
const IMAGE_POLL_INTERVAL = 3000      // 图片轮询间隔（毫秒）
const VIDEO_POLL_INTERVAL = 5000      // 视频轮询间隔（毫秒）
const POLL_TIMEOUT = 10 * 60 * 1000  // 轮询超时保护（10 分钟）
const HISTORY_KEEP_COUNT = 5          // 已完成任务保留数量
const HISTORY_KEEP_MS = 20 * 60 * 1000  // 已完成任务保留时长（20 分钟）
const MAX_CONCURRENT = 5              // 每种类型最大并发数
const PROGRESS_DURATION_ESTIMATE = 60000  // 预估进度填充基准（毫秒）

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
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : 'Failed to create task'
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
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : 'Failed to create task'
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
        } else if (isCancelled) {
          task.status = 'cancelled'
          this._stopPolling(taskId)
          this._saveToStorage()
        } else if (isFailed) {
          task.status = 'failed'
          task.errorMessage = (data as any).message as string || (data as any).error as string || 'Generation failed'
          this._stopPolling(taskId)
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
        }))
        const data = {
          tasks: tasksToSave,
          // 持久化当前选中的任务 ID，刷新后可恢复选中状态
          activeTaskId: this.activeTaskId,
          savedAt: Date.now(),
        }
        localStorage.setItem(STORAGE_KEY, JSON.stringify(data))
      } catch (_) {
        // localStorage 写入失败（如隐私模式），静默忽略
      }
    },

    _restoreFromStorage(): void {
      if (typeof localStorage === 'undefined') return
      try {
        const raw = localStorage.getItem(STORAGE_KEY)
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
        }
        // 恢复 activeTaskId（如果该任务仍然存在）
        if (data.activeTaskId && this.tasks[data.activeTaskId]) {
          this.activeTaskId = data.activeTaskId
        }
      } catch (_) {
        // 解析失败不影响启动
      }
    },
  },
})
