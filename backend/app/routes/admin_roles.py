# =====================================================
# 角色管理路由（仅管理员）
#
# GET    /api/admin/roles                 角色列表
# GET    /api/admin/roles/permissions     所有权限点定义（供前端展示）
# POST   /api/admin/roles                 新建角色
# PUT    /api/admin/roles/{name}          修改角色
# DELETE /api/admin/roles/{name}          删除角色（系统内置角色不可删除）
# =====================================================

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.database import get_async_db
from app.core.security import require_permission
from app.models.user import User
from app.models.role import Role, DEFAULT_ROLES
from app.schemas.role import (
    RoleResponse, RoleCreateRequest, RoleUpdateRequest, PermissionItem,
)

logger = logging.getLogger("agnes_platform")
router = APIRouter(prefix="/admin/roles", tags=["管理员-角色权限"])


# ---------- 权限点定义（供前端展示）----------
# 按模块分组，前端可渲染为树状或分组列表
PERMISSION_DEFS = [
    # 用户与角色
    {"key": "user:manage", "name": "用户管理", "description": "管理用户账号、积分、角色分配", "group": "用户与权限"},
    {"key": "role:manage", "name": "角色管理", "description": "创建/修改/删除角色、配置权限", "group": "用户与权限"},
    {"key": "credit:manage", "name": "积分规则管理", "description": "配置积分消耗与奖励规则", "group": "用户与权限"},
    # 内容审核
    {"key": "plaza:moderate", "name": "广场内容审核", "description": "屏蔽/恢复广场作品、处理举报", "group": "内容审核"},
    {"key": "moderation:config", "name": "审核配置管理", "description": "配置敏感词、审核规则等", "group": "内容审核"},
    # 水印
    {"key": "watermark:manage", "name": "水印配置管理", "description": "配置全局水印样式、为用户开启/关闭水印", "group": "水印设置"},
    # 内容创作
    {"key": "content:generate", "name": "内容生成", "description": "生成图片和视频（普通用户默认拥有）", "group": "内容创作"},
    {"key": "plaza:share", "name": "分享到广场", "description": "将生成的作品分享到广场", "group": "内容创作"},
]


# ---------- 初始化内置角色 ----------
async def ensure_default_roles(db: AsyncSession) -> None:
    """确保系统内置角色存在，启动时调用"""
    for default in DEFAULT_ROLES:
        result = await db.execute(select(Role).filter(Role.name == default["name"]))
        existing = result.scalar_one_or_none()
        if existing:
            # 系统角色：同步权限和显示名（admin 的权限保持全量更新）
            existing.display_name = default["display_name"]
            existing.description = default["description"]
            existing.permissions = default["permissions"]
            existing.is_system = 1
            existing.updated_at = datetime.utcnow()
        else:
            role = Role(
                name=default["name"],
                display_name=default["display_name"],
                description=default["description"],
                permissions=default["permissions"],
                is_system=1,
            )
            db.add(role)
    await db.commit()


# ---------- 角色列表 ----------
@router.get("", response_model=list[RoleResponse], summary="[管理员] 角色列表")
async def list_roles(
    db: AsyncSession = Depends(get_async_db),
    _admin: User = Depends(require_permission("role:manage")),
):
    result = await db.execute(select(Role).order_by(Role.id.asc()))
    roles = result.scalars().all()
    return [RoleResponse(
        id=r.id, name=r.name, display_name=r.display_name,
        description=r.description, permissions=r.permissions or [],
        is_system=bool(r.is_system),
        created_at=r.created_at, updated_at=r.updated_at,
    ) for r in roles]


# ---------- 权限点定义列表 ----------
@router.get("/permissions", response_model=list[PermissionItem], summary="[管理员] 获取所有权限点定义")
async def list_permissions(
    _admin: User = Depends(require_permission("role:manage")),
):
    return [PermissionItem(**p) for p in PERMISSION_DEFS]


# ---------- 新建角色 ----------
@router.post("", response_model=RoleResponse, summary="[管理员] 新建角色")
async def create_role(
    req: RoleCreateRequest,
    db: AsyncSession = Depends(get_async_db),
    admin: User = Depends(require_permission("role:manage")),
):
    # 检查重名
    result = await db.execute(select(Role).filter(Role.name == req.name))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"角色名已存在: {req.name}")

    role = Role(
        name=req.name,
        display_name=req.display_name,
        description=req.description,
        permissions=req.permissions or [],
        is_system=0,
    )
    db.add(role)
    await db.commit()
    await db.refresh(role)

    logger.info("[角色管理] %s 创建角色 %s", admin.username, role.name)
    return RoleResponse(
        id=role.id, name=role.name, display_name=role.display_name,
        description=role.description, permissions=role.permissions or [],
        is_system=bool(role.is_system),
        created_at=role.created_at, updated_at=role.updated_at,
    )


# ---------- 修改角色 ----------
@router.put("/{role_name}", response_model=RoleResponse, summary="[管理员] 修改角色")
async def update_role(
    role_name: str,
    req: RoleUpdateRequest,
    db: AsyncSession = Depends(get_async_db),
    admin: User = Depends(require_permission("role:manage")),
):
    result = await db.execute(select(Role).filter(Role.name == role_name))
    role = result.scalar_one_or_none()
    if not role:
        raise HTTPException(status_code=404, detail="角色不存在")

    if req.display_name is not None:
        role.display_name = req.display_name
    if req.description is not None:
        role.description = req.description
    if req.permissions is not None:
        # 系统内置角色的权限也允许修改（方便定制），但不可删除
        role.permissions = req.permissions

    role.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(role)

    logger.info("[角色管理] %s 修改角色 %s", admin.username, role.name)
    return RoleResponse(
        id=role.id, name=role.name, display_name=role.display_name,
        description=role.description, permissions=role.permissions or [],
        is_system=bool(role.is_system),
        created_at=role.created_at, updated_at=role.updated_at,
    )


# ---------- 删除角色 ----------
@router.delete("/{role_name}", summary="[管理员] 删除角色")
async def delete_role(
    role_name: str,
    db: AsyncSession = Depends(get_async_db),
    admin: User = Depends(require_permission("role:manage")),
):
    result = await db.execute(select(Role).filter(Role.name == role_name))
    role = result.scalar_one_or_none()
    if not role:
        raise HTTPException(status_code=404, detail="角色不存在")

    if role.is_system:
        raise HTTPException(status_code=400, detail="系统内置角色不可删除")

    # 检查是否有用户正在使用该角色
    user_result = await db.execute(select(User).filter(User.role == role_name).limit(1))
    if user_result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="该角色下仍有用户，无法删除")

    await db.delete(role)
    await db.commit()

    logger.info("[角色管理] %s 删除角色 %s", admin.username, role_name)
    return {"success": True, "message": "角色已删除"}
