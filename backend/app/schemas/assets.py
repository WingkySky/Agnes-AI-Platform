# =====================================================
# 资产库相关的 Pydantic Schema
# 包含角色、道具、场景、品牌等创意资产
# =====================================================

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

# =====================================================
# 风格预设 Schema
# =====================================================

class StylePresetBase(BaseModel):
    """风格预设基础字段"""
    key: str = Field(..., min_length=1, max_length=100, description="风格唯一标识")
    name: str = Field(..., min_length=1, max_length=200, description="风格名称")
    description: str | None = Field(None, max_length=1000, description="描述")
    category: str = Field(..., description="分类：art_style / mood / cinematography")
    visual_prefix: str | None = Field(None, description="视觉风格前缀")
    lighting: str | None = Field(None, max_length=500, description="光影风格")
    color_palette: str | None = Field(None, max_length=500, description="配色方案")
    quality_suffix: str | None = Field(None, description="品质增强词")
    negative_prompt: str | None = Field(None, description="负面提示词")
    camera_language: str | None = Field(None, max_length=500, description="镜头语言偏好")
    mood_keywords: str | None = Field(None, max_length=500, description="氛围关键词")
    preview_image: str | None = Field(None, max_length=500, description="预览图 URL")


class StylePresetResponse(StylePresetBase):
    """风格预设响应"""
    id: int
    tags: list[str] = Field(default_factory=list, description="标签列表")
    is_builtin: bool = False
    is_public: bool = False
    author_id: int | None = None
    use_count: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None

    class Config:
        from_attributes = True


# =====================================================
# 剧本模板 Schema
# =====================================================

class ScriptTemplateBase(BaseModel):
    """剧本模板基础字段"""
    key: str = Field(..., min_length=1, max_length=100, description="模板唯一标识")
    name: str = Field(..., min_length=1, max_length=200, description="模板名称")
    description: str | None = Field(None, description="描述")
    category: str = Field(..., description="分类：drama / ad / education / art")
    structure: str = Field(..., description="叙事结构：three_act / five_act / kishotenketsu")
    prompt_template: str = Field(..., description="提示词模板（Jinja2 风格）")
    output_schema: dict[str, Any] = Field(default_factory=dict, description="输出 JSON Schema")
    scenes_min: int = Field(3, ge=1, description="最少分镜数")
    scenes_max: int = Field(20, ge=1, description="最多分镜数")
    default_scene_duration: int = Field(5, ge=1, description="默认单镜时长（秒）")


class ScriptTemplateResponse(ScriptTemplateBase):
    """剧本模板响应"""
    id: int
    variables_schema: dict[str, Any] | None = None
    output_format: str = "json"
    tags: list[str] = Field(default_factory=list, description="标签列表")
    is_builtin: bool = False
    is_public: bool = False
    author_id: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    class Config:
        from_attributes = True


# =====================================================
# 资产 Schema
# =====================================================

class AssetBase(BaseModel):
    """资产基础字段"""
    type: str = Field(..., description="类型：character / prop / scene / brand")
    name: str = Field(..., min_length=1, max_length=200, description="名称")
    description: str | None = Field(None, description="详细描述")
    visual_description: str = Field(..., description="外观描述文本（用于生成提示词）")
    reference_images: list[str] = Field(default_factory=list, description="参考图 URL 数组")
    style_id: int | None = Field(None, description="关联的风格预设 ID")
    tags: list[str] = Field(default_factory=list, description="标签数组")


class AssetResponse(AssetBase):
    """资产响应"""
    id: int
    user_id: int | None = None
    is_public: bool = False
    moderation_status: str = "approved"
    moderation_reason: str | None = None
    version: int = 1
    parent_id: int | None = None
    likes_count: int = 0
    views_count: int = 0
    use_count: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None
    public_shared_at: datetime | None = None

    # ===== 创作归档字段（container_* 非空即为画布/项目生成的自动归档影子记录）=====
    container_type: str | None = None      # project / canvas_script / canvas
    container_id: str | None = None        # 项目 ID / 剧本面板 ID / 'canvas'
    container_name: str | None = None      # 容器名快照
    source_generation_id: int | None = None  # 来源生成记录 ID（归档去重键）
    kind: str | None = None                # image / video
    asset_url: str | None = None           # 单媒体 URL

    class Config:
        from_attributes = True


class AssetContainerResponse(BaseModel):
    """创作单元（容器）分组摘要

    同一 (container_type, container_id) 下的归档资产聚合成一个单元。
    """
    container_type: str | None = None
    container_id: str | None = None
    container_name: str | None = None
    type_label: str = ""          # 项目 / 剧本 / 画布
    asset_count: int = 0
    cover_url: str | None = None
    cover_kind: str | None = None   # image / video


class AssetContainersResponse(BaseModel):
    """创作单元列表 + 我的资产（container 为空的传统资产）统计"""
    containers: list[AssetContainerResponse] = Field(default_factory=list)
    standalone_total: int = 0


class AssetContainerDetailResponse(BaseModel):
    """单元详情：单元元信息 + 单元内资产列表"""
    container_type: str | None = None
    container_id: str | None = None
    container_name: str | None = None
    type_label: str = ""
    items: list[AssetResponse] = Field(default_factory=list)


class AssetSaveFromGenerationRequest(BaseModel):
    """从生成记录保存为资产请求"""
    generation_id: int = Field(..., description="生成记录 ID")
    type: str = Field(..., description="资产类型：character / prop / scene / brand")
    name: str = Field(..., min_length=1, max_length=200, description="资产名称")
    description: str | None = None
    visual_description: str | None = Field(None, description="外观描述，默认使用生成的 prompt")
    style_id: int | None = None
    tags: list[str] = Field(default_factory=list)


# 统一资产池的合法类型（实体四类 + 影子归档的行政三类）
ASSET_TYPE_CHOICES = {"character", "prop", "scene", "brand", "material", "clip", "final"}


class AssetUpdateRequest(BaseModel):
    """编辑资产元数据请求体（全字段可选，仅更新提交的字段）"""
    name: str | None = Field(None, min_length=1, max_length=200, description="名称")
    type: str | None = Field(None, description="类型：character / prop / scene / brand / material / clip / final")
    description: str | None = Field(None, description="详细描述")
    visual_description: str | None = Field(None, description="外观描述文本（用于生成提示词）")
    work_id: int | None = Field(None, description="所属作品标记（需归属当前用户）")


# =====================================================
# 兼容别名（Out 后缀与路由导入保持一致）
# =====================================================

StylePresetOut = StylePresetResponse
ScriptTemplateOut = ScriptTemplateResponse
AssetOut = AssetResponse
