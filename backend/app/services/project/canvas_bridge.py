# =====================================================
# 画布桥接 — 画布数据初始化 / 查询 / 保存（J4 双视图）
#
# 画布视图与列表视图共享同一份项目数据，
# canvas_data 字段仅保存布局信息（节点位置/连线/视口），
# 节点内容通过 API 实时拉取。
#
# 节点类型:
#   - script:    剧本节点
#   - character: 角色节点
#   - scene:     场景节点
#   - prop:      道具节点
#   - shot:      分镜节点
# =====================================================

import logging
from typing import Any, Dict, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import (
    Project,
    ProjectScript,
    ProjectCharacter,
    ProjectScene,
    ProjectProp,
    ProjectShot,
)

logger = logging.getLogger("agnes_platform.project.canvas")


# =====================================================
# 画布初始化（按生成依赖自动布局）
# =====================================================

async def init_canvas_layout(
    db: AsyncSession, project_id: int
) -> Dict[str, Any]:
    """
    初始化画布布局（按生成依赖自动排列节点）

    布局规则:
    - 剧本节点放最左
    - 角色/场景/道具节点放中部（垂直分布）
    - 分镜节点放右侧（垂直分布）
    """
    project = (
        await db.execute(select(Project).where(Project.id == project_id))
    ).scalar_one_or_none()
    if not project:
        return {}

    # 收集所有实体
    scripts = (
        await db.execute(
            select(ProjectScript)
            .where(ProjectScript.project_id == project_id)
            .order_by(ProjectScript.episode_no)
        )
    ).scalars().all()
    characters = (
        await db.execute(
            select(ProjectCharacter)
            .where(ProjectCharacter.project_id == project_id)
            .order_by(ProjectCharacter.sort_order)
        )
    ).scalars().all()
    scenes = (
        await db.execute(
            select(ProjectScene)
            .where(ProjectScene.project_id == project_id)
            .order_by(ProjectScene.sort_order)
        )
    ).scalars().all()
    props = (
        await db.execute(
            select(ProjectProp)
            .where(ProjectProp.project_id == project_id)
            .order_by(ProjectProp.sort_order)
        )
    ).scalars().all()
    shots = (
        await db.execute(
            select(ProjectShot)
            .where(ProjectShot.project_id == project_id)
            .order_by(ProjectShot.sort_order)
        )
    ).scalars().all()

    nodes = []
    edges = []

    # 剧本节点（最左）
    for idx, s in enumerate(scripts):
        nodes.append({
            "id": f"script-{s.id}",
            "type": "script",
            "ref_id": s.id,
            "position": {"x": 50, "y": 50 + idx * 120},
            "data": {"title": s.title or f"第{s.episode_no}集"},
        })

    # 角色/场景/道具节点（中部）
    entity_x = 400
    char_y = 50
    for c in characters:
        nodes.append({
            "id": f"character-{c.id}",
            "type": "character",
            "ref_id": c.id,
            "position": {"x": entity_x, "y": char_y},
            "data": {"name": c.name, "active_image_id": c.active_image_id},
        })
        char_y += 100

    scene_y = 50
    for s in scenes:
        nodes.append({
            "id": f"scene-{s.id}",
            "type": "scene",
            "ref_id": s.id,
            "position": {"x": entity_x + 200, "y": scene_y},
            "data": {"name": s.name, "active_image_id": s.active_image_id},
        })
        scene_y += 100

    prop_y = 50
    for p in props:
        nodes.append({
            "id": f"prop-{p.id}",
            "type": "prop",
            "ref_id": p.id,
            "position": {"x": entity_x + 400, "y": prop_y},
            "data": {"name": p.name, "active_image_id": p.active_image_id},
        })
        prop_y += 100

    # 分镜节点（右侧）
    shot_x = 1000
    for idx, sh in enumerate(shots):
        nodes.append({
            "id": f"shot-{sh.id}",
            "type": "shot",
            "ref_id": sh.id,
            "position": {"x": shot_x, "y": 50 + idx * 120},
            "data": {
                "title": sh.title or f"分镜 {sh.sequence_no}",
                "active_frame_image_id": sh.active_frame_image_id,
                "active_video_id": sh.active_video_id,
            },
        })

    # 自动连线（剧本 → 实体 → 分镜）
    for s in scripts:
        for c in characters:
            edges.append({
                "id": f"e-script-{s.id}-character-{c.id}",
                "source": f"script-{s.id}",
                "target": f"character-{c.id}",
                "animated": False,
            })

    canvas_data = {
        "nodes": nodes,
        "edges": edges,
        "viewport": {"x": 0, "y": 0, "zoom": 0.7},
    }

    # 持久化到 project.canvas_data
    project.canvas_data = canvas_data
    await db.commit()

    return canvas_data


# =====================================================
# 画布数据查询 / 保存
# =====================================================

async def get_canvas_data(
    db: AsyncSession, project_id: int
) -> Dict[str, Any]:
    """获取画布数据（无则自动初始化）"""
    project = (
        await db.execute(select(Project).where(Project.id == project_id))
    ).scalar_one_or_none()
    if not project:
        return {}
    if not project.canvas_data:
        # 自动初始化
        return await init_canvas_layout(db, project_id)
    return project.canvas_data


async def save_canvas_data(
    db: AsyncSession, project_id: int, canvas_data: Dict[str, Any]
) -> Optional[Project]:
    """保存画布布局"""
    project = (
        await db.execute(select(Project).where(Project.id == project_id))
    ).scalar_one_or_none()
    if not project:
        return None
    project.canvas_data = canvas_data
    await db.commit()
    await db.refresh(project)
    return project
