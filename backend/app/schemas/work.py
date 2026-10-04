# =====================================================
# Work Schemas — 作品（轻容器） 请求/响应结构
# =====================================================

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class WorkCreateRequest(BaseModel):
    """创建作品"""
    title: str = Field(..., min_length=1, max_length=255, description="作品名")
    description: Optional[str] = Field(None, max_length=2000, description="简介")
    cover_url: Optional[str] = Field(None, max_length=1024, description="封面图 URL")


class WorkUpdateRequest(BaseModel):
    """更新作品（全字段可选）"""
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=2000)
    cover_url: Optional[str] = Field(None, max_length=1024)


class WorkResponse(BaseModel):
    """作品项"""
    id: int
    title: str
    cover_url: Optional[str] = None
    description: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class WorkListResponse(BaseModel):
    """作品列表"""
    total: int
    items: List[WorkResponse]
