/* =====================================================
 * 前端错误收集与上报
 * - 捕获：window error（含资源加载）/ unhandledrejection / console.error / axios 接口失败（api/client.ts 挂钩）
 * - 队列：满 BATCH_SIZE 条或每 10 秒批量上报；页面卸载时 sendBeacon 兜底
 * - 上报走原生 fetch（不经 axios），失败静默，绝不递归上报
 * - 单条 message / stack 截断；单会话上限 200 条，防错误风暴
 * ===================================================== */

const REPORT_URL = `${import.meta.env.VITE_API_BASE_URL || ''}/api/logs/frontend`
const BATCH_SIZE = 10
const FLUSH_INTERVAL_MS = 10_000
const MAX_SESSION_EVENTS = 200
const MAX_MESSAGE_LENGTH = 2048
const MAX_STACK_LENGTH = 8192

interface ReportEvent {
  message: string
  stack?: string
  level?: 'error' | 'warning'
  url?: string
  timestamp?: string
}

let queue: ReportEvent[] = []
let sessionCount = 0
let flushTimer: ReturnType<typeof setTimeout> | undefined
let installed = false

function truncate(value: string, max: number): string {
  return value.length > max ? value.slice(0, max) : value
}

function currentPageUrl(): string {
  return typeof window !== 'undefined' ? window.location.href : ''
}

/** 记录一条前端事件；超过会话上限后静默丢弃 */
export function reportEvent(event: ReportEvent): void {
  if (sessionCount >= MAX_SESSION_EVENTS) return
  sessionCount += 1
  queue.push({
    message: truncate(event.message, MAX_MESSAGE_LENGTH),
    stack: event.stack ? truncate(event.stack, MAX_STACK_LENGTH) : undefined,
    level: event.level ?? 'error',
    url: event.url ?? currentPageUrl(),
    timestamp: new Date().toISOString(),
  })
  if (queue.length >= BATCH_SIZE) {
    void flush(false)
  } else if (flushTimer === undefined) {
    flushTimer = setTimeout(() => {
      flushTimer = undefined
      void flush(false)
    }, FLUSH_INTERVAL_MS)
  }
}

async function flush(useBeacon: boolean): Promise<void> {
  if (queue.length === 0) return
  const events = queue
  queue = []
  const body = JSON.stringify({ events })
  // 页面卸载时 fetch 可能被浏览器取消，优先 sendBeacon
  if (useBeacon && typeof navigator !== 'undefined' && typeof navigator.sendBeacon === 'function') {
    if (navigator.sendBeacon(REPORT_URL, new Blob([body], { type: 'application/json' }))) return
  }
  try {
    await fetch(REPORT_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body,
      keepalive: true,
    })
  } catch (_) {
    /* 上报失败静默，不重试不递归 */
  }
}

/** 安装全局收集器（main.ts 调用一次；重复调用无副作用） */
export function installLogReporter(): void {
  if (installed || typeof window === 'undefined') return
  installed = true

  // 脚本错误与资源加载失败（script/img/link 的 error 事件不冒泡，靠捕获阶段 target 区分）
  window.addEventListener('error', (event) => {
    const target = event.target
    if (target instanceof HTMLScriptElement || target instanceof HTMLImageElement || target instanceof HTMLLinkElement) {
      const url = 'src' in target ? target.src : 'href' in target ? target.href : ''
      reportEvent({ message: `资源加载失败: ${url || event.message}` })
      return
    }
    reportEvent({
      message: event.message || '未知脚本错误',
      stack: event.error instanceof Error ? event.error.stack : undefined,
    })
  })

  // 未处理的 Promise 拒绝
  window.addEventListener('unhandledrejection', (event) => {
    const reason: unknown = event.reason
    if (reason instanceof Error) {
      reportEvent({ message: `未处理的 Promise 拒绝: ${reason.message}`, stack: reason.stack })
    } else {
      reportEvent({ message: `未处理的 Promise 拒绝: ${String(reason)}` })
    }
  })

  // console.error 包装：保留原控制台输出后再入队
  const originalConsoleError = console.error.bind(console)
  console.error = (...args: unknown[]) => {
    try {
      const errorArg = args.find((arg): arg is Error => arg instanceof Error)
      reportEvent({
        message: args
          .map((arg) => (typeof arg === 'string' ? arg : arg instanceof Error ? arg.message : String(arg)))
          .join(' '),
        stack: errorArg?.stack,
      })
    } catch (_) {
      /* ignore */
    }
    originalConsoleError(...args)
  }

  // 页面卸载兜底
  window.addEventListener('beforeunload', () => {
    void flush(true)
  })
}

/** 仅供测试：清空队列与计数（不影响已安装的监听器） */
export function __resetForTest(): void {
  queue = []
  sessionCount = 0
  if (flushTimer !== undefined) {
    clearTimeout(flushTimer)
    flushTimer = undefined
  }
}
