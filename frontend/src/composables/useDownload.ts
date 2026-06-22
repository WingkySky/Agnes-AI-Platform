/* =====================================================
 * 通用文件下载组合式函数
 * 通过后端代理下载文件到本地，携带 JWT 避免鉴权失败，
 * 用 fetch 获取二进制 + Content-Disposition 文件名，再用 <a download> 触发保存
 * ===================================================== */

/**
 * 通过后端代理下载文件到本地的通用组合式函数
 *
 * 解决的问题：
 * - <a> 标签原生导航请求不带 JWT，导致后端按匿名用户处理（查不到登录用户的记录）
 * - 后端返回 JSON 错误时，<a> 标签会把 JSON 错误体当文件下载
 * - 源站返回 HTML 错误页时，需要前端能感知错误并提示
 */
export function useDownload() {
  /**
   * 通过后端代理 URL 下载文件
   * @param proxyUrl 后端代理接口完整 URL（如 /api/history/{id}/download）
   * @param defaultFilename 取不到 Content-Disposition 时的默认文件名
   */
  async function downloadViaProxy(proxyUrl: string, defaultFilename: string): Promise<void> {
    // 从 localStorage 取 token（与 client.ts 拦截器回退逻辑一致）
    let token: string | null = null
    try {
      token = localStorage.getItem('agnes.platform.auth.token')
    } catch (_) { /* ignore */ }

    const headers: Record<string, string> = {}
    if (token) headers.Authorization = `Bearer ${token}`

    const resp = await fetch(proxyUrl, { headers })
    if (!resp.ok) {
      // 解析后端返回的 JSON 错误信息
      let msg = `下载失败（HTTP ${resp.status}）`
      try {
        const data = await resp.json()
        if (data?.detail) msg = data.detail
      } catch (_) { /* 响应不是 JSON，忽略 */ }
      throw new Error(msg)
    }

    const blob = await resp.blob()
    // 从 Content-Disposition 提取文件名，取不到则用默认名
    const cd = resp.headers.get('content-disposition') || ''
    let filename = defaultFilename
    const match = cd.match(/filename="?([^"]+)"?/)
    if (match) filename = match[1]

    const blobUrl = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = blobUrl
    a.download = filename
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(blobUrl)
  }

  return { downloadViaProxy }
}
