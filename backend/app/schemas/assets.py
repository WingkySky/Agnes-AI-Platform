# =====================================================
# 资产库相关的 Pydantic Schema
# 包含角色、道具、场景、品牌等创意资产
# =====================================================

from typing import List, Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field


# =====================================================
# 风格预设 Schema
# =====================================================

class StylePresetBase(BaseModel):
    """风格预设基础字段"""
    key: str = Field(..., min_length=1, max_length=100, description="风格唯一标识")
    name: str = Field(..., min_length=1, max_length=200, description="风格名称")
    description: Optional[str] = Field(None, max_length=1000, description="描述")
    category: str = Field(..., description="分类：art_style / mood / cinematography")
    visual_prefix: Optional[str] = Field(None, description="视觉风格前缀")
    lighting: Optional[str] = Field(None, max_length=500, description="光影风格")
    color_palette: Optional[str] = Field(None, max_length=500, description="配色方案")
    quality_suffix: Optional[str] = Field(None, description="品质增强词")
    negative_prompt: Optional[str] = Field(None, description="负面提示词")
    camera_language: Optional[str] = Field(None, max_length=500, description="镜头语言偏好")
    mood_keywords: Optional[str] = Field(None, max_length=500, description="氛围关键词")
    preview_image: Optional[str] = Field(None, max_length=500, description="预览图 URL")


class StylePresetCreate(StylePresetBase):
    """创建风格预设请求"""
    is_public: bool = Field(False, description="是否公开")


class StylePresetUpdate(BaseModel):
    """更新风格预设请求"""
    name: Optional[str] = Field(None, max_length=200)
    description: Optional[str] = None
    category: Optional[str] = None
    visual_prefix: Optional[str] = None
    lighting: Optional[str] = None
    color_palette: Optional[str] = None
    quality_suffix: Optional[str] = None
    negative_prompt: Optional[str] = None
    camera_language: Optional[str] = None
    mood_keywords: Optional[str] = None
    preview_image: Optional[str] = None
    is_public: Optional[bool] = None


class StylePresetResponse(StylePresetBase):
    """风格预设响应"""
    id: int
    tags: List[str] = Field(default_factory=list, description="标签列表")
    is_builtin: bool = False
    is_public: bool = False
    author_id: Optional[int] = None
    use_count: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class StylePresetListResponse(BaseModel):
    """风格预设列表响应"""
    total: int
    page: int
    page_size: int
    items: List[StylePresetResponse]


# =====================================================
# 剧本模板 Schema
# =====================================================

class ScriptTemplateBase(BaseModel):
    """剧本模板基础字段"""
    key: str = Field(..., min_length=1, max_length=100, description="模板唯一标识")
    name: str = Field(..., min_length=1, max_length=200, description="模板名称")
    description: Optional[str] = Field(None, description="描述")
    category: str = Field(..., description="分类：drama / ad / education / art")
    structure: str = Field(..., description="叙事结构：three_act / five_act / kishotenketsu")
    prompt_template: str = Field(..., description="提示词模板（Jinja2 风格）")
    output_schema: Dict[str, Any] = Field(default_factory=dict, description="输出 JSON Schema")
    scenes_min: int = Field(3, ge=1, description="最少分镜数")
    scenes_max: int = Field(20, ge=1, description="最多分镜数")
    default_scene_duration: int = Field(5, ge=1, description="默认单镜时长（秒）")


class ScriptTemplateCreate(ScriptTemplateBase):
    """创建剧本模板请求"""
    is_public: bool = Field(False, description="是否公开")


class ScriptTemplateUpdate(BaseModel):
    """更新剧本模板请求"""
    name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    structure: Optional[str] = None
    prompt_template: Optional[str] = None
    output_schema: Optional[Dict[str, Any]] = None
    scenes_min: Optional[int] = None
    scenes_max: Optional[int] = None
    default_scene_duration: Optional[int] = None
    is_public: Optional[bool] = None


class ScriptTemplateResponse(ScriptTemplateBase):
    """剧本模板响应"""
    id: int
    variables_schema: Optional[Dict[str, Any]] = None
    output_format: str = "json"
    tags: List[str] = Field(default_factory=list, description="标签列表")
    is_builtin: bool = False
    is_public: bool = False
    author_id: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ScriptTemplateListResponse(BaseModel):
    """剧本模板列表响应"""
    total: int
    page: int
    page_size: int
    items: List[ScriptTemplateResponse]


# =====================================================
# 资产 Schema
# =====================================================

class AssetBase(BaseModel):
    """资产基础字段"""
    type: str = Field(..., description="类型：character / prop / scene / brand")
    name: str = Field(..., min_length=1, max_length=200, description="名称")
    description: Optional[str] = Field(None, description="详细描述")
    visual_description: str = Field(..., description="外观描述文本（用于生成提示词）")
    reference_images: List[str] = Field(default_factory=list, description="参考图 URL 数组")
    style_id: Optional[int] = Field(None, description="关联的风格预设 ID")
    tags: List[str] = Field(default_factory=list, description="标签数组")


class AssetCreate(AssetBase):
    """创建资产请求"""
    is_public: bool = Field(False, description="是否公开")


class AssetUpdate(BaseModel):
    """更新资产请求（创建新版本）"""
    name: Optional[str] = None
    description: Optional[str] = None
    visual_description: Optional[str] = None
    reference_images: Optional[List[str]] = None
    style_id: Optional[int] = None
    tags: Optional[List[str]] = None
    is_public: Optional[bool] = None


class AssetResponse(AssetBase):
    """资产响应"""
    id: int
    user_id: Optional[int] = None
    is_public: bool = False
    moderation_status: str = "approved"
    version: int = 1
    parent_id: Optional[int] = None
    likes_count: int = 0
    views_count: int = 0
    use_count: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class AssetListResponse(BaseModel):
    """资产列表响应"""
    total: int
    page: int
    page_size: int
    items: List[AssetResponse]


class AssetVersionResponse(AssetResponse):
    """资产版本信息"""
    pass


class AssetSaveFromGenerationRequest(BaseModel):
    """从生成记录保存为资产请求"""
    generation_id: int = Field(..., description="生成记录 ID")
    type: str = Field(..., description="资产类型：character / prop / scene / brand")
    name: str = Field(..., min_length=1, max_length=200, description="资产名称")
    description: Optional[str] = None
    visual_description: Optional[str] = Field(None, description="外观描述，默认使用生成的 prompt")
    style_id: Optional[int] = None
    tags: List[str] = Field(default_factory=list)


# =====================================================
# 兼容别名（Out 后缀与路由导入保持一致）
# =====================================================

StylePresetOut = StylePresetResponse
ScriptTemplateOut = ScriptTemplateResponse
AssetOut = AssetResponse
