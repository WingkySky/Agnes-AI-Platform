# =====================================================
# 角色服务 — 角色 CRUD + 单/批量生图 + 版本管理 + 从剧本提取
#
# 角色是项目的核心实体之一，对应 project_characters 表。
# 通过 ProjectEntityAsset 表实现多版本形象图管理（F1 + G1）。
# =====================================================

import json
import logging
from typing import List, Optional

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
)
from app.services.project.sse_manager import project_sse_manager
from app.services.project.wizard import parse_json_loose

logger = logging.getLogger("agnes_platform.project.character")

ENTITY_TYPE = "character"


# =====================================================
# 角色 CRUD
# =====================================================

async def list_characters(
    db: AsyncSession, project_id: int
) -> List[ProjectCharacter]:
    """列出项目所有角色（按 sort_order）"""
    result = await db.execute(
        select(ProjectCharacter)
        .where(ProjectCharacter.project_id == project_id)
        .order_by(ProjectCharacter.sort_order)
    )
    return result.scalars().all()


async def get_character(
    db: AsyncSession, character_id: int
) -> Optional[ProjectCharacter]:
    """获取角色详情"""
    result = await db.execute(
        select(ProjectCharacter).where(ProjectCharacter.id == character_id)
    )
    return result.scalar_one_or_none()


async def create_character(
    db: AsyncSession, project_id: int, data: CharacterCreate
) -> ProjectCharacter:
    """添加角色"""
    # 计算 sort_order（追加到末尾）
    max_order = (
        await db.execute(
            select(func.max(ProjectCharacter.sort_order)).where(
                ProjectCharacter.project_id == project_id
            )
        )
    ).scalar() or 0

    character = ProjectCharacter(
        project_id=project_id,
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
) -> Optional[ProjectCharacter]:
    """
    生成单个角色形象图（调用 agnes_client.create_image）

    Args:
        style_config: 风格配置（可包含画风/光影/配色等）
        model: 自定义模型，空则用默认
        size: 图片尺寸
    Returns:
        更新后的角色对象
    """
    character = await get_character(db, character_id)
    if not character:
        return None

    # 拼接 prompt: 外观描述 + 风格配置
    prompt_parts = [character.appearance_desc or character.description or character.name]
    if style_config:
        for k, v in style_config.items():
            if v:
                prompt_parts.append(f"{k}: {v}")
    prompt = ", ".join(prompt_parts)

    await project_sse_manager.push(
        character.project_id,
        "generation_started",
        {
            "target": f"{ENTITY_TYPE}:{character_id}",
            "version_type": "image",
            "user_id": user_id,
        },
    )

    try:
        result = await agnes_client.create_image(
            prompt=prompt,
            model=model or "agnes-image-2.0-flash",
            size=size,
            response_format="url",
        )
        # 提取图片 URL
        data_list = result.get("data", [])
        if not data_list:
            raise RuntimeError("图片生成返回空数据")
        image_url = data_list[0].get("url", "")
        if not image_url:
            raise RuntimeError("图片生成未返回 URL")

        asset, _ = await create_version(
            db,
            project_id=character.project_id,
            entity_type=ENTITY_TYPE,
            entity_id=character_id,
            file_url=image_url,
            thumbnail_url=image_url,
            prompt=prompt,
            model=model or "agnes-image-2.0-flash",
            file_type="image",
            set_active=True,
        )

        await project_sse_manager.push(
            character.project_id,
            "generation_completed",
            {
                "target": f"{ENTITY_TYPE}:{character_id}",
                "version_id": asset.id,
                "file_url": image_url,
            },
        )
        return character
    except Exception as e:
        await project_sse_manager.push(
            character.project_id,
            "generation_failed",
            {
                "target": f"{ENTITY_TYPE}:{character_id}",
                "error": str(e),
            },
        )
        raise


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
        set_active=True,
    )
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
    db: AsyncSession, project_id: int
) -> dict:
    """
    从剧本内容重新提取角色清单（追加到现有列表，不覆盖）

    Returns:
        {"added": N}
    """
    # 取第一集剧本
    script = (
        await db.execute(
            select(ProjectScript)
            .where(ProjectScript.project_id == project_id)
            .order_by(ProjectScript.episode_no)
        )
    ).scalars().first()
    if not script or not script.content:
        return {"added": 0}

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

    # 现有角色名集合（避免重复）
    existing = {
        c.name
        for c in (
            await db.execute(
                select(ProjectCharacter).where(
                    ProjectCharacter.project_id == project_id
                )
            )
        ).scalars().all()
    }

    max_order = (
        await db.execute(
            select(func.max(ProjectCharacter.sort_order)).where(
                ProjectCharacter.project_id == project_id
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
