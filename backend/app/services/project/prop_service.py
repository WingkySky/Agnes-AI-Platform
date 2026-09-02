# =====================================================
# 道具服务 — 道具 CRUD + 单/批量生图 + 版本管理 + 从剧本提取
#
# 与 character_service 同构，仅表名和字段不同（visual_desc）
# =====================================================

import logging
from typing import List, Optional

from fastapi import HTTPException
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
from app.services.project._async_gen import submit_image_task, claim_generation
from app.services.project._generation_history import record_manual_upload
from app.services.project.sse_manager import project_sse_manager
from app.services.project.wizard import parse_json_loose
from app.services.model_registry import resolve_project_chat_model_id

logger = logging.getLogger("agnes_platform.project.prop")

ENTITY_TYPE = "prop"


# =====================================================
# 道具 CRUD
# =====================================================

async def list_props(
    db: AsyncSession, project_id: int, script_id: Optional[int] = None
) -> List[ProjectProp]:
    """列出项目道具（可选按集过滤）"""
    stmt = select(ProjectProp).where(ProjectProp.project_id == project_id)
    if script_id is not None:
        stmt = stmt.where(ProjectProp.script_id == script_id)
    stmt = stmt.order_by(ProjectProp.sort_order)
    result = await db.execute(stmt)
    items = result.scalars().all()
    await attach_active_image_batch(db, ENTITY_TYPE, items)
    # 批量填充 episode_no
    await _fill_episode_no(db, items)
    return items


async def _fill_episode_no(db: AsyncSession, items: List) -> None:
    """批量给道具列表填充 episode_no 字段（从 ProjectScript 查一次字典映射）"""
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
    # 校验 script_id 属于该项目
    script = await db.get(ProjectScript, data.script_id)
    if not script or script.project_id != project_id:
        raise HTTPException(404, "剧本不存在或不属于该项目")

    # 计算 sort_order（按集追加到末尾）
    max_order = (
        await db.execute(
            select(func.max(ProjectProp.sort_order)).where(
                ProjectProp.script_id == data.script_id
            )
        )
    ).scalar() or 0

    prop = ProjectProp(
        project_id=project_id,
        script_id=data.script_id,
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
) -> dict:
    """生成单个道具图（异步模式）"""
    prop = await get_prop(db, prop_id)
    if not prop:
        return None

    prompt_parts = [prop.visual_desc or prop.description or prop.name]
    if style_config:
        for k, v in style_config.items():
            if v:
                prompt_parts.append(f"{k}: {v}")
    prompt = ", ".join(prompt_parts)
    used_model = model or "agnes-image-2.0-flash"

    task_id = await submit_image_task(
        db, user_id, prompt, used_model, size, mode="text2image",
        ref_type="project_prop_image",
        project_id=prop.project_id,
        asset_type="prop",
        asset_name=prop.name,
    )

    await project_sse_manager.push(
        prop.project_id,
        "generation_started",
        {
            "target": f"{ENTITY_TYPE}:{prop_id}",
            "version_type": "image",
            "user_id": user_id,
            "task_id": task_id,
        },
    )

    return {
        "task_id": task_id,
        "entity_type": ENTITY_TYPE,
        "entity_id": prop_id,
        "status": "pending",
        "prompt": prompt,
    }


async def claim_prop_image(
    db: AsyncSession, prop_id: int, task_id: str
) -> Optional[ProjectProp]:
    """任务完成后认领结果"""
    prop = await get_prop(db, prop_id)
    if not prop:
        return None

    gen = await claim_generation(db, task_id)
    if not gen or not gen.result_url:
        return None

    asset, _ = await create_version(
        db,
        project_id=prop.project_id,
        entity_type=ENTITY_TYPE,
        entity_id=prop_id,
        file_url=gen.result_url,
        thumbnail_url=gen.result_url,
        prompt=gen.prompt or "",
        model=gen.model or "",
        file_type="image",
        generation_id=gen.id,
        set_active=True,
    )

    await project_sse_manager.push(
        prop.project_id,
        "generation_completed",
        {
            "target": f"{ENTITY_TYPE}:{prop_id}",
            "version_id": asset.id,
            "file_url": gen.result_url,
            "generation_id": gen.id,
            "task_id": task_id,
        },
    )
    await attach_active_image(db, ENTITY_TYPE, prop)
    return prop


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

    gen_record = await record_manual_upload(
        db, user_id, "image", file_url, name=prop.name,
    )

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
        generation_id=gen_record.id,
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

async def extract_props_from_script(
    db: AsyncSession, project_id: int, script_id: int
) -> dict:
    """从指定集剧本内容重新提取道具清单（追加到该集，不覆盖）"""
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
        raise HTTPException(400, "剧本内容为空，无法提取道具")

    prompt = (
        "请从以下剧本中提取所有道具信息，返回 JSON 格式：\n"
        '{"props": [{"name": "道具名", "description": "简介", '
        '"visual_desc": "视觉描述"}]}\n\n'
        f"剧本：\n{script.content}"
    )
    model = await resolve_project_chat_model_id(db, project_id)
    if not model:
        raise HTTPException(400, "未配置可用的对话模型，请先在配置页同步或添加对话模型")
    text = await agnes_client.chat_text(
        model, [{"role": "user", "content": prompt}], temperature=0.5,
    )
    parsed = parse_json_loose(text)

    # 现有道具名集合（仅限该集，避免重复）
    existing = {
        p.name
        for p in (
            await db.execute(
                select(ProjectProp).where(
                    ProjectProp.script_id == script_id
                )
            )
        ).scalars().all()
    }

    max_order = (
        await db.execute(
            select(func.max(ProjectProp.sort_order)).where(
                ProjectProp.script_id == script_id
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
                script_id=script_id,
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


# =====================================================
# 跨集复制（深拷贝到目标集，不复制分镜关联）
# =====================================================

async def copy_prop_to_script(
    db: AsyncSession, project_id: int, prop_id: int, target_script_id: int
) -> ProjectProp:
    """把道具深拷贝到目标集（复制名称/描述/视觉描述/形象图引用，不复制分镜关联）"""
    # 校验源道具属于 project
    src = await get_prop(db, prop_id)
    if not src or src.project_id != project_id:
        raise HTTPException(404, "源道具不存在")

    # 校验目标 script 属于 project
    target_script = await db.get(ProjectScript, target_script_id)
    if not target_script or target_script.project_id != project_id:
        raise HTTPException(404, "目标集剧本不存在")

    # 名称冲突处理
    existing = (
        await db.execute(
            select(ProjectProp).where(
                ProjectProp.script_id == target_script_id,
                ProjectProp.name == src.name,
            )
        )
    ).scalars().first()
    new_name = f"{src.name}（副本）" if existing else src.name

    # sort_order 追加到目标集末尾
    max_order = (
        await db.execute(
            select(func.max(ProjectProp.sort_order)).where(
                ProjectProp.script_id == target_script_id
            )
        )
    ).scalar() or 0

    new_entity = ProjectProp(
        project_id=project_id,
        script_id=target_script_id,
        name=new_name,
        description=src.description,
        visual_desc=src.visual_desc,
        asset_id=src.asset_id,
        active_image_id=src.active_image_id,
        sort_order=max_order + 1,
    )
    db.add(new_entity)
    await db.commit()
    await db.refresh(new_entity)
    await attach_active_image(db, ENTITY_TYPE, new_entity)
    return new_entity
