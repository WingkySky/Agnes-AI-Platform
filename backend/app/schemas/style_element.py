# =====================================================
# StyleElement Schemas — 请求和响应数据结构
# =====================================================

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class StyleElementBase(BaseModel):
    """风格元素基础字段"""
    name: str = Field(..., max_length=200, description="显示名称")
    description: Optional[str] = Field(None, description="描述")
    layer: str = Field(..., description="所属层（visual_style/lighting/color/camera/mood/quality）")
    category: Optional[str] = Field(None, max_length=50, description="细分类")
    content: str = Field(..., description="提示词内容")
    negative_content: Optional[str] = Field(None, description="负面提示词")
    preview_image: Optional[str] = Field(None, description="缩略图 URL")
    weight_default: float = Field(1.0, ge=0.0, le=1.0, description="默认权重")
    tags: List[str] = Field(default_factory=list, description="标签")
    is_public: bool = Field(False, description="是否公开")


class StyleElementCreate(StyleElementBase):
    """创建风格元素请求"""
    key: Optional[str] = Field(None, max_length=100, description="唯一标识（不传则自动生成）")


class StyleElementUpdate(BaseModel):
    """更新风格元素请求（所有字段可选）"""
    name: Optional[str] = Field(None, max_length=200)
    description: Optional[str] = None
    content: Optional[str] = None
    negative_content: Optional[str] = None
    preview_image: Optional[str] = None
    weight_default: Optional[float] = Field(None, ge=0.0, le=1.0)
    tags: Optional[List[str]] = None
    is_public: Optional[bool] = None


class StyleElementResponse(StyleElementBase):
    """风格元素响应"""
    id: int
    key: str
    is_builtin: bool
    author_id: Optional[int] = None
    use_count: int = 0
    sort_order: int = 0

    class Config:
        from_attributes = True


class StyleElementListResponse(BaseModel):
    """风格元素列表响应"""
    items: List[StyleElementResponse]
    total: int


class ResolvedElementItem(BaseModel):
    """用户选择的风格元素项"""
    element_id: int
    weight: float = Field(1.0, ge=0.0, le=1.0)


class PromptPreviewRequest(BaseModel):
    """prompt 预览请求"""
    base_prompt: str = Field("", description="基础 prompt")
    elements: List[ResolvedElementItem] = Field(default_factory=list)


class PromptPreviewResponse(BaseModel):
    """prompt 预览响应"""
    positive: str
    negative: str
    negative_suffix: str
    final_prompt: str
