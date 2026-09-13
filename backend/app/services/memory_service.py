# =====================================================
# 用户记忆库服务（单一记忆库方案）
#
# - 创作偏好 = 用户 MCP 记忆图谱里的「创作偏好」实体的 observations（格式"类别：内容"）
# - 不建新存储：读写都走 mcp_service 网关，连官方 memory 服务器（per_user 隔离）
# - 定位服务器：启用且 market_slug='official-memory'（市场安装的唯一标识）
# =====================================================

import json
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.mcp_server import McpServer
from app.services import mcp_service

logger = logging.getLogger("agnes_platform")

MEMORY_SERVER_SLUG = "official-memory"
PREFERENCE_ENTITY = "创作偏好"


async def find_memory_server(db: AsyncSession) -> McpServer | None:
    row = await db.execute(
        select(McpServer).where(McpServer.enabled == True, McpServer.market_slug == MEMORY_SERVER_SLUG)  # noqa: E712
    )
    return row.scalar()


def _extract_preferences(graph_text: str) -> list[str]:
    """从 read_graph 结果文本里抽「创作偏好」实体的 observations（守卫式解析）"""
    try:
        graph = json.loads(graph_text)
    except ValueError:
        return []
    if not isinstance(graph, dict):
        return []
    for entity in graph.get("entities") or []:
        if isinstance(entity, dict) and entity.get("name") == PREFERENCE_ENTITY:
            return [str(o) for o in (entity.get("observations") or []) if o]
    return []


async def read_preferences(db: AsyncSession, user_id: int) -> dict:
    """用户偏好摘要（未安装记忆服务器时 available=False，前端静默降级）"""
    server = await find_memory_server(db)
    if not server:
        return {"available": False, "preferences": []}
    try:
        result = await mcp_service.call_server_tool(server, "read_graph", {}, user_id=user_id)
    except Exception as e:  # noqa: BLE001 —— 记忆服务器故障不阻断会话建立
        logger.warning("读取用户记忆失败：%s", e)
        return {"available": False, "preferences": []}
    return {"available": True, "preferences": _extract_preferences(result.get("text", ""))}


async def delete_preference(db: AsyncSession, user_id: int, observation: str) -> bool:
    """删除单条偏好（delete_observations）"""
    server = await find_memory_server(db)
    if not server:
        return False
    await mcp_service.call_server_tool(
        server,
        "delete_observations",
        {"observations": [{"entityName": PREFERENCE_ENTITY, "observations": [observation]}]},
        user_id=user_id,
    )
    return True


async def clear_preferences(db: AsyncSession, user_id: int) -> bool:
    """清空偏好实体（保留图谱里其他记忆）"""
    server = await find_memory_server(db)
    if not server:
        return False
    await mcp_service.call_server_tool(server, "delete_entities", {"entityNames": [PREFERENCE_ENTITY]}, user_id=user_id)
    return True
