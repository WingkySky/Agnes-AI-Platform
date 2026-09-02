/** 安全地从 unknown 错误中提取消息字符串 */
export function getErrorMessage(err: unknown): string {
  if (err instanceof Error) return err.message
  return String(err)
}
