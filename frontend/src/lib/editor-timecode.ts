/* =====================================================
 * 时间码显示格式化（预览器/时间线共用）
 * - 秒 → "HH:MM:SS.mmm"（毫秒 3 位，等宽数字场景防抖动）
 * ===================================================== */

/** 秒 → "HH:MM:SS.mmm"（负值截 0；四舍五入到毫秒并正确进位） */
export function formatTimecode(seconds: number): string {
  const totalMs = Math.max(0, Math.round(seconds * 1000))
  const p2 = (n: number) => String(n).padStart(2, '0')
  return `${p2(Math.floor(totalMs / 3600000))}:${p2(Math.floor((totalMs % 3600000) / 60000))}:${p2(Math.floor((totalMs % 60000) / 1000))}.${String(totalMs % 1000).padStart(3, '0')}`
}
