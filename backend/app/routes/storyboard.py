# =====================================================
# 分镜脚本生成路由（无限画布 script 节点）
# - POST /api/storyboard：剧情 + 角色 → 结构化分镜数组
# =====================================================

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.security import get_current_user_optional
from app.models.user import User
from app.schemas.storyboard import StoryboardRequest
from app.services import storyboard_service

router = APIRouter(prefix="/storyboard", tags=["分镜脚本"])


class StoryboardResponse(BaseModel):
    """统一响应结构"""
    status: str
    message: str
    data: Optional[dict] = Field(None, description="{ shots: [...], assets: { characters: [...], scenes: [...] } }")


@router.post("", response_model=StoryboardResponse, summary="生成分镜脚本")
async def generate_storyboard(
    req: StoryboardRequest,
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """剧情概述 + 角色/场景设定 → 分镜数组 + 全剧资产清单（无状态，不存储）"""
    try:
        result = await storyboard_service.generate_storyboard(req)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"分镜脚本生成失败: {e}")
    return StoryboardResponse(
        status="success",
        message="ok",
        data={
            "shots": [s.model_dump() for s in result.shots],
            "assets": result.assets.model_dump(),
        },
    )
