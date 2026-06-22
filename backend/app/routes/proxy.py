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

import httpx
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

logger = logging.getLogger("agnes_platform")
router = APIRouter(prefix="/proxy", tags=["图片代理"])

# 允许的图片 Content-Type 前缀
ALLOWED_CONTENT_TYPES = ("image/",)
# 最大响应体大小 20MB（防止下载超大文件）
MAX_PROXY_BYTES = 20 * 1024 * 1024
# 请求远程图片时使用的 User-Agent（部分 CDN 会拒绝无 UA 的请求）
UPSTREAM_USER_AGENT = "Agnes-Platform-ImageProxy/1.0"

# 独立的 httpx.AsyncClient（不复用 agnes_client 的连接池）
# - follow_redirects=True：CDN 301/302 重定向自动跟随
# - 专用超时：连接 10s，读取 30s
_proxy_client: httpx.AsyncClient | None = None


async def _get_proxy_client() -> httpx.AsyncClient:
    """获取（或惰性创建）图片代理专用的 httpx.AsyncClient"""
    global _proxy_client
    if _proxy_client is None or _proxy_client.is_closed:
        _proxy_client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, connect=10.0),
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=5),
            follow_redirects=True,
            http2=False,
        )
    return _proxy_client


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
    - 自动跟随 301/302 重定向（CDN 常见）

    注意：此接口不要求登录。原因：
    1. <img src="/api/proxy/image?..."> 标签请求不会带 JWT Authorization 头
    2. 图片 URL 是用户自己生成的结果，URL 不可枚举（含随机哈希）
    3. 仅代理 image/* 类型，安全风险低
    """
    if not _is_safe_url(url):
        raise HTTPException(status_code=400, detail="不支持的 URL")

    client = await _get_proxy_client()

    try:
        # 完整下载图片到内存后再返回（不用 StreamingResponse）
        # 原因：StreamingResponse 的 gen() 在 async with 上下文关闭后
        #   无法再从 upstream 读取数据，导致返回空响应体
        resp = await client.get(
            url,
            timeout=30.0,
            headers={"User-Agent": UPSTREAM_USER_AGENT},
        )

        if resp.status_code != 200:
            logger.warning(
                "[图片代理] 远程返回非 200: status=%s url=%s body=%s",
                resp.status_code, url[:120], resp.text[:200],
            )
            raise HTTPException(
                status_code=502,
                detail=f"远程图片拉取失败：HTTP {resp.status_code}",
            )

        content_type = resp.headers.get("content-type", "").split(";")[0].strip()
        if not content_type.startswith(ALLOWED_CONTENT_TYPES):
            raise HTTPException(status_code=400, detail=f"非图片类型：{content_type}")

        data = resp.content
        if not data or len(data) == 0:
            raise HTTPException(status_code=502, detail="远程图片数据为空")

        if len(data) > MAX_PROXY_BYTES:
            raise HTTPException(status_code=502, detail=f"图片过大：{len(data) // (1024*1024)}MB")

        logger.info(
            "[图片代理] 成功: url=%s size=%dKB type=%s",
            url[:80], len(data) // 1024, content_type,
        )

        # 用 Response 一次性返回完整数据（图片通常不超过几 MB，完全可以放内存）
        return Response(
            content=data,
            media_type=content_type or "image/octet-stream",
            headers={
                "Access-Control-Allow-Origin": "*",
                "Cache-Control": "public, max-age=3600",
            },
        )
    except httpx.HTTPError as e:
        logger.warning("[图片代理] 拉取失败 url=%s err=%s", url[:120], e)
        raise HTTPException(status_code=502, detail=f"远程图片拉取失败：{e}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("[图片代理] 未知错误 url=%s err=%s", url[:120], e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"代理内部错误：{e}")
