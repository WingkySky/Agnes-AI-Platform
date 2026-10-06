# =====================================================
# WorkEntity Schemas — 作品实体库 请求/响应结构
# =====================================================

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field

EntityKind = Literal["character", "scene", "prop"]
ImageRole = Literal["design", "turnaround", "angle"]


class EntityCreateRequest(BaseModel):
    """创建实体（可带首图资产 id，建首版本并采用）"""
    kind: EntityKind
    name: str = Field(..., min_length=1, max_length=64)
    description: Optional[str] = Field(None, max_length=2000)
    asset_id: Optional[int] = Field(None, description="首图资产 id，可选")


class EntityUpdateRequest(BaseModel):
    """更新实体（全字段可选）"""
    name: Optional[str] = Field(None, min_length=1, max_length=64)
    description: Optional[str] = Field(None, max_length=2000)


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
    url: Optional[str] = None


class EntityVersionResponse(BaseModel):
    id: int
    images: List[EntityImageResponse] = []
    is_active: bool
    created_at: datetime


class EntityResponse(BaseModel):
    """实体项（含版本列表与采用图 url）"""
    id: int
    work_id: int
    kind: str
    name: str
    description: Optional[str] = None
    versions: List[EntityVersionResponse] = []
    active_image_url: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class EntityListResponse(BaseModel):
    total: int
    items: List[EntityResponse]
