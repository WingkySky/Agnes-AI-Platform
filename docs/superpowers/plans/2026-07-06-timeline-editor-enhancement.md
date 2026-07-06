# 时间线编辑器增强实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为时间线编辑器添加项目素材库（拖拽到时间线）、弹性三区布局（素材库/预览/时间线可调整）、复制剪切粘贴、标记 Markers、轨道 Mute/Lock 五项核心功能。

**Architecture:** 后端新增 `project_markers` 表 + `source_ref` 字段 + 3 个素材库/标记 API 端点，扩展 `get_timeline_data` 支持新 source_type。前端新增 `MediaLibraryPanel` + `TimelineSplitter` + 4 个 composable，重构 `TimelineTab` 为弹性三区布局。

**Tech Stack:** FastAPI + SQLAlchemy async + httpx（后端）；Vue 3 + Element Plus + Pinia + localforage（前端）。

**Spec 文档:** [2026-07-06-timeline-editor-enhancement-design.md](file:///Users/skywing/agnes-platform/docs/superpowers/specs/2026-07-06-timeline-editor-enhancement-design.md)

---

## 文件结构

### 后端

| 文件 | 责任 | 改动类型 |
|---|---|---|
| `backend/app/models/project.py` | 新增 `ProjectMarker` 模型；`ProjectTimelineClip` 加 `source_ref` 字段 | 修改 |
| `backend/app/schemas/project.py` | 新增 `MediaLibraryItem` / `MediaLibraryResponse` / `MarkerCreate` / `MarkerResponse` schema；`TimelineClipResponse/Create` 加 `source_ref` | 修改 |
| `backend/app/services/project/timeline_service.py` | 新增 `get_media_library` 函数；扩展 `get_timeline_data` 预取 `shot_frame_image` / `bgm` | 修改 |
| `backend/app/services/project/marker_service.py` | 新增 marker_service（CRUD） | 新建 |
| `backend/app/routes/projects.py` | 新增 `/media-library` `/bgms/{bgm_id}/file` `/markers` 路由 | 修改 |
| `backend/app/services/project/merge_service.py` | 扩展支持 `shot_frame_image` / `bgm` source_type | 修改 |

### 前端

| 文件 | 责任 | 改动类型 |
|---|---|---|
| `frontend/src/types/project.ts` | 新增 `MediaLibraryItem` / `MediaLibraryResponse` / `ProjectMarker` / `TrackState` / `TimelineLayoutState` 类型；`TimelineClip` 加 `source_ref` | 修改 |
| `frontend/src/api/projects.ts` | 新增 `getMediaLibrary` / `getBgmFileUrl` / `listMarkers` / `createMarker` / `deleteMarker` | 修改 |
| `frontend/src/stores/project.ts` | 新增 `mediaLibrary` / `markers` / `trackStates` state 和 actions | 修改 |
| `frontend/src/composables/useTimelineLayout.ts` | 弹性布局状态 + localforage 持久化 | 新建 |
| `frontend/src/composables/useClipClipboard.ts` | 复制/剪切/粘贴剪贴板 | 新建 |
| `frontend/src/composables/useMarkers.ts` | 标记 CRUD + 快捷键 | 新建 |
| `frontend/src/composables/useTrackStates.ts` | 轨道 Mute/Lock 状态管理 | 新建 |
| `frontend/src/components/project/timeline/MediaLibraryPanel.vue` | 素材库面板（左侧抽屉，4 类 Tab） | 新建 |
| `frontend/src/components/project/timeline/TimelineSplitter.vue` | 可拖拽分隔条组件（复用） | 新建 |
| `frontend/src/components/project/timeline/MarkersRuler.vue` | 标记旗帜渲染 | 新建 |
| `frontend/src/components/project/timeline/TrackHeaderControls.vue` | 轨道头部 M/L 按钮 | 新建 |
| `frontend/src/components/project/timeline/TimelineTab.vue` | 重构为弹性三区布局；接入新功能 | 修改 |
| `frontend/src/components/project/timeline/TimelineEditor.vue` | 标尺加 MarkersRuler；轨道头部加 TrackHeaderControls；轨道支持 drop 事件 | 修改 |
| `frontend/src/components/project/timeline/TimelineTrack.vue` | 检查 trackStates.locked 拦截拖拽；轨道头部加按钮 | 修改 |
| `frontend/src/composables/useTimelinePreview.ts` | 播放时检查 trackStates.muted 跳过该轨音频 | 修改 |

---

## Task 1: 后端新增 ProjectMarker 模型 + source_ref 字段

**Files:**
- Modify: `backend/app/models/project.py`（在文件末尾追加 `ProjectMarker` 类，并在 `ProjectTimelineClip` 加 `source_ref` 字段）

- [ ] **Step 1: 在 `ProjectTimelineClip` 类中 `sort_order` 字段后添加 `source_ref` 字段**

在 `backend/app/models/project.py` 第 573 行 `sort_order = Column(Integer, default=0, nullable=False)` 后追加：

```python
    source_ref = Column(String(100), nullable=True)  # BGM 字符串 id 引用（source_id 是 Integer 不够用）
```

同步更新 `ProjectTimelineClip` 类的 docstring，把 `source_type` 注释从 `shot_video/shot_audio/bgm/subtitle` 改为 `shot_video/shot_audio/shot_frame_image/bgm/subtitle`。

- [ ] **Step 2: 在文件末尾追加 `ProjectMarker` 类**

```python
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
```

- [ ] **Step 3: 验证后端启动 + 自动迁移生效**

```bash
cd /Users/skywing/agnes-platform/backend
python -c "from app.main import app; from app.models.project import ProjectMarker, ProjectTimelineClip; print('OK:', ProjectMarker.__tablename__, hasattr(ProjectTimelineClip, 'source_ref'))"
```

Expected: `OK: project_markers True`

- [ ] **Step 4: 验证数据库表已创建 + 字段已添加**

```bash
sqlite3 /Users/skywing/agnes-platform/backend/agnes_platform.db ".schema project_markers"
sqlite3 /Users/skywing/agnes-platform/backend/agnes_platform.db "PRAGMA table_info(project_timeline_clips);" | grep source_ref
```

Expected: `project_markers` 表有完整 schema；`project_timeline_clips` 含 `source_ref` 列。

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/project.py
git commit -m "feat(models): 新增 ProjectMarker 表 + ProjectTimelineClip.source_ref 字段"
```

---

## Task 2: 后端新增 Schema（MediaLibrary + Marker + source_ref）

**Files:**
- Modify: `backend/app/schemas/project.py`

- [ ] **Step 1: 在 `TimelineClipResponse` 类中添加 `source_ref` 字段**

在 `backend/app/schemas/project.py` 第 619 行 `source_thumbnail_url: Optional[str] = None` 后追加：

```python
    source_ref: Optional[str] = None  # BGM 字符串 id（source_id 是 Integer 不够用时使用）
```

- [ ] **Step 2: 在 `TimelineClipCreate` 和 `TimelineClipUpdate` 类中添加 `source_ref` 字段**

在 `TimelineClipCreate`（第 622 行）的 `sort_order: int = 0` 后追加：

```python
    source_ref: Optional[str] = None
```

在 `TimelineClipUpdate`（第 639 行）的 `sort_order: Optional[int] = None` 后追加：

```python
    source_ref: Optional[str] = None
```

- [ ] **Step 3: 在文件末尾追加素材库和标记相关 Schema**

```python
# ---------- 素材库（Phase 2 增强） ----------

class MediaLibraryItem(BaseModel):
    """素材库统一项结构（用于拖拽到时间线）"""
    id: int
    type: str  # shot_video / shot_audio / shot_frame_image / bgm
    name: str
    file_url: str
    thumbnail_url: Optional[str] = None
    duration_ms: int
    width: Optional[int] = None
    height: Optional[int] = None
    shot_id: Optional[int] = None
    meta: Optional[Dict[str, Any]] = None


class MediaLibraryResponse(BaseModel):
    """素材库按类型分组的响应"""
    videos: List[MediaLibraryItem]
    audios: List[MediaLibraryItem]
    frame_images: List[MediaLibraryItem]
    bgms: List[MediaLibraryItem]


# ---------- 标记 Markers（Phase 2 增强） ----------

class MarkerCreate(BaseModel):
    """创建标记请求"""
    time: float = Field(..., ge=0, description="标记时间（秒）")
    name: Optional[str] = Field(None, max_length=100)
    color: str = Field("#4a9eff", max_length=20)


class MarkerResponse(BaseModel):
    """标记响应"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    time: float
    name: Optional[str] = None
    color: str
    created_at: Optional[datetime] = None
```

- [ ] **Step 4: 验证 import 成功**

```bash
cd /Users/skywing/agnes-platform/backend
python -c "from app.schemas.project import MediaLibraryItem, MediaLibraryResponse, MarkerCreate, MarkerResponse, TimelineClipResponse; print('OK:', hasattr(TimelineClipResponse, 'model_fields') and 'source_ref' in TimelineClipResponse.model_fields)"
```

Expected: `OK: True`

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/project.py
git commit -m "feat(schemas): 新增 MediaLibrary / Marker schema + TimelineClip 加 source_ref"
```

---

## Task 3: 后端 marker_service 实现

**Files:**
- Create: `backend/app/services/project/marker_service.py`

- [ ] **Step 1: 创建 marker_service.py**

```python
# =====================================================
# 标记 Markers 服务 — Phase 2 增强
#
# 职责:
#   - 标记 CRUD（创建/列出/删除）
#   - 标记按时间排序
# =====================================================

from typing import List, Optional
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import ProjectMarker


async def list_markers(db: AsyncSession, project_id: int) -> List[ProjectMarker]:
    """列出项目的所有标记（按时间升序）"""
    result = await db.execute(
        select(ProjectMarker)
        .where(ProjectMarker.project_id == project_id)
        .order_by(ProjectMarker.time.asc())
    )
    return list(result.scalars().all())


async def create_marker(
    db: AsyncSession, project_id: int,
    time: float, name: Optional[str] = None, color: str = "#4a9eff",
) -> ProjectMarker:
    """创建标记"""
    marker = ProjectMarker(
        project_id=project_id,
        time=time,
        name=name,
        color=color,
    )
    db.add(marker)
    await db.commit()
    await db.refresh(marker)
    return marker


async def delete_marker(db: AsyncSession, project_id: int, marker_id: int) -> bool:
    """删除标记（校验 project_id 防越权）"""
    result = await db.execute(
        delete(ProjectMarker)
        .where(ProjectMarker.id == marker_id)
        .where(ProjectMarker.project_id == project_id)
    )
    await db.commit()
    return result.rowcount > 0


async def find_nearest_marker(
    db: AsyncSession, project_id: int, time: float
) -> Optional[ProjectMarker]:
    """找到离指定时间最近的标记（用于 Shift+M 删除最近标记）"""
    markers = await list_markers(db, project_id)
    if not markers:
        return None
    return min(markers, key=lambda m: abs(m.time - time))
```

- [ ] **Step 2: 验证 import 成功**

```bash
cd /Users/skywing/agnes-platform/backend
python -c "from app.services.project.marker_service import list_markers, create_marker, delete_marker, find_nearest_marker; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/project/marker_service.py
git commit -m "feat(services): 新增 marker_service（标记 CRUD）"
```

---

## Task 4: 后端 timeline_service 新增 get_media_library + 扩展 get_timeline_data

**Files:**
- Modify: `backend/app/services/project/timeline_service.py`

- [ ] **Step 1: 在文件顶部 import 区追加 `ProjectShotFrameImage` 和 `ProjectMarker`**

读取文件顶部 import 区，确认现有 import 后追加：

```python
from app.models.project import (
    # ... 现有 import ...
    ProjectShotFrameImage,  # 新增
)
from app.services.project.bgm_library import list_bgms, get_bgm_by_id  # 新增
```

注意：如果 `ProjectShotFrameImage` 已在现有 import 中则跳过。

- [ ] **Step 2: 在 `get_timeline_data` 函数中扩展预取 `shot_frame_image` 类型的源信息**

在 `timeline_service.py` 的 `get_timeline_data` 函数中（约第 373 行），把现有的 `video_ids` / `audio_ids` 预取块扩展为：

```python
    # 批量预取视频/音频/帧图源数据，避免逐 clip N+1 查询
    video_ids = {c.source_id for c in clips if c.source_type == "shot_video" and c.source_id}
    audio_ids = {c.source_id for c in clips if c.source_type == "shot_audio" and c.source_id}
    frame_image_ids = {c.source_id for c in clips if c.source_type == "shot_frame_image" and c.source_id}

    video_map: Dict[int, ProjectShotVideo] = {}
    audio_map: Dict[int, ProjectShotAudio] = {}
    frame_image_map: Dict[int, ProjectShotFrameImage] = {}

    if video_ids:
        rows = (
            await db.execute(
                select(ProjectShotVideo).where(ProjectShotVideo.id.in_(video_ids))
            )
        ).scalars().all()
        video_map = {v.id: v for v in rows}

    if audio_ids:
        rows = (
            await db.execute(
                select(ProjectShotAudio).where(ProjectShotAudio.id.in_(audio_ids))
            )
        ).scalars().all()
        audio_map = {a.id: a for a in rows}

    if frame_image_ids:
        rows = (
            await db.execute(
                select(ProjectShotFrameImage).where(ProjectShotFrameImage.id.in_(frame_image_ids))
            )
        ).scalars().all()
        frame_image_map = {f.id: f for f in rows}
```

然后在序列化循环中（约第 422 行 `if c.source_type == "shot_video" ...` 块后）追加 `shot_frame_image` 和 `bgm` 的处理：

```python
        elif c.source_type == "shot_frame_image" and c.source_id and c.source_id in frame_image_map:
            f = frame_image_map[c.source_id]
            item["source_file_url"] = f.file_url
            item["source_duration_ms"] = int(c.duration * 1000)  # 静态图无 duration_ms，用片段 duration 反推
            item["source_width"] = f.width
            item["source_height"] = f.height
            item["source_thumbnail_url"] = f.thumbnail_url
        elif c.source_type == "bgm" and c.source_ref:
            # BGM 通过 source_ref 字符串引用，url 由前端拼接 /bgms/{bgm_id}/file
            bgm = get_bgm_by_id(c.source_ref)
            if bgm:
                item["source_file_url"] = f"/api/projects/{project_id}/bgms/{c.source_ref}/file"
                item["source_duration_ms"] = int(bgm["duration"] * 1000)
```

- [ ] **Step 3: 在文件末尾追加 `get_media_library` 函数**

```python
async def get_media_library(db: AsyncSession, project_id: int) -> Dict[str, Any]:
    """
    获取项目素材库（4 类素材聚合）— Phase 2 增强

    返回:
    - videos: 分镜视频列表（按 shot.sort_order 排序）
    - audios: 配音音频列表
    - frame_images: 帧图列表（静态图，duration_ms 默认 3000）
    - bgms: BGM 库（含 file_url）
    """
    # 查所有分镜（带排序）
    shots = (
        await db.execute(
            select(ProjectShot)
            .where(ProjectShot.project_id == project_id)
            .order_by(ProjectShot.sort_order.asc())
        )
    ).scalars().all()
    shot_map = {s.id: s for s in shots}

    # 查所有视频（关联分镜的 active_video_id）
    active_video_ids = [s.active_video_id for s in shots if s.active_video_id]
    videos: List[Dict[str, Any]] = []
    if active_video_ids:
        rows = (
            await db.execute(
                select(ProjectShotVideo).where(ProjectShotVideo.id.in_(active_video_ids))
            )
        ).scalars().all()
        for v in rows:
            shot = shot_map.get(v.shot_id)
            videos.append({
                "id": v.id,
                "type": "shot_video",
                "name": f"分镜{(shot.sequence_no if shot else '?')}视频",
                "file_url": v.file_url or "",
                "thumbnail_url": v.thumbnail_url,
                "duration_ms": v.duration_ms or 3000,
                "width": v.width,
                "height": v.height,
                "shot_id": v.shot_id,
                "meta": {},
            })

    # 查所有音频（关联分镜的 active_audio_id）
    active_audio_ids = [s.active_audio_id for s in shots if s.active_audio_id]
    audios: List[Dict[str, Any]] = []
    if active_audio_ids:
        rows = (
            await db.execute(
                select(ProjectShotAudio).where(ProjectShotAudio.id.in_(active_audio_ids))
            )
        ).scalars().all()
        for a in rows:
            shot = shot_map.get(a.shot_id)
            audios.append({
                "id": a.id,
                "type": "shot_audio",
                "name": f"分镜{(shot.sequence_no if shot else '?')}配音",
                "file_url": a.file_url or "",
                "thumbnail_url": None,
                "duration_ms": a.duration_ms or 3000,
                "width": None,
                "height": None,
                "shot_id": a.shot_id,
                "meta": {"voice_name": a.voice_name},
            })

    # 查所有帧图（active_frame_image_id，duration_ms 默认 3000）
    active_frame_ids = [s.active_frame_image_id for s in shots if s.active_frame_image_id]
    frame_images: List[Dict[str, Any]] = []
    if active_frame_ids:
        rows = (
            await db.execute(
                select(ProjectShotFrameImage).where(ProjectShotFrameImage.id.in_(active_frame_ids))
            )
        ).scalars().all()
        for f in rows:
            shot = shot_map.get(f.shot_id)
            frame_images.append({
                "id": f.id,
                "type": "shot_frame_image",
                "name": f"分镜{(shot.sequence_no if shot else '?')}帧图",
                "file_url": f.file_url or "",
                "thumbnail_url": f.thumbnail_url,
                "duration_ms": 3000,  # 静态图默认 3 秒
                "width": f.width,
                "height": f.height,
                "shot_id": f.shot_id,
                "meta": {"is_static_image": True},
            })

    # BGM 库（含 file_url 路径）
    bgm_list = list_bgms()
    bgms: List[Dict[str, Any]] = []
    for b in bgm_list:
        if not b.get("available"):
            continue
        bgms.append({
            "id": abs(hash(b["id"])) % (10**9),  # 字符串 id 转数字 id 供前端使用
            "type": "bgm",
            "name": b["name"],
            "file_url": f"/api/projects/{project_id}/bgms/{b['id']}/file",
            "thumbnail_url": None,
            "duration_ms": int(b["duration"] * 1000),
            "width": None,
            "height": None,
            "shot_id": None,
            "meta": {"mood": b["mood"], "bgm_id": b["id"]},  # bgm_id 字符串存在 meta
        })

    return {
        "videos": videos,
        "audios": audios,
        "frame_images": frame_images,
        "bgms": bgms,
    }
```

- [ ] **Step 4: 验证 import 成功**

```bash
cd /Users/skywing/agnes-platform/backend
python -c "from app.services.project.timeline_service import get_media_library, get_timeline_data; print('OK')"
```

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/project/timeline_service.py
git commit -m "feat(timeline): 新增 get_media_library + 扩展 get_timeline_data 支持新 source_type"
```

---

## Task 5: 后端新增路由（media-library + bgm file + markers）

**Files:**
- Modify: `backend/app/routes/projects.py`

- [ ] **Step 1: 在文件顶部 import 区追加 marker_service 和 FileResponse**

在 `backend/app/routes/projects.py` 顶部 import 区（约第 154 行附近）追加：

```python
from app.services.project.marker_service import (
    list_markers as list_project_markers,
    create_marker as create_project_marker,
    delete_marker as delete_project_marker,
    find_nearest_marker as find_nearest_project_marker,
)
from fastapi.responses import FileResponse
```

在 schema import 区追加：

```python
from app.schemas.project import (
    # ... 现有 import ...
    MediaLibraryResponse, MarkerCreate, MarkerResponse,
)
from app.services.project.timeline_service import get_media_library
```

- [ ] **Step 2: 在 BGM 路由区（第 2200 行 `list_bgm_moods_api` 后）追加 BGM 文件端点**

```python
@router.get(
    "/{project_id}/bgms/{bgm_id}/file",
    summary="BGM 文件 HTTP URL（供前端预览/拖拽使用）",
)
async def get_bgm_file_api(
    project_id: int,
    bgm_id: str,
    current_user: User = Depends(get_current_user),
):
    """暴露 BGM 文件 HTTP URL（FileResponse）"""
    from app.services.project.bgm_library import get_bgm_path
    path = get_bgm_path(bgm_id)
    if not path:
        raise HTTPException(status_code=404, detail="BGM 文件不存在")
    return FileResponse(path, media_type="audio/mpeg")
```

- [ ] **Step 3: 在 BGM 路由区后追加 media-library 路由**

```python
# =====================================================
# 18. 素材库（Phase 2 增强）
#    GET  /projects/{id}/media-library   聚合四类素材
# =====================================================

@router.get(
    "/{project_id}/media-library",
    response_model=MediaLibraryResponse,
    summary="项目素材库（4 类素材聚合）",
)
async def get_media_library_api(
    project_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """聚合项目下所有可拖拽到时间线的素材（视频/音频/帧图/BGM）"""
    project = await _get_project_or_404(db, project_id)
    _check_project_owner(project, current_user)
    return await get_media_library(db, project_id)
```

- [ ] **Step 4: 在 media-library 路由后追加 markers 路由组**

```python
# =====================================================
# 19. 标记 Markers（Phase 2 增强）
#    GET    /projects/{id}/markers        列出标记
#    POST   /projects/{id}/markers        创建标记
#    DELETE /projects/{id}/markers/{mid}  删除标记
# =====================================================

@router.get(
    "/{project_id}/markers",
    response_model=List[MarkerResponse],
    summary="列出项目标记",
)
async def list_markers_api(
    project_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project_or_404(db, project_id)
    _check_project_owner(project, current_user)
    return await list_project_markers(db, project_id)


@router.post(
    "/{project_id}/markers",
    response_model=MarkerResponse,
    status_code=201,
    summary="创建标记",
)
async def create_marker_api(
    project_id: int,
    data: MarkerCreate,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project_or_404(db, project_id)
    _check_project_owner(project, current_user)
    return await create_project_marker(
        db, project_id,
        time=data.time, name=data.name, color=data.color,
    )


@router.delete(
    "/{project_id}/markers/{marker_id}",
    summary="删除标记",
)
async def delete_marker_api(
    project_id: int,
    marker_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_project_or_404(db, project_id)
    _check_project_owner(project, current_user)
    ok = await delete_project_marker(db, project_id, marker_id)
    if not ok:
        raise HTTPException(status_code=404, detail="标记不存在")
    return {"status": "ok", "message": "标记已删除"}
```

- [ ] **Step 5: 更新文件顶部路由分组注释（在 17. BGM 库后追加 18. 19.）**

在 `backend/app/routes/projects.py` 顶部注释区第 22 行 `#  17. BGM 库（Phase 2）` 后追加：

```python
#  18. 素材库（Phase 2 增强）: /projects/{id}/media-library
#  19. 标记 Markers（Phase 2 增强）: /projects/{id}/markers[/{mid}]
```

- [ ] **Step 6: 验证后端启动 + 新端点注册**

```bash
cd /Users/skywing/agnes-platform/backend
python -c "from app.main import app; routes = [r.path for r in app.routes]; assert '/api/projects/{project_id}/media-library' in routes, 'media-library missing'; assert '/api/projects/{project_id}/bgms/{bgm_id}/file' in routes, 'bgm file missing'; assert '/api/projects/{project_id}/markers' in routes, 'markers missing'; print('OK')"
```

Expected: `OK`

- [ ] **Step 7: Commit**

```bash
git add backend/app/routes/projects.py
git commit -m "feat(routes): 新增 media-library / bgm file / markers 端点"
```

---

## Task 6: 后端 merge_service 扩展支持 shot_frame_image / bgm

**Files:**
- Modify: `backend/app/services/project/merge_service.py`

- [ ] **Step 1: 读取现有 merge_service.py 的 execute_merge_advanced 函数**

读取 `backend/app/services/project/merge_service.py` 找到片段下载与归一化逻辑，理解现有 `shot_video` / `shot_audio` 的处理方式。

- [ ] **Step 2: 在片段源信息注入逻辑中追加 shot_frame_image 和 bgm 分支**

在 `merge_service.py` 中处理片段源信息的函数（通常在 `execute_merge_advanced` 或辅助函数中）找到 `if clip.source_type == "shot_video"` 等分支，追加：

```python
elif clip.source_type == "shot_frame_image" and clip.source_id:
    # 静态图作视频段：用 -loop 1 -t duration 转视频流
    frame_img = await db.get(ProjectShotFrameImage, clip.source_id)
    if frame_img and frame_img.file_url:
        # 下载帧图到临时文件
        local_path = await _download_to_temp(frame_img.file_url, tmp_dir)
        # 用 ffmpeg 转视频流：-loop 1 -i image -t duration -r 30
        normalized_path = await _normalize_frame_image(local_path, clip.duration, width, height, tmp_dir)
        video_inputs.append(normalized_path)

elif clip.source_type == "bgm" and clip.source_ref:
    # BGM：通过 source_ref 取本地路径
    from app.services.project.bgm_library import get_bgm_path
    bgm_path = get_bgm_path(clip.source_ref)
    if bgm_path:
        audio_inputs.append(bgm_path)
```

- [ ] **Step 3: 新增 `_normalize_frame_image` 辅助函数**

在 merge_service.py 中新增：

```python
async def _normalize_frame_image(
    src_path: str, duration: float,
    target_width: int, target_height: int, tmp_dir: str,
) -> str:
    """把静态图归一化为视频流（-loop 1 -i image -t duration -r 30）"""
    out_path = os.path.join(tmp_dir, f"frame_{uuid4().hex}.mp4")
    # 归一化：scale+pad 到目标尺寸，30fps，libx264 crf=23，-t duration
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", src_path,
        "-t", str(duration),
        "-r", "30",
        "-vf", f"scale={target_width}:{target_height}:force_original_aspect_ratio=decrease,"
               f"pad={target_width}:{target_height}:(ow-iw)/2:(oh-ih)/2,setsar=1",
        "-c:v", "libx264", "-crf", "23", "-pix_fmt", "yuv420p",
        out_path,
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        logger.error("[merge] 静态图归一化失败: %s", stderr.decode())
        raise RuntimeError("frame image normalize failed")
    return out_path
```

- [ ] **Step 4: 验证 import 成功**

```bash
cd /Users/skywing/agnes-platform/backend
python -c "from app.services.project.merge_service import execute_merge_advanced, _normalize_frame_image; print('OK')"
```

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/project/merge_service.py
git commit -m "feat(merge): 扩展 merge_service 支持 shot_frame_image / bgm 源类型"
```

---

## Task 7: 前端 types + api + store 扩展

**Files:**
- Modify: `frontend/src/types/project.ts`
- Modify: `frontend/src/api/projects.ts`
- Modify: `frontend/src/stores/project.ts`

- [ ] **Step 1: 在 types/project.ts 添加新类型**

在 `frontend/src/types/project.ts` 末尾追加：

```typescript
// =====================================================
// 素材库 / 标记 / 轨道状态 / 布局状态（Phase 2 增强）
// =====================================================

/** 素材库项类型 */
export type MediaItemType = 'shot_video' | 'shot_audio' | 'shot_frame_image' | 'bgm'

/** 素材库统一项结构（用于拖拽到时间线） */
export interface MediaLibraryItem {
  id: number
  type: MediaItemType
  name: string
  file_url: string
  thumbnail_url?: string | null
  duration_ms: number
  width?: number | null
  height?: number | null
  shot_id?: number | null
  meta?: {
    voice_name?: string
    mood?: string
    is_static_image?: boolean
    bgm_id?: string  // BGM 字符串 id
  }
}

/** 素材库按类型分组的响应 */
export interface MediaLibraryResponse {
  videos: MediaLibraryItem[]
  audios: MediaLibraryItem[]
  frame_images: MediaLibraryItem[]
  bgms: MediaLibraryItem[]
}

/** 项目标记 */
export interface ProjectMarker {
  id: number
  project_id: number
  time: number
  name?: string | null
  color: string
  created_at?: string
}

/** 标记创建请求 */
export interface MarkerCreateRequest {
  time: number
  name?: string
  color?: string
}

/** 轨道状态（会话级 UI 状态） */
export interface TrackState {
  muted: boolean
  locked: boolean
}

/** 时间线布局状态（localforage 持久化） */
export interface TimelineLayoutState {
  libraryWidth: number
  libraryHidden: boolean
  timelineHeight: number
}
```

同时在 `TimelineClip` interface 中追加：

```typescript
  source_ref?: string | null  // BGM 字符串 id 引用
```

- [ ] **Step 2: 在 api/projects.ts 添加 API 函数**

在 `frontend/src/api/projects.ts` 末尾追加：

```typescript
// =====================================================
// 素材库 / BGM 文件 / 标记 API（Phase 2 增强）
// =====================================================

/** 获取项目素材库（4 类素材聚合） */
export function getMediaLibrary(projectId: number): Promise<MediaLibraryResponse> {
  return client.get(`/api/projects/${projectId}/media-library`)
}

/** BGM 文件 URL 拼接（供拖拽到时间线使用） */
export function getBgmFileUrl(projectId: number, bgmId: string): string {
  return `/api/projects/${projectId}/bgms/${bgmId}/file`
}

/** 列出项目标记 */
export function listMarkers(projectId: number): Promise<ProjectMarker[]> {
  return client.get(`/api/projects/${projectId}/markers`)
}

/** 创建标记 */
export function createMarker(projectId: number, data: MarkerCreateRequest): Promise<ProjectMarker> {
  return client.post(`/api/projects/${projectId}/markers`, data)
}

/** 删除标记 */
export function deleteMarker(projectId: number, markerId: number): Promise<{ status: string; message: string }> {
  return client.delete(`/api/projects/${projectId}/markers/${markerId}`)
}
```

同时在顶部 type import 中追加：

```typescript
  MediaLibraryItem,
  MediaLibraryResponse,
  ProjectMarker,
  MarkerCreateRequest,
```

- [ ] **Step 3: 在 stores/project.ts 添加 state + actions**

在 `frontend/src/stores/project.ts` 的 import 区追加：

```typescript
  getMediaLibrary as apiGetMediaLibrary,
  listMarkers as apiListMarkers,
  createMarker as apiCreateMarker,
  deleteMarker as apiDeleteMarker,
```

在 type import 中追加：

```typescript
  MediaLibraryResponse,
  ProjectMarker,
  MarkerCreateRequest,
  TrackState,
```

在 `ProjectState` interface 中追加：

```typescript
  /* Phase 2 增强 — 素材库 / 标记 / 轨道状态 */
  mediaLibrary: MediaLibraryResponse | null
  markers: ProjectMarker[]
  trackStates: Record<string, TrackState>
```

在 state 初始化中追加：

```typescript
    // Phase 2 增强
    mediaLibrary: null,
    markers: [],
    trackStates: {},
```

在 actions 末尾追加：

```typescript
    // ================ 素材库 ================
    async fetchMediaLibrary() {
      if (!this.currentProjectId) return
      this.mediaLibrary = await apiGetMediaLibrary(this.currentProjectId)
    },

    // ================ 标记 ================
    async fetchMarkers() {
      if (!this.currentProjectId) return
      this.markers = await apiListMarkers(this.currentProjectId)
    },

    async addMarker(data: MarkerCreateRequest) {
      if (!this.currentProjectId) return
      const marker = await apiCreateMarker(this.currentProjectId, data)
      this.markers.push(marker)
      this.markers.sort((a, b) => a.time - b.time)
      return marker
    },

    async removeMarker(markerId: number) {
      if (!this.currentProjectId) return
      await apiDeleteMarker(this.currentProjectId, markerId)
      this.markers = this.markers.filter(m => m.id !== markerId)
    },

    // ================ 轨道状态 ================
    setTrackMuted(trackType: string, trackIndex: number, muted: boolean) {
      const key = `${trackType}:${trackIndex}`
      const cur = this.trackStates[key] || { muted: false, locked: false }
      this.trackStates[key] = { ...cur, muted }
    },

    setTrackLocked(trackType: string, trackIndex: number, locked: boolean) {
      const key = `${trackType}:${trackIndex}`
      const cur = this.trackStates[key] || { muted: false, locked: false }
      this.trackStates[key] = { ...cur, locked }
    },

    isTrackMuted(trackType: string, trackIndex: number): boolean {
      return this.trackStates[`${trackType}:${trackIndex}`]?.muted ?? false
    },

    isTrackLocked(trackType: string, trackIndex: number): boolean {
      return this.trackStates[`${trackType}:${trackIndex}`]?.locked ?? false
    },
```

在 `clearCurrent` 函数中追加：

```typescript
      this.mediaLibrary = null
      this.markers = []
      this.trackStates = {}
```

- [ ] **Step 4: 验证前端类型检查**

```bash
cd /Users/skywing/agnes-platform/frontend
npx vue-tsc --noEmit 2>&1 | grep -E "types/project|api/projects|stores/project" | head -20
```

Expected: 无新增错误（已有错误无关）。

- [ ] **Step 5: Commit**

```bash
git add frontend/src/types/project.ts frontend/src/api/projects.ts frontend/src/stores/project.ts
git commit -m "feat(frontend): 新增素材库/标记/轨道状态类型与 store"
```

---

## Task 8: 前端 useTimelineLayout composable

**Files:**
- Create: `frontend/src/composables/useTimelineLayout.ts`

- [ ] **Step 1: 创建 useTimelineLayout.ts**

```typescript
/* =====================================================
 * 时间线弹性布局状态管理 — Phase 2 增强
 * 职责：
 *   - 素材库宽度 / 隐藏状态 / 时间线高度
 *   - localforage 持久化（按 project_id 分键）
 * ===================================================== */

import { ref, watch } from 'vue'
import localforage from 'localforage'
import type { TimelineLayoutState } from '@/types/project'

const DEFAULT_LAYOUT: TimelineLayoutState = {
  libraryWidth: 240,
  libraryHidden: false,
  timelineHeight: 240,
}

const MIN_LIBRARY_WIDTH = 180
const MAX_LIBRARY_WIDTH = 400
const MIN_TIMELINE_HEIGHT = 120
const MAX_TIMELINE_HEIGHT_RATIO = 0.6  // 占视口高度 60%

const layoutStore = localforage.createInstance({
  name: 'agnes-platform',
  storeName: 'timeline-layout',
})

function storageKey(projectId: number) {
  return `timeline_layout_${projectId}`
}

export function useTimelineLayout(projectId: Ref<number | null>) {
  const layout = ref<TimelineLayoutState>({ ...DEFAULT_LAYOUT })
  const loaded = ref(false)

  async function loadLayout() {
    if (!projectId.value) return
    try {
      const saved = await layoutStore.getItem<TimelineLayoutState>(storageKey(projectId.value))
      if (saved) {
        layout.value = { ...DEFAULT_LAYOUT, ...saved }
      } else {
        layout.value = { ...DEFAULT_LAYOUT }
      }
    } catch (e) {
      console.warn('[useTimelineLayout] load failed', e)
      layout.value = { ...DEFAULT_LAYOUT }
    }
    loaded.value = true
  }

  async function saveLayout() {
    if (!projectId.value) return
    try {
      await layoutStore.setItem(storageKey(projectId.value), layout.value)
    } catch (e) {
      console.warn('[useTimelineLayout] save failed', e)
    }
  }

  function clampLibraryWidth(v: number) {
    return Math.min(MAX_LIBRARY_WIDTH, Math.max(MIN_LIBRARY_WIDTH, v))
  }

  function clampTimelineHeight(v: number) {
    const maxH = window.innerHeight * MAX_TIMELINE_HEIGHT_RATIO
    return Math.min(maxH, Math.max(MIN_TIMELINE_HEIGHT, v))
  }

  function setLibraryWidth(v: number) {
    layout.value.libraryWidth = clampLibraryWidth(v)
    saveLayout()
  }

  function setLibraryHidden(hidden: boolean) {
    layout.value.libraryHidden = hidden
    saveLayout()
  }

  function toggleLibrary() {
    layout.value.libraryHidden = !layout.value.libraryHidden
    saveLayout()
  }

  function setTimelineHeight(v: number) {
    layout.value.timelineHeight = clampTimelineHeight(v)
    saveLayout()
  }

  // projectId 变化时重新加载
  watch(projectId, () => { loadLayout() }, { immediate: true })

  return {
    layout,
    loaded,
    setLibraryWidth,
    setLibraryHidden,
    toggleLibrary,
    setTimelineHeight,
    clampLibraryWidth,
    clampTimelineHeight,
    MIN_LIBRARY_WIDTH,
    MAX_LIBRARY_WIDTH,
    MIN_TIMELINE_HEIGHT,
  }
}
```

- [ ] **Step 2: 验证类型检查**

```bash
cd /Users/skywing/agnes-platform/frontend
npx vue-tsc --noEmit 2>&1 | grep "useTimelineLayout" | head -5
```

Expected: 无错误。

- [ ] **Step 3: Commit**

```bash
git add frontend/src/composables/useTimelineLayout.ts
git commit -m "feat(composables): 新增 useTimelineLayout 弹性布局状态管理"
```

---

## Task 9: 前端 TimelineSplitter 组件

**Files:**
- Create: `frontend/src/components/project/timeline/TimelineSplitter.vue`

- [ ] **Step 1: 创建 TimelineSplitter.vue**

```vue
<!-- =====================================================
     可拖拽分隔条组件 TimelineSplitter
     - 支持 horizontal（水平分隔，调整高度）/ vertical（垂直分隔，调整宽度）
     - 通过 v-model 绑定值，拖拽时实时 emit
     ===================================================== -->

<template>
  <div
    class="timeline-splitter"
    :class="direction"
    @mousedown="onMouseDown"
  >
    <div class="splitter-handle">
      <span v-if="direction === 'vertical'">⋮</span>
      <span v-else>⋯</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'

const props = withDefaults(defineProps<{
  modelValue: number
  direction?: 'horizontal' | 'vertical'
  min?: number
  max?: number
}>(), {
  direction: 'vertical',
  min: 120,
  max: 600,
})

const emit = defineEmits<{
  (e: 'update:modelValue', val: number): void
  (e: 'drag-start'): void
  (e: 'drag-end'): void
}>()

const dragging = ref(false)

function onMouseDown(e: MouseEvent) {
  e.preventDefault()
  e.stopPropagation()
  dragging.value = true
  emit('drag-start')

  const startPos = props.direction === 'vertical' ? e.clientX : e.clientY
  const startValue = props.modelValue

  function onMove(ev: MouseEvent) {
    if (!dragging.value) return
    const currentPos = props.direction === 'vertical' ? ev.clientX : ev.clientY
    // vertical：拖右→值增；horizontal：拖下→值增
    const delta = currentPos - startPos
    const newVal = startValue + delta
    const clamped = Math.min(props.max, Math.max(props.min, newVal))
    emit('update:modelValue', clamped)
  }

  function onUp() {
    dragging.value = false
    emit('drag-end')
    document.removeEventListener('mousemove', onMove)
    document.removeEventListener('mouseup', onUp)
    document.body.style.cursor = ''
    document.body.style.userSelect = ''
  }

  document.addEventListener('mousemove', onMove)
  document.addEventListener('mouseup', onUp)
  document.body.style.cursor = props.direction === 'vertical' ? 'col-resize' : 'row-resize'
  document.body.style.userSelect = 'none'
}
</script>

<style scoped>
.timeline-splitter {
  background: var(--el-border-color, #3a3d44);
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background-color 0.15s;
  user-select: none;
}

.timeline-splitter.vertical {
  width: 6px;
  cursor: col-resize;
  height: 100%;
}

.timeline-splitter.horizontal {
  height: 6px;
  cursor: row-resize;
  width: 100%;
  margin: 4px 0;
}

.timeline-splitter:hover,
.timeline-splitter.dragging {
  background: var(--el-color-primary, #4a9eff);
}

.splitter-handle {
  color: var(--el-text-color-placeholder, #666);
  font-size: 10px;
  line-height: 1;
}
</style>
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/project/timeline/TimelineSplitter.vue
git commit -m "feat(components): 新增 TimelineSplitter 可拖拽分隔条"
```

---

## Task 10: 前端 MediaLibraryPanel 组件

**Files:**
- Create: `frontend/src/components/project/timeline/MediaLibraryPanel.vue`

- [ ] **Step 1: 创建 MediaLibraryPanel.vue**

```vue
<!-- =====================================================
     素材库面板 MediaLibraryPanel
     - 左侧抽屉，4 类 Tab（视频/音频/帧图/BGM）
     - 每项 draggable=true，拖拽到时间线创建片段
     - 顶部 Tab 切换，底部缩略图列表
     ===================================================== -->

<template>
  <div class="media-library-panel">
    <div class="panel-header">
      <span class="header-title">📁 素材库</span>
      <el-button
        size="small"
        text
        :icon="ArrowLeftBold"
        @click="$emit('hide')"
        title="收起"
      />
    </div>

    <el-tabs v-model="activeTab" class="library-tabs">
      <el-tab-pane label="视频" name="videos">
        <div class="media-list">
          <div
            v-for="item in videos"
            :key="`v-${item.id}`"
            class="media-item"
            draggable="true"
            @dragstart="onDragStart($event, item)"
          >
            <div class="media-thumb">
              <img v-if="item.thumbnail_url" :src="item.thumbnail_url" :alt="item.name" />
              <el-icon v-else><VideoCamera /></el-icon>
            </div>
            <div class="media-info">
              <div class="media-name">{{ item.name }}</div>
              <div class="media-meta">{{ formatDuration(item.duration_ms) }}</div>
            </div>
          </div>
          <el-empty v-if="!videos.length" description="暂无视频" :image-size="60" />
        </div>
      </el-tab-pane>

      <el-tab-pane label="音频" name="audios">
        <div class="media-list">
          <div
            v-for="item in audios"
            :key="`a-${item.id}`"
            class="media-item"
            draggable="true"
            @dragstart="onDragStart($event, item)"
          >
            <div class="media-thumb">
              <el-icon><Microphone /></el-icon>
            </div>
            <div class="media-info">
              <div class="media-name">{{ item.name }}</div>
              <div class="media-meta">{{ formatDuration(item.duration_ms) }}</div>
            </div>
          </div>
          <el-empty v-if="!audios.length" description="暂无音频" :image-size="60" />
        </div>
      </el-tab-pane>

      <el-tab-pane label="帧图" name="frame_images">
        <div class="media-list">
          <div
            v-for="item in frameImages"
            :key="`f-${item.id}`"
            class="media-item"
            draggable="true"
            @dragstart="onDragStart($event, item)"
          >
            <div class="media-thumb">
              <img v-if="item.thumbnail_url" :src="item.thumbnail_url" :alt="item.name" />
              <el-icon v-else><Picture /></el-icon>
            </div>
            <div class="media-info">
              <div class="media-name">{{ item.name }}</div>
              <div class="media-meta">静态图 · 3s</div>
            </div>
          </div>
          <el-empty v-if="!frameImages.length" description="暂无帧图" :image-size="60" />
        </div>
      </el-tab-pane>

      <el-tab-pane label="BGM" name="bgms">
        <div class="media-list">
          <div
            v-for="item in bgms"
            :key="`b-${item.id}`"
            class="media-item"
            draggable="true"
            @dragstart="onDragStart($event, item)"
          >
            <div class="media-thumb">
              <el-icon><Headset /></el-icon>
            </div>
            <div class="media-info">
              <div class="media-name">{{ item.name }}</div>
              <div class="media-meta">{{ item.meta?.mood }} · {{ formatDuration(item.duration_ms) }}</div>
            </div>
          </div>
          <el-empty v-if="!bgms.length" description="暂无 BGM" :image-size="60" />
        </div>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { ArrowLeftBold, VideoCamera, Microphone, Picture, Headset } from '@element-plus/icons-vue'
import type { MediaLibraryItem, MediaLibraryResponse } from '@/types/project'

const props = defineProps<{
  mediaLibrary: MediaLibraryResponse | null
}>()

const emit = defineEmits<{
  (e: 'hide'): void
  /** 拖拽开始时携带素材项 JSON */
  (e: 'drag-item', item: MediaLibraryItem): void
}>()

const activeTab = ref<'videos' | 'audios' | 'frame_images' | 'bgms'>('videos')

const videos = computed(() => props.mediaLibrary?.videos ?? [])
const audios = computed(() => props.mediaLibrary?.audios ?? [])
const frameImages = computed(() => props.mediaLibrary?.frame_images ?? [])
const bgms = computed(() => props.mediaLibrary?.bgms ?? [])

function formatDuration(ms: number): string {
  const seconds = ms / 1000
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}

function onDragStart(e: DragEvent, item: MediaLibraryItem) {
  if (!e.dataTransfer) return
  e.dataTransfer.effectAllowed = 'copy'
  e.dataTransfer.setData('application/json', JSON.stringify(item))
  emit('drag-item', item)
}
</script>

<style scoped>
.media-library-panel {
  width: 100%;
  height: 100%;
  background: var(--el-bg-color, #1e2128);
  display: flex;
  flex-direction: column;
  border-right: 1px solid var(--el-border-color-light, #3a3d44);
  overflow: hidden;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  border-bottom: 1px solid var(--el-border-color-lighter, #2a2d34);
}

.header-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.library-tabs {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.library-tabs :deep(.el-tabs__content) {
  flex: 1;
  overflow-y: auto;
}

.media-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 6px;
}

.media-item {
  display: flex;
  gap: 8px;
  padding: 6px;
  border-radius: 4px;
  background: var(--el-fill-color-light, #2a2d34);
  cursor: grab;
  transition: background-color 0.15s;
}

.media-item:hover {
  background: var(--el-color-primary-light-9, #3a4eff20);
}

.media-item:active {
  cursor: grabbing;
}

.media-thumb {
  width: 48px;
  height: 36px;
  flex-shrink: 0;
  background: var(--el-fill-color-darker, #404448);
  border-radius: 3px;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
}

.media-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.media-thumb .el-icon {
  color: var(--el-text-color-placeholder);
  font-size: 16px;
}

.media-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 2px;
}

.media-name {
  font-size: 12px;
  color: var(--el-text-color-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.media-meta {
  font-size: 10px;
  color: var(--el-text-color-secondary);
}
</style>
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/project/timeline/MediaLibraryPanel.vue
git commit -m "feat(components): 新增 MediaLibraryPanel 素材库面板"
```

---

## Task 11: 前端 useClipClipboard / useMarkers / useTrackStates composables

**Files:**
- Create: `frontend/src/composables/useClipClipboard.ts`
- Create: `frontend/src/composables/useMarkers.ts`
- Create: `frontend/src/composables/useTrackStates.ts`

- [ ] **Step 1: 创建 useClipClipboard.ts**

```typescript
/* =====================================================
 * 片段剪贴板 — 复制/剪切/粘贴
 * 职责：
 *   - 内存剪贴板（不跨页面，不持久化）
 *   - copy：仅存入剪贴板，不删除原片段
 *   - cut：复制到剪贴板并立即删除原片段（调用方负责 pushHistory）
 *   - paste：在目标时间创建新片段，cut 模式 paste 后转为 copy
 * ===================================================== */

import { ref, computed } from 'vue'
import type { TimelineClip, TimelineClipCreateRequest } from '@/types/project'
import { useProjectStore } from '@/stores/project'

interface ClipClipboardEntry {
  clip: TimelineClip
  operation: 'copy' | 'cut'
}

function deepClone(clip: TimelineClip): TimelineClip {
  return JSON.parse(JSON.stringify(clip))
}

/** 从 TimelineClip 构造 CreateRequest（剥离 id/project_id/created_at 等服务端字段） */
function toCreatePayload(clip: TimelineClip, startTime: number): TimelineClipCreateRequest {
  return {
    track_type: clip.track_type,
    track_index: clip.track_index,
    source_type: clip.source_type ?? undefined,
    source_id: clip.source_id ?? undefined,
    shot_id: clip.shot_id ?? undefined,
    start_time: startTime,
    duration: clip.duration,
    trim_start: clip.trim_start,
    trim_end: clip.trim_end ?? undefined,
    transition_type: clip.transition_type,
    transition_duration: clip.transition_duration,
    subtitle_text: clip.subtitle_text ?? undefined,
    sort_order: clip.sort_order,
    source_ref: clip.source_ref ?? undefined,
  }
}

export function useClipClipboard() {
  const projectStore = useProjectStore()
  const clipboard = ref<ClipClipboardEntry | null>(null)
  const hasContent = computed(() => clipboard.value !== null)

  function copy(clip: TimelineClip) {
    clipboard.value = { clip: deepClone(clip), operation: 'copy' }
  }

  async function cut(clip: TimelineClip) {
    clipboard.value = { clip: deepClone(clip), operation: 'cut' }
    // 立即删除原片段（pushHistory 由调用方在调用 cut 前完成）
    await projectStore.deleteTimelineClip(clip.id)
  }

  async function paste(targetStartTime: number): Promise<void> {
    if (!clipboard.value) return
    const { clip, operation } = clipboard.value
    // 创建新片段（id 由后端生成）
    await projectStore.createTimelineClip(toCreatePayload(clip, targetStartTime))
    // paste 成功后，cut 模式转为 copy 模式，允许重复粘贴
    if (operation === 'cut') {
      clipboard.value.operation = 'copy'
    }
  }

  function clear() {
    clipboard.value = null
  }

  return { clipboard, hasContent, copy, cut, paste, clear }
}
```

- [ ] **Step 2: 创建 useMarkers.ts**

```typescript
/* =====================================================
 * 标记 Markers 管理 — Phase 2 增强
 * 职责：
 *   - 在播放头位置添加标记
 *   - 删除离播放头最近的标记
 *   - 跳到上一/下一标记
 * ===================================================== */

import { computed } from 'vue'
import { ElMessage } from 'element-plus'
import { useProjectStore } from '@/stores/project'

export function useMarkers(
  currentTime: Ref<number>,
  seekTo: (time: number) => void,
) {
  const projectStore = useProjectStore()
  const markers = computed(() => projectStore.markers)

  /** 在指定时间添加标记 */
  async function addMarker(time: number, name?: string) {
    try {
      await projectStore.addMarker({ time, name, color: '#4a9eff' })
      ElMessage.success('已添加标记')
    } catch (e: any) {
      ElMessage.error(e?.message || '添加标记失败')
    }
  }

  /** 在播放头位置添加标记（Ctrl+M） */
  async function addMarkerAtPlayhead() {
    await addMarker(currentTime.value)
  }

  /** 删除离播放头最近的标记（Shift+M） */
  async function deleteNearestMarker() {
    if (!markers.value.length) {
      ElMessage.warning('暂无标记')
      return
    }
    const nearest = markers.value.reduce((prev, cur) =>
      Math.abs(cur.time - currentTime.value) < Math.abs(prev.time - currentTime.value) ? cur : prev,
    )
    try {
      await projectStore.removeMarker(nearest.id)
      ElMessage.success('已删除最近标记')
    } catch (e: any) {
      ElMessage.error(e?.message || '删除标记失败')
    }
  }

  /** 跳到上一标记（[） */
  function jumpToPrevMarker() {
    const prevs = markers.value.filter(m => m.time < currentTime.value - 0.01)
    if (!prevs.length) {
      ElMessage.warning('已是第一个标记')
      return
    }
    const prev = prevs[prevs.length - 1]  // 已按 time 升序
    seekTo(prev.time)
  }

  /** 跳到下一标记（]） */
  function jumpToNextMarker() {
    const nexts = markers.value.filter(m => m.time > currentTime.value + 0.01)
    if (!nexts.length) {
      ElMessage.warning('已是最后一个标记')
      return
    }
    const next = nexts[0]
    seekTo(next.time)
  }

  return {
    markers,
    addMarker,
    addMarkerAtPlayhead,
    deleteNearestMarker,
    jumpToPrevMarker,
    jumpToNextMarker,
  }
}
```

注意：`Ref` 类型需要从 vue 导入，在文件顶部加：

```typescript
import { computed, type Ref } from 'vue'
```

- [ ] **Step 3: 创建 useTrackStates.ts**

```typescript
/* =====================================================
 * 轨道状态管理 — Mute / Lock
 * 职责：
 *   - 通过 projectStore.trackStates 读写轨道状态
 *   - 提供 isMuted / isLocked / toggleMuted / toggleLocked 便捷方法
 *   - localforage 持久化（按 project_id 分键）
 * ===================================================== */

import localforage from 'localforage'
import { useProjectStore } from '@/stores/project'
import type { TrackState } from '@/types/project'

const trackStateStore = localforage.createInstance({
  name: 'agnes-platform',
  storeName: 'timeline-track-states',
})

function storageKey(projectId: number) {
  return `track_states_${projectId}`
}

export function useTrackStates(projectId: Ref<number | null>) {
  const projectStore = useProjectStore()

  function trackKey(trackType: string, trackIndex: number) {
    return `${trackType}:${trackIndex}`
  }

  function isMuted(trackType: string, trackIndex: number): boolean {
    return projectStore.isTrackMuted(trackType, trackIndex)
  }

  function isLocked(trackType: string, trackIndex: number): boolean {
    return projectStore.isTrackLocked(trackType, trackIndex)
  }

  function toggleMuted(trackType: string, trackIndex: number) {
    const cur = isMuted(trackType, trackIndex)
    projectStore.setTrackMuted(trackType, trackIndex, !cur)
    persist()
  }

  function toggleLocked(trackType: string, trackIndex: number) {
    const cur = isLocked(trackType, trackIndex)
    projectStore.setTrackLocked(trackType, trackIndex, !cur)
    persist()
  }

  async function persist() {
    if (!projectId.value) return
    try {
      await trackStateStore.setItem(storageKey(projectId.value), projectStore.trackStates)
    } catch (e) {
      console.warn('[useTrackStates] persist failed', e)
    }
  }

  async function loadTrackStates() {
    if (!projectId.value) return
    try {
      const saved = await trackStateStore.getItem<Record<string, TrackState>>(storageKey(projectId.value))
      if (saved) {
        projectStore.trackStates = saved
      }
    } catch (e) {
      console.warn('[useTrackStates] load failed', e)
    }
  }

  return {
    isMuted,
    isLocked,
    toggleMuted,
    toggleLocked,
    loadTrackStates,
    persist,
  }
}
```

注意顶部要导入 `Ref`：

```typescript
import { type Ref } from 'vue'
```

- [ ] **Step 4: 验证类型检查**

```bash
cd /Users/skywing/agnes-platform/frontend
npx vue-tsc --noEmit 2>&1 | grep -E "useClipClipboard|useMarkers|useTrackStates" | head -10
```

Expected: 无错误。

- [ ] **Step 5: Commit**

```bash
git add frontend/src/composables/useClipClipboard.ts frontend/src/composables/useMarkers.ts frontend/src/composables/useTrackStates.ts
git commit -m "feat(composables): 新增 useClipClipboard / useMarkers / useTrackStates"
```

---

## Task 12: 前端 MarkersRuler + TrackHeaderControls 组件

**Files:**
- Create: `frontend/src/components/project/timeline/MarkersRuler.vue`
- Create: `frontend/src/components/project/timeline/TrackHeaderControls.vue`

- [ ] **Step 1: 创建 MarkersRuler.vue**

```vue
<!-- =====================================================
     标记旗帜渲染 MarkersRuler
     - 渲染在时间线标尺上方
     - 点击旗帜跳转到标记时间
     - 右键删除标记
     ===================================================== -->

<template>
  <div class="markers-ruler" :style="{ width: totalWidth + 'px' }">
    <div
      v-for="marker in markers"
      :key="marker.id"
      class="marker-flag"
      :style="{
        left: (marker.time * pixelsPerSecond) + 'px',
        '--marker-color': marker.color,
      }"
      :title="marker.name || `标记 @ ${formatTime(marker.time)}`"
      @click="$emit('seek', marker.time)"
      @contextmenu.prevent="$emit('delete', marker.id)"
    >
      <el-icon><Flag /></el-icon>
      <span v-if="marker.name" class="marker-name">{{ marker.name }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Flag } from '@element-plus/icons-vue'
import type { ProjectMarker } from '@/types/project'

defineProps<{
  markers: ProjectMarker[]
  pixelsPerSecond: number
  totalWidth: number
}>()

defineEmits<{
  (e: 'seek', time: number): void
  (e: 'delete', markerId: number): void
}>()

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  const cs = Math.floor((seconds % 1) * 100)
  return `${m}:${s.toString().padStart(2, '0')}.${cs.toString().padStart(2, '0')}`
}
</script>

<style scoped>
.markers-ruler {
  position: relative;
  height: 18px;
  margin-bottom: 2px;
}

.marker-flag {
  position: absolute;
  top: 0;
  transform: translateX(-50%);
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 1px 4px;
  background: var(--marker-color, #4a9eff);
  color: #fff;
  border-radius: 2px;
  font-size: 9px;
  cursor: pointer;
  white-space: nowrap;
  transition: transform 0.15s;
}

.marker-flag:hover {
  transform: translateX(-50%) scale(1.1);
}

.marker-name {
  max-width: 60px;
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>
```

- [ ] **Step 2: 创建 TrackHeaderControls.vue**

```vue
<!-- =====================================================
     轨道头部控制按钮 TrackHeaderControls
     - M（Mute）：静音，激活时蓝色
     - L（Lock）：锁定，激活时橙色
     ===================================================== -->

<template>
  <div class="track-header-controls">
    <button
      class="track-btn"
      :class="{ active: muted }"
      :title="muted ? '取消静音' : '静音'"
      @click.stop="$emit('toggle-mute')"
    >M</button>
    <button
      class="track-btn"
      :class="{ active: locked, 'lock-active': locked }"
      :title="locked ? '解锁' : '锁定'"
      @click.stop="$emit('toggle-lock')"
    >L</button>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  muted: boolean
  locked: boolean
}>()

defineEmits<{
  (e: 'toggle-mute'): void
  (e: 'toggle-lock'): void
}>()
</script>

<style scoped>
.track-header-controls {
  display: inline-flex;
  gap: 2px;
  margin-right: 6px;
}

.track-btn {
  width: 18px;
  height: 18px;
  border: 1px solid var(--el-border-color, #3a3d44);
  background: var(--el-fill-color, #2a2d34);
  color: var(--el-text-color-secondary, #888);
  border-radius: 3px;
  font-size: 10px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0;
}

.track-btn:hover {
  border-color: var(--el-color-primary, #4a9eff);
  color: var(--el-color-primary, #4a9eff);
}

.track-btn.active {
  background: var(--el-color-primary, #4a9eff);
  color: #fff;
  border-color: var(--el-color-primary, #4a9eff);
}

.track-btn.lock-active {
  background: var(--el-color-warning, #e6a23c);
  border-color: var(--el-color-warning, #e6a23c);
}
</style>
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/project/timeline/MarkersRuler.vue frontend/src/components/project/timeline/TrackHeaderControls.vue
git commit -m "feat(components): 新增 MarkersRuler + TrackHeaderControls"
```

---

## Task 13: 前端 TimelineTab 重构为弹性三区布局 + 接入新功能

**Files:**
- Modify: `frontend/src/components/project/timeline/TimelineTab.vue`

- [ ] **Step 1: 读取现有 TimelineTab.vue 完整内容**

读取 `frontend/src/components/project/timeline/TimelineTab.vue` 理解现有结构（TimelineToolbar / TimelinePreview / TimelineEditor / ClipPropertyPanel / AddClipDialog）。

- [ ] **Step 2: 引入新组件和 composable**

在 `<script setup>` 顶部 import 区追加：

```typescript
import { ref as useRef, computed as useComputed } from 'vue'  // 如果已 import 则跳过
import MediaLibraryPanel from './MediaLibraryPanel.vue'
import TimelineSplitter from './TimelineSplitter.vue'
import MarkersRuler from './MarkersRuler.vue'
import TrackHeaderControls from './TrackHeaderControls.vue'
import { useTimelineLayout } from '@/composables/useTimelineLayout'
import { useClipClipboard } from '@/composables/useClipClipboard'
import { useMarkers } from '@/composables/useMarkers'
import { useTrackStates } from '@/composables/useTrackStates'
import type { MediaLibraryItem } from '@/types/project'
```

- [ ] **Step 3: 初始化 composable 实例**

在 setup 中初始化：

```typescript
// 弹性布局
const projectIdRef = useComputed(() => projectStore.currentProjectId)
const { layout, toggleLibrary, setLibraryWidth, setTimelineHeight } = useTimelineLayout(projectIdRef)

// 剪贴板
const clipboard = useClipClipboard()

// 标记
const { addMarkerAtPlayhead, deleteNearestMarker, jumpToPrevMarker, jumpToNextMarker, markers } = useMarkers(
  preview.currentTime,
  (t: number) => preview.seekTo(t),
)

// 轨道状态
const { isMuted, isLocked, toggleMuted, toggleLocked, loadTrackStates } = useTrackStates(projectIdRef)
```

- [ ] **Step 4: 重构模板为弹性三区布局**

把 `<template>` 的主体改为：

```vue
<template>
  <div class="timeline-tab">
    <!-- 顶部工具栏 -->
    <TimelineToolbar
      :has-timeline="hasTimeline"
      :whisper-available="projectStore.whisperAvailable"
      @init-timeline="onInitTimeline"
      @generate-subtitles="onGenerateSubtitles"
      @open-subtitle-style="onOpenSubtitleStyle"
      @open-bgm-picker="onOpenBgmPicker"
      @merge="onMerge"
      @merge-advanced="onMergeAdvanced"
    />

    <!-- 主体：弹性三区布局 -->
    <div v-if="hasTimeline" class="timeline-body">
      <!-- 中间行：素材库（左） + 预览（右） -->
      <div class="mid-row" :style="{ height: `calc(100% - ${layout.timelineHeight}px - 10px)` }">
        <!-- 素材库收起时的展开按钮 -->
        <div v-if="layout.libraryHidden" class="library-expand-btn" @click="toggleLibrary">
          <el-icon><Folder /></el-icon>
          <span>展开素材库</span>
        </div>

        <!-- 素材库面板（左侧抽屉） -->
        <div
          v-if="!layout.libraryHidden"
          class="library-container"
          :style="{ width: layout.libraryWidth + 'px' }"
        >
          <MediaLibraryPanel
            :media-library="projectStore.mediaLibrary"
            @hide="toggleLibrary"
            @drag-item="onMediaDragItem"
          />
        </div>

        <!-- 垂直分隔条 -->
        <TimelineSplitter
          v-if="!layout.libraryHidden"
          direction="vertical"
          :min="180"
          :max="400"
          v-model="layout.libraryWidth"
          @update:model-value="setLibraryWidth"
        />

        <!-- 预览区 -->
        <div class="preview-container">
          <TimelinePreview
            :clips="draftClips"
            :playhead-time="preview.currentTime.value"
            :is-playing="preview.isPlaying.value"
            @play="preview.togglePlayPause"
            @seek="onSeek"
          />
        </div>
      </div>

      <!-- 水平分隔条 -->
      <TimelineSplitter
        direction="horizontal"
        :min="120"
        :max="Math.floor(window.innerHeight * 0.6)"
        v-model="layout.timelineHeight"
        @update:model-value="setTimelineHeight"
      />

      <!-- 时间线编辑器 -->
      <div class="editor-wrap" :style="{ height: layout.timelineHeight + 'px' }">
        <TimelineEditor
          :clips="draftClips"
          :total-duration="totalDuration"
          :selected-clip-id="selectedClipId"
          :editable="projectStore.isEditable"
          :playhead-time="preview.currentTime.value"
          :active-video-clip-id="preview.activeVideoClipId.value"
          :active-audio-clip-id="preview.activeAudioClipId.value"
          :active-subtitle-clip-id="preview.activeSubtitleClipId.value"
          :markers="markers"
          :track-states="projectStore.trackStates"
          :can-undo="canUndo"
          :can-redo="canRedo"
          @select-clip="onSelectClip"
          @deselect="onDeselectClip"
          @clip-drag="onClipDrag"
          @clip-trim="onClipTrim"
          @clip-updated="onClipUpdated"
          @play="preview.togglePlayPause"
          @seek="onSeek"
          @split-at-playhead="onSplitAtPlayhead"
          @ripple-delete="onRippleDelete"
          @seek-by-frames="onSeekByFrames"
          @context-menu="onContextMenu"
          @undo="undo"
          @redo="redo"
          @add-clip="addClipDialogVisible = true"
          @drop-media="onDropMedia"
          @toggle-track-mute="onToggleTrackMute"
          @toggle-track-lock="onToggleTrackLock"
          @marker-seek="onSeek"
          @marker-delete="onMarkerDelete"
        />
      </div>
    </div>

    <!-- 其余对话框保持原样 -->
    <ClipPropertyPanel v-model:visible="clipPanelVisible" :clip="selectedClip" :editable="projectStore.isEditable" @save="onSaveClip" @delete="onDeleteClip" />
    <AddClipDialog v-model="addClipDialogVisible" :suggested-start-time="preview.currentTime.value" @create="onAddClip" />
    <!-- 右键菜单、SubtitleStyleDialog、BgmPickerDialog 保持原样 -->
    <!-- ... 现有对话框代码 ... -->
  </div>
</template>
```

- [ ] **Step 5: 新增事件处理函数**

在 setup 中追加：

```typescript
// 拖拽素材到时间线
async function onDropMedia(item: MediaLibraryItem, trackType: string, trackIndex: number, startTime: number) {
  pushHistory()
  try {
    const payload: TimelineClipCreateRequest = {
      track_type: trackType,
      track_index: trackIndex,
      start_time: startTime,
      duration: item.duration_ms / 1000,
      trim_start: 0,
      transition_type: 'none',
      transition_duration: 0,
      sort_order: 0,
    }
    if (item.type === 'shot_video' || item.type === 'shot_frame_image') {
      payload.source_type = item.type
      payload.source_id = item.id
      payload.shot_id = item.shot_id ?? undefined
    } else if (item.type === 'shot_audio') {
      payload.source_type = 'shot_audio'
      payload.source_id = item.id
      payload.shot_id = item.shot_id ?? undefined
    } else if (item.type === 'bgm') {
      payload.source_type = 'bgm'
      payload.source_ref = item.meta?.bgm_id
    }
    await projectStore.createTimelineClip(payload)
    ElMessage.success('已添加片段到时间线')
  } catch (e: any) {
    undoStack.value.pop()
    ElMessage.error(e?.message || '添加失败')
  }
}

// 轨道状态切换
function onToggleTrackMute(trackType: string, trackIndex: number) {
  toggleMuted(trackType, trackIndex)
}

function onToggleTrackLock(trackType: string, trackIndex: number) {
  toggleLocked(trackType, trackIndex)
}

// 标记删除
async function onMarkerDelete(markerId: number) {
  try {
    await projectStore.removeMarker(markerId)
    ElMessage.success('标记已删除')
  } catch (e: any) {
    ElMessage.error(e?.message || '删除标记失败')
  }
}
```

- [ ] **Step 6: 在 onMounted 加载素材库 + 标记 + 轨道状态**

在现有 `onMounted` 中追加：

```typescript
  await Promise.all([
    projectStore.fetchMediaLibrary(),
    projectStore.fetchMarkers(),
  ])
  await loadTrackStates()
```

- [ ] **Step 7: 扩展 onKeyDown 快捷键**

在现有 `onKeyDown` 函数的 switch 中追加：

```typescript
    // Ctrl+C / Ctrl+V / Ctrl+X
    if (cmd && (e.key === 'c' || e.key === 'C')) {
      if (selectedClipId.value != null) {
        const clip = draftClips.value.find(c => c.id === selectedClipId.value)
        if (clip) {
          e.preventDefault()
          clipboard.copy(clip)
          ElMessage.success('已复制')
        }
      }
      return
    }
    if (cmd && (e.key === 'x' || e.key === 'X')) {
      if (selectedClipId.value != null) {
        const clip = draftClips.value.find(c => c.id === selectedClipId.value)
        if (clip) {
          e.preventDefault()
          pushHistory()
          await clipboard.cut(clip)
          ElMessage.success('已剪切')
          if (selectedClipId.value === clip.id) {
            selectedClipId.value = null
            clipPanelVisible.value = false
          }
        }
      }
      return
    }
    if (cmd && (e.key === 'v' || e.key === 'V')) {
      if (clipboard.hasContent.value) {
        e.preventDefault()
        pushHistory()
        await clipboard.paste(preview.currentTime.value)
        ElMessage.success('已粘贴')
      }
      return
    }

    // Ctrl+M 添加标记
    if (cmd && (e.key === 'm' || e.key === 'M')) {
      e.preventDefault()
      if (e.shiftKey) {
        await deleteNearestMarker()
      } else {
        await addMarkerAtPlayhead()
      }
      return
    }

    // [ / ] 跳到上一/下一标记
    if (e.key === '[') {
      e.preventDefault()
      jumpToPrevMarker()
      return
    }
    if (e.key === ']') {
      e.preventDefault()
      jumpToNextMarker()
      return
    }
```

- [ ] **Step 8: 添加弹性布局 CSS**

在 `<style scoped>` 中追加：

```css
.timeline-body {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 0;
}

.mid-row {
  display: flex;
  min-height: 0;
}

.library-expand-btn {
  width: 24px;
  background: var(--el-fill-color-light, #2a2d34);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 4px;
  cursor: pointer;
  color: var(--el-text-color-secondary);
  font-size: 10px;
  padding: 8px 2px;
  border-right: 1px solid var(--el-border-color-light, #3a3d44);
  transition: background-color 0.15s;
}

.library-expand-btn:hover {
  background: var(--el-color-primary-light-9, #3a4eff20);
  color: var(--el-color-primary);
}

.library-container {
  flex-shrink: 0;
  height: 100%;
  overflow: hidden;
}

.preview-container {
  flex: 1;
  min-width: 0;
  height: 100%;
}

.editor-wrap {
  flex-shrink: 0;
  overflow: auto;
}
```

- [ ] **Step 9: 验证类型检查**

```bash
cd /Users/skywing/agnes-platform/frontend
npx vue-tsc --noEmit 2>&1 | grep "TimelineTab" | head -20
```

Expected: 无新增错误。

- [ ] **Step 10: Commit**

```bash
git add frontend/src/components/project/timeline/TimelineTab.vue
git commit -m "feat(timeline): TimelineTab 重构为弹性三区布局 + 接入素材库/剪贴板/标记/轨道状态"
```

---

## Task 14: 前端 TimelineEditor 接入 MarkersRuler + TrackHeaderControls + drop 事件

**Files:**
- Modify: `frontend/src/components/project/timeline/TimelineEditor.vue`
- Modify: `frontend/src/components/project/timeline/TimelineTrack.vue`

- [ ] **Step 1: TimelineEditor 添加 markers / trackStates / drop-media 等 props 和 emits**

在 `TimelineEditor.vue` 的 props 中追加：

```typescript
  /** 标记列表（用于标尺上方旗帜渲染） */
  markers?: ProjectMarker[]
  /** 轨道状态（用于轨道头部 M/L 按钮） */
  trackStates?: Record<string, TrackState>
```

在 emits 中追加：

```typescript
  /** 拖拽素材到轨道 */
  (e: 'drop-media', item: MediaLibraryItem, trackType: string, trackIndex: number, startTime: number): void
  /** 轨道静音切换 */
  (e: 'toggle-track-mute', trackType: string, trackIndex: number): void
  /** 轨道锁定切换 */
  (e: 'toggle-track-lock', trackType: string, trackIndex: number): void
  /** 标记：点击旗帜跳转 */
  (e: 'marker-seek', time: number): void
  /** 标记：右键删除 */
  (e: 'marker-delete', markerId: number): void
```

在顶部 import 中追加：

```typescript
import MarkersRuler from './MarkersRuler.vue'
import TrackHeaderControls from './TrackHeaderControls.vue'
import type { MediaLibraryItem, ProjectMarker, TrackState } from '@/types/project'
```

- [ ] **Step 2: 在标尺上方渲染 MarkersRuler**

在 TimelineEditor.vue 模板的标尺 div 上方追加：

```vue
<MarkersRuler
  v-if="markers && markers.length"
  :markers="markers"
  :pixels-per-second="pixelsPerSecond"
  :total-width="totalWidth"
  @seek="$emit('marker-seek', $event)"
  @delete="$emit('marker-delete', $event)"
/>
```

- [ ] **Step 3: 在每个轨道头部渲染 TrackHeaderControls**

在轨道行模板中（TimelineTrack 渲染处）追加 TrackHeaderControls：

```vue
<div class="track-header">
  <TrackHeaderControls
    :muted="trackStates ? !!(trackStates[`${trackType}:0`]?.muted) : false"
    :locked="trackStates ? !!(trackStates[`${trackType}:0`]?.locked) : false"
    @toggle-mute="$emit('toggle-track-mute', trackType, 0)"
    @toggle-lock="$emit('toggle-track-lock', trackType, 0)"
  />
  <span class="track-name">{{ trackLabel(trackType) }}</span>
</div>
```

- [ ] **Step 4: TimelineTrack 支持 drop 事件**

在 `TimelineTrack.vue` 的轨道 div 上追加 `@dragover.prevent="onDragOver"` 和 `@drop="onDrop"`：

```vue
<div
  class="track-clips"
  @dragover.prevent="onDragOver"
  @drop="onDrop"
>
  <!-- 现有 TimelineClip 列表 -->
</div>
```

在 script 中添加：

```typescript
const props = defineProps<{
  // ... 现有 props ...
  /** 拖拽落点高亮 */
  dropHighlight?: boolean
}>()

const emit = defineEmits<{
  // ... 现有 emits ...
  (e: 'drop-media', item: MediaLibraryItem, trackType: string, trackIndex: number, startTime: number): void
}>()

function onDragOver(e: DragEvent) {
  if (e.dataTransfer) e.dataTransfer.dropEffect = 'copy'
}

function onDrop(e: DragEvent) {
  if (!e.dataTransfer) return
  const json = e.dataTransfer.getData('application/json')
  if (!json) return
  try {
    const item = JSON.parse(json) as MediaLibraryItem
    // 计算落点时间
    const rect = (e.currentTarget as HTMLElement).getBoundingClientRect()
    const x = e.clientX - rect.left
    const startTime = Math.max(0, x / props.pixelsPerSecond)
    // 决定 track_type
    const trackType = item.type === 'shot_video' || item.type === 'shot_frame_image' ? 'video' : 'audio'
    emit('drop-media', item, trackType, props.trackIndex, startTime)
  } catch (err) {
    console.error('[TimelineTrack] drop parse failed', err)
  }
}
```

并在 TimelineEditor 透传 `drop-media` 事件：

```vue
<TimelineTrack
  ...
  @drop-media="(item, tt, ti, st) => $emit('drop-media', item, tt, ti, st)"
/>
```

- [ ] **Step 5: TimelineTrack 检查 locked 拦截拖拽**

在 `TimelineTrack.vue` 的 `onClipDrag` / `onClipTrim` 函数开头追加锁定检查：

```typescript
function onClipDrag(clipId: number, deltaSeconds: number) {
  // 检查轨道锁定状态
  if (props.locked) return
  // ... 现有逻辑 ...
}
```

在 props 中加 `locked?: boolean`，由 TimelineEditor 根据 trackStates 传入。

- [ ] **Step 6: 验证类型检查**

```bash
cd /Users/skywing/agnes-platform/frontend
npx vue-tsc --noEmit 2>&1 | grep -E "TimelineEditor|TimelineTrack" | head -20
```

Expected: 无新增错误。

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/project/timeline/TimelineEditor.vue frontend/src/components/project/timeline/TimelineTrack.vue
git commit -m "feat(timeline): TimelineEditor 接入 MarkersRuler + TrackHeaderControls + drop 事件"
```

---

## Task 15: 前端 useTimelinePreview 支持 trackStates.muted

**Files:**
- Modify: `frontend/src/composables/useTimelinePreview.ts`

- [ ] **Step 1: 读取 useTimelinePreview.ts 理解播放逻辑**

读取 `frontend/src/composables/useTimelinePreview.ts` 找到音频元素播放的代码（通常在 `tick` 或 `updateActiveClips` 函数中调用 `audioEl.play()`）。

- [ ] **Step 2: 增加 trackStates 参数支持静音检查**

在 `useTimelinePreview` 函数签名中追加可选参数：

```typescript
export function useTimelinePreview(
  clips: Ref<TimelineClip[]>,
  totalDuration: Ref<number>,
  /** 轨道状态（用于静音检查） */
  trackStates?: Ref<Record<string, TrackState>>,
) {
  // ... 现有逻辑 ...
}
```

在播放/激活片段的逻辑中，对音频元素播放前检查静音：

```typescript
// 激活音频片段时检查静音
function activateAudioClip(clip: TimelineClip) {
  const key = `${clip.track_type}:${clip.track_index}`
  const isMuted = trackStates?.value?.[key]?.muted ?? false
  if (isMuted) {
    // 静音轨不播放音频
    return
  }
  // ... 现有激活逻辑 ...
}
```

- [ ] **Step 3: 在 TimelineTab.vue 传入 trackStates**

在 TimelineTab.vue 中调用 `useTimelinePreview` 时传入 `projectStore.trackStates`：

```typescript
const preview = useTimelinePreview(
  draftClips,
  totalDuration,
  useComputed(() => projectStore.trackStates),
)
```

- [ ] **Step 4: 验证类型检查**

```bash
cd /Users/skywing/agnes-platform/frontend
npx vue-tsc --noEmit 2>&1 | grep "useTimelinePreview" | head -5
```

Expected: 无错误。

- [ ] **Step 5: Commit**

```bash
git add frontend/src/composables/useTimelinePreview.ts frontend/src/components/project/timeline/TimelineTab.vue
git commit -m "feat(preview): useTimelinePreview 支持轨道静音检查"
```

---

## Task 16: 端到端验证

**Files:** 无文件改动，仅验证

- [ ] **Step 1: 后端启动验证**

```bash
cd /Users/skywing/agnes-platform/backend
python -c "from app.main import app; print('OK')"
```

Expected: `OK`，无 import 错误。

- [ ] **Step 2: 后端新端点功能验证（curl）**

启动后端后，验证新端点：

```bash
# 假设已有项目 id=1 和 token
TOKEN="your_token"
PID=1

# 素材库
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/projects/$PID/media-library | python -m json.tool | head -20

# 标记列表
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/projects/$PID/markers | python -m json.tool

# 创建标记
curl -s -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"time": 5.0, "name": "测试标记"}' \
  http://localhost:8000/api/projects/$PID/markers | python -m json.tool
```

Expected: 素材库返回四类列表；标记列表返回数组；创建标记返回 id。

- [ ] **Step 3: 前端类型检查**

```bash
cd /Users/skywing/agnes-platform/frontend
npx vue-tsc --noEmit 2>&1 | grep -E "timeline/|composables/use(ClipClipboard|Markers|TrackStates|TimelineLayout)" | head -30
```

Expected: 本次新增文件零错误。

- [ ] **Step 4: 前端启动 + 浏览器手动验证**

```bash
cd /Users/skywing/agnes-platform/frontend
npm run dev
```

手动验证以下流程：
1. 进入项目详情页 → 切到时间线 Tab
2. 验证弹性布局：素材库（左）+ 预览（右）+ 时间线（底部）
3. 拖拽垂直分隔条调整素材库宽度
4. 拖拽水平分隔条调整时间线高度
5. 点素材库右上角 ◀ 收起，预览区获得全宽
6. 点左侧边缘展开按钮重新展开素材库
7. 切换素材库 Tab（视频/音频/帧图/BGM）
8. 从素材库拖拽视频项到时间线 video 轨，验证创建片段
9. 选中片段按 Ctrl+C，移动播放头，按 Ctrl+V 粘贴
10. 选中片段按 Ctrl+X 剪切，按 Ctrl+V 粘贴
11. 按 Ctrl+M 在播放头添加标记，标尺上方出现旗帜
12. 按 [ / ] 跳到上一/下一标记
13. 按 Shift+M 删除最近标记
14. 点轨道头部 M 按钮静音，播放时该轨无声
15. 点轨道头部 L 按钮锁定，尝试拖拽该轨片段被拦截
16. 刷新页面，验证布局尺寸和轨道状态已持久化恢复

- [ ] **Step 5: Final commit**

如果有任何修复：

```bash
git add -A
git commit -m "fix: 端到端验证修复"
```

---

## Self-Review 检查清单

**Spec 覆盖**：
- ✅ 弹性三区布局（Task 8/9/13）
- ✅ 项目素材库 + 拖拽（Task 4/10/13/14）
- ✅ 复制/剪切/粘贴（Task 11/13）
- ✅ 标记 Markers（Task 1/3/5/11/12/14）
- ✅ 轨道 Mute/Lock（Task 7/11/12/14/15）
- ✅ BGM 文件 URL（Task 5）
- ✅ source_type 扩展 shot_frame_image / bgm（Task 1/4/6）
- ✅ merge_service 适配（Task 6）

**Placeholder 扫描**：无 TBD/TODO，所有步骤都给了完整代码。

**类型一致性**：
- ✅ `MediaLibraryItem` 在 types/schema/service/前端组件中字段一致
- ✅ `ProjectMarker` 在 model/schema/service/前端组件中字段一致
- ✅ `TrackState` 在 types/store/composable 中结构一致
- ✅ `source_ref` 在 model/schema/types 中字段名一致
- ✅ `useClipClipboard` 的 `cut/paste` 签名与 TimelineTab 调用一致
