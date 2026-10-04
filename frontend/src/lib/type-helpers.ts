/** 安全地从 unknown 错误中提取消息字符串 */
export function getErrorMessage(err: unknown): string {
  if (err instanceof Error) return err.message
  return String(err)
}

/** 安全地提取归一化错误上的错误类目（api/client 拦截器从响应 body.category 附加） */
export function getErrorCategory(err: unknown): string {
  if (err instanceof Error) {
    const category = (err as Error & { category?: unknown }).category
    if (typeof category === 'string') return category
  }
  return ''
}
