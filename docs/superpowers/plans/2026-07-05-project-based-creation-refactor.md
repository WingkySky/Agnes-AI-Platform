# 项目制创作重构 — Phase 1 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 agnes-platform 的 PipelineRun 抽象替换为 Project 抽象，实现"引导性生成 + 逐个适配"范式，跑通"创建项目 → 向导生成 → 逐个适配 → 简单合成"完整链路。

**Architecture:** 后端新增 `services/project/` 模块（wizard + 实体服务 + asset_bridge + sse_manager），前端新增 `views/projects/` + `components/project/` + `stores/project.ts`。删除旧 PipelineRun/Step 相关代码，保留 PipelineTemplate 改造为向导模板。数据层新增 11 张表（Phase 1）。

**Tech Stack:** FastAPI + SQLAlchemy async + httpx.AsyncClient + Vue 3 + Pinia + Element Plus + agn-sdk

**Spec:** [docs/superpowers/specs/2026-07-05-project-based-creation-refactor-design.md](file:///Users/skywing/agnes-platform/docs/superpowers/specs/2026-07-05-project-based-creation-refactor-design.md)

---

## 文件结构映射

### 后端新增

| 文件 | 职责 |
|------|------|
| `backend/app/models/project.py` | Project + 7 张实体表 + project_entity_assets + 2 张关联表 |
| `backend/app/schemas/project.py` | 项目相关 Pydantic 模型 |
| `backend/app/services/project/__init__.py` | 模块包 |
| `backend/app/services/project/sse_manager.py` | 项目级 SSE 推送 |
| `backend/app/services/project/project_service.py` | 项目 CRUD |
| `backend/app/services/project/wizard.py` | 项目创建向导（4 步 LLM 链） |
| `backend/app/services/project/script_service.py` | 剧本 CRUD + 重生成 |
| `backend/app/services/project/character_service.py` | 角色 CRUD + 生成 + 上传 + 版本 |
| `backend/app/services/project/scene_service.py` | 场景（同角色） |
| `backend/app/services/project/prop_service.py` | 道具（同角色） |
| `backend/app/services/project/shot_service.py` | 分镜 CRUD + 绑定 + 重排 |
| `backend/app/services/project/frame_image_service.py` | 帧图多版本 + 生成 + 上传 |
| `backend/app/services/project/video_service.py` | 视频多版本 + 生成 + 上传 |
| `backend/app/services/project/asset_bridge.py` | 项目实体 ↔ 资产库互转 |
| `backend/app/services/project/canvas_bridge.py` | 画布布局生成 |
| `backend/app/services/project/merge_service.py` | 简单合成（按分镜顺序拼接） |
| `backend/app/routes/projects.py` | 所有项目 API |

### 后端改造

| 文件 | 改造内容 |
|------|---------|
| `backend/app/models/pipeline.py` | 删除 PipelineRun/PipelineStep，保留 Template |
| `backend/app/models/__init__.py` | 注册新模型，移除旧模型导入 |
| `backend/app/services/pipeline/template_scenarios.py` | 改为 wizard_chain 定义 |
| `backend/app/main.py` | 注册 projects 路由 |

### 后端删除

- `backend/app/services/pipeline/engine.py`
- `backend/app/services/pipeline/run_service.py`
- `backend/app/services/pipeline/integration.py`
- `backend/app/services/pipeline/post_process_service.py`
- `backend/app/services/pipeline/moderation_service.py`
- `backend/app/services/pipeline/template_validate.py`
- `backend/app/services/pipeline/steps/`（保留 ffmpeg_composite.py 和 transition_compose.py 移到 project 服务下）
- `backend/app/models/pipeline_step_output_revision.py`
- `backend/app/routes/pipeline.py` 中的 runs/steps 路由

### 前端新增

| 文件 | 职责 |
|------|------|
| `frontend/src/api/projects.ts` | 项目 API 调用 |
| `frontend/src/stores/project.ts` | 项目状态管理 |
| `frontend/src/types/project.ts` | 项目类型定义 |
| `frontend/src/composables/useProjectSSE.ts` | 项目 SSE 订阅 |
| `frontend/src/views/projects/ProjectListView.vue` | 项目列表页 |
| `frontend/src/views/projects/ProjectDetailView.vue` | 项目详情页（含双视图） |
| `frontend/src/components/project/ProjectHeader.vue` | 顶部工具栏 |
| `frontend/src/components/project/ProjectManagerView.vue` | 管理视图（Tab 容器） |
| `frontend/src/components/project/ProjectCanvasView.vue` | 画布视图 |
| `frontend/src/components/project/ScriptTab.vue` | 剧本 Tab |
| `frontend/src/components/project/CharactersTab.vue` | 角色 Tab |
| `frontend/src/components/project/ScenesTab.vue` | 场景 Tab |
| `frontend/src/components/project/PropsTab.vue` | 道具 Tab |
| `frontend/src/components/project/ShotsTab.vue` | 分镜 Tab |
| `frontend/src/components/project/CharacterCard.vue` | 角色卡片 |
| `frontend/src/components/project/ShotCard.vue` | 分镜卡片 |
| `frontend/src/components/project/EntityVersionSwitcher.vue` | 版本切换器 |
| `frontend/src/components/project/EntityEditDialog.vue` | 实体编辑对话框 |
| `frontend/src/components/project/ProjectLaunchDialog.vue` | 项目创建对话框 |

### 前端改造

| 文件 | 改造内容 |
|------|---------|
| `frontend/src/router/index.ts` | 新增项目路由，废弃 pipeline 路由 |
| `frontend/src/config/menus.ts` | 新增"我的项目"菜单 |
| `frontend/src/views/WorkshopView.vue` | 改造为模板市场入口 |

### 前端删除

- `frontend/src/views/PipelineHistoryView.vue`
- `frontend/src/views/PipelineRunView.vue`
- `frontend/src/views/PipelineResultView.vue`
- `frontend/src/components/pipeline/StepList.vue`
- `frontend/src/components/pipeline/StepPanel.vue`
- `frontend/src/stores/pipeline.ts`
- `frontend/src/composables/usePipelineSSE.ts`

---

## Task 1: 数据模型层 — Project + 7 张实体表

**Files:**
- Create: `backend/app/models/project.py`
- Modify: `backend/app/models/__init__.py`

- [ ] **Step 1: 创建 project.py 模型文件**

创建 `backend/app/models/project.py`，包含以下模型（按 spec 4.2 节定义）：

```python
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
    - template_id: 创建向导使用的模板 ID（空白创建为 NULL）
    - user_id: 所属用户
    - status: 项目状态机
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
    template_id = Column(Integer, ForeignKey("pipeline_templates.id"), nullable=True)
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
    """项目剧本表（含分集）"""
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
    """项目角色实体表"""
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


class ProjectScene(Base):
    """项目场景实体表"""
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
    """项目道具实体表"""
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
    """项目分镜表"""
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
    """分镜帧图多版本表"""
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
    """分镜视频多版本表"""
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
```

- [ ] **Step 2: 注册新模型到 __init__.py**

修改 `backend/app/models/__init__.py`，在文件末尾添加：

```python
from app.models.project import (
    Project,
    ProjectScript,
    ProjectCharacter,
    ProjectScene,
    ProjectProp,
    ProjectEntityAsset,
    ProjectShot,
    ProjectShotCharacter,
    ProjectShotProp,
    ProjectShotFrameImage,
    ProjectShotVideo,
)
```

- [ ] **Step 3: 验证模型加载**

Run: `cd /Users/skywing/agnes-platform/backend && python -c "from app.models.project import Project, ProjectScript, ProjectCharacter, ProjectScene, ProjectProp, ProjectEntityAsset, ProjectShot, ProjectShotCharacter, ProjectShotProp, ProjectShotFrameImage, ProjectShotVideo; print('OK')"`
Expected: 输出 `OK`

- [ ] **Step 4: 提交**

```bash
cd /Users/skywing/agnes-platform
git add backend/app/models/project.py backend/app/models/__init__.py
git commit -m "feat(project): 新增项目制创作数据模型（11 张表）"
```

---

## Task 2: Pydantic Schema 层

**Files:**
- Create: `backend/app/schemas/project.py`

- [ ] **Step 1: 创建 schemas/project.py**

创建完整的请求/响应 Pydantic 模型，覆盖项目 CRUD、剧本、角色/场景/道具、分镜、帧图、视频、版本管理、向导等。具体字段参考 spec 第 9 节 API 设计。

关键 Schema：
- `ProjectCreate` / `ProjectUpdate` / `ProjectResponse` / `ProjectListResponse`
- `WizardCreateRequest` / `WizardStepEvent`
- `ScriptCreate` / `ScriptUpdate` / `ScriptResponse`
- `CharacterCreate` / `CharacterUpdate` / `CharacterResponse`（场景/道具同构）
- `ShotCreate` / `ShotUpdate` / `ShotResponse`
- `FrameImageResponse` / `VideoResponse` / `EntityAssetResponse`
- `GenerateImageRequest` / `BatchGenerateRequest` / `UploadRequest`
- `SetActiveVersionRequest` / `ReorderRequest`
- `ExtractEntitiesRequest` / `ImportAssetRequest` / `PromoteAssetRequest`

所有 Response 模型使用 `model_config = ConfigDict(from_attributes=True)`。

- [ ] **Step 2: 验证 Schema 加载**

Run: `cd /Users/skywing/agnes-platform/backend && python -c "from app.schemas.project import ProjectResponse, WizardCreateRequest; print('OK')"`
Expected: `OK`

- [ ] **Step 3: 提交**

```bash
git add backend/app/schemas/project.py
git commit -m "feat(project): 新增项目 Pydantic Schema"
```

---

## Task 3: 项目级 SSE 管理器

**Files:**
- Create: `backend/app/services/project/__init__.py`
- Create: `backend/app/services/project/sse_manager.py`

- [ ] **Step 1: 创建 sse_manager.py**

参考现有 `services/pipeline/sse_manager.py` 的 asyncio.Queue 多订阅者模式，改造为项目级：

```python
# =====================================================
# 项目级 SSE 进度推送管理器
# 功能：
#   1. 管理每个项目的 SSE 订阅者
#   2. 向导/生成/编辑等动作通过 push 推送事件
#   3. 自动清理超时连接
# =====================================================

import asyncio
import json
import logging
import time
from typing import Dict, Any, Set

logger = logging.getLogger("agnes_platform.project")


class ProjectSSEManager:
    """项目级 SSE 推送管理器（asyncio.Queue 多订阅者）"""

    def __init__(self):
        self._subscribers: Dict[int, Set[asyncio.Queue]] = {}
        self._lock = asyncio.Lock()

    async def subscribe(self, project_id: int) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        async with self._lock:
            if project_id not in self._subscribers:
                self._subscribers[project_id] = set()
            self._subscribers[project_id].add(queue)
        logger.debug(f"项目 SSE 订阅: project_id={project_id}")
        return queue

    async def unsubscribe(self, project_id: int, queue: asyncio.Queue):
        async with self._lock:
            if project_id in self._subscribers:
                self._subscribers[project_id].discard(queue)
                if not self._subscribers[project_id]:
                    del self._subscribers[project_id]

    async def push(self, project_id: int, event_type: str, data: dict):
        """推送事件给项目的所有订阅者"""
        async with self._lock:
            queues = self._subscribers.get(project_id, set()).copy()

        event_str = self._format_sse_event(event_type, data)
        for q in queues:
            try:
                q.put_nowait(event_str)
            except asyncio.QueueFull:
                logger.warning(f"项目 SSE 队列已满: project_id={project_id}")

    @staticmethod
    def _format_sse_event(event_type: str, data: dict) -> str:
        payload = json.dumps(data, ensure_ascii=False)
        return f"event: {event_type}\ndata: {payload}\n\n"


# 全局单例
project_sse_manager = ProjectSSEManager()
```

- [ ] **Step 2: 创建 __init__.py**

```python
# 项目制创作服务模块
```

- [ ] **Step 3: 提交**

```bash
git add backend/app/services/project/
git commit -m "feat(project): 新增项目级 SSE 管理器"
```

---

## Task 4: 项目 CRUD 服务

**Files:**
- Create: `backend/app/services/project/project_service.py`

- [ ] **Step 1: 创建 project_service.py**

实现以下函数（全部 async，使用 AsyncSession）：

```python
# =====================================================
# 项目 CRUD 服务
# =====================================================

from typing import Optional, List, Tuple
from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.project import (
    Project, ProjectScript, ProjectCharacter, ProjectScene,
    ProjectProp, ProjectShot, PROJECT_STATUS_DRAFT, PROJECT_STATUS_IN_PROGRESS,
)
from app.schemas.project import ProjectCreate, ProjectUpdate


async def create_project(db: AsyncSession, user_id: int, data: ProjectCreate) -> Project:
    """创建空项目（status=in_progress）"""
    project = Project(
        title=data.title,
        description=data.description,
        template_id=data.template_id,
        user_id=user_id,
        status=PROJECT_STATUS_IN_PROGRESS,
        aspect_ratio=data.aspect_ratio or "16:9",
        resolution=data.resolution or "1280x720",
        wizard_inputs=data.wizard_inputs or {},
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return project


async def get_project(db: AsyncSession, project_id: int) -> Optional[Project]:
    """获取项目详情"""
    result = await db.execute(
        select(Project)
        .options(selectinload(Project.scripts))
        .where(Project.id == project_id)
    )
    return result.scalar_one_or_none()


async def list_projects(
    db: AsyncSession,
    user_id: int,
    status: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
) -> Tuple[List[Project], int]:
    """获取用户项目列表（分页）"""
    query = select(Project).where(Project.user_id == user_id)
    if status:
        query = query.where(Project.status == status)
    query = query.order_by(Project.updated_at.desc())

    # 总数
    count_q = select(func.count()).select_from(Project).where(Project.user_id == user_id)
    if status:
        count_q = count_q.where(Project.status == status)
    total = (await db.execute(count_q)).scalar() or 0

    # 分页
    offset = (page - 1) * page_size
    result = await db.execute(query.offset(offset).limit(page_size))
    return result.scalars().all(), total


async def update_project(db: AsyncSession, project_id: int, data: ProjectUpdate) -> Optional[Project]:
    """更新项目"""
    project = await get_project(db, project_id)
    if not project:
        return None
    update_data = data.model_dump(exclude_unset=True)
    for k, v in update_data.items():
        setattr(project, k, v)
    await db.commit()
    await db.refresh(project)
    return project


async def delete_project(db: AsyncSession, project_id: int) -> bool:
    """删除项目（级联删除所有实体）"""
    project = await get_project(db, project_id)
    if not project:
        return False
    await db.delete(project)
    await db.commit()
    return True


async def archive_project(db: AsyncSession, project_id: int) -> Optional[Project]:
    """归档项目"""
    project = await get_project(db, project_id)
    if not project:
        return None
    project.status = "archived"
    await db.commit()
    await db.refresh(project)
    return project


async def update_active_view(db: AsyncSession, project_id: int, view: str) -> Optional[Project]:
    """切换活动视图"""
    project = await get_project(db, project_id)
    if not project:
        return None
    project.active_view = view
    await db.commit()
    await db.refresh(project)
    return project
```

- [ ] **Step 2: 提交**

```bash
git add backend/app/services/project/project_service.py
git commit -m "feat(project): 新增项目 CRUD 服务"
```

---

## Task 5: 项目创建向导

**Files:**
- Create: `backend/app/services/project/wizard.py`

- [ ] **Step 1: 创建 wizard.py**

实现 4 步 LLM 链：剧本生成 → 实体提取 → 分镜拆分 → 帧 prompt 提取。

关键要点：
1. `parse_json_loose()` 多层容错解析（代码块包裹、字段缺失、类型不符）
2. 单步失败重试 2 次
3. 每步立即落库
4. SSE 推送进度
5. 支持从失败步骤 resume

```python
# =====================================================
# 项目创建向导 — 按模板 wizard_chain 顺序执行 LLM 链
# 步骤：剧本生成 → 实体提取 → 分镜拆分 → 帧 prompt 提取
# =====================================================

import json
import re
import logging
from typing import Dict, Any, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import (
    Project, ProjectScript, ProjectCharacter, ProjectScene, ProjectProp,
    ProjectShot, ProjectShotCharacter, ProjectShotProp,
    PROJECT_STATUS_CREATING, PROJECT_STATUS_IN_PROGRESS,
)
from app.services.agnes_client import agnes_client
from app.services.project.sse_manager import project_sse_manager

logger = logging.getLogger("agnes_platform.project.wizard")


def parse_json_loose(text: str) -> Any:
    """
    宽松 JSON 解析：
    - 去除 markdown 代码块包裹
    - 提取首个 { ... } 或 [ ... ] 块
    - 容忍尾部逗号
    """
    if not text:
        return {}
    # 去除 markdown 代码块
    text = re.sub(r"```(?:json)?\s*", "", text)
    text = text.replace("```", "")
    text = text.strip()
    # 尝试直接解析
    try:
        return json.loads(text)
    except Exception:
        pass
    # 提取首个 JSON 对象/数组
    for start_char, end_char in [("{", "}"), ("[", "]")]:
        start = text.find(start_char)
        end = text.rfind(end_char)
        if start != -1 and end != -1 and end > start:
            fragment = text[start:end + 1]
            # 去除尾部逗号
            fragment = re.sub(r",\s*([}\]])", r"\1", fragment)
            try:
                return json.loads(fragment)
            except Exception:
                continue
    return {}


async def _call_llm(prompt: str, model: str = "", temperature: float = 0.7) -> str:
    """调用 LLM 返回文本"""
    body = {
        "model": model or "agnes-2.0-flash",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
    }
    result = await agnes_client._post(f"{agnes_client.base_url}/chat/completions", body)
    choices = result.get("choices", [])
    if not choices:
        raise RuntimeError("LLM 返回为空")
    return choices[0].get("message", {}).get("content", "") or ""


async def _step_script_generation(
    db: AsyncSession, project: Project, step_config: dict, inputs: dict
) -> dict:
    """步骤 1：剧本生成"""
    prompt = step_config["prompt_template"].format(**inputs)
    content = await _call_llm(prompt, step_config.get("model"), step_config.get("temperature", 0.8))

    script = ProjectScript(
        project_id=project.id,
        episode_no=1,
        title=f"{inputs.get('topic', '默认剧集')}",
        content=content,
        model=step_config.get("model"),
        prompt_template=step_config["prompt_template"],
        status="approved",
    )
    db.add(script)
    await db.commit()
    await db.refresh(script)
    return {"script_id": script.id, "content": content}


async def _step_entity_extraction(
    db: AsyncSession, project: Project, step_config: dict, context: dict
) -> dict:
    """步骤 2：从剧本提取角色/场景/道具清单"""
    script_content = context.get("script_generation", {}).get("content", "")
    prompt = step_config["prompt_template"].format(script=script_content)
    result_text = await _call_llm(prompt, step_config.get("model"), step_config.get("temperature", 0.5))
    parsed = parse_json_loose(result_text)

    stats = {"characters": 0, "scenes": 0, "props": 0}

    # 批量写入角色
    for item in parsed.get("characters", []):
        char = ProjectCharacter(
            project_id=project.id,
            name=item.get("name", "未命名"),
            description=item.get("description", ""),
            appearance_desc=item.get("appearance_desc", item.get("description", "")),
            role_type=item.get("role_type", "supporting"),
        )
        db.add(char)
        stats["characters"] += 1

    # 批量写入场景
    for item in parsed.get("scenes", []):
        scene = ProjectScene(
            project_id=project.id,
            name=item.get("name", "未命名场景"),
            description=item.get("description", ""),
            location=item.get("location", ""),
            time_of_day=item.get("time_of_day", ""),
            atmosphere=item.get("atmosphere", ""),
        )
        db.add(scene)
        stats["scenes"] += 1

    # 批量写入道具
    for item in parsed.get("props", []):
        prop = ProjectProp(
            project_id=project.id,
            name=item.get("name", "未命名道具"),
            description=item.get("description", ""),
            visual_desc=item.get("visual_desc", item.get("description", "")),
        )
        db.add(prop)
        stats["props"] += 1

    await db.commit()
    return stats


async def _step_storyboard_split(
    db: AsyncSession, project: Project, step_config: dict, context: dict
) -> dict:
    """步骤 3：基于已确认实体清单拆分分镜（E2）"""
    script_content = context.get("script_generation", {}).get("content", "")

    # 注入实体清单
    from sqlalchemy import select
    chars = (await db.execute(select(ProjectCharacter).where(ProjectCharacter.project_id == project.id))).scalars().all()
    scenes = (await db.execute(select(ProjectScene).where(ProjectScene.project_id == project.id))).scalars().all()
    props = (await db.execute(select(ProjectProp).where(ProjectProp.project_id == project.id))).scalars().all()

    char_info = json.dumps([{"id": c.id, "name": c.name, "desc": c.description} for c in chars], ensure_ascii=False)
    scene_info = json.dumps([{"id": s.id, "name": s.name, "desc": s.description} for s in scenes], ensure_ascii=False)
    prop_info = json.dumps([{"id": p.id, "name": p.name, "desc": p.description} for p in props], ensure_ascii=False)

    prompt = step_config["prompt_template"].format(
        script=script_content,
        characters=char_info,
        scenes=scene_info,
        props=prop_info,
    )
    result_text = await _call_llm(prompt, step_config.get("model"), step_config.get("temperature", 0.6))
    parsed = parse_json_loose(result_text)

    # 构建实体名→id 映射
    char_map = {c.name: c.id for c in chars}
    scene_map = {s.name: s.id for s in scenes}
    prop_map = {p.name: p.id for p in props}

    count = 0
    for idx, shot_data in enumerate(parsed.get("shots", parsed.get("storyboard", [])), start=1):
        shot = ProjectShot(
            project_id=project.id,
            sequence_no=idx,
            sort_order=idx - 1,
            title=shot_data.get("title", f"分镜 {idx}"),
            shot_type=shot_data.get("shot_type", ""),
            camera_movement=shot_data.get("camera_movement", ""),
            angle=shot_data.get("angle", ""),
            dialogue=shot_data.get("dialogue", ""),
            visual_desc=shot_data.get("visual_desc", shot_data.get("image_prompt", "")),
            atmosphere=shot_data.get("atmosphere", ""),
            image_prompt=shot_data.get("image_prompt", shot_data.get("visual_desc", "")),
            duration_ms=shot_data.get("duration_ms", 3000),
            scene_id=scene_map.get(shot_data.get("scene_name", "")),
            status="draft",
        )
        db.add(shot)
        await db.flush()  # 获取 shot.id

        # 绑定角色
        for char_name in shot_data.get("characters_in_scene", []):
            cid = char_map.get(char_name)
            if cid:
                db.add(ProjectShotCharacter(shot_id=shot.id, character_id=cid))

        # 绑定道具
        for prop_name in shot_data.get("props_in_scene", []):
            pid = prop_map.get(prop_name)
            if pid:
                db.add(ProjectShotProp(shot_id=shot.id, prop_id=pid))

        count += 1

    await db.commit()
    return {"shots": count}


async def _step_frame_prompt_extract(
    db: AsyncSession, project: Project, step_config: dict, context: dict
) -> dict:
    """步骤 4：为每个分镜提取帧级绘画 prompt（可选）"""
    from sqlalchemy import select
    shots = (await db.execute(
        select(ProjectShot).where(ProjectShot.project_id == project.id).order_by(ProjectShot.sequence_no)
    )).scalars().all()

    if not shots:
        return {"updated": 0}

    # 构建分镜概览
    shots_summary = json.dumps([
        {"id": s.id, "title": s.title, "visual_desc": s.visual_desc, "dialogue": s.dialogue}
        for s in shots
    ], ensure_ascii=False)

    prompt = step_config["prompt_template"].format(shots=shots_summary)
    result_text = await _call_llm(prompt, step_config.get("model"), step_config.get("temperature", 0.5))
    parsed = parse_json_loose(result_text)

    updated = 0
    prompts_map = {item["id"]: item.get("image_prompt", "") for item in parsed.get("shots", []) if "id" in item}
    for shot in shots:
        new_prompt = prompts_map.get(shot.id)
        if new_prompt and new_prompt != shot.image_prompt:
            shot.image_prompt = new_prompt
            updated += 1

    await db.commit()
    return {"updated": updated}


# 步骤执行器映射
STEP_EXECUTORS = {
    "script_generation": _step_script_generation,
    "entity_extraction": _step_entity_extraction,
    "storyboard_split": _step_storyboard_split,
    "frame_prompt_extract": _step_frame_prompt_extract,
}


async def run_wizard(
    db: AsyncSession,
    project: Project,
    wizard_chain: List[dict],
    inputs: dict,
    resume_from: str = "",
) -> Project:
    """
    执行项目创建向导 LLM 链

    参数:
    - project: 项目对象（status=creating）
    - wizard_chain: 向导链配置
    - inputs: 用户输入参数
    - resume_from: 从指定 step key 恢复（空字符串表示从头开始）
    """
    context = {"inputs": inputs}
    started = not resume_from

    for step in wizard_chain:
        step_key = step["key"]
        if not started:
            if step_key == resume_from:
                started = True
            else:
                continue

        await project_sse_manager.push(project.id, "wizard_step_started", {
            "step": step_key, "name": step.get("name", step_key)
        })

        executor = STEP_EXECUTORS.get(step_key)
        if not executor:
            # 未知步骤类型，跳过
            continue

        # 重试 2 次
        last_err = None
        for attempt in range(2):
            try:
                result = await executor(db, project, step.get("config", step), context)
                context[step_key] = result
                await project_sse_manager.push(project.id, "wizard_step_completed", {
                    "step": step_key, "stats": result
                })
                last_err = None
                break
            except Exception as e:
                last_err = e
                logger.warning(f"向导步骤 {step_key} 第 {attempt+1} 次失败: {e}")

        if last_err:
            await project_sse_manager.push(project.id, "wizard_step_failed", {
                "step": step_key, "error": str(last_err)
            })
            # 部分成功保留，不中断向导
            logger.error(f"向导步骤 {step_key} 最终失败: {last_err}")

    # 向导完成，状态 → in_progress
    project.status = PROJECT_STATUS_IN_PROGRESS
    await db.commit()
    await db.refresh(project)

    await project_sse_manager.push(project.id, "wizard_completed", {
        "project_id": project.id, "status": "in_progress"
    })
    return project
```

- [ ] **Step 2: 提交**

```bash
git add backend/app/services/project/wizard.py
git commit -m "feat(project): 新增项目创建向导（4 步 LLM 链）"
```

---

## Task 6: 实体服务层（角色/场景/道具/分镜/帧图/视频）

**Files:**
- Create: `backend/app/services/project/character_service.py`
- Create: `backend/app/services/project/scene_service.py`
- Create: `backend/app/services/project/prop_service.py`
- Create: `backend/app/services/project/shot_service.py`
- Create: `backend/app/services/project/frame_image_service.py`
- Create: `backend/app/services/project/video_service.py`
- Create: `backend/app/services/project/script_service.py`

- [ ] **Step 1: 创建 script_service.py**

实现剧本 CRUD + 重生成（调用 LLM）。

- [ ] **Step 2: 创建 character_service.py**

实现角色 CRUD + 单个生图 + 批量生图 + 上传替换 + 版本切换 + 删除版本 + 从剧本提取。

关键函数：
- `list_characters(db, project_id)`
- `get_character(db, character_id)`
- `create_character(db, project_id, data)`
- `update_character(db, character_id, data)`
- `delete_character(db, character_id)`
- `reorder_characters(db, project_id, character_ids)`
- `generate_character_image(db, character_id, user_id, style_config)` — 调用 agnes_client.create_image，写入 project_entity_assets 新版本
- `batch_generate_characters(db, project_ids, user_id, style_config)` — 批量入队
- `upload_character_image(db, character_id, user_id, file)` — 上传作为新版本
- `set_active_version(db, entity_type, entity_id, version_id)` — 切换采用版
- `list_versions(db, entity_type, entity_id)`
- `delete_version(db, entity_type, entity_id, version_id)`
- `extract_characters_from_script(db, project_id)` — 从剧本重新提取（追加，不覆盖）

- [ ] **Step 3: 创建 scene_service.py**

与 character_service 同构，仅表名和字段不同（location/time_of_day/atmosphere）。

- [ ] **Step 4: 创建 prop_service.py**

与 character_service 同构，仅表名和字段不同（visual_desc）。

- [ ] **Step 5: 创建 shot_service.py**

实现分镜 CRUD + 绑定实体 + 重排 + 帧 prompt 提取。

关键函数：
- `list_shots(db, project_id)` — 含关联的角色/场景/道具
- `get_shot(db, shot_id)`
- `create_shot(db, project_id, data)`
- `update_shot(db, shot_id, data)` — 检测 affected_fields 并推送 SSE
- `delete_shot(db, shot_id)`
- `reorder_shots(db, project_id, shot_ids)`
- `bind_character(db, shot_id, character_id)` / `unbind_character`
- `bind_prop(db, shot_id, prop_id)` / `unbind_prop`
- `generate_frame_prompt(db, shot_id)` — 单个分镜的帧 prompt 提取
- `split_shots_from_script(db, project_id)` — 从剧本 AI 拆分分镜（E2）

- [ ] **Step 6: 创建 frame_image_service.py**

实现帧图多版本 + 生成 + 上传。

关键函数：
- `list_frame_images(db, shot_id)`
- `generate_frame_image(db, shot_id, user_id, style_config)` — 注入角色参考图
- `batch_generate_frame_images(db, shot_ids, user_id, style_config)`
- `upload_frame_image(db, shot_id, user_id, file)`
- `set_active_frame_image(db, shot_id, version_id)`
- `delete_frame_image(db, shot_id, version_id)`

- [ ] **Step 7: 创建 video_service.py**

实现视频多版本 + 生成 + 上传。

关键函数：
- `list_videos(db, shot_id)`
- `generate_video(db, shot_id, user_id, frame_image_id=None)` — 基于采用帧图
- `upload_video(db, shot_id, user_id, file)`
- `set_active_video(db, shot_id, version_id)`
- `delete_video(db, shot_id, version_id)`

- [ ] **Step 8: 提交**

```bash
git add backend/app/services/project/
git commit -m "feat(project): 新增实体服务层（剧本/角色/场景/道具/分镜/帧图/视频）"
```

---

## Task 7: 资产桥接 + 画布桥接 + 简单合成

**Files:**
- Create: `backend/app/services/project/asset_bridge.py`
- Create: `backend/app/services/project/canvas_bridge.py`
- Create: `backend/app/services/project/merge_service.py`

- [ ] **Step 1: 创建 asset_bridge.py**

实现 C2 引用模式：
- `import_asset_to_project(db, asset_id, project_id, user_id)` — 资产库 → 项目实体
- `promote_entity_to_asset(db, entity_type, entity_id, user_id)` — 项目实体 → 资产库（走审核）

- [ ] **Step 2: 创建 canvas_bridge.py**

实现画布布局生成：
- `init_canvas_layout(db, project_id)` — 自动按生成依赖布局节点
- `get_canvas_data(db, project_id)` — 获取画布数据
- `save_canvas_data(db, project_id, canvas_data)` — 保存画布布局

- [ ] **Step 3: 创建 merge_service.py**

实现简单合成（按分镜顺序拼接 + 默认转场）：
- `merge_project(db, project_id, user_id)` — 入队异步合成
- `execute_merge(project_id)` — 实际执行 ffmpeg 合成（复用现有 ffmpeg_composite 逻辑）

- [ ] **Step 4: 提交**

```bash
git add backend/app/services/project/
git commit -m "feat(project): 新增资产桥接/画布桥接/简单合成"
```

---

## Task 8: 后端路由 routes/projects.py

**Files:**
- Create: `backend/app/routes/projects.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: 创建 routes/projects.py**

实现 spec 第 9 节所有 API 端点，使用 FastAPI APIRouter。

路由分组：
- 项目 CRUD：`POST /projects`, `GET /projects`, `GET /projects/{id}`, `PATCH /projects/{id}`, `DELETE /projects/{id}`, `POST /projects/{id}/archive`, `PATCH /projects/{id}/active-view`
- 向导：`POST /projects/wizard`, `POST /projects/{id}/wizard/resume`
- SSE：`GET /projects/{id}/events`
- 剧本：`GET/POST /projects/{id}/scripts`, `GET/PATCH/DELETE /projects/{id}/scripts/{sid}`, `POST /projects/{id}/scripts/{sid}/regenerate`
- 角色/场景/道具：统一模式（参考 spec 9.3）
- 分镜：`GET/POST /projects/{id}/shots`, `POST /projects/{id}/shots/split`, `GET/PATCH/DELETE /projects/{id}/shots/{sid}`, `PATCH /projects/{id}/shots/reorder`, `POST /projects/{id}/shots/{sid}/bind-character`, `POST /projects/{id}/shots/{sid}/bind-prop`
- 帧图：`GET/POST /projects/{id}/shots/{sid}/frame-images/...`
- 视频：`GET/POST /projects/{id}/shots/{sid}/videos/...`
- 画布：`GET/POST/PATCH /projects/{id}/canvas/...`
- 合成：`POST /projects/{id}/merge`

所有路由使用 `db: AsyncSession = Depends(get_async_db)` 和 `current_user = Depends(get_current_user)`。

SSE 路由使用 `StreamingResponse` + `project_sse_manager.subscribe()`。

- [ ] **Step 2: 注册路由到 main.py**

在 `backend/app/main.py` 中：
1. 添加 `from app.routes import projects as projects_route`
2. 添加 `app.include_router(projects_route.router, prefix="/api", tags=["项目制创作"])`

- [ ] **Step 3: 验证路由加载**

Run: `cd /Users/skywing/agnes-platform/backend && python -c "from app.routes.projects import router; print(f'路由数: {len(router.routes)}')"`
Expected: 路由数 > 30

- [ ] **Step 4: 提交**

```bash
git add backend/app/routes/projects.py backend/app/main.py
git commit -m "feat(project): 新增项目制创作 API 路由"
```

---

## Task 9: 改造模板场景为 wizard_chain

**Files:**
- Modify: `backend/app/services/pipeline/template_scenarios.py`
- Modify: `backend/app/services/pipeline/template_service.py`

- [ ] **Step 1: 改造 template_scenarios.py**

将 `steps_config_template` 改为 `wizard_chain` 结构（参考 spec 4.3 节）：

```python
"wizard_chain": [
    {
        "key": "script_generation",
        "name": "剧本生成",
        "type": "llm_generate",
        "config": {
            "prompt_template": "根据主题{topic}生成剧本...",
            "model": "agnes-2.0-flash",
            "temperature": 0.8,
        },
        "output_target": "project_scripts",
    },
    {
        "key": "entity_extraction",
        "name": "实体提取",
        "type": "llm_generate",
        "config": {
            "prompt_template": "从剧本提取角色/场景/道具清单...",
            "model": "agnes-2.0-flash",
            "temperature": 0.5,
        },
        "output_target": "project_characters+project_scenes+project_props",
        "depends_on": ["script_generation"],
    },
    {
        "key": "storyboard_split",
        "name": "分镜拆分",
        "type": "llm_generate",
        "config": {
            "prompt_template": "基于剧本+实体清单拆分分镜...",
            "model": "agnes-2.0-flash",
            "temperature": 0.6,
        },
        "output_target": "project_shots",
        "depends_on": ["entity_extraction"],
    },
    {
        "key": "frame_prompt_extract",
        "name": "帧 prompt 提取",
        "type": "llm_generate",
        "config": {
            "prompt_template": "为每个分镜提取帧级绘画 prompt...",
            "model": "agnes-2.0-flash",
            "temperature": 0.5,
        },
        "output_target": "project_shots.image_prompt",
        "depends_on": ["storyboard_split"],
    },
]
```

对 drama/ad/education/anime 四个预设都进行改造。

- [ ] **Step 2: 适配 template_service.py**

确保模板创建/更新时支持 `wizard_chain` 字段（存储在 `steps_config` JSON 字段内，兼容现有表结构）。

- [ ] **Step 3: 提交**

```bash
git add backend/app/services/pipeline/template_scenarios.py backend/app/services/pipeline/template_service.py
git commit -m "refactor(project): 模板场景改造为 wizard_chain 结构"
```

---

## Task 10: 清理旧 Pipeline 代码

**Files:**
- Delete: `backend/app/services/pipeline/engine.py`
- Delete: `backend/app/services/pipeline/run_service.py`
- Delete: `backend/app/services/pipeline/integration.py`
- Delete: `backend/app/services/pipeline/post_process_service.py`
- Delete: `backend/app/services/pipeline/moderation_service.py`
- Delete: `backend/app/services/pipeline/template_validate.py`
- Delete: `backend/app/services/pipeline/steps/`（保留 ffmpeg_composite.py 和 transition_compose.py，移动到 `services/project/`）
- Delete: `backend/app/models/pipeline_step_output_revision.py`
- Modify: `backend/app/models/pipeline.py`（删除 PipelineRun/PipelineStep 类）
- Modify: `backend/app/models/__init__.py`（移除旧模型导入）
- Modify: `backend/app/routes/pipeline.py`（删除 runs/steps 路由，保留模板路由）

- [ ] **Step 1: 移动 ffmpeg_composite.py 和 transition_compose.py 到 services/project/**

- [ ] **Step 2: 删除旧服务文件**

- [ ] **Step 3: 改造 pipeline.py 模型，删除 PipelineRun/PipelineStep 类**

- [ ] **Step 4: 改造 routes/pipeline.py，删除 runs/steps 路由**

- [ ] **Step 5: 验证后端启动**

Run: `cd /Users/skywing/agnes-platform/backend && python -c "from app.main import app; print(f'路由数: {len(app.routes)}')"`
Expected: 正常加载

- [ ] **Step 6: 提交**

```bash
git add -A
git commit -m "refactor(project): 删除旧 PipelineRun/Step 代码，保留模板"
```

---

## Task 11: 前端类型定义 + API + Store

**Files:**
- Create: `frontend/src/types/project.ts`
- Create: `frontend/src/api/projects.ts`
- Create: `frontend/src/stores/project.ts`
- Create: `frontend/src/composables/useProjectSSE.ts`

- [ ] **Step 1: 创建 types/project.ts**

定义所有 TypeScript 接口：Project, Script, Character, Scene, Prop, Shot, FrameImage, Video, EntityAsset, WizardEvent 等。

- [ ] **Step 2: 创建 api/projects.ts**

封装所有项目 API 调用，使用现有 axios 实例。

- [ ] **Step 3: 创建 stores/project.ts**

Pinia store，管理：
- `project` / `scripts` / `characters` / `scenes` / `props` / `shots`
- `activeView` / `loading` / `generatingIds`
- `sseConnection`
- 所有逐个适配动作（loadProject, generateCharacterImage, batchGenerate, setActiveVersion, uploadImage, etc.）

- [ ] **Step 4: 创建 composables/useProjectSSE.ts`

封装 EventSource 订阅，处理 wizard_step_started/completed/failed、entity_image_generated、frame_image_generated、shot_video_generated、shot_edited、shots_reordered、generation_failed 等事件。

- [ ] **Step 5: 提交**

```bash
git add frontend/src/types/project.ts frontend/src/api/projects.ts frontend/src/stores/project.ts frontend/src/composables/useProjectSSE.ts
git commit -m "feat(project): 新增前端类型/API/Store/SSE"
```

---

## Task 12: 前端项目页面 + 组件

**Files:**
- Create: `frontend/src/views/projects/ProjectListView.vue`
- Create: `frontend/src/views/projects/ProjectDetailView.vue`
- Create: `frontend/src/components/project/ProjectHeader.vue`
- Create: `frontend/src/components/project/ProjectManagerView.vue`
- Create: `frontend/src/components/project/ProjectCanvasView.vue`
- Create: `frontend/src/components/project/ScriptTab.vue`
- Create: `frontend/src/components/project/CharactersTab.vue`
- Create: `frontend/src/components/project/ScenesTab.vue`
- Create: `frontend/src/components/project/PropsTab.vue`
- Create: `frontend/src/components/project/ShotsTab.vue`
- Create: `frontend/src/components/project/CharacterCard.vue`
- Create: `frontend/src/components/project/ShotCard.vue`
- Create: `frontend/src/components/project/EntityVersionSwitcher.vue`
- Create: `frontend/src/components/project/EntityEditDialog.vue`
- Create: `frontend/src/components/project/ProjectLaunchDialog.vue`

- [ ] **Step 1: 创建 ProjectListView.vue**

项目列表页，展示用户所有项目，支持创建新项目（弹出 ProjectLaunchDialog）。

- [ ] **Step 2: 创建 ProjectLaunchDialog.vue**

改造自 PipelineLaunchDialog.vue，选模板 + 填参数 + 触发向导创建。

- [ ] **Step 3: 创建 ProjectDetailView.vue**

项目详情页，含：
- ProjectHeader（标题/状态/视图切换/合成按钮）
- 视图切换：ProjectManagerView / ProjectCanvasView
- SSE 订阅 + 局部更新

- [ ] **Step 4: 创建 ProjectManagerView.vue**

Tab 容器：剧本 / 角色 / 场景 / 道具 / 分镜。

- [ ] **Step 5: 创建各 Tab 组件**

ScriptTab / CharactersTab / ScenesTab / PropsTab / ShotsTab，每个 Tab 含卡片网格 + 多选批量 + 单个操作。

- [ ] **Step 6: 创建 CharacterCard.vue 和 ShotCard.vue**

参考 LingGuo-Drama `detail.vue` 的卡片范式：预览图 + 生成中遮罩 + AI 生成/编辑/上传/删除/多选/版本切换器。

- [ ] **Step 7: 创建 EntityVersionSwitcher.vue 和 EntityEditDialog.vue**

版本切换器：展示所有版本，点击切换采用版。
编辑对话框：编辑实体名称/描述/prompt 等。

- [ ] **Step 8: 创建 ProjectCanvasView.vue**

复用 InfiniteCanvas.vue，新增"项目画布"模式，从项目实体生成节点。

- [ ] **Step 9: 提交**

```bash
git add frontend/src/views/projects/ frontend/src/components/project/
git commit -m "feat(project): 新增前端项目页面和组件"
```

---

## Task 13: 前端路由 + 菜单 + 清理旧代码

**Files:**
- Modify: `frontend/src/router/index.ts`
- Modify: `frontend/src/config/menus.ts`
- Modify: `frontend/src/views/WorkshopView.vue`
- Delete: `frontend/src/views/PipelineHistoryView.vue`
- Delete: `frontend/src/views/PipelineRunView.vue`
- Delete: `frontend/src/views/PipelineResultView.vue`
- Delete: `frontend/src/components/pipeline/StepList.vue`
- Delete: `frontend/src/components/pipeline/StepPanel.vue`
- Delete: `frontend/src/stores/pipeline.ts`
- Delete: `frontend/src/composables/usePipelineSSE.ts`

- [ ] **Step 1: 改造路由**

新增：
- `/projects` → ProjectListView
- `/projects/:id` → ProjectDetailView

废弃：`/pipeline/runs/:id`, `/pipeline/history`, `/pipeline/results/:id`

- [ ] **Step 2: 改造菜单**

参考 spec 12.3 节，新增"我的项目"菜单项，废弃"创意流水线"。

- [ ] **Step 3: 改造 WorkshopView.vue**

改为模板市场入口，点击模板触发 ProjectLaunchDialog。

- [ ] **Step 4: 删除旧前端代码**

- [ ] **Step 5: 验证前端启动**

Run: `cd /Users/skywing/agnes-platform/frontend && npm run build`
Expected: 构建成功

- [ ] **Step 6: 提交**

```bash
git add -A
git commit -m "refactor(project): 前端路由/菜单调整，清理旧 Pipeline 代码"
```

---

## Self-Review

**1. Spec 覆盖检查：**

| Spec 章节 | 对应 Task |
|----------|----------|
| 4. 数据模型（11 张表） | Task 1 |
| 5. 引导式生成流程 | Task 5 |
| 6. 逐个适配机制 | Task 6 |
| 6.5. 资产互转（C2） | Task 7 |
| 6.6. SSE 推送 | Task 3 |
| 7. 时间线（Phase 2） | 不在本计划（Phase 2） |
| 8. 画布双视图（J4） | Task 12（基础版）, Task 7（canvas_bridge） |
| 9. API 设计 | Task 8 |
| 10. 前端架构 | Task 11, 12, 13 |
| 12. 迁移策略（K1） | Task 10 |
| 4.3. 模板改造（L1） | Task 9 |

**2. 类型一致性：** 模型字段名、服务函数签名、API 路径在各个 Task 间保持一致。

**3. 占位符扫描：** 无 TBD/TODO，每个步骤都有具体代码或明确指令。

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-07-05-project-based-creation-refactor.md`. Two execution options:**

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
