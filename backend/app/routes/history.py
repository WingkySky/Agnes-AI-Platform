# =====================================================
# 生成历史记录路由（全异步）
# GET    /api/history           - 获取历史列表（分页 + 按类型筛选）
# DELETE /api/history/{id}      - 删除单条记录
# DELETE /api/history/batch     - 批量删除多条记录（按 ID 列表）
# GET    /api/history/{id}/download         - 下载文件（图片/视频，强制浏览器保存到本地）
# GET    /api/history/batch-download         - 批量下载文件（打包为 zip）
# GET    /api/download                        - 通过 URL 代理下载文件
# GET    /api/history/video/{id}/stream    - 视频流代理（支持 Range 请求 + CORS）
# GET    /api/history/video/{id}/thumbnail - 视频首帧缩略图提取
# GET    /api/history/video/{id}/preview   - 视频预览片段（悬停 GIF 效果）
# =====================================================

import logging
import os
import hashlib
import tempfile
import asyncio
import httpx
import glob as glob_module
import zipfile
import io
from datetime import datetime
from typing import Optional, List, Tuple
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, Depends, Query, Request
from fastapi.responses import Response as FastAPIResponse, FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import desc, func

from app.core.database import get_async_db
from app.core.security import get_current_user_optional, get_current_user
from app.models.generation import Generation
from app.models.user import User
from app.routes._media_proxy import proxy_video_stream
from app.services.moderation_service import mark_pending_with_keyword_check, queue_ai_moderation
from app.schemas.common import (
    HistoryListResponse,
    GenerationRecord,
    DeleteResponse,
    BatchDeleteRequest,
    BatchDeleteResponse,
)
from app.schemas.plaza import (
    UpdateShareStatusRequest,
    UpdateShareStatusResponse,
    BatchShareRequest,
    BatchShareResponse,
)

logger = logging.getLogger("agnes_platform")
router = APIRouter()


def _user_scope(col, current_user):
    """用户隔离过滤条件：已登录限定本人记录，未登录仅可见无主记录。"""
    if current_user:
        return col == current_user.id
    return col.is_(None)


# =====================================================
# 下载代理公共工具（批量下载 / 单文件下载 / URL 下载共用）
# =====================================================

# URL 路径后缀 → (扩展名, MIME 类型) 探测规则（顺序即匹配优先级）
_URL_EXT_RULES = (
    (".jpg", ".jpg", "image/jpeg"),
    (".jpeg", ".jpg", "image/jpeg"),
    (".webp", ".webp", "image/webp"),
    (".gif", ".gif", "image/gif"),
    (".mp4", ".mp4", "video/mp4"),
)


def _sniff_url_ext(url: str) -> Optional[Tuple[str, str]]:
    """从 URL 路径中尝试提取更准确的扩展名与 MIME 类型，未命中返回 None。"""
    url_path = urlparse(url).path.lower()
    for suffix, ext, content_type in _URL_EXT_RULES:
        if url_path.endswith(suffix):
            return ext, content_type
    return None


def _is_html_content_type(ct: str) -> bool:
    """源站返回 HTML（通常是错误页/鉴权页）时视为无效内容。"""
    return bool(ct) and ("text/html" in ct or "application/xhtml" in ct)


async def _proxy_attachment(url: str) -> httpx.Response:
    """代理下载远程文件。非 200 或源站返回 HTML 时抛 502 HTTPException。"""
    async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
        response = await client.get(url, headers={"User-Agent": "Agnes-Platform-Download"})

    if response.status_code != 200:
        raise HTTPException(status_code=502, detail=f"下载源文件失败 (HTTP {response.status_code})")

    if _is_html_content_type(response.headers.get("content-type", "")):
        raise HTTPException(
            status_code=502,
            detail="源文件返回了 HTML 页面（可能链接已失效或被拦截），无法下载",
        )
    return response


async def _apply_watermark_if_needed(
    db: AsyncSession,
    current_user: Optional[User],
    file_type: str,
    file_content: bytes,
) -> Tuple[bytes, bool]:
    """
    图片类型：按水印配置动态应用水印（不保存到磁盘）。
    返回 (文件内容, 是否已加水印)；非图片、未启用或处理失败时返回原图。
    """
    if file_type != "image":
        return file_content, False
    try:
        from app.services.watermark_service import get_watermark_config, should_apply_watermark, apply_image_watermark
        wm_config = await get_watermark_config(db)
        if should_apply_watermark(wm_config, current_user):
            return apply_image_watermark(file_content, wm_config), True
    except Exception as e:
        logger.warning("[下载代理] 水印处理失败，返回原图: %s", e)
    return file_content, False


def _download_response_headers(filename: str) -> dict:
    """下载代理统一响应头：强制浏览器保存文件并允许 CORS 读取文件名。"""
    return {
        "Content-Disposition": f'attachment; filename="{filename}"',
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Expose-Headers": "Content-Disposition",
    }


@router.get("/history", response_model=HistoryListResponse, summary="获取生成历史列表")
async def get_history(
    type: Optional[str] = Query(None, description="筛选类型: image / video / all（默认）"),
    source: Optional[str] = Query("independent", description="来源筛选: independent（默认，独立生成）/ canvas / project / all"),
    task_id: Optional[str] = Query(None, description="按 task_id 精确匹配（用于从积分明细跳转）"),
    page: int = Query(1, ge=1, description="页码，从 1 开始"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    db: AsyncSession = Depends(get_async_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """
    分页获取生成历史记录（按用户隔离，异步查询，不阻塞事件循环），按创建时间倒序排列。
    支持通过 task_id 精确匹配某条记录（用于积分明细跳转）。

    来源筛选（source）：
      - independent：默认，仅独立生成（画布/项目生成已自动归档进资产库，历史页默认隐藏）
      - canvas / project：仅对应创作容器的生成
      - all：全部（按 task_id 跳转时忽略 source，确保能定位到任意记录）
    """
    stmt = select(Generation)

    # --- 用户隔离：只返回当前用户的记录 ---
    stmt = stmt.filter(_user_scope(Generation.user_id, current_user))

    if type and type.lower() in ("image", "video"):
        stmt = stmt.filter(Generation.type == type.lower())

    # 按 task_id 精确匹配（用于积分明细跳转到对应历史记录）：忽略 source 筛选
    if task_id:
        stmt = stmt.filter(Generation.task_id == task_id)
    elif source and source != "all":
        # 默认 independent：隐藏画布/项目生成（已自动归档进资产库）
        stmt = stmt.filter(Generation.source == source)

    # 总数查询（按筛选条件）
    count_stmt = select(func.count()).select_from(stmt.subquery())
    count_result = await db.execute(count_stmt)
    total = count_result.scalar_one() or 0

    # 各类型全局计数（按用户隔离，不受 type 筛选条件影响）
    img_count_stmt = select(func.count()).filter(Generation.type == "image")
    vid_count_stmt = select(func.count()).filter(Generation.type == "video")
    img_count_stmt = img_count_stmt.filter(_user_scope(Generation.user_id, current_user))
    vid_count_stmt = vid_count_stmt.filter(_user_scope(Generation.user_id, current_user))
    img_count_result = await db.execute(img_count_stmt)
    vid_count_result = await db.execute(vid_count_stmt)
    total_image_count = img_count_result.scalar_one() or 0
    total_video_count = vid_count_result.scalar_one() or 0

    # 分页 + 倒序查询
    stmt = stmt.order_by(desc(Generation.created_at)).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(stmt)
    items = result.scalars().all()

    # 转换为响应对象
    records = [GenerationRecord.model_validate(item) for item in items]

    return HistoryListResponse(
        total=total,
        page=page,
        page_size=page_size,
        items=records,
        total_image_count=total_image_count,
        total_video_count=total_video_count,
    )


@router.delete("/history/{record_id}", response_model=DeleteResponse, summary="删除单条历史记录")
async def delete_history_record(
    record_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """
    根据 ID 删除一条生成历史记录（按用户隔离，异步操作，不阻塞事件循环）。
    """
    stmt = select(Generation).filter(Generation.id == record_id)
    stmt = stmt.filter(_user_scope(Generation.user_id, current_user))
    result = await db.execute(stmt)
    record = result.scalar_one_or_none()

    if not record:
        raise HTTPException(status_code=404, detail="未找到对应记录")

    try:
        # 删除记录前先清理缩略图缓存
        _cleanup_thumbnail_cache(record_id)
        await db.delete(record)
        await db.commit()
        logger.info("[历史记录] 已异步删除: id=%s", record_id)
        return DeleteResponse(success=True, message=f"已删除记录 ID={record_id}")
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"删除失败: {e}")


@router.post("/history/batch-delete", response_model=BatchDeleteResponse, summary="批量删除历史记录")
async def batch_delete_history(
    body: BatchDeleteRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """
    根据 ID 列表批量删除多条生成历史记录（按用户隔离，异步事务操作）。
    即使部分 ID 不属于当前用户，也会被忽略。
    """
    ids = body.ids or []
    if not ids:
        raise HTTPException(status_code=400, detail="请提供至少一个要删除的记录 ID")

    # 去重
    unique_ids = list(set(ids))

    try:
        # 查询所有待删除记录（按用户隔离）
        stmt = select(Generation).filter(Generation.id.in_(unique_ids))
        stmt = stmt.filter(_user_scope(Generation.user_id, current_user))
        result = await db.execute(stmt)
        records = result.scalars().all()

        deleted_ids = []
        for record in records:
            deleted_ids.append(record.id)
            # 清理该记录的缩略图缓存
            _cleanup_thumbnail_cache(record.id)
            await db.delete(record)

        await db.commit()

        # 计算失败（未找到或不属于当前用户）的 ID
        failed_ids = [rid for rid in unique_ids if rid not in deleted_ids]

        logger.info(
            "[历史记录] 批量删除完成：请求 %d 条，成功 %d 条，失败 %d 条",
            len(unique_ids),
            len(deleted_ids),
            len(failed_ids),
        )

        return BatchDeleteResponse(
            success=True,
            message=f"已删除 {len(deleted_ids)} 条记录",
            deleted_count=len(deleted_ids),
            failed_ids=failed_ids,
        )
    except Exception as e:
        await db.rollback()
        logger.exception("[历史记录] 批量删除失败: %s", e)
        raise HTTPException(status_code=500, detail=f"批量删除失败: {e}")


# =====================================================
# 批量下载接口（必须在 /history/{record_id}/download 之前注册，避免路由冲突）
# 用途：将多个图片/视频打包为 zip 文件下载
# =====================================================


@router.get("/history/batch-download", summary="批量下载文件（打包为 zip）")
async def batch_download_files(
    ids: str = Query(..., description="记录 ID 列表，逗号分隔"),
    db: AsyncSession = Depends(get_async_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """
    批量下载图片/视频，打包为 zip 文件（按用户隔离）。

    参数：
    - ids: 逗号分隔的记录 ID 列表（如 "1,2,3"）

    返回：
    - zip 文件流，包含所有选中记录的图片/视频文件
    """
    if not ids:
        raise HTTPException(status_code=400, detail="缺少 ids 参数")

    try:
        id_list = [int(i.strip()) for i in ids.split(",") if i.strip()]
    except ValueError:
        raise HTTPException(status_code=400, detail="ids 格式错误，应为逗号分隔的数字")

    if not id_list:
        raise HTTPException(status_code=400, detail="ids 不能为空")

    if len(id_list) > 100:
        raise HTTPException(status_code=400, detail="单次最多下载 100 个文件")

    # 查询所有选中记录（按用户隔离）
    stmt = select(Generation).filter(Generation.id.in_(id_list))
    stmt = stmt.filter(_user_scope(Generation.user_id, current_user))
    result = await db.execute(stmt)
    records = result.scalars().all()

    if not records:
        raise HTTPException(status_code=404, detail="未找到对应记录")

    # 获取水印配置（只查一次，复用）
    wm_config = None
    need_watermark = False
    try:
        from app.services.watermark_service import get_watermark_config, should_apply_watermark
        wm_config = await get_watermark_config(db)
        need_watermark = should_apply_watermark(wm_config, current_user)
    except Exception as e:
        logger.warning("[批量下载] 获取水印配置失败，跳过水印: %s", e)

    # 在内存中构建 zip 文件
    zip_buffer = io.BytesIO()

    async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            for record in records:
                if not record.result_url:
                    continue

                # 确定文件扩展名：按类型取默认值，再从 URL 路径中尝试提取更准确的扩展名
                sniffed = _sniff_url_ext(record.result_url)
                ext = sniffed[0] if sniffed else (".mp4" if record.type == "video" else ".png")
                filename = f"agnes-{record.type}-{record.id}{ext}"

                try:
                    response = await client.get(
                        record.result_url,
                        headers={"User-Agent": "Agnes-Platform-Download"}
                    )
                    if response.status_code == 200:
                        # 跳过源站返回的 HTML 错误页，避免把 HTML 当图片打包进 zip
                        if _is_html_content_type(response.headers.get("content-type", "")):
                            logger.warning("[批量下载] 跳过返回 HTML 的文件: id=%s", record.id)
                            continue

                        file_content = response.content

                        # 图片类型：动态应用水印
                        if record.type == "image" and need_watermark and wm_config:
                            try:
                                from app.services.watermark_service import apply_image_watermark
                                file_content = apply_image_watermark(file_content, wm_config)
                                # 水印后统一为 PNG，更新文件名
                                filename = f"agnes-{record.type}-{record.id}.png"
                            except Exception as e:
                                logger.warning("[批量下载] 水印处理失败，用原图: id=%s, error=%s", record.id, e)

                        zf.writestr(filename, file_content)
                    else:
                        logger.warning("[批量下载] 跳过失败文件: id=%s, status=%s",
                                       record.id, response.status_code)
                except Exception as e:
                    logger.warning("[批量下载] 跳过异常文件: id=%s, error=%s", record.id, e)

    zip_buffer.seek(0)
    zip_filename = f"agnes-batch-{int(asyncio.get_event_loop().time())}.zip"

    return FastAPIResponse(
        content=zip_buffer.read(),
        media_type="application/zip",
        headers=_download_response_headers(zip_filename),
    )


# =====================================================
# 单文件下载代理接口
# 用途：通过后端代理下载图片/视频，设置 Content-Disposition: attachment
#       强制浏览器弹出保存对话框，而非在新标签页中打开
# =====================================================


@router.get("/history/{record_id}/download", summary="下载文件（图片/视频，强制保存到本地）")
async def download_file(
    record_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """
    通过后端代理下载图片或视频文件（按用户隔离）。

    解决的问题：
    - 前端直接 fetch 远程 URL 会因 CORS 被拦截
    - window.open() 只会在新标签页打开，不会下载
    - 后端代理下载并设置 Content-Disposition: attachment，强制浏览器保存文件

    支持的文件类型：
    - 图片（image）：下载为 .png 文件
    - 视频（video）：下载为 .mp4 文件
    """
    # 查询记录（按用户隔离）
    stmt = select(Generation).filter(Generation.id == record_id)
    stmt = stmt.filter(_user_scope(Generation.user_id, current_user))
    result = await db.execute(stmt)
    record = result.scalar_one_or_none()

    if not record:
        raise HTTPException(status_code=404, detail="未找到对应记录")

    if not record.result_url:
        raise HTTPException(status_code=400, detail="该记录没有可下载的资源")

    file_url = record.result_url
    file_type = record.type  # "image" 或 "video"

    # 根据类型确定文件扩展名和 MIME 类型
    ext, content_type = (".mp4", "video/mp4") if file_type == "video" else (".png", "image/png")

    # 生成文件名
    filename = f"agnes-{file_type}-{record_id}{ext}"

    try:
        response = await _proxy_attachment(file_url)

        # 从响应中获取实际 Content-Type（如果有的话）
        actual_ct = response.headers.get("content-type", "")
        if actual_ct and actual_ct != "application/octet-stream":
            content_type = actual_ct

        # 从 URL 路径中尝试提取更准确的扩展名（与原逻辑一致：仅识别 jpg/webp 后缀）
        sniffed = _sniff_url_ext(file_url)
        if sniffed and sniffed[0] in (".jpg", ".webp"):
            ext = sniffed[0]
            filename = f"agnes-{file_type}-{record_id}{ext}"
            if file_type != "video":
                content_type = sniffed[1]

        file_content = response.content

        # 图片类型：动态应用水印（不保存到磁盘）
        file_content, watermarked = await _apply_watermark_if_needed(db, current_user, file_type, file_content)
        if watermarked:
            # 水印处理后统一为 PNG，更新扩展名和 MIME
            ext = ".png"
            filename = f"agnes-{file_type}-{record_id}{ext}"
            content_type = "image/png"

        return FastAPIResponse(
            content=file_content,
            media_type=content_type,
            headers=_download_response_headers(filename),
        )
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="下载源文件超时")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("[历史记录] 下载代理失败: %s", e)
        raise HTTPException(status_code=500, detail=f"下载失败: {str(e)}")


@router.get("/download", summary="通过 URL 代理下载文件（强制保存到本地）")
async def download_by_url(
    url: str,
    type: str = Query("image", description="文件类型：image 或 video"),
    filename: Optional[str] = Query(None, description="自定义文件名（含扩展名），不传则自动生成"),
    db: AsyncSession = Depends(get_async_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """
    通过 URL 代理下载文件。

    用于图片/视频预览页面的下载功能，这些页面只有远程 URL 而没有 record_id。
    后端代理下载并设置 Content-Disposition: attachment，强制浏览器保存文件。

    参数：
    - url: 远程文件的公网 URL
    - type: 文件类型（image 或 video），用于确定文件扩展名
    - filename: 自定义文件名（含扩展名），不传则自动生成
    """
    if not url:
        raise HTTPException(status_code=400, detail="缺少 url 参数")

    if not url.startswith("http://") and not url.startswith("https://"):
        raise HTTPException(status_code=400, detail="url 必须是 HTTP/HTTPS 链接")

    # 根据类型确定默认扩展名和 MIME 类型
    ext, content_type = (".mp4", "video/mp4") if type == "video" else (".png", "image/png")

    # 从 URL 路径中尝试提取更准确的扩展名
    sniffed = _sniff_url_ext(url)
    if sniffed:
        ext, content_type = sniffed

    # 优先使用前端传入的自定义文件名，否则自动生成
    if filename:
        # 确保文件名有扩展名
        if not any(filename.lower().endswith(e) for e in ['.png', '.jpg', '.jpeg', '.webp', '.gif', '.mp4']):
            filename += ext
    else:
        filename = f"agnes-{type}-{int(asyncio.get_event_loop().time())}{ext}"

    try:
        response = await _proxy_attachment(url)

        # 从响应中获取实际 Content-Type
        actual_ct = response.headers.get("content-type", "")
        if actual_ct and actual_ct != "application/octet-stream":
            content_type = actual_ct

        file_content = response.content

        # 图片类型：动态应用水印
        file_content, watermarked = await _apply_watermark_if_needed(db, current_user, type, file_content)
        if watermarked:
            # 水印后统一为 PNG，替换文件名扩展名
            ext = ".png"
            content_type = "image/png"
            base = filename.rsplit('.', 1)[0] if '.' in filename else filename
            filename = base + ext

        return FastAPIResponse(
            content=file_content,
            media_type=content_type,
            headers=_download_response_headers(filename),
        )
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="下载源文件超时")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("[下载代理] URL 下载失败: %s", e)
        raise HTTPException(status_code=500, detail=f"下载失败: {str(e)}")


# =====================================================
# 视频流代理接口
# 用途：解决前端直接播放 Google Storage 视频时的 CORS 和 Range 请求问题
# =====================================================


@router.get("/history/video/{record_id}/stream", summary="视频流代理（支持 Range + CORS）")
async def stream_video(
    request: Request,
    record_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """
    代理播放历史视频资源（按用户隔离）。

    当前端直接访问 Google Storage 视频 URL 时，会遇到：
    1. CORS 缺少 Access-Control-Allow-Origin 头
    2. Range 请求返回 206 但浏览器解析失败

    本接口通过后端转发视频流，自动处理：
    - 添加 CORS 响应头（Allow-Origin、Accept-Ranges、Content-Type 等）
    - 支持 HTTP Range 请求（用于视频拖动/seek）
    - 正确返回 Content-Range / Content-Length，确保浏览器可正常播放和拖动
    - 以流式传输避免大文件内存占用
    """
    # 查询视频记录（按用户隔离）
    stmt = select(Generation).filter(Generation.id == record_id)
    stmt = stmt.filter(_user_scope(Generation.user_id, current_user))
    result = await db.execute(stmt)
    record = result.scalar_one_or_none()

    if not record:
        raise HTTPException(status_code=404, detail="未找到对应视频记录")

    if record.type != "video":
        raise HTTPException(status_code=400, detail="该记录不是视频类型")

    if not record.result_url:
        raise HTTPException(status_code=404, detail="视频资源链接不存在")

    video_url = record.result_url
    return await proxy_video_stream(video_url, request.headers.get("range"))


# =====================================================
# 视频缩略图 & 预览接口
# 用途：提取视频首帧作为缩略图，提取多帧生成 GIF 预览
# 缓存策略：使用文件系统缓存，避免重复提取
# =====================================================

# 缩略图缓存目录
THUMBNAIL_CACHE_DIR = os.path.join(tempfile.gettempdir(), "agnes_thumbnails")
os.makedirs(THUMBNAIL_CACHE_DIR, exist_ok=True)


def _get_cache_path(record_id: int, suffix: str, video_url: str = "") -> str:
    """
    根据记录 ID 和视频 URL 生成缓存文件路径。
    文件名包含视频 URL 的哈希值，避免删除旧记录后新记录复用相同 ID 时命中旧缓存。
    """
    url_hash = hashlib.md5(video_url.encode()).hexdigest()[:8] if video_url else "nourl"
    filename = f"video_{record_id}_{url_hash}{suffix}"
    return os.path.join(THUMBNAIL_CACHE_DIR, filename)


def _cleanup_thumbnail_cache(record_id: int):
    """
    清理指定记录 ID 的所有缩略图和预览缓存文件。
    删除记录时调用，避免缓存残留。
    """
    try:
        # 匹配所有以 video_{id}_ 开头的缓存文件（包括新旧格式）
        patterns = [
            os.path.join(THUMBNAIL_CACHE_DIR, f"video_{record_id}_*"),
            os.path.join(THUMBNAIL_CACHE_DIR, f"video_{record_id}_thumb.jpg"),
            os.path.join(THUMBNAIL_CACHE_DIR, f"video_{record_id}_preview.gif"),
        ]
        for pattern in patterns:
            for f in glob_module.glob(pattern):
                os.remove(f)
                logger.info("[缓存清理] 已删除缓存文件: %s", f)
    except Exception as e:
        logger.warning("[缓存清理] 清理记录 %d 的缓存失败: %s", record_id, e)


async def _download_video_partial(video_url: str, output_path: str, max_bytes: int = 5 * 1024 * 1024) -> bool:
    """
    下载视频的前 N 字节到临时文件（用于 ffmpeg 提取帧）。
    大多数视频的 moov atom 在文件头部，5MB 足够提取首帧。
    返回是否下载成功。
    """
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            async with client.stream("GET", video_url, headers={"Range": "bytes=0-" + str(max_bytes - 1)}) as response:
                # 某些服务器不支持 Range，返回 200；支持则返回 206
                if response.status_code not in (200, 206):
                    return False
                with open(output_path, "wb") as f:
                    async for chunk in response.aiter_bytes():
                        f.write(chunk)
                        if f.tell() >= max_bytes:
                            break
        return os.path.getsize(output_path) > 0
    except Exception as e:
        logger.warning("[缩略图] 下载视频片段失败: %s", e)
        return False


async def _extract_frame_with_ffmpeg(input_path: str, output_path: str, time_offset: str = "0") -> bool:
    """
    使用 ffmpeg 从视频中提取指定时间点的帧。
    time_offset 格式：如 "0"（首帧）、"1"（第1秒）等。
    返回是否提取成功。
    """
    try:
        cmd = [
            "ffmpeg", "-y",
            "-ss", time_offset,
            "-i", input_path,
            "-vframes", "1",
            "-q:v", "4",
            "-vf", "scale=480:-2",
            output_path,
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=15.0)
        if proc.returncode != 0:
            logger.warning("[缩略图] ffmpeg 提取帧失败 (offset=%s): %s", time_offset, stderr.decode(errors="ignore")[:200])
            return False
        return os.path.getsize(output_path) > 0
    except asyncio.TimeoutError:
        logger.warning("[缩略图] ffmpeg 超时")
        return False
    except Exception as e:
        logger.warning("[缩略图] ffmpeg 异常: %s", e)
        return False


async def _extract_gif_with_ffmpeg(input_path: str, output_path: str, duration: float = 3.0) -> bool:
    """
    使用 ffmpeg 从视频中提取前 N 秒生成 GIF 预览。
    返回是否生成成功。
    """
    try:
        cmd = [
            "ffmpeg", "-y",
            "-t", str(duration),
            "-i", input_path,
            "-vf", "fps=6,scale=320:-1:flags=lanczos,split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse",
            "-loop", "0",
            output_path,
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=30.0)
        if proc.returncode != 0:
            logger.warning("[缩略图] ffmpeg 生成 GIF 失败: %s", stderr.decode(errors="ignore")[:200])
            return False
        return os.path.getsize(output_path) > 0
    except asyncio.TimeoutError:
        logger.warning("[缩略图] ffmpeg GIF 生成超时")
        return False
    except Exception as e:
        logger.warning("[缩略图] ffmpeg GIF 异常: %s", e)
        return False


@router.get("/history/video/{record_id}/thumbnail", summary="视频首帧缩略图")
async def get_video_thumbnail(
    record_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """
    提取视频首帧作为缩略图（JPEG 格式）。
    - 视频所有者可访问
    - 已公开且审核通过的作品，所有用户均可访问（用于广场展示）
    - 管理员/审核员可访问任意状态的作品（用于审核页展示）
    使用文件缓存，同一视频只提取一次。
    """
    # 查询视频记录
    stmt = select(Generation).filter(Generation.id == record_id)
    result = await db.execute(stmt)
    record = result.scalar_one_or_none()

    if not record:
        raise HTTPException(status_code=404, detail="未找到对应视频记录")

    if record.type != "video":
        raise HTTPException(status_code=400, detail="该记录不是视频类型")

    # 权限校验：本人可看；已公开且审核通过的作品所有人可看；管理员/审核员可看任意作品
    is_owner = current_user and record.user_id == current_user.id
    is_public_approved = record.is_public and record.moderation_status == "approved"
    is_staff = current_user and (
        current_user.role == "admin"
        or getattr(current_user, "is_admin", False)
        or current_user.role == "moderator"
    )
    if not is_owner and not is_public_approved and not is_staff:
        raise HTTPException(status_code=404, detail="未找到对应视频记录")

    if not record.result_url:
        raise HTTPException(status_code=404, detail="视频资源链接不存在")

    # 检查缓存（缓存路径包含视频 URL 哈希，避免旧记录缓存误命中）
    cache_path = _get_cache_path(record_id, "_thumb.jpg", record.result_url)
    if os.path.exists(cache_path) and os.path.getsize(cache_path) > 0:
        return FileResponse(
            cache_path,
            media_type="image/jpeg",
            headers={
                "Access-Control-Allow-Origin": "*",
                "Cache-Control": "public, max-age=60, must-revalidate",
            },
        )

    # 下载视频片段并提取首帧
    # 注意：5MB 对某些视频（如 Seedance 输出）不足以包含完整 moov atom，
    # 这里与 preview 端点一致使用 10MB；若仍失败则回退到完整下载。
    tmp_video = os.path.join(tempfile.gettempdir(), f"agnes_vtmp_{record_id}.mp4")
    try:
        download_ok = await _download_video_partial(
            record.result_url, tmp_video, max_bytes=10 * 1024 * 1024
        )
        if not download_ok:
            raise HTTPException(status_code=500, detail="下载视频片段失败，无法提取缩略图")

        extract_ok = await _extract_frame_with_ffmpeg(tmp_video, cache_path, time_offset="0")
        if not extract_ok:
            # 首帧提取失败时，尝试第 0.5 秒
            extract_ok = await _extract_frame_with_ffmpeg(tmp_video, cache_path, time_offset="0.5")

        # 10MB 片段仍失败（moov atom 在文件尾部等场景），回退到下载完整视频再提取
        if not extract_ok:
            logger.info(
                "[缩略图] 10MB 片段提取失败，回退到完整下载: record_id=%d", record_id
            )
            download_ok = await _download_video_partial(
                record.result_url, tmp_video, max_bytes=100 * 1024 * 1024
            )
            if download_ok:
                extract_ok = await _extract_frame_with_ffmpeg(
                    tmp_video, cache_path, time_offset="0"
                )
                if not extract_ok:
                    extract_ok = await _extract_frame_with_ffmpeg(
                        tmp_video, cache_path, time_offset="0.5"
                    )

        if not extract_ok or not os.path.exists(cache_path):
            raise HTTPException(status_code=500, detail="提取视频首帧失败")

        return FileResponse(
            cache_path,
            media_type="image/jpeg",
            headers={
                "Access-Control-Allow-Origin": "*",
                "Cache-Control": "public, max-age=60, must-revalidate",
            },
        )
    finally:
        # 清理临时视频文件
        if os.path.exists(tmp_video):
            os.remove(tmp_video)


@router.get("/history/video/{record_id}/preview", summary="视频预览 GIF（悬停效果）")
async def get_video_preview(
    record_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """
    生成视频前 3 秒的 GIF 预览，用于鼠标悬停时的动态效果。
    - 视频所有者可访问
    - 已公开且审核通过的作品，所有用户均可访问（用于广场展示）
    - 管理员/审核员可访问任意状态的作品（用于审核页展示）
    使用文件缓存，同一视频只生成一次。
    """
    # 查询视频记录
    stmt = select(Generation).filter(Generation.id == record_id)
    result = await db.execute(stmt)
    record = result.scalar_one_or_none()

    if not record:
        raise HTTPException(status_code=404, detail="未找到对应视频记录")

    if record.type != "video":
        raise HTTPException(status_code=400, detail="该记录不是视频类型")

    # 权限校验：本人可看；已公开且审核通过的作品所有人可看；管理员/审核员可看任意作品
    is_owner = current_user and record.user_id == current_user.id
    is_public_approved = record.is_public and record.moderation_status == "approved"
    is_staff = current_user and (
        current_user.role == "admin"
        or getattr(current_user, "is_admin", False)
        or current_user.role == "moderator"
    )
    if not is_owner and not is_public_approved and not is_staff:
        raise HTTPException(status_code=404, detail="未找到对应视频记录")

    if not record.result_url:
        raise HTTPException(status_code=404, detail="视频资源链接不存在")

    # 检查缓存（缓存路径包含视频 URL 哈希，避免旧记录缓存误命中）
    cache_path = _get_cache_path(record_id, "_preview.gif", record.result_url)
    if os.path.exists(cache_path) and os.path.getsize(cache_path) > 0:
        return FileResponse(
            cache_path,
            media_type="image/gif",
            headers={
                "Access-Control-Allow-Origin": "*",
                "Cache-Control": "public, max-age=60, must-revalidate",
            },
        )

    # 下载视频片段并生成 GIF
    tmp_video = os.path.join(tempfile.gettempdir(), f"agnes_vtmp_{record_id}_preview.mp4")
    try:
        download_ok = await _download_video_partial(record.result_url, tmp_video, max_bytes=10 * 1024 * 1024)
        if not download_ok:
            raise HTTPException(status_code=500, detail="下载视频片段失败，无法生成预览")

        gif_ok = await _extract_gif_with_ffmpeg(tmp_video, cache_path, duration=3.0)
        if not gif_ok or not os.path.exists(cache_path):
            raise HTTPException(status_code=500, detail="生成视频预览 GIF 失败")

        return FileResponse(
            cache_path,
            media_type="image/gif",
            headers={
                "Access-Control-Allow-Origin": "*",
                "Cache-Control": "public, max-age=60, must-revalidate",
            },
        )
    finally:
        # 清理临时视频文件
        if os.path.exists(tmp_video):
            os.remove(tmp_video)


# =====================================================
# 分享状态管理接口（广场功能）
# PATCH  /api/history/{id}/share       - 单条切换分享状态（需登录，按用户隔离）
# PATCH  /api/history/batch-share      - 批量设置分享状态（需登录，按用户隔离）
# =====================================================


@router.patch("/history/{record_id}/share", response_model=UpdateShareStatusResponse, summary="单条切换分享状态")
async def update_share_status(
    record_id: int,
    body: UpdateShareStatusRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """
    切换单条记录的公开/私有状态（需登录，按用户隔离）。
    - false → true 且 public_shared_at 为空时，写入 public_shared_at = NOW()
    - true → false 时，保留 public_shared_at（方便二次公开时保留历史时间）
    - 设为公开时，默认进入待审核状态（pending），需 AI 预审 + 人工复审通过后才在广场展示
    """
    stmt = select(Generation).filter(
        Generation.id == record_id,
        Generation.user_id == current_user.id,
    )
    result = await db.execute(stmt)
    record = result.scalar_one_or_none()

    if not record:
        raise HTTPException(status_code=404, detail="未找到对应记录或无权操作")

    # ===== 被管理员屏蔽的作品，用户不能再次设为公开 =====
    if body.is_public and record.moderation_status == "rejected":
        raise HTTPException(
            status_code=403,
            detail="该作品已被管理员屏蔽，无法公开到广场",
        )

    was_public = record.is_public
    record.is_public = body.is_public

    # 首次设为公开时记录时间
    if body.is_public and not was_public and not record.public_shared_at:
        record.public_shared_at = datetime.utcnow()

    # ===== 设为公开时：进入待审核状态，先做敏感词快速筛查，再异步触发 AI 图像审核 =====
    if body.is_public and not was_public:
        await mark_pending_with_keyword_check(record, db)
        # 异步触发 AI 图像/视频内容审核（不阻塞接口响应）
        queue_ai_moderation(record)

    await db.commit()
    await db.refresh(record)

    if body.is_public:
        msg = "已提交分享，正在审核中，审核通过后将展示到广场"
    else:
        msg = "已设为仅自己可见"
    logger.info("[广场] 用户 %s 切换记录 %s 分享状态: %s", current_user.id, record_id, body.is_public)

    return UpdateShareStatusResponse(
        success=True,
        id=record_id,
        is_public=body.is_public,
        message=msg,
    )


@router.patch("/history/batch-share", response_model=BatchShareResponse, summary="批量设置分享状态")
async def batch_update_share_status(
    body: BatchShareRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """
    批量设置多条记录的公开/私有状态（需登录，按用户隔离）。
    不属于当前用户的 ID 会被忽略并计入 failed_ids。
    设为公开时默认进入待审核状态。
    """
    ids = body.ids or []
    if not ids:
        raise HTTPException(status_code=400, detail="请提供至少一个记录 ID")

    unique_ids = list(set(ids))

    # 查询所有待更新记录（按用户隔离）
    stmt = select(Generation).filter(
        Generation.id.in_(unique_ids),
        Generation.user_id == current_user.id,
    )
    result = await db.execute(stmt)
    records = result.scalars().all()

    now = datetime.utcnow()
    updated_ids = []
    newly_public_records = []  # 收集本次新公开的记录，用于触发异步 AI 审核

    for record in records:
        # ===== 被管理员屏蔽的作品，跳过，不允许再次公开 =====
        if body.is_public and record.moderation_status == "rejected":
            continue

        was_public = record.is_public
        record.is_public = body.is_public
        # 首次设为公开时记录时间
        if body.is_public and not was_public and not record.public_shared_at:
            record.public_shared_at = now

        # ===== 设为公开时：进入待审核状态，敏感词快速筛查 =====
        if body.is_public and not was_public:
            await mark_pending_with_keyword_check(record, db)
            newly_public_records.append(record)

        updated_ids.append(record.id)

    await db.commit()

    # 批量触发异步 AI 审核
    for rec in newly_public_records:
        queue_ai_moderation(rec)

    failed_ids = [rid for rid in unique_ids if rid not in updated_ids]
    if body.is_public:
        msg = f"已提交 {len(updated_ids)} 条作品分享，正在审核中，审核通过后将展示到广场"
    else:
        msg = f"已将 {len(updated_ids)} 条记录设为仅自己可见"
    logger.info("[广场] 用户 %s 批量切换 %d 条记录分享状态: %s", current_user.id, len(updated_ids), body.is_public)

    return BatchShareResponse(
        success=True,
        updated_count=len(updated_ids),
        failed_ids=failed_ids,
        message=msg,
    )
