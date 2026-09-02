/* =====================================================
 * blob — 二进制资源下载工具
 * 通过 axios 下载并转 blob URL，请求拦截器自动携带 JWT，
 * 解决 <img>/<video> 等标签的 src 无法携带 token 的问题
 * ===================================================== */

import client from '@/api/client'

/** 通过 axios 下载二进制资源并生成 blob URL（静默模式，失败时 reject 由调用方处理） */
export async function fetchBlobAsUrl(url: string): Promise<string> {
  const resp = await client.get<Blob>(url, { responseType: 'blob', silent: true })
  const blob = resp.data ?? resp
  return URL.createObjectURL(blob as Blob)
}
