# =====================================================
# MCP Server 端点装配 —— streamable HTTP 挂载到主应用 /mcp
#
# - PAT 鉴权在 ASGI 包裹层：Bearer agn_pat_* → mcp_gateway.authenticate_pat，
#   通过后写入 ContextVar（工具内读取）；无效/已吊销 401
# - stateless + json_response：每次 POST 独立处理（CLI 场景无需会话保持，
#   也保证 ContextVar 随请求任务传播，工具能读到本请求身份）
# - 挂载子应用的 lifespan 不被 FastAPI 传播：session manager 由主应用
#   lifespan 通过 mcp_session_manager 启停（必须在 streamable_http_app() 之后取）
# - DNS rebinding 防护面向浏览器 CSRF 场景，本端点 Bearer PAT 鉴权且供 CLI 使用，显式关闭
# =====================================================

from starlette.requests import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings

from app.services import mcp_gateway

mcp_server = MCPServer(
    name="agnes-platform",
    version="1.0.0",
    instructions=(
        "Agnes AI Platform 创作平台的 MCP 接入。当前提供画布工具（canvas_list / canvas_create / "
        "canvas_get_overview / canvas_apply_ops），用于建画布、落节点、连线与读概要；"
        "编辑器与生成类工具随后续版本扩展。写操作需要 full 档令牌。"
    ),
)

mcp_gateway.register_tools(mcp_server)

# 对外路径：主应用以 Mount("/", 子应用) 兜底挂在路由表末尾，此路径由子应用承接
MCP_HTTP_PATH = "/mcp"


class PatAuthMiddleware:
    """PAT 鉴权 ASGI 包裹层：Bearer token 校验 + 请求身份注入 ContextVar

    非 MCP 路径的请求原样放行（根挂载会兜到其它未匹配路径，需保持主应用 404 语义）
    """

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("path") != MCP_HTTP_PATH:
            await self.app(scope, receive, send)
            return
        auth = Headers(scope=scope).get("Authorization", "")
        token = auth[len("Bearer "):] if auth.startswith("Bearer ") else ""
        principal = await mcp_gateway.authenticate_request(token)
        if principal is None:
            resp = JSONResponse(
                {"detail": "无效或已吊销的访问令牌"},
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            )
            await resp(scope, receive, send)
            return
        mcp_gateway.pat_principal.set(principal)
        await self.app(scope, receive, send)


mcp_asgi_app = PatAuthMiddleware(
    mcp_server.streamable_http_app(
        streamable_http_path=MCP_HTTP_PATH,
        json_response=True,
        stateless_http=True,
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )
)

mcp_session_manager = mcp_server.session_manager
