# =====================================================
# 广场（Plaza）相关的 Pydantic Schema
# 包含：广场作品列表/详情响应、点赞操作、分享状态切换
# =====================================================

from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field


# =====================================================
# 广场作品响应
# =====================================================

class PlazaWork(BaseModel):
    """广场作品（列表项 / 详情）"""
    id: int
    type: str                                                    # 'image' | 'video'
    prompt: str
    model: Optional[str] = None
    params: Optional[Dict[str, Any]] = None
    mode: Optional[str] = None
    result_url: Optional[str] = None
    likes_count: int = 0
    views_count: int = 0
    author_nickname: Optional[str] = None                        # 作者昵称（优先 nickname，回退 username）
    author_avatar_url: Optional[str] = None                      # 作者头像（相对路径如 /uploads/avatars/xxx.jpg，未上传则为 None）
    created_at: Optional[datetime] = None
    public_shared_at: Optional[datetime] = None
    is_mine: bool = False                                        # 当前用户是否为作者
    is_liked: bool = False                                       # 当前用户是否已点赞
    # ── 预设来源：作品使用了哪个预设（用于"按预设浏览"和抽屉作品效果展示） ──
    preset_id: Optional[int] = None

    class Config:
        from_attributes = True


class PlazaListResponse(BaseModel):
    """广场列表响应（分页）"""
    total: int
    page: int
    page_size: int
    items: List[PlazaWork]


# =====================================================
# 点赞相关
# =====================================================

class LikeActionResponse(BaseModel):
    """点赞/取消点赞操作响应"""
    liked: bool
    likes_count: int


class LikeStatusResponse(BaseModel):
    """批量查询点赞状态响应"""
    liked_ids: List[int] = []


# =====================================================
# 分享状态切换
# =====================================================

class UpdateShareStatusRequest(BaseModel):
    """单条切换分享状态请求"""
    is_public: bool = Field(..., description="是否设置为公开分享")


class UpdateShareStatusResponse(BaseModel):
    """单条切换分享状态响应"""
    success: bool
    id: int
    is_public: bool
    message: str


class BatchShareRequest(BaseModel):
    """批量设置分享状态请求"""
    ids: List[int]
    is_public: bool


class BatchShareResponse(BaseModel):
    """批量设置分享状态响应"""
    success: bool
    updated_count: int
    failed_ids: List[int] = []
    message: str
