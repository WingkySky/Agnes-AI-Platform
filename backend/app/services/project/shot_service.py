# =====================================================
# 分镜服务 — 分镜 CRUD + 绑定实体 + 重排 + 帧 prompt 提取 + 从剧本 AI 拆分
#
# 分镜是项目创作的核心载体，对应 project_shots 表。
# 通过 ProjectShotCharacter / ProjectShotProp 关联表绑定角色/道具。
# =====================================================

import json
import logging
from typing import List, Optional

from fastapi import HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import (
    ProjectShot,
    ProjectShotCharacter,
    ProjectShotProp,
    ProjectShotFrameImage,
    ProjectShotVideo,
    ProjectShotAudio,
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
# 内部工具：给 shot 注入关联数据（用于响应序列化）
# =====================================================

async def _attach_shot_relations(db: AsyncSession, shot: ProjectShot) -> None:
    """
    给单个 shot 注入关联数据到 __dict__（避免 SQLAlchemy async lazy load 报错）：
    - characters / props（关联实体）
    - frame_images / videos / audios（多版本列表）
    - active_frame_image / active_video / active_audio（采用版）
    """
    # 角色
    chars_result = await db.execute(
        select(ProjectCharacter)
        .join(
            ProjectShotCharacter,
            ProjectShotCharacter.character_id == ProjectCharacter.id,
        )
        .where(ProjectShotCharacter.shot_id == shot.id)
        .order_by(ProjectShotCharacter.sort_order)
    )
    shot.__dict__["characters"] = chars_result.scalars().all()

    # 道具
    props_result = await db.execute(
        select(ProjectProp)
        .join(ProjectShotProp, ProjectShotProp.prop_id == ProjectProp.id)
        .where(ProjectShotProp.shot_id == shot.id)
        .order_by(ProjectShotProp.sort_order)
    )
    shot.__dict__["props"] = props_result.scalars().all()

    # 帧图版本列表
    frames_result = await db.execute(
        select(ProjectShotFrameImage)
        .where(ProjectShotFrameImage.shot_id == shot.id)
        .order_by(ProjectShotFrameImage.version.desc())
    )
    frames = frames_result.scalars().all()
    shot.__dict__["frame_images"] = frames

    # 视频版本列表
    videos_result = await db.execute(
        select(ProjectShotVideo)
        .where(ProjectShotVideo.shot_id == shot.id)
        .order_by(ProjectShotVideo.version.desc())
    )
    videos = videos_result.scalars().all()
    shot.__dict__["videos"] = videos

    # 音频版本列表（Phase 2）
    audios_result = await db.execute(
        select(ProjectShotAudio)
        .where(ProjectShotAudio.shot_id == shot.id)
        .order_by(ProjectShotAudio.version.desc())
    )
    audios = audios_result.scalars().all()
    shot.__dict__["audios"] = audios

    # 采用帧图
    active_frame = None
    if shot.active_frame_image_id:
        active_frame = next((f for f in frames if f.id == shot.active_frame_image_id), None)
    if not active_frame and frames:
        # 回退：取 is_active=True 的
        active_frame = next((f for f in frames if f.is_active), None)
    shot.__dict__["active_frame_image"] = active_frame

    # 采用视频
    active_vid = None
    if shot.active_video_id:
        active_vid = next((v for v in videos if v.id == shot.active_video_id), None)
    if not active_vid and videos:
        active_vid = next((v for v in videos if v.is_active), None)
    shot.__dict__["active_video"] = active_vid

    # 采用音频（Phase 2）
    active_audio = None
    if shot.active_audio_id:
        active_audio = next((a for a in audios if a.id == shot.active_audio_id), None)
    if not active_audio and audios:
        active_audio = next((a for a in audios if a.is_active), None)
    shot.__dict__["active_audio"] = active_audio


async def _attach_shot_relations_batch(db: AsyncSession, shots: List[ProjectShot]) -> None:
    """批量给 shots 注入关联数据（减少查询次数）"""
    if not shots:
        return
    shot_ids = [s.id for s in shots]

    # 角色关联（一次查所有）
    char_rows = (
        await db.execute(
            select(ProjectShotCharacter.shot_id, ProjectCharacter)
            .join(
                ProjectCharacter,
                ProjectCharacter.id == ProjectShotCharacter.character_id,
            )
            .where(ProjectShotCharacter.shot_id.in_(shot_ids))
            .order_by(ProjectShotCharacter.shot_id, ProjectShotCharacter.sort_order)
        )
    ).all()
    char_map: dict = {}
    for sid, char in char_rows:
        char_map.setdefault(sid, []).append(char)

    # 道具关联
    prop_rows = (
        await db.execute(
            select(ProjectShotProp.shot_id, ProjectProp)
            .join(ProjectProp, ProjectProp.id == ProjectShotProp.prop_id)
            .where(ProjectShotProp.shot_id.in_(shot_ids))
            .order_by(ProjectShotProp.shot_id, ProjectShotProp.sort_order)
        )
    ).all()
    prop_map: dict = {}
    for sid, prop in prop_rows:
        prop_map.setdefault(sid, []).append(prop)

    # 帧图
    frame_rows = (
        await db.execute(
            select(ProjectShotFrameImage)
            .where(ProjectShotFrameImage.shot_id.in_(shot_ids))
            .order_by(ProjectShotFrameImage.shot_id, ProjectShotFrameImage.version.desc())
        )
    ).scalars().all()
    frame_map: dict = {}
    for f in frame_rows:
        frame_map.setdefault(f.shot_id, []).append(f)

    # 视频
    video_rows = (
        await db.execute(
            select(ProjectShotVideo)
            .where(ProjectShotVideo.shot_id.in_(shot_ids))
            .order_by(ProjectShotVideo.shot_id, ProjectShotVideo.version.desc())
        )
    ).scalars().all()
    video_map: dict = {}
    for v in video_rows:
        video_map.setdefault(v.shot_id, []).append(v)

    # 音频（Phase 2）
    audio_rows = (
        await db.execute(
            select(ProjectShotAudio)
            .where(ProjectShotAudio.shot_id.in_(shot_ids))
            .order_by(ProjectShotAudio.shot_id, ProjectShotAudio.version.desc())
        )
    ).scalars().all()
    audio_map: dict = {}
    for a in audio_rows:
        audio_map.setdefault(a.shot_id, []).append(a)

    for shot in shots:
        sid = shot.id
        frames = frame_map.get(sid, [])
        videos = video_map.get(sid, [])
        audios = audio_map.get(sid, [])
        shot.__dict__["characters"] = char_map.get(sid, [])
        shot.__dict__["props"] = prop_map.get(sid, [])
        shot.__dict__["frame_images"] = frames
        shot.__dict__["videos"] = videos
        shot.__dict__["audios"] = audios

        active_frame = None
        if shot.active_frame_image_id:
            active_frame = next((f for f in frames if f.id == shot.active_frame_image_id), None)
        if not active_frame and frames:
            active_frame = next((f for f in frames if f.is_active), None)
        shot.__dict__["active_frame_image"] = active_frame

        active_vid = None
        if shot.active_video_id:
            active_vid = next((v for v in videos if v.id == shot.active_video_id), None)
        if not active_vid and videos:
            active_vid = next((v for v in videos if v.is_active), None)
        shot.__dict__["active_video"] = active_vid

        # 采用音频（Phase 2）
        active_audio = None
        if shot.active_audio_id:
            active_audio = next((a for a in audios if a.id == shot.active_audio_id), None)
        if not active_audio and audios:
            active_audio = next((a for a in audios if a.is_active), None)
        shot.__dict__["active_audio"] = active_audio


# =====================================================
# 分镜 CRUD
# =====================================================

async def list_shots(
    db: AsyncSession, project_id: int, script_id: Optional[int] = None
) -> List[ProjectShot]:
    """
    列出项目所有分镜（按 sort_order）
    含关联的角色/场景/道具/帧图/视频（用于前端列表展示）
    可选按集过滤（script_id），并批量填充 episode_no 字段
    """
    stmt = select(ProjectShot).where(ProjectShot.project_id == project_id)
    if script_id is not None:
        stmt = stmt.where(ProjectShot.script_id == script_id)
    stmt = stmt.order_by(ProjectShot.sort_order)
    result = await db.execute(stmt)
    shots = result.scalars().all()
    await _attach_shot_relations_batch(db, shots)
    # 批量填充 episode_no（避免 N+1）
    await _fill_episode_no(db, project_id, shots)
    return shots


async def _fill_episode_no(db: AsyncSession, project_id: int, items: List) -> None:
    """批量给分镜列表填充 episode_no 字段（一次查询 ProjectScript 字典映射）"""
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


async def get_shot(db: AsyncSession, shot_id: int) -> Optional[ProjectShot]:
    """获取分镜详情（含关联实体/帧图/视频）"""
    result = await db.execute(
        select(ProjectShot).where(ProjectShot.id == shot_id)
    )
    shot = result.scalar_one_or_none()
    if not shot:
        return None
    await _attach_shot_relations(db, shot)
    return shot


async def create_shot(
    db: AsyncSession, project_id: int, data: ShotCreate
) -> ProjectShot:
    """添加分镜（自动计算 sequence_no 和 sort_order，按集 script_id 维度）"""
    # 校验 script_id 属于该项目
    script = await db.get(ProjectScript, data.script_id)
    if not script or script.project_id != project_id:
        raise HTTPException(404, "剧本不存在或不属于该项目")

    # 计算 sequence_no 和 sort_order 起点（按集）
    max_seq = (
        await db.execute(
            select(func.coalesce(func.max(ProjectShot.sequence_no), 0)).where(
                ProjectShot.script_id == data.script_id
            )
        )
    ).scalar() or 0
    max_order = (
        await db.execute(
            select(func.coalesce(func.max(ProjectShot.sort_order), 0)).where(
                ProjectShot.script_id == data.script_id
            )
        )
    ).scalar() or 0

    shot = ProjectShot(
        project_id=project_id,
        script_id=data.script_id,
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

    # 构建上下文（get_shot 已注入 characters 到 __dict__）
    chars = shot.__dict__.get("characters") or []
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
    db: AsyncSession, project_id: int, script_id: int
) -> dict:
    """
    从剧本重新 AI 拆分分镜（追加，不覆盖现有分镜）
    按集 script_id 精确取剧本，序号按集从 1 开始递增

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
        raise HTTPException(400, "剧本内容为空，无法拆分分镜")

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

    # 计算 sequence_no / sort_order 起点（按集）
    max_seq = (
        await db.execute(
            select(func.coalesce(func.max(ProjectShot.sequence_no), 0)).where(
                ProjectShot.script_id == script_id
            )
        )
    ).scalar() or 0
    max_order = (
        await db.execute(
            select(func.coalesce(func.max(ProjectShot.sort_order), 0)).where(
                ProjectShot.script_id == script_id
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
