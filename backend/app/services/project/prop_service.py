# =====================================================
# 道具服务 — 道具 CRUD + 单/批量生图 + 版本管理 + 从剧本提取
#
# 与 character_service 同构，仅表名和字段不同（visual_desc）
# =====================================================

import logging
from typing import List, Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import ProjectProp, ProjectScript
from app.schemas.project import PropCreate, PropUpdate
from app.services.agnes_client import agnes_client
from app.services.project._entity_versions import (
    create_version,
    list_versions,
    set_active_version,
    delete_version,
    attach_active_image,
    attach_active_image_batch,
)
from app.services.project.sse_manager import project_sse_manager
from app.services.project.wizard import parse_json_loose

logger = logging.getLogger("agnes_platform.project.prop")

ENTITY_TYPE = "prop"


# =====================================================
# 道具 CRUD
# =====================================================

async def list_props(
    db: AsyncSession, project_id: int
) -> List[ProjectProp]:
    """列出项目所有道具（按 sort_order）"""
    result = await db.execute(
        select(ProjectProp)
        .where(ProjectProp.project_id == project_id)
        .order_by(ProjectProp.sort_order)
    )
    items = result.scalars().all()
    await attach_active_image_batch(db, ENTITY_TYPE, items)
    return items


async def get_prop(db: AsyncSession, prop_id: int) -> Optional[ProjectProp]:
    """获取道具详情"""
    result = await db.execute(
        select(ProjectProp).where(ProjectProp.id == prop_id)
    )
    item = result.scalar_one_or_none()
    if item:
        await attach_active_image(db, ENTITY_TYPE, item)
    return item


async def create_prop(
    db: AsyncSession, project_id: int, data: PropCreate
) -> ProjectProp:
    """添加道具"""
    max_order = (
        await db.execute(
            select(func.max(ProjectProp.sort_order)).where(
                ProjectProp.project_id == project_id
            )
        )
    ).scalar() or 0

    prop = ProjectProp(
        project_id=project_id,
        name=data.name,
        description=data.description,
        visual_desc=data.visual_desc,
        sort_order=max_order + 1,
        asset_id=data.asset_id,
    )
    db.add(prop)
    await db.commit()
    await db.refresh(prop)
    await attach_active_image(db, ENTITY_TYPE, prop)
    return prop


async def update_prop(
    db: AsyncSession, prop_id: int, data: PropUpdate
) -> Optional[ProjectProp]:
    """编辑道具"""
    prop = await get_prop(db, prop_id)
    if not prop:
        return None
    update_data = data.model_dump(exclude_unset=True)
    for k, v in update_data.items():
        setattr(prop, k, v)
    await db.commit()
    await db.refresh(prop)
    await attach_active_image(db, ENTITY_TYPE, prop)

    await project_sse_manager.push(
        prop.project_id,
        "entity_updated",
        {"target": f"{ENTITY_TYPE}:{prop_id}", "fields": list(update_data.keys())},
    )
    return prop


async def delete_prop(db: AsyncSession, prop_id: int) -> bool:
    """删除道具"""
    prop = await get_prop(db, prop_id)
    if not prop:
        return False
    project_id = prop.project_id
    await db.delete(prop)
    await db.commit()

    await project_sse_manager.push(
        project_id,
        "entity_updated",
        {"target": f"{ENTITY_TYPE}:{prop_id}", "action": "deleted"},
    )
    return True


async def reorder_props(
    db: AsyncSession, project_id: int, prop_ids: List[int]
) -> None:
    """按给定 ID 顺序重排道具"""
    for idx, pid in enumerate(prop_ids):
        prop = (
            await db.execute(
                select(ProjectProp).where(
                    ProjectProp.id == pid,
                    ProjectProp.project_id == project_id,
                )
            )
        ).scalar_one_or_none()
        if prop:
            prop.sort_order = idx
    await db.commit()


# =====================================================
# 道具图生成（单/批量）
# =====================================================

async def generate_prop_image(
    db: AsyncSession,
    prop_id: int,
    user_id: int,
    style_config: Optional[dict] = None,
    model: str = "",
    size: str = "1024x1024",
) -> Optional[ProjectProp]:
    """生成单个道具图"""
    prop = await get_prop(db, prop_id)
    if not prop:
        return None

    prompt_parts = [prop.visual_desc or prop.description or prop.name]
    if style_config:
        for k, v in style_config.items():
            if v:
                prompt_parts.append(f"{k}: {v}")
    prompt = ", ".join(prompt_parts)

    await project_sse_manager.push(
        prop.project_id,
        "generation_started",
        {
            "target": f"{ENTITY_TYPE}:{prop_id}",
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
        data_list = result.get("data", [])
        if not data_list:
            raise RuntimeError("图片生成返回空数据")
        image_url = data_list[0].get("url", "")
        if not image_url:
            raise RuntimeError("图片生成未返回 URL")

        asset, _ = await create_version(
            db,
            project_id=prop.project_id,
            entity_type=ENTITY_TYPE,
            entity_id=prop_id,
            file_url=image_url,
            thumbnail_url=image_url,
            prompt=prompt,
            model=model or "agnes-image-2.0-flash",
            file_type="image",
            set_active=True,
        )

        await project_sse_manager.push(
            prop.project_id,
            "generation_completed",
            {
                "target": f"{ENTITY_TYPE}:{prop_id}",
                "version_id": asset.id,
                "file_url": image_url,
            },
        )
        await attach_active_image(db, ENTITY_TYPE, prop)
        return prop
    except Exception as e:
        await project_sse_manager.push(
            prop.project_id,
            "generation_failed",
            {"target": f"{ENTITY_TYPE}:{prop_id}", "error": str(e)},
        )
        raise


async def batch_generate_props(
    db: AsyncSession,
    prop_ids: List[int],
    user_id: int,
    style_config: Optional[dict] = None,
    model: str = "",
    size: str = "1024x1024",
) -> List[dict]:
    """批量生成道具图"""
    results = []
    for pid in prop_ids:
        try:
            await generate_prop_image(db, pid, user_id, style_config, model, size)
            results.append({"prop_id": pid, "success": True})
        except Exception as e:
            results.append({"prop_id": pid, "success": False, "error": str(e)})
    return results


async def upload_prop_image(
    db: AsyncSession,
    prop_id: int,
    user_id: int,
    file_url: str,
    thumbnail_url: str = "",
    file_size: Optional[int] = None,
    width: Optional[int] = None,
    height: Optional[int] = None,
) -> Optional[ProjectProp]:
    """用户手动上传道具图作为新版本（G1）"""
    prop = await get_prop(db, prop_id)
    if not prop:
        return None

    await create_version(
        db,
        project_id=prop.project_id,
        entity_type=ENTITY_TYPE,
        entity_id=prop_id,
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
    await attach_active_image(db, ENTITY_TYPE, prop)
    return prop


# =====================================================
# 版本管理
# =====================================================

async def list_prop_versions(db: AsyncSession, prop_id: int):
    return await list_versions(db, ENTITY_TYPE, prop_id)


async def set_active_prop_version(
    db: AsyncSession, prop_id: int, version_id: int
):
    return await set_active_version(db, ENTITY_TYPE, prop_id, version_id)


async def delete_prop_version(
    db: AsyncSession, prop_id: int, version_id: int
) -> bool:
    return await delete_version(db, ENTITY_TYPE, prop_id, version_id)


# =====================================================
# 从剧本重新提取道具
# =====================================================

async def extract_props_from_script(db: AsyncSession, project_id: int) -> dict:
    """从剧本重新提取道具（追加，不覆盖）"""
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
        "请从以下剧本中提取所有道具信息，返回 JSON 格式：\n"
        '{"props": [{"name": "道具名", "description": "简介", '
        '"visual_desc": "视觉描述"}]}\n\n'
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

    existing = {
        p.name
        for p in (
            await db.execute(
                select(ProjectProp).where(ProjectProp.project_id == project_id)
            )
        ).scalars().all()
    }
    max_order = (
        await db.execute(
            select(func.max(ProjectProp.sort_order)).where(
                ProjectProp.project_id == project_id
            )
        )
    ).scalar() or 0

    added = 0
    for item in parsed.get("props", []):
        name = item.get("name", "").strip()
        if not name or name in existing:
            continue
        max_order += 1
        db.add(
            ProjectProp(
                project_id=project_id,
                name=name,
                description=item.get("description", ""),
                visual_desc=item.get("visual_desc", ""),
                sort_order=max_order,
            )
        )
        existing.add(name)
        added += 1

    await db.commit()
    return {"added": added}
