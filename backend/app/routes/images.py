# =====================================================
# 图片生成路由（支持异步任务模式）
# POST /api/images/tasks        - 创建异步图片任务（登录用户扣除积分）
# GET  /api/images/tasks/{id}   - 查询异步任务状态
# POST /api/images/generations  - 同步生成（向后兼容，已不推荐）
# GET  /api/images/{id}         - 获取单张图片历史记录
#
# 关键设计：
#   - 必须登录，未登录返回 401
#   - 积分不足时返回 402（由 credits_service.consume_credits 抛出）
#   - user_id / credits_consumed 写入 generations 表
# =====================================================

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.database import get_async_db
from app.core.security import get_current_user, get_current_user_optional
from app.models.generation import Generation
from app.models.user import User
from app.schemas.images import ImageGenerationRequest, ImageGenerationResponse, ImageRecordResponse
from app.services.agnes_client import agnes_client
from app.services.credits_service import consume_credits, get_image_cost_async
from app.services.image_poller import image_poller_manager

logger = logging.getLogger("agnes_platform")
router = APIRouter()


# =====================================================
# 【异步任务模式】—— 推荐使用
# =====================================================
@router.post("/images/tasks", summary="创建图片异步生成任务")
async def create_image_task_async(
    req: ImageGenerationRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """
    创建图片异步生成任务，立即返回 task_id。

    - 必须登录，未登录返回 401
    - 积分不足返回 402（由 consume_credits 抛出）
    - user_id / credits_consumed 写入 generations 表
    """
    # API Key 检查（从 agnes_client 读取当前配置，Provider 可能在前端配置页修改）
    if not agnes_client.api_key or agnes_client.api_key.startswith("sk-your"):
        raise HTTPException(
            status_code=401,
            detail="Agnes AI API Key 未配置，请在前端「配置管理」页面添加 Provider",
        )

    # 参数校验（确保 size 格式正确）
    try:
        size = req.size or "1024x1024"
        if "x" in size.lower():
            parts = size.lower().split("x")
            int(parts[0])
            int(parts[1])
    except Exception:
        raise HTTPException(status_code=400, detail="尺寸格式错误，应为 '宽x高'，如 '1024x1024'")

    mode = "image2image" if req.is_image_to_image else "text2image"

    # ===== 严格内容安全模式：生成前拦截敏感词 =====
    if getattr(current_user, "content_safety_strict", False) and req.prompt:
        from app.services.moderation_service import check_sensitive_text
        hit, hit_words = await check_sensitive_text(db, req.prompt)
        if hit:
            raise HTTPException(
                status_code=403,
                detail=f"内容包含敏感词，无法生成：{', '.join(hit_words[:5])}",
            )

    # --- 计算本次任务需要消耗的积分 ---
    cost = await get_image_cost_async(db, mode=mode, size=size)

    # --- 必须登录：先预扣积分再发起生成（积分不足会抛 402）---
    # 预先生成 task_id，作为积分流水的 ref_id，确保后续 confirm/refund 能匹配到
    import time as _time
    import uuid as _uuid
    task_id = f"img_{int(_time.time() * 1000)}_{_uuid.uuid4().hex[:8]}"
    await consume_credits(
        db, current_user, cost,
        description=f"image/{mode}/{size}",
        ref_type="image",
        ref_id=task_id,
    )

    # 【多图参考改造点】合并 all_reference_images，区分 URL 和 base64
    params = {
        "model": req.model,
        "size": size,
        "response_format": req.response_format,
        "mode": mode,
        "is_public": req.is_public,
    }

    if req.is_image_to_image:
        ref_imgs = req.all_reference_images
        b64_imgs = [img for img in ref_imgs if not img.strip().lower().startswith("http")]
        url_imgs = [img.strip() for img in ref_imgs if img.strip().lower().startswith("http")]
        if b64_imgs:
            params["base64_images"] = b64_imgs
        if url_imgs:
            params["image_urls"] = url_imgs
        if req.mask and req.mask.strip():
            params["mask"] = req.mask
        logger.info(
            "[图片API] 异步图生图任务创建: ref_images=%d 张 (b64=%d, url=%d), mask=%s, size=%s, model=%s",
            len(ref_imgs), len(b64_imgs), len(url_imgs), "yes" if req.mask and req.mask.strip() else "no", size, req.model,
        )

    task = await image_poller_manager.create_task(
        prompt=req.prompt,
        params=params,
        user_id=current_user.id,
        credits_consumed=cost,
        task_id=task_id,
    )

    logger.info("[图片生成] 异步任务已创建: task_id=%s user=%s cost=%d", task.task_id, current_user.username, cost)

    return {
        "task_id": task.task_id,
        "id": task.task_id,
        "status": "pending",
        "prompt": req.prompt,
        "model": req.model,
        "size": size,
        "credits_consumed": cost,
        "remaining_credits": current_user.credits,
        "created_at": datetime.utcnow().isoformat(),
        "message": "任务已创建，请使用 GET /api/images/tasks/{task_id} 轮询状态",
    }


@router.get("/images/tasks/{task_id}", summary="查询图片异步任务状态")
async def get_image_task_status(
    task_id: str,
    db: AsyncSession = Depends(get_async_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """查询图片任务状态（按用户隔离），前端用于轮询"""
    task = await image_poller_manager.get_status(task_id)

    # --- 内存缓存的用户隔离检查 ---
    if task is not None:
        if current_user is None and task.user_id is not None:
            task = None
        elif current_user is not None and task.user_id != current_user.id:
            task = None

    if not task:
        # 不在缓存中，尝试从数据库查询已完成的任务（按用户隔离）
        try:
            stmt = select(Generation).filter(
                Generation.task_id == task_id,
                Generation.type == "image",
            )
            if current_user:
                stmt = stmt.filter(Generation.user_id == current_user.id)
            else:
                stmt = stmt.filter(Generation.user_id.is_(None))
            result = await db.execute(stmt)
            record = result.scalar_one_or_none()
            if record:
                return {
                    "task_id": task_id,
                    "status": record.status,
                    "progress": 100 if record.status == "success" else 0,
                    "result_url": record.result_url,
                    "url": record.result_url,
                    "credits_consumed": record.credits_consumed,
                    "elapsed_sec": 0,
                }
        except Exception as e:
            logger.warning("[图片生成] 数据库查询失败: %s", e)

        raise HTTPException(
            status_code=404,
            detail=f"未找到任务（ID: {task_id}），可能已过期或不存在",
        )

    return task.to_dict()


@router.delete("/images/tasks/{task_id}", summary="取消图片异步任务")
async def cancel_image_task(
    task_id: str,
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """取消指定图片任务（按用户隔离，仅允许任务创建者取消）"""
    task = await image_poller_manager.get_status(task_id)
    if task is not None:
        if current_user is None and task.user_id is not None:
            raise HTTPException(status_code=404, detail="任务不存在或无权操作")
        if current_user is not None and task.user_id != current_user.id:
            raise HTTPException(status_code=404, detail="任务不存在或无权操作")

    await image_poller_manager.cancel(task_id)
    return {
        "success": True,
        "task_id": task_id,
        "status": "cancelled",
        "message": f"已尝试取消任务 {task_id}",
    }


# =====================================================
# 【同步模式】—— 向后兼容
# =====================================================
@router.post("/images/generations", response_model=ImageGenerationResponse, summary="同步生成图片（向后兼容）")
async def create_image_generation(
    req: ImageGenerationRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """
    同步图片生成接口（保留以向后兼容）。新代码建议使用异步任务模式（POST /images/tasks）。
    - 必须登录，未登录返回 401
    - 积分不足返回 402
    """
    if not agnes_client.api_key or agnes_client.api_key.startswith("sk-your"):
        raise HTTPException(
            status_code=401,
            detail="Agnes AI API Key 未配置，请在前端「配置管理」页面添加 Provider",
        )

    # 参考图大小校验
    if req.is_image_to_image:
        total_bytes = 0
        for img in req.all_reference_images:
            if not img.strip().lower().startswith("http"):
                pure_b64 = img.split(",")[-1] if "," in img else img
                total_bytes += len(pure_b64) * 3 / 4
        if total_bytes > settings.max_upload_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"参考图总大小过大，最大允许 {settings.max_upload_size_mb}MB",
            )

    # --- 计算并扣除积分（必须登录，积分不足会抛 402）---
    mode = "image2image" if req.is_image_to_image else "text2image"
    size = req.size or "1024x1024"

    # ===== 严格内容安全模式：生成前拦截敏感词 =====
    if getattr(current_user, "content_safety_strict", False) and req.prompt:
        from app.services.moderation_service import check_sensitive_text
        hit, hit_words = await check_sensitive_text(db, req.prompt)
        if hit:
            raise HTTPException(
                status_code=403,
                detail=f"内容包含敏感词，无法生成：{', '.join(hit_words[:5])}",
            )

    cost = await get_image_cost_async(db, mode=mode, size=size)
    await consume_credits(db, current_user, cost, description=f"image/{mode}/{size}")

    # 调用 Agnes AI
    try:
        ref_imgs = req.all_reference_images
        b64_imgs = [img for img in ref_imgs if not img.strip().lower().startswith("http")]
        url_imgs = [img.strip() for img in ref_imgs if img.strip().lower().startswith("http")]
        result = await agnes_client.create_image(
            prompt=req.prompt,
            model=req.model,
            size=size,
            response_format=req.response_format,
            base64_images=b64_imgs or None,
            image_urls=url_imgs or None,
            mask=req.mask,
        )
    except Exception as e:
        logger.error("[图片生成] Agnes AI 调用失败: %s", e)
        raise HTTPException(status_code=502, detail=str(e))

    # 解析结果
    output_url = None
    output_b64 = None
    try:
        data = result.get("data", [])
        if isinstance(data, list) and len(data) > 0:
            output_url = data[0].get("url")
            output_b64 = data[0].get("b64_json")
        if not output_url and isinstance(result.get("url"), str):
            output_url = result["url"]
        if not output_url and result.get("image"):
            output_url = result["image"]
    except Exception as e:
        logger.error("[图片生成] 结果解析异常: %s", e)

    if not output_url and not output_b64:
        raise HTTPException(
            status_code=502,
            detail=f"Agnes AI 返回异常，未找到图片数据: {str(result)[:200]}",
        )

    # 写入数据库
    try:
        record = Generation(
            type="image",
            user_id=current_user.id,
            prompt=req.prompt,
            model=req.model,
            params={"size": size, "response_format": req.response_format, "mode": mode},
            mode=mode,
            result_url=output_url or "(base64)",
            status="success",
            credits_consumed=cost,
        )
        db.add(record)
        await db.commit()
        await db.refresh(record)
        logger.info("[图片生成] 同步模式记录已写入: id=%s user=%s cost=%d", record.id, current_user.username, cost)
    except Exception as e:
        logger.warning("[图片生成] 写入历史失败: %s", e)

    return ImageGenerationResponse(
        id=record.id if record else 0,
        status="success",
        url=output_url,
        b64_json=output_b64,
        model=req.model,
        prompt=req.prompt,
        size=size,
        created_at=datetime.utcnow().isoformat(),
        credits_consumed=cost,
        remaining_credits=current_user.credits,
    )


@router.get("/images/{image_id}", response_model=ImageRecordResponse, summary="获取单张图片记录")
async def get_image_record(
    image_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """根据 ID 获取单张图片生成历史记录（按用户隔离）"""
    stmt = select(Generation).filter(
        Generation.id == image_id,
        Generation.type == "image",
    )
    if current_user:
        stmt = stmt.filter(Generation.user_id == current_user.id)
    else:
        stmt = stmt.filter(Generation.user_id.is_(None))
    result = await db.execute(stmt)
    record = result.scalar_one_or_none()

    if not record:
        raise HTTPException(status_code=404, detail="未找到对应图片记录")

    return ImageRecordResponse(
        id=record.id,
        type="image",
        prompt=record.prompt,
        model=record.model,
        params=record.params,
        result_url=record.result_url,
        status=record.status,
        credits_consumed=record.credits_consumed,
        created_at=record.created_at.isoformat() if record.created_at else None,
    )


# 向后兼容引用 settings（避免未使用 lint）
from app.core.config import settings
