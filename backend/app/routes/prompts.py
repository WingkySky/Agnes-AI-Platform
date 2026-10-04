# =====================================================
# 提示词优化路由 — POST /api/prompts/optimize
# 登录用户可用；routes 层轻量（入参校验 → service → 统一响应）
# =====================================================

from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.response import ok
from app.core.security import get_current_user
from app.models.user import User
from app.services import prompt_optimize_service as svc

router = APIRouter(prefix="/prompts", tags=["提示词优化"])


class PromptOptimizeContext(BaseModel):
    """优化上下文：model-adapt 按模型注入方言规则；reference 注入参考素材名"""

    model_id: str = ""
    reference_asset_names: List[str] = []


class PromptOptimizeRequest(BaseModel):
    prompt: str
    mode: Literal["expand", "refine", "style", "model-adapt", "reference"] = "refine"
    target: Literal["image", "video"] = "image"
    context: Optional[PromptOptimizeContext] = None


@router.post("/optimize", summary="优化提示词（结构化返回正负提示词）")
async def optimize_prompt_route(
    payload: PromptOptimizeRequest,
    current_user: User = Depends(get_current_user),
):
    del current_user  # 仅登录门槛
    prompt = payload.prompt.strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="提示词不能为空")
    context = payload.context or PromptOptimizeContext()
    try:
        result = await svc.optimize_prompt(
            prompt=prompt,
            mode=payload.mode,
            target=payload.target,
            model_id=context.model_id,
            reference_names=context.reference_asset_names,
        )
    except RuntimeError as e:
        # LLM 异常 / 两次解析失败：上游问题映射 502
        raise HTTPException(status_code=502, detail=str(e))
    return ok(data=result)
