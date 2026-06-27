# =====================================================
# 统一预设聚合服务
# aggregate_presets 函数：跨 CameraPreset + PromptPreset
# 聚合查询，统一返回格式。
#
# 规则：
# - 指定 type → 查该类型原表
# - 不指定 type → 直查 preset_index 表
# =====================================================

from typing import Optional

from sqlalchemy import and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models.camera_preset import CameraPreset
from app.models.prompt_preset import PromptPreset, PresetIndex
from app.models.pipeline import StylePreset, ScriptTemplate, PipelineTemplate


async def aggregate_presets(
    db: AsyncSession,
    user_id: Optional[int] = None,
    preset_type: Optional[str] = None,
    category: Optional[str] = None,
    tags: Optional[list[str]] = None,
    search: Optional[str] = None,
    sort: str = "new",
    page: int = 1,
    page_size: int = 100,
) -> tuple[list[dict], int]:
    """
    统一预设聚合查询。

    返回统一格式的 dict 列表，包含所有字段（camera 类型
    的 prompt_text / style_params 等字段为 None）。

    参数:
    - db: 异步数据库会话
    - user_id: 当前用户 ID（用于可见性过滤）
    - preset_type: 预设类型（camera/prompt/style/script/pipeline）
    - category: 分类筛选
    - tags: 标签筛选
    - search: 搜索名称/描述关键词
    - sort: 排序（new/hot/usage）
    - page: 页码（1-based）
    - page_size: 每页数量
    """
    offset = (page - 1) * page_size

    if preset_type == "camera":
        return await _aggregate_from_camera(db, user_id, category, tags, search, sort, page_size, offset)
    elif preset_type == "style":
        return await _aggregate_from_style(db, user_id, category, tags, search, sort, page_size, offset)
    elif preset_type == "script":
        return await _aggregate_from_script(db, user_id, category, tags, search, sort, page_size, offset)
    elif preset_type == "pipeline":
        return await _aggregate_from_pipeline(db, user_id, category, tags, search, sort, page_size, offset)
    elif preset_type is not None:
        return await _aggregate_from_prompt(db, user_id, preset_type, category, tags, search, sort, page_size, offset)
    else:
        return await _aggregate_from_index(db, user_id, category, tags, search, sort, page_size, offset)


async def _aggregate_from_index(
    db: AsyncSession,
    user_id: Optional[int],
    category: Optional[str],
    tags: Optional[list[str]],
    search: Optional[str],
    sort: str,
    limit: int,
    offset: int,
) -> tuple[list[dict], int]:
    """从 preset_index 表聚合查询（所有类型）"""
    conditions = _build_visibility_conditions(PresetIndex, user_id)

    if category:
        conditions.append(PresetIndex.category == category)
    if search:
        search_pattern = f"%{search}%"
        conditions.append(
            or_(
                PresetIndex.name.like(search_pattern),
                PresetIndex.description.like(search_pattern),
            )
        )

    where = and_(*conditions)

    # 排序
    if sort in ("hot", "usage"):
        order_by = PresetIndex.usage_count.desc()
    else:
        order_by = PresetIndex.created_at.desc()

    base_query = select(PresetIndex).filter(where)

    # 总数
    count_result = await db.execute(base_query)
    total = len(count_result.scalars().all())

    # 分页
    result = await db.execute(
        base_query.order_by(order_by).offset(offset).limit(limit)
    )
    entries = result.scalars().all()

    items = [_index_to_unified(e) for e in entries]
    return items, total


async def _aggregate_from_camera(
    db: AsyncSession,
    user_id: Optional[int],
    category: Optional[str],
    tags: Optional[list[str]],
    search: Optional[str],
    sort: str,
    limit: int,
    offset: int,
) -> tuple[list[dict], int]:
    """从 camera_presets 表查询"""
    conditions = _build_visibility_conditions(CameraPreset, user_id)

    if category:
        conditions.append(CameraPreset.category == category)
    if search:
        search_pattern = f"%{search}%"
        conditions.append(
            or_(
                CameraPreset.name.like(search_pattern),
                CameraPreset.description.like(search_pattern),
            )
        )

    where = and_(*conditions)

    if sort in ("hot", "usage"):
        order_by = CameraPreset.usage_count.desc()
    else:
        order_by = CameraPreset.updated_at.desc()

    base_query = select(CameraPreset).filter(where)

    count_result = await db.execute(base_query)
    total = len(count_result.scalars().all())

    result = await db.execute(
        base_query.order_by(order_by).offset(offset).limit(limit)
    )
    presets = result.scalars().all()

    items = [_camera_to_unified(p) for p in presets]
    return items, total


async def _aggregate_from_prompt(
    db: AsyncSession,
    user_id: Optional[int],
    preset_type: str,
    category: Optional[str],
    tags: Optional[list[str]],
    search: Optional[str],
    sort: str,
    limit: int,
    offset: int,
) -> tuple[list[dict], int]:
    """从 prompt_presets 表查询"""
    conditions = _build_visibility_conditions(PromptPreset, user_id)
    conditions.append(PromptPreset.type == preset_type)

    if category:
        conditions.append(PromptPreset.category == category)
    if search:
        search_pattern = f"%{search}%"
        conditions.append(
            or_(
                PromptPreset.name.like(search_pattern),
                PromptPreset.description.like(search_pattern),
            )
        )

    where = and_(*conditions)

    if sort in ("hot", "usage"):
        order_by = PromptPreset.usage_count.desc()
    else:
        order_by = PromptPreset.updated_at.desc()

    base_query = select(PromptPreset).filter(where)

    count_result = await db.execute(base_query)
    total = len(count_result.scalars().all())

    result = await db.execute(
        base_query.order_by(order_by).offset(offset).limit(limit)
    )
    presets = result.scalars().all()

    items = [_prompt_to_unified(p) for p in presets]
    return items, total


# ---------- Style / Script / Pipeline 聚合查询 ----------

async def _aggregate_from_style(
    db: AsyncSession, user_id, category, tags, search, sort, limit, offset
) -> tuple[list[dict], int]:
    """从 style_presets 表查询，虚拟映射 type="style" """
    conditions = _build_simple_visibility_conditions(StylePreset, user_id)
    if category:
        conditions.append(StylePreset.category == category)
    if search:
        s = f"%{search}%"
        conditions.append(or_(StylePreset.name.like(s), StylePreset.description.like(s)))

    where = and_(*conditions)
    order_by = StylePreset.use_count.desc() if sort in ("hot", "usage") else StylePreset.updated_at.desc()

    base_query = select(StylePreset).filter(where)
    count_result = await db.execute(base_query)
    total = len(count_result.scalars().all())

    result = await db.execute(base_query.order_by(order_by).offset(offset).limit(limit))
    presets = result.scalars().all()

    items = [_style_to_unified(p) for p in presets]
    return items, total


async def _aggregate_from_script(
    db: AsyncSession, user_id, category, tags, search, sort, limit, offset
) -> tuple[list[dict], int]:
    """从 script_templates 表查询，虚拟映射 type="script" """
    conditions = _build_simple_visibility_conditions(ScriptTemplate, user_id)
    if category:
        conditions.append(ScriptTemplate.category == category)
    if search:
        s = f"%{search}%"
        conditions.append(or_(ScriptTemplate.name.like(s), ScriptTemplate.description.like(s)))

    where = and_(*conditions)
    order_by = ScriptTemplate.updated_at.desc()

    base_query = select(ScriptTemplate).filter(where)
    count_result = await db.execute(base_query)
    total = len(count_result.scalars().all())

    result = await db.execute(base_query.order_by(order_by).offset(offset).limit(limit))
    presets = result.scalars().all()

    items = [_script_to_unified(p) for p in presets]
    return items, total


async def _aggregate_from_pipeline(
    db: AsyncSession, user_id, category, tags, search, sort, limit, offset
) -> tuple[list[dict], int]:
    """从 pipeline_templates 表查询，虚拟映射 type="pipeline" """
    conditions = _build_simple_visibility_conditions(PipelineTemplate, user_id)
    if category:
        conditions.append(PipelineTemplate.category == category)
    if search:
        s = f"%{search}%"
        conditions.append(or_(PipelineTemplate.name.like(s), PipelineTemplate.description.like(s)))

    where = and_(*conditions)
    order_by = PipelineTemplate.use_count.desc() if sort in ("hot", "usage") else PipelineTemplate.updated_at.desc()

    base_query = select(PipelineTemplate).filter(where)
    count_result = await db.execute(base_query)
    total = len(count_result.scalars().all())

    result = await db.execute(base_query.order_by(order_by).offset(offset).limit(limit))
    presets = result.scalars().all()

    items = [_pipeline_to_unified(p) for p in presets]
    return items, total


# ---------- 可见性过滤 ----------

def _build_visibility_conditions(model, user_id: Optional[int]) -> list:
    """构建可见性过滤条件"""
    if user_id is not None:
        return [
            or_(
                model.user_id == user_id,
                and_(model.is_public == True, model.is_approved == True),
            )
        ]
    else:
        return [
            and_(model.is_public == True, model.is_approved == True)
        ]


# ---------- 统一格式转换 ----------

def _camera_to_unified(cp: CameraPreset) -> dict:
    """CameraPreset → 统一 dict"""
    return {
        "id": cp.id,
        "user_id": cp.user_id,
        "name": cp.name,
        "description": cp.description,
        "type": "camera",
        "category": cp.category,
        "tags": cp.tags or [],
        "is_public": cp.is_public,
        "is_approved": cp.is_approved,
        "usage_count": cp.usage_count,
        "created_at": cp.created_at.isoformat() if cp.created_at else None,
        "updated_at": cp.updated_at.isoformat() if cp.updated_at else None,
        # 扩展字段（camera 类型专属）
        "prompt_text": "",
        "camera_params": {
            "camera_model": cp.camera_model,
            "focal_length": cp.focal_length,
            "aperture": cp.aperture,
            "depth_of_field": cp.depth_of_field,
            "shutter_speed": cp.shutter_speed,
            "shutter_angle": cp.shutter_angle,
            "camera_movement": cp.camera_movement,
            "camera_angle": cp.camera_angle,
            "aspect_ratio": cp.aspect_ratio,
            "visual_style": cp.visual_style,
        },
        "style_params": None,
        "script_text": None,
        "pipeline_config": None,
    }


def _prompt_to_unified(pp: PromptPreset) -> dict:
    """PromptPreset → 统一 dict"""
    return {
        "id": pp.id,
        "user_id": pp.user_id,
        "name": pp.name,
        "description": pp.description,
        "type": pp.type,
        "category": pp.category,
        "tags": pp.tags or [],
        "is_public": pp.is_public,
        "is_approved": pp.is_approved,
        "usage_count": pp.usage_count,
        "created_at": pp.created_at.isoformat() if pp.created_at else None,
        "updated_at": pp.updated_at.isoformat() if pp.updated_at else None,
        "prompt_text": pp.prompt_text or "",
        "camera_params": pp.camera_params,
        "style_params": pp.style_params,
        "script_text": pp.script_text,
        "pipeline_config": pp.pipeline_config,
    }


def _index_to_unified(idx: PresetIndex) -> dict:
    """PresetIndex → 统一 dict（仅含索引字段，扩展字段为默认值）"""
    return {
        "id": idx.preset_id,
        "user_id": idx.user_id,
        "name": idx.name,
        "description": idx.description,
        "type": idx.preset_type,
        "category": idx.category,
        "tags": idx.tags or [],
        "is_public": idx.is_public,
        "is_approved": idx.is_approved,
        "usage_count": idx.usage_count,
        "created_at": idx.created_at.isoformat() if idx.created_at else None,
        "updated_at": None,
        "prompt_text": "",
        "camera_params": None,
        "style_params": None,
        "script_text": None,
        "pipeline_config": None,
    }


# ---------- 可见性过滤（author_id 字段的表） ----------

def _build_simple_visibility_conditions(model, user_id: Optional[int]) -> list:
    """构建可见性过滤条件（用于 StylePreset / ScriptTemplate / PipelineTemplate，使用 author_id 字段）"""
    if user_id is not None:
        return [
            or_(
                model.author_id == user_id,
                and_(model.is_public == True),
            )
        ]
    else:
        return [model.is_public == True]


# ---------- Style / Script / Pipeline 转换 ----------

def _style_to_unified(sp: StylePreset) -> dict:
    """StylePreset → 统一 dict"""
    prompt_parts = []
    if sp.visual_prefix:
        prompt_parts.append(sp.visual_prefix)
    if sp.lighting:
        prompt_parts.append(sp.lighting)
    if sp.color_palette:
        prompt_parts.append(sp.color_palette)
    if sp.quality_suffix:
        prompt_parts.append(sp.quality_suffix)

    return {
        "id": sp.id,
        "user_id": sp.author_id,
        "name": sp.name,
        "description": sp.description,
        "type": "style",
        "category": sp.category,
        "tags": sp.tags or [],
        "is_public": sp.is_public,
        "is_approved": sp.is_public,  # 无审核字段，直接以 is_public 为准
        "usage_count": sp.use_count,
        "created_at": sp.created_at.isoformat() if sp.created_at else None,
        "updated_at": sp.updated_at.isoformat() if sp.updated_at else None,
        "prompt_text": ", ".join(prompt_parts) if prompt_parts else sp.description or "",
        "camera_params": {
            "camera_language": sp.camera_language,
            "mood_keywords": sp.mood_keywords,
        },
        "style_params": {
            "visual_prefix": sp.visual_prefix,
            "lighting": sp.lighting,
            "color_palette": sp.color_palette,
            "quality_suffix": sp.quality_suffix,
            "negative_prompt": sp.negative_prompt,
        },
        "script_text": None,
        "pipeline_config": None,
    }


def _script_to_unified(st: ScriptTemplate) -> dict:
    """ScriptTemplate → 统一 dict"""
    return {
        "id": st.id,
        "user_id": st.author_id,
        "name": st.name,
        "description": st.description,
        "type": "script",
        "category": st.category,
        "tags": st.tags or [],
        "is_public": st.is_public,
        "is_approved": st.is_public,
        "usage_count": 0,
        "created_at": st.created_at.isoformat() if st.created_at else None,
        "updated_at": st.updated_at.isoformat() if st.updated_at else None,
        "prompt_text": st.prompt_template or "",
        "camera_params": None,
        "style_params": None,
        "script_text": st.prompt_template,
        "pipeline_config": {
            "structure": st.structure,
            "scenes_min": st.scenes_min,
            "scenes_max": st.scenes_max,
            "default_scene_duration": st.default_scene_duration,
            "output_schema": st.output_schema,
        },
    }


def _pipeline_to_unified(pt: PipelineTemplate) -> dict:
    """PipelineTemplate → 统一 dict"""
    return {
        "id": pt.id,
        "user_id": pt.author_id,
        "name": pt.name,
        "description": pt.description,
        "type": "pipeline",
        "category": pt.category,
        "tags": pt.tags or [],
        "is_public": pt.is_public,
        "is_approved": pt.is_public,
        "usage_count": pt.use_count,
        "created_at": pt.created_at.isoformat() if pt.created_at else None,
        "updated_at": pt.updated_at.isoformat() if pt.updated_at else None,
        "prompt_text": pt.description or "",
        "camera_params": None,
        "style_params": None,
        "script_text": None,
        "pipeline_config": {
            "key": pt.key,
            "inputs_config": pt.inputs_config,
            "steps_config": pt.steps_config,
            "estimated_credits": pt.estimated_credits,
            "estimated_time_minutes": pt.estimated_time_minutes,
        },
    }
