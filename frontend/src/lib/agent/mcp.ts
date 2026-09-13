/* =====================================================
 * MCP 工具转译（外部 MCP 服务器 → 内核工具）
 *
 * - 命名约定 mcp__{serverId}__{tool}：数字 id 合法唯一，前缀同时是 policy
 *   的 'mcp' 组判定依据（纯命名约定，见 policy.ts）
 * - MCP inputSchema（JSON Schema）经 Type.Unsafe 直接作 parameters，
 *   机制层只做序列化透传，不做 TypeBox 重建
 * - 服务器故障降级：单服务器清单获取失败跳过，整体失败返回空，不阻塞会话
 * ===================================================== */

import { Type } from 'typebox'
import type { HostTool } from './kernel'
import { callMcpTool, fetchMcpAgentTools } from '@/api/mcp'
import type { McpAgentTool, McpServerTools } from '@/api/mcp'

export const MCP_TOOL_PREFIX = 'mcp__'

export function mcpToolName(serverId: number, tool: string): string {
  return `${MCP_TOOL_PREFIX}${serverId}__${tool}`
}

/** 单个 MCP 工具定义 → 内核 HostTool（execute 走后端 BFF） */
function toHostTool(serverId: number, serverName: string, def: McpAgentTool): HostTool {
  const schema = def.input_schema && typeof def.input_schema === 'object' ? def.input_schema : { type: 'object' }
  return {
    name: mcpToolName(serverId, def.name),
    description: `【MCP·${serverName}】${def.description || def.name}`,
    parameters: Type.Unsafe(schema),
    execute: async (args) => {
      try {
        return { ok: true, data: await callMcpTool(serverId, def.name, args) }
      } catch (e) {
        return { ok: false, error: e instanceof Error ? e.message : String(e) }
      }
    },
  }
}

/** 已接入能力（面板清单展示用，按服务器聚合） */
export interface McpCapability {
  name: string
  tools: string[]
}

/** 能力摘要（系统提示追加段）：按服务器列工具清单，提升模型对 mcp__ 工具的触发率 */
export function mcpCapabilitySummary(servers: McpServerTools[]): string {
  const lines = servers
    .filter((s) => (s.tools ?? []).length > 0)
    .map((s) => {
      const shown = s.tools.slice(0, 8).map((t) => t.name).join('、')
      const more = s.tools.length > 8 ? ` 等 ${s.tools.length} 个工具` : ''
      return `- ${s.server_name}（${shown}${more}）`
    })
  if (!lines.length) return ''
  return ['## 已接入的外部能力（MCP）', '', '当任务需要以下能力时，优先使用对应的 mcp__ 前缀工具：', ...lines].join('\n')
}

/** 拉取工具清单并转译：工具组 + 系统能力摘要一次取齐（失败降级为空，不阻塞会话） */
export async function fetchMcpBundle(): Promise<{ tools: HostTool[]; summary: string; capabilities: McpCapability[] }> {
  try {
    const servers = await fetchMcpAgentTools()
    const usable = servers.filter((s) => (s.tools ?? []).length > 0)
    return {
      tools: usable.flatMap((s) => s.tools.map((t) => toHostTool(s.server_id, s.server_name, t))),
      summary: mcpCapabilitySummary(usable),
      capabilities: usable.map((s) => ({ name: s.server_name, tools: s.tools.map((t) => t.name) })),
    }
  } catch {
    return { tools: [], summary: '', capabilities: [] }
  }
}

/** 拉取全部启用服务器的工具并转译为内核工具组（会话建立时调用；失败降级为空） */
export async function buildMcpTools(): Promise<HostTool[]> {
  return (await fetchMcpBundle()).tools
}
