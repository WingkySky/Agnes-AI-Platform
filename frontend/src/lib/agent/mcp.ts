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
import type { McpAgentTool } from '@/api/mcp'

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

/** 拉取全部启用服务器的工具并转译为内核工具组（会话建立时调用；失败降级为空） */
export async function buildMcpTools(): Promise<HostTool[]> {
  try {
    const servers = await fetchMcpAgentTools()
    return servers.flatMap((s) => (s.tools ?? []).map((t) => toHostTool(s.server_id, s.server_name, t)))
  } catch {
    return []
  }
}
