/* =====================================================
 * Agent 反向控制桥 · 前端内核（Agent 一级公民批次 2）
 *
 * - startBridgeClient：页面侧执行者（画布/剪辑器页挂载）——WS 注册、心跳、
 *   断线重连、接收 relay_call 分发本地执行器并回执
 * - relayCall：调用侧——把工具调用 POST 给后端中继（在线→页面执行回执 /
 *   离线→routed:'offline' 由调用方走既有回退实现；超时→按 relay 失败返回，绝不自动重试）
 * - listBridgeTargets：当前用户在线执行目标（深度工具注入条件用）
 *
 * 白名单与后端 app/services/relay_service.py 的 BRIDGE_*_TOOLS 对齐（双侧维护）。
 * agent_delegate 不可跨页（执行体依赖内核对象），不在清单内。
 * ===================================================== */

import client from '@/api/client'
import type { AgentToolResult } from './tools'

export type BridgeHost = 'canvas' | 'editor'

export interface BridgeTarget {
  host: BridgeHost
  target_id: string
}

/** 桥白名单（与后端 BRIDGE_CANVAS_TOOLS 对齐） */
export const BRIDGE_CANVAS_TOOLS = [
  'agent_get_state',
  'agent_get_selection',
  'agent_get_models',
  'agent_read_image',
  'agent_apply_ops',
  'agent_create_text_node',
  'agent_select',
  'storyboard_set_style',
  'storyboard_list_styles',
  'storyboard_extract_entities',
  'storyboard_split',
  'agent_run_generation',
  'agent_stage_review',
] as const

/** 桥白名单（与后端 BRIDGE_EDITOR_TOOLS 对齐）：仅两个可见性敏感的写工具 */
export const BRIDGE_EDITOR_TOOLS = ['editor_apply_ops', 'editor_generate_subtitles'] as const

export type BridgeExecutor = (args: Record<string, unknown>) => Promise<AgentToolResult>

export type RelayCallOutcome =
  | { routed: 'relay'; result: AgentToolResult }
  | { routed: 'offline' }

/** 当前用户在线执行目标清单 */
export async function listBridgeTargets(): Promise<BridgeTarget[]> {
  const r = (await client.get('/api/agent/relay/targets')) as { targets?: BridgeTarget[] }
  return Array.isArray(r?.targets) ? r.targets : []
}

/** 中继一次工具调用；offline 语义由调用方决定回退（超时按 relay 失败返回，不回退防双执行） */
export async function relayCall(
  host: BridgeHost,
  targetId: string,
  tool: string,
  args: Record<string, unknown>,
): Promise<RelayCallOutcome> {
  let r: { routed?: string; result?: unknown } | null = null
  try {
    r = await client.post(
      '/api/agent/relay/call',
      { host, target_id: targetId, tool, args },
      { timeout: 0 },
    )
  } catch (e) {
    const status = (e as { response?: { status?: number } })?.response?.status
    if (status === 504) {
      return {
        routed: 'relay',
        result: { ok: false, error: '页面未在窗口内回执（操作可能已在执行，请勿原样重试）' },
      }
    }
    throw e
  }
  if (r?.routed === 'offline') return { routed: 'offline' }
  const result = r?.result
  if (result && typeof result === 'object' && typeof (result as AgentToolResult).ok === 'boolean') {
    return { routed: 'relay', result: result as AgentToolResult }
  }
  return { routed: 'relay', result: { ok: false, error: '桥回执格式异常' } }
}

export interface BridgeClientHandle {
  /** 停止客户端（页面卸载） */
  stop: () => void
  /** 目标 id 变化后重注册（画布切换工作区用） */
  refresh: () => void
}

export interface BridgeClientOptions {
  host: BridgeHost
  getTargetId: () => string
  /** 本页可执行的桥工具集（超出后端白名单的调用会被后端拒绝，这里兜底防御） */
  executors: Record<string, BridgeExecutor>
  /** 执行活动回调（批次 3 过程可视化）：真实分发给 executor 才触发（demoted/白名单兜底不触发）；
   *  并发由客户端内部计数，0→1 亮、1→0 灭，页面无需自己计数 */
  onActivity?: (active: boolean, tool: string, args: Record<string, unknown>) => void
}

/** 启动页面侧执行者：注册/心跳/断线重连/分发执行；返回 stop/refresh 句柄 */
export function startBridgeClient(opts: BridgeClientOptions): BridgeClientHandle {
  let ws: WebSocket | null = null
  let stopped = false
  let demoted = false
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null
  let heartbeatTimer: ReturnType<typeof setInterval> | null = null
  let backoffMs = 1000
  let registeredTarget = ''
  let activityDepth = 0

  function clearTimers(): void {
    if (heartbeatTimer) {
      clearInterval(heartbeatTimer)
      heartbeatTimer = null
    }
  }

  function send(payload: Record<string, unknown>): void {
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(payload))
  }

  function registerCurrent(): void {
    const targetId = opts.getTargetId()
    if (!targetId) return
    registeredTarget = targetId
    send({ type: 'register', host: opts.host, target_id: targetId })
  }

  function connect(): void {
    if (stopped) return
    const token = localStorage.getItem('agnes.platform.auth.token') || ''
    const proto = location.protocol === 'https:' ? 'wss' : 'ws'
    ws = new WebSocket(`${proto}://${location.host}/api/agent/relay/ws?token=${encodeURIComponent(token)}`)
    ws.onopen = () => {
      backoffMs = 1000
      demoted = false
      registerCurrent()
      // 心跳保活 + 目标 id 变化（画布切工作区）自动重注册
      heartbeatTimer = setInterval(() => {
        if (opts.getTargetId() !== registeredTarget) {
          registerCurrent()
          return
        }
        send({ type: 'ping' })
      }, 25000)
    }
    ws.onmessage = (ev: MessageEvent) => {
      let msg: { type?: string; call_id?: string; tool?: string; args?: Record<string, unknown> }
      try {
        msg = JSON.parse(ev.data)
      } catch {
        return
      }
      if (msg.type === 'relay_call' && msg.call_id && msg.tool) {
        void dispatch(msg.call_id, msg.tool, msg.args ?? {})
      } else if (msg.type === 'register_rejected') {
        console.warn('[bridge] register_rejected:', msg)
      } else if (msg.type === 'demoted') {
        // 被其他标签页顶替后静默失能（不自动抢回，避免双 tab 乒乓）；页面刷新/重连时重置
        demoted = true
      }
    }
    ws.onclose = () => {
      clearTimers()
      if (stopped) return
      // 断线自动重连（指数退避，封顶 15s）
      reconnectTimer = setTimeout(() => {
        backoffMs = Math.min(backoffMs * 2, 15000)
        connect()
      }, backoffMs)
    }
  }

  async function dispatch(callId: string, tool: string, args: Record<string, unknown>): Promise<void> {
    const executor = opts.executors[tool]
    let payload: AgentToolResult
    if (demoted) {
      payload = { ok: false, error: '本页执行者已被其他标签页顶替，请在目标标签页重试' }
    } else if (!executor) {
      payload = { ok: false, error: `工具 ${tool} 不在本页执行器清单内` }
    } else {
      activityDepth++
      if (activityDepth === 1) opts.onActivity?.(true, tool, args)
      try {
        payload = await executor(args)
      } catch (e) {
        payload = { ok: false, error: e instanceof Error ? e.message : String(e) }
      } finally {
        activityDepth = Math.max(0, activityDepth - 1)
        if (activityDepth === 0) opts.onActivity?.(false, '', {})
      }
    }
    send({ type: 'relay_result', call_id: callId, payload })
  }

  connect()

  return {
    stop: () => {
      stopped = true
      clearTimers()
      if (reconnectTimer) {
        clearTimeout(reconnectTimer)
        reconnectTimer = null
      }
      if (ws) {
        ws.close()
        ws = null
      }
    },
    refresh: () => {
      if (!stopped && ws && ws.readyState === WebSocket.OPEN) registerCurrent()
    },
  }
}
