# =====================================================
# 菜单配置路由
#
# 设计理念：
#   - 菜单元数据（名称、图标、路径）在前端内置，不存储在后端
#   - 后端只存储配置：是否显示、位置（顶部/侧边栏/隐藏）、分组、排序
#   - GET  /api/menu-configs           获取当前菜单配置（所有用户可访问）
#   - POST /api/admin/menu-configs     保存菜单配置（仅管理员）
#   - POST /api/admin/menu-configs/reset 重置为默认配置（仅管理员）
# =====================================================

import logging
from typing import List, Literal, Optional
from pydantic import BaseModel, Field

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_db
from app.core.security import get_current_admin_user, get_current_user_optional
from app.models.user import User
from app.services import menu_service

logger = logging.getLogger("agnes_platform")
router = APIRouter(tags=["菜单配置"])


# ---------- 请求/响应模型 ----------

class MenuItemConfigItem(BaseModel):
    """单个菜单项配置"""
    key: str = Field(..., description="菜单唯一标识（前端内置）")
    show_in_top: bool = Field(..., description="是否在顶部导航显示")
    show_in_sidebar: bool = Field(..., description="是否在侧边栏显示")
    sidebar_group_key: Optional[str] = Field(None, description="侧边栏分组key")
    top_sort_order: int = Field(..., ge=1, description="顶部导航排序序号")
    sidebar_sort_order: int = Field(..., ge=1, description="侧边栏排序序号")


class SaveMenuConfigsRequest(BaseModel):
    """保存菜单配置请求"""
    configs: List[MenuItemConfigItem]


class GetMenuConfigsResponse(BaseModel):
    """获取菜单配置响应"""
    configs: List[MenuItemConfigItem]


# ---------- 公开接口（所有用户可访问，用于获取菜单配置） ----------

@router.get("/menu-configs", response_model=GetMenuConfigsResponse, summary="获取当前菜单配置")
async def get_menu_configs(
    db: AsyncSession = Depends(get_async_db),
    _user: Optional[User] = Depends(get_current_user_optional),
):
    """
    获取当前菜单配置。
    如果没有自定义配置，返回空数组，前端会使用内置默认菜单。
    """
    configs = await menu_service.get_menu_configs(db)
    return {"configs": configs}


# ---------- 管理员接口 ----------

@router.post("/admin/menu-configs", summary="[管理员] 保存菜单配置")
async def save_menu_configs(
    req: SaveMenuConfigsRequest,
    db: AsyncSession = Depends(get_async_db),
    admin: User = Depends(get_current_admin_user),
):
    """
    保存菜单配置（全量覆盖）。
    管理员可以配置每个菜单项：是否显示、放顶部还是侧边栏、属于哪个分组、排序顺序。
    """
    # 转换为字典列表存储
    config_dicts = [item.model_dump() for item in req.configs]
    await menu_service.save_menu_configs(db, config_dicts)
    logger.info("[菜单配置] %s 保存了菜单配置，共 %d 项", admin.username, len(config_dicts))
    return {"message": "菜单配置已保存", "count": len(config_dicts)}


@router.post("/admin/menu-configs/reset", summary="[管理员] 重置菜单为默认配置")
async def reset_menu_configs(
    db: AsyncSession = Depends(get_async_db),
    admin: User = Depends(get_current_admin_user),
):
    """重置菜单为系统默认配置（清除自定义配置）"""
    await menu_service.reset_menu_configs(db)
    logger.info("[菜单配置] %s 重置了菜单配置", admin.username)
    return {"message": "菜单配置已重置为默认"}
