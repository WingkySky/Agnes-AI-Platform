# =====================================================
# 图片生成路由（全异步）
# POST /api/images/generations - 创建图片生成任务（同步等待 Agnes AI 返回
# GET  /api/images/{id}        - 获取单张图片生成记录
#
# 关键设计：
#   - 所有路由函数为 async def，数据库操作使用 AsyncSession
#   - 图片生成任务同步等待 Agnes AI，不会阻塞事件循环（await）
#   - 与视频任务（videos.py）在独立的 asyncio.Task 中运行，互不干扰
# =====================================================

import logging
from datetime import datetime

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.database import get_async_db
from app.core.config import settings
from app.models.generation import Generation
from app.schemas.images import ImageGenerationRequest, ImageGenerationResponse, ImageRecordResponse
from app.services.agnes_client import agnes_client

logger = logging.getLogger("agnes_platform")
router = APIRouter()


@router.post("/images/generations", response_model=ImageGenerationResponse, summary="生成图片")
async def create_image_generation(req: ImageGenerationRequest, db: AsyncSession = Depends(get_async_db)):
    """
    图片生成接口（异步，不会阻塞事件循环）。
    流程：校验 API Key → 调用 Agnes AI → 解析结果 → 异步写入数据库 → 返回结果
    """
    # ---------- 1. API Key 检查 ----------
    if not settings.agnes_api_key or settings.agnes_api_key.startswith("sk-your"):
        raise HTTPException(
            status_code=401,
            detail="Agnes AI API Key 未配置，请在 backend/.env 中设置 AGNES_API_KEY",
        )

    # ---------- 2. 图片大小校验 ----------
    if req.base64_image:
        estimated_bytes = len(req.base64_image) * 3 / 4
        if estimated_bytes > settings.max_upload_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"图片过大，最大允许 {settings.max_upload_size_mb}MB",
            )

    # ---------- 3. 异步调用 Agnes AI（await，不阻塞事件循环）----------
    try:
        result = await agnes_client.create_image(
            prompt=req.prompt,
            model=req.model,
            size=req.size,
            response_format=req.response_format,
            base64_image=req.base64_image,
        )
    except Exception as e:
        logger.error("[图片生成] Agnes AI 调用失败: %s", e)
        raise HTTPException(status_code=502, detail=str(e))

    # ---------- 4. 解析结果 ----------
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

    # ---------- 5. 异步写入数据库（AsyncSession，不阻塞事件循环）----------
    record_id = None
    try:
        params = {
            "size": req.size,
            "response_format": req.response_format,
            "mode": "image2image" if req.base64_image else "text2image",
        }
        record = Generation(
            type="image",
            prompt=req.prompt,
            model=req.model,
            params=params,
            image_input=req.base64_image[:512] + "..." if req.base64_image and len(req.base64_image) > 512 else None,
            result_url=output_url or "(base64)",
            status="success",
        )
        db.add(record)
        await db.commit()
        await db.refresh(record)
        record_id = record.id
        logger.info("[图片生成] 记录已异步写入数据库: id=%s", record_id)
    except Exception as e:
        logger.warning("[图片生成] 写入历史失败: %s", e)

    # ---------- 6. 返回结果 ----------
    return ImageGenerationResponse(
        id=record_id,
        status="success",
        url=output_url,
        b64_json=output_b64,
        model=req.model,
        prompt=req.prompt,
        size=req.size,
        created_at=datetime.utcnow().isoformat(),
    )


@router.get("/images/{image_id}", response_model=ImageRecordResponse, summary="获取单张图片记录")
async def get_image_record(image_id: int, db: AsyncSession = Depends(get_async_db)):
    """
    根据 ID 获取单条图片生成记录（异步查询，不阻塞事件循环）。
    """
    result = await db.execute(
        select(Generation).filter(
            Generation.id == image_id,
            Generation.type == "image",
        )
    )
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
        created_at=record.created_at.isoformat() if record.created_at else None,
    )
