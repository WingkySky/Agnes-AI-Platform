# =====================================================
# 视频生成路由（全异步）
# POST /api/videos                    - 创建视频生成任务（立即返回 task_id，后台异步轮询
# GET  /api/videos/{id}               - 查询视频任务状态（前端定时轮询此接口
# GET  /api/videos/{id}/stream        - 视频流代理（支持 Range + CORS，解决 Google Storage 跨域问题）
# DELETE /api/videos/{id}             - 中止视频任务
#
# 关键设计：
#   - 必须登录，未登录返回 401
#   - 积分不足返回 402（由 credits_service.consume_credits 抛出）
#   - 视频创建后立即返回 task_id，不阻塞后续请求
#   - 视频轮询在独立的 asyncio.Task 中进行，不影响图片生成任务
#   - 图片/视频/历史三个路由模块**互不阻塞**
# =====================================================

import logging
import httpx

from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.config import settings
from app.core.database import get_async_db, new_async_session
from app.core.security import get_current_user, get_current_user_optional
from app.models.generation import Generation
from app.models.user import User
from app.schemas.videos import (
    VideoGenerationRequest,
    VideoTaskCreatedResponse,
    VideoStatusResponse,
)
from app.services.agnes_client import agnes_client
from app.services.provider_registry import provider_registry
from app.services.credits_service import consume_credits, get_video_cost_async
from app.services.video_poller import poller_manager

logger = logging.getLogger("agnes_platform")
router = APIRouter()


# ---------- 工具：判断输入是 URL / Data URI / 纯 base64 ----------
# 仅用于日志打标签；真正的归一化在 agnes_client._normalize_image_input 里统一做
def _classify_image(s: str) -> str:
    if not s or not isinstance(s, str):
        return "empty"
    lowered = s.strip().lower()
    if lowered.startswith(("http://", "https://")):
        return "url"
    if lowered.startswith("data:"):
        return "data_uri"
    return "base64"


# ---------- 工具：校验单张参考图的大小（base64 / data_uri 都会折算为原始字节数）----------
def _validate_image_size(raw: str, label: str) -> None:
    if not raw or not isinstance(raw, str):
        return
    if raw.strip().lower().startswith(("http://", "https://")):
        return  # URL 不走本地 size 校验
    body = raw.split(",")[-1] if "," in raw else raw
    body = body.strip().replace("=", "")
    approx_bytes = len(body) * 3 / 4
    if approx_bytes > settings.max_upload_bytes:
        mb = round(approx_bytes / 1024 / 1024, 2)
        raise HTTPException(
            status_code=413,
            detail=(
                f"{label} 过大（约 {mb}MB，最大允许 {settings.max_upload_size_mb}MB），"
                "请更换更小的图片或改用公网 URL 方式。"
            ),
        )


@router.post("/videos", response_model=VideoTaskCreatedResponse, summary="创建视频生成任务")
async def create_video_task(
    req: VideoGenerationRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """
    创建视频生成异步任务。
    - 必须登录，未登录返回 401
    - 积分不足返回 402
    - text2video：只传 prompt
    - image2video: 传 image（单张）或 images（多张参考图，自动识别）
    - keyframes: 传 images 数组（1-2 张，起始帧+结束帧）
    """
    if not agnes_client.api_key or agnes_client.api_key.startswith("sk-your"):
        raise HTTPException(
            status_code=401,
            detail="Agnes AI API Key 未配置，请在前端「配置管理」页面添加 Provider",
        )

    # ---------- 参考图 size 校验 + 类型日志（便于排查本地图/URL 是否混传）----------
    if req.mode == "image2video" and req.images:
        for idx, img in enumerate(req.images):
            if not img:
                continue
            _validate_image_size(img, f"images[{idx}]")
            logger.info(
                "[视频生成][image2video] images[%d]: type=%s, length=%d, mime=%s, preview=%s",
                idx,
                _classify_image(img),
                len(img),
                (req.image_mime_types[idx] if req.image_mime_types and idx < len(req.image_mime_types) else "image/png"),
                img[:100],
            )
    if req.mode == "keyframes" and req.images:
        for idx, img in enumerate(req.images):
            if not img:
                continue
            _validate_image_size(img, f"images[{idx}]")
            logger.info(
                "[视频生成][keyframes] images[%d]: type=%s, length=%d, mime=%s, preview=%s",
                idx,
                _classify_image(img),
                len(img),
                (req.image_mime_types[idx] if req.image_mime_types and idx < len(req.image_mime_types) else "image/png"),
                img[:100],
            )

    # --- 计算并预扣积分（必须登录，积分不足会抛 402）---
    # 视频任务的 task_id 由 Agnes AI 返回，无法预先生成，先用临时 ref_id 扣分
    # 拿到真实 task_id 后更新流水的 ref_id；若 Agnes 调用失败则退还预扣积分

    # ===== 严格内容安全模式：生成前拦截敏感词 =====
    if getattr(current_user, "content_safety_strict", False) and req.prompt:
        from app.services.moderation_service import check_sensitive_text
        hit, hit_words = await check_sensitive_text(db, req.prompt)
        if hit:
            raise HTTPException(
                status_code=403,
                detail=f"内容包含敏感词，无法生成：{', '.join(hit_words[:5])}",
            )

    cost = await get_video_cost_async(db, mode=req.mode, seconds=req.seconds or 5, num_frames=req.num_frames)
    import uuid as _uuid
    _pending_ref_id = f"pending_{_uuid.uuid4().hex}"
    await consume_credits(
        db, current_user, cost,
        description=f"video/{req.mode}/{req.seconds}s",
        ref_type="video",
        ref_id=_pending_ref_id,
    )
    user_id = current_user.id

    # 摄像机参数拼接：若 camera_params.enabled=True，追加到 prompt 末尾
    prompt = req.prompt or ""
    if (
        req.camera_params
        and isinstance(req.camera_params, dict)
        and req.camera_params.get("enabled")
    ):
        from app.services.camera_prompt import build_camera_prompt_suffix
        suffix = build_camera_prompt_suffix(req.camera_params)
        if suffix:
            prompt = prompt + suffix

    try:
        client = await provider_registry.get_client_for_model(req.model)
        result = await client.create_video_task(
            prompt=prompt,
            model=req.model,
            num_frames=req.num_frames,
            frame_rate=req.frame_rate,
            width=req.width,
            height=req.height,
            aspect_ratio=req.aspect_ratio,
            seconds=req.seconds,
            negative_prompt=req.negative_prompt,
            mode=req.mode,
            image=req.image,
            images=req.images,
            image_mime_type=req.image_mime_type,
            image_mime_types=req.image_mime_types,
            seed=req.seed,
        )
    except Exception as e:
        logger.exception("[视频生成] 创建任务失败（上游 Agnes 响应异常）: %s", e)
        # Agnes 调用失败：退还预扣的积分
        try:
            from app.services.credits_service import refund_credits
            async with new_async_session() as session:
                await refund_credits(
                    session, user_id, _pending_ref_id,
                    reason=f"视频任务创建失败：{str(e)[:200]}",
                )
        except Exception as refund_err:
            logger.error("[视频生成] 退还预扣积分失败: %s", refund_err)
        raise HTTPException(status_code=502, detail=str(e))

    result_data = result.get("data")
    if isinstance(result_data, list) and result_data:
        first_result = result_data[0]
    elif isinstance(result_data, dict):
        first_result = result_data
    else:
        first_result = {}

    video_id = result.get("video_id") or (
        first_result.get("video_id") if isinstance(first_result, dict) else None
    )
    task_id = (
        result.get("task_id")
        or result.get("id")
        or (first_result.get("task_id") if isinstance(first_result, dict) else None)
        or (first_result.get("id") if isinstance(first_result, dict) else None)
    )

    if not video_id and not task_id:
        # 拿不到 task_id 也视为失败：退还预扣积分
        try:
            from app.services.credits_service import refund_credits
            async with new_async_session() as session:
                await refund_credits(
                    session, user_id, _pending_ref_id,
                    reason="视频任务创建失败：Agnes AI 未返回 task_id",
                )
        except Exception as refund_err:
            logger.error("[视频生成] 退还预扣积分失败: %s", refund_err)
        raise HTTPException(
            status_code=502,
            detail=f"Agnes AI 返回的数据中未找到 video_id 或 task_id: {str(result)[:200]}",
        )

    logger.info("[视频生成] 任务创建成功: video_id=%s task_id=%s", video_id, task_id)

    # 拿到真实 task_id 后，更新积分流水的 ref_id（从临时 _pending_ref_id 改为真实 task_id）
    # 这样后续 poller 的 confirm/refund 才能匹配到对应的预扣流水
    real_ref_id = task_id or video_id
    if real_ref_id != _pending_ref_id:
        from app.models.credit_transaction import CreditTransaction
        from sqlalchemy import update as sa_update
        stmt = (
            sa_update(CreditTransaction)
            .where(CreditTransaction.user_id == user_id)
            .where(CreditTransaction.ref_id == _pending_ref_id)
            .where(CreditTransaction.status == "pending")
            .values(ref_id=real_ref_id)
        )
        await db.execute(stmt)
        await db.commit()

    # 启动后台轮询协程（独立 Task，不阻塞当前请求返回）
    params = {
        "model": req.model,
        "aspect_ratio": req.aspect_ratio,
        "seconds": req.seconds,
        "num_frames": req.num_frames,
        "frame_rate": req.frame_rate,
        "width": req.width,
        "height": req.height,
        "negative_prompt": req.negative_prompt,
        "mode": req.mode,
        "seed": req.seed,
        "is_public": req.is_public,
    }
    await poller_manager.start_polling(
        task_id=task_id,
        video_id=video_id,
        prompt=prompt,
        params=params,
        user_id=user_id,
        credits_consumed=cost,
        preset_id=req.preset_id,
    )

    return VideoTaskCreatedResponse(
        task_id=task_id,
        video_id=video_id,
        status="pending",
        prompt=prompt,
        model=req.model,
        num_frames=req.num_frames,
        frame_rate=req.frame_rate,
        width=req.width,
        height=req.height,
        aspect_ratio=req.aspect_ratio,
        seconds=req.seconds,
        mode=req.mode,
        credits_consumed=cost,
        remaining_credits=current_user.credits,
        message="任务已创建，请轮询 GET /api/videos/{task_id} 获取最新状态",
    )


@router.get("/videos/{task_id}", response_model=VideoStatusResponse, summary="查询视频任务状态")
async def get_video_status(
    task_id: str,
    db: AsyncSession = Depends(get_async_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """
    查询视频任务状态（按用户隔离）。
    优先从后端内存缓存获取（实时状态），缓存中不存在则回退查询数据库。
    """
    # 方式 1：从内存缓存查询（并发安全
    cached_task = await poller_manager.get_status(task_id=task_id)
    if not cached_task:
        cached_task = await poller_manager.get_status(video_id=task_id)

    # --- 用户隔离检查（内存缓存）---
    if cached_task is not None:
        if current_user is None and cached_task.user_id is not None:
            cached_task = None
        elif current_user is not None and cached_task.user_id != current_user.id:
            cached_task = None

    if cached_task:
        return VideoStatusResponse(
            task_id=cached_task.task_id,
            video_id=cached_task.video_id,
            status=cached_task.status,
            progress=cached_task.progress,
            video_url=cached_task.video_url,
            message=cached_task.error_message,
            elapsed_sec=cached_task.to_dict()["elapsed_sec"],
        )

    # 方式 2：从数据库查询已完成的记录（按用户隔离）
    stmt = select(Generation).filter(
        (Generation.task_id == task_id) & (Generation.type == "video")
    )
    if current_user:
        stmt = stmt.filter(Generation.user_id == current_user.id)
    else:
        stmt = stmt.filter(Generation.user_id.is_(None))
    result = await db.execute(stmt)
    record = result.scalar_one_or_none()

    if record:
        return VideoStatusResponse(
            task_id=record.task_id,
            status=record.status,
            progress=100 if record.status == "success" else 0,
            video_url=record.result_url,
            message=None if record.status == "success" else "任务已完成",
            elapsed_sec=0,
        )

    raise HTTPException(
        status_code=404,
        detail=f"未找到视频任务（ID: {task_id}），可能尚未创建或已过期",
    )


@router.delete("/videos/{task_id}", summary="中止视频任务")
async def cancel_video_task(
    task_id: str,
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """
    中止指定视频任务的后台轮询（按用户隔离，仅允许任务创建者取消）。
    """
    # 先从缓存中检查是否属于当前用户
    cached_task = await poller_manager.get_status(task_id=task_id)
    if cached_task is not None:
        if current_user is None and cached_task.user_id is not None:
            raise HTTPException(status_code=404, detail="任务不存在或无权操作")
        if current_user is not None and cached_task.user_id != current_user.id:
            raise HTTPException(status_code=404, detail="任务不存在或无权操作")

    await poller_manager.cancel(task_id=task_id)
    return {"success": True, "message": f"已尝试中止任务 {task_id}"}


# =====================================================
# 视频流代理接口
# 用途：解决视频生成页面直接播放 Google Storage 视频时的 CORS 问题
# 通过 task_id 查找视频 URL，后端代理转发视频流
# =====================================================


async def _find_video_url_by_task_id(
    task_id: str,
    db: AsyncSession,
    current_user: Optional[User] = None,
) -> str:
    """
    根据 task_id 查找视频 URL（按用户隔离）。
    优先从内存缓存获取（进行中的任务），回退查询数据库（已完成的任务）。
    """
    # 方式 1：从内存缓存查询
    cached_task = await poller_manager.get_status(task_id=task_id)
    if not cached_task:
        cached_task = await poller_manager.get_status(video_id=task_id)

    # 用户隔离检查（内存缓存）
    if cached_task is not None:
        if current_user is None and cached_task.user_id is not None:
            cached_task = None
        elif current_user is not None and cached_task.user_id != current_user.id:
            cached_task = None

    if cached_task and cached_task.video_url:
        return cached_task.video_url

    # 方式 2：从数据库查询（按用户隔离）
    stmt = select(Generation).filter(
        (Generation.task_id == task_id) & (Generation.type == "video")
    )
    if current_user:
        stmt = stmt.filter(Generation.user_id == current_user.id)
    else:
        stmt = stmt.filter(Generation.user_id.is_(None))
    result = await db.execute(stmt)
    record = result.scalar_one_or_none()
    if record and record.result_url:
        return record.result_url

    return ""


@router.get("/videos/{task_id}/stream", summary="视频流代理（支持 Range + CORS）")
async def stream_video_by_task(
    request: Request,
    task_id: str,
    db: AsyncSession = Depends(get_async_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """
    通过 task_id 代理播放视频资源（按用户隔离，解决 CORS 和 Range 请求问题）。
    """
    # 查找视频 URL
    video_url = await _find_video_url_by_task_id(task_id, db, current_user)
    if not video_url:
        raise HTTPException(status_code=404, detail="未找到对应的视频资源")

    range_header = request.headers.get("range", None)

    # 先通过 HEAD 请求获取视频元信息
    content_type = "video/mp4"
    total_size = 0
    head_ok = False
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            head_resp = await client.head(video_url, follow_redirects=True)
            if head_resp.status_code < 400:
                head_ok = True
                content_type = head_resp.headers.get("content-type", "video/mp4")
                content_length_hdr = head_resp.headers.get("content-length")
                content_range_hdr = head_resp.headers.get("content-range")
                if content_length_hdr:
                    total_size = int(content_length_hdr)
                elif content_range_hdr:
                    parts = content_range_hdr.split("/")
                    if len(parts) == 2 and parts[1] != "*":
                        total_size = int(parts[1])
    except Exception:
        pass

    # HEAD 失败时：直接流式转发完整视频
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

    # 解析 Range 请求
    start = 0
    end = total_size - 1

    if range_header:
        try:
            range_spec = range_header.replace("bytes=", "").strip()
            range_parts = range_spec.split("-")
            start = int(range_parts[0]) if range_parts[0] else 0
            end = int(range_parts[1]) if len(range_parts) > 1 and range_parts[1] else total_size - 1
            start = max(0, min(start, total_size - 1))
            end = max(start, min(end, total_size - 1))
        except (ValueError, IndexError):
            start = 0
            end = total_size - 1

    # 构造转发给上游的 Range 请求头
    req_headers = {"User-Agent": "Agnes-Platform-VideoProxy"}
    if range_header:
        req_headers["Range"] = f"bytes={start}-{end}"

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

    # 根据 Range 请求返回 206 或 200
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
