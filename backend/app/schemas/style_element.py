# =====================================================
# StyleElement Schemas — 请求和响应数据结构
# =====================================================

from pydantic import BaseModel, Field


class StyleElementBase(BaseModel):
    """风格元素基础字段"""
    name: str = Field(..., max_length=200, description="显示名称")
    description: str | None = Field(None, description="描述")
    layer: str = Field(..., description="所属层（visual_style/lighting/color/camera/mood/quality）")
    category: str | None = Field(None, max_length=50, description="细分类")
    content: str = Field(..., description="提示词内容")
    negative_content: str | None = Field(None, description="负面提示词")
    preview_image: str | None = Field(None, description="缩略图 URL")
    weight_default: float = Field(1.0, ge=0.0, le=1.0, description="默认权重")
    tags: list[str] = Field(default_factory=list, description="标签")
    is_public: bool = Field(False, description="是否公开")


class StyleElementCreate(StyleElementBase):
    """创建风格元素请求"""
    key: str | None = Field(None, max_length=100, description="唯一标识（不传则自动生成）")


class StyleElementUpdate(BaseModel):
    """更新风格元素请求（所有字段可选）"""
    name: str | None = Field(None, max_length=200)
    description: str | None = None
    content: str | None = None
    negative_content: str | None = None
    preview_image: str | None = None
    weight_default: float | None = Field(None, ge=0.0, le=1.0)
    tags: list[str] | None = None
    is_public: bool | None = None


class StyleElementResponse(StyleElementBase):
    """风格元素响应"""
    id: int
    key: str
    is_builtin: bool
    author_id: int | None = None
    use_count: int = 0
    sort_order: int = 0

    class Config:
        from_attributes = True


class StyleElementListResponse(BaseModel):
    """风格元素列表响应"""
    items: list[StyleElementResponse]
    total: int


class ResolvedElementItem(BaseModel):
    """用户选择的风格元素项"""
    element_id: int
    weight: float = Field(1.0, ge=0.0, le=1.0)


class PromptPreviewRequest(BaseModel):
    """prompt 预览请求"""
    base_prompt: str = Field("", description="基础 prompt")
    elements: list[ResolvedElementItem] = Field(default_factory=list)


class PromptPreviewResponse(BaseModel):
    """prompt 预览响应"""
    positive: str
    negative: str
    negative_suffix: str
    final_prompt: str
