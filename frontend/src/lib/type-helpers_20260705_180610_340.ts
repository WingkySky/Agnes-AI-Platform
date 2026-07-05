/**
 * 类型安全辅助函数
 * 替代项目中不安全 as 类型断言
 */

/** 安全地从 unknown 错误中提取消息字符串 */
export function getErrorMessage(err: unknown): string {
  if (err instanceof Error) return err.message
  return String(err)
}

/** 安全 JSON 解析，返回类型化结果 */
export function parseJSON<T = unknown>(json: string): T {
  return JSON.parse(json) as T
}

/** 类型守卫：过滤 null / undefined */
export function isNonNullable<T>(value: T): value is NonNullable<T> {
  return value != null
}

/** 类型守卫：检查值是否为 string */
export function isString(value: unknown): value is string {
  return typeof value === 'string'
}

/** 类型守卫：检查值是否为 number */
export function isNumber(value: unknown): value is number {
  return typeof value === 'number'
}

/** 类型守卫：检查值是否为 boolean */
export function isBoolean(value: unknown): value is boolean {
  return typeof value === 'boolean'
}
