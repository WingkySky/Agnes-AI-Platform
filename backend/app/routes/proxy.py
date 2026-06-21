# =====================================================
# 图片代理路由
#
# GET /api/proxy/image?url=<远程图片 URL>
#   - 后端拉取远程图片并透传给前端，绕过浏览器同源策略（CORS）
#   - 用于无限画布的图片裁剪/旋转/拆分/放大等 canvas 像素操作
#   - 仅允许 http/https 协议，禁止内网地址（防 SSRF）
# =====================================================

import logging
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
import httpx

from app.services.agnes_client import agnes_client

logger = logging.getLogger("agnes_platform")
router = APIRouter(prefix="/proxy", tags=["图片代理"])

# 允许的图片 Content-Type 前缀
ALLOWED_CONTENT_TYPES = ("image/",)
# 最大响应体大小 20MB（防止下载超大文件）
MAX_PROXY_BYTES = 20 * 1024 * 1024


def _is_safe_url(url: str) -> bool:
    """校验 URL 是否安全：必须是 http/https，且不是内网地址（简单防 SSRF）"""
    try:
        parsed = urlparse(url)
    except Exception:
        return False
    if parsed.scheme not in ("http", "https"):
        return False
    if not parsed.hostname:
        return False
    # 禁止 localhost / 127.x / 10.x / 192.168.x / 169.254.x / ::1
    host = parsed.hostname.lower()
    if host in ("localhost",):
        return False
    if host.startswith(("127.", "10.", "192.168.", "169.254.")):
        return False
    if host in ("::1",):
        return False
    return True


@router.get("/image", summary="代理远程图片（绕过 CORS）")
async def proxy_image(
    url: str = Query(..., description="远程图片 URL"),
):
    """
    代理拉取远程图片并透传给前端。
    - 仅允许 http/https 协议，禁止内网地址（防 SSRF）
    - 仅允许 image/* Content-Type
    - 响应头带 Access-Control-Allow-Origin: * 让前端 canvas 可读取像素

    注意：此接口不要求登录。原因：
    1. <img src="/api/proxy/image?..."> 标签请求不会带 JWT Authorization 头
    2. 图片 URL 是用户自己生成的结果，URL 不可枚举（含随机哈希）
    3. 仅代理 image/* 类型，安全风险低
    """
    if not _is_safe_url(url):
        raise HTTPException(status_code=400, detail="不支持的 URL")

    # 复用全局 agnes_client 的 httpx.AsyncClient 连接池
    client = agnes_client.client  # httpx.AsyncClient（property，自动创建）

    try:
        # stream=True 流式拉取，避免大图占满内存
        async with client.stream("GET", url, timeout=30.0) as upstream:
            if upstream.status_code != 200:
                raise HTTPException(status_code=502, detail=f"远程图片拉取失败：HTTP {upstream.status_code}")

            content_type = upstream.headers.get("content-type", "").split(";")[0].strip()
            if not content_type.startswith(ALLOWED_CONTENT_TYPES):
                raise HTTPException(status_code=400, detail=f"非图片类型：{content_type}")

            # 流式透传，同时累计大小防止超大文件
            total = 0

            async def gen():
                nonlocal total
                async for chunk in upstream.aiter_raw():
                    total += len(chunk)
                    if total > MAX_PROXY_BYTES:
                        break
                    yield chunk

            return StreamingResponse(
                gen(),
                media_type=content_type or "image/octet-stream",
                headers={
                    "Access-Control-Allow-Origin": "*",
                    "Cache-Control": "public, max-age=3600",
                },
            )
    except httpx.HTTPError as e:
        logger.warning("[图片代理] 拉取失败 url=%s err=%s", url, e)
        raise HTTPException(status_code=502, detail=f"远程图片拉取失败：{e}")
