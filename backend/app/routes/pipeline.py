# =====================================================
# 流水线模板 / 风格 / 剧本模板 / 资产库 路由
#
# 项目制创作（Project）已迁移到 /api/projects/*，本文件仅保留模板市场相关 API
#
# API 列表:
#   /api/pipeline/templates            - 获取模板列表
#   /api/pipeline/templates/{id}       - 获取模板详情
#   /api/pipeline/templates             - 创建自定义模板 (POST)
#   /api/pipeline/templates/{id}        - 更新模板 (PUT) / 删除模板 (DELETE)
#   /api/pipeline/templates/{id}/estimate-credits - 预估积分
#   /api/pipeline/templates/export      - 导出模板为 JSON (GET)
#   /api/pipeline/templates/import      - 批量导入模板 (POST)
#   /api/pipeline/styles               - 风格预设列表
#   /api/pipeline/styles/{id}          - 风格预设详情
#   /api/pipeline/script-templates     - 剧本模板列表
#   /api/pipeline/script-templates/{id} - 剧本模板详情
#   /api/pipeline/assets               - 资产库列表
#   /api/pipeline/assets/{id}          - 资产详情
#   /api/pipeline/template-scenarios   - 模板场景预设列表
#   /api/pipeline/templates/from-scenario - 从场景预设创建模板
#   /api/pipeline/available-models     - 获取可用的模型列表
# =====================================================

import logging
from datetime import datetime
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy import select, func, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_db
from app.core.security import get_current_user, get_current_user_optional
from app.models.user import User
from app.models.pipeline import PipelineTemplate, StylePreset, ScriptTemplate
from app.models.asset import Asset
from app.models.model_definition import ModelDefinition
from app.schemas.pipeline import (
    PipelineTemplateOut,
    PipelineTemplateCreate,
    PipelineTemplateUpdate,
    PipelineTemplateRevisionOut,
    CreditEstimateOut,
    CreditEstimateRequest,
    TemplateFromScenarioRequest,
)
from app.schemas.assets import (
    StylePresetOut,
    ScriptTemplateOut,
    AssetOut,
    AssetSaveFromGenerationRequest,
)
from app.services.pipeline import (
    list_templates,
    get_template_by_id,
    validate_steps_config,
)
from app.services.pipeline import template_service
from app.services.pipeline import template_scenarios
from app.services import style_service
from app.services import script_template_service
from app.services import asset_library

logger = logging.getLogger("agnes_platform")
router = APIRouter()


# =====================================================
# 流水线模板 API
# =====================================================

@router.get("/pipeline/templates", summary="获取流水线模板列表")
async def get_pipeline_templates(
    category: Optional[str] = None,
    search: Optional[str] = None,
    scope: str = Query("market", description="列表范围：market 模板市场 / my 我的模板"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_async_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """
    获取流水线模板列表。

    - scope=market（默认）：模板市场，返回内置模板 + 审核通过的公开模板
    - scope=my：我的模板，返回当前用户创建的所有模板（需登录）
    """
    query = select(PipelineTemplate)
    filters = []
    if category:
        filters.append(PipelineTemplate.category == category)
    if search:
        search_pattern = f"%{search}%"
        filters.append(or_(
            PipelineTemplate.name.ilike(search_pattern),
            PipelineTemplate.description.ilike(search_pattern),
            PipelineTemplate.key.ilike(search_pattern),
        ))

    if scope == "my":
        # 我的模板：必须登录，只看自己创建的
        if not current_user:
            raise HTTPException(status_code=401, detail="请先登录")
        filters.append(PipelineTemplate.author_id == current_user.id)
        filters.append(PipelineTemplate.is_builtin == False)  # noqa: E712
    else:
        # 模板市场：内置 + 审核通过的公开模板
        filters.append(or_(
            PipelineTemplate.is_builtin == True,  # noqa: E712
            and_(PipelineTemplate.is_public == True, PipelineTemplate.is_approved == True)  # noqa: E712
        ))

    if filters:
        query = query.where(*filters)

    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    query = query.order_by(
        PipelineTemplate.is_builtin.desc(),
        PipelineTemplate.use_count.desc(),
        PipelineTemplate.id.asc(),
    ).offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    items = list(result.scalars().all())

    return {
        "items": [PipelineTemplateOut.model_validate(item) for item in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/pipeline/templates/{template_id}", summary="获取流水线模板详情")
async def get_pipeline_template_detail(
    template_id: int,
    db: AsyncSession = Depends(get_async_db),
    _current_user: Optional[User] = Depends(get_current_user_optional),
):
    """获取单个流水线模板的详细配置"""
    template = await get_template_by_id(db, template_id)
    if not template:
        raise HTTPException(status_code=404, detail="流水线模板不存在")

    return PipelineTemplateOut.model_validate(template)


@router.post("/pipeline/templates", summary="创建自定义流水线模板")
async def create_pipeline_template(
    req: PipelineTemplateCreate,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """创建用户自定义流水线模板（非内置模板，作者为当前用户）"""
    tpl = await template_service.create_template(
        db, req, author_id=current_user.id, is_builtin=False
    )
    return PipelineTemplateOut.model_validate(tpl)


@router.put("/pipeline/templates/{template_id}", summary="编辑流水线模板")
async def update_pipeline_template(
    template_id: int,
    req: PipelineTemplateUpdate,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """
    编辑流水线模板。

    - admin 可编辑任意模板（含内置模板，直接生效）
    - 作者可编辑自己的非内置模板
    - 公开已审核非内置模板被编辑 → 走 draft 流程（生成 pending revision + 敏感词预筛）
    - 其他情况直接改原模板字段
    """
    # 计算是否为 admin（与项目其他路由保持一致：role == 'admin' 或 is_admin == True）
    is_admin = bool(getattr(current_user, "is_admin", False)) or current_user.role == "admin"
    tpl = await template_service.update_template(
        db, template_id, req, user_id=current_user.id, is_admin=is_admin
    )
    return PipelineTemplateOut.model_validate(tpl)


@router.get("/pipeline/templates/{template_id}/revision", summary="获取模板的修订草稿")
async def get_template_revision(
    template_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """
    获取公开模板的 pending revision（编辑器进入时拉取，恢复未保存草稿）。

    - 仅作者或 admin 可访问
    - 没有 pending revision 时返回 404
    """
    tpl = await template_service.get_template_by_id(db, template_id)
    if not tpl:
        raise HTTPException(status_code=404, detail="流水线模板不存在")

    is_admin = bool(getattr(current_user, "is_admin", False)) or current_user.role == "admin"
    if tpl.author_id != current_user.id and not is_admin:
        raise HTTPException(status_code=403, detail="无权查看此模板的修订")

    revision = await template_service.get_pending_revision(db, template_id)
    if not revision:
        raise HTTPException(status_code=404, detail="该模板暂无待审核的修订")
    return PipelineTemplateRevisionOut.model_validate(revision)


@router.post("/pipeline/templates/{template_id}/thumbnail/ai-generate", summary="AI 生成模板缩略图")
async def generate_template_thumbnail_ai(
    template_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """
    按模板 name + description + tags 调用 Agnes AI 生图接口生成缩略图。

    - 仅作者或 admin 可调用
    - 生成后写入 tpl.thumbnail_url，返回新 URL
    - 复用现有 AgnesAIClient.create_image，不新写底层
    """
    tpl = await template_service.get_template_by_id(db, template_id)
    if not tpl:
        raise HTTPException(status_code=404, detail="流水线模板不存在")

    is_admin = bool(getattr(current_user, "is_admin", False)) or current_user.role == "admin"
    if tpl.author_id != current_user.id and not is_admin:
        raise HTTPException(status_code=403, detail="无权生成此模板的缩略图")

    # 后端拼装 prompt：竖版 4:3 风格化插画缩略图，避免文字
    tags_text = "、".join(tpl.tags or [])
    prompt = (
        f"竖版 4:3 风格化插画缩略图，主题：{tpl.name or ''}，"
        f"{tpl.description or ''}，标签：{tags_text}，"
        f"适合作为创意工坊模板封面，避免文字"
    )

    from app.services.agnes_client import agnes_client
    from app.services.model_registry import get_models_by_type

    # 选取第一个可用图片模型
    try:
        image_models = await get_models_by_type("image")
        model_id = image_models[0].id if image_models else ""
    except Exception:
        model_id = ""
    if not model_id:
        raise HTTPException(status_code=500, detail="无可用图片生成模型")

    # 调用 Agnes 图像生成（竖版 4:3 → 768x1024）
    try:
        resp = await agnes_client.create_image(
            prompt=prompt,
            model=model_id,
            size="768x1024",
            response_format="url",
        )
    except Exception as e:
        logger.warning("AI 生成模板缩略图失败: %s", e)
        raise HTTPException(status_code=500, detail=f"AI 生图失败：{e}")

    # 解析返回的图片 URL
    image_url = None
    try:
        data_list = resp.get("data", []) if isinstance(resp, dict) else []
        if isinstance(data_list, list) and data_list:
            image_url = data_list[0].get("url")
        if not image_url and isinstance(resp, dict) and resp.get("url"):
            image_url = resp["url"]
    except Exception as e:
        logger.warning("解析 AI 生图响应失败: %s", e)

    if not image_url:
        raise HTTPException(status_code=500, detail="AI 生图未返回有效 URL")

    # 写入模板 thumbnail_url
    tpl.thumbnail_url = image_url
    await db.commit()

    return {"thumbnail_url": image_url, "template_id": template_id}


@router.delete("/pipeline/templates/{template_id}", summary="删除流水线模板")
async def delete_pipeline_template(
    template_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """删除自己的流水线模板（内置模板不可删除）"""
    await template_service.delete_template(
        db, template_id, user_id=current_user.id
    )
    return {"message": "删除成功", "template_id": template_id}


@router.post("/pipeline/templates/{template_id}/submit-public", summary="提交模板到公开市场审核")
async def submit_template_public(
    template_id: int,
    payload: Dict[str, Any] = None,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """
    将模板提交到公开市场审核。

    - 只能提交自己的非内置模板
    - 已被驳回的模板不可再次提交（硬约束：被驳回内容不能再公开）
    - 提交前进行敏感词预筛，命中则直接驳回
    - 提交后 is_public=True, is_approved=False, is_rejected=False
    """
    result = await db.execute(
        select(PipelineTemplate).filter(PipelineTemplate.id == template_id)
    )
    tpl = result.scalar_one_or_none()
    if not tpl:
        raise HTTPException(status_code=404, detail="模板不存在")
    if tpl.is_builtin:
        raise HTTPException(status_code=400, detail="内置模板不可提交公开")
    if tpl.author_id != current_user.id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="只能提交自己的模板")
    if tpl.is_rejected:
        raise HTTPException(status_code=403, detail="该模板已被驳回，不可再次提交公开")
    if tpl.is_public and tpl.is_approved:
        raise HTTPException(status_code=400, detail="模板已在公开市场中")

    submit_reason = (payload or {}).get("reason") or ""

    # ---------- 敏感词预筛 ----------
    check_text = " ".join([
        tpl.name or "",
        tpl.description or "",
        " ".join(tpl.tags or []),
        submit_reason,
    ])
    from app.services.moderation_service import check_sensitive_text
    hit, hit_words = await check_sensitive_text(db, check_text)
    if hit:
        # 命中敏感词：直接驳回
        tpl.is_public = False
        tpl.is_approved = False
        tpl.is_rejected = True
        tpl.reject_reason = f"AI 预筛命中敏感词：{', '.join(hit_words[:5])}"
        tpl.submit_reason = submit_reason
        await db.commit()
        return {
            "message": "提交未通过 AI 预筛",
            "rejected": True,
            "hit_words": hit_words,
            "template_id": template_id,
        }

    # 提交审核
    tpl.is_public = True
    tpl.is_approved = False
    tpl.is_rejected = False
    tpl.submit_reason = submit_reason
    tpl.reject_reason = None
    await db.commit()

    return {
        "message": "已提交审核，等待管理员处理",
        "template_id": template_id,
        "is_public": True,
        "is_approved": False,
    }


@router.post("/pipeline/templates/{template_id}/cancel-public", summary="取消模板公开")
async def cancel_template_public(
    template_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """
    取消模板的公开状态（从市场下架，仅自己可见）。

    - 只能操作自己的模板
    - 取消后 is_public=False, is_approved=False, is_rejected 保持不变
    """
    result = await db.execute(
        select(PipelineTemplate).filter(PipelineTemplate.id == template_id)
    )
    tpl = result.scalar_one_or_none()
    if not tpl:
        raise HTTPException(status_code=404, detail="模板不存在")
    if tpl.is_builtin:
        raise HTTPException(status_code=400, detail="内置模板不可取消公开")
    if tpl.author_id != current_user.id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="只能操作自己的模板")

    tpl.is_public = False
    tpl.is_approved = False
    await db.commit()

    return {
        "message": "已取消公开",
        "template_id": template_id,
        "is_public": False,
    }


@router.post("/pipeline/templates/{template_id}/estimate-credits", summary="预估积分消耗")
async def estimate_pipeline_credits(
    template_id: int,
    req: CreditEstimateRequest,
    db: AsyncSession = Depends(get_async_db),
    _current_user: Optional[User] = Depends(get_current_user_optional),
):
    """预估流水线运行需要消耗的积分（粗略估算）"""
    # wizard_chain 模式下积分预估简化为模板 estimated_credits 字段
    tpl = await get_template_by_id(db, template_id)
    if not tpl:
        raise HTTPException(status_code=404, detail="流水线模板不存在")
    estimated = tpl.estimated_credits or 0
    return CreditEstimateOut(total_credits=estimated, steps=[])


# =====================================================
# 模板导入/导出 API
# =====================================================

# 导出文件格式版本号，用于后续兼容性处理
TEMPLATE_EXPORT_VERSION = "1.0"

# 模板导出时需要排除的字段（运行时字段，导入时由后端重新生成）
_TEMPLATE_EXPORT_EXCLUDE_FIELDS = {
    "id", "author_id", "use_count", "likes_count",
    "created_at", "updated_at", "is_builtin",
}


@router.get("/pipeline/export/templates", summary="导出流水线模板为 JSON")
async def export_pipeline_templates(
    template_ids: Optional[str] = Query(
        None, description="要导出的模板 ID 列表（逗号分隔），不传则导出所有可见模板"
    ),
    include_script: bool = Query(True, description="是否包含关联的剧本模板"),
    include_style: bool = Query(
        False, description="是否包含模板内引用的风格预设（仅对 inputs_config 中 style_select 类型有效）"
    ),
    db: AsyncSession = Depends(get_async_db),
    _current_user: User = Depends(get_current_user),
):
    """
    导出流水线模板为 JSON（导出是只读操作，所有可见模板均可导出）。

    - 默认导出所有可见模板（内置 + 公开），template_ids 指定时仅导出指定 ID 的模板
    - include_script=true 时一并导出关联的 ScriptTemplate
    - include_style=true 时一并导出 inputs_config 中引用的 StylePreset
    - 导入时所有模板都会变成当前用户的自定义模板（is_builtin=False, is_public=False）
    """
    # 构建查询：所有可见模板（内置 + 公开 + 当前用户自己的）
    query = select(PipelineTemplate).filter(
        or_(
            PipelineTemplate.is_builtin == True,
            PipelineTemplate.is_public == True,
            PipelineTemplate.author_id == _current_user.id,
        )  # noqa: E712
    )

    # 按指定 ID 过滤
    selected_ids: List[int] = []
    if template_ids:
        for raw in template_ids.split(","):
            raw = raw.strip()
            if raw.isdigit():
                selected_ids.append(int(raw))
        if selected_ids:
            query = query.filter(PipelineTemplate.id.in_(selected_ids))

    result = await db.execute(query.order_by(PipelineTemplate.id.asc()))
    templates = list(result.scalars().all())

    if not templates:
        raise HTTPException(status_code=404, detail="没有可导出的模板")

    # 序列化模板（剔除运行时字段）
    templates_data: List[Dict[str, Any]] = []
    script_ids_collected: set = set()
    style_ids_collected: set = set()
    for tpl in templates:
        tpl_dict = _serialize_template(tpl)
        templates_data.append(tpl_dict)
        # 收集关联的剧本模板 ID
        if tpl.script_template_id:
            script_ids_collected.add(tpl.script_template_id)
        # 收集 inputs_config 中 style_select 引用的风格预设 ID
        if include_style:
            for cfg in (tpl.inputs_config or []):
                if isinstance(cfg, dict) and cfg.get("type") == "style_select":
                    default_val = cfg.get("default")
                    if isinstance(default_val, int):
                        style_ids_collected.add(default_val)

    # 加载关联的剧本模板
    script_templates_data: List[Dict[str, Any]] = []
    if include_script and script_ids_collected:
        scripts_result = await db.execute(
            select(ScriptTemplate).filter(ScriptTemplate.id.in_(list(script_ids_collected)))
        )
        for st in scripts_result.scalars().all():
            script_templates_data.append(_serialize_script_template(st))

    # 加载关联的风格预设
    style_presets_data: List[Dict[str, Any]] = []
    if include_style and style_ids_collected:
        styles_result = await db.execute(
            select(StylePreset).filter(StylePreset.id.in_(list(style_ids_collected)))
        )
        for sp in styles_result.scalars().all():
            style_presets_data.append(_serialize_style_preset(sp))

    return {
        "version": TEMPLATE_EXPORT_VERSION,
        "exported_at": datetime.utcnow().isoformat() + "Z",
        "templates": templates_data,
        "script_templates": script_templates_data,
        "style_presets": style_presets_data,
    }


@router.get("/pipeline/templates/sample", summary="下载示例模板 JSON")
async def get_pipeline_template_sample():
    """
    返回一份最小可用的示例模板 JSON（标准漫剧流程）。

    用途：用户在导入对话框点"下载示例模板"时调用，下载后照着改即可。
    无需鉴权（公开接口，方便未登录用户也能获取格式参考）。
    返回的 JSON 结构与 /pipeline/export/templates 一致，可直接作为
    /pipeline/templates/import 的 payload.data 字段导入。
    """
    return template_service.get_sample_template()


@router.post("/pipeline/templates/validate", summary="无副作用校验模板结构")
async def validate_pipeline_template(
    payload: Dict[str, Any],
    _current_user: User = Depends(get_current_user),
):
    """
    无副作用校验模板结构（不落库、不启动运行）。

    请求体：完整模板 JSON（与 create/update 接口的 body 结构一致，不含 id）。

    校验项:
      - steps_config 每个 step.type 必须命中后端支持的类型清单
      - step.key 必须非空且在同模板内唯一
      - depends_on 引用的 key 必须存在于同模板内
      - from_step / audio_from_step / subtitle_from_step 同样校验存在性

    返回: { is_valid: bool, errors: [{step_key, field, reason}] }
    """
    is_valid, errors = template_service.validate_template(payload or {})
    return {"is_valid": is_valid, "errors": errors}


@router.post("/pipeline/templates/import", summary="批量导入流水线模板")
async def import_pipeline_templates(
    payload: Dict[str, Any],
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """
    批量导入流水线模板（JSON 文件内容）。

    请求体格式：
    {
      "data": { ... 导出文件内容 ... },
      "conflict_strategy": "rename" | "skip" | "overwrite",  // 冲突处理策略
      "import_mode": "private" | "public" | "builtin"         // 导入模式（仅管理员可选 public/builtin）
    }

    返回：{ imported, skipped, renamed, overwritten, items }
    - 冲突检测基于模板 key（unique）
    - rename：自动追加 " (导入)" 后缀（key 追加 _imported_N）
    - skip：跳过冲突项
    - overwrite：覆盖同 key 模板（仅限自己的非内置模板）
    - import_mode:
        - private（默认，所有用户可用）：导入为私有模板
        - public（仅管理员）：导入后直接设为公开并审核通过
        - builtin（仅管理员）：导入为内置模板（无作者）
    """
    data = payload.get("data") or {}
    conflict_strategy = payload.get("conflict_strategy", "rename")
    import_mode = payload.get("import_mode", "private")

    if conflict_strategy not in ("rename", "skip", "overwrite"):
        raise HTTPException(status_code=400, detail="conflict_strategy 必须是 rename/skip/overwrite 之一")
    if import_mode not in ("private", "public", "builtin"):
        raise HTTPException(status_code=400, detail="import_mode 必须是 private/public/builtin 之一")

    # 权限校验：public 和 builtin 模式仅管理员可用
    is_admin = bool(getattr(current_user, "is_admin", False) or (current_user.role == "admin"))
    if import_mode in ("public", "builtin") and not is_admin:
        raise HTTPException(status_code=403, detail="仅管理员可使用 public/builtin 导入模式")

    # 根据 import_mode 确定模板的初始状态
    def _get_template_flags() -> Dict[str, Any]:
        if import_mode == "builtin":
            return {"is_builtin": True, "is_public": False, "is_approved": True, "author_id": None}
        elif import_mode == "public":
            return {"is_builtin": False, "is_public": True, "is_approved": True, "author_id": current_user.id}
        else:  # private
            return {"is_builtin": False, "is_public": False, "is_approved": False, "author_id": current_user.id}

    flags = _get_template_flags()

    templates_in = data.get("templates") or []
    scripts_in = data.get("script_templates") or []
    styles_in = data.get("style_presets") or []

    if not isinstance(templates_in, list) or not templates_in:
        raise HTTPException(status_code=400, detail="文件中未找到有效的 templates 字段")

    imported: List[Dict[str, Any]] = []
    skipped: List[str] = []
    renamed: List[str] = []
    overwritten: List[str] = []
    errors: List[Dict[str, Any]] = []  # 校验失败的模板明细

    # 第一步：导入剧本模板（建立 key→new_id 映射，供模板引用时重映射）
    script_key_to_id: Dict[str, int] = {}
    for st_data in scripts_in:
        st_key = st_data.get("key")
        if not st_key:
            skipped.append("(剧本模板缺 key)")
            continue
        # 检查同 key 是否已存在
        existing_st = await db.execute(
            select(ScriptTemplate).filter(ScriptTemplate.key == st_key)
        )
        existing_st_obj = existing_st.scalar_one_or_none()
        if existing_st_obj:
            # 已存在的剧本模板复用，不重复创建
            script_key_to_id[st_key] = existing_st_obj.id
            continue
        try:
            new_st = ScriptTemplate(
                key=st_key,
                name=st_data.get("name", st_key),
                description=st_data.get("description"),
                category=st_data.get("category", "drama"),
                structure=st_data.get("structure", "three_act"),
                prompt_template=st_data.get("prompt_template", ""),
                output_schema=st_data.get("output_schema") or {},
                variables_schema=st_data.get("variables_schema"),
                scenes_min=st_data.get("scenes_min", 3),
                scenes_max=st_data.get("scenes_max", 20),
                default_scene_duration=st_data.get("default_scene_duration", 5),
                output_format=st_data.get("output_format", "json"),
                tags=st_data.get("tags") or [],
                is_builtin=False,
                is_public=False,
                author_id=current_user.id,
            )
            db.add(new_st)
            await db.flush()
            script_key_to_id[st_key] = new_st.id
        except Exception as e:
            logger.warning("导入剧本模板 %s 失败: %s", st_key, e)
            skipped.append(f"剧本模板 {st_key}")

    # 第二步：导入风格预设（建立 key→new_id 映射）
    style_key_to_id: Dict[str, int] = {}
    for sp_data in styles_in:
        sp_key = sp_data.get("key")
        if not sp_key:
            skipped.append("(风格预设缺 key)")
            continue
        existing_sp = await db.execute(
            select(StylePreset).filter(StylePreset.key == sp_key)
        )
        existing_sp_obj = existing_sp.scalar_one_or_none()
        if existing_sp_obj:
            style_key_to_id[sp_key] = existing_sp_obj.id
            continue
        try:
            new_sp = StylePreset(
                key=sp_key,
                name=sp_data.get("name", sp_key),
                description=sp_data.get("description"),
                category=sp_data.get("category", "art_style"),
                visual_prefix=sp_data.get("visual_prefix"),
                lighting=sp_data.get("lighting"),
                color_palette=sp_data.get("color_palette"),
                quality_suffix=sp_data.get("quality_suffix"),
                negative_prompt=sp_data.get("negative_prompt"),
                camera_language=sp_data.get("camera_language"),
                mood_keywords=sp_data.get("mood_keywords"),
                preview_image=sp_data.get("preview_image"),
                tags=sp_data.get("tags") or [],
                is_builtin=False,
                is_public=False,
                author_id=current_user.id,
            )
            db.add(new_sp)
            await db.flush()
            style_key_to_id[sp_key] = new_sp.id
        except Exception as e:
            logger.warning("导入风格预设 %s 失败: %s", sp_key, e)
            skipped.append(f"风格预设 {sp_key}")

    # 第三步：导入流水线模板（按 key 处理冲突）
    for tpl_data in templates_in:
        tpl_key = tpl_data.get("key")
        tpl_name = tpl_data.get("name", "未命名")
        if not tpl_key:
            skipped.append(f"模板 {tpl_name}（缺 key）")
            continue

        # 校验模板结构
        is_valid, validation_errors = template_service.validate_template(tpl_data)
        if not is_valid:
            errors.append(
                {
                    "template_key": tpl_key,
                    "template_name": tpl_name,
                    "reasons": [
                        f"[{e.get('field')}] {e.get('reason')}"
                        for e in validation_errors
                    ],
                }
            )
            logger.warning(
                "导入模板 %s 校验失败，跳过: %s",
                tpl_key,
                validation_errors,
            )
            continue

        # 查询同 key 是否已存在
        existing_q = await db.execute(
            select(PipelineTemplate).filter(PipelineTemplate.key == tpl_key)
        )
        existing_tpl = existing_q.scalar_one_or_none()

        # 重映射剧本模板 ID
        script_template_id = None
        if tpl_data.get("script_template_id"):
            st_key = tpl_data.get("script_template_key")
            if st_key and st_key in script_key_to_id:
                script_template_id = script_key_to_id[st_key]

        # 重映射 inputs_config 中 style_select 的 default（原 id → 新 id）
        inputs_config = _remap_style_ids_in_inputs(
            tpl_data.get("inputs_config") or [],
            styles_in,
            style_key_to_id,
        )

        # 构造用于创建/覆盖的模板数据
        def _build_template_data(final_key: str, final_name: str) -> PipelineTemplate:
            return PipelineTemplate(
                key=final_key,
                name=final_name,
                description=tpl_data.get("description"),
                category=tpl_data.get("category", "drama"),
                thumbnail_url=tpl_data.get("thumbnail_url"),
                inputs_config=inputs_config,
                steps_config=tpl_data.get("steps_config") or [],
                output_mapping=tpl_data.get("output_mapping"),
                script_template_id=script_template_id,
                estimated_credits=tpl_data.get("estimated_credits", 100),
                estimated_time_minutes=tpl_data.get("estimated_time_minutes", 10),
                tags=tpl_data.get("tags") or [],
                is_builtin=flags["is_builtin"],
                is_public=flags["is_public"],
                is_approved=flags["is_approved"],
                author_id=flags["author_id"],
            )

        if existing_tpl is None:
            # 无冲突：直接创建
            try:
                new_tpl = _build_template_data(tpl_key, tpl_name)
                db.add(new_tpl)
                await db.flush()
                imported.append({"id": new_tpl.id, "key": new_tpl.key, "name": new_tpl.name})
            except Exception as e:
                logger.warning("导入模板 %s 失败: %s", tpl_key, e)
                skipped.append(tpl_name)
        else:
            # 冲突处理
            if existing_tpl.is_builtin:
                # 内置模板不可覆盖，跳过
                skipped.append(f"{tpl_name}（内置模板不可覆盖）")
                continue
            if existing_tpl.author_id != current_user.id:
                # 不属于当前用户，跳过
                skipped.append(f"{tpl_name}（无权覆盖）")
                continue

            if conflict_strategy == "skip":
                skipped.append(tpl_name)
            elif conflict_strategy == "overwrite":
                # 覆盖：更新已有模板字段
                existing_tpl.name = tpl_name
                existing_tpl.description = tpl_data.get("description")
                existing_tpl.category = tpl_data.get("category", existing_tpl.category)
                existing_tpl.thumbnail_url = tpl_data.get("thumbnail_url")
                existing_tpl.inputs_config = inputs_config
                existing_tpl.steps_config = tpl_data.get("steps_config") or []
                existing_tpl.output_mapping = tpl_data.get("output_mapping")
                existing_tpl.script_template_id = script_template_id
                existing_tpl.tags = tpl_data.get("tags") or []
                await db.flush()
                overwritten.append(tpl_name)
                imported.append({"id": existing_tpl.id, "key": existing_tpl.key, "name": existing_tpl.name})
            else:  # rename
                # 重命名：key 追加 _imported_N，name 追加 " (导入)"
                rename_suffix = 1
                while True:
                    candidate_key = f"{tpl_key}_imported_{rename_suffix}"
                    check_q = await db.execute(
                        select(PipelineTemplate).filter(PipelineTemplate.key == candidate_key)
                    )
                    if check_q.scalar_one_or_none() is None:
                        break
                    rename_suffix += 1
                final_key = f"{tpl_key}_imported_{rename_suffix}"
                final_name = f"{tpl_name} (导入)"
                try:
                    new_tpl = _build_template_data(final_key, final_name)
                    db.add(new_tpl)
                    await db.flush()
                    renamed.append(tpl_name)
                    imported.append({"id": new_tpl.id, "key": new_tpl.key, "name": new_tpl.name})
                except Exception as e:
                    logger.warning("重命名导入模板 %s 失败: %s", tpl_key, e)
                    skipped.append(tpl_name)

    try:
        await db.commit()
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"导入失败：{e}")

    return {
        "imported": len(imported),
        "skipped": len(skipped),
        "renamed": len(renamed),
        "overwritten": len(overwritten),
        "items": imported,
        "skipped_items": skipped,
        "renamed_items": renamed,
        "overwritten_items": overwritten,
        "errors": errors,
    }


# ---------- 模板导入导出辅助函数 ----------

def _serialize_template(tpl: PipelineTemplate) -> Dict[str, Any]:
    """将 PipelineTemplate 序列化为可导出的字典（剔除运行时字段）"""
    # wizard_chain 模式下 output_mapping 不再推断，直接保留原值
    data: Dict[str, Any] = {
        "key": tpl.key,
        "name": tpl.name,
        "description": tpl.description,
        "category": tpl.category,
        "thumbnail_url": tpl.thumbnail_url,
        "inputs_config": tpl.inputs_config,
        "steps_config": tpl.steps_config,
        "output_mapping": tpl.output_mapping,
        "script_template_id": tpl.script_template_id,
        "estimated_credits": tpl.estimated_credits,
        "estimated_time_minutes": tpl.estimated_time_minutes,
        "tags": tpl.tags or [],
        "is_public": tpl.is_public,
    }
    # 携带关联剧本模板的 key，便于导入侧重建引用
    if tpl.script_template and tpl.script_template.key:
        data["script_template_key"] = tpl.script_template.key
    return data


def _serialize_script_template(st: ScriptTemplate) -> Dict[str, Any]:
    """将 ScriptTemplate 序列化为可导出的字典"""
    return {
        "key": st.key,
        "name": st.name,
        "description": st.description,
        "category": st.category,
        "structure": st.structure,
        "prompt_template": st.prompt_template,
        "output_schema": st.output_schema,
        "variables_schema": st.variables_schema,
        "scenes_min": st.scenes_min,
        "scenes_max": st.scenes_max,
        "default_scene_duration": st.default_scene_duration,
        "output_format": st.output_format,
        "tags": st.tags or [],
    }


def _serialize_style_preset(sp: StylePreset) -> Dict[str, Any]:
    """将 StylePreset 序列化为可导出的字典"""
    return {
        "key": sp.key,
        "name": sp.name,
        "description": sp.description,
        "category": sp.category,
        "visual_prefix": sp.visual_prefix,
        "lighting": sp.lighting,
        "color_palette": sp.color_palette,
        "quality_suffix": sp.quality_suffix,
        "negative_prompt": sp.negative_prompt,
        "camera_language": sp.camera_language,
        "mood_keywords": sp.mood_keywords,
        "preview_image": sp.preview_image,
        "tags": sp.tags or [],
    }


def _remap_style_ids_in_inputs(
    inputs_config: List[Dict[str, Any]],
    styles_in: List[Dict[str, Any]],
    style_key_to_id: Dict[str, int],
) -> List[Dict[str, Any]]:
    """
    重映射 inputs_config 中 style_select 类型字段的 default 值。

    导出文件中 style_presets 已重新创建并按 key 映射到新 id，
    inputs_config 中的 default（原 id）需要根据导出数据中携带的 id→key 反查新 id。
    """
    if not styles_in or not style_key_to_id:
        return inputs_config

    # 简化处理：style_select 的 default 在导入时保持原值，由用户手动校正
    # （因为 style_select 的 options 通常存储在 inputs_config 内，且 id 会变）
    return inputs_config


# =====================================================
# 风格预设 API
# =====================================================

@router.get("/pipeline/styles", summary="获取风格预设列表")
async def get_style_presets(
    category: Optional[str] = None,
    search: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_async_db),
    _current_user: Optional[User] = Depends(get_current_user_optional),
):
    """获取风格预设列表（内置 + 用户自定义公开的）"""
    query = select(StylePreset)
    filters = []
    if category:
        filters.append(StylePreset.category == category)
    if search:
        search_pattern = f"%{search}%"
        filters.append(or_(
            StylePreset.name.ilike(search_pattern),
            StylePreset.description.ilike(search_pattern),
            StylePreset.key.ilike(search_pattern),
        ))
    filters.append(or_(StylePreset.is_builtin == True, StylePreset.is_public == True))

    if filters:
        query = query.where(*filters)

    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    query = query.order_by(
        StylePreset.is_builtin.desc(),
        StylePreset.use_count.desc(),
        StylePreset.id.asc(),
    ).offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    items = list(result.scalars().all())

    return {
        "items": [StylePresetOut.model_validate(item) for item in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/pipeline/styles/{style_id}", summary="获取风格预设详情")
async def get_style_preset_detail(
    style_id: int,
    db: AsyncSession = Depends(get_async_db),
    _current_user: Optional[User] = Depends(get_current_user_optional),
):
    """获取单个风格预设详情"""
    style = await style_service.get_style_by_id(db, style_id)
    if not style:
        raise HTTPException(status_code=404, detail="风格预设不存在")

    return StylePresetOut.model_validate(style)


# =====================================================
# 剧本模板 API
# =====================================================

@router.get("/pipeline/script-templates", summary="获取剧本模板列表")
async def get_script_templates(
    category: Optional[str] = None,
    search: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_async_db),
    _current_user: Optional[User] = Depends(get_current_user_optional),
):
    """获取剧本模板列表"""
    query = select(ScriptTemplate)
    filters = []
    if category:
        filters.append(ScriptTemplate.category == category)
    if search:
        search_pattern = f"%{search}%"
        filters.append(or_(
            ScriptTemplate.name.ilike(search_pattern),
            ScriptTemplate.description.ilike(search_pattern),
            ScriptTemplate.key.ilike(search_pattern),
        ))
    filters.append(or_(ScriptTemplate.is_builtin == True, ScriptTemplate.is_public == True))

    if filters:
        query = query.where(*filters)

    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    query = query.order_by(
        ScriptTemplate.is_builtin.desc(),
        ScriptTemplate.id.asc(),
    ).offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    items = list(result.scalars().all())

    return {
        "items": [ScriptTemplateOut.model_validate(item) for item in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/pipeline/script-templates/{tpl_id}", summary="获取剧本模板详情")
async def get_script_template_detail(
    tpl_id: int,
    db: AsyncSession = Depends(get_async_db),
    _current_user: Optional[User] = Depends(get_current_user_optional),
):
    """获取单个剧本模板详情"""
    tpl = await script_template_service.get_script_template_by_id(db, tpl_id)
    if not tpl:
        raise HTTPException(status_code=404, detail="剧本模板不存在")

    return ScriptTemplateOut.model_validate(tpl)


# =====================================================
# 资产库 API
# =====================================================

@router.get("/pipeline/assets", summary="获取资产库列表")
async def get_assets(
    asset_type: Optional[str] = None,
    category: Optional[str] = None,
    search: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_async_db),
    _current_user: Optional[User] = Depends(get_current_user_optional),
):
    """获取资产库列表（角色、道具、场景等公开资产）"""
    query = select(Asset)
    filters = []
    if asset_type:
        filters.append(Asset.type == asset_type)
    if search:
        search_pattern = f"%{search}%"
        filters.append(or_(
            Asset.name.ilike(search_pattern),
            Asset.description.ilike(search_pattern),
            Asset.visual_description.ilike(search_pattern),
        ))
    filters.append(Asset.is_public == True)

    if filters:
        query = query.where(*filters)

    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    query = query.order_by(
        Asset.use_count.desc(),
        Asset.id.desc(),
    ).offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    items = list(result.scalars().all())

    return {
        "items": [AssetOut.model_validate(item) for item in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/pipeline/assets/{asset_id}", summary="获取资产详情")
async def get_asset_detail(
    asset_id: int,
    db: AsyncSession = Depends(get_async_db),
    _current_user: Optional[User] = Depends(get_current_user_optional),
):
    """获取单个资产详情"""
    asset = await asset_library.get_asset_by_id(db, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="资产不存在")

    return AssetOut.model_validate(asset)


@router.post("/pipeline/assets/save-from-generation", summary="从生成记录保存为资产")
async def save_asset_from_generation(
    req: AssetSaveFromGenerationRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """将生成的图片/视频保存为资产库中的资产"""
    asset = await asset_library.save_asset_from_generation(
        db, req, user_id=current_user.id
    )
    return AssetOut.model_validate(asset)


# =====================================================
# 场景化模板 API
# =====================================================

@router.get("/pipeline/template-scenarios", summary="获取模板场景预设列表")
async def get_template_scenarios():
    """
    获取场景化模板预设列表。

    返回所有预设的场景（漫剧、广告、教育、二次元等），
    每个场景包含：key、name、description、icon、color、inputs_config 模板。
    """
    return {
        "items": template_scenarios.TEMPLATE_SCENARIOS,
        "total": len(template_scenarios.TEMPLATE_SCENARIOS),
    }


@router.post("/pipeline/templates/from-scenario", summary="从场景预设创建模板")
async def create_template_from_scenario(
    req: TemplateFromScenarioRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """
    从场景预设创建模板。

    根据 scenario_key 加载预设，用 inputs 渲染 steps_config_template，
    自动计算 estimated_credits，创建模板。
    """
    # 1. 加载场景预设
    scenario = template_scenarios.get_scenario_by_key(req.scenario_key)
    if not scenario:
        raise HTTPException(status_code=404, detail=f"场景预设 '{req.scenario_key}' 不存在")

    # 2. 渲染 steps_config（wizard_chain 模式下直接拷贝预设链路）
    try:
        if req.custom_steps_config:
            steps_config = req.custom_steps_config
        else:
            steps_config = template_scenarios.render_steps_config(
                scenario=scenario,
                inputs=req.inputs or {},
            )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"渲染步骤配置失败: {e}")

    # 3. 构造模板创建请求
    template_name = req.name or scenario["name"]
    template_description = req.description or scenario.get("description", "")
    template_key = f"{req.scenario_key}_{current_user.id}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"

    create_req = PipelineTemplateCreate(
        key=template_key,
        name=template_name,
        description=template_description,
        category=scenario.get("category", "drama"),
        inputs_config=scenario.get("inputs_config", []),
        steps_config=steps_config,
        is_public=req.is_public,
        tags=req.tags or scenario.get("tags", []),
    )

    # 4. 自动计算预估积分（create_template 内部会调用 auto_fill_estimated_credits）
    tpl = await template_service.create_template(
        db, create_req, author_id=current_user.id, is_builtin=False
    )

    # 5. 如果提供了缩略图 URL，更新
    thumbnail_url = req.inputs.get("thumbnail_url") if req.inputs else None
    if thumbnail_url:
        tpl.thumbnail_url = thumbnail_url
        await db.commit()
        await db.refresh(tpl)

    return PipelineTemplateOut.model_validate(tpl)


@router.get("/pipeline/available-models", summary="获取可用的模型列表")
async def get_available_models(
    db: AsyncSession = Depends(get_async_db),
    model_type: Optional[str] = None,
):
    """
    获取可用的模型列表（从 model_definitions 表读取）。

    - model_type: 可选过滤条件，image/video/chat
    """
    query = select(ModelDefinition).where(
        ModelDefinition.is_active == True
    )

    if model_type:
        query = query.where(ModelDefinition.type == model_type)

    query = query.order_by(ModelDefinition.sort_order.asc())

    result = await db.execute(query)
    models = result.scalars().all()

    return {
        "items": [m.to_dict() for m in models],
        "total": len(models),
    }
