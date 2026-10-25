# =====================================================
# 角色管理相关 Pydantic Schema
# =====================================================

from datetime import datetime

from pydantic import BaseModel, Field


class RoleResponse(BaseModel):
    """角色信息响应"""
    id: int
    name: str
    display_name: str
    description: str | None = None
    permissions: list[str] = []
    is_system: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None

    class Config:
        from_attributes = True


class RoleCreateRequest(BaseModel):
    """创建角色请求"""
    name: str = Field(..., min_length=2, max_length=32, description="角色英文标识，如 editor")
    display_name: str = Field(..., min_length=2, max_length=64, description="角色显示名称")
    description: str | None = Field(default=None, max_length=255)
    permissions: list[str] = Field(default_factory=list, description="权限点列表")


class RoleUpdateRequest(BaseModel):
    """更新角色请求（所有字段可选，只更新传入的字段）"""
    display_name: str | None = Field(default=None, min_length=2, max_length=64)
    description: str | None = Field(default=None, max_length=255)
    permissions: list[str] | None = Field(default=None, description="权限点列表（全量替换）")


class PermissionItem(BaseModel):
    """权限点定义（供前端展示权限列表）"""
    key: str
    name: str
    description: str
    group: str
