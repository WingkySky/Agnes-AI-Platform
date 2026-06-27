// =====================================================
// 流水线 SSE 实时进度 Hook
//
// 功能:
//   1. 通过 EventSource 建立 SSE 连接
//   2. 接收后端推送的实时进度事件
//   3. 自动重连（连接断开时）
//   4. 轮询兜底（SSE 异常时通过 HTTP 轮询获取状态）
//   5. 页面卸载时自动关闭连接
//   6. 暴露响应式状态供 UI 绑定
//   7. 同步更新 taskQueue 任务面板状态
//   8. 同步更新 pipelineStore 当前运行详情
//   9. 401 未授权时对齐 client.ts 处理流程
//
// 支持的事件类型:
//   - state_snapshot: 连接时快照（当前进度）
//   - pipeline_started: 流水线开始启动
//   - step_started: 步骤开始
//   - step_progress: 步骤进度
//   - step_completed: 步骤完成
//   - step_failed: 步骤失败
//   - pipeline_completed: 流水线结束
//   - unauthorized: 认证失效（后端推送，触发 401 处理）
// =====================================================

import { ref, onUnmounted, watch, computed, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { getPipelineRunDetail, getPipelineRunSteps, buildSSEUrl, type PipelineStep } from '@/api/pipeline'
import { useUserStore } from '@/stores/user'
import { useTaskQueueStore } from '@/stores/taskQueue'
import { usePipelineStore } from '@/stores/pipeline'
import { t } from '@/i18n'

export interface StepSSEState {
  status?: 'pending' | 'running' | 'success' | 'failed' | 'skipped'
  progress?: number
  output?: any
  error?: string
  output_summary?: string
  name?: string
  // 步骤内逐元素进度详情（来自后端 step_progress 事件的 data.progress 对象）
  // 后端 video_batch / image_batch 等步骤每 2 秒推送一次，包含 current/total/phase/phase_text
  progress_detail?: {
    current?: number       // 已完成元素数（如已生成视频数）
    total?: number         // 总元素数
    percent?: number       // 0~1 步骤内百分比
    phase?: string         // 阶段标识（creating / polling）
    phase_text?: string    // 阶段中文描述（如"创建视频任务中"）
    message?: string       // 兜底文案
  }
}

export type ConnectionStatus = 'idle' | 'connecting' | 'connected' | 'disconnected' | 'error'

export interface PipelineSSEState {
  connected: Ref<boolean>
  connectionStatus: Ref<ConnectionStatus>
  pipelineStatus: Ref<string>
  currentStep: Ref<string | null>
  stepStates: Ref<Record<string, StepSSEState>>
  pipelineError: Ref<string | null>
  outputSummary: Ref<any>
  stepsFromApi: Ref<PipelineStep[]>
}

/**
 * 使用 SSE 监听流水线进度。
 *
 * @param runId 响应式的流水线运行 ID
 * @returns 响应式 SSE 状态
 */
export function usePipelineSSE(runId: Ref<number | string | null>): PipelineSSEState {
  // ================ 响应式状态 ================
  const connected = ref(false)
  const connectionStatus = ref<ConnectionStatus>('idle')
  const pipelineStatus = ref('pending')
  const currentStep = ref<string | null>(null)
  const stepStates = ref<Record<string, StepSSEState>>({})
  const pipelineError = ref<string | null>(null)
  const outputSummary = ref<any>(null)
  const stepsFromApi = ref<PipelineStep[]>([])

  // ================ 复用全局 stores ================
  // 通过 userStore 获取 token（不再硬编码 localStorage 读取）
  const userStore = useUserStore()
  const token = computed(() => userStore.token)
  // 同步任务面板与当前运行详情
  const taskQueue = useTaskQueueStore()
  const pipelineStore = usePipelineStore()

  // ================ SSE 内部状态 ================
  let eventSource: EventSource | null = null
  let reconnectTimer: number | null = null
  let pollTimer: number | null = null
  let noEventTimer: number | null = null
  let reconnectAttempts = 0
  const MAX_RECONNECT_ATTEMPTS = 20
  // 修复拼写：原 manuallClosed → manualClosed
  const manualClosed = ref(false)
  let hasReceivedEvent = false
  // P1 修复：in-flight 锁 + 指数退避计数器
  let pollingInFlight = false
  let backoffCount = 0

  /**
   * 401 处理：对齐 api/client.ts 行 56-76 的标准流程
   * - 清空本地登录态
   * - 触发用户登出事件，让所有 store 清理各自状态
   * - 提示用户并跳转登录页
   */
  function handleUnauthorized() {
    userStore.clearAll()
    if (typeof window !== 'undefined') {
      window.dispatchEvent(new CustomEvent('agnes:user-logout'))
      ElMessage.warning(t('pipelineResult.sse.unauthorized'))
      if (!window.location.hash.startsWith('#/login')) {
        window.location.hash = '#/login'
      }
    }
  }

  /**
   * 构造 SSE 订阅 URL
   * 复用 api/pipeline.buildSSEUrl 生成路径，再拼接 baseURL 与 token query
   */
  function buildSSEUrlWithToken(id: number | string): string {
    const baseUrl: string = (import.meta as any).env?.VITE_API_BASE_URL || ''
    const path = buildSSEUrl(Number(id))
    const url = `${baseUrl}${path}`
    const tokenValue = token.value
    if (tokenValue) {
      return `${url}?token=${encodeURIComponent(tokenValue)}`
    }
    return url
  }

  function closeConnection() {
    if (reconnectTimer) {
      clearTimeout(reconnectTimer)
      reconnectTimer = null
    }
    if (eventSource) {
      eventSource.close()
      eventSource = null
    }
    connected.value = false
    if (connectionStatus.value !== 'idle') {
      connectionStatus.value = 'disconnected'
    }
  }

  function stopPolling() {
    if (pollTimer) {
      clearInterval(pollTimer)
      pollTimer = null
    }
    if (noEventTimer) {
      clearTimeout(noEventTimer)
      noEventTimer = null
    }
  }

  /**
   * 通过 HTTP API 主动拉取状态（轮询兜底）
   */
  async function pollStatus() {
    const id = runId.value
    if (!id) return
    // In-flight 锁：正在请求中时跳过本次调用
    if (pollingInFlight) return
    pollingInFlight = true
    try {
      const [runDetail, steps] = await Promise.all([
        getPipelineRunDetail(Number(id)),
        getPipelineRunSteps(Number(id)),
      ])
      stepsFromApi.value = steps

      // 更新状态（仅在 SSE 没有更及时数据时使用）
      if (!hasReceivedEvent || pipelineStatus.value === 'pending') {
        pipelineStatus.value = runDetail.status
        pipelineError.value = runDetail.error_message
        currentStep.value = runDetail.current_step
      }
      // 无论 SSE 状态如何，都用 API 返回的 output_data 兜底更新 stepStates
      // 场景：step_completed 事件丢失或 SSE 断连重连后，前端仍能从轮询中拿到产物数据
      steps.forEach(step => {
        const existing = stepStates.value[step.step_key]
        // 仅在 SSE 未推送过 output 时用 API 数据兜底
        // SSE 已推送 output 的情况下优先用 SSE 的实时数据
        if (!existing || !existing.output) {
          stepStates.value[step.step_key] = {
            ...existing,
            status: (existing?.status || step.status) as any,
            name: step.name,
            error: step.error_message || undefined,
            output: step.output_data,
          }
        }
      })
    } catch (e: any) {
      // 401 已由 client.ts 拦截器统一处理；其他错误仅记录
      if (e?.message !== 'unauthorized') {
        console.warn(t('pipelineResult.sse.pollFailed'), e)
      }
    } finally {
      pollingInFlight = false
    }
  }

  function startPolling() {
    stopPolling()
    // 重置退避计数器
    backoffCount = 0
    // 首次轮询使用指数退避（初始 2s）
    schedulePollWithBackoff()
    // 每 10 秒轮询一次作为备用（与 noEventTimer 互斥：有事件时只走 pollTimer）
    pollTimer = window.setInterval(() => {
      pollStatus()
    }, 10000)
  }

  /**
   * 指数退避: 2s → 4s → 8s → max 30s
   * noEventTimer 和 pollTimer 互斥：如果 pollTimer 已激活则跳过 noEventTimer
   */
  function schedulePollWithBackoff() {
    const delay = Math.min(2000 * Math.pow(2, backoffCount), 30000)
    backoffCount++
    noEventTimer = window.setTimeout(() => {
      pollStatus()
    }, delay)
  }

  /**
   * 同步更新 taskQueue 任务面板状态
   * 依据事件类型映射出 status / progress / currentStep / 元素级进度
   * 修复历史问题：原实现仅同步 percent，TaskCard 上的 completedSteps/totalSteps 永远 0
   */
  function syncTaskQueue(eventType: string, payload: any) {
    const id = runId.value
    if (id == null) return
    const numericId = Number(id)

    let status: string | undefined
    let progress: number | undefined
    let currentStepKey: string | undefined
    // 元素级进度（用于 TaskCard 展示"3/8"计数 + 阶段文案）
    let itemCurrent: number | undefined
    let itemTotal: number | undefined
    let phaseText: string | undefined

    switch (eventType) {
      case 'pipeline_started':
        status = 'running'
        progress = 0
        break
      case 'step_started':
        status = 'running'
        currentStepKey = payload?.step_key
        break
      case 'step_progress': {
        currentStepKey = payload?.step_key
        const p = payload?.data?.progress
        if (typeof p === 'number') {
          progress = p
        } else if (p && typeof p === 'object') {
          progress = p.percent ?? p.progress
          itemCurrent = p.current
          itemTotal = p.total
          phaseText = p.phase_text || p.message
        }
        break
      }
      case 'step_completed':
        currentStepKey = payload?.step_key
        // 步骤完成后清空元素级计数，避免下个步骤沿用旧值
        itemCurrent = undefined
        itemTotal = undefined
        phaseText = undefined
        break
      case 'step_failed':
        currentStepKey = payload?.step_key
        break
      case 'pipeline_completed':
        status = payload?.data?.status || 'success'
        progress = 100
        break
      case 'state_snapshot':
        status = payload?.data?.status || payload?.status
        currentStepKey = payload?.data?.current_step || payload?.current_step
        break
    }

    taskQueue.updatePipelineTask(numericId, {
      status: status as any,
      progress,
      currentStep: currentStepKey,
      // 元素级进度透传到 task.params，供 TaskCard 展示
      itemCurrent,
      itemTotal,
      phaseText,
    })
  }

  /**
   * 处理单个事件数据
   */
  function handleEvent(event: MessageEvent) {
    // unauthorized 事件：后端检测到认证失效时推送，触发 401 处理
    if (event.type === 'unauthorized') {
      manualClosed.value = true
      closeConnection()
      stopPolling()
      handleUnauthorized()
      return
    }

    hasReceivedEvent = true
    let payload: any
    try {
      payload = JSON.parse(event.data)
    } catch (e) {
      console.error(t('pipelineResult.sse.parseFailed'), e, event.data)
      return
    }

    // 同步任务面板状态
    syncTaskQueue(event.type, payload)
    // 同步当前运行详情（pipelineStore）
    pipelineStore.updateRunFromEvent(event.type, payload?.data ?? payload)

    try {
      switch (event.type) {
        case 'state_snapshot': {
          // 快照包含完整当前状态（数据在 payload.data 中）
          const snapshot = payload.data || payload
          if (snapshot.status) pipelineStatus.value = snapshot.status
          if (snapshot.current_step) currentStep.value = snapshot.current_step
          if (snapshot.steps) {
            Object.entries(snapshot.steps).forEach(([key, state]: [string, any]) => {
              // 快照中 progress 可能是数字也可能是对象，统一处理为 progress + progress_detail
              const snapProgress = state.progress
              const isObj = snapProgress && typeof snapProgress === 'object'
              const percentNum = isObj
                ? (snapProgress.percent ?? snapProgress.progress)
                : (typeof snapProgress === 'number' ? snapProgress : undefined)
              stepStates.value[key] = {
                ...stepStates.value[key],
                status: state.status,
                progress: percentNum,
                output_summary: state.output_summary,
                error: state.error,
                name: state.name,
                output: state.output,
                progress_detail: isObj
                  ? {
                      current: snapProgress.current,
                      total: snapProgress.total,
                      percent: percentNum,
                      phase: snapProgress.phase,
                      phase_text: snapProgress.phase_text,
                      message: snapProgress.message,
                    }
                  : stepStates.value[key]?.progress_detail,
              }
            })
          }
          if (snapshot.output_summary) outputSummary.value = snapshot.output_summary
          if (snapshot.error) pipelineError.value = snapshot.error
          if (snapshot.status === 'failed' && snapshot.error) {
            pipelineError.value = snapshot.error
          }
          break
        }

        case 'pipeline_started': {
          pipelineStatus.value = 'running'
          pipelineError.value = null
          // 如果事件中带了步骤列表，初始化步骤状态
          if (payload.data?.steps) {
            payload.data.steps.forEach((s: any) => {
              if (!stepStates.value[s.key]) {
                stepStates.value[s.key] = {
                  status: s.status || 'pending',
                  name: s.name,
                }
              }
            })
          }
          break
        }

        case 'step_started': {
          const stepKey = payload.step_key
          currentStep.value = stepKey
          stepStates.value[stepKey] = {
            ...stepStates.value[stepKey],
            status: 'running',
            name: payload.data?.name,
            error: undefined,
          }
          break
        }

        case 'step_progress': {
          const stepKey = payload.step_key
          const progressInfo = payload.data?.progress
          if (progressInfo && typeof progressInfo === 'object') {
            // 保留完整的 progress 对象（current/total/phase/phase_text），
            // 前端 PipelineProgress 据此展示"3/8 视频已生成"等元素级进度
            const percent = progressInfo.percent ?? progressInfo.progress
            stepStates.value[stepKey] = {
              ...stepStates.value[stepKey],
              status: 'running',
              progress: typeof percent === 'number' ? percent : stepStates.value[stepKey]?.progress,
              output_summary: progressInfo.message || progressInfo.status || progressInfo.phase_text,
              progress_detail: {
                current: progressInfo.current,
                total: progressInfo.total,
                percent: typeof percent === 'number' ? percent : undefined,
                phase: progressInfo.phase,
                phase_text: progressInfo.phase_text,
                message: progressInfo.message,
              },
            }
          } else if (typeof progressInfo === 'number') {
            stepStates.value[stepKey] = {
              ...stepStates.value[stepKey],
              status: 'running',
              progress: progressInfo,
            }
          }
          break
        }

        case 'step_completed': {
          const stepKey = payload.step_key
          stepStates.value[stepKey] = {
            ...stepStates.value[stepKey],
            status: 'success',
            progress: 100,
            output_summary: payload.data?.output_summary,
            output: payload.data?.output,
            // 完成后清除进度详情，避免遗留旧的元素计数
            progress_detail: undefined,
          }
          break
        }

        case 'step_failed': {
          const stepKey = payload.step_key
          stepStates.value[stepKey] = {
            ...stepStates.value[stepKey],
            status: 'failed',
            error: payload.data?.error || t('pipelineResult.sse.stepFailed'),
          }
          break
        }

        case 'step_skipped': {
          const stepKey = payload.step_key
          stepStates.value[stepKey] = {
            ...stepStates.value[stepKey],
            status: 'skipped',
            error: payload.data?.reason || t('pipelineResult.sse.stepSkipped'),
          }
          break
        }

        case 'pipeline_completed': {
          const finalStatus = payload.data?.status || 'success'
          pipelineStatus.value = finalStatus
          if (finalStatus === 'success') {
            outputSummary.value = payload.data?.output_summary || null
            pipelineError.value = null
          } else if (finalStatus === 'failed') {
            pipelineError.value = payload.data?.error || t('pipelineResult.sse.pipelineFailed')
          }
          // 结束后主动关闭连接
          manualClosed.value = true
          closeConnection()
          stopPolling()
          // 最后再拉取一次完整状态
          pollStatus()
          break
        }
      }
    } catch (e) {
      console.error(t('pipelineResult.sse.handleFailed'), e)
    }
  }

  /**
   * 建立 SSE 连接
   */
  function connect(id: number | string) {
    closeConnection()
    stopPolling()
    hasReceivedEvent = false

    if (manualClosed.value) return

    connectionStatus.value = 'connecting'
    try {
      const url = buildSSEUrlWithToken(id)
      eventSource = new EventSource(url)

      // 监听所有已知事件类型（含 unauthorized）
      const eventTypes = [
        'state_snapshot',
        'pipeline_started',
        'step_started',
        'step_progress',
        'step_completed',
        'step_failed',
        'pipeline_completed',
        'unauthorized',
      ]

      eventTypes.forEach(type => {
        eventSource?.addEventListener(type, handleEvent as any)
      })

      eventSource.onopen = () => {
        connected.value = true
        connectionStatus.value = 'connected'
        reconnectAttempts = 0
      }

      eventSource.onerror = () => {
        connected.value = false
        connectionStatus.value = 'disconnected'

        // 流水线已结束时不再重连
        if (pipelineStatus.value === 'success' || pipelineStatus.value === 'failed' || pipelineStatus.value === 'cancelled') {
          closeConnection()
          stopPolling()
          return
        }

        // 自动重连（指数退避）
        if (reconnectAttempts < MAX_RECONNECT_ATTEMPTS && !manualClosed.value) {
          reconnectAttempts++
          const delay = Math.min(1000 * Math.pow(1.5, reconnectAttempts), 10000)
          reconnectTimer = window.setTimeout(() => {
            if (runId.value && !manualClosed.value) {
              connect(runId.value)
            }
          }, delay)
        } else {
          closeConnection()
          connectionStatus.value = 'error'
          ElMessage.error(t('pipelineResult.sse.reconnectFailed'))
        }
      }

      // 启动轮询兜底
      startPolling()
    } catch (e) {
      console.error(t('pipelineResult.sse.connectFailed'), e)
      connectionStatus.value = 'error'
      // SSE 创建失败，至少启动轮询
      startPolling()
    }
  }

  // 监听 runId 变化，自动重连
  watch(
    () => runId.value,
    (newId) => {
      manualClosed.value = false
      reconnectAttempts = 0
      pipelineError.value = null
      outputSummary.value = null
      stepStates.value = {}
      stepsFromApi.value = []
      hasReceivedEvent = false
      if (newId) {
        pipelineStatus.value = 'pending'
        connect(newId)
      } else {
        closeConnection()
        stopPolling()
        connectionStatus.value = 'idle'
      }
    },
    { immediate: true }
  )

  onUnmounted(() => {
    manualClosed.value = true
    closeConnection()
    stopPolling()
  })

  return {
    connected,
    connectionStatus,
    pipelineStatus,
    currentStep,
    stepStates,
    pipelineError,
    outputSummary,
    stepsFromApi,
    close: () => { manualClosed.value = true; closeConnection(); stopPolling() },
    reconnect: () => { manualClosed.value = false; reconnectAttempts = 0; if (runId.value) connect(runId.value) },
    pollNow: pollStatus,
  }
}
