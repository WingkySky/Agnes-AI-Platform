# =====================================================
# 生成历史记录路由（全异步）
# GET    /api/history           - 获取历史列表（分页 + 按类型筛选）
# DELETE /api/history/{id}      - 删除单条记录
# DELETE /api/history/batch     - 批量删除多条记录（按 ID 列表）
# GET    /api/history/video/{id}/stream - 视频流代理（支持 Range 请求 + CORS）
# =====================================================

import logging
import httpx
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Depends, Query, Request
from fastapi.responses import StreamingResponse, Response as FastAPIResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import desc, func

from app.core.database import get_async_db
from app.models.generation import Generation
from app.schemas.common import (
    HistoryListResponse,
    GenerationRecord,
    DeleteResponse,
    BatchDeleteRequest,
    BatchDeleteResponse,
)

logger = logging.getLogger("agnes_platform")
router = APIRouter()


@router.get("/history", response_model=HistoryListResponse, summary="获取生成历史列表")
async def get_history(
    type: Optional[str] = Query(None, description="筛选类型: image / video / all（默认）"),
    page: int = Query(1, ge=1, description="页码，从 1 开始"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    db: AsyncSession = Depends(get_async_db),
):
    """
    分页获取生成历史记录（异步查询，不阻塞事件循环），按创建时间倒序排列。
    """
    stmt = select(Generation)

    if type and type.lower() in ("image", "video"):
        stmt = stmt.filter(Generation.type == type.lower())

    # 总数查询
    count_stmt = select(func.count()).select_from(stmt.subquery())
    count_result = await db.execute(count_stmt)
    total = count_result.scalar_one() or 0

    # 分页 + 倒序查询
    stmt = stmt.order_by(desc(Generation.created_at)).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(stmt)
    items = result.scalars().all()

    # 转换为响应对象
    records = []
    for item in items:
        records.append(GenerationRecord(
            id=item.id,
            type=item.type,
            prompt=item.prompt,
            model=item.model,
            params=item.params,
            result_url=item.result_url,
            status=item.status,
            task_id=item.task_id,
            created_at=item.created_at,
        ))

    return HistoryListResponse(
        total=total,
        page=page,
        page_size=page_size,
        items=records,
    )


@router.delete("/history/{record_id}", response_model=DeleteResponse, summary="删除单条历史记录")
async def delete_history_record(record_id: int, db: AsyncSession = Depends(get_async_db)):
    """
    根据 ID 删除一条生成历史记录（异步操作，不阻塞事件循环）。
    """
    result = await db.execute(
        select(Generation).filter(Generation.id == record_id)
    )
    record = result.scalar_one_or_none()

    if not record:
        raise HTTPException(status_code=404, detail="未找到对应记录")

    try:
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
):
    """
    根据 ID 列表批量删除多条生成历史记录（异步事务操作）。
    即使部分 ID 不存在，也会尽量删除能查到的记录。
    """
    ids = body.ids or []
    if not ids:
        raise HTTPException(status_code=400, detail="请提供至少一个要删除的记录 ID")

    # 去重
    unique_ids = list(set(ids))

    try:
        # 查询所有待删除记录
        result = await db.execute(
            select(Generation).filter(Generation.id.in_(unique_ids))
        )
        records = result.scalars().all()

        deleted_ids = []
        for record in records:
            deleted_ids.append(record.id)
            await db.delete(record)

        await db.commit()

        # 计算失败（未找到）的 ID
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
# 视频流代理接口
# 用途：解决前端直接播放 Google Storage 视频时的 CORS 和 Range 请求问题
# =====================================================


@router.get("/history/video/{record_id}/stream", summary="视频流代理（支持 Range + CORS）")
async def stream_video(request: Request, record_id: int, db: AsyncSession = Depends(get_async_db)):
    """
    代理播放历史视频资源。

    当前端直接访问 Google Storage 视频 URL 时，会遇到：
    1. CORS 缺少 Access-Control-Allow-Origin 头
    2. Range 请求返回 206 但浏览器解析失败

    本接口通过后端转发视频流，自动处理：
    - 添加 CORS 响应头（Allow-Origin、Accept-Ranges、Content-Type 等）
    - 支持 HTTP Range 请求（用于视频拖动/seek）
    - 正确返回 Content-Range / Content-Length，确保浏览器可正常播放和拖动
    - 以流式传输避免大文件内存占用
    """
    # 查询视频记录
    result = await db.execute(
        select(Generation).filter(Generation.id == record_id)
    )
    record = result.scalar_one_or_none()

    if not record:
        raise HTTPException(status_code=404, detail="未找到对应视频记录")

    if record.type != "video":
        raise HTTPException(status_code=400, detail="该记录不是视频类型")

    if not record.result_url:
        raise HTTPException(status_code=404, detail="视频资源链接不存在")

    video_url = record.result_url
    range_header = request.headers.get("range", None)

    # 先通过 HEAD 请求获取视频元信息（总大小、内容类型）
    # 如果 HEAD 失败（某些存储服务不支持 HEAD），则回退为直接流式转发完整视频
    content_type = "video/mp4"
    total_size = 0
    head_ok = False
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            head_resp = await client.head(video_url, follow_redirects=True)
            if head_resp.status_code < 400:
                head_ok = True
                content_type = head_resp.headers.get("content-type", "video/mp4")
                # 从 Content-Length 或 Content-Range 获取文件总大小
                content_length_hdr = head_resp.headers.get("content-length")
                content_range_hdr = head_resp.headers.get("content-range")
                if content_length_hdr:
                    total_size = int(content_length_hdr)
                elif content_range_hdr:
                    # Content-Range: bytes 0-1023/10240 → 取 / 后面的总大小
                    parts = content_range_hdr.split("/")
                    if len(parts) == 2 and parts[1] != "*":
                        total_size = int(parts[1])
    except Exception:
        pass  # HEAD 失败，回退为完整流转发

    # HEAD 请求失败时：直接流式转发完整视频，不处理 Range
    if not head_ok or total_size == 0:
        async def fallback_stream():
            """HEAD 失败时的回退：直接流式转发完整视频"""
            async with httpx.AsyncClient(timeout=120.0) as client:
                async with client.stream("GET", video_url, headers={"User-Agent": "Agnes-Platform-VideoProxy"}, follow_redirects=True) as response:
                    async for chunk in response.aiter_bytes():
                        yield chunk

        return StreamingResponse(
            fallback_stream(),
            media_type=content_type,
            headers={
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Expose-Headers": "Content-Length, Content-Range, Accept-Ranges",
                "Accept-Ranges": "bytes",
                "Content-Type": content_type,
                "Cache-Control": "no-cache",
            },
            status_code=200,
        )

    # 解析 Range 请求，计算起止字节位置
    start = 0
    end = total_size - 1

    if range_header:
        # Range: bytes=0-1023 或 bytes=0-
        try:
            range_spec = range_header.replace("bytes=", "").strip()
            range_parts = range_spec.split("-")
            start = int(range_parts[0]) if range_parts[0] else 0
            end = int(range_parts[1]) if len(range_parts) > 1 and range_parts[1] else total_size - 1
            # 边界保护
            start = max(0, min(start, total_size - 1))
            end = max(start, min(end, total_size - 1))
        except (ValueError, IndexError):
            start = 0
            end = total_size - 1

    # 构造转发给上游的 Range 请求头
    req_headers = {"User-Agent": "Agnes-Platform-VideoProxy"}
    if range_header:
        req_headers["Range"] = f"bytes={start}-{end}"

    # 本次响应的内容长度
    resp_content_length = end - start + 1

    # 创建异步流生成器
    async def video_stream():
        """异步生成器：流式转发视频数据"""
        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream("GET", video_url, headers=req_headers, follow_redirects=True) as response:
                async for chunk in response.aiter_bytes():
                    yield chunk

    # 响应头设置
    response_headers = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Expose-Headers": "Content-Length, Content-Range, Accept-Ranges",
        "Accept-Ranges": "bytes",
        "Content-Type": content_type,
    }

    # 根据 Range 请求返回 206 或 200，并设置对应的 Content-Length / Content-Range
    if range_header:
        response_headers["Content-Length"] = str(resp_content_length)
        response_headers["Content-Range"] = f"bytes {start}-{end}/{total_size}"
        status_code = 206
    else:
        response_headers["Content-Length"] = str(total_size)
        status_code = 200

    return StreamingResponse(
        video_stream(),
        media_type=content_type,
        headers=response_headers,
        status_code=status_code,
    )
