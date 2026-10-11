# =====================================================
# PAT（个人访问令牌）Schemas —— 请求/响应结构
# =====================================================

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class PatCreate(BaseModel):
    """创建 PAT"""
    name: str = Field(..., min_length=1, max_length=100, description="令牌名称（用户起名）")
    permission: str = Field("readonly", pattern="^(readonly|full)$", description="readonly=只读档 / full=完全档")


class PatInfo(BaseModel):
    """令牌条目（脱敏，无 token 材料）"""
    id: int
    name: str
    permission: str
    last_used_at: Optional[datetime] = None
    revoked_at: Optional[datetime] = None
    created_at: datetime


class PatCreated(PatInfo):
    """创建响应：明文 token 仅此一次返回"""
    token: str
