# =====================================================
# 3D 场景（导演台）相关的 Pydantic Schema — SceneData v2
# 多机位（cameras[]）/ 镜头序列（shots[]）/ id 寻址，
# 对齐前端 types/scene.ts，用于接口参数校验与文档生成。
# =====================================================

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

ShotSizeType = Literal[
    "extreme_wide", "wide", "medium", "medium_close", "close_up", "extreme_close_up"
]
CameraMoveType = Literal[
    "static", "push_in", "pull_out", "pan", "tilt", "orbit", "tracking", "crane", "handheld"
]
KeyframeEasingType = Literal["linear", "smooth", "cut"]


class CamelModel(BaseModel):
    """多词字段接受 camelCase（前端形态），dump 用 by_alias 保持存储形态一致"""
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class Vec3(BaseModel):
    """三维坐标"""
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0


class SubjectPose(BaseModel):
    """主体姿势（预设起步，关节级编辑后置）"""
    preset: str = Field(default="stand", description="姿势预设 id")


class SubjectData(CamelModel):
    """主体（角色/物体）占位"""
    id: str = Field(..., min_length=1, description="主体 id（uuid）")
    label: str = Field(default="主体", description="主体标签，如 '角色A'")
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    rotation: Vec3 = Field(default_factory=Vec3, description="主体旋转（欧拉角，度）")
    pose: SubjectPose | None = Field(default=None, description="姿势预设")
    visible: bool = Field(default=True, description="是否可见")
    locked: bool = Field(default=False, description="是否锁定（锁定不可选中/删除）")


class CameraDevice(CamelModel):
    """机位（v2 多机位；active 机位=视口当前编辑对象）"""
    id: str = Field(..., min_length=1, description="机位 id（uuid）")
    name: str = Field(default="A 机位", description="机位名称")
    position: Vec3 = Field(default_factory=lambda: Vec3(x=0, y=1.6, z=5))
    target: Vec3 = Field(default_factory=Vec3, description="注视点")
    fov: float = Field(default=50, ge=10, le=120, description="视场角（度）")
    active: bool = Field(default=False, description="是否激活机位")
    follow_subject_id: str | None = Field(default=None, description="镜头跟随主体 id")
    locked: bool = Field(default=False, description="是否锁定")


class LightData(BaseModel):
    """灯光参数（方向光带 direction 控制照射方向）"""
    id: str = Field(..., min_length=1, description="灯光 id（uuid）")
    type: str = Field(default="directional", description="灯光类型：directional/ambient")
    x: float = 5.0
    y: float = 8.0
    z: float = 5.0
    intensity: float = Field(default=1.0, ge=0, le=5)
    direction: Vec3 = Field(
        default_factory=lambda: Vec3(x=0, y=-1, z=0),
        description="灯光照射方向（归一化向量），directional 类型有效",
    )
    visible: bool = Field(default=True, description="是否可见")
    locked: bool = Field(default=False, description="是否锁定")


class PropData(BaseModel):
    """道具占位（布景元素）"""
    id: str = Field(..., min_length=1, description="道具 id（uuid）")
    type: str = Field(default="box", description="道具几何类型：box/plane/sphere/cylinder")
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    label: str = Field(default="道具", description="道具标签，如 '桌子'、'树'")
    rotation: Vec3 = Field(default_factory=Vec3, description="道具旋转（欧拉角，度）")
    scale: float = Field(default=1.0, ge=0.05, le=20, description="缩放")
    visible: bool = Field(default=True, description="是否可见")
    locked: bool = Field(default=False, description="是否锁定")


class EnvironmentData(BaseModel):
    """环境布景描述"""
    type: str = Field(default="studio", description="环境类型：studio/indoor/outdoor/night/custom")
    label: str = Field(default="工作室", description="环境显示名")


class StageData(CamelModel):
    """舞台级设置"""
    environment: EnvironmentData = Field(default_factory=EnvironmentData)
    aspect_ratio: str = Field(default="", description="画幅取景框（'16:9' 等，空=无）")


class CameraKeyframe(CamelModel):
    """相机关键帧（easing 描述从上一帧到本帧的过渡）"""
    time: float = Field(default=0, ge=0, description="相对 shot 起始的秒数")
    position: Vec3 = Field(default_factory=lambda: Vec3(x=0, y=1.6, z=5))
    target: Vec3 = Field(default_factory=Vec3)
    fov: float = Field(default=50, ge=10, le=120)
    easing: KeyframeEasingType = Field(default="smooth")


class ShotData(CamelModel):
    """镜头（Shot）：机位 + 时长 + 景别/运镜 + 关键帧"""
    id: str = Field(..., min_length=1, description="镜头 id（uuid）")
    camera_id: str = Field(..., min_length=1, description="使用的机位 id")
    duration: float = Field(default=4, ge=0.5, le=60, description="时长（秒）")
    fps: Literal[24, 25, 30] = Field(default=24)
    shot_size: ShotSizeType = Field(default="medium", description="景别（6 档）")
    camera_move: CameraMoveType = Field(default="static", description="运镜（9 种）")
    keyframes: list[CameraKeyframe] = Field(default_factory=list, description="相机关键帧（≥1）")
    prompt: str = Field(default="", description="镜头附加描述")
    cover_url: str | None = Field(default=None, description="预演截图封面")
    derived_task_ids: list[str] = Field(default_factory=list, description="批量派生任务留痕")


class SceneData(CamelModel):
    """3D 场景布局数据 v2（多机位 / 镜头序列）"""
    stage: StageData = Field(default_factory=StageData)
    subjects: list[SubjectData] = Field(default_factory=list)
    cameras: list[CameraDevice] = Field(default_factory=list)
    lights: list[LightData] = Field(default_factory=list)
    props: list[PropData] = Field(default_factory=list)
    shots: list[ShotData] = Field(default_factory=list)
    active_shot_id: str | None = Field(default=None)


# ---------- 请求模型 ----------

class SceneCreate(BaseModel):
    """创建 3D 场景请求"""
    name: str = Field(..., min_length=1, max_length=200, description="场景名称")
    description: str | None = Field(None, description="场景描述")
    scene_data: SceneData = Field(default_factory=SceneData, description="3D 布局数据（v2 严格校验）")
    is_public: bool = Field(default=False, description="是否公开")


class SceneUpdate(BaseModel):
    """更新 3D 场景请求（所有字段可选）"""
    name: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = None
    scene_data: SceneData | None = None
    is_public: bool | None = None
    cover_url: str | None = Field(None, max_length=500, description="视口截图封面 URL")


class ScenePromptPreviewRequest(BaseModel):
    """场景 → prompt 预览请求（shot 可选：按该镜头机位编译并追加景别/运镜）"""
    scene_data: SceneData
    shot: ShotData | None = None


# ---------- 响应模型 ----------

class SceneResponse(BaseModel):
    """3D 场景响应"""
    id: int
    user_id: int | None = None
    name: str
    description: str | None = None
    scene_data: dict
    is_public: bool
    cover_url: str | None = None
    created_at: str | None = None
    updated_at: str | None = None

    class Config:
        from_attributes = True

    @classmethod
    def from_model(cls, m) -> "SceneResponse":
        return cls(
            id=m.id,
            user_id=m.user_id,
            name=m.name,
            description=m.description,
            scene_data=m.scene_data or {},
            is_public=m.is_public,
            cover_url=getattr(m, "cover_url", None),
            created_at=m.created_at.isoformat() if m.created_at else None,
            updated_at=m.updated_at.isoformat() if m.updated_at else None,
        )


class SceneListResponse(BaseModel):
    """场景列表响应"""
    items: list[SceneResponse]
    total: int


class ScenePromptPreviewResponse(BaseModel):
    """场景 → prompt 预览响应"""
    prompt_suffix: str = Field(..., description="翻译后的镜头语言描述，追加到原 prompt 末尾")
    details: dict = Field(..., description="各维度翻译明细（调试用）")
