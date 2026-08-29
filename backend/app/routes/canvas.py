# =====================================================
# 无限画布路由 — 三节点执行链路（tts / subtitle / compose）
#
# 设计（spec: 2026-08-29-final-cut-pipeline-design M3）:
#   - 无状态、按节点 content 传参，不建表；产物经 /uploads 静态访问
#   - POST /api/canvas/tts      文本 → 配音音频
#   - POST /api/canvas/subtitle 文本 → SRT 字幕
#   - POST /api/canvas/compose  多段视频（+配音/字幕）→ 成片
# =====================================================

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_db
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.canvas import (
    CanvasTtsRequest,
    CanvasTtsResponse,
    CanvasSubtitleRequest,
    CanvasSubtitleResponse,
    CanvasComposeRequest,
    CanvasComposeResponse,
)
from app.services import canvas_media_service

router = APIRouter(prefix="/canvas", tags=["无限画布"])


@router.post("/tts", response_model=CanvasTtsResponse, summary="画布文本生成配音")
async def canvas_tts(
    payload: CanvasTtsRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return await canvas_media_service.generate_tts(payload.text, payload.voice, payload.speed)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/subtitle", response_model=CanvasSubtitleResponse, summary="画布文本生成 SRT 字幕")
async def canvas_subtitle(
    payload: CanvasSubtitleRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return await canvas_media_service.generate_subtitles(payload.text, payload.max_chars)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/compose", response_model=CanvasComposeResponse, summary="画布多段视频合成成片")
async def canvas_compose(
    payload: CanvasComposeRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return await canvas_media_service.compose_videos(
            video_urls=payload.video_urls,
            audio_url=payload.audio_url,
            subtitles=[s.model_dump() for s in payload.subtitles] if payload.subtitles else None,
            with_subtitle=payload.with_subtitle,
            bgm_id=payload.bgm_id,
            aspect_ratio=payload.aspect_ratio,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))
