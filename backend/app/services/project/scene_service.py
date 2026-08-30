# =====================================================
# 场景服务 — 场景 CRUD + 单/批量生图 + 版本管理 + 从剧本提取
#
# 与 character_service 同构，仅表名和字段不同
# （location / time_of_day / atmosphere）
# =====================================================

import logging
from typing import List, Optional

from fastapi import HTTPException
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
from app.services.model_registry import resolve_project_chat_model_id

logger = logging.getLogger("agnes_platform.project.scene")

ENTITY_TYPE = "scene"


# =====================================================
# 场景 CRUD
# =====================================================

async def list_scenes(
    db: AsyncSession, project_id: int, script_id: Optional[int] = None
) -> List[ProjectScene]:
    """列出项目场景（可选按集过滤）"""
    stmt = select(ProjectScene).where(ProjectScene.project_id == project_id)
    if script_id is not None:
        stmt = stmt.where(ProjectScene.script_id == script_id)
    stmt = stmt.order_by(ProjectScene.sort_order)
    result = await db.execute(stmt)
    items = result.scalars().all()
    await attach_active_image_batch(db, ENTITY_TYPE, items)
    # 批量填充 episode_no
    await _fill_episode_no(db, items)
    return items


async def _fill_episode_no(db: AsyncSession, items: List) -> None:
    """批量给场景列表填充 episode_no 字段（从 ProjectScript 查一次字典映射）"""
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
    # 校验 script_id 属于该项目
    script = await db.get(ProjectScript, data.script_id)
    if not script or script.project_id != project_id:
        raise HTTPException(404, "剧本不存在或不属于该项目")

    # 计算 sort_order（按集追加到末尾）
    max_order = (
        await db.execute(
            select(func.max(ProjectScene.sort_order)).where(
                ProjectScene.script_id == data.script_id
            )
        )
    ).scalar() or 0

    scene = ProjectScene(
        project_id=project_id,
        script_id=data.script_id,
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
        project_id=scene.project_id,
        asset_type="scene",
        asset_name=scene.name,
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

async def extract_scenes_from_script(
    db: AsyncSession, project_id: int, script_id: int
) -> dict:
    """从指定集剧本内容重新提取场景清单（追加到该集，不覆盖）"""
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
        raise HTTPException(400, "剧本内容为空，无法提取场景")

    prompt = (
        "请从以下剧本中提取所有场景信息，返回 JSON 格式：\n"
        '{"scenes": [{"name": "场景名", "description": "简介", '
        '"location": "地点", "time_of_day": "时间段", "atmosphere": "氛围"}]}\n\n'
        f"剧本：\n{script.content}"
    )
    model = await resolve_project_chat_model_id(db, project_id)
    if not model:
        raise HTTPException(400, "未配置可用的对话模型，请先在配置页同步或添加对话模型")
    body = {
        "model": model,
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

    # 现有场景名集合（仅限该集，避免重复）
    existing = {
        s.name
        for s in (
            await db.execute(
                select(ProjectScene).where(
                    ProjectScene.script_id == script_id
                )
            )
        ).scalars().all()
    }
    max_order = (
        await db.execute(
            select(func.max(ProjectScene.sort_order)).where(
                ProjectScene.script_id == script_id
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
                script_id=script_id,
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


# =====================================================
# 跨集复制（深拷贝到目标集，不复制分镜关联）
# =====================================================

async def copy_scene_to_script(
    db: AsyncSession, project_id: int, scene_id: int, target_script_id: int
) -> ProjectScene:
    """
    把场景深拷贝到目标集（复制名称/描述/位置/时间/氛围/形象图，不复制分镜关联）

    名称冲突时自动加"（副本）"后缀。
    """
    # 校验源场景属于 project
    src = await get_scene(db, scene_id)
    if not src or src.project_id != project_id:
        raise HTTPException(404, "源场景不存在")

    # 校验目标 script 属于 project
    target_script = await db.get(ProjectScript, target_script_id)
    if not target_script or target_script.project_id != project_id:
        raise HTTPException(404, "目标集剧本不存在")

    # 名称冲突处理
    existing = (
        await db.execute(
            select(ProjectScene).where(
                ProjectScene.script_id == target_script_id,
                ProjectScene.name == src.name,
            )
        )
    ).scalars().first()
    new_name = f"{src.name}（副本）" if existing else src.name

    # sort_order 追加到目标集末尾
    max_order = (
        await db.execute(
            select(func.max(ProjectScene.sort_order)).where(
                ProjectScene.script_id == target_script_id
            )
        )
    ).scalar() or 0

    new_entity = ProjectScene(
        project_id=project_id,
        script_id=target_script_id,
        name=new_name,
        description=src.description,
        location=src.location,
        time_of_day=src.time_of_day,
        atmosphere=src.atmosphere,
        asset_id=src.asset_id,
        active_image_id=src.active_image_id,
        sort_order=max_order + 1,
    )
    db.add(new_entity)
    await db.commit()
    await db.refresh(new_entity)
    await attach_active_image(db, ENTITY_TYPE, new_entity)
    return new_entity
