# =====================================================
# MCP 服务器管理路由（CRUD/测试 → 管理员；工具调用 → 登录用户 BFF）
#
# GET    /api/mcp/servers                  服务器列表（脱敏）
# POST   /api/mcp/servers                  创建
# PUT    /api/mcp/servers/{server_id}      更新（env/headers 缺省=保留原值，传空=清空）
# DELETE /api/mcp/servers/{server_id}      删除
# POST   /api/mcp/servers/{server_id}/test 连接测试 + 工具清单
# POST   /api/mcp/call                     Agent 工具调用（登录用户）
# =====================================================

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_db
from app.core.response import ok
from app.core.security import get_current_admin_user, get_current_user
from app.models.mcp_server import McpServer
from app.models.user import User
from app.services import mcp_service

logger = logging.getLogger("agnes_platform")
router = APIRouter(prefix="/mcp", tags=["MCP 服务器"])


# ---------- 请求模型 ----------

class McpServerUpsert(BaseModel):
    """创建/更新请求：name/transport 必填；stdio 传 command+args+env，http 传 url+headers。
    env/headers 为 None（缺省）= 保留原值；{} = 清空。"""
    name: str
    transport: str
    command: str | None = None
    args: list[str] | None = None
    env: dict[str, str] | None = None
    url: str | None = None
    headers: dict[str, str] | None = None
    enabled: bool = True

    @field_validator("transport")
    @classmethod
    def _check_transport(cls, v: str) -> str:
        if v not in ("stdio", "http"):
            raise ValueError("transport 仅支持 stdio / http")
        return v

    @field_validator("name")
    @classmethod
    def _check_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("服务器名称不能为空")
        return v

    def transport_fields(self) -> dict:
        """按传输类型归并字段；env/headers 未传（None）时不产出键，更新路径自然保留原值"""
        if self.transport == "stdio":
            if not (self.command or "").strip():
                raise ValueError("stdio 传输必须填写启动命令")
            fields: dict = {
                "command": self.command.strip(),
                "args_json": mcp_service.dump_json(self.args, "[]"),
                "url": None,
                "headers_json": None,
            }
            if self.env is not None:
                fields["env_json"] = mcp_service.dump_json(self.env, "{}")
            return fields
        if not (self.url or "").strip():
            raise ValueError("http 传输必须填写服务器地址")
        fields = {
            "command": None,
            "args_json": None,
            "url": self.url.strip(),
        }
        if self.headers is not None:
            fields["headers_json"] = mcp_service.dump_json(self.headers, "{}")
        return fields


class McpToolCall(BaseModel):
    """Agent 工具调用请求（登录用户 BFF）"""
    server_id: int
    tool: str
    arguments: dict[str, Any] | None = None

    @field_validator("tool")
    @classmethod
    def _check_tool(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("工具名不能为空")
        return v


# ---------- 服务器管理（管理员） ----------

@router.get("/servers", summary="[管理员] MCP 服务器列表（脱敏）")
async def list_servers(
    db: AsyncSession = Depends(get_async_db),
    _admin: User = Depends(get_current_admin_user),
):
    servers = await mcp_service.list_servers(db)
    return ok([s.to_safe_dict() for s in servers])


@router.post("/servers", summary="[管理员] 创建 MCP 服务器")
async def create_server(
    body: McpServerUpsert,
    db: AsyncSession = Depends(get_async_db),
    _admin: User = Depends(get_current_admin_user),
):
    fields = {"name": body.name, "transport": body.transport, "enabled": body.enabled, **body.transport_fields()}
    try:
        server = await mcp_service.create_server(db, fields)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return ok(server.to_safe_dict(), "MCP 服务器已创建")


@router.put("/servers/{server_id}", summary="[管理员] 更新 MCP 服务器")
async def update_server(
    server_id: int,
    body: McpServerUpsert,
    db: AsyncSession = Depends(get_async_db),
    _admin: User = Depends(get_current_admin_user),
):
    server = await mcp_service.get_server(db, server_id)
    if not server:
        raise HTTPException(status_code=404, detail="MCP 服务器不存在")
    fields = {"name": body.name, "transport": body.transport, "enabled": body.enabled, **body.transport_fields()}
    if body.transport != server.transport:
        # 切换传输类型：两侧密钥全部重置，不保留旧侧密钥
        fields["env_json"] = None
        fields["headers_json"] = None
    try:
        server = await mcp_service.update_server(db, server, fields)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return ok(server.to_safe_dict(), "MCP 服务器已更新")


@router.delete("/servers/{server_id}", summary="[管理员] 删除 MCP 服务器")
async def delete_server(
    server_id: int,
    db: AsyncSession = Depends(get_async_db),
    _admin: User = Depends(get_current_admin_user),
):
    server = await mcp_service.get_server(db, server_id)
    if not server:
        raise HTTPException(status_code=404, detail="MCP 服务器不存在")
    await mcp_service.delete_server(db, server)
    return ok(None, "MCP 服务器已删除")


@router.post("/servers/{server_id}/test", summary="[管理员] 连接测试 + 工具清单")
async def test_server(
    server_id: int,
    db: AsyncSession = Depends(get_async_db),
    _admin: User = Depends(get_current_admin_user),
):
    server = await mcp_service.get_server(db, server_id)
    if not server:
        raise HTTPException(status_code=404, detail="MCP 服务器不存在")
    try:
        tools = await mcp_service.list_server_tools(server)
    except Exception as e:  # noqa: BLE001 —— 连接失败原样转可读错误
        raise HTTPException(status_code=502, detail=f"连接失败：{e}")
    return ok({"name": server.name, "transport": server.transport, "tools": tools})


# ---------- Agent 工具清单（登录用户） ----------

@router.get("/tools", summary="[登录用户] Agent 可用的 MCP 工具清单（按服务器聚合，带指纹缓存）")
async def agent_tools(
    db: AsyncSession = Depends(get_async_db),
    _user: User = Depends(get_current_user),
):
    return ok(await mcp_service.agent_tools(db))


# ---------- Agent 工具调用（登录用户 BFF） ----------

@router.post("/call", summary="[登录用户] 调用 MCP 工具")
async def call_tool(
    body: McpToolCall,
    db: AsyncSession = Depends(get_async_db),
    _user: User = Depends(get_current_user),
):
    server = await mcp_service.get_server(db, body.server_id)
    if not server or not server.enabled:
        raise HTTPException(status_code=404, detail="MCP 服务器不存在或已停用")
    try:
        result = await mcp_service.call_server_tool(server, body.tool, body.arguments)
    except Exception as e:  # noqa: BLE001 —— 调用失败转可读错误（连接/超时/工具错误）
        raise HTTPException(status_code=502, detail=f"MCP 工具调用失败：{e}")
    if result.get("is_error"):
        raise HTTPException(status_code=502, detail=f"MCP 工具返回错误：{result.get('text', '')}")
    return ok(result)
