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
# 支持多主体关系、多灯光叠加、道具布景描述。
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


def _composition_desc(cam_x: float, primary_sub_x: float) -> str:
    """相机 x 与主主体 x 偏移 → 侧拍角度 + 构图位置"""
    parts = []
    dx = cam_x - primary_sub_x
    if abs(dx) < 0.5:
        parts.append("正面构图")
    elif abs(dx) < 2.0:
        parts.append("三分位侧拍")
    else:
        parts.append("侧面构图")

    if primary_sub_x < -1.0:
        parts.append("主体位于画面左侧")
    elif primary_sub_x > 1.0:
        parts.append("主体位于画面右侧")
    else:
        parts.append("主体居中")
    return "，".join(parts)


def _subject_orientation_desc(rotation: dict) -> str:
    """
    主体朝向描述（基于 rotation.y 绕 y 轴旋转角度）。
    假设相机在 +z 方向看向主体：
      - 0° 附近 = 正面（面向相机）
      - 90° 附近 = 侧面
      - 180° 附近 = 背影（背向相机）
    """
    if not rotation:
        return ""
    ry = float(rotation.get("y", 0)) % 360
    # 归一化到 [0, 360)
    if ry < 0:
        ry += 360
    # 判断朝向区间
    if ry < 30 or ry > 330:
        return "正面朝向"
    if 60 <= ry <= 120:
        return "侧面朝向"
    if 150 <= ry <= 210:
        return "背影朝向"
    if 240 <= ry <= 300:
        return "侧面朝向"
    # 过渡区间（30-60, 120-150, 210-240, 300-330）
    return "半侧身朝向"


def _camera_facing_desc(cam_pos: dict, cam_look: dict, primary_sub: dict) -> str:
    """
    相机朝向描述（基于 position→lookAt 与 position→主体 的水平夹角）。
    反映相机旋转后是否仍对准主体：
      - < 30°：正面拍摄主体
      - 30-70°：侧拍主体
      - 70-110°：镜头扫过主体边缘
      - > 110°：背向主体拍摄（镜头看向别处）
    """
    if not cam_pos or not cam_look:
        return ""
    # 相机拍摄方向（水平面 xz）
    shoot_x = float(cam_look.get("x", 0)) - float(cam_pos.get("x", 0))
    shoot_z = float(cam_look.get("z", 0)) - float(cam_pos.get("z", 0))
    # 相机到主体方向（水平面 xz）
    to_sub_x = float(primary_sub.get("x", 0)) - float(cam_pos.get("x", 0))
    to_sub_z = float(primary_sub.get("z", 0)) - float(cam_pos.get("z", 0))
    shoot_len = math.sqrt(shoot_x * shoot_x + shoot_z * shoot_z)
    to_sub_len = math.sqrt(to_sub_x * to_sub_x + to_sub_z * to_sub_z)
    if shoot_len < 0.01 or to_sub_len < 0.01:
        return ""
    # 余弦夹角
    cos_a = (shoot_x * to_sub_x + shoot_z * to_sub_z) / (shoot_len * to_sub_len)
    cos_a = max(-1.0, min(1.0, cos_a))
    angle = math.degrees(math.acos(cos_a))
    if angle < 30:
        return "镜头正对主体"
    if angle < 70:
        return "侧拍主体"
    if angle < 110:
        return "镜头扫过主体边缘"
    return "镜头背向主体"


def _prop_orientation_desc(rotation: dict) -> str:
    """
    道具朝向描述（基于 rotation.y 绕 y 轴旋转角度）。
    """
    if not rotation:
        return ""
    ry = float(rotation.get("y", 0)) % 360
    if ry < 0:
        ry += 360
    if ry < 30 or ry > 330:
        return "正向放置"
    if 60 <= ry <= 120 or 240 <= ry <= 300:
        return "侧向放置"
    if 150 <= ry <= 210:
        return "反向放置"
    return "斜向放置"


def _subjects_desc(subjects: list) -> str:
    """
    多主体 → 数量 + 主体间空间关系描述 + 各主体 label。
    - 1 个：单人
    - 2 个：双人，描述相对位置（左右并排/前后/对峙）
    - 3+ 个：群像构图
    label 会被追加为辅助描述（如"角色A"、"角色B"）。
    """
    if not subjects:
        return ""

    n = len(subjects)
    # 收集非默认 label（过滤掉"主体"默认值）
    labels = [s.get("label", "") for s in subjects if s.get("label") and s.get("label") != "主体"]

    if n == 1:
        base = "单人构图"
    elif n == 2:
        s1, s2 = subjects[0], subjects[1]
        dx = float(s2.get("x", 0)) - float(s1.get("x", 0))
        dz = float(s2.get("z", 0)) - float(s1.get("z", 0))
        # 判断主要关系方向
        if abs(dx) > abs(dz):
            # 左右关系为主
            if abs(dx) < 1.5:
                relation = "双人靠近站立"
            else:
                relation = "双人左右并排"
        elif abs(dz) > abs(dx):
            # 前后关系为主
            if abs(dz) < 1.5:
                relation = "双人靠近站立"
            else:
                relation = "双人前后站位"
        else:
            # dx、dz 接近，判断是否对峙
            if abs(dx) < 1.5 and abs(dz) < 1.5:
                relation = "双人近距离对峙"
            else:
                relation = "双人斜向站位"
        base = relation
    else:
        # 3+ 主体：群像
        if n == 3:
            base = "三人群像构图"
        else:
            base = f"{n}人群像构图"

    # 追加 label 辅助描述
    if labels:
        return f"{base}（{'、'.join(labels)}）"
    return base


def _multi_light_desc(lights: list) -> str:
    """
    多灯光 → 光位组合描述。
    按强度排序：最强=主光，次=辅光，其余=轮廓光/背景光。
    """
    if not lights:
        return ""

    # 只处理方向光
    dir_lights = [l for l in lights if l.get("type", "directional") == "directional"]
    if not dir_lights:
        return ""

    # 按强度降序
    sorted_lights = sorted(
        dir_lights,
        key=lambda l: float(l.get("intensity", 1.0)),
        reverse=True,
    )

    def _single_light_pos(light: dict) -> str:
        """单灯光位描述：优先基于 direction 方向向量判断，回退到位置判断"""
        # 优先使用 direction 方向向量（更准确反映用户旋转后的朝向）
        direction = light.get("direction") or {}
        dx = float(direction.get("x", 0))
        dy = float(direction.get("y", -1))
        dz = float(direction.get("z", 0))

        # 归一化（避免用户输入未归一化）
        length = math.sqrt(dx * dx + dy * dy + dz * dz)
        if length > 0:
            dx, dy, dz = dx / length, dy / length, dz / length

        # 基于 direction 判光位（direction 是灯光照射方向）
        # dy < -0.5 表示主要向下照 = 顶光/高位光
        # dy > 0.5 表示主要向上照 = 底光/低位光
        # dz < -0.5 表示向 -z 照（如果相机在 +z，则是顺光；反之逆光）—— 这里用绝对值判断前后
        if dy < -0.5:
            pos = "顶光"
        elif dy > 0.5:
            pos = "低位光"
        elif dz < -0.5:
            pos = "逆光"
        elif abs(dx) > abs(dz) and abs(dx) > 0.4:
            pos = "侧光"
        else:
            pos = "顺光"
        return pos

    def _strength_desc(intensity: float) -> str:
        if intensity > 1.5:
            return "强光"
        if intensity < 0.6:
            return "柔光"
        return "常光"

    if len(sorted_lights) == 1:
        light = sorted_lights[0]
        return f"{_single_light_pos(light)}，{_strength_desc(float(light.get('intensity', 1.0)))}"

    # 多光组合
    parts = []
    roles = ["主光", "辅光", "轮廓光", "背景光"]
    for i, light in enumerate(sorted_lights[:4]):
        role = roles[i] if i < len(roles) else "补光"
        pos = _single_light_pos(light)
        strength = _strength_desc(float(light.get("intensity", 1.0)))
        parts.append(f"{role}（{pos}，{strength}）")

    return "，".join(parts)


def _props_desc(props: list) -> str:
    """
    道具占位 → 道具 label 列表 + 朝向描述。
    朝向取第一个道具的 rotation.y（多数场景下道具朝向一致）。
    """
    if not props:
        return ""
    labels = [p.get("label", "道具") for p in props if p.get("label")]
    # 去重并保留顺序
    seen = set()
    unique_labels = []
    for lb in labels:
        if lb not in seen:
            seen.add(lb)
            unique_labels.append(lb)
    parts = []
    if unique_labels:
        if len(unique_labels) == 1:
            parts.append(f"画面包含{unique_labels[0]}")
        else:
            parts.append(f"画面包含{('、'.join(unique_labels))}")
    # 追加道具朝向描述
    orientation = _prop_orientation_desc(props[0].get("rotation") or {})
    if orientation:
        parts.append(orientation)
    return "，".join(parts)


# 环境类型 → 镜头语言关键词映射
_ENV_KEYWORDS = {
    "studio": "工作室布光",
    "indoor": "室内场景",
    "outdoor": "室外场景",
    "night": "夜景",
    "custom": "",  # custom 由 label 决定
}


def _environment_desc(env: dict) -> str:
    """环境布景 → 环境关键词描述"""
    if not env:
        return ""
    env_type = env.get("type", "studio")
    label = env.get("label", "")
    if env_type == "custom" and label:
        return label
    keyword = _ENV_KEYWORDS.get(env_type, "")
    if keyword and label and label != keyword:
        return f"{label}（{keyword}）"
    return keyword or label or ""


def scene_to_prompt_suffix(scene_data: dict) -> Tuple[str, dict]:
    """
    把 3D 场景数据翻译为镜头语言描述字符串。
    支持多主体关系、多灯光叠加、道具布景、环境描述。

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

    subjects = scene_data.get("subjects", []) or []
    lights = scene_data.get("lights", []) or []
    props = scene_data.get("props", []) or []
    environment = scene_data.get("environment", {}) or {}

    # 以第一个主体作为相机距离/构图参考（若无主体则用原点）
    primary = subjects[0] if subjects else {"x": 0, "z": 0}
    sub_x = float(primary.get("x", 0))
    sub_z = float(primary.get("z", 0))

    # 计算各维度
    distance = _distance({"x": cam_x, "z": cam_z}, {"x": sub_x, "z": sub_z})
    angle = _camera_angle_desc(cam_y)
    focal = _focal_desc(distance, fov)
    fov_desc = _fov_desc(fov)
    composition = _composition_desc(cam_x, sub_x)
    # 相机朝向（基于 position→lookAt 与 position→主体 的夹角，反映旋转后是否对准主体）
    camera_facing = _camera_facing_desc(cam_pos, cam_look, primary)
    subjects_desc = _subjects_desc(subjects)
    # 主体朝向（取第一个主体的旋转）
    primary_rotation = (subjects[0].get("rotation") if subjects else {}) or {}
    orientation = _subject_orientation_desc(primary_rotation)
    light = _multi_light_desc(lights)
    props_d = _props_desc(props)
    env_d = _environment_desc(environment)

    details = {
        "distance": round(distance, 2),
        "angle": angle,
        "focal": focal,
        "fov_desc": fov_desc,
        "composition": composition,
        "camera_facing": camera_facing,
        "subjects": subjects_desc,
        "orientation": orientation,
        "light": light,
        "props": props_d,
        "environment": env_d,
    }

    # 组装：视角/焦段/视野/构图/相机朝向 + 主体关系 + 主体朝向 + 灯光 + 道具 + 环境
    parts = [angle, focal, fov_desc, composition]
    if camera_facing:
        parts.append(camera_facing)
    if subjects_desc:
        parts.append(subjects_desc)
    if orientation:
        parts.append(orientation)
    if light:
        parts.append(light)
    if props_d:
        parts.append(props_d)
    if env_d:
        parts.append(env_d)

    suffix = "。" + "，".join(p for p in parts if p) + "。"
    return suffix, details
