# =====================================================
# Work Schemas — 作品（轻容器） 请求/响应结构
# =====================================================

from datetime import datetime

from pydantic import BaseModel, Field


class WorkCreateRequest(BaseModel):
    """创建作品"""
    title: str = Field(..., min_length=1, max_length=255, description="作品名")
    description: str | None = Field(None, max_length=2000, description="简介")
    cover_url: str | None = Field(None, max_length=1024, description="封面图 URL")


class WorkUpdateRequest(BaseModel):
    """更新作品（全字段可选）"""
    title: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = Field(None, max_length=2000)
    cover_url: str | None = Field(None, max_length=1024)


class WorkResponse(BaseModel):
    """作品项"""
    id: int
    title: str
    cover_url: str | None = None
    description: str | None = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class WorkListResponse(BaseModel):
    """作品列表"""
    total: int
    items: list[WorkResponse]
