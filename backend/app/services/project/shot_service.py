# =====================================================
# 分镜服务 — 分镜 CRUD + 绑定实体 + 重排 + 帧 prompt 提取 + 从剧本 AI 拆分
#
# 分镜是项目创作的核心载体，对应 project_shots 表。
# 通过 ProjectShotCharacter / ProjectShotProp 关联表绑定角色/道具。
# =====================================================

import json
import logging
from typing import List, Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import (
    ProjectShot,
    ProjectShotCharacter,
    ProjectShotProp,
    ProjectCharacter,
    ProjectScene,
    ProjectProp,
    ProjectScript,
)
from app.schemas.project import ShotCreate, ShotUpdate
from app.services.agnes_client import agnes_client
from app.services.project.sse_manager import project_sse_manager
from app.services.project.wizard import parse_json_loose

logger = logging.getLogger("agnes_platform.project.shot")


# =====================================================
# 分镜 CRUD
# =====================================================

async def list_shots(db: AsyncSession, project_id: int) -> List[ProjectShot]:
    """
    列出项目所有分镜（按 sort_order）
    含关联的角色/场景/道具（用于前端列表展示）
    """
    result = await db.execute(
        select(ProjectShot)
        .where(ProjectShot.project_id == project_id)
        .order_by(ProjectShot.sort_order)
    )
    shots = result.scalars().all()

    # 批量加载关联（避免 N+1）
    for shot in shots:
        # 加载关联角色
        chars_result = await db.execute(
            select(ProjectCharacter)
            .join(
                ProjectShotCharacter,
                ProjectShotCharacter.character_id == ProjectCharacter.id,
            )
            .where(ProjectShotCharacter.shot_id == shot.id)
            .order_by(ProjectShotCharacter.sort_order)
        )
        shot._characters = chars_result.scalars().all()

        # 加载关联道具
        props_result = await db.execute(
            select(ProjectProp)
            .join(
                ProjectShotProp,
                ProjectShotProp.prop_id == ProjectProp.id,
            )
            .where(ProjectShotProp.shot_id == shot.id)
            .order_by(ProjectShotProp.sort_order)
        )
        shot._props = props_result.scalars().all()

    return shots


async def get_shot(db: AsyncSession, shot_id: int) -> Optional[ProjectShot]:
    """获取分镜详情（含关联实体）"""
    result = await db.execute(
        select(ProjectShot).where(ProjectShot.id == shot_id)
    )
    shot = result.scalar_one_or_none()
    if not shot:
        return None

    # 加载关联
    chars_result = await db.execute(
        select(ProjectCharacter)
        .join(
            ProjectShotCharacter,
            ProjectShotCharacter.character_id == ProjectCharacter.id,
        )
        .where(ProjectShotCharacter.shot_id == shot_id)
        .order_by(ProjectShotCharacter.sort_order)
    )
    shot._characters = chars_result.scalars().all()

    props_result = await db.execute(
        select(ProjectProp)
        .join(ProjectShotProp, ProjectShotProp.prop_id == ProjectProp.id)
        .where(ProjectShotProp.shot_id == shot_id)
        .order_by(ProjectShotProp.sort_order)
    )
    shot._props = props_result.scalars().all()

    return shot


async def create_shot(
    db: AsyncSession, project_id: int, data: ShotCreate
) -> ProjectShot:
    """添加分镜（自动计算 sequence_no 和 sort_order）"""
    max_seq = (
        await db.execute(
            select(func.max(ProjectShot.sequence_no)).where(
                ProjectShot.project_id == project_id
            )
        )
    ).scalar() or 0
    max_order = (
        await db.execute(
            select(func.max(ProjectShot.sort_order)).where(
                ProjectShot.project_id == project_id
            )
        )
    ).scalar() or 0

    shot = ProjectShot(
        project_id=project_id,
        sequence_no=data.sequence_no or (max_seq + 1),
        sort_order=max_order + 1,
        title=data.title,
        shot_type=data.shot_type,
        camera_movement=data.camera_movement,
        angle=data.angle,
        dialogue=data.dialogue,
        visual_desc=data.visual_desc,
        atmosphere=data.atmosphere,
        image_prompt=data.image_prompt,
        duration_ms=data.duration_ms or 3000,
        scene_id=data.scene_id,
        status="draft",
    )
    db.add(shot)
    await db.commit()
    await db.refresh(shot)
    return shot


async def update_shot(
    db: AsyncSession, shot_id: int, data: ShotUpdate
) -> Optional[ProjectShot]:
    """编辑分镜（检测变更字段并推送 SSE）"""
    shot = await get_shot(db, shot_id)
    if not shot:
        return None
    update_data = data.model_dump(exclude_unset=True)
    affected_fields = []
    for k, v in update_data.items():
        old_v = getattr(shot, k, None)
        if old_v != v:
            affected_fields.append(k)
            setattr(shot, k, v)
    await db.commit()
    await db.refresh(shot)

    if affected_fields:
        await project_sse_manager.push(
            shot.project_id,
            "entity_updated",
            {"target": f"shot:{shot_id}", "fields": affected_fields},
        )
    return shot


async def delete_shot(db: AsyncSession, shot_id: int) -> bool:
    """删除分镜（级联删除关联）"""
    shot = await get_shot(db, shot_id)
    if not shot:
        return False
    project_id = shot.project_id
    await db.delete(shot)
    await db.commit()

    await project_sse_manager.push(
        project_id,
        "entity_updated",
        {"target": f"shot:{shot_id}", "action": "deleted"},
    )
    return True


async def reorder_shots(
    db: AsyncSession, project_id: int, shot_ids: List[int]
) -> None:
    """按给定 ID 顺序重排分镜（同时更新 sort_order 与 sequence_no）"""
    for idx, sid in enumerate(shot_ids):
        shot = (
            await db.execute(
                select(ProjectShot).where(
                    ProjectShot.id == sid,
                    ProjectShot.project_id == project_id,
                )
            )
        ).scalar_one_or_none()
        if shot:
            shot.sort_order = idx
            shot.sequence_no = idx + 1
    await db.commit()


# =====================================================
# 绑定实体（角色/道具）
# =====================================================

async def bind_character(
    db: AsyncSession, shot_id: int, character_id: int
) -> bool:
    """绑定角色到分镜（已存在则跳过）"""
    # 检查是否已存在
    exists = (
        await db.execute(
            select(ProjectShotCharacter).where(
                ProjectShotCharacter.shot_id == shot_id,
                ProjectShotCharacter.character_id == character_id,
            )
        )
    ).scalar_one_or_none()
    if exists:
        return True

    # 计算 sort_order
    max_order = (
        await db.execute(
            select(func.max(ProjectShotCharacter.sort_order)).where(
                ProjectShotCharacter.shot_id == shot_id
            )
        )
    ).scalar() or 0

    db.add(
        ProjectShotCharacter(
            shot_id=shot_id,
            character_id=character_id,
            sort_order=max_order + 1,
        )
    )
    await db.commit()

    shot = await get_shot(db, shot_id)
    if shot:
        await project_sse_manager.push(
            shot.project_id,
            "entity_updated",
            {"target": f"shot:{shot_id}", "action": "bind_character", "character_id": character_id},
        )
    return True


async def unbind_character(
    db: AsyncSession, shot_id: int, character_id: int
) -> bool:
    """解绑角色"""
    rel = (
        await db.execute(
            select(ProjectShotCharacter).where(
                ProjectShotCharacter.shot_id == shot_id,
                ProjectShotCharacter.character_id == character_id,
            )
        )
    ).scalar_one_or_none()
    if not rel:
        return False
    await db.delete(rel)
    await db.commit()

    shot = await get_shot(db, shot_id)
    if shot:
        await project_sse_manager.push(
            shot.project_id,
            "entity_updated",
            {"target": f"shot:{shot_id}", "action": "unbind_character", "character_id": character_id},
        )
    return True


async def bind_prop(
    db: AsyncSession, shot_id: int, prop_id: int
) -> bool:
    """绑定道具到分镜"""
    exists = (
        await db.execute(
            select(ProjectShotProp).where(
                ProjectShotProp.shot_id == shot_id,
                ProjectShotProp.prop_id == prop_id,
            )
        )
    ).scalar_one_or_none()
    if exists:
        return True

    max_order = (
        await db.execute(
            select(func.max(ProjectShotProp.sort_order)).where(
                ProjectShotProp.shot_id == shot_id
            )
        )
    ).scalar() or 0

    db.add(
        ProjectShotProp(
            shot_id=shot_id, prop_id=prop_id, sort_order=max_order + 1
        )
    )
    await db.commit()
    return True


async def unbind_prop(
    db: AsyncSession, shot_id: int, prop_id: int
) -> bool:
    """解绑道具"""
    rel = (
        await db.execute(
            select(ProjectShotProp).where(
                ProjectShotProp.shot_id == shot_id,
                ProjectShotProp.prop_id == prop_id,
            )
        )
    ).scalar_one_or_none()
    if not rel:
        return False
    await db.delete(rel)
    await db.commit()
    return True


# =====================================================
# 帧 prompt 提取（单个分镜）
# =====================================================

async def generate_frame_prompt(
    db: AsyncSession, shot_id: int
) -> Optional[ProjectShot]:
    """
    为单个分镜生成/优化帧级绘画 prompt

    通过 LLM 基于分镜的 visual_desc / dialogue / 关联实体生成英文绘画 prompt
    """
    shot = await get_shot(db, shot_id)
    if not shot:
        return None

    # 构建上下文
    char_info = ", ".join(
        [f"{c.name}({c.appearance_desc or c.description})" for c in shot._props]
    ) if hasattr(shot, "_characters") else ""
    # 重新加载角色（_props 可能未加载）
    chars_result = await db.execute(
        select(ProjectCharacter)
        .join(
            ProjectShotCharacter,
            ProjectShotCharacter.character_id == ProjectCharacter.id,
        )
        .where(ProjectShotCharacter.shot_id == shot_id)
    )
    chars = chars_result.scalars().all()
    char_info = ", ".join(
        [f"{c.name}({c.appearance_desc or c.description or ''})" for c in chars]
    )

    prompt = (
        "请基于以下分镜信息生成一段详细的英文绘画 prompt，"
        "用于 AI 图片生成。要求：\n"
        "1. 包含主体、场景、光照、构图、风格等细节\n"
        "2. 不要使用 SD 语法权重括号 (keyword:weight)\n"
        "3. 只返回 prompt 文本，不要附加任何说明\n\n"
        f"分镜标题：{shot.title or ''}\n"
        f"画面描述：{shot.visual_desc or ''}\n"
        f"氛围：{shot.atmosphere or ''}\n"
        f"景别：{shot.shot_type or ''}\n"
        f"运镜：{shot.camera_movement or ''}\n"
        f"视角：{shot.angle or ''}\n"
        f"关联角色：{char_info}\n"
        f"台词：{shot.dialogue or ''}\n"
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
        return shot
    text = choices[0].get("message", {}).get("content", "") or ""
    text = text.strip()

    if text:
        shot.image_prompt = text
        await db.commit()
        await db.refresh(shot)

        await project_sse_manager.push(
            shot.project_id,
            "entity_updated",
            {"target": f"shot:{shot_id}", "fields": ["image_prompt"]},
        )
    return shot


# =====================================================
# 从剧本 AI 拆分分镜（E2 - 注入实体清单）
# =====================================================

async def split_shots_from_script(
    db: AsyncSession, project_id: int
) -> dict:
    """
    从剧本重新 AI 拆分分镜（追加，不覆盖现有分镜）

    Returns:
        {"added": N}
    """
    script = (
        await db.execute(
            select(ProjectScript)
            .where(ProjectScript.project_id == project_id)
            .order_by(ProjectScript.episode_no)
        )
    ).scalars().first()
    if not script or not script.content:
        return {"added": 0}

    # 注入实体清单（E2）
    chars = (
        await db.execute(
            select(ProjectCharacter).where(ProjectCharacter.project_id == project_id)
        )
    ).scalars().all()
    scenes = (
        await db.execute(
            select(ProjectScene).where(ProjectScene.project_id == project_id)
        )
    ).scalars().all()
    props = (
        await db.execute(
            select(ProjectProp).where(ProjectProp.project_id == project_id)
        )
    ).scalars().all()

    char_info = json.dumps(
        [{"id": c.id, "name": c.name} for c in chars], ensure_ascii=False
    )
    scene_info = json.dumps(
        [{"id": s.id, "name": s.name} for s in scenes], ensure_ascii=False
    )
    prop_info = json.dumps(
        [{"id": p.id, "name": p.name} for p in props], ensure_ascii=False
    )

    prompt = (
        "请将以下剧本拆分为分镜列表，返回 JSON 格式：\n"
        '{"shots": [{"title": "分镜标题", "shot_type": "景别", '
        '"camera_movement": "运镜", "angle": "视角", "dialogue": "台词", '
        '"visual_desc": "画面描述", "atmosphere": "氛围", '
        '"duration_ms": 3000, "scene_name": "场景名", '
        '"characters_in_scene": ["角色名"], "props_in_scene": ["道具名"]}]}\n\n'
        f"剧本：\n{script.content}\n\n"
        f"可选角色清单：{char_info}\n"
        f"可选场景清单：{scene_info}\n"
        f"可选道具清单：{prop_info}\n"
    )
    body = {
        "model": "agnes-2.0-flash",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.6,
    }
    result = await agnes_client._post(
        f"{agnes_client.base_url}/chat/completions", body
    )
    choices = result.get("choices", [])
    if not choices:
        return {"added": 0}
    text = choices[0].get("message", {}).get("content", "") or ""
    parsed = parse_json_loose(text)

    # 构建映射
    char_map = {c.name: c.id for c in chars}
    scene_map = {s.name: s.id for s in scenes}
    prop_map = {p.name: p.id for p in props}

    # 计算 sequence_no / sort_order 起点
    max_seq = (
        await db.execute(
            select(func.max(ProjectShot.sequence_no)).where(
                ProjectShot.project_id == project_id
            )
        )
    ).scalar() or 0
    max_order = (
        await db.execute(
            select(func.max(ProjectShot.sort_order)).where(
                ProjectShot.project_id == project_id
            )
        )
    ).scalar() or 0

    added = 0
    for shot_data in parsed.get("shots", parsed.get("storyboard", [])):
        max_seq += 1
        max_order += 1
        shot = ProjectShot(
            project_id=project_id,
            script_id=script.id,
            sequence_no=max_seq,
            sort_order=max_order,
            title=shot_data.get("title", f"分镜 {max_seq}"),
            shot_type=shot_data.get("shot_type", ""),
            camera_movement=shot_data.get("camera_movement", ""),
            angle=shot_data.get("angle", ""),
            dialogue=shot_data.get("dialogue", ""),
            visual_desc=shot_data.get("visual_desc", ""),
            atmosphere=shot_data.get("atmosphere", ""),
            image_prompt=shot_data.get("visual_desc", ""),
            duration_ms=shot_data.get("duration_ms", 3000),
            scene_id=scene_map.get(shot_data.get("scene_name", "")),
            status="draft",
        )
        db.add(shot)
        await db.flush()

        for char_name in shot_data.get("characters_in_scene", []):
            cid = char_map.get(char_name)
            if cid:
                db.add(
                    ProjectShotCharacter(shot_id=shot.id, character_id=cid)
                )

        for prop_name in shot_data.get("props_in_scene", []):
            pid = prop_map.get(prop_name)
            if pid:
                db.add(ProjectShotProp(shot_id=shot.id, prop_id=pid))

        added += 1

    await db.commit()

    await project_sse_manager.push(
        project_id,
        "entity_updated",
        {"target": f"project:{project_id}", "action": "shots_added", "count": added},
    )
    return {"added": added}
