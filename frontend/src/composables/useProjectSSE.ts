// =====================================================
// 项目制创作 SSE 实时进度 Hook
//
// 功能:
//   1. 通过 EventSource 订阅项目级事件
//   2. 接收后端推送的实时进度（向导步骤 / 实体更新 / 生成进度 / 合成进度）
//   3. 自动重连（指数退避）
//   4. 轮询兜底（SSE 异常时通过 HTTP 获取项目状态）
//   5. 页面卸载时自动关闭连接
//   6. 暴露响应式状态供 UI 绑定
//   7. 401 未授权时对齐 client.ts 处理流程
// =====================================================

import { ref, onUnmounted, watch, computed, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { buildProjectSSEUrl, getProject } from '@/api/projects'
import { useUserStore } from '@/stores/user'
import type {
  ProjectEventType,
  ProjectStatus,
} from '@/types/project'

export type ConnectionStatus = 'idle' | 'connecting' | 'connected' | 'disconnected' | 'error'

export interface WizardStepState {
  step_key: string
  step_name?: string
  status: 'pending' | 'running' | 'completed' | 'failed'
  error?: string
  data?: Record<string, any>
}

export interface ProjectSSEState {
  /** 是否已连接 */
  connected: Ref<boolean>
  /** 连接状态 */
  connectionStatus: Ref<ConnectionStatus>
  /** 项目当前状态机 */
  projectStatus: Ref<ProjectStatus | null>
  /** 当前正在运行的向导步骤 key */
  currentWizardStep: Ref<string | null>
  /** 向导各步骤状态 */
  wizardSteps: Ref<Record<string, WizardStepState>>
  /** 最近一次实体更新事件（角色/场景/道具/分镜等） */
  lastEntityUpdate: Ref<Record<string, any> | null>
  /** 最近一次生成事件 */
  lastGenerationEvent: Ref<Record<string, any> | null>
  /** 最近一次合成进度 */
  mergeProgress: Ref<Record<string, any> | null>
  /** 项目错误信息 */
  projectError: Ref<string | null>
  /** 项目详情快照（轮询兜底时拉取） */
  projectSnapshot: Ref<any>
  /** Phase 2 — TTS 配音进度事件 */
  ttsProgress: Ref<Record<string, any> | null>
  /** Phase 2 — 字幕生成进度事件 */
  subtitleProgress: Ref<Record<string, any> | null>
  /** Phase 2 — 时间线片段变更事件 */
  timelineClipEvent: Ref<Record<string, any> | null>
  /** 主动关闭连接 */
  close: () => void
  /** 主动重连 */
  reconnect: () => void
  /** 立即拉取一次状态 */
  pollNow: () => Promise<void>
}

/**
 * 订阅项目级 SSE 事件
 *
 * @param projectId 响应式项目 ID（null 时不连接）
 */
export function useProjectSSE(projectId: Ref<number | string | null>): ProjectSSEState {
  // ================ 响应式状态 ================
  const connected = ref(false)
  const connectionStatus = ref<ConnectionStatus>('idle')
  const projectStatus = ref<ProjectStatus | null>(null)
  const currentWizardStep = ref<string | null>(null)
  const wizardSteps = ref<Record<string, WizardStepState>>({})
  const lastEntityUpdate = ref<Record<string, any> | null>(null)
  const lastGenerationEvent = ref<Record<string, any> | null>(null)
  const mergeProgress = ref<Record<string, any> | null>(null)
  const projectError = ref<string | null>(null)
  const projectSnapshot = ref<any>(null)
  // Phase 2 — TTS / 字幕 / 时间线 事件
  const ttsProgress = ref<Record<string, any> | null>(null)
  const subtitleProgress = ref<Record<string, any> | null>(null)
  const timelineClipEvent = ref<Record<string, any> | null>(null)

  // ================ 复用全局 store ================
  const userStore = useUserStore()
  const token = computed(() => userStore.token)

  // ================ SSE 内部状态 ================
  let eventSource: EventSource | null = null
  let reconnectTimer: number | null = null
  let pollTimer: number | null = null
  let reconnectAttempts = 0
  const MAX_RECONNECT_ATTEMPTS = 20
  const manualClosed = ref(false)

  /**
   * 401 处理：对齐 api/client.ts 行 56-76 的标准流程
   */
  function handleUnauthorized() {
    userStore.clearAll()
    if (typeof window !== 'undefined') {
      window.dispatchEvent(new CustomEvent('agnes:user-logout'))
      ElMessage.warning('登录已过期，请重新登录')
      if (!window.location.hash.startsWith('#/login')) {
        window.location.hash = '#/login'
      }
    }
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
  }

  /**
   * 通过 HTTP API 主动拉取项目详情（轮询兜底）
   */
  async function pollStatus() {
    const id = projectId.value
    if (!id) return
    try {
      const detail = await getProject(Number(id))
      projectSnapshot.value = detail
      // 仅在 SSE 没有更及时数据时使用轮询结果更新状态
      if (projectStatus.value === null) {
        projectStatus.value = detail.status
      }
    } catch (e: any) {
      if (e?.message !== 'unauthorized') {
        console.warn('[ProjectSSE] 轮询失败:', e)
      }
    }
  }

  function startPolling() {
    stopPolling()
    // 立即拉一次
    pollStatus()
    // 每 10 秒轮询一次作为备用
    pollTimer = window.setInterval(() => {
      pollStatus()
    }, 10000)
  }

  /**
   * 处理单个事件数据
   */
  function handleEvent(event: MessageEvent) {
    if (event.type === 'unauthorized') {
      manualClosed.value = true
      closeConnection()
      stopPolling()
      handleUnauthorized()
      return
    }

    let payload: any
    try {
      payload = JSON.parse(event.data)
    } catch (e) {
      console.error('[ProjectSSE] 事件解析失败:', e, event.data)
      return
    }

    try {
      switch (event.type as ProjectEventType) {
        case 'state_snapshot': {
          // 快照包含完整当前状态
          const snapshot = payload.data || payload
          if (snapshot.status) projectStatus.value = snapshot.status
          if (snapshot.current_step) currentWizardStep.value = snapshot.current_step
          if (snapshot.wizard_steps) {
            Object.entries(snapshot.wizard_steps).forEach(([key, state]: [string, any]) => {
              wizardSteps.value[key] = {
                step_key: key,
                step_name: state.name,
                status: state.status,
                error: state.error,
                data: state.data,
              }
            })
          }
          if (snapshot.error) projectError.value = snapshot.error
          break
        }

        case 'wizard_step_started': {
          const stepKey = payload.step_key || payload.data?.step_key
          currentWizardStep.value = stepKey
          if (stepKey) {
            wizardSteps.value[stepKey] = {
              step_key: stepKey,
              step_name: payload.step_name || payload.data?.step_name,
              status: 'running',
            }
          }
          break
        }

        case 'wizard_step_completed': {
          const stepKey = payload.step_key || payload.data?.step_key
          if (stepKey) {
            wizardSteps.value[stepKey] = {
              ...wizardSteps.value[stepKey],
              step_key: stepKey,
              status: 'completed',
              data: payload.data,
            }
          }
          break
        }

        case 'wizard_step_failed': {
          const stepKey = payload.step_key || payload.data?.step_key
          if (stepKey) {
            wizardSteps.value[stepKey] = {
              ...wizardSteps.value[stepKey],
              step_key: stepKey,
              status: 'failed',
              error: payload.error || payload.data?.error,
            }
          }
          projectError.value = payload.error || payload.data?.error || '向导步骤失败'
          break
        }

        case 'wizard_progress': {
          // 通用进度事件，直接记录在 lastGenerationEvent
          lastGenerationEvent.value = payload
          break
        }

        case 'entity_updated': {
          // 实体（角色/场景/道具/分镜）数据更新
          lastEntityUpdate.value = payload
          break
        }

        case 'generation_started':
        case 'generation_progress':
        case 'generation_completed':
        case 'generation_failed': {
          lastGenerationEvent.value = payload
          break
        }

        case 'active_version_changed': {
          // 活动版本变更：作为 entity_updated 的特化事件
          lastEntityUpdate.value = payload
          break
        }

        case 'project_status_changed': {
          const newStatus = payload.status || payload.data?.status
          if (newStatus) projectStatus.value = newStatus as ProjectStatus
          break
        }

        case 'merge_progress': {
          mergeProgress.value = payload
          break
        }

        case 'merge_completed': {
          mergeProgress.value = payload
          const newStatus = payload.status || payload.data?.status
          if (newStatus) projectStatus.value = newStatus as ProjectStatus
          // 合成完成后主动拉取最新详情
          pollStatus()
          break
        }

        // Phase 2 — TTS 配音进度
        case 'tts_progress':
        case 'tts_completed':
        case 'audio_activated': {
          ttsProgress.value = payload
          // TTS 完成 / 音频激活后视为实体更新，触发 UI 刷新
          lastEntityUpdate.value = payload
          break
        }

        // Phase 2 — 字幕生成进度
        case 'subtitle_progress':
        case 'subtitle_completed': {
          subtitleProgress.value = payload
          break
        }

        // Phase 2 — 时间线片段变更
        case 'timeline_clip_created':
        case 'timeline_clip_updated':
        case 'timeline_clip_deleted': {
          timelineClipEvent.value = payload
          break
        }
      }
    } catch (e) {
      console.error('[ProjectSSE] 事件处理失败:', e)
    }
  }

  /**
   * 建立 SSE 连接
   */
  function connect(id: number | string) {
    closeConnection()
    stopPolling()

    if (manualClosed.value) return

    connectionStatus.value = 'connecting'
    try {
      const url = buildProjectSSEUrl(Number(id), token.value)
      eventSource = new EventSource(url)

      // 监听所有已知事件类型
      const eventTypes: ProjectEventType[] = [
        'state_snapshot',
        'wizard_step_started',
        'wizard_step_completed',
        'wizard_step_failed',
        'wizard_progress',
        'entity_updated',
        'generation_started',
        'generation_progress',
        'generation_completed',
        'generation_failed',
        'active_version_changed',
        'project_status_changed',
        'merge_progress',
        'merge_completed',
        // Phase 2
        'tts_progress',
        'tts_completed',
        'subtitle_progress',
        'subtitle_completed',
        'audio_activated',
        'timeline_clip_created',
        'timeline_clip_updated',
        'timeline_clip_deleted',
        'unauthorized',
      ]

      eventTypes.forEach(type => {
        eventSource?.addEventListener(type, ((event: MessageEvent) => handleEvent(event)) as EventListener)
      })

      eventSource.onopen = () => {
        connected.value = true
        connectionStatus.value = 'connected'
        reconnectAttempts = 0
      }

      eventSource.onerror = () => {
        connected.value = false
        connectionStatus.value = 'disconnected'

        // 项目已结束时不重连
        const s = projectStatus.value
        if (s === 'completed' || s === 'archived') {
          closeConnection()
          stopPolling()
          return
        }

        // 自动重连（指数退避）
        if (reconnectAttempts < MAX_RECONNECT_ATTEMPTS && !manualClosed.value) {
          reconnectAttempts++
          const delay = Math.min(1000 * Math.pow(1.5, reconnectAttempts), 10000)
          reconnectTimer = window.setTimeout(() => {
            if (projectId.value && !manualClosed.value) {
              connect(projectId.value)
            }
          }, delay)
        } else {
          closeConnection()
          connectionStatus.value = 'error'
          ElMessage.error('项目 SSE 连接失败，已切换到轮询模式')
        }
      }

      // 启动轮询兜底
      startPolling()
    } catch (e) {
      console.error('[ProjectSSE] 连接创建失败:', e)
      connectionStatus.value = 'error'
      // SSE 创建失败，至少启动轮询
      startPolling()
    }
  }

  // 监听 projectId 变化，自动重连
  watch(
    () => projectId.value,
    (newId) => {
      manualClosed.value = false
      reconnectAttempts = 0
      projectError.value = null
      wizardSteps.value = {}
      currentWizardStep.value = null
      lastEntityUpdate.value = null
      lastGenerationEvent.value = null
      mergeProgress.value = null
      projectStatus.value = null
      if (newId) {
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
    projectStatus,
    currentWizardStep,
    wizardSteps,
    lastEntityUpdate,
    lastGenerationEvent,
    mergeProgress,
    projectError,
    projectSnapshot,
    // Phase 2
    ttsProgress,
    subtitleProgress,
    timelineClipEvent,
    close: () => { manualClosed.value = true; closeConnection(); stopPolling() },
    reconnect: () => {
      manualClosed.value = false
      reconnectAttempts = 0
      if (projectId.value) connect(projectId.value)
    },
    pollNow: pollStatus,
  }
}
