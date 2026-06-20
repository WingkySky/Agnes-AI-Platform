# =====================================================
# Provider 与模型定义相关的 Pydantic Schema
# 用于 /api/providers/* 和 /api/models/* 接口的请求/响应校验
# =====================================================

from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field


# =====================================================
# Provider 相关 Schema
# =====================================================

class ProviderCreateRequest(BaseModel):
    """创建 Provider 请求体"""
    name: str = Field(..., description="Provider 名称，如 Agnes AI（默认）")
    base_url: str = Field(..., description="API 基础地址，如 https://apihub.agnes-ai.com/v1")
    api_key: str = Field(..., description="API Key（明文传入，后端加密存储）")
    poll_url: str = Field(default="", description="异步任务轮询专用接口（如视频轮询）")
    is_active: bool = Field(default=True, description="是否激活")
    is_default: bool = Field(default=False, description="是否设为默认 Provider")
    sort_order: int = Field(default=0, description="排序权重（越小越靠前）")


class ProviderUpdateRequest(BaseModel):
    """更新 Provider 请求体（所有字段可选）"""
    name: Optional[str] = Field(default=None, description="Provider 名称")
    base_url: Optional[str] = Field(default=None, description="API 基础地址")
    api_key: Optional[str] = Field(default=None, description="API Key（留空表示不修改）")
    poll_url: Optional[str] = Field(default=None, description="异步任务轮询接口")
    is_active: Optional[bool] = Field(default=None, description="是否激活")
    is_default: Optional[bool] = Field(default=None, description="是否设为默认 Provider")
    sort_order: Optional[int] = Field(default=None, description="排序权重")


class ProviderResponse(BaseModel):
    """Provider 响应体（不含明文 API Key）"""
    id: int
    name: str
    base_url: str
    api_key: str = Field(description="API Key 脱敏后的展示值，如 sk-a****b123")
    poll_url: str = ""
    is_active: bool
    is_default: bool
    sort_order: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ProviderListResponse(BaseModel):
    """Provider 列表响应"""
    total: int
    items: List[ProviderResponse]


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
    capabilities: Optional[List[str]] = Field(default=None, description="能力标签列表")
    sort_order: int = Field(default=0, description="排序权重")


class ModelUpdateRequest(BaseModel):
    """更新模型定义请求体（所有字段可选）"""
    display_name: Optional[str] = Field(default=None, description="显示名称")
    model_type: Optional[str] = Field(default=None, description="模型类型")
    provider_name: Optional[str] = Field(default=None, description="供应商名称")
    capabilities: Optional[List[str]] = Field(default=None, description="能力标签列表")
    is_active: Optional[bool] = Field(default=None, description="是否激活")
    sort_order: Optional[int] = Field(default=None, description="排序权重")


class ModelDefinitionResponse(BaseModel):
    """模型定义响应体（含管理字段）"""
    id: int
    provider_id: int
    model_id: str
    display_name: str = ""
    type: str
    provider_name: str = ""
    capabilities: List[str] = Field(default_factory=list)
    is_active: bool
    is_custom: bool
    sort_order: int

    class Config:
        from_attributes = True


class ModelListResponse(BaseModel):
    """模型定义列表响应"""
    total: int
    items: List[ModelDefinitionResponse]


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
    error: Optional[str] = Field(default=None, description="同步失败时的错误信息")


class SyncAllResponse(BaseModel):
    """同步所有 Provider 模型的响应"""
    results: List[SyncModelsResponse]
