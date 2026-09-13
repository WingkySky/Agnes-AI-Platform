/* =====================================================
 * 日志查询 API 封装（管理员，log:view 权限）
 * - queryLogs   : 查询日志（支持级别 / 关键词 / request_id / 时间 / before 翻页）
 * - getLogStats : 日志文件统计（文件名 + 大小，用于数据源下拉）
 * - clearLog    : 清空 / 删除日志文件（主文件清空并删备份，备份单删）
 * - 下载复用 useDownload.downloadViaProxy（/api/logs/download?file=…）
 * ===================================================== */

import client from './client'

export interface LogQueryParams {
  file?: string
  level?: string
  keyword?: string
  request_id?: string
  since?: string
  before?: string
  limit?: number
}

/** 单条日志：jsonl 结构化条目（后端 / 前端错误）或文本行（raw） */
export interface LogEntry {
  timestamp?: string
  level?: string
  request_id?: string
  module?: string
  func?: string
  lineno?: number
  message?: string
  exception?: string
  context?: Record<string, unknown>
  raw?: string
  [key: string]: unknown
}

export interface LogQueryResult {
  logs: LogEntry[]
  total: number
  file: string
}

export interface LogStats {
  exists: boolean
  files?: Record<string, { size_bytes?: number; size_mb?: number; line_count?: number; modified?: string }>
}

/** 查询日志（倒序，最新在前） */
export function queryLogs(params: LogQueryParams): Promise<LogQueryResult> {
  return client.get('/api/logs', { params })
}

/** 日志文件统计 */
export function getLogStats(): Promise<LogStats> {
  return client.get('/api/logs/stats')
}

/** 清空主日志文件（连同轮转备份）或删除单个备份文件 */
export function clearLog(file: string): Promise<{ cleared: string; removed: string[] }> {
  return client.delete('/api/logs', { params: { file } })
}
