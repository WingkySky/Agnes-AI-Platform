# =====================================================
# 3D 场景（导演台）服务
# - CRUD 业务逻辑
# - scene_to_prompt：把 3D 空间布局翻译成镜头语言描述
#   （视角 / 焦段 / 构图位置 / 侧拍角度 / 光位 / 视野）
# 翻译结果追加到 prompt 末尾，复用现有图片/视频生成流程，
# 让构图、机位、视角变得可控。
# =====================================================

import math
from typing import Optional, Tuple

from sqlalchemy import and_, or_, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models.scene3d import Scene3D


# =====================================================
# CRUD
# =====================================================

async def create_scene(
    db: AsyncSession,
    user_id: int,
    name: str,
    description: Optional[str] = None,
    scene_data: Optional[dict] = None,
    is_public: bool = False,
) -> Scene3D:
    """创建 3D 场景"""
    scene = Scene3D(
        user_id=user_id,
        name=name,
        description=description,
        scene_data=scene_data or {},
        is_public=is_public,
    )
    db.add(scene)
    await db.commit()
    await db.refresh(scene)
    return scene


async def get_scene(db: AsyncSession, scene_id: int) -> Optional[Scene3D]:
    """按 ID 获取场景"""
    result = await db.execute(select(Scene3D).filter(Scene3D.id == scene_id))
    return result.scalar_one_or_none()


async def list_scenes(
    db: AsyncSession,
    user_id: Optional[int] = None,
    limit: int = 100,
    offset: int = 0,
    search: Optional[str] = None,
    is_public: Optional[bool] = None,
) -> Tuple[list, int]:
    """
    列出 3D 场景。
    - 指定 user_id：返回该用户的场景 + 公开场景
    - 未指定 user_id：仅返回公开场景
    """
    conditions = []
    if user_id is not None:
        conditions.append(
            or_(
                Scene3D.user_id == user_id,
                Scene3D.is_public == True,
            )
        )
    else:
        conditions.append(Scene3D.is_public == True)

    if is_public is not None:
        conditions.append(Scene3D.is_public == is_public)

    if search:
        pattern = f"%{search}%"
        conditions.append(
            or_(
                Scene3D.name.like(pattern),
                Scene3D.description.like(pattern),
            )
        )

    where = and_(*conditions) if conditions else None

    count_q = select(func.count(Scene3D.id))
    if where is not None:
        count_q = count_q.filter(where)
    total = (await db.execute(count_q)).scalar() or 0

    list_q = select(Scene3D).order_by(Scene3D.updated_at.desc())
    if where is not None:
        list_q = list_q.filter(where)
    result = await db.execute(list_q.offset(offset).limit(limit))
    return list(result.scalars().all()), total


async def update_scene(db: AsyncSession, scene_id: int, **kwargs) -> Optional[Scene3D]:
    """更新场景（仅更新传入的非 None 字段）"""
    scene = await get_scene(db, scene_id)
    if not scene:
        return None
    for key, value in kwargs.items():
        if value is not None and hasattr(scene, key):
            setattr(scene, key, value)
    await db.commit()
    await db.refresh(scene)
    return scene


async def delete_scene(db: AsyncSession, scene_id: int) -> bool:
    """删除场景"""
    scene = await get_scene(db, scene_id)
    if not scene:
        return False
    await db.delete(scene)
    await db.commit()
    return True


# =====================================================
# scene_to_prompt 翻译层
# 把 3D 空间数据翻译成中文镜头语言描述，
# 返回追加到原 prompt 末尾的字符串。
# =====================================================

def _distance(p1: dict, p2: dict) -> float:
    """计算两点欧氏距离（仅 xz 平面，忽略 y）"""
    dx = p1.get("x", 0) - p2.get("x", 0)
    dz = p1.get("z", 0) - p2.get("z", 0)
    return math.sqrt(dx * dx + dz * dz)


def _camera_angle_desc(cam_y: float) -> str:
    """相机高度 → 视角描述"""
    if cam_y > 3.0:
        return "俯视视角"
    if cam_y < 0.3:
        return "仰视视角"
    return "平视视角"


def _focal_desc(distance: float, fov: float) -> str:
    """相机距离 + FOV → 焦段描述"""
    if distance < 1.5:
        return "近景特写，85mm 长焦"
    if distance < 3.0:
        return "中景，50mm 标准镜头"
    if distance < 6.0:
        return "中全景，35mm 镜头"
    if distance < 10.0:
        return "全景，24mm 广角镜头"
    return "远景，16mm 超广角"


def _fov_desc(fov: float) -> str:
    """FOV → 视野描述"""
    if fov < 35:
        return "长焦压缩感"
    if fov > 65:
        return "广角开阔感"
    return "标准视野"


def _composition_desc(cam_x: float, subject_x: float) -> str:
    """相机 x 与主体 x 偏移 → 侧拍角度 + 构图位置"""
    parts = []
    dx = cam_x - subject_x
    if abs(dx) < 0.5:
        parts.append("正面构图")
    elif abs(dx) < 2.0:
        parts.append("三分位侧拍")
    else:
        parts.append("侧面构图")

    if subject_x < -1.0:
        parts.append("主体位于画面左侧")
    elif subject_x > 1.0:
        parts.append("主体位于画面右侧")
    else:
        parts.append("主体居中")
    return "，".join(parts)


def _light_desc(lights: list) -> str:
    """灯光 → 光位描述（MVP 仅取第一个方向光）"""
    if not lights:
        return ""
    light = lights[0]
    lx, ly, lz = light.get("x", 5), light.get("y", 8), light.get("z", 5)
    intensity = light.get("intensity", 1.0)

    # 判断光位：基于 y 高度与 x/z 方向
    if ly < 1.0:
        position = "低位光"
    elif ly > 6.0:
        position = "顶光"
    elif lz < 0:
        position = "逆光"
    elif abs(lx) > abs(lz):
        position = "侧光"
    else:
        position = "顺光"

    strength = "强光" if intensity > 1.5 else "柔和光" if intensity < 0.6 else "常光"
    return f"{position}，{strength}"


def scene_to_prompt_suffix(scene_data: dict) -> Tuple[str, dict]:
    """
    把 3D 场景数据翻译为镜头语言描述字符串。

    返回:
        (suffix, details)
        - suffix: 追加到原 prompt 末尾的中文描述（以句号开头和结尾）
        - details: 各维度翻译明细，便于前端展示与调试
    """
    if not scene_data or not isinstance(scene_data, dict):
        return "", {}

    cam = scene_data.get("camera", {}) or {}
    cam_pos = cam.get("position", {}) or {}
    cam_look = cam.get("lookAt", {}) or {}
    fov = float(cam.get("fov", 50))
    cam_x = float(cam_pos.get("x", 0))
    cam_y = float(cam_pos.get("y", 1.6))
    cam_z = float(cam_pos.get("z", 5))

    subject = scene_data.get("subject", {}) or {}
    sub_x = float(subject.get("x", 0))
    sub_y = float(subject.get("y", 0))
    sub_z = float(subject.get("z", 0))

    lights = scene_data.get("lights", []) or []

    # 计算各维度
    distance = _distance({"x": cam_x, "z": cam_z}, {"x": sub_x, "z": sub_z})
    angle = _camera_angle_desc(cam_y)
    focal = _focal_desc(distance, fov)
    fov_desc = _fov_desc(fov)
    composition = _composition_desc(cam_x, sub_x)
    light = _light_desc(lights)

    details = {
        "distance": round(distance, 2),
        "angle": angle,
        "focal": focal,
        "fov_desc": fov_desc,
        "composition": composition,
        "light": light,
    }

    parts = [angle, focal, fov_desc, composition]
    if light:
        parts.append(light)

    suffix = "。" + "，".join(p for p in parts if p) + "。"
    return suffix, details
