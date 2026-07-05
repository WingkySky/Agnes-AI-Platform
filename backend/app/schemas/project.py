# =====================================================
# 项目制创作相关的 Pydantic Schema
# 覆盖项目 CRUD、剧本、角色/场景/道具、分镜、帧图、视频、版本管理、向导等
# =====================================================

from typing import List, Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict


# =====================================================
# 项目 CRUD Schema
# =====================================================

class ProjectCreate(BaseModel):
    """创建项目请求（空白创建）"""
    title: str = Field(..., min_length=1, max_length=200, description="项目标题")
    description: Optional[str] = Field(None, description="项目描述")
    aspect_ratio: Optional[str] = Field("16:9", description="宽高比")
    resolution: Optional[str] = Field("1280x720", description="分辨率")
    wizard_inputs: Optional[Dict[str, Any]] = Field(default_factory=dict, description="向导参数")


class ProjectUpdate(BaseModel):
    """更新项目请求"""
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    cover_url: Optional[str] = None
    aspect_ratio: Optional[str] = None
    resolution: Optional[str] = None
    status: Optional[str] = None


class ProjectResponse(BaseModel):
    """项目响应"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: Optional[str] = None
    user_id: int
    status: str
    cover_url: Optional[str] = None
    aspect_ratio: str
    resolution: str
    wizard_inputs: Dict[str, Any] = Field(default_factory=dict)
    active_view: str
    canvas_data: Dict[str, Any] = Field(default_factory=dict)
    timeline_data: Dict[str, Any] = Field(default_factory=dict)
    final_video_url: Optional[str] = None
    total_duration: float = 0
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ProjectListResponse(BaseModel):
    """项目列表响应"""
    items: List[ProjectResponse]
    total: int
    page: int
    page_size: int


class ActiveViewUpdate(BaseModel):
    """切换活动视图"""
    view: str = Field(..., description="视图类型：manager/canvas")


# =====================================================
# 向导 Schema
# =====================================================

class WizardCreateRequest(BaseModel):
    """通过模板向导创建项目

    使用 category 模式：从 wizard_chains.WIZARD_CHAINS 预设链路查找（drama/ad/education/anime）
    """
    category: Optional[str] = Field(None, description="场景分类（drama/ad/education/anime）")
    title: str = Field(..., min_length=1, max_length=200, description="项目标题")
    description: Optional[str] = Field(None, description="项目描述")
    inputs: Dict[str, Any] = Field(..., description="用户输入参数")
    aspect_ratio: Optional[str] = Field("16:9", description="宽高比")
    resolution: Optional[str] = Field("1280x720", description="分辨率")


class WizardResumeRequest(BaseModel):
    """恢复中断的向导"""
    resume_from: Optional[str] = Field("", description="从指定 step key 恢复")


class WizardStepEvent(BaseModel):
    """向导步骤事件"""
    step: str
    name: Optional[str] = None
    stats: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


# =====================================================
# 剧本 Schema
# =====================================================

class ScriptCreate(BaseModel):
    """新增剧本分集"""
    episode_no: int = Field(1, ge=1, description="分集号")
    title: Optional[str] = Field(None, max_length=200)
    content: Optional[str] = None
    outline: Optional[str] = None


class ScriptUpdate(BaseModel):
    """编辑剧本"""
    title: Optional[str] = None
    content: Optional[str] = None
    outline: Optional[str] = None
    status: Optional[str] = None


class ScriptResponse(BaseModel):
    """剧本响应"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    episode_no: int
    title: Optional[str] = None
    content: Optional[str] = None
    outline: Optional[str] = None
    model: Optional[str] = None
    tokens_used: int = 0
    status: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ScriptRegenerateRequest(BaseModel):
    """重生成剧本"""
    prompt_template: Optional[str] = None
    model: Optional[str] = None


# =====================================================
# 角色/场景/道具 Schema（统一模式）
# =====================================================

class CharacterCreate(BaseModel):
    """添加角色"""
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    appearance_desc: Optional[str] = None
    role_type: Optional[str] = Field("supporting", description="main/supporting/minor")
    asset_id: Optional[int] = None


class CharacterUpdate(BaseModel):
    """编辑角色"""
    name: Optional[str] = None
    description: Optional[str] = None
    appearance_desc: Optional[str] = None
    role_type: Optional[str] = None


class CharacterResponse(BaseModel):
    """角色响应"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    name: str
    description: Optional[str] = None
    appearance_desc: Optional[str] = None
    role_type: str
    asset_id: Optional[int] = None
    active_image_id: Optional[int] = None
    sort_order: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    # service 层注入：当前激活版本详情（前端展示图像用）
    active_image: Optional["EntityAssetResponse"] = None


class SceneCreate(BaseModel):
    """添加场景"""
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    location: Optional[str] = None
    time_of_day: Optional[str] = None
    atmosphere: Optional[str] = None
    asset_id: Optional[int] = None


class SceneUpdate(BaseModel):
    """编辑场景"""
    name: Optional[str] = None
    description: Optional[str] = None
    location: Optional[str] = None
    time_of_day: Optional[str] = None
    atmosphere: Optional[str] = None


class SceneResponse(BaseModel):
    """场景响应"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    name: str
    description: Optional[str] = None
    location: Optional[str] = None
    time_of_day: Optional[str] = None
    atmosphere: Optional[str] = None
    asset_id: Optional[int] = None
    active_image_id: Optional[int] = None
    sort_order: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    # service 层注入：当前激活版本详情
    active_image: Optional["EntityAssetResponse"] = None


class PropCreate(BaseModel):
    """添加道具"""
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    visual_desc: Optional[str] = None
    asset_id: Optional[int] = None


class PropUpdate(BaseModel):
    """编辑道具"""
    name: Optional[str] = None
    description: Optional[str] = None
    visual_desc: Optional[str] = None


class PropResponse(BaseModel):
    """道具响应"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    name: str
    description: Optional[str] = None
    visual_desc: Optional[str] = None
    asset_id: Optional[int] = None
    active_image_id: Optional[int] = None
    sort_order: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    # service 层注入：当前激活版本详情
    active_image: Optional["EntityAssetResponse"] = None


# =====================================================
# 实体素材版本 Schema
# =====================================================

class EntityAssetResponse(BaseModel):
    """实体素材版本响应"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    entity_type: str
    entity_id: int
    version: int
    is_active: bool
    is_manual: bool
    file_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    prompt: Optional[str] = None
    model: Optional[str] = None
    generation_id: Optional[int] = None
    file_type: Optional[str] = None
    file_size: Optional[int] = None
    duration_ms: Optional[int] = None
    width: Optional[int] = None
    height: Optional[int] = None
    created_by: str
    created_at: Optional[datetime] = None


class SetActiveVersionRequest(BaseModel):
    """设为采用版"""
    entity_type: str = Field(..., description="character/scene/prop")
    entity_id: int
    version_id: int


# =====================================================
# 分镜 Schema
# =====================================================

class ShotCreate(BaseModel):
    """添加分镜"""
    sequence_no: Optional[int] = None
    title: Optional[str] = None
    shot_type: Optional[str] = None
    camera_movement: Optional[str] = None
    angle: Optional[str] = None
    dialogue: Optional[str] = None
    visual_desc: Optional[str] = None
    atmosphere: Optional[str] = None
    image_prompt: Optional[str] = None
    duration_ms: Optional[int] = 3000
    scene_id: Optional[int] = None


class ShotUpdate(BaseModel):
    """编辑分镜"""
    title: Optional[str] = None
    shot_type: Optional[str] = None
    camera_movement: Optional[str] = None
    angle: Optional[str] = None
    dialogue: Optional[str] = None
    visual_desc: Optional[str] = None
    atmosphere: Optional[str] = None
    image_prompt: Optional[str] = None
    duration_ms: Optional[int] = None
    scene_id: Optional[int] = None
    status: Optional[str] = None


class ShotResponse(BaseModel):
    """分镜响应"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    script_id: Optional[int] = None
    sequence_no: int
    title: Optional[str] = None
    shot_type: Optional[str] = None
    camera_movement: Optional[str] = None
    angle: Optional[str] = None
    dialogue: Optional[str] = None
    visual_desc: Optional[str] = None
    atmosphere: Optional[str] = None
    image_prompt: Optional[str] = None
    duration_ms: int
    scene_id: Optional[int] = None
    active_frame_image_id: Optional[int] = None
    active_video_id: Optional[int] = None
    active_audio_id: Optional[int] = None  # Phase 2
    status: str
    sort_order: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    # 关联实体（可选展开）
    characters: Optional[List["CharacterResponse"]] = None
    props: Optional[List["PropResponse"]] = None
    frame_images: Optional[List["FrameImageResponse"]] = None
    videos: Optional[List["VideoResponse"]] = None
    audios: Optional[List["ProjectShotAudioResponse"]] = None  # Phase 2
    active_frame_image: Optional["FrameImageResponse"] = None
    active_video: Optional["VideoResponse"] = None
    active_audio: Optional["ProjectShotAudioResponse"] = None  # Phase 2


class ReorderRequest(BaseModel):
    """重排顺序"""
    ids: List[int] = Field(..., description="按新顺序排列的 ID 数组")


class BindEntityRequest(BaseModel):
    """绑定实体"""
    entity_id: int = Field(..., description="角色/道具 ID")


# =====================================================
# 帧图/视频 Schema
# =====================================================

class FrameImageResponse(BaseModel):
    """帧图版本响应"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    shot_id: int
    version: int
    is_active: bool
    is_manual: bool
    file_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    prompt: Optional[str] = None
    model: Optional[str] = None
    generation_id: Optional[int] = None
    reference_character_ids: List[int] = Field(default_factory=list)
    width: Optional[int] = None
    height: Optional[int] = None
    file_size: Optional[int] = None
    created_by: str
    created_at: Optional[datetime] = None


class VideoResponse(BaseModel):
    """视频版本响应"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    shot_id: int
    version: int
    is_active: bool
    is_manual: bool
    file_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    frame_image_id: Optional[int] = None
    prompt: Optional[str] = None
    model: Optional[str] = None
    generation_id: Optional[int] = None
    duration_ms: Optional[int] = None
    width: Optional[int] = None
    height: Optional[int] = None
    file_size: Optional[int] = None
    created_by: str
    created_at: Optional[datetime] = None


class GenerateImageRequest(BaseModel):
    """生成图片请求"""
    style_config: Optional[Dict[str, Any]] = None
    model: Optional[str] = None
    size: Optional[str] = None


class BatchGenerateRequest(BaseModel):
    """批量生成请求"""
    ids: List[int] = Field(..., description="实体/分镜 ID 数组")
    style_config: Optional[Dict[str, Any]] = None
    model: Optional[str] = None
    size: Optional[str] = None


class GenerateVideoRequest(BaseModel):
    """生成视频请求"""
    frame_image_id: Optional[int] = Field(None, description="来源帧图 ID（不传则用采用版）")
    model: Optional[str] = None
    duration_ms: Optional[int] = 3000


# =====================================================
# 资产桥接 Schema
# =====================================================

class ImportAssetRequest(BaseModel):
    """从资产库导入"""
    asset_id: int


class PromoteAssetRequest(BaseModel):
    """沉淀到资产库"""
    entity_type: str
    entity_id: int


# =====================================================
# 画布 Schema
# =====================================================

class CanvasDataUpdate(BaseModel):
    """保存画布布局"""
    canvas_data: Dict[str, Any]


class CanvasLayoutResponse(BaseModel):
    """画布布局响应"""
    canvas_data: Dict[str, Any] = Field(default_factory=dict)


# =====================================================
# 合成 Schema
# =====================================================

class MergeRequest(BaseModel):
    """触发合成"""
    pass


class MergeStatusResponse(BaseModel):
    """合成状态响应"""
    status: str
    final_video_url: Optional[str] = None
    total_duration: float = 0
    error: Optional[str] = None


# =====================================================
# Phase 2 Schema — 配音 / 音色映射 / 字幕 / 时间线
# =====================================================

# ---------- 配音 ----------

class ProjectShotAudioResponse(BaseModel):
    """分镜配音响应（多版本）"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    shot_id: int
    version: int
    is_active: bool
    is_manual: bool
    file_url: Optional[str] = None
    text: Optional[str] = None
    voice_id: Optional[str] = None
    voice_name: Optional[str] = None
    character_id: Optional[int] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    duration_ms: Optional[int] = None
    file_size: Optional[int] = None
    created_by: str = "ai"
    created_at: Optional[datetime] = None


class GenerateTTSRequest(BaseModel):
    """TTS 配音生成请求"""
    voice_id: Optional[str] = Field(None, description="音色 ID，不传则自动分配（同角色同声音）")
    character_id: Optional[int] = Field(None, description="关联角色 ID（用于音色固定）")
    text: Optional[str] = Field(None, description="TTS 文本，不传则用 shot.dialogue")
    model: Optional[str] = None
    provider: Optional[str] = None


class BatchGenerateTTSRequest(BaseModel):
    """批量 TTS 生成"""
    shot_ids: List[int] = Field(..., description="分镜 ID 数组")
    voice_id: Optional[str] = None


class SetActiveAudioRequest(BaseModel):
    """设为采用版音频"""
    version_id: int


# ---------- 音色映射 ----------

class CharacterVoiceResponse(BaseModel):
    """角色-音色映射响应"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    character_id: int
    voice_id: str
    voice_name: Optional[str] = None
    assigned_at: Optional[datetime] = None


class AssignCharacterVoiceRequest(BaseModel):
    """为角色分配音色"""
    voice_id: str
    voice_name: Optional[str] = None


class VoiceOption(BaseModel):
    """内置音色选项"""
    voice_id: str
    name: str
    gender: str = Field(..., description="male/female/neutral")
    suitable_for: str = Field("", description="适用角色描述")


# ---------- 字幕 ----------

class GenerateSubtitleRequest(BaseModel):
    """从分镜对白生成字幕"""
    shot_ids: Optional[List[int]] = Field(None, description="不传则全部有对白的分镜")
    style: Optional[Dict[str, Any]] = None


class SubtitleStyle(BaseModel):
    """字幕样式"""
    font_family: str = "Microsoft YaHei"
    font_size: int = 48
    font_color: str = "#FFFFFF"
    outline_color: str = "#000000"
    outline_width: int = 2
    position: str = "bottom"  # bottom/top/center
    margin_vertical: int = 60


class SubtitleClip(BaseModel):
    """单条字幕"""
    start_time: float
    end_time: float
    text: str


# ---------- 时间线 ----------

class TimelineClipResponse(BaseModel):
    """时间线片段响应"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    track_type: str  # video/audio/subtitle
    track_index: int
    source_type: Optional[str] = None
    source_id: Optional[int] = None
    shot_id: Optional[int] = None
    start_time: float
    duration: float
    trim_start: float = 0
    trim_end: Optional[float] = None
    transition_type: str = "none"
    transition_duration: float = 0
    subtitle_text: Optional[str] = None
    sort_order: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class TimelineClipCreate(BaseModel):
    """创建时间线片段"""
    track_type: str
    track_index: int = 0
    source_type: Optional[str] = None
    source_id: Optional[int] = None
    shot_id: Optional[int] = None
    start_time: float
    duration: float
    trim_start: float = 0
    trim_end: Optional[float] = None
    transition_type: str = "none"
    transition_duration: float = 0
    subtitle_text: Optional[str] = None
    sort_order: int = 0


class TimelineClipUpdate(BaseModel):
    """更新时间线片段"""
    start_time: Optional[float] = None
    duration: Optional[float] = None
    trim_start: Optional[float] = None
    trim_end: Optional[float] = None
    transition_type: Optional[str] = None
    transition_duration: Optional[float] = None
    subtitle_text: Optional[str] = None
    track_index: Optional[int] = None
    sort_order: Optional[int] = None


class TimelineDataUpdate(BaseModel):
    """时间线草稿数据更新（含字幕样式）"""
    subtitle_style: Optional[Dict[str, Any]] = None
    draft: Optional[Dict[str, Any]] = None


class TimelineDataResponse(BaseModel):
    """时间线数据响应"""
    clips: List[TimelineClipResponse]
    subtitle_style: Optional[Dict[str, Any]] = None
    total_duration: float = 0


class MergeAdvancedRequest(BaseModel):
    """高级合成请求（Phase 2）"""
    with_audio: bool = True
    with_subtitle: bool = True
    with_bgm: bool = False
    bgm_id: Optional[str] = None
    use_timeline: bool = True


class GenerateSubtitleAdvancedRequest(BaseModel):
    """高级字幕生成请求（支持 whisper 模式）"""
    shot_ids: Optional[List[int]] = Field(None, description="不传则全部有对白的分镜")
    mode: str = Field("llm", description="字幕模式: llm（默认）/ whisper（forced alignment）")
    whisper_model_size: str = Field("small", description="whisper 模型大小: tiny/base/small/medium/large-v3")


# =====================================================
# 解决前向引用：CharacterResponse/SceneResponse/PropResponse/ShotResponse
# 在定义时引用了尚未定义的 EntityAssetResponse / ProjectShotAudioResponse
# =====================================================
CharacterResponse.model_rebuild()
SceneResponse.model_rebuild()
PropResponse.model_rebuild()
ShotResponse.model_rebuild()
