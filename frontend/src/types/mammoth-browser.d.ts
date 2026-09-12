/* =====================================================
 * mammoth 浏览器构建类型声明
 *
 * 主入口（lib/index）依赖 Node 内建模块，浏览器端走 mammoth.browser 子路径；
 * 包未提供该子路径类型，且 bundler 解析会命中真实 JS 文件（环境模块声明被遮蔽），
 * 故经 tsconfig paths 把类型映射到本文件，运行时仍由 Vite 解析 node_modules 真实 JS。
 * ===================================================== */

export interface MammothMessage {
  type: string
  message: string
}

export interface MammothRawTextResult {
  value: string
  messages: MammothMessage[]
}

export function extractRawText(input: { arrayBuffer: ArrayBuffer }): Promise<MammothRawTextResult>
