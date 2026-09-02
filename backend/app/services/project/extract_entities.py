# =====================================================
# 从剧本提取实体（角色/场景/道具）共享逻辑
#
# character_service / scene_service / prop_service 的
# extract_X_from_script 为同一流程的三份拷贝，仅
# ORM 模型、prompt、JSON 清单键、实体字段映射不同，统一抽到此模块。
#
# 无 SSE 事件：三份原实现均只写库后返回 {"added": N}。
# =====================================================

from typing import Any, Dict, Tuple, Type

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import ProjectScript
from app.services.agnes_client import agnes_client
from app.services.model_registry import resolve_project_chat_model_id
from app.services.project.wizard import parse_json_loose


async def extract_entities_from_script(
    db: AsyncSession,
    *,
    project_id: int,
    script_id: int,
    entity_label: str,
    model_cls: Type,
    prompt_head: str,
    list_key: str,
    field_map: Dict[str, Tuple[str, Any]],
) -> dict:
    """
    从指定集剧本内容用 LLM 提取实体清单（追加到该集，不覆盖）

    Args:
        entity_label: 实体中文名（"角色"/"场景"/"道具"，用于错误文案）
        model_cls: 实体 ORM 模型（ProjectCharacter/ProjectScene/ProjectProp）
        prompt_head: 提取指令 + JSON 输出形状说明（共享函数在其后拼接"剧本：\\n{content}"）
        list_key: LLM 返回 JSON 中实体清单的键（characters/scenes/props）
        field_map: LLM JSON 键 -> (模型字段, 缺省值)

    Returns:
        {"added": N}
    """
    # 精确查指定集剧本
    script = (
        await db.execute(
            select(ProjectScript).where(
                ProjectScript.id == script_id,
                ProjectScript.project_id == project_id,
            )
        )
    ).scalars().first()
    if not script:
        raise HTTPException(404, "剧本不存在或不属于该项目")
    if not script.content:
        raise HTTPException(400, f"剧本内容为空，无法提取{entity_label}")

    prompt = f"{prompt_head}剧本：\n{script.content}"
    model = await resolve_project_chat_model_id(db, project_id)
    if not model:
        raise HTTPException(400, "未配置可用的对话模型，请先在配置页同步或添加对话模型")
    text = await agnes_client.chat_text(
        model, [{"role": "user", "content": prompt}], temperature=0.5,
    )
    parsed = parse_json_loose(text)

    # 现有名称集合（仅限该集，避免重复）
    existing = {
        e.name
        for e in (
            await db.execute(
                select(model_cls).where(model_cls.script_id == script_id)
            )
        ).scalars().all()
    }

    max_order = (
        await db.execute(
            select(func.max(model_cls.sort_order)).where(
                model_cls.script_id == script_id
            )
        )
    ).scalar() or 0

    added = 0
    for item in parsed.get(list_key, []):
        name = item.get("name", "").strip()
        if not name or name in existing:
            continue
        max_order += 1
        db.add(
            model_cls(
                project_id=project_id,
                script_id=script_id,
                name=name,
                sort_order=max_order,
                **{
                    field: item.get(key, default)
                    for key, (field, default) in field_map.items()
                },
            )
        )
        existing.add(name)
        added += 1

    await db.commit()
    return {"added": added}
