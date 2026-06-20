# =====================================================
# Provider 与模型管理接口路由
# 提供前端配置页面所需的所有 CRUD 接口：
#   - Provider 增删改查
#   - 模型定义增删改查（含自定义模型）
#   - 模型同步（调用 Provider 的 /models API）
# =====================================================

from fastapi import APIRouter, HTTPException

from app.schemas.providers import (
    ProviderCreateRequest,
    ProviderUpdateRequest,
    ProviderResponse,
    ProviderListResponse,
    CustomModelCreateRequest,
    ModelUpdateRequest,
    ModelDefinitionResponse,
    ModelListResponse,
    SyncModelsResponse,
    SyncAllResponse,
)
from app.services.provider_registry import provider_registry

router = APIRouter()


# =====================================================
# Provider 管理接口
# =====================================================

@router.get("/providers", response_model=ProviderListResponse, summary="列出所有 Provider")
async def list_providers():
    """列出所有 Provider（API Key 脱敏显示）"""
    items = await provider_registry.list_providers(include_key=False)
    return ProviderListResponse(total=len(items), items=items)


@router.post("/providers", response_model=ProviderResponse, summary="创建 Provider")
async def create_provider(req: ProviderCreateRequest):
    """创建新的 API Provider"""
    if not req.name.strip():
        raise HTTPException(status_code=400, detail="Provider 名称不能为空")
    if not req.base_url.strip():
        raise HTTPException(status_code=400, detail="base_url 不能为空")
    if not req.api_key.strip():
        raise HTTPException(status_code=400, detail="api_key 不能为空")

    provider = await provider_registry.create_provider(
        name=req.name.strip(),
        base_url=req.base_url.strip(),
        api_key=req.api_key.strip(),
        poll_url=req.poll_url.strip(),
        is_active=req.is_active,
        is_default=req.is_default,
        sort_order=req.sort_order,
    )
    # 返回脱敏后的 Provider 信息
    from app.core.security import mask_api_key, decrypt_api_key
    decrypted = decrypt_api_key(provider.api_key_encrypted or "")
    return ProviderResponse(
        id=provider.id,
        name=provider.name,
        base_url=provider.base_url,
        api_key=mask_api_key(decrypted),
        poll_url=provider.poll_url or "",
        is_active=provider.is_active,
        is_default=provider.is_default,
        sort_order=provider.sort_order,
        created_at=provider.created_at,
        updated_at=provider.updated_at,
    )


@router.put("/providers/{provider_id}", response_model=ProviderResponse, summary="更新 Provider")
async def update_provider(provider_id: int, req: ProviderUpdateRequest):
    """更新 Provider 配置（api_key 留空表示不修改）"""
    provider = await provider_registry.update_provider(
        provider_id=provider_id,
        name=req.name,
        base_url=req.base_url,
        api_key=req.api_key,
        poll_url=req.poll_url,
        is_active=req.is_active,
        is_default=req.is_default,
        sort_order=req.sort_order,
    )
    if provider is None:
        raise HTTPException(status_code=404, detail=f"Provider {provider_id} 不存在")

    from app.core.security import mask_api_key, decrypt_api_key
    decrypted = decrypt_api_key(provider.api_key_encrypted or "")
    return ProviderResponse(
        id=provider.id,
        name=provider.name,
        base_url=provider.base_url,
        api_key=mask_api_key(decrypted),
        poll_url=provider.poll_url or "",
        is_active=provider.is_active,
        is_default=provider.is_default,
        sort_order=provider.sort_order,
        created_at=provider.created_at,
        updated_at=provider.updated_at,
    )


@router.delete("/providers/{provider_id}", summary="删除 Provider")
async def delete_provider(provider_id: int):
    """删除 Provider（级联删除其下所有模型定义）"""
    success = await provider_registry.delete_provider(provider_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Provider {provider_id} 不存在")
    return {"status": "success", "message": f"Provider {provider_id} 已删除"}


# =====================================================
# 模型定义管理接口
# =====================================================

@router.get("/providers/{provider_id}/models", response_model=ModelListResponse, summary="列出指定 Provider 的模型")
async def list_provider_models(provider_id: int):
    """列出指定 Provider 下的所有模型定义（包括未激活和自定义）"""
    items = await provider_registry.list_models(provider_id=provider_id)
    return ModelListResponse(total=len(items), items=items)


@router.get("/models", response_model=ModelListResponse, summary="列出所有模型定义")
async def list_all_models_admin():
    """列出所有 Provider 的所有模型定义（管理视图，包括未激活和自定义）"""
    items = await provider_registry.list_models(provider_id=None)
    return ModelListResponse(total=len(items), items=items)


@router.post("/models", response_model=ModelDefinitionResponse, summary="添加自定义模型")
async def add_custom_model(req: CustomModelCreateRequest):
    """添加用户自定义模型（is_custom=True，同步时不会被覆盖）"""
    if not req.model_id.strip():
        raise HTTPException(status_code=400, detail="model_id 不能为空")

    # 检查模型是否已存在
    existing = await provider_registry.get_model_definition(req.model_id.strip())
    if existing is not None:
        raise HTTPException(status_code=409, detail=f"模型 {req.model_id} 已存在")

    defn = await provider_registry.add_custom_model(
        provider_id=req.provider_id,
        model_id=req.model_id.strip(),
        display_name=req.display_name.strip(),
        model_type=req.model_type.strip(),
        provider_name=req.provider_name.strip(),
        capabilities=req.capabilities,
        sort_order=req.sort_order,
    )
    return ModelDefinitionResponse(
        id=defn.id,
        provider_id=defn.provider_id,
        model_id=defn.model_id,
        display_name=defn.display_name or "",
        type=defn.type,
        provider_name=defn.provider_name or "",
        capabilities=defn.capabilities or [],
        is_active=defn.is_active,
        is_custom=defn.is_custom,
        sort_order=defn.sort_order,
    )


@router.put("/models/{model_id}", response_model=ModelDefinitionResponse, summary="更新模型定义")
async def update_model(model_id: str, req: ModelUpdateRequest):
    """更新模型定义的展示信息或激活状态"""
    defn = await provider_registry.update_model(
        model_id=model_id,
        display_name=req.display_name,
        model_type=req.model_type,
        provider_name=req.provider_name,
        capabilities=req.capabilities,
        is_active=req.is_active,
        sort_order=req.sort_order,
    )
    if defn is None:
        raise HTTPException(status_code=404, detail=f"模型 {model_id} 不存在")

    return ModelDefinitionResponse(
        id=defn.id,
        provider_id=defn.provider_id,
        model_id=defn.model_id,
        display_name=defn.display_name or "",
        type=defn.type,
        provider_name=defn.provider_name or "",
        capabilities=defn.capabilities or [],
        is_active=defn.is_active,
        is_custom=defn.is_custom,
        sort_order=defn.sort_order,
    )


@router.delete("/models/{model_id}", summary="删除模型定义")
async def delete_model(model_id: str):
    """删除模型定义（包括自定义和 API 同步的）"""
    success = await provider_registry.delete_model(model_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"模型 {model_id} 不存在")
    return {"status": "success", "message": f"模型 {model_id} 已删除"}


# =====================================================
# 模型同步接口
# =====================================================

@router.post(
    "/providers/{provider_id}/sync-models",
    response_model=SyncModelsResponse,
    summary="同步指定 Provider 的模型列表",
)
async def sync_provider_models(provider_id: int):
    """
    调用指定 Provider 的 /models API，同步模型列表到数据库。
    - 新增的模型自动添加
    - 用户自定义模型不会被覆盖或删除
    - API 中已不存在的非自定义模型会被软删除（is_active=False）
    """
    try:
        result = await provider_registry.sync_provider_models(provider_id)
        return SyncModelsResponse(provider_id=provider_id, **result)
    except RuntimeError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"同步失败: {e}")


@router.post(
    "/providers/sync-all-models",
    response_model=SyncAllResponse,
    summary="同步所有 Provider 的模型列表",
)
async def sync_all_providers_models():
    """同步所有已激活 Provider 的模型列表"""
    results = await provider_registry.sync_all_providers()
    return SyncAllResponse(results=[SyncModelsResponse(**r) for r in results])
