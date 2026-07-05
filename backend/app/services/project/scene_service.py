# =====================================================
# 场景服务 — 场景 CRUD + 单/批量生图 + 版本管理 + 从剧本提取
#
# 与 character_service 同构，仅表名和字段不同
# （location / time_of_day / atmosphere）
# =====================================================

import logging
from typing import List, Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import ProjectScene, ProjectScript
from app.schemas.project import SceneCreate, SceneUpdate
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

logger = logging.getLogger("agnes_platform.project.scene")

ENTITY_TYPE = "scene"


# =====================================================
# 场景 CRUD
# =====================================================

async def list_scenes(
    db: AsyncSession, project_id: int
) -> List[ProjectScene]:
    """列出项目所有场景（按 sort_order）"""
    result = await db.execute(
        select(ProjectScene)
        .where(ProjectScene.project_id == project_id)
        .order_by(ProjectScene.sort_order)
    )
    items = result.scalars().all()
    await attach_active_image_batch(db, ENTITY_TYPE, items)
    return items


async def get_scene(db: AsyncSession, scene_id: int) -> Optional[ProjectScene]:
    """获取场景详情"""
    result = await db.execute(
        select(ProjectScene).where(ProjectScene.id == scene_id)
    )
    item = result.scalar_one_or_none()
    if item:
        await attach_active_image(db, ENTITY_TYPE, item)
    return item


async def create_scene(
    db: AsyncSession, project_id: int, data: SceneCreate
) -> ProjectScene:
    """添加场景"""
    max_order = (
        await db.execute(
            select(func.max(ProjectScene.sort_order)).where(
                ProjectScene.project_id == project_id
            )
        )
    ).scalar() or 0

    scene = ProjectScene(
        project_id=project_id,
        name=data.name,
        description=data.description,
        location=data.location,
        time_of_day=data.time_of_day,
        atmosphere=data.atmosphere,
        sort_order=max_order + 1,
        asset_id=data.asset_id,
    )
    db.add(scene)
    await db.commit()
    await db.refresh(scene)
    await attach_active_image(db, ENTITY_TYPE, scene)
    return scene


async def update_scene(
    db: AsyncSession, scene_id: int, data: SceneUpdate
) -> Optional[ProjectScene]:
    """编辑场景"""
    scene = await get_scene(db, scene_id)
    if not scene:
        return None
    update_data = data.model_dump(exclude_unset=True)
    for k, v in update_data.items():
        setattr(scene, k, v)
    await db.commit()
    await db.refresh(scene)
    await attach_active_image(db, ENTITY_TYPE, scene)

    await project_sse_manager.push(
        scene.project_id,
        "entity_updated",
        {"target": f"{ENTITY_TYPE}:{scene_id}", "fields": list(update_data.keys())},
    )
    return scene


async def delete_scene(db: AsyncSession, scene_id: int) -> bool:
    """删除场景"""
    scene = await get_scene(db, scene_id)
    if not scene:
        return False
    project_id = scene.project_id
    await db.delete(scene)
    await db.commit()

    await project_sse_manager.push(
        project_id,
        "entity_updated",
        {"target": f"{ENTITY_TYPE}:{scene_id}", "action": "deleted"},
    )
    return True


async def reorder_scenes(
    db: AsyncSession, project_id: int, scene_ids: List[int]
) -> None:
    """按给定 ID 顺序重排场景"""
    for idx, sid in enumerate(scene_ids):
        scene = (
            await db.execute(
                select(ProjectScene).where(
                    ProjectScene.id == sid,
                    ProjectScene.project_id == project_id,
                )
            )
        ).scalar_one_or_none()
        if scene:
            scene.sort_order = idx
    await db.commit()


# =====================================================
# 场景图生成（单/批量）
# =====================================================

async def generate_scene_image(
    db: AsyncSession,
    scene_id: int,
    user_id: int,
    style_config: Optional[dict] = None,
    model: str = "",
    size: str = "1024x1024",
) -> dict:
    """生成单个场景图（异步模式）"""
    scene = await get_scene(db, scene_id)
    if not scene:
        return None

    prompt_parts = [
        scene.description or scene.name,
        f"location: {scene.location}" if scene.location else "",
        f"time: {scene.time_of_day}" if scene.time_of_day else "",
        f"atmosphere: {scene.atmosphere}" if scene.atmosphere else "",
    ]
    if style_config:
        for k, v in style_config.items():
            if v:
                prompt_parts.append(f"{k}: {v}")
    prompt = ", ".join([p for p in prompt_parts if p])
    used_model = model or "agnes-image-2.0-flash"

    task_id = await submit_image_task(
        db, user_id, prompt, used_model, size, mode="text2image",
        ref_type="project_scene_image",
    )

    await project_sse_manager.push(
        scene.project_id,
        "generation_started",
        {
            "target": f"{ENTITY_TYPE}:{scene_id}",
            "version_type": "image",
            "user_id": user_id,
            "task_id": task_id,
        },
    )

    return {
        "task_id": task_id,
        "entity_type": ENTITY_TYPE,
        "entity_id": scene_id,
        "status": "pending",
        "prompt": prompt,
    }


async def claim_scene_image(
    db: AsyncSession, scene_id: int, task_id: str
) -> Optional[ProjectScene]:
    """任务完成后认领结果"""
    scene = await get_scene(db, scene_id)
    if not scene:
        return None

    gen = await claim_generation(db, task_id)
    if not gen or not gen.result_url:
        return None

    asset, _ = await create_version(
        db,
        project_id=scene.project_id,
        entity_type=ENTITY_TYPE,
        entity_id=scene_id,
        file_url=gen.result_url,
        thumbnail_url=gen.result_url,
        prompt=gen.prompt or "",
        model=gen.model or "",
        file_type="image",
        generation_id=gen.id,
        set_active=True,
    )

    await project_sse_manager.push(
        scene.project_id,
        "generation_completed",
        {
            "target": f"{ENTITY_TYPE}:{scene_id}",
            "version_id": asset.id,
            "file_url": gen.result_url,
            "generation_id": gen.id,
            "task_id": task_id,
        },
    )
    await attach_active_image(db, ENTITY_TYPE, scene)
    return scene


async def batch_generate_scenes(
    db: AsyncSession,
    scene_ids: List[int],
    user_id: int,
    style_config: Optional[dict] = None,
    model: str = "",
    size: str = "1024x1024",
) -> List[dict]:
    """批量生成场景图"""
    results = []
    for sid in scene_ids:
        try:
            await generate_scene_image(db, sid, user_id, style_config, model, size)
            results.append({"scene_id": sid, "success": True})
        except Exception as e:
            results.append({"scene_id": sid, "success": False, "error": str(e)})
    return results


async def upload_scene_image(
    db: AsyncSession,
    scene_id: int,
    user_id: int,
    file_url: str,
    thumbnail_url: str = "",
    file_size: Optional[int] = None,
    width: Optional[int] = None,
    height: Optional[int] = None,
) -> Optional[ProjectScene]:
    """用户手动上传场景图作为新版本（G1）"""
    scene = await get_scene(db, scene_id)
    if not scene:
        return None

    gen_record = await record_manual_upload(
        db, user_id, "image", file_url, name=scene.name,
    )

    await create_version(
        db,
        project_id=scene.project_id,
        entity_type=ENTITY_TYPE,
        entity_id=scene_id,
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
    await attach_active_image(db, ENTITY_TYPE, scene)
    return scene


# =====================================================
# 版本管理
# =====================================================

async def list_scene_versions(db: AsyncSession, scene_id: int):
    return await list_versions(db, ENTITY_TYPE, scene_id)


async def set_active_scene_version(
    db: AsyncSession, scene_id: int, version_id: int
):
    return await set_active_version(db, ENTITY_TYPE, scene_id, version_id)


async def delete_scene_version(
    db: AsyncSession, scene_id: int, version_id: int
) -> bool:
    return await delete_version(db, ENTITY_TYPE, scene_id, version_id)


# =====================================================
# 从剧本重新提取场景
# =====================================================

async def extract_scenes_from_script(db: AsyncSession, project_id: int) -> dict:
    """从剧本重新提取场景（追加，不覆盖）"""
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
        "请从以下剧本中提取所有场景信息，返回 JSON 格式：\n"
        '{"scenes": [{"name": "场景名", "description": "简介", '
        '"location": "地点", "time_of_day": "时间段", "atmosphere": "氛围"}]}\n\n'
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
        s.name
        for s in (
            await db.execute(
                select(ProjectScene).where(ProjectScene.project_id == project_id)
            )
        ).scalars().all()
    }
    max_order = (
        await db.execute(
            select(func.max(ProjectScene.sort_order)).where(
                ProjectScene.project_id == project_id
            )
        )
    ).scalar() or 0

    added = 0
    for item in parsed.get("scenes", []):
        name = item.get("name", "").strip()
        if not name or name in existing:
            continue
        max_order += 1
        db.add(
            ProjectScene(
                project_id=project_id,
                name=name,
                description=item.get("description", ""),
                location=item.get("location", ""),
                time_of_day=item.get("time_of_day", ""),
                atmosphere=item.get("atmosphere", ""),
                sort_order=max_order,
            )
        )
        existing.add(name)
        added += 1

    await db.commit()
    return {"added": added}
