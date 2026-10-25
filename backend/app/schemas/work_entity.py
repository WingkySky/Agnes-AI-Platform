# =====================================================
# WorkEntity Schemas — 作品实体库 请求/响应结构
# =====================================================

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

EntityKind = Literal["character", "scene", "prop"]
ImageRole = Literal["design", "turnaround", "angle"]


class EntityCreateRequest(BaseModel):
    """创建实体（可带首图资产 id，建首版本并采用）"""
    kind: EntityKind
    name: str = Field(..., min_length=1, max_length=64)
    description: str | None = Field(None, max_length=2000)
    asset_id: int | None = Field(None, description="首图资产 id，可选")


class EntityUpdateRequest(BaseModel):
    """更新实体（全字段可选）"""
    name: str | None = Field(None, min_length=1, max_length=64)
    description: str | None = Field(None, max_length=2000)


class EntityVersionCreateRequest(BaseModel):
    """新增版本（design=新版本并自动采用；angle/turnaround=追加进当前采用版本）"""
    asset_id: int
    role: ImageRole = "design"


class EntityAdoptRequest(BaseModel):
    """采用切换"""
    version_id: int


class EntityImageResponse(BaseModel):
    asset_id: int
    role: str
    url: str | None = None


class EntityVersionResponse(BaseModel):
    id: int
    images: list[EntityImageResponse] = []
    is_active: bool
    created_at: datetime


class EntityResponse(BaseModel):
    """实体项（含版本列表与采用图 url）"""
    id: int
    work_id: int
    kind: str
    name: str
    description: str | None = None
    versions: list[EntityVersionResponse] = []
    active_image_url: str | None = None
    created_at: datetime
    updated_at: datetime


class EntityListResponse(BaseModel):
    total: int
    items: list[EntityResponse]
