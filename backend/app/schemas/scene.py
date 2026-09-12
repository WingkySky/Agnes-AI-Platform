# =====================================================
# 3D 场景（导演台）相关的 Pydantic Schema
# 对齐 Scene3D 模型，用于接口参数校验与文档生成。
# =====================================================

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


class Vec3(BaseModel):
    """三维坐标"""
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0


class SubjectData(BaseModel):
    """主体（角色/物体）占位"""
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    label: str = Field(default="主体", description="主体标签，如 '角色A'")


class CameraData(BaseModel):
    """相机参数"""
    position: Vec3 = Field(default_factory=lambda: Vec3(x=0, y=1.6, z=5))
    lookAt: Vec3 = Field(default_factory=lambda: Vec3(x=0, y=0, z=0))
    fov: float = Field(default=50, ge=10, le=120, description="视场角（度），决定焦段感")


class LightData(BaseModel):
    """灯光参数（支持方向光/环境光，方向光带 direction 控制照射方向）"""
    type: str = Field(default="directional", description="灯光类型：directional/ambient")
    x: float = 5.0
    y: float = 8.0
    z: float = 5.0
    intensity: float = Field(default=1.0, ge=0, le=5)
    direction: Vec3 = Field(
        default_factory=lambda: Vec3(x=0, y=-1, z=0),
        description="灯光照射方向（归一化向量），directional 类型有效",
    )


class PropData(BaseModel):
    """道具占位（布景元素：立方体/平面/球体等，用于提示生成画面中的道具）"""
    type: str = Field(default="box", description="道具几何类型：box/plane/sphere/cylinder")
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    label: str = Field(default="道具", description="道具标签，如 '桌子'、'树'")
    rotation: Vec3 = Field(
        default_factory=lambda: Vec3(x=0, y=0, z=0),
        description="道具旋转（欧拉角，度）",
    )


class EnvironmentData(BaseModel):
    """环境布景描述（室内/室外/特定场景类型）"""
    type: str = Field(default="studio", description="环境类型：studio/indoor/outdoor/night/custom")
    label: str = Field(default="工作室", description="环境显示名，如 '室内'、'夜景街头'")


class SceneData(BaseModel):
    """3D 场景布局数据（支持多主体/多灯光/道具布景）"""
    subjects: List[SubjectData] = Field(default_factory=list, description="主体列表")
    camera: CameraData = Field(default_factory=CameraData)
    lights: List[LightData] = Field(default_factory=list, description="灯光列表")
    props: List[PropData] = Field(default_factory=list, description="道具占位列表")
    environment: EnvironmentData = Field(default_factory=EnvironmentData, description="环境布景")


# ---------- 请求模型 ----------

class SceneCreate(BaseModel):
    """创建 3D 场景请求"""
    name: str = Field(..., min_length=1, max_length=200, description="场景名称")
    description: Optional[str] = Field(None, description="场景描述")
    scene_data: dict = Field(default_factory=dict, description="3D 布局数据")
    is_public: bool = Field(default=False, description="是否公开")


class SceneUpdate(BaseModel):
    """更新 3D 场景请求（所有字段可选）"""
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    scene_data: Optional[dict] = None
    is_public: Optional[bool] = None


class ScenePromptPreviewRequest(BaseModel):
    """场景 → prompt 预览请求"""
    scene_data: dict = Field(..., description="3D 布局数据")


# ---------- 响应模型 ----------

class SceneResponse(BaseModel):
    """3D 场景响应"""
    id: int
    user_id: Optional[int] = None
    name: str
    description: Optional[str] = None
    scene_data: dict
    is_public: bool
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

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
            created_at=m.created_at.isoformat() if m.created_at else None,
            updated_at=m.updated_at.isoformat() if m.updated_at else None,
        )


class SceneListResponse(BaseModel):
    """场景列表响应"""
    items: List[SceneResponse]
    total: int


class ScenePromptPreviewResponse(BaseModel):
    """场景 → prompt 预览响应"""
    prompt_suffix: str = Field(..., description="翻译后的镜头语言描述，追加到原 prompt 末尾")
    details: dict = Field(..., description="各维度翻译明细（调试用）")
