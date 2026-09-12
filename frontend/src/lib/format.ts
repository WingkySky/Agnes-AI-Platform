/* =====================================================
 * format — 统一时间格式化
 * 空值兜底、支持 Date|string|number、输出本地时间字符串
 * ===================================================== */

export type FormatTimeMode = 'datetime' | 'datetime-padded' | 'date'

export interface FormatTimeOptions {
  /** 输出格式：datetime 本地格式（默认）/ datetime-padded YYYY-MM-DD HH:mm:ss / date YYYY-MM-DD */
  mode?: FormatTimeMode
  /** 空值（null / undefined / ''）兜底文案，默认 '-' */
  emptyText?: string
  /** 无法解析为日期时的兜底文案，默认原样返回输入值 */
  invalidText?: string
}

const pad = (n: number) => String(n).padStart(2, '0')

/** 统一时间格式化：空值兜底、支持 Date|string|number、输出本地时间字符串 */
export function formatTime(
  value: string | number | Date | null | undefined,
  options: FormatTimeOptions = {}
): string {
  const { mode = 'datetime', emptyText = '-', invalidText } = options
  if (value === null || value === undefined || value === '') return emptyText
  const d = new Date(value)
  if (isNaN(d.getTime())) return invalidText ?? String(value)
  if (mode === 'date') {
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
  }
  if (mode === 'datetime-padded') {
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
  }
  return d.toLocaleString()
}
