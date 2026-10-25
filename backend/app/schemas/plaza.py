# =====================================================
# 广场（Plaza）相关的 Pydantic Schema
# 包含：广场作品列表/详情响应、点赞操作、分享状态切换
# =====================================================

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

# =====================================================
# 广场作品响应
# =====================================================

class PlazaWork(BaseModel):
    """广场作品（列表项 / 详情）"""
    id: int
    type: str                                                    # 'image' | 'video'
    prompt: str
    model: str | None = None
    params: dict[str, Any] | None = None
    mode: str | None = None
    result_url: str | None = None
    likes_count: int = 0
    views_count: int = 0
    author_nickname: str | None = None                        # 作者昵称（优先 nickname，回退 username）
    author_avatar_url: str | None = None                      # 作者头像（相对路径如 /uploads/avatars/xxx.jpg，未上传则为 None）
    created_at: datetime | None = None
    public_shared_at: datetime | None = None
    is_mine: bool = False                                        # 当前用户是否为作者
    is_liked: bool = False                                       # 当前用户是否已点赞
    # ── 预设来源：作品使用了哪个预设（用于"按预设浏览"和抽屉作品效果展示） ──
    preset_id: int | None = None

    class Config:
        from_attributes = True


class PlazaListResponse(BaseModel):
    """广场列表响应（分页）"""
    total: int
    page: int
    page_size: int
    items: list[PlazaWork]


# =====================================================
# 广场「创作」Tab 响应（来自 assets 表，与作品 Tab 平行）
# =====================================================

class PlazaCreation(BaseModel):
    """广场创作资产（列表项 / 详情）"""
    id: int
    kind: str                                                    # 'image' | 'video'
    asset_type: str                                             # character/scene/material/clip/final/prop/brand
    name: str
    description: str | None = None
    asset_url: str | None = None                             # 单媒体 URL（图片/视频）
    container_type: str | None = None                        # project/canvas_script/canvas
    container_name: str | None = None                        # 创作单元名快照
    likes_count: int = 0
    views_count: int = 0
    author_nickname: str | None = None
    author_avatar_url: str | None = None
    created_at: datetime | None = None
    public_shared_at: datetime | None = None
    is_mine: bool = False
    is_liked: bool = False

    class Config:
        from_attributes = True


class PlazaCreationListResponse(BaseModel):
    """广场创作列表响应（分页）"""
    total: int
    page: int
    page_size: int
    items: list[PlazaCreation]


# =====================================================
# 点赞相关
# =====================================================

class LikeActionResponse(BaseModel):
    """点赞/取消点赞操作响应"""
    liked: bool
    likes_count: int


class LikeStatusResponse(BaseModel):
    """批量查询点赞状态响应"""
    liked_ids: list[int] = []


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
    ids: list[int]
    is_public: bool


class BatchShareResponse(BaseModel):
    """批量设置分享状态响应"""
    success: bool
    updated_count: int
    failed_ids: list[int] = []
    message: str
