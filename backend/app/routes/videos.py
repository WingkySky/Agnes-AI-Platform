# =====================================================
# 视频生成路由（全异步）
# POST /api/videos       - 创建视频生成任务（立即返回 task_id，后台异步轮询
# GET  /api/videos/{id}  - 查询视频任务状态（前端定时轮询此接口
# DELETE /api/videos/{id}- 中止视频任务
#
# 关键设计：
#   - 视频创建后立即返回 task_id，不阻塞后续请求
#   - 视频轮询在独立的 asyncio.Task 中进行，不影响图片生成任务
#   - 图片/视频/历史三个路由模块**互不阻塞**
# =====================================================

import logging

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.database import get_async_db
from app.core.config import settings
from app.models.generation import Generation
from app.schemas.videos import (
    VideoGenerationRequest,
    VideoTaskCreatedResponse,
    VideoStatusResponse,
)
from app.services.agnes_client import agnes_client
from app.services.video_poller import poller_manager

logger = logging.getLogger("agnes_platform")
router = APIRouter()


@router.post("/videos", response_model=VideoTaskCreatedResponse, summary="创建视频生成任务")
async def create_video_task(req: VideoGenerationRequest):
    """
    创建视频生成异步任务。
    返回 task_id/video_id，前端可立即释放，不阻塞用户操作。
    实际视频生成轮询在后台独立 asyncio.Task 中运行，不影响其他请求。
    """
    if not settings.agnes_api_key or settings.agnes_api_key.startswith("sk-your"):
        raise HTTPException(
            status_code=401,
            detail="Agnes AI API Key 未配置，请在 backend/.env 中设置 AGNES_API_KEY",
        )

    try:
        result = await agnes_client.create_video_task(
            prompt=req.prompt,
            model=req.model,
            num_frames=req.num_frames,
            frame_rate=req.frame_rate,
            width=req.width,
            height=req.height,
            negative_prompt=req.negative_prompt,
            mode=req.mode,
            image=req.image,
            images=req.images,
            seed=req.seed,
        )
    except Exception as e:
        logger.error("[视频生成] 创建任务失败: %s", e)
        raise HTTPException(status_code=502, detail=str(e))

    video_id = result.get("video_id") or (
        result.get("data").get("video_id") if isinstance(result.get("data"), dict) else None
    )
    task_id = (
        result.get("task_id")
        or result.get("id")
        or (result.get("data").get("task_id") if isinstance(result.get("data"), dict) else None)
        or (result.get("data").get("id") if isinstance(result.get("data"), dict) else None)
    )

    if not video_id and not task_id:
        raise HTTPException(
            status_code=502,
            detail=f"Agnes AI 返回的数据中未找到 video_id 或 task_id: {str(result)[:200]}",
        )

    logger.info("[视频生成] 任务创建成功: video_id=%s task_id=%s", video_id, task_id)

    # 启动后台轮询协程（独立 Task，不阻塞当前请求返回）
    params = {
        "model": req.model,
        "num_frames": req.num_frames,
        "frame_rate": req.frame_rate,
        "width": req.width,
        "height": req.height,
        "negative_prompt": req.negative_prompt,
        "mode": req.mode,
        "seed": req.seed,
    }
    await poller_manager.start_polling(
        task_id=task_id,
        video_id=video_id,
        prompt=req.prompt,
        params=params,
    )

    return VideoTaskCreatedResponse(
        task_id=task_id,
        video_id=video_id,
        status="pending",
        prompt=req.prompt,
        model=req.model,
        num_frames=req.num_frames,
        frame_rate=req.frame_rate,
        width=req.width,
        height=req.height,
        mode=req.mode,
        message="任务已创建，请轮询 GET /api/videos/{task_id} 获取最新状态",
    )


@router.get("/videos/{task_id}", response_model=VideoStatusResponse, summary="查询视频任务状态")
async def get_video_status(task_id: str, db: AsyncSession = Depends(get_async_db)):
    """
    查询视频任务状态。
    优先从后端内存缓存获取（实时状态），缓存中不存在则回退查询数据库。
    """
    # 方式 1：从内存缓存查询（并发安全
    cached_task = await poller_manager.get_status(task_id=task_id)
    if not cached_task:
        cached_task = await poller_manager.get_status(video_id=task_id)

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

    # 方式 2：从数据库查询已完成的记录（异步查询，不阻塞事件循环）
    result = await db.execute(
        select(Generation).filter(
            (Generation.task_id == task_id) & (Generation.type == "video")
        )
    )
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
async def cancel_video_task(task_id: str):
    """
    中止指定视频任务的后台轮询（仅停止本地轮询，不保证服务端已终止）。
    """
    await poller_manager.cancel(task_id=task_id)
    return {"success": True, "message": f"已尝试中止任务 {task_id}"}
