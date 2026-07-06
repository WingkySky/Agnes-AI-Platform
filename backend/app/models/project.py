# =====================================================
# Project 模型 — 项目制创作的核心数据模型
# 包含项目主表、剧本、角色、场景、道具、分镜、帧图、视频、实体素材版本表
# 借鉴 LingGuo-Drama 的"引导性生成 + 逐个适配"范式
# =====================================================

from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Text, DateTime, JSON, Boolean, Float,
    ForeignKey, Index, UniqueConstraint, BigInteger
)
from sqlalchemy.orm import relationship

from app.core.database import Base


# =====================================================
# 项目状态常量
# =====================================================
PROJECT_STATUS_DRAFT = "draft"           # 草稿
PROJECT_STATUS_CREATING = "creating"     # 向导运行中
PROJECT_STATUS_IN_PROGRESS = "in_progress"  # 项目已创建，可逐个适配
PROJECT_STATUS_MERGING = "merging"       # 合成中
PROJECT_STATUS_COMPLETED = "completed"   # 已完成
PROJECT_STATUS_ARCHIVED = "archived"     # 已归档


class Project(Base):
    """
    项目主表 — 顶层载体，承载剧本/角色/场景/道具/分镜等独立实体

    字段说明:
    - id: 主键
    - title: 项目标题
    - description: 项目描述
    - user_id: 所属用户
    - status: 项目状态机（draft/creating/in_progress/merging/completed/archived）
    - cover_url: 封面图 URL
    - aspect_ratio: 宽高比（16:9 / 9:16 / 1:1）
    - resolution: 分辨率（1280x720 等）
    - wizard_inputs: 向导创建时用户输入的参数（JSON）
    - active_view: 当前活动视图（manager/canvas）
    - canvas_data: 画布视图布局数据（JSON）
    - timeline_data: 时间线草稿数据（JSON）
    - final_video_url: 最终成片 URL
    - total_duration: 总时长（秒）
    """
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    status = Column(String(30), default=PROJECT_STATUS_DRAFT, nullable=False, index=True)
    cover_url = Column(String(500), nullable=True)
    aspect_ratio = Column(String(20), default="16:9", nullable=False)
    resolution = Column(String(20), default="1280x720", nullable=False)
    wizard_inputs = Column(JSON, default=dict, nullable=False)
    active_view = Column(String(20), default="manager", nullable=False)
    canvas_data = Column(JSON, default=dict, nullable=False)
    timeline_data = Column(JSON, default=dict, nullable=False)
    final_video_url = Column(String(500), nullable=True)
    total_duration = Column(Float, default=0, nullable=False)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 关联
    scripts = relationship("ProjectScript", back_populates="project", cascade="all, delete-orphan")
    characters = relationship("ProjectCharacter", back_populates="project", cascade="all, delete-orphan")
    scenes = relationship("ProjectScene", back_populates="project", cascade="all, delete-orphan")
    props = relationship("ProjectProp", back_populates="project", cascade="all, delete-orphan")
    shots = relationship("ProjectShot", back_populates="project", cascade="all, delete-orphan")


class ProjectScript(Base):
    """
    项目剧本表（含分集）

    字段说明:
    - project_id: 所属项目
    - episode_no: 分集号（同一项目内唯一）
    - title: 分集标题
    - content: 剧本正文
    - outline: 剧本大纲
    - model: 生成模型
    - prompt_template: 生成时使用的提示词模板
    - tokens_used: 消耗 token 数
    - status: 剧本状态（draft/approved）
    """
    __tablename__ = "project_scripts"
    __table_args__ = (
        UniqueConstraint("project_id", "episode_no", name="uq_project_scripts_episode"),
        Index("idx_project_scripts_project", "project_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    episode_no = Column(Integer, default=1, nullable=False)
    title = Column(String(200), nullable=True)
    content = Column(Text, nullable=True)
    outline = Column(Text, nullable=True)
    model = Column(String(100), nullable=True)
    prompt_template = Column(Text, nullable=True)
    tokens_used = Column(Integer, default=0, nullable=False)
    status = Column(String(30), default="draft", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    project = relationship("Project", back_populates="scripts")
    shots = relationship("ProjectShot", back_populates="script")


class ProjectCharacter(Base):
    """
    项目角色实体表

    字段说明:
    - project_id: 所属项目
    - name: 角色名
    - description: 角色描述
    - appearance_desc: 外观描述（用于生图 prompt）
    - role_type: 角色类型（main/supporting/minor）
    - asset_id: 关联的公共资产 ID（C2 引用模式，可为空）
    - active_image_id: 当前采用的形象图 ID（指向 project_entity_assets.id）
    - sort_order: 排序序号
    """
    __tablename__ = "project_characters"
    __table_args__ = (
        Index("idx_project_characters_project", "project_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    appearance_desc = Column(Text, nullable=True)
    role_type = Column(String(20), default="supporting", nullable=False)  # main/supporting/minor
    asset_id = Column(Integer, ForeignKey("assets.id"), nullable=True)  # C2 引用模式
    active_image_id = Column(Integer, nullable=True)  # 指向 project_entity_assets.id
    sort_order = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    project = relationship("Project", back_populates="characters")
    asset = relationship("Asset", foreign_keys=[asset_id])
    shots = relationship("ProjectShotCharacter", back_populates="character", cascade="all, delete-orphan")
    voice_assignments = relationship("ProjectCharacterVoice", back_populates="character", cascade="all, delete-orphan")  # Phase 2


class ProjectScene(Base):
    """
    项目场景实体表

    字段说明:
    - project_id: 所属项目
    - name: 场景名
    - description: 场景描述
    - location: 地点
    - time_of_day: 时间段（白天/夜晚/黄昏等）
    - atmosphere: 氛围描述
    - asset_id: 关联的公共资产 ID
    - active_image_id: 当前采用的场景图 ID
    - sort_order: 排序序号
    """
    __tablename__ = "project_scenes"
    __table_args__ = (
        Index("idx_project_scenes_project", "project_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    location = Column(String(200), nullable=True)
    time_of_day = Column(String(50), nullable=True)
    atmosphere = Column(Text, nullable=True)
    asset_id = Column(Integer, ForeignKey("assets.id"), nullable=True)
    active_image_id = Column(Integer, nullable=True)
    sort_order = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    project = relationship("Project", back_populates="scenes")
    asset = relationship("Asset", foreign_keys=[asset_id])
    shots = relationship("ProjectShot", back_populates="scene")


class ProjectProp(Base):
    """
    项目道具实体表

    字段说明:
    - project_id: 所属项目
    - name: 道具名
    - description: 道具描述
    - visual_desc: 视觉描述（用于生图 prompt）
    - asset_id: 关联的公共资产 ID
    - active_image_id: 当前采用的道具图 ID
    - sort_order: 排序序号
    """
    __tablename__ = "project_props"
    __table_args__ = (
        Index("idx_project_props_project", "project_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    visual_desc = Column(Text, nullable=True)
    asset_id = Column(Integer, ForeignKey("assets.id"), nullable=True)
    active_image_id = Column(Integer, nullable=True)
    sort_order = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    project = relationship("Project", back_populates="props")
    asset = relationship("Asset", foreign_keys=[asset_id])
    shots = relationship("ProjectShotProp", back_populates="prop", cascade="all, delete-orphan")


class ProjectEntityAsset(Base):
    """
    实体素材多版本表（统一表）

    多态引用：entity_id 指向 project_characters/scenes/props 的 id
    （应用层保证一致性，不设外键）

    字段说明:
    - project_id: 所属项目
    - entity_type: 实体类型（character/scene/prop）
    - entity_id: 实体 ID（多态引用）
    - version: 版本号（从 1 开始）
    - is_active: 是否为当前采用版
    - is_manual: 是否为用户手动上传（G1）
    - file_url: 文件 URL
    - thumbnail_url: 缩略图 URL
    - prompt: 生成时使用的 prompt
    - model: 生成模型
    - generation_id: 关联的生成记录 ID
    - file_type: 文件类型（image/video 等）
    - file_size: 文件大小（字节）
    - duration_ms: 时长（毫秒，视频/音频用）
    - width/height: 宽高（图片/视频用）
    - created_by: 创建方式（ai/manual/import）
    """
    __tablename__ = "project_entity_assets"
    __table_args__ = (
        UniqueConstraint("entity_type", "entity_id", "version", name="uq_pea_entity_version"),
        Index("idx_pea_project", "project_id"),
        Index("idx_pea_entity", "entity_type", "entity_id"),
        Index("idx_pea_active", "entity_type", "entity_id", "is_active"),
    )

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    entity_type = Column(String(20), nullable=False)  # character/scene/prop
    entity_id = Column(Integer, nullable=False)
    version = Column(Integer, default=1, nullable=False)
    is_active = Column(Boolean, default=False, nullable=False)
    is_manual = Column(Boolean, default=False, nullable=False)
    file_url = Column(String(500), nullable=True)
    thumbnail_url = Column(String(500), nullable=True)
    prompt = Column(Text, nullable=True)
    model = Column(String(100), nullable=True)
    generation_id = Column(Integer, ForeignKey("generations.id"), nullable=True)
    file_type = Column(String(20), nullable=True)
    file_size = Column(BigInteger, nullable=True)
    duration_ms = Column(Integer, nullable=True)
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    created_by = Column(String(20), default="ai", nullable=False)  # ai/manual/import
    created_at = Column(DateTime, default=datetime.utcnow)


class ProjectShot(Base):
    """
    项目分镜表

    字段说明:
    - project_id: 所属项目
    - script_id: 关联的剧本 ID
    - sequence_no: 分镜序号（同一项目内唯一）
    - title: 分镜标题
    - shot_type: 景别（特写/中景/全景等）
    - camera_movement: 运镜（推/拉/摇/移等）
    - angle: 视角（俯视/平视/仰视等）
    - dialogue: 台词/旁白（用于 TTS）
    - visual_desc: 画面描述
    - atmosphere: 氛围描述
    - image_prompt: 绘画 prompt
    - duration_ms: 预计时长（毫秒）
    - scene_id: 绑定的场景 ID
    - active_frame_image_id: 当前采用的帧图 ID
    - active_video_id: 当前采用的视频 ID
    - active_audio_id: 当前采用的音频 ID（Phase 2）
    - status: 分镜状态（draft/ready/completed）
    - sort_order: 排序序号
    """
    __tablename__ = "project_shots"
    __table_args__ = (
        UniqueConstraint("project_id", "sequence_no", name="uq_project_shots_seq"),
        Index("idx_project_shots_project", "project_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    script_id = Column(Integer, ForeignKey("project_scripts.id"), nullable=True)
    sequence_no = Column(Integer, nullable=False)
    title = Column(String(200), nullable=True)
    shot_type = Column(String(50), nullable=True)  # 景别
    camera_movement = Column(String(50), nullable=True)  # 运镜
    angle = Column(String(50), nullable=True)  # 视角
    dialogue = Column(Text, nullable=True)  # 台词/旁白（用于 TTS）
    visual_desc = Column(Text, nullable=True)
    atmosphere = Column(Text, nullable=True)
    image_prompt = Column(Text, nullable=True)  # 绘画 prompt
    duration_ms = Column(Integer, default=3000, nullable=False)
    scene_id = Column(Integer, ForeignKey("project_scenes.id"), nullable=True)
    active_frame_image_id = Column(Integer, nullable=True)
    active_video_id = Column(Integer, nullable=True)
    active_audio_id = Column(Integer, nullable=True)  # Phase 2
    status = Column(String(30), default="draft", nullable=False)
    sort_order = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    project = relationship("Project", back_populates="shots")
    script = relationship("ProjectScript", back_populates="shots")
    scene = relationship("ProjectScene", back_populates="shots")
    frame_images = relationship("ProjectShotFrameImage", back_populates="shot", cascade="all, delete-orphan")
    videos = relationship("ProjectShotVideo", back_populates="shot", cascade="all, delete-orphan")
    audios = relationship("ProjectShotAudio", back_populates="shot", cascade="all, delete-orphan")  # Phase 2
    shot_characters = relationship("ProjectShotCharacter", back_populates="shot", cascade="all, delete-orphan")
    shot_props = relationship("ProjectShotProp", back_populates="shot", cascade="all, delete-orphan")


class ProjectShotCharacter(Base):
    """分镜-角色多对多关联表"""
    __tablename__ = "project_shot_characters"

    shot_id = Column(Integer, ForeignKey("project_shots.id", ondelete="CASCADE"), primary_key=True)
    character_id = Column(Integer, ForeignKey("project_characters.id", ondelete="CASCADE"), primary_key=True)
    sort_order = Column(Integer, default=0, nullable=False)

    shot = relationship("ProjectShot", back_populates="shot_characters")
    character = relationship("ProjectCharacter", back_populates="shots")


class ProjectShotProp(Base):
    """分镜-道具多对多关联表"""
    __tablename__ = "project_shot_props"

    shot_id = Column(Integer, ForeignKey("project_shots.id", ondelete="CASCADE"), primary_key=True)
    prop_id = Column(Integer, ForeignKey("project_props.id", ondelete="CASCADE"), primary_key=True)
    sort_order = Column(Integer, default=0, nullable=False)

    shot = relationship("ProjectShot", back_populates="shot_props")
    prop = relationship("ProjectProp", back_populates="shots")


class ProjectShotFrameImage(Base):
    """
    分镜帧图多版本表

    字段说明:
    - shot_id: 所属分镜
    - version: 版本号
    - is_active: 是否为当前采用版
    - is_manual: 是否为用户手动上传
    - file_url: 图片 URL
    - thumbnail_url: 缩略图 URL
    - prompt: 生成时使用的 prompt
    - model: 生成模型
    - generation_id: 关联的生成记录 ID
    - reference_character_ids: 参考的角色 ID 数组（JSON）
    - width/height: 图片宽高
    - file_size: 文件大小
    - created_by: 创建方式（ai/manual）
    """
    __tablename__ = "project_shot_frame_images"
    __table_args__ = (
        UniqueConstraint("shot_id", "version", name="uq_psf_shot_version"),
        Index("idx_psf_shot", "shot_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    shot_id = Column(Integer, ForeignKey("project_shots.id", ondelete="CASCADE"), nullable=False)
    version = Column(Integer, default=1, nullable=False)
    is_active = Column(Boolean, default=False, nullable=False)
    is_manual = Column(Boolean, default=False, nullable=False)
    file_url = Column(String(500), nullable=True)
    thumbnail_url = Column(String(500), nullable=True)
    prompt = Column(Text, nullable=True)
    model = Column(String(100), nullable=True)
    generation_id = Column(Integer, ForeignKey("generations.id"), nullable=True)
    reference_character_ids = Column(JSON, default=list, nullable=False)
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    file_size = Column(BigInteger, nullable=True)
    created_by = Column(String(20), default="ai", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    shot = relationship("ProjectShot", back_populates="frame_images")


class ProjectShotVideo(Base):
    """
    分镜视频多版本表

    字段说明:
    - shot_id: 所属分镜
    - version: 版本号
    - is_active: 是否为当前采用版
    - is_manual: 是否为用户手动上传
    - file_url: 视频 URL
    - thumbnail_url: 缩略图 URL
    - frame_image_id: 来源帧图 ID（图生视频）
    - prompt: 生成时使用的 prompt
    - model: 生成模型
    - generation_id: 关联的生成记录 ID
    - duration_ms: 视频时长（毫秒）
    - width/height: 视频宽高
    - file_size: 文件大小
    - created_by: 创建方式（ai/manual）
    """
    __tablename__ = "project_shot_videos"
    __table_args__ = (
        UniqueConstraint("shot_id", "version", name="uq_psv_shot_version"),
        Index("idx_psv_shot", "shot_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    shot_id = Column(Integer, ForeignKey("project_shots.id", ondelete="CASCADE"), nullable=False)
    version = Column(Integer, default=1, nullable=False)
    is_active = Column(Boolean, default=False, nullable=False)
    is_manual = Column(Boolean, default=False, nullable=False)
    file_url = Column(String(500), nullable=True)
    thumbnail_url = Column(String(500), nullable=True)
    frame_image_id = Column(Integer, ForeignKey("project_shot_frame_images.id"), nullable=True)
    prompt = Column(Text, nullable=True)
    model = Column(String(100), nullable=True)
    generation_id = Column(Integer, ForeignKey("generations.id"), nullable=True)
    duration_ms = Column(Integer, nullable=True)
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    file_size = Column(BigInteger, nullable=True)
    created_by = Column(String(20), default="ai", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    shot = relationship("ProjectShot", back_populates="videos")


# =====================================================
# Phase 2 模型 — 配音 / 音色映射 / 时间线片段
# =====================================================

class ProjectShotAudio(Base):
    """
    分镜配音多版本表（TTS 生成或用户上传）— Phase 2

    字段说明:
    - shot_id: 所属分镜
    - version: 版本号
    - is_active: 是否为当前采用版
    - is_manual: 是否为用户手动上传
    - file_url: 音频文件 URL
    - text: TTS 输入文本（即对白）
    - voice_id: 音色 ID
    - voice_name: 音色名称（冗余存储，便于展示）
    - character_id: 关联角色（同角色同声音策略）
    - provider: TTS provider（agnes/aliyun/volcengine 等）
    - model: TTS 模型名
    - duration_ms: 时长（毫秒）
    - file_size: 文件大小（字节）
    - created_by: 创建方式（ai/manual）
    """
    __tablename__ = "project_shot_audios"
    __table_args__ = (
        UniqueConstraint("shot_id", "version", name="uq_psa_shot_version"),
        Index("idx_psa_shot", "shot_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    shot_id = Column(Integer, ForeignKey("project_shots.id", ondelete="CASCADE"), nullable=False)
    version = Column(Integer, default=1, nullable=False)
    is_active = Column(Boolean, default=False, nullable=False)
    is_manual = Column(Boolean, default=False, nullable=False)
    file_url = Column(String(500), nullable=True)
    text = Column(Text, nullable=True)  # TTS 输入文本（即对白）
    voice_id = Column(String(100), nullable=True)  # 音色 ID
    voice_name = Column(String(200), nullable=True)  # 音色名称（冗余存储，便于展示）
    character_id = Column(Integer, ForeignKey("project_characters.id"), nullable=True)  # 关联角色（同角色同声音）
    provider = Column(String(50), nullable=True)  # TTS provider（agnes/aliyun/volcengine 等）
    model = Column(String(100), nullable=True)  # TTS 模型名
    duration_ms = Column(Integer, nullable=True)
    file_size = Column(BigInteger, nullable=True)
    created_by = Column(String(20), default="ai", nullable=False)  # ai/manual
    created_at = Column(DateTime, default=datetime.utcnow)

    shot = relationship("ProjectShot", back_populates="audios")
    character = relationship("ProjectCharacter")


class ProjectCharacterVoice(Base):
    """
    角色-音色映射表（同角色同声音）— Phase 2

    字段说明:
    - project_id: 所属项目
    - character_id: 关联角色
    - voice_id: 音色 ID
    - voice_name: 音色名称（冗余存储）
    - assigned_at: 分配时间
    """
    __tablename__ = "project_character_voices"
    __table_args__ = (
        UniqueConstraint("project_id", "character_id", name="uq_pcv_project_character"),
    )

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    character_id = Column(Integer, ForeignKey("project_characters.id", ondelete="CASCADE"), nullable=False)
    voice_id = Column(String(100), nullable=False)
    voice_name = Column(String(200), nullable=True)
    assigned_at = Column(DateTime, default=datetime.utcnow)

    character = relationship("ProjectCharacter", back_populates="voice_assignments")


class ProjectTimelineClip(Base):
    """
    时间线片段表（多轨：video/audio/subtitle）— Phase 2

    字段说明:
    - project_id: 所属项目
    - track_type: 轨道类型（video/audio/subtitle）
    - track_index: 轨道序号（0=主轨, 1=次轨）
    - source_type: 来源类型（shot_video/shot_audio/shot_frame_image/bgm/subtitle）
    - source_id: 来源 ID（多态引用 project_shot_videos/audios.id）
    - shot_id: 关联分镜（便于溯源）
    - start_time: 起始时间（秒）
    - duration: 时长（秒）
    - trim_start: 裁剪起始（秒）
    - trim_end: 裁剪结束（秒）
    - transition_type: 转场类型（fade/slide/wipe/dissolve/none）
    - transition_duration: 转场时长（秒）
    - subtitle_text: 字幕片段的文本
    - sort_order: 排序序号
    """
    __tablename__ = "project_timeline_clips"
    __table_args__ = (
        Index("idx_ptc_project", "project_id"),
        Index("idx_ptc_track", "project_id", "track_type", "track_index"),
    )

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    track_type = Column(String(20), nullable=False)  # video/audio/subtitle
    track_index = Column(Integer, default=0, nullable=False)  # 轨道序号
    source_type = Column(String(20), nullable=True)  # shot_video/shot_audio/bgm/subtitle
    source_id = Column(Integer, nullable=True)  # 多态引用 project_shot_videos/audios.id
    shot_id = Column(Integer, ForeignKey("project_shots.id"), nullable=True)
    start_time = Column(Float, nullable=False)  # 起始时间（秒）
    duration = Column(Float, nullable=False)  # 时长（秒）
    trim_start = Column(Float, default=0, nullable=False)  # 裁剪起始
    trim_end = Column(Float, nullable=True)  # 裁剪结束
    transition_type = Column(String(50), default="none", nullable=False)  # fade/slide/wipe/dissolve/none
    transition_duration = Column(Float, default=0, nullable=False)
    subtitle_text = Column(Text, nullable=True)  # 字幕片段的文本
    sort_order = Column(Integer, default=0, nullable=False)
    source_ref = Column(String(100), nullable=True)  # BGM 字符串 id 引用（source_id 是 Integer 不够用）
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ProjectMarker(Base):
    """
    项目时间线标记 — Phase 2 增强

    字段说明:
    - project_id: 所属项目
    - time: 标记时间点（秒）
    - name: 可选命名（如"重要节点"）
    - color: 颜色（默认 #4a9eff）
    """
    __tablename__ = "project_markers"
    __table_args__ = (
        Index("idx_pm_project", "project_id"),
        Index("idx_pm_project_time", "project_id", "time"),
    )

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    time = Column(Float, nullable=False)
    name = Column(String(100), nullable=True)
    color = Column(String(20), default="#4a9eff", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
