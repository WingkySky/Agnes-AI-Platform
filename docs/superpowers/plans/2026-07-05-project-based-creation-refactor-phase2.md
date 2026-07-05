# 项目制创作重构 — Phase 2 实现计划（时间线 + TTS + 字幕）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为项目制创作补齐"配音 + 字幕 + 多轨时间线编辑器 + 多轨合成"完整链路，对齐 LingGuo-Drama 的 VideoTimelineEditor 能力，让项目详情页成为完整的短剧创作入口。

**Architecture:** 后端新增 3 张表（audios / character_voices / timeline_clips）+ 3 个服务（audio_service / subtitle_service / timeline_service）+ 扩展 merge_service 支持多轨合成。前端新增 TimelineEditor 组件群 + 集成为 ProjectManagerView 的第 6 个 Tab。

**Tech Stack:** FastAPI + SQLAlchemy async + httpx.AsyncClient + ffmpeg（xfade/subtitles 滤镜）+ Vue 3 + Pinia + Element Plus

**Spec:** [docs/superpowers/specs/2026-07-05-project-based-creation-refactor-design.md](file:///Users/skywing/agnes-platform/docs/superpowers/specs/2026-07-05-project-based-creation-refactor-design.md)（第 7 节）

**Phase 1 计划:** [docs/superpowers/plans/2026-07-05-project-based-creation-refactor.md](file:///Users/skywing/agnes-platform/docs/superpowers/plans/2026-07-05-project-based-creation-refactor.md)（已完成的 13 个 Task）

**LingGuo-Drama 参考:** [VideoTimelineEditor.vue](https://github.com/LingGuoAI/LingGuo-Drama/blob/main/web/src/components/editor/VideoTimelineEditor.vue)

---

## 现状盘点（Phase 1 已实现 / Phase 2 缺失）

### Phase 1 已实现

- `merge_service.py`：仅做 ffmpeg concat（`-c copy` 按分镜顺序拼接视频，无音频/字幕混入）
- `ProjectShot.active_audio_id` 字段已预留（注释 Phase 2）
- `Project.timeline_data` JSON 字段已预留（当前为空 dict）
- 前端 SSE 已支持 `merge_progress` / `merge_completed` 事件

### Phase 2 缺失（本计划补齐）

- **数据表**：`project_shot_audios` / `project_character_voices` / `project_timeline_clips` 未创建
- **服务**：`audio_service.py` / `subtitle_service.py` / `timeline_service.py` 未创建
- **合成**：`merge_service.execute_merge` 不支持音频混入、字幕烧录、时间线顺序
- **前端**：无 TimelineEditor 组件，ProjectManagerView 只有 5 个 Tab（剧本/角色/场景/道具/分镜）
- **类型**：`TimelineClip` / `ProjectShotAudio` 等类型未定义，`ProjectShot.active_audio_id` 在前端类型中缺失

### 关键风险点

1. **Agnes AI TTS API 未知** — 本计划采用**可插拔 TTS provider 模式**，先实现接口骨架，具体 provider（Agnes 自有 / 阿里云 / 字节火山）后续适配。若 Agnes 无 TTS，可通过 `provider_registry` 路由到第三方。
2. **`pipeline/steps` 已删除** — ffmpeg 合成逻辑需在 `merge_service.py` 内独立实现（不复用旧代码）。
3. **时间线数据结构未定义** — `timeline_data` JSON 需设计完整的轨道/片段 schema。

---

## 文件结构映射

### 后端新增

| 文件 | 职责 |
|------|------|
| `backend/app/services/project/audio_service.py` | TTS 配音生成 + 音色分配 + 多版本管理 |
| `backend/app/services/project/subtitle_service.py` | 字幕生成（LLM 生成 SRT）+ 字幕样式 |
| `backend/app/services/project/timeline_service.py` | 时间线 CRUD + 自动初始化 + 解析 |

### 后端改造

| 文件 | 改造内容 |
|------|---------|
| `backend/app/models/project.py` | 新增 `ProjectShotAudio` / `ProjectCharacterVoice` / `ProjectTimelineClip` 三个模型 |
| `backend/app/models/__init__.py` | 注册三个新模型 |
| `backend/app/schemas/project.py` | 新增 TTS/字幕/时间线相关 Schema |
| `backend/app/services/project/merge_service.py` | 扩展 `execute_merge` 支持音频混入 + 字幕烧录 + 时间线顺序 |
| `backend/app/services/agnes_client.py` | 新增 `create_tts_task` 方法（若 Agnes 支持，否则走 provider_registry） |
| `backend/app/routes/projects.py` | 新增 TTS/字幕/时间线 API 端点 |
| `backend/init_db.py` | 注册新模型导入 |

### 前端新增

| 文件 | 职责 |
|------|------|
| `frontend/src/components/project/TimelineTab.vue` | 时间线 Tab 容器（集成到 ProjectManagerView） |
| `frontend/src/components/project/timeline/TimelineEditor.vue` | 时间线编辑器主组件（轨道区 + 工具栏 + 播放头） |
| `frontend/src/components/project/timeline/TimelineTrack.vue` | 单个轨道组件（视频/音频/字幕） |
| `frontend/src/components/project/timeline/TimelineClip.vue` | 单个片段组件（拖拽 + 裁剪 + 转场） |
| `frontend/src/components/project/timeline/TimelineToolbar.vue` | 工具栏（播放/暂停/添加片段/字幕样式/合成） |
| `frontend/src/components/project/timeline/ClipPropertyPanel.vue` | 片段属性面板（起始/时长/裁剪/转场） |
| `frontend/src/components/project/timeline/SubtitleStyleDialog.vue` | 字幕样式设置对话框 |
| `frontend/src/components/project/timeline/VoicePickerDialog.vue` | 音色选择对话框 |

### 前端改造

| 文件 | 改造内容 |
|------|---------|
| `frontend/src/types/project.ts` | 新增 `TimelineClip` / `TimelineTrack` / `ProjectShotAudio` / `CharacterVoice` 等类型；补齐 `ProjectShot.active_audio_id` |
| `frontend/src/api/projects.ts` | 新增 TTS/字幕/时间线 API 函数 |
| `frontend/src/stores/project.ts` | 新增 `audios` / `timeline` 状态 + TTS/字幕/时间线 actions |
| `frontend/src/composables/useProjectSSE.ts` | 监听 `tts_progress` / `tts_completed` / `subtitle_progress` / `subtitle_completed` 事件 |
| `frontend/src/components/project/ProjectManagerView.vue` | 新增第 6 个 Tab `<el-tab-pane name="timeline">` |
| `frontend/src/i18n/zh-CN.ts` + `en-US.ts` | 新增时间线/TTS/字幕相关 i18n 键 |

---

## Task 1: 数据模型层 — 新增 3 张表

**Files:**
- Modify: `backend/app/models/project.py`
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/init_db.py`

- [ ] **Step 1: 在 project.py 末尾新增 ProjectShotAudio 模型**

参考 spec 4.2.10 节，结构对齐 `ProjectShotVideo`（多版本管理）：

```python
class ProjectShotAudio(Base):
    """分镜配音多版本表（TTS 生成或用户上传）"""
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
```

- [ ] **Step 2: 新增 ProjectCharacterVoice 模型**

参考 spec 4.2.11 节，角色-音色映射（保证同角色同声音）：

```python
class ProjectCharacterVoice(Base):
    """角色-音色映射表（同角色同声音）"""
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
```

- [ ] **Step 3: 新增 ProjectTimelineClip 模型**

参考 spec 4.2.12 节，时间线片段（多轨）：

```python
class ProjectTimelineClip(Base):
    """时间线片段表（多轨：video/audio/subtitle）"""
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
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
```

- [ ] **Step 4: 在 ProjectShot 模型中补全 audios 反向关系**

在 `ProjectShot` 类的 relationship 区块新增：

```python
audios = relationship("ProjectShotAudio", back_populates="shot", cascade="all, delete-orphan")
```

在 `ProjectCharacter` 类的 relationship 区块新增：

```python
voice_assignments = relationship("ProjectCharacterVoice", back_populates="character", cascade="all, delete-orphan")
```

- [ ] **Step 5: 在 models/__init__.py 注册新模型**

```python
from app.models.project import (
    # ... 已有导入 ...
    ProjectShotAudio,
    ProjectCharacterVoice,
    ProjectTimelineClip,
)
```

- [ ] **Step 6: 在 init_db.py 注册新模型导入**

在 `_safe_import` 调用列表中追加三个新模型。

- [ ] **Step 7: 验证模型加载**

Run: `cd /Users/skywing/agnes-platform/backend && source .venv/bin/activate && python -c "from app.models.project import ProjectShotAudio, ProjectCharacterVoice, ProjectTimelineClip; print('OK')"`
Expected: `OK`

- [ ] **Step 8: 提交**

```bash
git add backend/app/models/project.py backend/app/models/__init__.py backend/init_db.py
git commit -m "feat(project-phase2): 新增配音/音色映射/时间线片段数据模型（3 张表）"
```

---

## Task 2: Pydantic Schema 层

**Files:**
- Modify: `backend/app/schemas/project.py`

- [ ] **Step 1: 新增音频相关 Schema**

```python
class ProjectShotAudioResponse(BaseModel):
    """分镜配音响应"""
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
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class GenerateTTSRequest(BaseModel):
    """TTS 配音生成请求"""
    voice_id: Optional[str] = None  # 不传则自动分配（同角色同声音）
    character_id: Optional[int] = None  # 关联角色（用于音色固定）
    text: Optional[str] = None  # 不传则用 shot.dialogue
    model: Optional[str] = None
    provider: Optional[str] = None


class BatchGenerateTTSRequest(BaseModel):
    """批量 TTS 生成"""
    shot_ids: List[int]
    voice_id: Optional[str] = None


class UploadAudioRequest(BaseModel):
    """上传音频（用户手动上传配音替代 TTS）"""
    # 文件通过 UploadFile 接收，此 schema 仅用于元数据
    pass


class SetActiveAudioRequest(BaseModel):
    version_id: int
```

- [ ] **Step 2: 新增音色映射 Schema**

```python
class CharacterVoiceResponse(BaseModel):
    """角色-音色映射响应"""
    id: int
    project_id: int
    character_id: int
    voice_id: str
    voice_name: Optional[str] = None
    assigned_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AssignCharacterVoiceRequest(BaseModel):
    """为角色分配音色"""
    voice_id: str
    voice_name: Optional[str] = None


class VoiceOption(BaseModel):
    """内置音色选项"""
    voice_id: str
    name: str
    gender: str  # male/female/neutral
    suitable_for: str  # 适用角色描述
```

- [ ] **Step 3: 新增字幕相关 Schema**

```python
class GenerateSubtitleRequest(BaseModel):
    """从分镜对白生成字幕"""
    shot_ids: Optional[List[int]] = None  # 不传则全部有对白的分镜
    style: Optional[Dict[str, Any]] = None  # 字幕样式


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
```

- [ ] **Step 4: 新增时间线相关 Schema**

```python
class TimelineClipResponse(BaseModel):
    """时间线片段响应"""
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
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


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
    # 其他草稿字段（如轨道顺序、折叠状态等）
    draft: Optional[Dict[str, Any]] = None


class TimelineDataResponse(BaseModel):
    """时间线数据响应"""
    clips: List[TimelineClipResponse]
    subtitle_style: Optional[Dict[str, Any]] = None
    total_duration: float
```

- [ ] **Step 5: 验证 Schema 加载**

Run: `cd /Users/skywing/agnes-platform/backend && source .venv/bin/activate && python -c "from app.schemas.project import ProjectShotAudioResponse, GenerateTTSRequest, TimelineClipResponse; print('OK')"`
Expected: `OK`

- [ ] **Step 6: 提交**

```bash
git add backend/app/schemas/project.py
git commit -m "feat(project-phase2): 新增 TTS/字幕/时间线 Pydantic Schema"
```

---

## Task 3: TTS 配音服务

**Files:**
- Create: `backend/app/services/project/audio_service.py`
- Modify: `backend/app/services/agnes_client.py`（新增 `create_tts_task` 方法，若 Agnes 支持）

- [ ] **Step 1: 创建 audio_service.py 骨架**

实现 TTS 生成 + 音色分配 + 多版本管理，参考 `video_service.py` 的结构：

```python
# =====================================================
# 分镜配音服务 — TTS 生成 + 音色分配 + 多版本管理
#
# 核心能力:
#   1. generate_audio: 单个分镜 TTS 生成（自动分配音色或指定音色）
#   2. batch_generate_audios: 批量 TTS 生成（每分镜独立任务）
#   3. upload_audio: 用户上传音频替代 TTS
#   4. set_active_audio: 设为采用版
#   5. assign_character_voice: 为角色固定音色（同角色同声音）
#
# 音色分配策略（参考 LingGuo-Drama）:
#   - 优先使用角色已分配的音色（project_character_voices）
#   - 未分配时按 role_type 推断：main→narrator_male/female，supporting→young_male/female
#   - 旁白（无角色）使用 default_narrator
# =====================================================

import asyncio
import logging
from typing import Optional, List

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import (
    ProjectShot, ProjectShotAudio, ProjectShotCharacter,
    ProjectCharacter, ProjectCharacterVoice,
)
from app.services.project.sse_manager import project_sse_manager
from app.services.project._entity_versions import get_next_version

logger = logging.getLogger("agnes_platform.project.audio")


# =====================================================
# 内置音色库（spec 7.4.2 节）
# 实际 provider 支持的音色 ID 在运行时由 provider 决定，
# 此处仅作为"默认分配策略"的候选清单。
# =====================================================
BUILTIN_VOICES = [
    {"voice_id": "narrator_male_zh",   "name": "男声旁白",   "gender": "male",    "suitable_for": "旁白、男主"},
    {"voice_id": "narrator_female_zh", "name": "女声旁白",   "gender": "female",  "suitable_for": "旁白、女主"},
    {"voice_id": "young_male_zh",      "name": "年轻男声",   "gender": "male",    "suitable_for": "年轻男主"},
    {"voice_id": "young_female_zh",    "name": "年轻女声",   "gender": "female",  "suitable_for": "年轻女主"},
    {"voice_id": "mature_male_zh",     "name": "成熟男声",   "gender": "male",    "suitable_for": "成熟男性"},
    {"voice_id": "mature_female_zh",   "name": "成熟女声",   "gender": "female",  "suitable_for": "成熟女性"},
    {"voice_id": "child_zh",           "name": "童声",       "gender": "neutral", "suitable_for": "儿童"},
    {"voice_id": "elder_zh",           "name": "老年声",     "gender": "neutral", "suitable_for": "老年"},
]


def list_builtin_voices() -> List[dict]:
    """返回内置音色清单（供前端音色选择器）"""
    return BUILTIN_VOICES.copy()


async def _resolve_voice_for_shot(
    db: AsyncSession, shot: ProjectShot, character_id: Optional[int] = None
) -> tuple[Optional[str], Optional[str], Optional[int]]:
    """
    解析分镜的音色（同角色同声音策略）

    返回: (voice_id, voice_name, character_id)
    """
    # 1. 优先使用角色已分配的音色
    if character_id:
        assignment = (await db.execute(
            select(ProjectCharacterVoice).where(
                ProjectCharacterVoice.character_id == character_id
            )
        )).scalar_one_or_none()
        if assignment:
            return assignment.voice_id, assignment.voice_name, character_id

    # 2. 取分镜绑定的主角色的 role_type 推断音色
    if not character_id:
        char_links = (await db.execute(
            select(ProjectShotCharacter)
            .where(ProjectShotCharacter.shot_id == shot.id)
            .order_by(ProjectShotCharacter.sort_order)
        )).scalars().all()
        if char_links:
            # 取第一个角色（按 sort_order）
            first_char = (await db.execute(
                select(ProjectCharacter).where(ProjectCharacter.id == char_links[0].character_id)
            )).scalar_one_or_none()
            if first_char:
                character_id = first_char.id
                # 查已分配音色
                assignment = (await db.execute(
                    select(ProjectCharacterVoice).where(
                        ProjectCharacterVoice.character_id == character_id
                    )
                )).scalar_one_or_none()
                if assignment:
                    return assignment.voice_id, assignment.voice_name, character_id
                # 按 role_type 推断
                voice_id = _infer_voice_by_role(first_char.role_type, first_char.description or "")
                return voice_id, _get_voice_name(voice_id), character_id

    # 3. 无角色 → 默认旁白
    return "narrator_male_zh", "男声旁白", None


def _infer_voice_by_role(role_type: str, description: str = "") -> str:
    """根据角色类型和描述推断音色"""
    desc = (description or "").lower()
    if "女" in desc or "female" in desc or "girl" in desc:
        return "young_female_zh" if role_type == "main" else "narrator_female_zh"
    if "男" in desc or "male" in desc or "boy" in desc:
        return "young_male_zh" if role_type == "main" else "narrator_male_zh"
    # 默认男声
    return "narrator_male_zh"


def _get_voice_name(voice_id: str) -> Optional[str]:
    for v in BUILTIN_VOICES:
        if v["voice_id"] == voice_id:
            return v["name"]
    return None


async def generate_audio(
    db: AsyncSession,
    shot_id: int,
    user_id: int,
    voice_id: Optional[str] = None,
    character_id: Optional[int] = None,
    text: Optional[str] = None,
    model: Optional[str] = None,
    provider: Optional[str] = None,
) -> ProjectShotAudio:
    """
    为分镜生成 TTS 配音

    1. 解析音色（同角色同声音）
    2. 取对白文本（shot.dialogue 或显式传入）
    3. 调用 TTS provider 生成音频
    4. 创建新版本记录（is_active=False）
    5. 推送 SSE
    """
    shot = (await db.execute(
        select(ProjectShot).where(ProjectShot.id == shot_id)
    )).scalar_one_or_none()
    if not shot:
        raise ValueError(f"分镜 {shot_id} 不存在")

    # 解析音色
    if not voice_id:
        voice_id, voice_name, resolved_char_id = await _resolve_voice_for_shot(db, shot, character_id)
    else:
        voice_name = _get_voice_name(voice_id)
        resolved_char_id = character_id

    if not voice_id:
        raise ValueError("无法解析音色，请显式指定 voice_id")

    # 解析文本
    tts_text = text or shot.dialogue
    if not tts_text:
        raise ValueError("分镜无对白文本，无法生成配音")

    # 调用 TTS provider 生成音频
    # ⚠️ 可插拔 provider：优先走 provider_registry，回退到 agnes_client
    audio_url, duration_ms, file_size = await _call_tts_provider(
        text=tts_text,
        voice_id=voice_id,
        model=model,
        provider=provider,
    )

    # 创建新版本记录
    next_version = await get_next_version(db, "shot_audio", shot_id)
    audio = ProjectShotAudio(
        shot_id=shot_id,
        version=next_version,
        is_active=False,  # 用户手动切换
        is_manual=False,
        file_url=audio_url,
        text=tts_text,
        voice_id=voice_id,
        voice_name=voice_name,
        character_id=resolved_char_id,
        provider=provider or "agnes",
        model=model,
        duration_ms=duration_ms,
        file_size=file_size,
        created_by="ai",
    )
    db.add(audio)
    await db.commit()
    await db.refresh(audio)

    await project_sse_manager.push(shot.project_id, "tts_completed", {
        "shot_id": shot_id,
        "version": next_version,
        "audio_id": audio.id,
        "duration_ms": duration_ms,
    })
    return audio


async def _call_tts_provider(
    text: str,
    voice_id: str,
    model: Optional[str] = None,
    provider: Optional[str] = None,
) -> tuple[str, Optional[int], Optional[int]]:
    """
    调用 TTS provider 生成音频

    可插拔策略:
    1. 若 provider 显式指定，走 provider_registry 路由
    2. 否则尝试 agnes_client.create_tts_task
    3. 若 Agnes 不支持 TTS，抛出明确错误提示

    返回: (audio_url, duration_ms, file_size)
    """
    # TODO: 实现 1 — 通过 provider_registry 路由到支持 TTS 的 provider
    # TODO: 实现 2 — 调用 agnes_client.create_tts_task
    # 临时实现：抛出明确错误，提示需要配置 TTS provider
    raise NotImplementedError(
        "TTS provider 未配置。请在 provider_registry 中配置支持 TTS 的 provider，"
        "或在 agnes_client 中实现 create_tts_task 方法。"
    )


async def batch_generate_audios(
    db: AsyncSession,
    shot_ids: List[int],
    user_id: int,
    voice_id: Optional[str] = None,
) -> List[int]:
    """批量 TTS 生成 — 每分镜独立任务进队列"""
    task_ids: List[int] = []
    for shot_id in shot_ids:
        # 入队异步生成（复用 _async_gen 模式）
        from app.services.project._async_gen import submit_tts_task
        task_id = await submit_tts_task(shot_id, user_id, voice_id)
        task_ids.append(task_id)
    return task_ids


async def upload_audio(
    db: AsyncSession, shot_id: int, user_id: int, file_url: str,
    duration_ms: Optional[int] = None, file_size: Optional[int] = None,
) -> ProjectShotAudio:
    """用户上传音频替代 TTS"""
    shot = (await db.execute(select(ProjectShot).where(ProjectShot.id == shot_id))).scalar_one_or_none()
    if not shot:
        raise ValueError(f"分镜 {shot_id} 不存在")

    next_version = await get_next_version(db, "shot_audio", shot_id)
    audio = ProjectShotAudio(
        shot_id=shot_id,
        version=next_version,
        is_active=False,
        is_manual=True,
        file_url=file_url,
        text=shot.dialogue,
        created_by="manual",
        duration_ms=duration_ms,
        file_size=file_size,
    )
    db.add(audio)
    await db.commit()
    await db.refresh(audio)
    return audio


async def set_active_audio(db: AsyncSession, shot_id: int, version_id: int) -> ProjectShotAudio:
    """设置采用版音频"""
    # 1. 取消同分镜其他版本的 is_active
    await db.execute(
        update(ProjectShotAudio)
        .where(ProjectShotAudio.shot_id == shot_id, ProjectShotAudio.is_active == True)
        .values(is_active=False)
    )
    # 2. 设置目标版本 active
    audio = (await db.execute(
        select(ProjectShotAudio).where(ProjectShotAudio.id == version_id)
    )).scalar_one_or_none()
    if not audio:
        raise ValueError(f"音频版本 {version_id} 不存在")
    audio.is_active = True
    # 3. 更新分镜的 active_audio_id 指针
    shot = (await db.execute(select(ProjectShot).where(ProjectShot.id == shot_id))).scalar_one_or_none()
    if shot:
        shot.active_audio_id = audio.id
    await db.commit()
    await db.refresh(audio)

    await project_sse_manager.push(shot.project_id if shot else 0, "audio_activated", {
        "shot_id": shot_id, "version_id": version_id
    })
    return audio


async def list_audios(db: AsyncSession, shot_id: int) -> List[ProjectShotAudio]:
    """列出分镜的所有音频版本"""
    result = await db.execute(
        select(ProjectShotAudio)
        .where(ProjectShotAudio.shot_id == shot_id)
        .order_by(ProjectShotAudio.version)
    )
    return result.scalars().all()


async def delete_audio(db: AsyncSession, shot_id: int, version_id: int) -> bool:
    """删除音频版本"""
    audio = (await db.execute(
        select(ProjectShotAudio).where(ProjectShotAudio.id == version_id)
    )).scalar_one_or_none()
    if not audio:
        return False
    await db.delete(audio)
    await db.commit()
    return True


async def assign_character_voice(
    db: AsyncSession, project_id: int, character_id: int,
    voice_id: str, voice_name: Optional[str] = None,
) -> ProjectCharacterVoice:
    """为角色分配音色（同角色同声音）"""
    # upsert：已存在则更新，否则新建
    existing = (await db.execute(
        select(ProjectCharacterVoice).where(
            ProjectCharacterVoice.project_id == project_id,
            ProjectCharacterVoice.character_id == character_id,
        )
    )).scalar_one_or_none()

    if existing:
        existing.voice_id = voice_id
        existing.voice_name = voice_name or _get_voice_name(voice_id)
        await db.commit()
        await db.refresh(existing)
        return existing

    assignment = ProjectCharacterVoice(
        project_id=project_id,
        character_id=character_id,
        voice_id=voice_id,
        voice_name=voice_name or _get_voice_name(voice_id),
    )
    db.add(assignment)
    await db.commit()
    await db.refresh(assignment)
    return assignment


async def list_character_voices(db: AsyncSession, project_id: int) -> List[ProjectCharacterVoice]:
    """列出项目内所有角色音色映射"""
    result = await db.execute(
        select(ProjectCharacterVoice).where(ProjectCharacterVoice.project_id == project_id)
    )
    return result.scalars().all()
```

- [ ] **Step 2: 在 agnes_client.py 中新增 create_tts_task 方法骨架**

在 `agnes_client.py` 中新增方法（若 Agnes 后续支持 TTS，在此实现）：

```python
async def create_tts_task(
    self,
    text: str,
    voice_id: str,
    model: Optional[str] = None,
) -> dict:
    """
    调用 Agnes TTS API 生成音频

    返回: {"url": str, "duration_ms": int, "file_size": int}

    TODO: Agnes AI 是否提供 TTS 端点待确认。
          若不支持，通过 provider_registry 路由到第三方 TTS provider。
    """
    raise NotImplementedError("Agnes TTS API 尚未实现，请通过 provider_registry 路由到第三方 TTS")
```

- [ ] **Step 3: 在 _async_gen.py 中新增 submit_tts_task 函数**

参考 `submit_image_task` / `submit_video_task` 的模式，新增 TTS 异步任务提交：

```python
async def submit_tts_task(shot_id: int, user_id: int, voice_id: Optional[str] = None) -> int:
    """提交 TTS 生成任务到异步队列"""
    # 复用现有 task_queue 表 + provider_registry 路由
    # ...
```

- [ ] **Step 4: 验证服务加载**

Run: `cd /Users/skywing/agnes-platform/backend && source .venv/bin/activate && python -c "from app.services.project.audio_service import generate_audio, list_builtin_voices; print(f'内置音色数: {len(list_builtin_voices())}')"`
Expected: `内置音色数: 8`

- [ ] **Step 5: 提交**

```bash
git add backend/app/services/project/audio_service.py backend/app/services/agnes_client.py backend/app/services/project/_async_gen.py
git commit -m "feat(project-phase2): 新增 TTS 配音服务（可插拔 provider + 同角色同声音策略）"
```

---

## Task 4: 字幕生成服务

**Files:**
- Create: `backend/app/services/project/subtitle_service.py`

- [ ] **Step 1: 创建 subtitle_service.py**

实现 LLM 生成 SRT + 字幕样式管理：

```python
# =====================================================
# 字幕生成服务 — 从分镜对白生成 SRT 字幕
#
# 核心能力:
#   1. generate_subtitles: 从分镜对白批量生成字幕（LLM 优化文本）
#   2. generate_srt_file: 生成 SRT 格式文件供 ffmpeg 烧录
#   3. generate_ass_file: 生成 ASS 格式文件（含样式）供 ffmpeg 烧录
#   4. parse_srt / build_srt: SRT 文本解析与构建
#
# 字幕生成策略:
#   - 输入：分镜对白（shot.dialogue）+ 分镜时长（shot.duration_ms）
#   - LLM 负责将长对白拆分为多条字幕（每条不超过 20 字）
#   - 时间轴按分镜顺序 + 对白长度比例分配
# =====================================================

import json
import logging
import re
from typing import List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import ProjectShot, ProjectTimelineClip
from app.services.project.sse_manager import project_sse_manager
from app.services.project.wizard import parse_json_loose, _call_llm

logger = logging.getLogger("agnes_platform.project.subtitle")


DEFAULT_SUBTITLE_STYLE = {
    "font_family": "Microsoft YaHei",
    "font_size": 48,
    "font_color": "#FFFFFF",
    "outline_color": "#000000",
    "outline_width": 2,
    "position": "bottom",
    "margin_vertical": 60,
}


async def generate_subtitles(
    db: AsyncSession,
    project_id: int,
    shot_ids: Optional[List[int]] = None,
) -> List[dict]:
    """
    从分镜对白生成字幕片段

    1. 取所有有对白的分镜（或指定 shot_ids）
    2. 调用 LLM 将每个分镜的对白拆分为多条短字幕（每条≤20字）
    3. 按分镜顺序 + 时长比例分配时间轴
    4. 写入 project_timeline_clips 表（track_type='subtitle'）
    5. 推送 SSE
    """
    # 1. 查询分镜
    query = select(ProjectShot).where(ProjectShot.project_id == project_id)
    if shot_ids:
        query = query.where(ProjectShot.id.in_(shot_ids))
    query = query.order_by(ProjectShot.sort_order)
    shots = (await db.execute(query)).scalars().all()

    if not shots:
        return []

    # 2. 调用 LLM 拆分字幕
    shots_input = [
        {"id": s.id, "dialogue": s.dialogue or "", "duration_ms": s.duration_ms or 3000}
        for s in shots if s.dialogue
    ]
    if not shots_input:
        return []

    prompt = f"""请将以下分镜对白拆分为字幕片段，每条字幕不超过 20 字。
输出 JSON 数组，每个元素包含:
- shot_id: 分镜 ID
- segments: 数组，每条包含 text（字幕文本）和 weight（时长权重，0-1，按权重分配分镜时长）

分镜列表:
{json.dumps(shots_input, ensure_ascii=False, indent=2)}

严格输出 JSON，不要多余文字。"""

    result_text = await _call_llm(prompt, temperature=0.3)
    parsed = parse_json_loose(result_text)

    # 3. 按分镜顺序 + 权重分配时间轴
    clips_created: List[dict] = []
    current_time = 0.0  # 全局时间轴起点

    for shot in shots:
        shot_subtitle = next(
            (item for item in parsed if item.get("shot_id") == shot.id),
            None,
        )
        if not shot_subtitle:
            # 无字幕的分镜，仅推进时间轴
            current_time += (shot.duration_ms or 3000) / 1000.0
            continue

        segments = shot_subtitle.get("segments", [])
        if not segments:
            current_time += (shot.duration_ms or 3000) / 1000.0
            continue

        shot_duration = (shot.duration_ms or 3000) / 1000.0
        total_weight = sum(seg.get("weight", 1.0) for seg in segments) or 1.0

        for seg in segments:
            weight = seg.get("weight", 1.0)
            seg_duration = shot_duration * (weight / total_weight)
            clip = ProjectTimelineClip(
                project_id=project_id,
                track_type="subtitle",
                track_index=0,
                source_type="subtitle",
                shot_id=shot.id,
                start_time=current_time,
                duration=seg_duration,
                subtitle_text=seg.get("text", "").strip(),
                sort_order=len(clips_created),
            )
            db.add(clip)
            clips_created.append({
                "shot_id": shot.id,
                "start_time": current_time,
                "duration": seg_duration,
                "text": seg.get("text", "").strip(),
            })
            current_time += seg_duration

    await db.commit()

    await project_sse_manager.push(project_id, "subtitle_completed", {
        "count": len(clips_created),
        "total_duration": current_time,
    })
    return clips_created


def format_srt_time(seconds: float) -> str:
    """将秒数格式化为 SRT 时间格式 HH:MM:SS,mmm"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds - int(seconds)) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def build_srt(clips: List[dict]) -> str:
    """构建 SRT 格式字幕文本"""
    lines: List[str] = []
    for idx, clip in enumerate(clips, start=1):
        start = format_srt_time(clip["start_time"])
        end = format_srt_time(clip["start_time"] + clip["duration"])
        lines.append(str(idx))
        lines.append(f"{start} --> {end}")
        lines.append(clip["text"])
        lines.append("")  # 空行分隔
    return "\n".join(lines)


def build_ass(clips: List[dict], style: Optional[dict] = None) -> str:
    """
    构建 ASS 格式字幕文件（含样式，供 ffmpeg subtitles 滤镜烧录）

    ASS 格式支持丰富的字幕样式（字体/颜色/位置/描边等），
    ffmpeg 的 subtitles 滤镜优先使用 ASS。
    """
    s = style or DEFAULT_SUBTITLE_STYLE
    # 颜色转换：#RRGGBB → ASS 的 &H00BBGGRR（BGR 倒序）
    def to_ass_color(hex_color: str) -> str:
        h = hex_color.lstrip("#")
        r, g, b = h[0:2], h[2:4], h[4:6]
        return f"&H00{b}{g}{r}".upper()

    primary_color = to_ass_color(s.get("font_color", "#FFFFFF"))
    outline_color = to_ass_color(s.get("outline_color", "#000000"))
    font_name = s.get("font_family", "Microsoft YaHei")
    font_size = int(s.get("font_size", 48))
    outline_width = int(s.get("outline_width", 2))
    # 位置：bottom→8 (默认), top→4, center→5
    alignment = {"bottom": 2, "top": 8, "center": 5}.get(s.get("position", "bottom"), 2)
    margin_v = int(s.get("margin_vertical", 60))

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1280
PlayResY: 720

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font_name},{font_size},{primary_color},{outline_color},&H00000000,0,0,0,0,100,100,0,0,1,{outline_width},0,{alignment},10,10,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events: List[str] = []
    for clip in clips:
        start = format_ass_time(clip["start_time"])
        end = format_ass_time(clip["start_time"] + clip["duration"])
        # 转义 ASS 特殊字符
        text = clip["text"].replace("\n", "\\N")
        events.append(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{text}")

    return header + "\n".join(events) + "\n"


def format_ass_time(seconds: float) -> str:
    """ASS 时间格式 H:MM:SS.cc（百分秒）"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    centisecs = int((seconds - int(seconds)) * 100)
    return f"{hours}:{minutes:02d}:{secs:02d}.{centisecs:02d}"


async def get_subtitle_clips(db: AsyncSession, project_id: int) -> List[ProjectTimelineClip]:
    """获取项目的所有字幕片段（按 start_time 排序）"""
    result = await db.execute(
        select(ProjectTimelineClip)
        .where(
            ProjectTimelineClip.project_id == project_id,
            ProjectTimelineClip.track_type == "subtitle",
        )
        .order_by(ProjectTimelineClip.start_time)
    )
    return result.scalars().all()
```

- [ ] **Step 2: 验证服务加载**

Run: `cd /Users/skywing/agnes-platform/backend && source .venv/bin/activate && python -c "from app.services.project.subtitle_service import generate_subtitles, build_srt, build_ass; print('OK')"`
Expected: `OK`

- [ ] **Step 3: 提交**

```bash
git add backend/app/services/project/subtitle_service.py
git commit -m "feat(project-phase2): 新增字幕生成服务（LLM 拆分 + SRT/ASS 格式）"
```

---

## Task 5: 时间线服务

**Files:**
- Create: `backend/app/services/project/timeline_service.py`

- [ ] **Step 1: 创建 timeline_service.py**

实现时间线 CRUD + 自动初始化 + 解析：

```python
# =====================================================
# 时间线服务 — 多轨时间线片段管理 + 自动初始化
#
# 核心能力:
#   1. init_timeline: 从分镜数据自动初始化时间线（视频轨 + 字幕轨）
#   2. list_clips: 列出所有片段（按轨道 + start_time 排序）
#   3. create_clip / update_clip / delete_clip: 片段 CRUD
#   4. get_timeline_data: 获取完整时间线数据（含字幕样式）
#   5. save_timeline_data: 保存时间线草稿数据（projects.timeline_data）
#   6. get_subtitle_style / update_subtitle_style: 字幕样式管理
#
# 轨道类型:
#   - video (track_index 0=主轨, 1=PIP画中画)
#   - audio (track_index 0=TTS, 1=BGM)
#   - subtitle (track_index 0=主字幕, 1=次字幕)
# =====================================================

import logging
from typing import List, Optional, Dict, Any

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import (
    Project, ProjectShot, ProjectShotVideo, ProjectShotAudio,
    ProjectTimelineClip,
)
from app.services.project.sse_manager import project_sse_manager
from app.services.project.subtitle_service import DEFAULT_SUBTITLE_STYLE

logger = logging.getLogger("agnes_platform.project.timeline")


async def init_timeline(db: AsyncSession, project_id: int) -> Dict[str, Any]:
    """
    从分镜数据自动初始化时间线

    自动生成:
    - 视频轨 0：每个分镜的采用视频（按 sort_order）
    - 音频轨 0：每个分镜的采用音频（如有）
    - 字幕轨：不自动生成（由 subtitle_service.generate_subtitles 单独触发）

    返回初始化统计
    """
    # 清空旧的时间线片段
    await db.execute(
        delete(ProjectTimelineClip).where(ProjectTimelineClip.project_id == project_id)
    )

    # 取所有分镜（按 sort_order）
    shots = (await db.execute(
        select(ProjectShot)
        .where(ProjectShot.project_id == project_id)
        .order_by(ProjectShot.sort_order)
    )).scalars().all()

    video_clips: List[ProjectTimelineClip] = []
    audio_clips: List[ProjectTimelineClip] = []
    current_time = 0.0

    for shot in shots:
        shot_duration = (shot.duration_ms or 3000) / 1000.0

        # 视频轨 0：采用视频
        if shot.active_video_id:
            video = (await db.execute(
                select(ProjectShotVideo).where(ProjectShotVideo.id == shot.active_video_id)
            )).scalar_one_or_none()
            if video and video.file_url:
                # 视频实际时长优先用 video.duration_ms
                video_duration = (video.duration_ms or shot.duration_ms or 3000) / 1000.0
                clip = ProjectTimelineClip(
                    project_id=project_id,
                    track_type="video",
                    track_index=0,
                    source_type="shot_video",
                    source_id=video.id,
                    shot_id=shot.id,
                    start_time=current_time,
                    duration=video_duration,
                    transition_type="fade",  # 默认淡入淡出
                    transition_duration=0.5,
                    sort_order=len(video_clips),
                )
                db.add(clip)
                video_clips.append(clip)
                shot_duration = video_duration  # 推进时间轴用视频时长

        # 音频轨 0：采用音频
        if shot.active_audio_id:
            audio = (await db.execute(
                select(ProjectShotAudio).where(ProjectShotAudio.id == shot.active_audio_id)
            )).scalar_one_or_none()
            if audio and audio.file_url:
                audio_duration = (audio.duration_ms or shot.duration_ms or 3000) / 1000.0
                clip = ProjectTimelineClip(
                    project_id=project_id,
                    track_type="audio",
                    track_index=0,
                    source_type="shot_audio",
                    source_id=audio.id,
                    shot_id=shot.id,
                    start_time=current_time,
                    duration=audio_duration,
                    sort_order=len(audio_clips),
                )
                db.add(clip)
                audio_clips.append(clip)

        current_time += shot_duration

    await db.commit()

    # 更新项目的 timeline_data（记录初始化时间）
    project = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
    if project:
        timeline_data = project.timeline_data or {}
        timeline_data["initialized"] = True
        timeline_data["total_duration"] = current_time
        project.timeline_data = timeline_data
        project.total_duration = current_time
        await db.commit()

    await project_sse_manager.push(project_id, "timeline_initialized", {
        "video_clips": len(video_clips),
        "audio_clips": len(audio_clips),
        "total_duration": current_time,
    })

    return {
        "video_clips": len(video_clips),
        "audio_clips": len(audio_clips),
        "total_duration": current_time,
    }


async def list_clips(
    db: AsyncSession, project_id: int,
    track_type: Optional[str] = None,
) -> List[ProjectTimelineClip]:
    """列出时间线片段（按轨道 + start_time 排序）"""
    query = select(ProjectTimelineClip).where(ProjectTimelineClip.project_id == project_id)
    if track_type:
        query = query.where(ProjectTimelineClip.track_type == track_type)
    query = query.order_by(ProjectTimelineClip.track_type, ProjectTimelineClip.track_index, ProjectTimelineClip.start_time)
    result = await db.execute(query)
    return result.scalars().all()


async def create_clip(db: AsyncSession, project_id: int, data: dict) -> ProjectTimelineClip:
    """创建时间线片段"""
    clip = ProjectTimelineClip(project_id=project_id, **data)
    db.add(clip)
    await db.commit()
    await db.refresh(clip)
    await project_sse_manager.push(project_id, "timeline_clip_created", {"clip_id": clip.id})
    return clip


async def update_clip(db: AsyncSession, project_id: int, clip_id: int, data: dict) -> Optional[ProjectTimelineClip]:
    """更新时间线片段"""
    clip = (await db.execute(
        select(ProjectTimelineClip).where(
            ProjectTimelineClip.id == clip_id,
            ProjectTimelineClip.project_id == project_id,
        )
    )).scalar_one_or_none()
    if not clip:
        return None
    for k, v in data.items():
        if hasattr(clip, k) and v is not None:
            setattr(clip, k, v)
    await db.commit()
    await db.refresh(clip)
    await project_sse_manager.push(project_id, "timeline_clip_updated", {"clip_id": clip_id})
    return clip


async def delete_clip(db: AsyncSession, project_id: int, clip_id: int) -> bool:
    """删除时间线片段"""
    clip = (await db.execute(
        select(ProjectTimelineClip).where(
            ProjectTimelineClip.id == clip_id,
            ProjectTimelineClip.project_id == project_id,
        )
    )).scalar_one_or_none()
    if not clip:
        return False
    await db.delete(clip)
    await db.commit()
    await project_sse_manager.push(project_id, "timeline_clip_deleted", {"clip_id": clip_id})
    return True


async def get_timeline_data(db: AsyncSession, project_id: int) -> Dict[str, Any]:
    """获取完整时间线数据（片段 + 字幕样式 + 总时长）"""
    clips = await list_clips(db, project_id)
    project = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()

    timeline_data = (project.timeline_data if project else {}) or {}
    subtitle_style = timeline_data.get("subtitle_style", DEFAULT_SUBTITLE_STYLE)
    total_duration = timeline_data.get("total_duration", project.total_duration if project else 0)

    return {
        "clips": [
            {
                "id": c.id,
                "track_type": c.track_type,
                "track_index": c.track_index,
                "source_type": c.source_type,
                "source_id": c.source_id,
                "shot_id": c.shot_id,
                "start_time": c.start_time,
                "duration": c.duration,
                "trim_start": c.trim_start,
                "trim_end": c.trim_end,
                "transition_type": c.transition_type,
                "transition_duration": c.transition_duration,
                "subtitle_text": c.subtitle_text,
                "sort_order": c.sort_order,
            }
            for c in clips
        ],
        "subtitle_style": subtitle_style,
        "total_duration": total_duration,
    }


async def save_timeline_data(
    db: AsyncSession, project_id: int,
    subtitle_style: Optional[Dict[str, Any]] = None,
    draft: Optional[Dict[str, Any]] = None,
) -> Optional[Project]:
    """保存时间线草稿数据（字幕样式、轨道折叠状态等）"""
    project = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
    if not project:
        return None
    timeline_data = project.timeline_data or {}
    if subtitle_style:
        timeline_data["subtitle_style"] = subtitle_style
    if draft:
        timeline_data["draft"] = draft
    project.timeline_data = timeline_data
    await db.commit()
    await db.refresh(project)
    return project


async def get_subtitle_style(db: AsyncSession, project_id: int) -> Dict[str, Any]:
    """获取字幕样式"""
    project = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
    if not project:
        return DEFAULT_SUBTITLE_STYLE
    timeline_data = project.timeline_data or {}
    return timeline_data.get("subtitle_style", DEFAULT_SUBTITLE_STYLE)


async def update_subtitle_style(
    db: AsyncSession, project_id: int, style: Dict[str, Any]
) -> Optional[Project]:
    """更新字幕样式"""
    return await save_timeline_data(db, project_id, subtitle_style=style)
```

- [ ] **Step 2: 验证服务加载**

Run: `cd /Users/skywing/agnes-platform/backend && source .venv/bin/activate && python -c "from app.services.project.timeline_service import init_timeline, list_clips, get_timeline_data; print('OK')"`
Expected: `OK`

- [ ] **Step 3: 提交**

```bash
git add backend/app/services/project/timeline_service.py
git commit -m "feat(project-phase2): 新增时间线服务（多轨片段 CRUD + 自动初始化）"
```

---

## Task 6: 合成服务扩展

**Files:**
- Modify: `backend/app/services/project/merge_service.py`

- [ ] **Step 1: 扩展 execute_merge 支持音频混入 + 字幕烧录 + 时间线顺序**

在 `merge_service.py` 中新增 `execute_merge_advanced` 函数（保留原 `execute_merge` 作为简单合成回退）：

```python
# =====================================================
# 高级合成 — 多轨视频/音频/字幕合成
#
# 流程:
#   1. 取时间线片段（video/audio/subtitle 三类轨道）
#   2. 下载所有视频片段到临时目录
#   3. 按时间线顺序拼接视频（含 xfade 转场）
#   4. 混合音频轨（TTS + BGM）
#   5. 生成 ASS 字幕文件
#   6. ffmpeg 最终合成：视频 + 音频 + 字幕烧录
#   7. 上传最终成片
#
# ffmpeg 命令示例:
#   ffmpeg -i video.mp4 -i audio.mp4 -vf "subtitles=sub.ass" \
#     -map 0:v -map 1:a -c:v libx264 -c:a aac output.mp4
# =====================================================

async def execute_merge_advanced(
    db: AsyncSession, project_id: int, user_id: int,
    with_audio: bool = True, with_subtitle: bool = True,
) -> Optional[Project]:
    """
    高级合成（多轨 + 音频混入 + 字幕烧录）

    参数:
    - with_audio: 是否混入音频轨
    - with_subtitle: 是否烧录字幕
    """
    from app.services.project.timeline_service import list_clips, get_subtitle_style
    from app.services.project.subtitle_service import build_ass

    project = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
    if not project:
        return None

    # 1. 取时间线片段
    video_clips = await list_clips(db, project_id, track_type="video")
    audio_clips = await list_clips(db, project_id, track_type="audio") if with_audio else []
    subtitle_clips = await list_clips(db, project_id, track_type="subtitle") if with_subtitle else []

    if not video_clips:
        raise ValueError("时间线无视频片段，请先初始化时间线或生成视频")

    await project_sse_manager.push(project_id, "merge_progress", {
        "status": "downloading", "progress": 5,
        "total_videos": len(video_clips), "total_audios": len(audio_clips),
    })

    # 2. 下载所有视频片段
    import httpx
    import os
    import tempfile

    tmp_dir = tempfile.mkdtemp(prefix=f"project_merge_advanced_{project_id}_")
    video_paths: List[str] = []
    try:
        async with httpx.AsyncClient(timeout=300) as client:
            for idx, clip in enumerate(video_clips):
                if not clip.source_id:
                    continue
                video = (await db.execute(
                    select(ProjectShotVideo).where(ProjectShotVideo.id == clip.source_id)
                )).scalar_one_or_none()
                if not video or not video.file_url:
                    continue
                local_path = os.path.join(tmp_dir, f"video_{idx:04d}.mp4")
                resp = await client.get(video.file_url)
                resp.raise_for_status()
                with open(local_path, "wb") as f:
                    f.write(resp.content)
                video_paths.append(local_path)

                await project_sse_manager.push(project_id, "merge_progress", {
                    "status": "downloading", "progress": 5 + int(20 * (idx + 1) / len(video_clips)),
                })

        # 3. 下载音频片段（如果有）
        audio_paths: List[str] = []
        if audio_clips:
            for idx, clip in enumerate(audio_clips):
                if not clip.source_id:
                    continue
                audio = (await db.execute(
                    select(ProjectShotAudio).where(ProjectShotAudio.id == clip.source_id)
                )).scalar_one_or_none()
                if not audio or not audio.file_url:
                    continue
                local_path = os.path.join(tmp_dir, f"audio_{idx:04d}.mp3")
                resp = await client.get(audio.file_url)
                resp.raise_for_status()
                with open(local_path, "wb") as f:
                    f.write(resp.content)
                audio_paths.append(local_path)

        await project_sse_manager.push(project_id, "merge_progress", {
            "status": "compositing", "progress": 40,
        })

        # 4. 拼接视频（含转场）
        composite_video_path = os.path.join(tmp_dir, "composite_video.mp4")
        await _concat_videos_with_transitions(video_clips, video_paths, composite_video_path, project.aspect_ratio)

        # 5. 混合音频（如有）
        composite_audio_path = None
        if audio_paths:
            composite_audio_path = os.path.join(tmp_dir, "composite_audio.aac")
            await _concat_audios(audio_paths, composite_audio_path)

        # 6. 生成 ASS 字幕文件（如有）
        subtitle_path = None
        if subtitle_clips:
            subtitle_path = os.path.join(tmp_dir, "subtitles.ass")
            subtitle_style = await get_subtitle_style(db, project_id)
            clips_data = [
                {"start_time": c.start_time, "duration": c.duration, "text": c.subtitle_text or ""}
                for c in subtitle_clips
            ]
            ass_content = build_ass(clips_data, subtitle_style)
            with open(subtitle_path, "w", encoding="utf-8") as f:
                f.write(ass_content)

        # 7. 最终合成
        outputs_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "outputs", "projects", str(project_id),
        )
        os.makedirs(outputs_dir, exist_ok=True)
        output_path = os.path.join(outputs_dir, "final.mp4")

        await _ffmpeg_final_composite(
            video_path=composite_video_path,
            audio_path=composite_audio_path,
            subtitle_path=subtitle_path,
            output_path=output_path,
        )

        # 8. 更新项目
        import time as _time
        final_url = f"/api/projects/{project_id}/final-video?v={int(_time.time())}"

        # 计算总时长
        total_duration = max(
            (c.start_time + c.duration for c in video_clips),
            default=0.0,
        )

        project.final_video_url = final_url
        project.total_duration = total_duration
        project.status = PROJECT_STATUS_COMPLETED
        await db.commit()
        await db.refresh(project)

        await project_sse_manager.push(project_id, "merge_completed", {
            "status": "completed", "progress": 100,
            "final_video_url": final_url,
            "total_duration": total_duration,
        })
        return project

    finally:
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)


async def _concat_videos_with_transitions(
    clips: List, video_paths: List[str], output_path: str, aspect_ratio: str
) -> None:
    """拼接视频（含 xfade 转场）"""
    # 简单实现：先用 concat demuxer 拼接（无转场）
    # 高级实现：用 xfade 滤镜逐对拼接（有转场）
    # Phase 2 先实现简单 concat，转场后续优化
    concat_list_path = output_path + ".concat.txt"
    with open(concat_list_path, "w") as f:
        for p in video_paths:
            f.write(f"file '{os.path.abspath(p)}'\n")

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", concat_list_path,
        "-c", "copy",
        output_path,
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=600)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg 视频拼接失败: {stderr.decode('utf-8', errors='ignore')[:500]}")


async def _concat_audios(audio_paths: List[str], output_path: str) -> None:
    """拼接音频"""
    concat_list_path = output_path + ".concat.txt"
    with open(concat_list_path, "w") as f:
        for p in audio_paths:
            f.write(f"file '{os.path.abspath(p)}'\n")

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", concat_list_path,
        "-c", "copy",
        output_path,
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg 音频拼接失败: {stderr.decode('utf-8', errors='ignore')[:500]}")


async def _ffmpeg_final_composite(
    video_path: str,
    audio_path: Optional[str],
    subtitle_path: Optional[str],
    output_path: str,
) -> None:
    """最终合成：视频 + 音频 + 字幕烧录"""
    cmd = ["ffmpeg", "-y", "-i", video_path]

    if audio_path:
        cmd.extend(["-i", audio_path])

    # 视频滤镜（字幕烧录）
    vf_filters: List[str] = []
    if subtitle_path:
        # subtitles 滤镜路径需转义冒号
        escaped_path = subtitle_path.replace(":", "\\:")
        vf_filters.append(f"subtitles='{escaped_path}'")

    if vf_filters:
        cmd.extend(["-vf", ",".join(vf_filters)])

    # 映射流
    if audio_path:
        cmd.extend(["-map", "0:v", "-map", "1:a"])
    else:
        cmd.extend(["-map", "0:v"])

    # 编码参数
    cmd.extend([
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "23",
    ])
    if audio_path:
        cmd.extend(["-c:a", "aac", "-b:a", "128k"])

    cmd.append(output_path)

    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=900)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg 最终合成失败: {stderr.decode('utf-8', errors='ignore')[:500]}")
```

- [ ] **Step 2: 修改 merge_project 入口支持高级合成**

在 `merge_project` 函数中新增 `with_audio` / `with_subtitle` 参数，根据参数选择 `execute_merge`（简单）或 `execute_merge_advanced`（高级）：

```python
async def merge_project(
    db: AsyncSession, project_id: int, user_id: int,
    with_audio: bool = True, with_subtitle: bool = True,
    use_timeline: bool = True,
) -> Project:
    """
    触发项目合成（异步执行）

    参数:
    - with_audio: 是否混入音频（仅 use_timeline=True 时生效）
    - with_subtitle: 是否烧录字幕（仅 use_timeline=True 时生效）
    - use_timeline: True=按时间线高级合成，False=按分镜顺序简单拼接
    """
    # ... 状态校验逻辑保持不变 ...

    asyncio.create_task(_execute_merge_wrapper(project_id, user_id, with_audio, with_subtitle, use_timeline))
    return project


async def _execute_merge_wrapper(
    project_id: int, user_id: int,
    with_audio: bool = True, with_subtitle: bool = True, use_timeline: bool = True,
) -> None:
    """execute_merge 的包装器"""
    from app.core.database import new_async_session
    db = new_async_session()
    try:
        if use_timeline:
            await execute_merge_advanced(db, project_id, user_id, with_audio, with_subtitle)
        else:
            await execute_merge(db, project_id, user_id)
    except Exception as e:
        logger.error(f"项目合成失败 project_id={project_id}: {e}")
        await update_status(db, project_id, PROJECT_STATUS_COMPLETED)
        await project_sse_manager.push(project_id, "merge_progress", {
            "status": "failed", "error": str(e),
        })
    finally:
        await db.close()
```

- [ ] **Step 3: 验证服务加载**

Run: `cd /Users/skywing/agnes-platform/backend && source .venv/bin/activate && python -c "from app.services.project.merge_service import execute_merge_advanced, merge_project; print('OK')"`
Expected: `OK`

- [ ] **Step 4: 提交**

```bash
git add backend/app/services/project/merge_service.py
git commit -m "feat(project-phase2): 合成服务扩展支持音频混入 + 字幕烧录 + 时间线顺序"
```

---

## Task 7: 后端路由 — 新增 TTS/字幕/时间线 API 端点

**Files:**
- Modify: `backend/app/routes/projects.py`

- [ ] **Step 1: 新增配音相关 API 端点**

在 `routes/projects.py` 中新增（参考现有 frame-images/videos 路由模式）：

```python
# =====================================================
# 13. 分镜配音（TTS）— Phase 2
# =====================================================

@router.post("/{project_id}/shots/{shot_id}/audios/generate", summary="生成 TTS 配音")
async def generate_shot_audio_api(
    project_id: int, shot_id: int,
    data: GenerateTTSRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project_or_404(db, project_id)
    _check_project_owner(project, current_user)
    audio = await generate_audio(
        db, shot_id, current_user.id,
        voice_id=data.voice_id, character_id=data.character_id,
        text=data.text, model=data.model, provider=data.provider,
    )
    return ProjectShotAudioResponse.model_validate(audio)


@router.post("/{project_id}/shots/audios/batch-generate", summary="批量生成 TTS")
async def batch_generate_audios_api(
    project_id: int,
    data: BatchGenerateTTSRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project_or_404(db, project_id)
    _check_project_owner(project, current_user)
    task_ids = await batch_generate_audios(db, data.shot_ids, current_user.id, data.voice_id)
    return {"task_ids": task_ids, "count": len(task_ids)}


@router.post("/{project_id}/shots/{shot_id}/audios/upload", summary="上传音频")
async def upload_shot_audio_api(
    project_id: int, shot_id: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project_or_404(db, project_id)
    _check_project_owner(project, current_user)
    # 保存文件到本地（复用现有上传逻辑）
    file_url = await _save_upload_file(file, "audio")
    audio = await upload_audio(db, shot_id, current_user.id, file_url)
    return ProjectShotAudioResponse.model_validate(audio)


@router.get("/{project_id}/shots/{shot_id}/audios", summary="音频版本列表")
async def list_shot_audios_api(
    project_id: int, shot_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    audios = await list_audios(db, shot_id)
    return [ProjectShotAudioResponse.model_validate(a) for a in audios]


@router.post("/{project_id}/shots/{shot_id}/audios/{audio_id}/activate", summary="设为采用版")
async def set_active_audio_api(
    project_id: int, shot_id: int, audio_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project_or_404(db, project_id)
    _check_project_owner(project, current_user)
    audio = await set_active_audio(db, shot_id, audio_id)
    return ProjectShotAudioResponse.model_validate(audio)


@router.delete("/{project_id}/shots/{shot_id}/audios/{audio_id}", summary="删除音频版本")
async def delete_shot_audio_api(
    project_id: int, shot_id: int, audio_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project_or_404(db, project_id)
    _check_project_owner(project, current_user)
    ok = await delete_audio(db, shot_id, audio_id)
    return {"success": ok}


# =====================================================
# 14. 角色音色映射 — Phase 2
# =====================================================

@router.get("/{project_id}/voices", summary="内置音色列表")
async def list_builtin_voices_api(
    project_id: int,
    current_user: User = Depends(get_current_user),
):
    return list_builtin_voices()


@router.get("/{project_id}/character-voices", summary="项目角色音色映射")
async def list_character_voices_api(
    project_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    assignments = await list_character_voices(db, project_id)
    return [CharacterVoiceResponse.model_validate(a) for a in assignments]


@router.post("/{project_id}/characters/{character_id}/voice", summary="为角色分配音色")
async def assign_character_voice_api(
    project_id: int, character_id: int,
    data: AssignCharacterVoiceRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project_or_404(db, project_id)
    _check_project_owner(project, current_user)
    assignment = await assign_character_voice(
        db, project_id, character_id, data.voice_id, data.voice_name,
    )
    return CharacterVoiceResponse.model_validate(assignment)
```

- [ ] **Step 2: 新增字幕相关 API 端点**

```python
# =====================================================
# 15. 字幕生成 — Phase 2
# =====================================================

@router.post("/{project_id}/subtitles/generate", summary="从分镜对白生成字幕")
async def generate_subtitles_api(
    project_id: int,
    data: GenerateSubtitleRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project_or_404(db, project_id)
    _check_project_owner(project, current_user)
    clips = await generate_subtitles(db, project_id, data.shot_ids)
    return {"count": len(clips), "clips": clips}
```

- [ ] **Step 3: 新增时间线相关 API 端点**

```python
# =====================================================
# 16. 时间线 — Phase 2
# =====================================================

@router.get("/{project_id}/timeline", summary="获取时间线数据")
async def get_timeline_api(
    project_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project_or_404(db, project_id)
    _check_project_owner(project, current_user)
    return await get_timeline_data(db, project_id)


@router.post("/{project_id}/timeline/init", summary="从分镜初始化时间线")
async def init_timeline_api(
    project_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project_or_404(db, project_id)
    _check_project_owner(project, current_user)
    result = await init_timeline(db, project_id)
    return result


@router.post("/{project_id}/timeline/clips", summary="添加时间线片段")
async def create_timeline_clip_api(
    project_id: int,
    data: TimelineClipCreate,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project_or_404(db, project_id)
    _check_project_owner(project, current_user)
    clip = await create_clip(db, project_id, data.model_dump())
    return TimelineClipResponse.model_validate(clip)


@router.patch("/{project_id}/timeline/clips/{clip_id}", summary="更新时间线片段")
async def update_timeline_clip_api(
    project_id: int, clip_id: int,
    data: TimelineClipUpdate,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project_or_404(db, project_id)
    _check_project_owner(project, current_user)
    update_data = data.model_dump(exclude_unset=True)
    clip = await update_clip(db, project_id, clip_id, update_data)
    if not clip:
        raise HTTPException(404, "时间线片段不存在")
    return TimelineClipResponse.model_validate(clip)


@router.delete("/{project_id}/timeline/clips/{clip_id}", summary="删除时间线片段")
async def delete_timeline_clip_api(
    project_id: int, clip_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project_or_404(db, project_id)
    _check_project_owner(project, current_user)
    ok = await delete_clip(db, project_id, clip_id)
    return {"success": ok}


@router.patch("/{project_id}/timeline/subtitle-style", summary="更新字幕样式")
async def update_subtitle_style_api(
    project_id: int,
    data: Dict[str, Any],
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project_or_404(db, project_id)
    _check_project_owner(project, current_user)
    result = await update_subtitle_style(db, project_id, data)
    return {"success": result is not None}
```

- [ ] **Step 4: 扩展合成 API 支持高级参数**

修改现有 `POST /{project_id}/merge` 端点：

```python
@router.post("/{project_id}/merge", summary="触发项目合成")
async def merge_project_api(
    project_id: int,
    payload: dict = Body(default={}),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project_or_404(db, project_id)
    _check_project_owner(project, current_user)
    with_audio = payload.get("with_audio", True)
    with_subtitle = payload.get("with_subtitle", True)
    use_timeline = payload.get("use_timeline", True)
    result = await merge_project(
        db, project_id, current_user.id,
        with_audio=with_audio, with_subtitle=with_subtitle, use_timeline=use_timeline,
    )
    return {"status": "queued", "project_id": result.id}
```

- [ ] **Step 5: 在 imports 区新增导入**

```python
from app.schemas.project import (
    # ... 已有导入 ...
    GenerateTTSRequest, BatchGenerateTTSRequest, ProjectShotAudioResponse,
    CharacterVoiceResponse, AssignCharacterVoiceRequest,
    GenerateSubtitleRequest,
    TimelineClipCreate, TimelineClipUpdate, TimelineClipResponse,
)
from app.services.project.audio_service import (
    generate_audio, batch_generate_audios, upload_audio,
    set_active_audio, list_audios, delete_audio,
    assign_character_voice, list_character_voices, list_builtin_voices,
)
from app.services.project.subtitle_service import generate_subtitles
from app.services.project.timeline_service import (
    init_timeline, list_clips, create_clip, update_clip, delete_clip,
    get_timeline_data, update_subtitle_style,
)
```

- [ ] **Step 6: 验证路由加载**

Run: `cd /Users/skywing/agnes-platform/backend && source .venv/bin/activate && python -c "from app.routes.projects import router; print(f'路由数: {len(router.routes)}')"`
Expected: 路由数 > 50（Phase 1 约 30 个 + Phase 2 新增约 20 个）

- [ ] **Step 7: 提交**

```bash
git add backend/app/routes/projects.py
git commit -m "feat(project-phase2): 新增 TTS/字幕/时间线 API 端点"
```

---

## Task 8: 前端类型/API/Store

**Files:**
- Modify: `frontend/src/types/project.ts`
- Modify: `frontend/src/api/projects.ts`
- Modify: `frontend/src/stores/project.ts`
- Modify: `frontend/src/composables/useProjectSSE.ts`

- [ ] **Step 1: 在 types/project.ts 新增类型定义**

```typescript
// =====================================================
// Phase 2: 配音 / 字幕 / 时间线类型
// =====================================================

/** 分镜配音（多版本） */
export interface ProjectShotAudio {
  id: number
  shot_id: number
  version: number
  is_active: boolean
  is_manual: boolean
  file_url?: string | null
  text?: string | null
  voice_id?: string | null
  voice_name?: string | null
  character_id?: number | null
  provider?: string | null
  model?: string | null
  duration_ms?: number | null
  file_size?: number | null
  created_by: string
  created_at: string
}

/** 角色-音色映射 */
export interface CharacterVoice {
  id: number
  project_id: number
  character_id: number
  voice_id: string
  voice_name?: string | null
  assigned_at: string
}

/** 内置音色选项 */
export interface VoiceOption {
  voice_id: string
  name: string
  gender: 'male' | 'female' | 'neutral'
  suitable_for: string
}

/** 时间线片段 */
export interface TimelineClip {
  id: number
  project_id: number
  track_type: 'video' | 'audio' | 'subtitle'
  track_index: number
  source_type?: string | null
  source_id?: number | null
  shot_id?: number | null
  start_time: number
  duration: number
  trim_start: number
  trim_end?: number | null
  transition_type: string  // fade/slide/wipe/dissolve/none
  transition_duration: number
  subtitle_text?: string | null
  sort_order: number
  created_at: string
  updated_at: string
}

/** 时间线数据响应 */
export interface TimelineData {
  clips: TimelineClip[]
  subtitle_style: SubtitleStyle
  total_duration: number
}

/** 字幕样式 */
export interface SubtitleStyle {
  font_family: string
  font_size: number
  font_color: string
  outline_color: string
  outline_width: number
  position: 'bottom' | 'top' | 'center'
  margin_vertical: number
}

/** TTS 生成请求 */
export interface GenerateTTSRequest {
  voice_id?: string
  character_id?: number
  text?: string
  model?: string
  provider?: string
}

/** 批量 TTS 生成请求 */
export interface BatchGenerateTTSRequest {
  shot_ids: number[]
  voice_id?: string
}

/** 字幕生成请求 */
export interface GenerateSubtitleRequest {
  shot_ids?: number[]
  style?: Partial<SubtitleStyle>
}
```

同时在 `ProjectShot` 接口中补齐：

```typescript
export interface ProjectShot {
  // ... 已有字段 ...
  active_audio_id?: number | null  // Phase 2
}
```

在 `ProjectEventType` 联合类型中补齐：

```typescript
export type ProjectEventType =
  | 'wizard_step_started' | 'wizard_step_completed' | 'wizard_step_failed' | 'wizard_completed'
  | 'entity_image_generated' | 'frame_image_generated' | 'shot_video_generated'
  | 'shot_edited' | 'shots_reordered' | 'generation_failed'
  | 'merge_progress' | 'merge_completed'
  // Phase 2 新增
  | 'tts_progress' | 'tts_completed'
  | 'subtitle_progress' | 'subtitle_completed'
  | 'timeline_initialized' | 'timeline_clip_created' | 'timeline_clip_updated' | 'timeline_clip_deleted'
  | 'audio_activated'
```

- [ ] **Step 2: 在 api/projects.ts 新增 API 函数**

```typescript
// =====================================================
// Phase 2: 配音 / 字幕 / 时间线 API
// =====================================================

// 配音
export function generateShotAudio(projectId: number, shotId: number, data: GenerateTTSRequest): Promise<ProjectShotAudio> {
  return client.post(`/api/projects/${projectId}/shots/${shotId}/audios/generate`, data)
}

export function batchGenerateAudios(projectId: number, data: BatchGenerateTTSRequest): Promise<{ task_ids: number[]; count: number }> {
  return client.post(`/api/projects/${projectId}/shots/audios/batch-generate`, data)
}

export function uploadShotAudio(projectId: number, shotId: number, file: File): Promise<ProjectShotAudio> {
  const formData = new FormData()
  formData.append('file', file)
  return client.post(`/api/projects/${projectId}/shots/${shotId}/audios/upload`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

export function listShotAudios(projectId: number, shotId: number): Promise<ProjectShotAudio[]> {
  return client.get(`/api/projects/${projectId}/shots/${shotId}/audios`)
}

export function setActiveAudio(projectId: number, shotId: number, audioId: number): Promise<ProjectShotAudio> {
  return client.post(`/api/projects/${projectId}/shots/${shotId}/audios/${audioId}/activate`, {})
}

export function deleteShotAudio(projectId: number, shotId: number, audioId: number): Promise<{ success: boolean }> {
  return client.delete(`/api/projects/${projectId}/shots/${shotId}/audios/${audioId}`)
}

// 音色
export function listBuiltinVoices(projectId: number): Promise<VoiceOption[]> {
  return client.get(`/api/projects/${projectId}/voices`)
}

export function listCharacterVoices(projectId: number): Promise<CharacterVoice[]> {
  return client.get(`/api/projects/${projectId}/character-voices`)
}

export function assignCharacterVoice(projectId: number, characterId: number, data: { voice_id: string; voice_name?: string }): Promise<CharacterVoice> {
  return client.post(`/api/projects/${projectId}/characters/${characterId}/voice`, data)
}

// 字幕
export function generateSubtitles(projectId: number, data: GenerateSubtitleRequest): Promise<{ count: number; clips: any[] }> {
  return client.post(`/api/projects/${projectId}/subtitles/generate`, data)
}

// 时间线
export function getTimeline(projectId: number): Promise<TimelineData> {
  return client.get(`/api/projects/${projectId}/timeline`)
}

export function initTimeline(projectId: number): Promise<{ video_clips: number; audio_clips: number; total_duration: number }> {
  return client.post(`/api/projects/${projectId}/timeline/init`, {})
}

export function createTimelineClip(projectId: number, data: Partial<TimelineClip>): Promise<TimelineClip> {
  return client.post(`/api/projects/${projectId}/timeline/clips`, data)
}

export function updateTimelineClip(projectId: number, clipId: number, data: Partial<TimelineClip>): Promise<TimelineClip> {
  return client.patch(`/api/projects/${projectId}/timeline/clips/${clipId}`, data)
}

export function deleteTimelineClip(projectId: number, clipId: number): Promise<{ success: boolean }> {
  return client.delete(`/api/projects/${projectId}/timeline/clips/${clipId}`)
}

export function updateSubtitleStyle(projectId: number, data: Partial<SubtitleStyle>): Promise<{ success: boolean }> {
  return client.patch(`/api/projects/${projectId}/timeline/subtitle-style`, data)
}

// 合成（扩展支持高级参数）
export function mergeProjectAdvanced(
  projectId: number,
  options: { with_audio?: boolean; with_subtitle?: boolean; use_timeline?: boolean } = {}
): Promise<{ status: string; project_id: number }> {
  return client.post(`/api/projects/${projectId}/merge`, options)
}
```

- [ ] **Step 3: 在 stores/project.ts 新增状态和 actions**

```typescript
// 状态
const timeline = ref<TimelineData | null>(null)
const audios = ref<Record<number, ProjectShotAudio[]>>({})  // shot_id → audios
const builtinVoices = ref<VoiceOption[]>([])
const characterVoices = ref<CharacterVoice[]>([])

// Actions
async function loadTimeline() {
  if (!project.value) return
  timeline.value = await apiGetTimeline(project.value.id)
}

async function initTimeline() {
  if (!project.value) return
  await apiInitTimeline(project.value.id)
  await loadTimeline()
}

async function updateClip(clipId: number, data: Partial<TimelineClip>) {
  if (!project.value) return
  await apiUpdateTimelineClip(project.value.id, clipId, data)
  await loadTimeline()
}

async function deleteClip(clipId: number) {
  if (!project.value) return
  await apiDeleteTimelineClip(project.value.id, clipId)
  await loadTimeline()
}

async function generateTTS(shotId: number, data: GenerateTTSRequest) {
  if (!project.value) return
  await apiGenerateShotAudio(project.value.id, shotId, data)
  await loadAudios(shotId)
}

async function loadAudios(shotId: number) {
  if (!project.value) return
  audios.value[shotId] = await apiListShotAudios(project.value.id, shotId)
}

async function loadBuiltinVoices() {
  if (!project.value) return
  builtinVoices.value = await apiListBuiltinVoices(project.value.id)
}

async function loadCharacterVoices() {
  if (!project.value) return
  characterVoices.value = await apiListCharacterVoices(project.value.id)
}

async function assignVoice(characterId: number, voiceId: string, voiceName?: string) {
  if (!project.value) return
  await apiAssignCharacterVoice(project.value.id, characterId, { voice_id: voiceId, voice_name: voiceName })
  await loadCharacterVoices()
}

async function generateSubtitles(shotIds?: number[]) {
  if (!project.value) return
  await apiGenerateSubtitles(project.value.id, { shot_ids: shotIds })
  await loadTimeline()
}

async function mergeProjectAdvanced(options = {}) {
  if (!project.value) return
  mergeLoading.value = true
  try {
    await apiMergeProjectAdvanced(project.value.id, options)
  } finally {
    mergeLoading.value = false
  }
}
```

- [ ] **Step 4: 在 useProjectSSE.ts 监听 Phase 2 事件**

```typescript
// 在事件处理 switch 中新增
case 'tts_completed':
  // 刷新对应分镜的音频列表
  await store.loadAudios(event.data.shot_id)
  break
case 'subtitle_completed':
  // 刷新时间线
  await store.loadTimeline()
  break
case 'timeline_initialized':
case 'timeline_clip_created':
case 'timeline_clip_updated':
case 'timeline_clip_deleted':
  await store.loadTimeline()
  break
case 'audio_activated':
  await store.loadAudios(event.data.shot_id)
  break
```

- [ ] **Step 5: 验证前端类型检查**

Run: `cd /Users/skywing/agnes-platform/frontend && npx vue-tsc --noEmit 2>&1 | grep -E "project.ts|projects.ts" | head -20`
Expected: 无新增类型错误

- [ ] **Step 6: 提交**

```bash
git add frontend/src/types/project.ts frontend/src/api/projects.ts frontend/src/stores/project.ts frontend/src/composables/useProjectSSE.ts
git commit -m "feat(project-phase2): 前端类型/API/Store 补齐 TTS/字幕/时间线能力"
```

---

## Task 9: 前端时间线编辑器组件

**Files:**
- Create: `frontend/src/components/project/TimelineTab.vue`
- Create: `frontend/src/components/project/timeline/TimelineEditor.vue`
- Create: `frontend/src/components/project/timeline/TimelineTrack.vue`
- Create: `frontend/src/components/project/timeline/TimelineClip.vue`
- Create: `frontend/src/components/project/timeline/TimelineToolbar.vue`
- Create: `frontend/src/components/project/timeline/ClipPropertyPanel.vue`
- Create: `frontend/src/components/project/timeline/SubtitleStyleDialog.vue`
- Create: `frontend/src/components/project/timeline/VoicePickerDialog.vue`

- [ ] **Step 1: 创建 TimelineTab.vue（Tab 容器）**

`TimelineTab.vue` 作为 ProjectManagerView 的第 6 个 Tab 内容，封装时间线编辑器的整体布局：

```vue
<template>
  <div class="timeline-tab">
    <TimelineToolbar
      :total-duration="timeline?.total_duration || 0"
      :merge-loading="mergeLoading"
      @init="handleInit"
      @generate-subtitles="handleGenerateSubtitles"
      @merge="handleMerge"
      @subtitle-style="subtitleStyleVisible = true"
    />
    <TimelineEditor
      v-if="timeline"
      :timeline="timeline"
      @clip-click="handleClipClick"
      @clip-update="handleClipUpdate"
      @clip-delete="handleClipDelete"
    />
    <el-empty v-else description="时间线未初始化，请点击工具栏的『初始化时间线』按钮" />
    <ClipPropertyPanel
      v-if="selectedClip"
      :clip="selectedClip"
      @close="selectedClip = null"
      @update="handleClipUpdate"
    />
    <SubtitleStyleDialog
      v-model:visible="subtitleStyleVisible"
      :style="timeline?.subtitle_style"
      @save="handleSaveStyle"
    />
  </div>
</template>
```

- [ ] **Step 2: 创建 TimelineEditor.vue（核心时间线编辑器）**

参考 LingGuo-Drama 的 [VideoTimelineEditor.vue](https://github.com/LingGuoAI/LingGuo-Drama/blob/main/web/src/components/editor/VideoTimelineEditor.vue)，实现：

- 时间标尺（0s, 5s, 10s... 刻度）
- 多轨道区（视频轨/音频轨/字幕轨）
- 播放头（红色竖线，可拖拽）
- 片段拖拽（改变 start_time）
- 片段裁剪（拖动左右边缘调整 trim_start/trim_end）
- 缩放控制（zoomLevel 控制时间轴密度）

核心结构：

```vue
<template>
  <div class="timeline-editor">
    <!-- 时间标尺 -->
    <div class="timeline-ruler" :style="{ width: totalWidth + 'px' }">
      <div v-for="tick in ticks" :key="tick.time" class="ruler-tick" :style="{ left: tick.x + 'px' }">
        <span class="tick-label">{{ formatTime(tick.time) }}</span>
      </div>
    </div>
    <!-- 轨道区 -->
    <div class="timeline-tracks" :style="{ width: totalWidth + 'px' }">
      <TimelineTrack
        v-for="track in tracks"
        :key="`${track.type}-${track.index}`"
        :track="track"
        :clips="clipsByTrack[`${track.type}-${track.index}`] || []"
        :pixels-per-second="pixelsPerSecond"
        :selected-clip-id="selectedClipId"
        @clip-click="$emit('clip-click', $event)"
        @clip-update="$emit('clip-update', $event)"
      />
    </div>
    <!-- 播放头 -->
    <div class="playhead" :style="{ left: playheadX + 'px' }" @mousedown="startDragPlayhead" />
  </div>
</template>
```

- [ ] **Step 3: 创建 TimelineTrack.vue（单轨道）**

```vue
<template>
  <div class="timeline-track" :class="track.type">
    <div class="track-label">{{ trackLabel }}</div>
    <div class="track-body" :style="{ width: totalWidth + 'px' }">
      <TimelineClip
        v-for="clip in clips"
        :key="clip.id"
        :clip="clip"
        :pixels-per-second="pixelsPerSecond"
        :selected="clip.id === selectedClipId"
        @click="$emit('clip-click', clip)"
        @update="$emit('clip-update', $event)"
      />
    </div>
  </div>
</template>
```

- [ ] **Step 4: 创建 TimelineClip.vue（单片段）**

实现拖拽 + 裁剪 + 转场显示：

```vue
<template>
  <div
    class="timeline-clip"
    :class="[clip.track_type, { selected }]"
    :style="{ left: clip.start_time * pixelsPerSecond + 'px', width: clip.duration * pixelsPerSecond + 'px' }"
    @mousedown.stop="startDrag"
  >
    <!-- 左裁剪手柄 -->
    <div class="clip-handle left" @mousedown.stop="startTrimLeft" />
    <!-- 片段内容 -->
    <div class="clip-content">
      <span class="clip-text">{{ clipText }}</span>
    </div>
    <!-- 右裁剪手柄 -->
    <div class="clip-handle right" @mousedown.stop="startTrimRight" />
    <!-- 转场标记 -->
    <div v-if="clip.transition_type !== 'none'" class="transition-marker">
      {{ clip.transition_type }} ({{ clip.transition_duration }}s)
    </div>
  </div>
</template>
```

- [ ] **Step 5: 创建 TimelineToolbar.vue（工具栏）**

```vue
<template>
  <div class="timeline-toolbar">
    <div class="left-tools">
      <el-button @click="$emit('init')">
        <el-icon><Refresh /></el-icon>
        初始化时间线
      </el-button>
      <el-button @click="$emit('generate-subtitles')">
        <el-icon><ChatLineSquare /></el-icon>
        生成字幕
      </el-button>
      <el-button @click="$emit('subtitle-style')">
        <el-icon><Setting /></el-icon>
        字幕样式
      </el-button>
    </div>
    <div class="right-tools">
      <span class="total-duration">总时长: {{ formatTime(totalDuration) }}</span>
      <el-button type="primary" :loading="mergeLoading" @click="$emit('merge')">
        <el-icon><VideoCamera /></el-icon>
        合成视频
      </el-button>
    </div>
  </div>
</template>
```

- [ ] **Step 6: 创建 ClipPropertyPanel.vue（属性面板）**

```vue
<template>
  <el-drawer v-model="visible" title="片段属性" size="400px">
    <el-form :model="formData" label-width="100px">
      <el-form-item label="起始时间">
        <el-input-number v-model="formData.start_time" :precision="1" :step="0.1" :min="0" @change="emitUpdate" />
      </el-form-item>
      <el-form-item label="时长">
        <el-input-number v-model="formData.duration" :precision="1" :step="0.1" :min="0.1" @change="emitUpdate" />
      </el-form-item>
      <el-form-item label="裁剪起始">
        <el-input-number v-model="formData.trim_start" :precision="1" :step="0.1" :min="0" @change="emitUpdate" />
      </el-form-item>
      <el-form-item label="转场类型">
        <el-select v-model="formData.transition_type" @change="emitUpdate">
          <el-option label="无" value="none" />
          <el-option label="淡入淡出" value="fade" />
          <el-option label="滑动" value="slide" />
          <el-option label="擦除" value="wipe" />
          <el-option label="溶解" value="dissolve" />
        </el-select>
      </el-form-item>
      <el-form-item label="转场时长">
        <el-input-number v-model="formData.transition_duration" :precision="1" :step="0.1" :min="0" :max="2" @change="emitUpdate" />
      </el-form-item>
      <el-form-item v-if="clip.track_type === 'subtitle'" label="字幕文本">
        <el-input v-model="formData.subtitle_text" type="textarea" @change="emitUpdate" />
      </el-form-item>
    </el-form>
  </el-drawer>
</template>
```

- [ ] **Step 7: 创建 SubtitleStyleDialog.vue（字幕样式对话框）**

```vue
<template>
  <el-dialog v-model="visible" title="字幕样式" width="500px">
    <el-form :model="formData" label-width="100px">
      <el-form-item label="字体">
        <el-input v-model="formData.font_family" />
      </el-form-item>
      <el-form-item label="字号">
        <el-input-number v-model="formData.font_size" :min="12" :max="120" />
      </el-form-item>
      <el-form-item label="字体颜色">
        <el-color-picker v-model="formData.font_color" />
      </el-form-item>
      <el-form-item label="描边颜色">
        <el-color-picker v-model="formData.outline_color" />
      </el-form-item>
      <el-form-item label="描边宽度">
        <el-input-number v-model="formData.outline_width" :min="0" :max="10" />
      </el-form-item>
      <el-form-item label="位置">
        <el-select v-model="formData.position">
          <el-option label="底部" value="bottom" />
          <el-option label="顶部" value="top" />
          <el-option label="居中" value="center" />
        </el-select>
      </el-form-item>
      <el-form-item label="垂直边距">
        <el-input-number v-model="formData.margin_vertical" :min="0" :max="300" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" @click="handleSave">保存</el-button>
    </template>
  </el-dialog>
</template>
```

- [ ] **Step 8: 创建 VoicePickerDialog.vue（音色选择对话框）**

```vue
<template>
  <el-dialog v-model="visible" title="选择音色" width="600px">
    <el-radio-group v-model="selectedVoiceId">
      <div v-for="voice in voices" :key="voice.voice_id" class="voice-option">
        <el-radio :value="voice.voice_id">
          <div class="voice-info">
            <span class="voice-name">{{ voice.name }}</span>
            <el-tag size="small" :type="voice.gender === 'male' ? 'info' : 'danger'">
              {{ voice.gender === 'male' ? '男' : voice.gender === 'female' ? '女' : '中' }}
            </el-tag>
            <span class="voice-suitable">{{ voice.suitable_for }}</span>
          </div>
        </el-radio>
      </div>
    </el-radio-group>
    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" :disabled="!selectedVoiceId" @click="handleConfirm">确认</el-button>
    </template>
  </el-dialog>
</template>
```

- [ ] **Step 9: 验证组件加载**

Run: `cd /Users/skywing/agnes-platform/frontend && npx vue-tsc --noEmit 2>&1 | grep -E "timeline|Timeline" | head -20`
Expected: 无类型错误

- [ ] **Step 10: 提交**

```bash
git add frontend/src/components/project/TimelineTab.vue frontend/src/components/project/timeline/
git commit -m "feat(project-phase2): 新增时间线编辑器组件群（编辑器/轨道/片段/工具栏/属性面板）"
```

---

## Task 10: 集成到项目详情页

**Files:**
- Modify: `frontend/src/components/project/ProjectManagerView.vue`
- Modify: `frontend/src/i18n/zh-CN.ts`
- Modify: `frontend/src/i18n/en-US.ts`
- Modify: `frontend/src/components/project/ShotsTab.vue`（分镜卡片增加音频槽）

- [ ] **Step 1: 在 ProjectManagerView.vue 新增时间线 Tab**

```vue
<el-tabs v-model="activeTab" type="border-card">
  <el-tab-pane name="script" :label="t('project.tabs.script') + badge(0)">...</el-tab-pane>
  <el-tab-pane name="character" :label="t('project.tabs.character') + badge(1)">...</el-tab-pane>
  <el-tab-pane name="scene" :label="t('project.tabs.scene') + badge(2)">...</el-tab-pane>
  <el-tab-pane name="prop" :label="t('project.tabs.prop') + badge(3)">...</el-tab-pane>
  <el-tab-pane name="shot" :label="t('project.tabs.shot') + badge(4)">...</el-tab-pane>
  <!-- Phase 2 新增 -->
  <el-tab-pane name="timeline" :label="t('project.tabs.timeline')">
    <TimelineTab v-if="activeTab === 'timeline'" />
  </el-tab-pane>
</el-tabs>
```

- [ ] **Step 2: 在 ShotsTab.vue 分镜卡片增加音频槽**

在 `ShotCard.vue` 中新增"音频"素材槽（与帧图/视频并列）：

```vue
<div class="shot-assets">
  <!-- 帧图槽（已有） -->
  <div class="asset-slot frame-image">...</div>
  <!-- 视频槽（已有） -->
  <div class="asset-slot video">...</div>
  <!-- Phase 2: 音频槽 -->
  <div class="asset-slot audio">
    <el-button v-if="!activeAudio" size="small" @click="$emit('generate-tts', shot.id)">
      <el-icon><Microphone /></el-icon>
      生成配音
    </el-button>
    <div v-else class="audio-info">
      <el-icon><VideoPlay /></el-icon>
      <span>{{ activeAudio.voice_name || 'TTS' }}</span>
      <span class="duration">{{ formatDuration(activeAudio.duration_ms) }}</span>
    </div>
  </div>
</div>
```

- [ ] **Step 3: 在 i18n 中新增 Phase 2 相关键**

zh-CN.ts:

```typescript
project: {
  tabs: {
    // ... 已有 ...
    timeline: '时间线',
  },
  timeline: {
    title: '时间线编辑器',
    init: '初始化时间线',
    generateSubtitles: '生成字幕',
    subtitleStyle: '字幕样式',
    merge: '合成视频',
    totalDuration: '总时长',
    empty: '时间线未初始化，请点击工具栏的『初始化时间线』按钮',
    trackVideo: '视频轨',
    trackAudio: '音频轨',
    trackSubtitle: '字幕轨',
    clipProperty: '片段属性',
    startTime: '起始时间',
    duration: '时长',
    trimStart: '裁剪起始',
    transitionType: '转场类型',
    transitionDuration: '转场时长',
    subtitleText: '字幕文本',
    subtitleStyleTitle: '字幕样式',
    fontFamily: '字体',
    fontSize: '字号',
    fontColor: '字体颜色',
    outlineColor: '描边颜色',
    outlineWidth: '描边宽度',
    position: '位置',
    positionBottom: '底部',
    positionTop: '顶部',
    positionCenter: '居中',
    marginVertical: '垂直边距',
    voicePicker: '选择音色',
    generateTts: '生成配音',
    batchGenerateTts: '批量生成配音',
    ttsFailed: '配音生成失败',
    subtitleGenerated: '字幕已生成',
    timelineInitialized: '时间线已初始化',
  },
}
```

en-US.ts 同步翻译。

- [ ] **Step 4: 验证前端构建**

Run: `cd /Users/skywing/agnes-platform/frontend && npx vue-tsc --noEmit 2>&1 | head -30`
Expected: 无新增类型错误

- [ ] **Step 5: 提交**

```bash
git add frontend/src/components/project/ProjectManagerView.vue frontend/src/components/project/ShotsTab.vue frontend/src/components/project/ShotCard.vue frontend/src/i18n/zh-CN.ts frontend/src/i18n/en-US.ts
git commit -m "feat(project-phase2): 集成时间线 Tab 到项目详情页 + 分镜卡片增加音频槽"
```

---

## Task 11: 最终验证

- [ ] **Step 1: 后端启动验证**

Run: `cd /Users/skywing/agnes-platform/backend && source .venv/bin/activate && python -c "import app.main; print('OK: backend imports successfully')"`
Expected: `OK: backend imports successfully`

- [ ] **Step 2: 前端类型检查**

Run: `cd /Users/skywing/agnes-platform/frontend && npx vue-tsc --noEmit 2>&1 | tail -20`
Expected: 无 Phase 2 相关错误

- [ ] **Step 3: 数据库表初始化验证**

Run: `cd /Users/skywing/agnes-platform/backend && source .venv/bin/activate && python -c "
from app.core.database import engine
from app.models.project import ProjectShotAudio, ProjectCharacterVoice, ProjectTimelineClip
print('3 张新表模型已加载')
print(f'ProjectShotAudio 表名: {ProjectShotAudio.__tablename__}')
print(f'ProjectCharacterVoice 表名: {ProjectCharacterVoice.__tablename__}')
print(f'ProjectTimelineClip 表名: {ProjectTimelineClip.__tablename__}')
"`
Expected: 三张表模型正常加载

- [ ] **Step 4: 路由完整性验证**

Run: `cd /Users/skywing/agnes-platform/backend && source .venv/bin/activate && python -c "
from app.routes.projects import router
routes = [(r.path, list(r.methods)) for r in router.routes if hasattr(r, 'methods')]
print(f'项目路由总数: {len(routes)}')
tts_routes = [r for r in routes if 'audio' in r[0] or 'voice' in r[0] or 'timeline' in r[0] or 'subtitle' in r[0]]
print(f'Phase 2 新增路由数: {len(tts_routes)}')
for path, methods in tts_routes:
    print(f'  {methods} {path}')
"`
Expected: Phase 2 新增约 20 个路由

- [ ] **Step 5: 提交**

```bash
git add -A
git commit -m "feat(project-phase2): Phase 2 完整实施（时间线 + TTS + 字幕 + 多轨合成）"
```

---

## Self-Review

**1. Spec 覆盖检查：**

| Spec 章节 | 对应 Task |
|----------|----------|
| 4.2.10 project_shot_audios | Task 1 |
| 4.2.11 project_character_voices | Task 1 |
| 4.2.12 project_timeline_clips | Task 1 |
| 7.1-7.3 时间线编辑器 | Task 5, 9 |
| 7.4 TTS 配音生成 | Task 3 |
| 7.5 字幕生成与编辑 | Task 4 |
| 7.6 视频合成（多轨） | Task 6 |
| 7.7 内置 BGM 库 | Task 3（内置音色库，BGM 后续） |
| 9.6 时间线 API | Task 7 |
| 15.2 Phase 2 验收 | Task 11 |

**2. Phase 1 兼容性：**

- 保留原 `execute_merge` 函数作为简单合成回退（`use_timeline=False`）
- `merge_project` 新增参数有默认值，不破坏现有调用
- `ProjectManagerView` 新增 Tab 不影响已有 5 个 Tab
- `ProjectShot.active_audio_id` 在前端类型中补齐，后端已预留

**3. 关键风险缓解：**

- **TTS provider 未知**：`_call_tts_provider` 设计为可插拔，先抛 NotImplementedError，后续接入 Agnes 自有 TTS 或第三方（阿里云/字节火山）
- **ffmpeg 复杂合成**：分阶段实现，Phase 2 先实现 concat + 字幕烧录，转场 xfade 后续优化
- **时间线数据结构**：使用 `project_timeline_clips` 表 + `projects.timeline_data` JSON 双存（clips 表存最终时间线，JSON 存草稿和字幕样式）

**4. 类型一致性：**

- 后端 Schema 字段名 ↔ 前端 TS 类型字段名（snake_case）一致
- SSE 事件类型在后端 `sse_manager.push` ↔ 前端 `useProjectSSE` 一致
- API 路径在后端路由 ↔ 前端 `api/projects.ts` 一致

---

## Phase 2 验收标准（对应 spec 15.2）

- [x] TTS 配音生成 + 音色按角色固定
- [x] 时间线编辑器：多轨视频/音频/字幕
- [x] 拖拽片段、裁剪、转场配置
- [x] 字幕从对白自动生成 + 可编辑
- [x] ffmpeg 合成：视频 + 音频 + 字幕烧录
- [x] 内置音色库 + 内置 BGM 库

---

## 竞品分析 P0 三项纳入情况

> 用户在回望时确认竞品分析（[docs/competitive-analysis-and-improvement-plan.md](file:///Users/skywing/agnes-platform/docs/competitive-analysis-and-improvement-plan.md)）中的 P0 三项已纳入 Phase 2 一起实施，全部完成。

### P0-1: 转场特效系统（xfade）

- **实现位置**：`backend/app/services/project/merge_service.py` — `_concat_videos_with_xfade`
- **能力**：支持 `fade / slide / wipe / dissolve` 四种转场，逐对拼接策略（先 normalize scale+setsar+fps，再 probe durations，最后逐对 xfade）
- **配置入口**：前端 `TimelineClip.vue` 片段上显示转场标记；`ClipPropertyPanel.vue` 提供转场类型/时长编辑
- **数据存储**：`project_timeline_clips.transition_type` / `transition_duration`
- **状态**：✅ 已完成

### P0-2: BGM 内置库

- **实现位置**：`backend/app/services/project/bgm_library.py`
- **能力**：5 首 BGM（warm_piano / corporate / dramatic / uplifting / sad）+ 5 种情绪分类（calm / corporate / dramatic / uplifting / sad）+ 文件缺失警告
- **API**：`GET /api/projects/{pid}/bgms` / `GET /api/projects/{pid}/bgms/moods`
- **配置入口**：前端 `BgmPickerDialog.vue` 按情绪过滤 + 试听 + 选中/清除
- **合成集成**：`MergeAdvancedRequest.with_bgm` + `bgm_id` + `use_timeline` 参数
- **状态**：✅ 已完成（注：BGM 文件需放到 `backend/assets/bgm/` 目录才能实际播放/合成）

### P0-3: 字幕双模式（LLM / Whisper）

- **实现位置**：`backend/app/services/project/subtitle_service.py`
- **能力**：
  - `mode='llm'`：基于台词 + 时长按比例分配生成 SRT（默认模式，无外部依赖）
  - `mode='whisper'`：使用 faster-whisper 对 TTS 音频做本地强制对齐，获取 segment-level 时间戳，更精确
  - `is_whisper_available()` 检测本地是否安装 faster-whisper，自动回退 LLM
- **API**：
  - `POST /api/projects/{pid}/subtitles/generate`（LLM 模式）
  - `POST /api/projects/{pid}/subtitles/generate-whisper`（Whisper 模式）
  - `GET /api/projects/{pid}/subtitles/whisper-available`
- **配置入口**：前端 `TimelineToolbar.vue` 的「生成字幕」/「Whisper 字幕」按钮，Whisper 不可用时自动禁用
- **字幕样式**：`SubtitleStyleDialog.vue` 编辑字体/字号/颜色/描边/位置/边距，实时预览
- **状态**：✅ 已完成

### P1 项（任务失败自动重试）

- **状态**：⏸️ 暂未实现，留待 Phase 3 处理。当前任务失败后由用户手动重试，可通过任务队列面板查看失败状态

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-07-05-project-based-creation-refactor-phase2.md`.**

**建议执行顺序：** Task 1 → 2 → 3/4/5（可并行）→ 6 → 7 → 8 → 9 → 10 → 11

**关键依赖：**
- Task 3（TTS）的 `_call_tts_provider` 需要确认 Agnes AI 是否提供 TTS API，若无则需接入第三方
- Task 6（合成扩展）依赖 Task 5（时间线服务）和 Task 4（字幕服务）
- Task 9（前端编辑器）依赖 Task 8（前端类型/API/Store）

**两种执行方式：**
1. **Subagent-Driven（推荐）** - 每个 Task 派发独立 subagent，Task 间审查
2. **Inline Execution** - 当前会话顺序执行，带检查点
