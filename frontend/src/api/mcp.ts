/* =====================================================
 * MCP 服务器相关 API 封装
 * - 管理接口（管理员）：服务器 CRUD / 连接测试
 * - Agent 接口（登录用户）：工具清单聚合 / 工具调用 BFF
 * - env/headers 的值仅服务端持有，列表响应只回键名
 * ===================================================== */

import client from './client'

/** 服务器脱敏信息（env/headers 只回键名） */
export interface McpServerSafe {
  id: number
  name: string
  transport: 'stdio' | 'http'
  command: string | null
  args: string[]
  env_keys: Record<string, boolean>
  url: string | null
  header_keys: Record<string, boolean>
  enabled: boolean
  created_at: string | null
  updated_at: string | null
}

/** 创建/更新请求：env/headers 缺省=保留原值，传 {}=清空 */
export interface McpUpsertBody {
  name: string
  transport: 'stdio' | 'http'
  command?: string
  args?: string[]
  env?: Record<string, string>
  url?: string
  headers?: Record<string, string>
  enabled: boolean
}

/** 单个 MCP 工具定义（服务端转交的 JSON Schema） */
export interface McpAgentTool {
  name: string
  description: string
  input_schema: Record<string, unknown>
}

/** 按服务器聚合的工具清单（Agent 会话建立时拉取） */
export interface McpServerTools {
  server_id: number
  server_name: string
  tools: McpAgentTool[]
}

/** 工具调用结果（MCP content 文本块拼接） */
export interface McpCallResult {
  text: string
  is_error: boolean
}

export function listMcpServers(): Promise<McpServerSafe[]> {
  return client.get('/api/mcp/servers')
}

export function createMcpServer(body: McpUpsertBody): Promise<McpServerSafe> {
  return client.post('/api/mcp/servers', body)
}

export function updateMcpServer(id: number, body: McpUpsertBody): Promise<McpServerSafe> {
  return client.put(`/api/mcp/servers/${id}`, body)
}

export function deleteMcpServer(id: number): Promise<null> {
  return client.delete(`/api/mcp/servers/${id}`)
}

export function testMcpServer(id: number): Promise<{ name: string; transport: string; tools: McpAgentTool[] }> {
  return client.post(`/api/mcp/servers/${id}/test`)
}

export function fetchMcpAgentTools(): Promise<McpServerTools[]> {
  return client.get('/api/mcp/tools')
}

export function callMcpTool(serverId: number, tool: string, args?: Record<string, unknown>): Promise<McpCallResult> {
  return client.post('/api/mcp/call', { server_id: serverId, tool, arguments: args })
}

// ---------- 市场（发现与一键安装） ----------

/** 市场源（管理员自建：URL 指向 manifest JSON） */
export interface McpMarketSourceInfo {
  id: number
  name: string
  url: string
  enabled: boolean
  last_fetched_at: string | null
  item_count: number
}

/** 市场项密钥声明（安装弹窗按声明生成输入框） */
export interface McpSecretField {
  key: string
  description?: string
  required?: boolean
}

/** 市场项（官方 + 远程合并；command/args/url 为可编辑预填） */
export interface McpMarketItemInfo {
  slug: string
  name: string
  description: string
  category: string
  transport: 'stdio' | 'http'
  command: string | null
  args: string[]
  url: string | null
  env_fields: McpSecretField[]
  headers_fields: McpSecretField[]
  tools_preview: string[]
  source_type: 'official' | 'remote'
  installed: boolean
}

export function listMarketSources(): Promise<McpMarketSourceInfo[]> {
  return client.get('/api/mcp/market/sources')
}

export function createMarketSource(name: string, url: string): Promise<McpMarketSourceInfo> {
  return client.post('/api/mcp/market/sources', { name, url })
}

export function deleteMarketSource(id: number): Promise<null> {
  return client.delete(`/api/mcp/market/sources/${id}`)
}

export function refreshMarketSource(id: number): Promise<{ count: number }> {
  return client.post(`/api/mcp/market/sources/${id}/refresh`)
}

export function listMarketItems(q = ''): Promise<McpMarketItemInfo[]> {
  return client.get('/api/mcp/market/items', { params: q ? { q } : {} })
}

export interface McpMarketInstallBody {
  slug: string
  name?: string
  command?: string
  args?: string[]
  url?: string
  env?: Record<string, string>
  headers?: Record<string, string>
}

export function installMarketItem(body: McpMarketInstallBody): Promise<McpServerSafe> {
  return client.post('/api/mcp/market/install', body)
}
