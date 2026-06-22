# =====================================================
# 用户偏好设置路由
#
# GET    /api/preferences          获取当前用户的全部偏好设置
# PUT    /api/preferences          全量更新偏好设置（覆盖）
# PATCH  /api/preferences          部分更新偏好设置（合并）
# DELETE /api/preferences          重置为默认偏好设置
# =====================================================

import copy
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.database import get_async_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.user_preference import UserPreference, DEFAULT_PREFERENCES
from sqlalchemy.future import select

logger = logging.getLogger("agnes_platform")
router = APIRouter(prefix="/preferences", tags=["用户偏好设置"])


# =====================================================
# Schema 定义
# =====================================================

class PreferencesResponse(BaseModel):
    """GET 返回结构"""
    user_id: int
    preferences: dict
    updated_at: str | None


class PreferencesUpdateRequest(BaseModel):
    """PUT（全量更新）请求结构：传完整的 preferences 对象"""
    preferences: dict


class PreferencesPatchRequest(BaseModel):
    """PATCH（部分更新）请求结构：只传需要修改的 key，支持深层合并"""
    preferences: dict


class MessageResponse(BaseModel):
    """通用消息响应"""
    message: str


# =====================================================
# 辅助函数
# =====================================================

async def _get_or_create_preference(db, user_id: int) -> UserPreference:
    """获取用户的偏好记录，不存在则创建默认记录"""
    result = await db.execute(
        select(UserPreference).filter(UserPreference.user_id == user_id)
    )
    pref = result.scalar_one_or_none()
    if pref is None:
        pref = UserPreference(
            user_id=user_id,
            preferences=copy.deepcopy(DEFAULT_PREFERENCES),
        )
        db.add(pref)
        await db.commit()
        await db.refresh(pref)
    return pref


# =====================================================
# 接口实现
# =====================================================

@router.get("", response_model=PreferencesResponse, summary="获取偏好设置")
async def get_preferences(
    current_user: User = Depends(get_current_user),
    db=Depends(get_async_db),
):
    """
    获取当前登录用户的全部偏好设置。
    若用户从未设置过偏好（数据库无记录），自动创建一条默认记录。
    """
    pref = await _get_or_create_preference(db, current_user.id)
    return PreferencesResponse(
        user_id=pref.user_id,
        preferences=pref.preferences,
        updated_at=pref.updated_at.isoformat() if pref.updated_at else None,
    )


@router.put("", response_model=PreferencesResponse, summary="全量更新偏好设置")
async def update_preferences(
    req: PreferencesUpdateRequest,
    current_user: User = Depends(get_current_user),
    db=Depends(get_async_db),
):
    """
    全量更新偏好设置：用 req.preferences 整体覆盖数据库记录。
    通常用于导入他人偏好配置。
    """
    pref = await _get_or_create_preference(db, current_user.id)
    pref.preferences = req.preferences
    await db.commit()
    await db.refresh(pref)
    logger.info("[偏好设置] 用户 %s 全量更新偏好", current_user.username)
    return PreferencesResponse(
        user_id=pref.user_id,
        preferences=pref.preferences,
        updated_at=pref.updated_at.isoformat() if pref.updated_at else None,
    )


@router.patch("", response_model=PreferencesResponse, summary="部分更新偏好设置")
async def patch_preferences(
    req: PreferencesPatchRequest,
    current_user: User = Depends(get_current_user),
    db=Depends(get_async_db),
):
    """
    部分更新偏好设置：对 req.preferences 做深度合并。
    - 只传 {"generation": {"default_model_id": "xxx"}}，其他 generation 字段不受影响
    - 新增的 category / key 会被创建
    - 传 null 可删除某个值（等效于恢复默认值）
    """
    pref = await _get_or_create_preference(db, current_user.id)

    def deep_merge(base: dict, patch: dict) -> dict:
        """深度合并两字典，返回新字典（不修改原对象）"""
        result = copy.deepcopy(base)
        for k, v in patch.items():
            if v is None:
                result.pop(k, None)
            elif isinstance(v, dict) and k in result and isinstance(result[k], dict):
                result[k] = deep_merge(result[k], v)
            else:
                result[k] = v
        return result

    pref.preferences = deep_merge(pref.preferences, req.preferences)
    await db.commit()
    await db.refresh(pref)
    logger.info("[偏好设置] 用户 %s 部分更新偏好", current_user.username)
    return PreferencesResponse(
        user_id=pref.user_id,
        preferences=pref.preferences,
        updated_at=pref.updated_at.isoformat() if pref.updated_at else None,
    )


@router.delete("", response_model=PreferencesResponse, summary="重置为默认偏好")
async def reset_preferences(
    current_user: User = Depends(get_current_user),
    db=Depends(get_async_db),
):
    """
    重置所有偏好设置为默认值。
    """
    pref = await _get_or_create_preference(db, current_user.id)
    pref.preferences = copy.deepcopy(DEFAULT_PREFERENCES)
    await db.commit()
    await db.refresh(pref)
    logger.info("[偏好设置] 用户 %s 重置为默认偏好", current_user.username)
    return PreferencesResponse(
        user_id=pref.user_id,
        preferences=pref.preferences,
        updated_at=pref.updated_at.isoformat() if pref.updated_at else None,
    )
