# =====================================================
# Provider 与模型定义相关的 Pydantic Schema
# 用于 /api/providers/* 和 /api/models/* 接口的请求/响应校验
# =====================================================

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.common import ModelGenParams

# =====================================================
# Provider 相关 Schema
# =====================================================

_ALLOWED_HTTP_METHODS = ("GET", "POST", "PUT", "PATCH")
_MODELS_MODES = ("static", "openai", "custom")
_VALID_POLL_STATUSES = ("success", "processing", "failed", "cancelled")


class _HttpActionBase(BaseModel):
    """声明式 HTTP 动作模板（endpoint+方法+额外头+超时）"""

    model_config = ConfigDict(extra="forbid", protected_namespaces=())
    path: str = Field(..., min_length=1, max_length=500, description="端点路径（相对 base_url 或完整 http(s) URL），支持 {{task_id}} 占位")
    method: str = Field(default="POST", description="HTTP 方法")
    headers: dict[str, str] = Field(default_factory=dict, description="额外请求头（值支持 {{api_key}}）；默认已自动带 Bearer 鉴权")
    timeout_sec: int = Field(default=60, ge=1, le=600, description="单次请求超时秒数")

    @field_validator("method")
    @classmethod
    def _check_method(cls, v: str) -> str:
        upper = (v or "POST").upper()
        if upper not in _ALLOWED_HTTP_METHODS:
            raise ValueError(f"不支持的 HTTP 方法：{v}")
        return upper


class HttpImageCreateConfig(_HttpActionBase):
    """同步图片创建模板"""

    body: str = Field(..., min_length=1, description="JSON 请求体模板：{{prompt}}/{{model}}/{{size}}/{{image}}/{{images}}")
    url_path: str = Field(default="", description="图片 URL 点路径映射，如 data.0.url")
    b64_path: str = Field(default="", description="base64 图片点路径映射，如 data.0.b64_json")


class HttpVideoCreateConfig(_HttpActionBase):
    """异步视频提交模板"""

    body: str = Field(..., min_length=1, description="JSON 请求体模板：{{prompt}}/{{model}}/{{width}}/{{height}}/{{seconds}}/{{aspect_ratio}}/{{image}}/{{images}}/{{negative_prompt}}")
    task_id_path: str = Field(default="", description="任务 ID 点路径映射")
    video_id_path: str = Field(default="", description="视频 ID 点路径映射（与 task_id 至少配一个）")


class HttpVideoPollConfig(BaseModel):
    """异步视频轮询模板"""

    model_config = ConfigDict(extra="forbid", protected_namespaces=())
    path: str = Field(..., min_length=1, max_length=500, description="轮询端点，支持 {{task_id}} 占位（自动用提交凭据填充）")
    method: str = Field(default="GET", description="HTTP 方法")
    headers: dict[str, str] = Field(default_factory=dict, description="额外请求头")
    status_path: str = Field(..., min_length=1, description="状态字段点路径")
    status_map: dict[str, str] = Field(..., description="上游状态值 → success/processing/failed/cancelled")
    video_url_path: str = Field(default="", description="视频地址点路径映射")
    progress_path: str = Field(default="", description="进度字段点路径映射（数字或百分比字符串）")
    error_path: str = Field(default="", description="错误信息点路径映射")
    timeout_sec: int = Field(default=15, ge=1, le=600, description="单次轮询超时秒数")

    @field_validator("method")
    @classmethod
    def _check_method(cls, v: str) -> str:
        upper = (v or "GET").upper()
        if upper not in _ALLOWED_HTTP_METHODS:
            raise ValueError(f"不支持的 HTTP 方法：{v}")
        return upper

    @field_validator("status_map")
    @classmethod
    def _check_status_map(cls, v: dict[str, str]) -> dict[str, str]:
        if not v:
            raise ValueError("status_map 不能为空")
        for upstream, standard in v.items():
            if standard not in _VALID_POLL_STATUSES:
                raise ValueError(f"status_map 值必须 ∈ {'/'.join(_VALID_POLL_STATUSES)}，得到 {upstream}→{standard}")
        return v


class HttpModelsEndpointConfig(BaseModel):
    """自定义模型目录端点（id 提取自动适配 {data:[...]} 包裹或裸数组、item.id 或条目本身）"""

    model_config = ConfigDict(extra="forbid", protected_namespaces=())
    path: str = Field(..., min_length=1, max_length=500, description="目录端点路径")
    method: str = Field(default="GET", description="HTTP 方法")
    headers: dict[str, str] = Field(default_factory=dict, description="额外请求头")
    timeout_sec: int = Field(default=15, ge=1, le=600, description="请求超时秒数")

    @field_validator("method")
    @classmethod
    def _check_method(cls, v: str) -> str:
        upper = (v or "GET").upper()
        if upper not in _ALLOWED_HTTP_METHODS:
            raise ValueError(f"不支持的 HTTP 方法：{v}")
        return upper


class HttpStaticModelItem(BaseModel):
    """静态模型目录条目"""

    model_config = ConfigDict(extra="forbid")
    id: str = Field(..., min_length=1, max_length=100, description="模型 ID")
    type: str = Field(default="", description="模型类型 image/video/chat（留空按名推断）")


class HttpConfigModel(BaseModel):
    """声明式 HTTP 渠道配置（api_providers.http_config；provider_type=http_custom 时使用）"""

    model_config = ConfigDict(extra="forbid", protected_namespaces=())
    models_mode: str = Field(default="openai", description="模型目录模式: static(静态列表) / openai(兼容 /models) / custom(自定义端点)")
    static_models: list[HttpStaticModelItem] | None = Field(default=None, description="静态模型目录（models_mode=static 时必填）")
    models_endpoint: HttpModelsEndpointConfig | None = Field(default=None, description="自定义目录端点（models_mode=custom 时必填）")
    image_create: HttpImageCreateConfig | None = Field(default=None, description="同步图片创建模板（None=不支持图片）")
    video_create: HttpVideoCreateConfig | None = Field(default=None, description="视频提交模板")
    video_poll: HttpVideoPollConfig | None = Field(default=None, description="视频轮询模板")

    @field_validator("models_mode")
    @classmethod
    def _check_models_mode(cls, v: str) -> str:
        if v not in _MODELS_MODES:
            raise ValueError(f"models_mode 必须 ∈ {'/'.join(_MODELS_MODES)}，得到 {v}")
        return v

    @model_validator(mode="after")
    def _check_modes(self) -> "HttpConfigModel":
        if self.models_mode == "static" and not self.static_models:
            raise ValueError("models_mode=static 时必须提供 static_models")
        if self.models_mode == "custom" and self.models_endpoint is None:
            raise ValueError("models_mode=custom 时必须提供 models_endpoint")
        if not any([self.image_create, self.video_create, self.video_poll]):
            raise ValueError("至少配置 image_create 或 video_create+video_poll 之一组动作模板")
        if (self.video_create is None) != (self.video_poll is None):
            raise ValueError("视频为两段式：video_create 与 video_poll 必须同时配置")
        return self


class ProviderCreateRequest(BaseModel):
    """创建 Provider 请求体"""
    name: str = Field(..., description="Provider 名称，如 Agnes AI（默认）")
    provider_type: str = Field(
        default="agnes",
        description="aibridge adapter 标识：agnes / volcengine_cv / kling / runway / pika 等",
    )
    base_url: str = Field(..., description="API 基础地址，如 https://apihub.agnes-ai.com/v1")
    api_key: str = Field(..., description="API Key（明文传入，后端加密存储）")
    poll_url: str = Field(default="", description="异步任务轮询专用接口（如视频轮询）")
    is_active: bool = Field(default=True, description="是否激活")
    is_default: bool = Field(default=False, description="是否设为默认 Provider")
    sort_order: int = Field(default=0, description="排序权重（越小越靠前）")
    billing_tier: str = Field(default="paid", description="计费档位: free(免费) / paid(付费)")
    http_config: HttpConfigModel | None = Field(default=None, description="声明式 HTTP 渠道模板（provider_type=http_custom 时使用）")


class ProviderUpdateRequest(BaseModel):
    """更新 Provider 请求体（所有字段可选）"""
    name: str | None = Field(default=None, description="Provider 名称")
    provider_type: str | None = Field(
        default=None, description="aibridge adapter 标识"
    )
    base_url: str | None = Field(default=None, description="API 基础地址")
    api_key: str | None = Field(default=None, description="API Key（留空表示不修改）")
    poll_url: str | None = Field(default=None, description="异步任务轮询接口")
    is_active: bool | None = Field(default=None, description="是否激活")
    is_default: bool | None = Field(default=None, description="是否设为默认 Provider")
    sort_order: int | None = Field(default=None, description="排序权重")
    billing_tier: str | None = Field(default=None, description="计费档位: free/paid")
    http_config: HttpConfigModel | None = Field(default=None, description="声明式 HTTP 渠道模板（None=不修改；显式置空请传空对象会校验失败，改用 provider_type 切换）")


class ProviderResponse(BaseModel):
    """Provider 响应体（不含明文 API Key）"""
    id: int
    name: str
    provider_type: str = "agnes"
    base_url: str
    api_key: str = Field(description="API Key 脱敏后的展示值，如 sk-a****b123")
    poll_url: str = ""
    is_active: bool
    is_default: bool
    sort_order: int
    billing_tier: str = "paid"
    http_config: dict | None = Field(default=None, description="声明式 HTTP 渠道模板")
    created_at: datetime | None = None
    updated_at: datetime | None = None

    class Config:
        from_attributes = True


class ProviderListResponse(BaseModel):
    """Provider 列表响应"""
    total: int
    items: list[ProviderResponse]


# =====================================================
# 模型定义相关 Schema
# =====================================================

class CustomModelCreateRequest(BaseModel):
    """添加自定义模型请求体"""
    provider_id: int = Field(..., description="所属 Provider ID")
    model_id: str = Field(..., description="模型标识，如 agnes-image-2.1-flash")
    display_name: str = Field(default="", description="显示名称（留空自动推断）")
    model_type: str = Field(default="", description="模型类型：image / video / chat（留空自动推断）")
    provider_name: str = Field(default="", description="供应商名称（留空自动推断）")
    capabilities: list[str] | None = Field(default=None, description="能力标签列表")
    gen_params: ModelGenParams | None = Field(
        default=None,
        description="生成能力配置（参考图上限/水印/尺寸规则/默认尺寸等）；None=按模型名自动画像",
    )
    sort_order: int = Field(default=0, description="排序权重")
    asset_storage_mode: str = Field(default="auto", description="资源存储策略: auto/keep/migrate")


class ModelUpdateRequest(BaseModel):
    """更新模型定义请求体（所有字段可选）"""
    display_name: str | None = Field(default=None, description="显示名称")
    model_type: str | None = Field(default=None, description="模型类型")
    provider_name: str | None = Field(default=None, description="供应商名称")
    capabilities: list[str] | None = Field(default=None, description="能力标签列表")
    gen_params: ModelGenParams | None = Field(
        default=None,
        description="生成能力配置（全默认值=清空显式配置回退自动画像）；None=不修改",
    )
    is_active: bool | None = Field(default=None, description="是否激活")
    is_disabled: bool | None = Field(
        default=None,
        description="是否用户手动停用（停用后不出现在生成页模型列表，同步不会自动恢复）",
    )
    sort_order: int | None = Field(default=None, description="排序权重")
    asset_storage_mode: str | None = Field(default=None, description="资源存储策略: auto/keep/migrate")
    cost_multiplier: float | None = Field(default=None, ge=0.1, le=100, description="积分倍率（实扣=基准价×倍率；None=不修改）")


class ModelDefinitionResponse(BaseModel):
    """模型定义响应体（含管理字段）"""
    id: int
    provider_id: int
    model_id: str
    display_name: str = ""
    type: str
    provider_name: str = ""
    capabilities: list[str] = Field(default_factory=list)
    gen_params: ModelGenParams | None = None
    is_active: bool
    is_disabled: bool = False
    is_custom: bool
    sort_order: int
    asset_storage_mode: str = Field(default="auto", description="资源存储策略: auto/keep/migrate")
    cost_multiplier: float = Field(default=1.0, description="积分倍率：实扣=基准价×倍率")

    class Config:
        from_attributes = True


class ModelListResponse(BaseModel):
    """模型定义列表响应"""
    total: int
    items: list[ModelDefinitionResponse]


class ModelBatchUpdateRequest(BaseModel):
    """批量更新模型请求体（当前仅支持停用/启用）"""
    model_ids: list[str] = Field(..., description="模型 ID 列表")
    is_disabled: bool = Field(..., description="是否停用")


class ModelBatchDeleteRequest(BaseModel):
    """批量删除模型请求体"""
    model_ids: list[str] = Field(..., description="模型 ID 列表")


class ModelBatchCostMultiplierRequest(BaseModel):
    """批量设置模型积分倍率请求体（实扣积分 = 基准价 × 倍率）"""
    model_ids: list[str] = Field(..., description="模型 ID 列表")
    cost_multiplier: float = Field(..., ge=0.1, le=100, description="积分倍率")


# =====================================================
# 模型同步相关 Schema
# =====================================================

class SyncModelsResponse(BaseModel):
    """模型同步结果响应"""
    provider_id: int
    added: int = Field(description="新增的模型数量")
    updated: int = Field(description="更新的模型数量")
    deactivated: int = Field(description="被软删除（API 中已不存在）的模型数量")
    total: int = Field(description="API 返回的模型总数")
    error: str | None = Field(default=None, description="同步失败时的错误信息")


class SyncAllResponse(BaseModel):
    """同步所有 Provider 模型的响应"""
    results: list[SyncModelsResponse]


# =====================================================
# 模型备用路由 Schema（多渠道路由 failover）
# =====================================================

class ModelRouteItemRequest(BaseModel):
    """备用路由条目（保存请求）"""
    provider_id: int = Field(..., description="目标渠道 Provider ID")
    model_id: str = Field(..., min_length=1, max_length=100, description="目标模型 ID（同款渠道或等价模型）")
    priority: int = Field(default=0, ge=0, description="优先级：越小越优先")
    is_enabled: bool = Field(default=True, description="是否启用")


class ModelRouteSaveRequest(BaseModel):
    """保存锚点模型的备用路由列表（整表替换语义）"""
    routes: list[ModelRouteItemRequest] = Field(default_factory=list, description="备用路由列表（空=清空）")


class ModelRouteItemResponse(BaseModel):
    """备用路由条目（含渠道信息快照）"""
    id: int
    provider_id: int
    provider_name: str = ""
    billing_tier: str = "paid"
    model_id: str
    display_name: str = ""
    priority: int
    is_enabled: bool


class ModelRoutesResponse(BaseModel):
    """锚点模型备用路由响应"""
    anchor_model_id: str
    anchor_type: str = ""
    anchor_provider_id: int | None = None
    items: list[ModelRouteItemResponse]
