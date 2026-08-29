# =====================================================
# 角色服务 — 角色 CRUD + 单/批量生图 + 版本管理 + 从剧本提取
#
# 角色是项目的核心实体之一，对应 project_characters 表。
# 通过 ProjectEntityAsset 表实现多版本形象图管理（F1 + G1）。
# =====================================================

import json
import logging
from typing import List, Optional

from fastapi import HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import (
    Project,
    ProjectCharacter,
    ProjectScript,
)
from app.schemas.project import CharacterCreate, CharacterUpdate
from app.services.agnes_client import agnes_client
from app.services.project._entity_versions import (
    create_version,
    list_versions,
    set_active_version,
    delete_version,
    attach_active_image,
    attach_active_image_batch,
)
from app.services.project._async_gen import submit_image_task, claim_generation
from app.services.project._generation_history import record_manual_upload
from app.services.project.sse_manager import project_sse_manager
from app.services.project.wizard import parse_json_loose

logger = logging.getLogger("agnes_platform.project.character")

ENTITY_TYPE = "character"


# =====================================================
# 角色 CRUD
# =====================================================

async def list_characters(
    db: AsyncSession, project_id: int, script_id: Optional[int] = None
) -> List[ProjectCharacter]:
    """列出项目角色（可选按集过滤）"""
    stmt = select(ProjectCharacter).where(ProjectCharacter.project_id == project_id)
    if script_id is not None:
        stmt = stmt.where(ProjectCharacter.script_id == script_id)
    stmt = stmt.order_by(ProjectCharacter.sort_order)
    result = await db.execute(stmt)
    items = result.scalars().all()
    await attach_active_image_batch(db, ENTITY_TYPE, items)
    # 批量填充 episode_no
    await _fill_episode_no(db, items)
    return items


async def _fill_episode_no(db: AsyncSession, items: List) -> None:
    """批量给角色列表填充 episode_no 字段（从 ProjectScript 查一次字典映射）"""
    if not items:
        return
    script_ids = {it.script_id for it in items if it.script_id is not None}
    if not script_ids:
        return
    result = await db.execute(
        select(ProjectScript.id, ProjectScript.episode_no).where(
            ProjectScript.id.in_(script_ids)
        )
    )
    ep_map = dict(result.all())
    for it in items:
        it.episode_no = ep_map.get(it.script_id)


async def get_character(
    db: AsyncSession, character_id: int
) -> Optional[ProjectCharacter]:
    """获取角色详情"""
    result = await db.execute(
        select(ProjectCharacter).where(ProjectCharacter.id == character_id)
    )
    item = result.scalar_one_or_none()
    if item:
        await attach_active_image(db, ENTITY_TYPE, item)
    return item


async def create_character(
    db: AsyncSession, project_id: int, data: CharacterCreate
) -> ProjectCharacter:
    """添加角色"""
    # 校验 script_id 属于该项目
    script = await db.get(ProjectScript, data.script_id)
    if not script or script.project_id != project_id:
        raise HTTPException(404, "剧本不存在或不属于该项目")

    # 计算 sort_order（按集追加到末尾）
    max_order = (
        await db.execute(
            select(func.max(ProjectCharacter.sort_order)).where(
                ProjectCharacter.script_id == data.script_id
            )
        )
    ).scalar() or 0

    character = ProjectCharacter(
        project_id=project_id,
        script_id=data.script_id,
        name=data.name,
        description=data.description,
        appearance_desc=data.appearance_desc,
        role_type=data.role_type or "supporting",
        sort_order=max_order + 1,
        asset_id=data.asset_id,
    )
    db.add(character)
    await db.commit()
    await db.refresh(character)
    await attach_active_image(db, ENTITY_TYPE, character)
    return character


async def update_character(
    db: AsyncSession, character_id: int, data: CharacterUpdate
) -> Optional[ProjectCharacter]:
    """编辑角色"""
    character = await get_character(db, character_id)
    if not character:
        return None
    update_data = data.model_dump(exclude_unset=True)
    for k, v in update_data.items():
        setattr(character, k, v)
    await db.commit()
    await db.refresh(character)
    await attach_active_image(db, ENTITY_TYPE, character)

    await project_sse_manager.push(
        character.project_id,
        "entity_updated",
        {"target": f"{ENTITY_TYPE}:{character_id}", "fields": list(update_data.keys())},
    )
    return character


async def delete_character(db: AsyncSession, character_id: int) -> bool:
    """删除角色（级联删除其所有版本）"""
    character = await get_character(db, character_id)
    if not character:
        return False
    project_id = character.project_id
    await db.delete(character)
    await db.commit()

    await project_sse_manager.push(
        project_id,
        "entity_updated",
        {"target": f"{ENTITY_TYPE}:{character_id}", "action": "deleted"},
    )
    return True


async def reorder_characters(
    db: AsyncSession, project_id: int, character_ids: List[int]
) -> None:
    """按给定 ID 顺序重排角色"""
    for idx, cid in enumerate(character_ids):
        await db.execute(
            select(ProjectCharacter).where(ProjectCharacter.id == cid)
        )
        character = (
            await db.execute(
                select(ProjectCharacter).where(
                    ProjectCharacter.id == cid,
                    ProjectCharacter.project_id == project_id,
                )
            )
        ).scalar_one_or_none()
        if character:
            character.sort_order = idx
    await db.commit()


# =====================================================
# 角色形象图生成（单/批量）
# =====================================================

async def generate_character_image(
    db: AsyncSession,
    character_id: int,
    user_id: int,
    style_config: Optional[dict] = None,
    model: str = "",
    size: str = "1024x1024",
) -> dict:
    """
    生成单个角色形象图（异步模式）

    提交到 image_poller_manager，立即返回 task_id。
    任务完成后前端调 claim 端点认领结果到 ProjectEntityAsset。
    """
    character = await get_character(db, character_id)
    if not character:
        return None

    # 拼接 prompt
    prompt_parts = [character.appearance_desc or character.description or character.name]
    if style_config:
        for k, v in style_config.items():
            if v:
                prompt_parts.append(f"{k}: {v}")
    prompt = ", ".join(prompt_parts)
    used_model = model or "agnes-image-2.0-flash"

    # 提交到 image_poller（poller 负责扣费 + AI 调用 + 写 Generation + confirm/refund）
    task_id = await submit_image_task(
        db, user_id, prompt, used_model, size, mode="text2image",
        ref_type="project_character_image",
        project_id=character.project_id,
        asset_type="character",
        asset_name=character.name,
    )

    await project_sse_manager.push(
        character.project_id,
        "generation_started",
        {
            "target": f"{ENTITY_TYPE}:{character_id}",
            "version_type": "image",
            "user_id": user_id,
            "task_id": task_id,
        },
    )

    return {
        "task_id": task_id,
        "entity_type": ENTITY_TYPE,
        "entity_id": character_id,
        "status": "pending",
        "prompt": prompt,
    }


async def claim_character_image(
    db: AsyncSession, character_id: int, task_id: str
) -> Optional[ProjectCharacter]:
    """任务完成后认领结果：从 Generation 拿 result_url，创建 ProjectEntityAsset 新版本"""
    character = await get_character(db, character_id)
    if not character:
        return None

    gen = await claim_generation(db, task_id)
    if not gen or not gen.result_url:
        return None

    asset, _ = await create_version(
        db,
        project_id=character.project_id,
        entity_type=ENTITY_TYPE,
        entity_id=character_id,
        file_url=gen.result_url,
        thumbnail_url=gen.result_url,
        prompt=gen.prompt or "",
        model=gen.model or "",
        file_type="image",
        generation_id=gen.id,
        set_active=True,
    )

    await project_sse_manager.push(
        character.project_id,
        "generation_completed",
        {
            "target": f"{ENTITY_TYPE}:{character_id}",
            "version_id": asset.id,
            "file_url": gen.result_url,
            "generation_id": gen.id,
            "task_id": task_id,
        },
    )
    await attach_active_image(db, ENTITY_TYPE, character)
    return character


async def batch_generate_characters(
    db: AsyncSession,
    character_ids: List[int],
    user_id: int,
    style_config: Optional[dict] = None,
    model: str = "",
    size: str = "1024x1024",
) -> List[dict]:
    """
    批量生成角色形象图（顺序触发，逐个返回结果）

    Returns:
        [{"character_id": 1, "success": True, "file_url": "..."}, ...]
    """
    results = []
    for cid in character_ids:
        try:
            character = await generate_character_image(
                db, cid, user_id, style_config, model, size
            )
            results.append(
                {
                    "character_id": cid,
                    "success": bool(character),
                    "file_url": (
                        character.active_image_id  # 指针已更新
                        and (await list_versions(db, ENTITY_TYPE, cid))[0].file_url
                        if character
                        else None
                    ),
                }
            )
        except Exception as e:
            results.append(
                {"character_id": cid, "success": False, "error": str(e)}
            )
    return results


async def upload_character_image(
    db: AsyncSession,
    character_id: int,
    user_id: int,
    file_url: str,
    thumbnail_url: str = "",
    file_size: Optional[int] = None,
    width: Optional[int] = None,
    height: Optional[int] = None,
) -> Optional[ProjectCharacter]:
    """用户手动上传图片作为新版本（G1）"""
    character = await get_character(db, character_id)
    if not character:
        return None

    # 写入生成历史（手动上传，不计费）
    gen_record = await record_manual_upload(
        db, user_id, "image", file_url, name=character.name,
    )

    await create_version(
        db,
        project_id=character.project_id,
        entity_type=ENTITY_TYPE,
        entity_id=character_id,
        file_url=file_url,
        thumbnail_url=thumbnail_url or file_url,
        prompt="(用户上传)",
        file_type="image",
        file_size=file_size,
        width=width,
        height=height,
        is_manual=True,
        generation_id=gen_record.id,
        set_active=True,
    )
    await attach_active_image(db, ENTITY_TYPE, character)
    return character


# =====================================================
# 版本管理（转发到 _entity_versions）
# =====================================================

async def list_character_versions(
    db: AsyncSession, character_id: int
):
    return await list_versions(db, ENTITY_TYPE, character_id)


async def set_active_character_version(
    db: AsyncSession, character_id: int, version_id: int
):
    return await set_active_version(db, ENTITY_TYPE, character_id, version_id)


async def delete_character_version(
    db: AsyncSession, character_id: int, version_id: int
) -> bool:
    return await delete_version(db, ENTITY_TYPE, character_id, version_id)


# =====================================================
# 从剧本重新提取角色（追加，不覆盖现有）
# =====================================================

async def extract_characters_from_script(
    db: AsyncSession, project_id: int, script_id: int
) -> dict:
    """
    从指定集剧本内容重新提取角色清单（追加到该集，不覆盖）

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
        raise HTTPException(400, "剧本内容为空，无法提取角色")

    prompt = (
        "请从以下剧本中提取所有角色信息，返回 JSON 格式：\n"
        '{"characters": [{"name": "角色名", "description": "简介", '
        '"appearance_desc": "外观描述", "role_type": "main|supporting|minor"}]}\n\n'
        f"剧本：\n{script.content}"
    )
    body = {
        "model": "agnes-2.0-flash",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.5,
    }
    result = await agnes_client._post(
        f"{agnes_client.base_url}/chat/completions", body
    )
    choices = result.get("choices", [])
    if not choices:
        return {"added": 0}
    text = choices[0].get("message", {}).get("content", "") or ""
    parsed = parse_json_loose(text)

    # 现有角色名集合（仅限该集，避免重复）
    existing = {
        c.name
        for c in (
            await db.execute(
                select(ProjectCharacter).where(
                    ProjectCharacter.script_id == script_id
                )
            )
        ).scalars().all()
    }

    max_order = (
        await db.execute(
            select(func.max(ProjectCharacter.sort_order)).where(
                ProjectCharacter.script_id == script_id
            )
        )
    ).scalar() or 0

    added = 0
    for item in parsed.get("characters", []):
        name = item.get("name", "").strip()
        if not name or name in existing:
            continue
        max_order += 1
        db.add(
            ProjectCharacter(
                project_id=project_id,
                script_id=script_id,
                name=name,
                description=item.get("description", ""),
                appearance_desc=item.get("appearance_desc", ""),
                role_type=item.get("role_type", "supporting"),
                sort_order=max_order,
            )
        )
        existing.add(name)
        added += 1

    await db.commit()
    return {"added": added}


# =====================================================
# 跨集复制（深拷贝到目标集，不复制分镜关联）
# =====================================================

async def copy_character_to_script(
    db: AsyncSession, project_id: int, character_id: int, target_script_id: int
) -> ProjectCharacter:
    """
    把角色深拷贝到目标集（复制名称/描述/外观/形象图引用，不复制分镜关联）

    名称冲突时自动加"（副本）"后缀。
    """
    # 校验源角色属于 project
    src = await get_character(db, character_id)
    if not src or src.project_id != project_id:
        raise HTTPException(404, "源角色不存在")

    # 校验目标 script 属于 project
    target_script = await db.get(ProjectScript, target_script_id)
    if not target_script or target_script.project_id != project_id:
        raise HTTPException(404, "目标集剧本不存在")

    # 名称冲突处理
    existing = (
        await db.execute(
            select(ProjectCharacter).where(
                ProjectCharacter.script_id == target_script_id,
                ProjectCharacter.name == src.name,
            )
        )
    ).scalars().first()
    new_name = f"{src.name}（副本）" if existing else src.name

    # sort_order 追加到目标集末尾
    max_order = (
        await db.execute(
            select(func.max(ProjectCharacter.sort_order)).where(
                ProjectCharacter.script_id == target_script_id
            )
        )
    ).scalar() or 0

    new_entity = ProjectCharacter(
        project_id=project_id,
        script_id=target_script_id,
        name=new_name,
        description=src.description,
        appearance_desc=src.appearance_desc,
        role_type=src.role_type,
        asset_id=src.asset_id,
        active_image_id=src.active_image_id,
        sort_order=max_order + 1,
    )
    db.add(new_entity)
    await db.commit()
    await db.refresh(new_entity)
    await attach_active_image(db, ENTITY_TYPE, new_entity)
    return new_entity
