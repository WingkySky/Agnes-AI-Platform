# 集数隔离（Episode Isolation）实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让大项目下多集剧本的分镜/角色/场景/道具强属于某一集，彻底修复第二集分镜追加到第一集、资源只拿第一集剧本的混乱问题。

**Architecture:** 四张资源表新增 `script_id` NOT NULL 外键（级联删除）+ 分镜序号按集重置；Service/路由层全链路接收 script_id；前端引入 `currentScriptId` 全局状态 + 顶部统一切换器 + 全部集分组视图 + 跨集复制。

**Tech Stack:** FastAPI + SQLAlchemy async + Pydantic + Vue 3 + Pinia + Element Plus + pytest

**Spec:** `docs/superpowers/specs/2026-07-07-episode-isolation-design.md`

---

## 文件结构总览

### 后端
| 文件 | 责任 |
|---|---|
| `backend/app/models/project.py` | 数据模型——四张资源表加 script_id 外键、改唯一约束、加反向关系 |
| `backend/app/schemas/project.py` | Pydantic 模型——Create/Response 加 script_id/episode_no、新增请求体模型 |
| `backend/app/services/project/shot_service.py` | 分镜服务——split/list/create 接收 script_id、序号按集 |
| `backend/app/services/project/character_service.py` | 角色服务——extract/list/create 接收 script_id、新增 copy_to |
| `backend/app/services/project/scene_service.py` | 场景服务——同角色 |
| `backend/app/services/project/prop_service.py` | 道具服务——同角色 |
| `backend/app/services/project/wizard.py` | 向导——分镜步骤传 script_id |
| `backend/app/routes/projects.py` | 路由——list 加 query、extract/split 改请求体、新增 copy-to |
| `backend/tests/test_episode_isolation.py` | 后端测试 |

### 前端
| 文件 | 责任 |
|---|---|
| `frontend/src/api/projects.ts` | API——list 加 scriptId、修复 extract/split、新增 copyTo |
| `frontend/src/stores/project.ts` | Store——currentScriptId 状态、setCurrentScript、按集分组 getter |
| `frontend/src/components/project/ProjectManagerView.vue` | 顶部集数切换器 |
| `frontend/src/components/project/ShotsTab.vue` | 分镜列表——按集分组、新建禁用 |
| `frontend/src/components/project/CharactersTab.vue` | 角色列表——修复 extract、跨集复制 |
| `frontend/src/components/project/ScenesTab.vue` | 场景列表——同角色 |
| `frontend/src/components/project/PropsTab.vue` | 道具列表——同角色 |
| `frontend/src/i18n/index.ts` | 国际化——新增集数切换相关 key |

---

## 阶段 1：后端数据模型

### Task 1: 数据模型层改造

**Files:**
- Modify: `backend/app/models/project.py`

- [ ] **Step 1: 给 ProjectCharacter 加 script_id 外键**

在 `backend/app/models/project.py` 的 `ProjectCharacter` 类（约 L129-149），在 `project_id` 字段后新增 `script_id` 字段，并加 `script` relationship：

```python
class ProjectCharacter(Base):
    """项目角色实体表"""
    __tablename__ = "project_characters"
    __table_args__ = (
        Index("idx_project_characters_project", "project_id"),
        Index("idx_project_characters_script", "script_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    script_id = Column(
        Integer,
        ForeignKey("project_scripts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="所属集剧本ID",
    )
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    appearance_desc = Column(Text, nullable=True)
    role_type = Column(String(20), default="supporting", nullable=False)
    asset_id = Column(Integer, ForeignKey("assets.id"), nullable=True)
    active_image_id = Column(Integer, nullable=True)
    sort_order = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    project = relationship("Project", back_populates="characters")
    script = relationship("ProjectScript", back_populates="characters")
    asset = relationship("Asset", foreign_keys=[asset_id])
    shots = relationship("ProjectShotCharacter", back_populates="character", cascade="all, delete-orphan")
    voice_assignments = relationship("ProjectCharacterVoice", back_populates="character", cascade="all, delete-orphan")
```

- [ ] **Step 2: 给 ProjectScene 加 script_id 外键**

同样模式改造 `ProjectScene`（约 L152-187）：

```python
class ProjectScene(Base):
    """项目场景实体表"""
    __tablename__ = "project_scenes"
    __table_args__ = (
        Index("idx_project_scenes_project", "project_id"),
        Index("idx_project_scenes_script", "script_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    script_id = Column(
        Integer,
        ForeignKey("project_scripts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="所属集剧本ID",
    )
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
    script = relationship("ProjectScript", back_populates="scenes")
    asset = relationship("Asset", foreign_keys=[asset_id])
    shots = relationship("ProjectShot", back_populates="scene")
```

- [ ] **Step 3: 给 ProjectProp 加 script_id 外键**

同样模式改造 `ProjectProp`（约 L190-221）：

```python
class ProjectProp(Base):
    """项目道具实体表"""
    __tablename__ = "project_props"
    __table_args__ = (
        Index("idx_project_props_project", "project_id"),
        Index("idx_project_props_script", "script_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    script_id = Column(
        Integer,
        ForeignKey("project_scripts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="所属集剧本ID",
    )
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    visual_desc = Column(Text, nullable=True)
    asset_id = Column(Integer, ForeignKey("assets.id"), nullable=True)
    active_image_id = Column(Integer, nullable=True)
    sort_order = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    project = relationship("Project", back_populates="props")
    script = relationship("ProjectScript", back_populates="props")
    asset = relationship("Asset", foreign_keys=[asset_id])
    shots = relationship("ProjectShotProp", back_populates="prop", cascade="all, delete-orphan")
```

- [ ] **Step 4: 改造 ProjectShot 的 script_id 为 NOT NULL + 改唯一约束**

修改 `ProjectShot`（约 L278-337）。把 `script_id` 从 nullable=True 改为 nullable=False，并改唯一约束：

```python
class ProjectShot(Base):
    """项目分镜表"""
    __tablename__ = "project_shots"
    __table_args__ = (
        UniqueConstraint("project_id", "script_id", "sequence_no", name="uq_project_shots_seq"),
        Index("idx_project_shots_project", "project_id"),
        Index("idx_project_shots_script", "script_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    script_id = Column(
        Integer,
        ForeignKey("project_scripts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="所属集剧本ID",
    )
    sequence_no = Column(Integer, nullable=False)
    # ...其余字段保持不变（title/shot_type/camera_movement/angle/dialogue/visual_desc/atmosphere/image_prompt/duration_ms/scene_id/active_frame_image_id/active_video_id/active_audio_id/status/sort_order/created_at/updated_at）

    project = relationship("Project", back_populates="shots")
    script = relationship("ProjectScript", back_populates="shots")
    scene = relationship("ProjectScene", back_populates="shots")
    # ...其余 relationship 保持不变
```

- [ ] **Step 5: 给 ProjectScript 加反向 relationship**

修改 `ProjectScript`（约 L77-112），在现有 `shots = relationship(...)` 之前增加三个反向关系：

```python
    project = relationship("Project", back_populates="scripts")
    characters = relationship("ProjectCharacter", back_populates="script", cascade="all, delete-orphan")
    scenes = relationship("ProjectScene", back_populates="script", cascade="all, delete-orphan")
    props = relationship("ProjectProp", back_populates="script", cascade="all, delete-orphan")
    shots = relationship("ProjectShot", back_populates="script", cascade="all, delete-orphan")
```

- [ ] **Step 6: 语法检查**

Run: `cd /Users/skywing/agnes-platform/backend && python -c "from app.models.project import Project, ProjectScript, ProjectCharacter, ProjectScene, ProjectProp, ProjectShot; print('OK')"`
Expected: 输出 `OK`，无报错

- [ ] **Step 7: Commit**

```bash
git add backend/app/models/project.py
git commit -m "feat(models): 四张资源表新增 script_id NOT NULL 外键，分镜序号按集重置"
```

---

### Task 2: 重建数据库表

**Files:**
- 无文件改动，仅执行重建

- [ ] **Step 1: 删除并重建数据库表**

由于改了 NOT NULL 约束和唯一约束，按 AGENTS.md "不写迁移"规则直接重建。执行：

```bash
cd /Users/skywing/agnes-platform/backend
python -c "
import asyncio
from app.core.database import engine, Base
from app.models import project  # noqa: F401  确保所有模型加载

async def main():
    async with engine.begin() as conn:
        # 先 drop 受影响的表（含外键依赖顺序）
        await conn.run_sync(lambda c: Base.metadata.drop_all(bind=c, tables=[
            'project_shot_audios',
            'project_shot_videos',
            'project_shot_frame_images',
            'project_shot_props',
            'project_shot_characters',
            'project_shots',
            'project_character_voices',
            'project_props',
            'project_scenes',
            'project_characters',
            'project_scripts',
            'project_timeline_clips',
            'project_markers',
            'project_entity_assets',
            'projects',
        ]))
        await conn.run_sync(Base.metadata.create_all)
    print('重建完成')

asyncio.run(main())
"
```

Expected: 输出 `重建完成`，无报错

- [ ] **Step 2: 验证表结构**

```bash
cd /Users/skywing/agnes-platform/backend
python -c "
import asyncio
from sqlalchemy import inspect
from app.core.database import engine

async def main():
    async with engine.connect() as conn:
        def check(c):
            insp = inspect(c)
            for tbl in ['project_characters', 'project_scenes', 'project_props', 'project_shots']:
                cols = {col['name']: col for col in insp.get_columns(tbl)}
                assert 'script_id' in cols, f'{tbl} 缺少 script_id'
                assert not cols['script_id']['nullable'], f'{tbl}.script_id 应为 NOT NULL'
            # 验证唯一约束
            uqs = insp.get_unique_constraints('project_shots')
            names = {u['name'] for u in uqs}
            assert 'uq_project_shots_seq' in names
            print('表结构验证通过')
        await conn.run_sync(check)

asyncio.run(main())
"
```

Expected: 输出 `表结构验证通过`

---

## 阶段 2：后端 Schema 层

### Task 3: Schema 层改造

**Files:**
- Modify: `backend/app/schemas/project.py`

- [ ] **Step 1: 先读取现有 Schema 了解字段**

Run: `cd /Users/skywing/agnes-platform && head -n 400 backend/app/schemas/project.py | tail -n +100`
查看 CharacterCreate/Response、SceneCreate/Response、PropCreate/Response、ShotCreate/Response 的精确字段定义。

- [ ] **Step 2: 给四类 Create Schema 加 script_id 必填字段**

在 `backend/app/schemas/project.py` 中找到 `CharacterCreate`、`SceneCreate`、`PropCreate`、`ShotCreate` 四个类，每个类顶部加：

```python
class CharacterCreate(BaseModel):
    script_id: int = Field(..., description="所属集剧本ID")
    name: str
    # ...其余字段保持不变
```

```python
class SceneCreate(BaseModel):
    script_id: int = Field(..., description="所属集剧本ID")
    name: str
    # ...其余字段保持不变
```

```python
class PropCreate(BaseModel):
    script_id: int = Field(..., description="所属集剧本ID")
    name: str
    # ...其余字段保持不变
```

```python
class ShotCreate(BaseModel):
    script_id: int = Field(..., description="所属集剧本ID")
    sequence_no: int
    # ...其余字段保持不变
```

- [ ] **Step 3: 给四类 Response Schema 加 script_id 和 episode_no 字段**

找到 `CharacterResponse`、`SceneResponse`、`PropResponse`、`ShotResponse`，每个加：

```python
class CharacterResponse(BaseModel):
    id: int
    project_id: int
    script_id: int
    episode_no: int | None = None  # 来自 join ProjectScript，便于前端直接展示"第N集"
    name: str
    # ...其余字段保持不变
```

其余三个 Response 同理。

- [ ] **Step 4: 给 ScriptResponse 加计数字段**

找到 `ScriptResponse`，加四个可选计数字段：

```python
class ScriptResponse(BaseModel):
    id: int
    project_id: int
    episode_no: int
    title: str | None = None
    content: str | None = None
    # ...其余字段保持不变
    shot_count: int | None = None
    character_count: int | None = None
    scene_count: int | None = None
    prop_count: int | None = None
```

- [ ] **Step 5: 新增 ExtractRequest 和 CopyToRequest 请求体模型**

在 `backend/app/schemas/project.py` 末尾（或合适位置）加：

```python
class ExtractFromScriptRequest(BaseModel):
    """从剧本提取/拆分 请求体"""
    script_id: int


class CopyToScriptRequest(BaseModel):
    """跨集复制到目标集 请求体"""
    target_script_id: int
```

- [ ] **Step 6: 语法检查**

Run: `cd /Users/skywing/agnes-platform/backend && python -c "from app.schemas.project import CharacterCreate, CharacterResponse, ShotCreate, ShotResponse, ScriptResponse, ExtractFromScriptRequest, CopyToScriptRequest; print('OK')"`
Expected: 输出 `OK`

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas/project.py
git commit -m "feat(schemas): 四类 Create/Response 加 script_id/episode_no，新增 Extract/CopyTo 请求体"
```

---

## 阶段 3：后端 Service 层

### Task 4: shot_service 改造

**Files:**
- Modify: `backend/app/services/project/shot_service.py`

- [ ] **Step 1: 读取 shot_service 现有代码**

Run: `cd /Users/skywing/agnes-platform && wc -l backend/app/services/project/shot_service.py`
了解文件规模，然后用 Read 工具读取 `list_shots`、`create_shot`、`split_shots_from_script` 三个函数。

- [ ] **Step 2: 改造 list_shots 接收 script_id 可选参数**

把 `list_shots` 函数（约 L229-241）改为：

```python
async def list_shots(
    db: AsyncSession, project_id: int, script_id: Optional[int] = None
) -> List[ProjectShot]:
    """列出项目分镜（可选按集过滤）"""
    stmt = select(ProjectShot).where(ProjectShot.project_id == project_id)
    if script_id is not None:
        stmt = stmt.where(ProjectShot.script_id == script_id)
    stmt = stmt.order_by(ProjectShot.sort_order)
    result = await db.execute(stmt)
    items = result.scalars().all()
    # 批量填充 episode_no（避免 N+1）
    await _fill_episode_no(db, project_id, items)
    return items


async def _fill_episode_no(db: AsyncSession, project_id: int, items: List) -> None:
    """批量给资源列表填充 episode_no 字段（从 ProjectScript 查一次字典映射）"""
    if not items:
        return
    script_ids = {it.script_id for it in items if it.script_id is not None}
    if not script_ids:
        return
    result = await db.execute(
        select(ProjectScript.id, ProjectScript.episode_no).where(
            ProjectScript.id.in_(script_ids)
        )
    )
    ep_map = dict(result.all())
    for it in items:
        it.episode_no = ep_map.get(it.script_id)
```

注意：`ProjectScript` 和 `select` 需要在文件顶部 import。

- [ ] **Step 3: 改造 create_shot 接收并写入 script_id**

`create_shot` 函数（约 L256-294）改为接收 `script_id` 入参并写入。由于 `ShotCreate` schema 已含 `script_id`，直接从 `data` 取：

```python
async def create_shot(
    db: AsyncSession, project_id: int, data: ShotCreate
) -> ProjectShot:
    """新建分镜"""
    # 校验 script_id 属于该项目
    script = await db.get(ProjectScript, data.script_id)
    if not script or script.project_id != project_id:
        raise HTTPException(404, "剧本不存在或不属于该项目")

    # 计算 sequence_no 和 sort_order（按集）
    max_seq = (
        await db.execute(
            select(func.coalesce(func.max(ProjectShot.sequence_no), 0)).where(
                ProjectShot.script_id == data.script_id
            )
        )
    ).scalar() or 0
    max_order = (
        await db.execute(
            select(func.coalesce(func.max(ProjectShot.sort_order), 0)).where(
                ProjectShot.script_id == data.script_id
            )
        )
    ).scalar() or 0

    shot = ProjectShot(
        project_id=project_id,
        script_id=data.script_id,
        sequence_no=max_seq + 1,
        sort_order=max_order + 1,
        title=data.title,
        shot_type=data.shot_type,
        camera_movement=data.camera_movement,
        angle=data.angle,
        dialogue=data.dialogue,
        visual_desc=data.visual_desc,
        atmosphere=data.atmosphere,
        image_prompt=data.image_prompt,
        duration_ms=data.duration_ms or 3000,
        scene_id=data.scene_id,
        status="draft",
    )
    db.add(shot)
    await db.commit()
    await db.refresh(shot)
    return shot
```

注意：顶部需 import `HTTPException` from fastapi、`func` from sqlalchemy、`ProjectScript`。

- [ ] **Step 4: 改造 split_shots_from_script 接收 script_id**

把 `split_shots_from_script`（约 L553-691）签名和内部取剧本逻辑改为：

```python
async def split_shots_from_script(
    db: AsyncSession, project_id: int, script_id: int
) -> dict:
    """从剧本拆分分镜（按集，序号从 1 开始）"""
    # 精确查指定集剧本
    script = (
        await db.execute(
            select(ProjectScript).where(
                ProjectScript.id == script_id,
                ProjectScript.project_id == project_id,
            )
        )
    ).scalars().first()
    if not script:
        raise HTTPException(404, "剧本不存在或不属于该项目")
    if not script.content:
        raise HTTPException(400, "剧本内容为空，无法拆分分镜")

    # ... 中间 LLM 调用逻辑保持不变，使用 script.content ...

    # 序号计算改为按集
    max_seq = (
        await db.execute(
            select(func.coalesce(func.max(ProjectShot.sequence_no), 0)).where(
                ProjectShot.script_id == script_id
            )
        )
    ).scalar() or 0
    max_order = (
        await db.execute(
            select(func.coalesce(func.max(ProjectShot.sort_order), 0)).where(
                ProjectShot.script_id == script_id
            )
        )
    ).scalar() or 0

    # 创建 ProjectShot 时传 script_id=script.id
    # ... 在创建循环里：
    # shot = ProjectShot(
    #     project_id=project_id,
    #     script_id=script.id,
    #     sequence_no=max_seq + i + 1,
    #     sort_order=max_order + i + 1,
    #     ...
    # )

    await db.commit()
    return {"added": added}
```

**关键**：保留原有的 LLM 调用和解析逻辑，只改三处：
1. 函数签名加 `script_id` 参数
2. 取剧本从 `.first()` 改为按 `script_id` 精确查
3. 序号 max 计算从 `where(project_id)` 改为 `where(script_id)`
4. 创建 ProjectShot 时传 `script_id=script.id`

- [ ] **Step 5: 语法检查**

Run: `cd /Users/skywing/agnes-platform/backend && python -c "from app.services.project.shot_service import list_shots, create_shot, split_shots_from_script; print('OK')"`
Expected: 输出 `OK`

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/project/shot_service.py
git commit -m "feat(shot_service): split/list/create 接收 script_id，序号按集重置"
```

---

### Task 5: character_service 改造（含 copy_to）

**Files:**
- Modify: `backend/app/services/project/character_service.py`

- [ ] **Step 1: 改造 list_characters 接收 script_id 可选参数**

把 `list_characters`（约 L44-55）改为：

```python
async def list_characters(
    db: AsyncSession, project_id: int, script_id: Optional[int] = None
) -> List[ProjectCharacter]:
    """列出项目角色（可选按集过滤）"""
    stmt = select(ProjectCharacter).where(ProjectCharacter.project_id == project_id)
    if script_id is not None:
        stmt = stmt.where(ProjectCharacter.script_id == script_id)
    stmt = stmt.order_by(ProjectCharacter.sort_order)
    result = await db.execute(stmt)
    items = result.scalars().all()
    await attach_active_image_batch(db, ENTITY_TYPE, items)
    # 批量填充 episode_no
    await _fill_episode_no(db, items)
    return items


async def _fill_episode_no(db: AsyncSession, items: List) -> None:
    """批量给角色列表填充 episode_no 字段"""
    if not items:
        return
    script_ids = {it.script_id for it in items if it.script_id is not None}
    if not script_ids:
        return
    result = await db.execute(
        select(ProjectScript.id, ProjectScript.episode_no).where(
            ProjectScript.id.in_(script_ids)
        )
    )
    ep_map = dict(result.all())
    for it in items:
        it.episode_no = ep_map.get(it.script_id)
```

注意：顶部需 import `ProjectScript`（已有）、`Optional`（已有）。

- [ ] **Step 2: 改造 create_character 写入 script_id**

`create_character`（约 L71-97）改为从 `data.script_id` 取并写入：

```python
async def create_character(
    db: AsyncSession, project_id: int, data: CharacterCreate
) -> ProjectCharacter:
    """添加角色"""
    # 校验 script_id 属于该项目
    script = await db.get(ProjectScript, data.script_id)
    if not script or script.project_id != project_id:
        raise HTTPException(404, "剧本不存在或不属于该项目")

    # 计算 sort_order（按集追加到末尾）
    max_order = (
        await db.execute(
            select(func.max(ProjectCharacter.sort_order)).where(
                ProjectCharacter.script_id == data.script_id
            )
        )
    ).scalar() or 0

    character = ProjectCharacter(
        project_id=project_id,
        script_id=data.script_id,
        name=data.name,
        description=data.description,
        appearance_desc=data.appearance_desc,
        role_type=data.role_type or "supporting",
        sort_order=max_order + 1,
        asset_id=data.asset_id,
    )
    db.add(character)
    await db.commit()
    await db.refresh(character)
    await attach_active_image(db, ENTITY_TYPE, character)
    return character
```

注意：顶部 import `HTTPException` from fastapi。

- [ ] **Step 3: 改造 extract_characters_from_script 接收 script_id**

把 `extract_characters_from_script`（约 L363-443）签名和内部逻辑改为：

```python
async def extract_characters_from_script(
    db: AsyncSession, project_id: int, script_id: int
) -> dict:
    """从指定集剧本内容重新提取角色清单（追加到该集，不覆盖）"""
    # 精确查指定集剧本
    script = (
        await db.execute(
            select(ProjectScript).where(
                ProjectScript.id == script_id,
                ProjectScript.project_id == project_id,
            )
        )
    ).scalars().first()
    if not script:
        raise HTTPException(404, "剧本不存在或不属于该项目")
    if not script.content:
        raise HTTPException(400, "剧本内容为空，无法提取角色")

    prompt = (
        "请从以下剧本中提取所有角色信息，返回 JSON 格式：\n"
        '{"characters": [{"name": "角色名", "description": "简介", '
        '"appearance_desc": "外观描述", "role_type": "main|supporting|minor"}]}\n\n'
        f"剧本：\n{script.content}"
    )
    body = {
        "model": "agnes-2.0-flash",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.5,
    }
    result = await agnes_client._post(
        f"{agnes_client.base_url}/chat/completions", body
    )
    choices = result.get("choices", [])
    if not choices:
        return {"added": 0}
    text = choices[0].get("message", {}).get("content", "") or ""
    parsed = parse_json_loose(text)

    # 现有角色名集合（仅限该集，避免重复）
    existing = {
        c.name
        for c in (
            await db.execute(
                select(ProjectCharacter).where(
                    ProjectCharacter.script_id == script_id
                )
            )
        ).scalars().all()
    }

    max_order = (
        await db.execute(
            select(func.max(ProjectCharacter.sort_order)).where(
                ProjectCharacter.script_id == script_id
            )
        )
    ).scalar() or 0

    added = 0
    for item in parsed.get("characters", []):
        name = item.get("name", "").strip()
        if not name or name in existing:
            continue
        max_order += 1
        db.add(
            ProjectCharacter(
                project_id=project_id,
                script_id=script_id,
                name=name,
                description=item.get("description", ""),
                appearance_desc=item.get("appearance_desc", ""),
                role_type=item.get("role_type", "supporting"),
                sort_order=max_order,
            )
        )
        existing.add(name)
        added += 1

    await db.commit()
    return {"added": added}
```

- [ ] **Step 4: 新增 copy_character_to_script 函数**

在 `character_service.py` 末尾加：

```python
# =====================================================
# 跨集复制（深拷贝到目标集，不复制分镜关联）
# =====================================================

async def copy_character_to_script(
    db: AsyncSession, project_id: int, character_id: int, target_script_id: int
) -> ProjectCharacter:
    """
    把角色深拷贝到目标集（复制名称/描述/外观/形象图引用，不复制分镜关联）

    名称冲突时自动加"（副本）"后缀。
    """
    # 校验源角色属于 project
    src = await get_character(db, character_id)
    if not src or src.project_id != project_id:
        raise HTTPException(404, "源角色不存在")

    # 校验目标 script 属于 project
    target_script = await db.get(ProjectScript, target_script_id)
    if not target_script or target_script.project_id != project_id:
        raise HTTPException(404, "目标集剧本不存在")

    # 名称冲突处理
    existing = (
        await db.execute(
            select(ProjectCharacter).where(
                ProjectCharacter.script_id == target_script_id,
                ProjectCharacter.name == src.name,
            )
        )
    ).scalars().first()
    new_name = f"{src.name}（副本）" if existing else src.name

    # sort_order 追加到目标集末尾
    max_order = (
        await db.execute(
            select(func.max(ProjectCharacter.sort_order)).where(
                ProjectCharacter.script_id == target_script_id
            )
        )
    ).scalar() or 0

    new_entity = ProjectCharacter(
        project_id=project_id,
        script_id=target_script_id,
        name=new_name,
        description=src.description,
        appearance_desc=src.appearance_desc,
        role_type=src.role_type,
        asset_id=src.asset_id,
        active_image_id=src.active_image_id,
        sort_order=max_order + 1,
    )
    db.add(new_entity)
    await db.commit()
    await db.refresh(new_entity)
    await attach_active_image(db, ENTITY_TYPE, new_entity)
    return new_entity
```

- [ ] **Step 5: 语法检查**

Run: `cd /Users/skywing/agnes-platform/backend && python -c "from app.services.project.character_service import list_characters, create_character, extract_characters_from_script, copy_character_to_script; print('OK')"`
Expected: 输出 `OK`

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/project/character_service.py
git commit -m "feat(character_service): extract/list/create 接收 script_id，新增 copy_to_script"
```

---

### Task 6: scene_service 改造（含 copy_to）

**Files:**
- Modify: `backend/app/services/project/scene_service.py`

- [ ] **Step 1: 读取 scene_service 现有代码**

Run: `cd /Users/skywing/agnes-platform && wc -l backend/app/services/project/scene_service.py`
用 Read 工具读取 `list_scenes`、`create_scene`、`extract_scenes_from_script` 三个函数的精确位置。

- [ ] **Step 2: 改造 list_scenes 接收 script_id 可选参数**

参考 Task 5 Step 1 的模式，把 `list_scenes` 改为：

```python
async def list_scenes(
    db: AsyncSession, project_id: int, script_id: Optional[int] = None
) -> List[ProjectScene]:
    """列出项目场景（可选按集过滤）"""
    stmt = select(ProjectScene).where(ProjectScene.project_id == project_id)
    if script_id is not None:
        stmt = stmt.where(ProjectScene.script_id == script_id)
    stmt = stmt.order_by(ProjectScene.sort_order)
    result = await db.execute(stmt)
    items = result.scalars().all()
    await attach_active_image_batch(db, ENTITY_TYPE, items)
    await _fill_episode_no(db, items)
    return items


async def _fill_episode_no(db: AsyncSession, items: List) -> None:
    """批量给场景列表填充 episode_no 字段"""
    if not items:
        return
    script_ids = {it.script_id for it in items if it.script_id is not None}
    if not script_ids:
        return
    result = await db.execute(
        select(ProjectScript.id, ProjectScript.episode_no).where(
            ProjectScript.id.in_(script_ids)
        )
    )
    ep_map = dict(result.all())
    for it in items:
        it.episode_no = ep_map.get(it.script_id)
```

- [ ] **Step 3: 改造 create_scene 写入 script_id**

参考 Task 5 Step 2，`create_scene` 改为：

```python
async def create_scene(
    db: AsyncSession, project_id: int, data: SceneCreate
) -> ProjectScene:
    """添加场景"""
    script = await db.get(ProjectScript, data.script_id)
    if not script or script.project_id != project_id:
        raise HTTPException(404, "剧本不存在或不属于该项目")

    max_order = (
        await db.execute(
            select(func.max(ProjectScene.sort_order)).where(
                ProjectScene.script_id == data.script_id
            )
        )
    ).scalar() or 0

    scene = ProjectScene(
        project_id=project_id,
        script_id=data.script_id,
        name=data.name,
        description=data.description,
        location=data.location,
        time_of_day=data.time_of_day,
        atmosphere=data.atmosphere,
        sort_order=max_order + 1,
        asset_id=data.asset_id,
    )
    db.add(scene)
    await db.commit()
    await db.refresh(scene)
    await attach_active_image(db, ENTITY_TYPE, scene)
    return scene
```

- [ ] **Step 4: 改造 extract_scenes_from_script 接收 script_id**

参考 Task 5 Step 3 的模式，把 `extract_scenes_from_script` 签名改为 `(db, project_id, script_id)`，内部取剧本改为按 script_id 精确查，existing/max_order 都按 `script_id` 过滤，创建 ProjectScene 时传 `script_id=script_id`。LLM prompt 和解析逻辑保持不变。

- [ ] **Step 5: 新增 copy_scene_to_script 函数**

参考 Task 5 Step 4 的模式，在 scene_service.py 末尾加：

```python
async def copy_scene_to_script(
    db: AsyncSession, project_id: int, scene_id: int, target_script_id: int
) -> ProjectScene:
    """把场景深拷贝到目标集"""
    src = await get_scene(db, scene_id)
    if not src or src.project_id != project_id:
        raise HTTPException(404, "源场景不存在")

    target_script = await db.get(ProjectScript, target_script_id)
    if not target_script or target_script.project_id != project_id:
        raise HTTPException(404, "目标集剧本不存在")

    existing = (
        await db.execute(
            select(ProjectScene).where(
                ProjectScene.script_id == target_script_id,
                ProjectScene.name == src.name,
            )
        )
    ).scalars().first()
    new_name = f"{src.name}（副本）" if existing else src.name

    max_order = (
        await db.execute(
            select(func.max(ProjectScene.sort_order)).where(
                ProjectScene.script_id == target_script_id
            )
        )
    ).scalar() or 0

    new_entity = ProjectScene(
        project_id=project_id,
        script_id=target_script_id,
        name=new_name,
        description=src.description,
        location=src.location,
        time_of_day=src.time_of_day,
        atmosphere=src.atmosphere,
        asset_id=src.asset_id,
        active_image_id=src.active_image_id,
        sort_order=max_order + 1,
    )
    db.add(new_entity)
    await db.commit()
    await db.refresh(new_entity)
    await attach_active_image(db, ENTITY_TYPE, new_entity)
    return new_entity
```

- [ ] **Step 6: 语法检查**

Run: `cd /Users/skywing/agnes-platform/backend && python -c "from app.services.project.scene_service import list_scenes, create_scene, extract_scenes_from_script, copy_scene_to_script; print('OK')"`
Expected: 输出 `OK`

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/project/scene_service.py
git commit -m "feat(scene_service): extract/list/create 接收 script_id，新增 copy_to_script"
```

---

### Task 7: prop_service 改造（含 copy_to）

**Files:**
- Modify: `backend/app/services/project/prop_service.py`

- [ ] **Step 1: 读取 prop_service 现有代码**

Run: `cd /Users/skywing/agnes-platform && wc -l backend/app/services/project/prop_service.py`
用 Read 工具读取 `list_props`、`create_prop`、`extract_props_from_script` 三个函数。

- [ ] **Step 2: 改造 list_props 接收 script_id 可选参数**

参考 Task 6 Step 2 的模式，改 `list_props` 为接收可选 `script_id` 参数，加 `_fill_episode_no` 辅助函数。

- [ ] **Step 3: 改造 create_prop 写入 script_id**

参考 Task 6 Step 3 的模式。ProjectProp 的业务字段为 `name/description/visual_desc/asset_id/active_image_id/sort_order`，对应调整。

- [ ] **Step 4: 改造 extract_props_from_script 接收 script_id**

参考 Task 6 Step 4 的模式。

- [ ] **Step 5: 新增 copy_prop_to_script 函数**

参考 Task 6 Step 5 的模式，ProjectProp 的复制字段为 `name/description/visual_desc/asset_id/active_image_id`。

```python
async def copy_prop_to_script(
    db: AsyncSession, project_id: int, prop_id: int, target_script_id: int
) -> ProjectProp:
    """把道具深拷贝到目标集"""
    src = await get_prop(db, prop_id)
    if not src or src.project_id != project_id:
        raise HTTPException(404, "源道具不存在")

    target_script = await db.get(ProjectScript, target_script_id)
    if not target_script or target_script.project_id != project_id:
        raise HTTPException(404, "目标集剧本不存在")

    existing = (
        await db.execute(
            select(ProjectProp).where(
                ProjectProp.script_id == target_script_id,
                ProjectProp.name == src.name,
            )
        )
    ).scalars().first()
    new_name = f"{src.name}（副本）" if existing else src.name

    max_order = (
        await db.execute(
            select(func.max(ProjectProp.sort_order)).where(
                ProjectProp.script_id == target_script_id
            )
        )
    ).scalar() or 0

    new_entity = ProjectProp(
        project_id=project_id,
        script_id=target_script_id,
        name=new_name,
        description=src.description,
        visual_desc=src.visual_desc,
        asset_id=src.asset_id,
        active_image_id=src.active_image_id,
        sort_order=max_order + 1,
    )
    db.add(new_entity)
    await db.commit()
    await db.refresh(new_entity)
    await attach_active_image(db, ENTITY_TYPE, new_entity)
    return new_entity
```

- [ ] **Step 6: 语法检查**

Run: `cd /Users/skywing/agnes-platform/backend && python -c "from app.services.project.prop_service import list_props, create_prop, extract_props_from_script, copy_prop_to_script; print('OK')"`
Expected: 输出 `OK`

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/project/prop_service.py
git commit -m "feat(prop_service): extract/list/create 接收 script_id，新增 copy_to_script"
```

---

### Task 8: wizard.py 修复

**Files:**
- Modify: `backend/app/services/project/wizard.py`

- [ ] **Step 1: 读取 wizard.py 的 _step_storyboard_split 函数**

Run: `cd /Users/skywing/agnes-platform && sed -n '179,275p' backend/app/services/project/wizard.py`
查看创建 ProjectShot 的精确位置。

- [ ] **Step 2: 在创建 ProjectShot 时传 script_id**

在 `_step_storyboard_split` 函数（约 L179-275）中，找到创建 `ProjectShot(...)` 的地方（约 L235-238），给每个 ProjectShot 构造加 `script_id=script.id`：

```python
# 原来（缺失 script_id）：
# shot = ProjectShot(
#     project_id=project.id,
#     sequence_no=...,
#     sort_order=...,
#     ...
# )

# 改为：
shot = ProjectShot(
    project_id=project.id,
    script_id=script.id,  # 新增：强属于该集剧本
    sequence_no=...,
    sort_order=...,
    ...
)
```

**注意**：`_step_storyboard_split` 内部使用的 `script` 变量来自向导步骤 1 已创建的 script 对象（通过 `context.get("script_generation")` 或查询数据库）。需确认该函数内有 `script` 对象可用——如果没有，从 `project.scripts[0]` 取（向导只生成第一集）。

- [ ] **Step 3: 语法检查**

Run: `cd /Users/skywing/agnes-platform/backend && python -c "from app.services.project.wizard import _step_storyboard_split; print('OK')"`
Expected: 输出 `OK`

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/project/wizard.py
git commit -m "fix(wizard): 分镜步骤创建 ProjectShot 时传 script_id"
```

---

## 阶段 4：后端路由层

### Task 9: 路由层改造

**Files:**
- Modify: `backend/app/routes/projects.py`

- [ ] **Step 1: 读取路由层现有代码**

Run: `cd /Users/skywing/agnes-platform && wc -l backend/app/routes/projects.py`
用 Read 工具读取以下区间：
- list_shots_api（约 L949-971）
- split_shots_api（约 L986-997）
- 工厂模式 `_build_entity_routes`（约 L634-942），重点看 list handler 和 extract handler

- [ ] **Step 2: 改造 list_shots_api 支持 script_id query 参数**

把 `list_shots_api`（约 L949-971）改为：

```python
@router.get("/{project_id}/shots")
async def list_shots_api(
    project_id: int,
    script_id: int | None = None,
    db: AsyncSession = Depends(get_db),
):
    """列出项目分镜（可选 ?script_id=N 按集过滤）"""
    await _check_project_exists(db, project_id)
    items = await shot_service.list_shots(db, project_id, script_id)
    return items
```

- [ ] **Step 3: 改造 split_shots_api 接收请求体**

把 `split_shots_api`（约 L986-997）改为接收 `ExtractFromScriptRequest`：

```python
@router.post("/{project_id}/shots/split")
async def split_shots_api(
    project_id: int,
    req: ExtractFromScriptRequest,
    db: AsyncSession = Depends(get_db),
):
    """从剧本拆分分镜（按 script_id 指定的集）"""
    await _check_project_exists(db, project_id)
    result = await shot_service.split_shots_from_script(db, project_id, req.script_id)
    return result
```

注意：顶部需 import `ExtractFromScriptRequest` from `app.schemas.project`。

- [ ] **Step 4: 改造工厂模式 _build_entity_routes 的 list handler**

在 `_build_entity_routes` 函数内，找到 list handler（约 L696-708），改为接收可选 `script_id` query 参数：

```python
# 工厂内 list handler
async def list_api(
    project_id: int,
    script_id: int | None = None,
    db: AsyncSession = Depends(get_db),
):
    await _check_project_exists(db, project_id)
    items = await list_fn(db, project_id, script_id)
    return items
```

- [ ] **Step 5: 改造工厂模式 _build_entity_routes 的 extract handler**

找到 extract handler（约 L925-936），改为接收 `ExtractFromScriptRequest`：

```python
# 工厂内 extract handler
async def extract_api(
    project_id: int,
    req: ExtractFromScriptRequest,
    db: AsyncSession = Depends(get_db),
):
    await _check_project_exists(db, project_id)
    result = await extract_fn(db, project_id, req.script_id)
    return result
```

**注意**：工厂入参签名 `extract_fn` 的类型是 Callable，需确认 Service 层的 extract 函数签名已改为 `(db, project_id, script_id)`（Task 5/6/7 已完成）。

- [ ] **Step 6: 新增 copy-to 接口（工厂模式注册）**

在 `_build_entity_routes` 内，新增 copy-to handler 注册：

```python
# 工厂内 copy-to handler
async def copy_to_api(
    project_id: int,
    entity_id: int,
    req: CopyToScriptRequest,
    db: AsyncSession = Depends(get_db),
):
    await _check_project_exists(db, project_id)
    new_entity = await copy_to_fn(db, project_id, entity_id, req.target_script_id)
    return new_entity

router.add_api_route(
    f"/{{project_id}}/{prefix}/{{entity_id}}/copy-to",
    copy_to_api,
    methods=["POST"],
    summary=f"复制{entity_label}到其他集",
)
```

并在 `_build_entity_routes` 的入参签名加 `copy_to_fn: Callable` 参数，调用处（characters/scenes/props 三处）传入对应的 `copy_character_to_script` / `copy_scene_to_script` / `copy_prop_to_script`。

注意：顶部 import `CopyToScriptRequest`。

- [ ] **Step 7: 语法检查 + 启动后端验证路由注册**

Run: `cd /Users/skywing/agnes-platform/backend && python -c "from app.routes.projects import router; routes = [(r.path, list(r.methods)) for r in router.routes if 'copy-to' in r.path]; print(routes)"`
Expected: 输出包含三个 copy-to 路由

- [ ] **Step 8: Commit**

```bash
git add backend/app/routes/projects.py
git commit -m "feat(routes): list 加 script_id query、extract/split 改请求体、新增 copy-to 接口"
```

---

## 阶段 5：后端测试

### Task 10: 后端测试

**Files:**
- Create: `backend/tests/test_episode_isolation.py`

- [ ] **Step 1: 检查现有测试基础设施**

Run: `cd /Users/skywing/agnes-platform/backend && ls tests/ && cat tests/conftest.py 2>/dev/null | head -50`
了解现有 conftest.py 的 fixture（db session、client 等）。

- [ ] **Step 2: 编写测试文件**

创建 `backend/tests/test_episode_isolation.py`：

```python
"""集数隔离测试——验证四类资源强属于某一集、按集过滤、跨集复制、级联删除"""
import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import (
    Project, ProjectScript, ProjectCharacter, ProjectScene, ProjectProp, ProjectShot,
)


@pytest_asyncio.fixture
async def project_with_two_episodes(db: AsyncSession):
    """创建一个项目含两集剧本"""
    project = Project(title="测试项目", user_id=1, status="in_progress")
    db.add(project)
    await db.flush()
    s1 = ProjectScript(project_id=project.id, episode_no=1, title="第一集", content="第一集剧本内容")
    s2 = ProjectScript(project_id=project.id, episode_no=2, title="第二集", content="第二集剧本内容")
    db.add_all([s1, s2])
    await db.commit()
    await db.refresh(project)
    return project, s1, s2


@pytest.mark.asyncio
async def test_create_character_requires_script_id(client: AsyncClient, project_with_two_episodes):
    """不传 script_id 创建角色返回 422"""
    project, s1, s2 = project_with_two_episodes
    resp = await client.post(f"/api/projects/{project.id}/characters", json={"name": "角色A"})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_character_with_script_id(client: AsyncClient, db: AsyncSession, project_with_two_episodes):
    """传 script_id 创建角色成功，且归属正确"""
    project, s1, s2 = project_with_two_episodes
    resp = await client.post(
        f"/api/projects/{project.id}/characters",
        json={"script_id": s2.id, "name": "角色B"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["script_id"] == s2.id
    # 数据库验证
    char = await db.get(ProjectCharacter, data["id"])
    assert char.script_id == s2.id


@pytest.mark.asyncio
async def test_list_characters_filter_by_script_id(client: AsyncClient, db: AsyncSession, project_with_two_episodes):
    """?script_id=N 只返回该集角色"""
    project, s1, s2 = project_with_two_episodes
    db.add_all([
        ProjectCharacter(project_id=project.id, script_id=s1.id, name="角色1", sort_order=1),
        ProjectCharacter(project_id=project.id, script_id=s2.id, name="角色2", sort_order=1),
    ])
    await db.commit()

    resp = await client.get(f"/api/projects/{project.id}/characters?script_id={s2.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["name"] == "角色2"
    assert data[0]["script_id"] == s2.id


@pytest.mark.asyncio
async def test_list_characters_without_script_id_returns_all(client: AsyncClient, db: AsyncSession, project_with_two_episodes):
    """不传 script_id 返回全部集角色"""
    project, s1, s2 = project_with_two_episodes
    db.add_all([
        ProjectCharacter(project_id=project.id, script_id=s1.id, name="角色1", sort_order=1),
        ProjectCharacter(project_id=project.id, script_id=s2.id, name="角色2", sort_order=1),
    ])
    await db.commit()

    resp = await client.get(f"/api/projects/{project.id}/characters")
    assert resp.status_code == 200
    assert len(resp.json()) == 2


@pytest.mark.asyncio
async def test_shot_sequence_no_resets_per_script(client: AsyncClient, db: AsyncSession, project_with_two_episodes):
    """分镜序号按集重置——第二集分镜序号从 1 开始"""
    project, s1, s2 = project_with_two_episodes
    # 第一集两个分镜
    db.add_all([
        ProjectShot(project_id=project.id, script_id=s1.id, sequence_no=1, sort_order=1),
        ProjectShot(project_id=project.id, script_id=s1.id, sequence_no=2, sort_order=2),
    ])
    await db.commit()
    # 第二集创建分镜，应从 1 开始
    resp = await client.post(
        f"/api/projects/{project.id}/shots",
        json={"script_id": s2.id, "sequence_no": 1},
    )
    assert resp.status_code == 200
    shot = resp.json()
    assert shot["sequence_no"] == 1
    assert shot["script_id"] == s2.id


@pytest.mark.asyncio
async def test_split_shots_invalid_script_id_returns_404(client: AsyncClient, project_with_two_episodes):
    """不存在的 script_id 返回 404"""
    project, _, _ = project_with_two_episodes
    resp = await client.post(
        f"/api/projects/{project.id}/shots/split",
        json={"script_id": 999999},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_copy_character_to_other_episode(client: AsyncClient, db: AsyncSession, project_with_two_episodes):
    """跨集复制角色——目标集出现新记录，名称/形象图一致"""
    project, s1, s2 = project_with_two_episodes
    src = ProjectCharacter(
        project_id=project.id, script_id=s1.id, name="主角",
        description="描述", appearance_desc="外观", sort_order=1,
    )
    db.add(src)
    await db.commit()
    await db.refresh(src)

    resp = await client.post(
        f"/api/projects/{project.id}/characters/{src.id}/copy-to",
        json={"target_script_id": s2.id},
    )
    assert resp.status_code == 200
    new_char = resp.json()
    assert new_char["script_id"] == s2.id
    assert new_char["name"] == "主角"
    assert new_char["id"] != src.id


@pytest.mark.asyncio
async def test_copy_character_name_conflict_adds_suffix(client: AsyncClient, db: AsyncSession, project_with_two_episodes):
    """目标集已有同名时加（副本）后缀"""
    project, s1, s2 = project_with_two_episodes
    src = ProjectCharacter(project_id=project.id, script_id=s1.id, name="主角", sort_order=1)
    dst = ProjectCharacter(project_id=project.id, script_id=s2.id, name="主角", sort_order=1)
    db.add_all([src, dst])
    await db.commit()
    await db.refresh(src)

    resp = await client.post(
        f"/api/projects/{project.id}/characters/{src.id}/copy-to",
        json={"target_script_id": s2.id},
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "主角（副本）"


@pytest.mark.asyncio
async def test_delete_script_cascades_characters(db: AsyncSession, project_with_two_episodes):
    """删除某集剧本后该集角色级联删除"""
    project, s1, s2 = project_with_two_episodes
    db.add_all([
        ProjectCharacter(project_id=project.id, script_id=s1.id, name="角色1", sort_order=1),
        ProjectCharacter(project_id=project.id, script_id=s2.id, name="角色2", sort_order=1),
    ])
    await db.commit()

    # 删除第一集剧本
    await db.delete(s1)
    await db.commit()

    # 第一集角色应被级联删除，第二集保留
    from sqlalchemy import select
    remaining = (await db.execute(
        select(ProjectCharacter).where(ProjectCharacter.project_id == project.id)
    )).scalars().all()
    assert len(remaining) == 1
    assert remaining[0].script_id == s2.id


@pytest.mark.asyncio
async def test_response_includes_episode_no(client: AsyncClient, db: AsyncSession, project_with_two_episodes):
    """Response 带 episode_no 字段"""
    project, s1, _ = project_with_two_episodes
    db.add(ProjectCharacter(project_id=project.id, script_id=s1.id, name="角色", sort_order=1))
    await db.commit()

    resp = await client.get(f"/api/projects/{project.id}/characters")
    assert resp.status_code == 200
    assert resp.json()[0]["episode_no"] == 1
```

- [ ] **Step 3: 运行测试**

Run: `cd /Users/skywing/agnes-platform/backend && pytest tests/test_episode_isolation.py -v`
Expected: 全部测试通过（如有失败根据失败信息修复）

- [ ] **Step 4: Commit**

```bash
git add backend/tests/test_episode_isolation.py
git commit -m "test(episode_isolation): 新增集数隔离后端测试覆盖"
```

---

## 阶段 6：前端 API 层

### Task 11: 前端 API 层改造

**Files:**
- Modify: `frontend/src/api/projects.ts`

- [ ] **Step 1: 读取现有 API 代码**

Run: `cd /Users/skywing/agnes-platform && sed -n '200,310p' frontend/src/api/projects.ts`
查看 `buildEntityApi`、`listShots`、`extractFromScript`、`splitShotsFromScript` 的精确位置。

- [ ] **Step 2: 改造 buildEntityApi 的 list 接收 scriptId 可选参数**

把 `buildEntityApi` 内的 `list` 改为：

```typescript
list: (projectId: number, scriptId?: number) =>
  client.get(`/api/projects/${projectId}/${prefix}`, {
    params: scriptId !== undefined ? { script_id: scriptId } : undefined,
  }),
```

- [ ] **Step 3: 修复 extractFromScript 真正发送 scriptId**

把 `extractFromScript`（约 L226-228）从 `_scriptId` 改为 `scriptId` 并发送请求体：

```typescript
extractFromScript: (projectId: number, scriptId: number) =>
  client.post(`/api/projects/${projectId}/${prefix}/extract-from-script`, { script_id: scriptId }),
```

- [ ] **Step 4: 新增 copyTo 接口**

在 `buildEntityApi` 内新增：

```typescript
copyTo: (projectId: number, entityId: number, targetScriptId: number) =>
  client.post(`/api/projects/${projectId}/${prefix}/${entityId}/copy-to`, {
    target_script_id: targetScriptId,
  }),
```

- [ ] **Step 5: 改造 listShots 接收 scriptId 可选参数**

把 `listShots`（约 L270-272）改为：

```typescript
export function listShots(projectId: number, scriptId?: number): Promise<any> {
  return client.get(`/api/projects/${projectId}/shots`, {
    params: scriptId !== undefined ? { script_id: scriptId } : undefined,
  })
}
```

- [ ] **Step 6: 修复 splitShotsFromScript 真正发送 scriptId**

把 `splitShotsFromScript`（约 L298-300）从 `_scriptId` 改为 `scriptId` 并发送请求体：

```typescript
export function splitShotsFromScript(projectId: number, scriptId: number): Promise<any> {
  return client.post(`/api/projects/${projectId}/shots/split`, { script_id: scriptId })
}
```

- [ ] **Step 7: 类型检查**

Run: `cd /Users/skywing/agnes-platform/frontend && npx vue-tsc --noEmit 2>&1 | head -30`
Expected: 无新增类型错误（可能有已存在的无关错误）

- [ ] **Step 8: Commit**

```bash
git add frontend/src/api/projects.ts
git commit -m "feat(api): list 加 scriptId、修复 extract/split 丢弃 scriptId、新增 copyTo"
```

---

## 阶段 7：前端 Store 层

### Task 12: 前端 Store 层改造

**Files:**
- Modify: `frontend/src/stores/project.ts`

- [ ] **Step 1: state 增加 currentScriptId**

在 `ProjectState` 接口（约 L163-206）增加字段：

```typescript
interface ProjectState {
  // ...现有字段
  /* 当前选中的集剧本 ID（null=全部集视图，number=某集） */
  currentScriptId: number | null
  // ...
}
```

在 `state: (): ProjectState => ({...})`（约 L209-246）增加初始值：

```typescript
state: (): ProjectState => ({
  // ...现有字段
  currentScriptId: null,
  // ...
}),
```

- [ ] **Step 2: 增加 setCurrentScript action**

在 `actions` 内（约 L262 之后）增加：

```typescript
/** 切换当前集——自动重新拉取四类资源 */
async setCurrentScript(scriptId: number | null) {
  this.currentScriptId = scriptId
  if (!this.currentProjectId) return
  await Promise.all([
    this.fetchShots(),
    this.fetchEntities('character'),
    this.fetchEntities('scene'),
    this.fetchEntities('prop'),
  ])
},
```

- [ ] **Step 3: 改造 fetchShots 使用 currentScriptId**

把 `fetchShots`（约 L586-589）改为：

```typescript
async fetchShots() {
  if (!this.currentProjectId) return
  this.shots = await apiListShots(this.currentProjectId, this.currentScriptId ?? undefined)
},
```

- [ ] **Step 4: 改造 fetchEntities 使用 currentScriptId**

把 `fetchEntities`（约 L459-466）改为：

```typescript
async fetchEntities(entityType: EntityType) {
  if (!this.currentProjectId) return
  const api = getEntityApi(entityType)
  const list = await api.list(this.currentProjectId, this.currentScriptId ?? undefined)
  if (entityType === 'character') this.characters = list as ProjectCharacter[]
  else if (entityType === 'scene') this.scenes = list as ProjectScene[]
  else if (entityType === 'prop') this.props = list as ProjectProp[]
},
```

- [ ] **Step 5: 改造 createShot 校验 currentScriptId**

把 `createShot`（约 L591-596）改为：

```typescript
async createShot(data: ShotCreateRequest) {
  if (!this.currentProjectId) throw new Error('未选择项目')
  if (!this.currentScriptId) throw new Error('请先选择集数后再新建分镜')
  const shot = await apiCreateShot(this.currentProjectId, {
    ...data,
    script_id: this.currentScriptId,
  })
  this.shots.push(shot)
  return shot
},
```

注意：需确认 `ShotCreateRequest` 类型已含 `script_id` 字段——若没有，到 `frontend/src/types/project.ts` 加上。

- [ ] **Step 6: 增加 createEntity 校验 currentScriptId**

把 `createEntity`（约 L468-476）改为：

```typescript
async createEntity(entityType: EntityType, data: any) {
  if (!this.currentProjectId) throw new Error('未选择项目')
  if (!this.currentScriptId) throw new Error('请先选择集数后再新建')
  const api = getEntityApi(entityType)
  const entity = await api.create(this.currentProjectId, {
    ...data,
    script_id: this.currentScriptId,
  })
  if (entityType === 'character') this.characters.push(entity)
  else if (entityType === 'scene') this.scenes.push(entity)
  else if (entityType === 'prop') this.props.push(entity)
  return entity
},
```

- [ ] **Step 7: 增加 copyEntityTo action**

在 `actions` 内增加：

```typescript
/** 跨集复制角色/场景/道具到目标集 */
async copyEntityTo(
  entityType: EntityType,
  entityId: number,
  targetScriptId: number,
) {
  if (!this.currentProjectId) throw new Error('未选择项目')
  const api = getEntityApi(entityType)
  await api.copyTo(this.currentProjectId, entityId, targetScriptId)
  // 不自动切换到目标集，留在当前集
},
```

- [ ] **Step 8: 增加按集分组的 getter**

在 `getters`（约 L248-260）增加：

```typescript
getters: {
  // ...现有 getter
  /** 按 episode_no 分组的分镜（全部集视图用） */
  shotsByEpisode(state): Record<number, ProjectShot[]> {
    const grouped: Record<number, ProjectShot[]> = {}
    for (const shot of state.shots) {
      const ep = (shot as any).episode_no ?? 0
      ;(grouped[ep] ??= []).push(shot)
    }
    return grouped
  },
  /** 按 episode_no 分组的角色 */
  charactersByEpisode(state): Record<number, ProjectCharacter[]> {
    const grouped: Record<number, ProjectCharacter[]> = {}
    for (const c of state.characters) {
      const ep = (c as any).episode_no ?? 0
      ;(grouped[ep] ??= []).push(c)
    }
    return grouped
  },
  /** 按 episode_no 分组的场景 */
  scenesByEpisode(state): Record<number, ProjectScene[]> {
    const grouped: Record<number, ProjectScene[]> = {}
    for (const s of state.scenes) {
      const ep = (s as any).episode_no ?? 0
      ;(grouped[ep] ??= []).push(s)
    }
    return grouped
  },
  /** 按 episode_no 分组的道具 */
  propsByEpisode(state): Record<number, ProjectProp[]> {
    const grouped: Record<number, ProjectProp[]> = {}
    for (const p of state.props) {
      const ep = (p as any).episode_no ?? 0
      ;(grouped[ep] ??= []).push(p)
    }
    return grouped
  },
},
```

- [ ] **Step 9: clearCurrent 同步清空 currentScriptId**

把 `clearCurrent`（约 L301-317）增加 `this.currentScriptId = null`：

```typescript
clearCurrent() {
  this.currentProject = null
  this.currentProjectId = null
  this.currentScriptId = null  // 新增
  this.scripts = []
  // ...其余清空保持不变
},
```

- [ ] **Step 10: 类型检查**

Run: `cd /Users/skywing/agnes-platform/frontend && npx vue-tsc --noEmit 2>&1 | grep -E "project.ts|stores" | head -20`
Expected: 无新增类型错误

- [ ] **Step 11: Commit**

```bash
git add frontend/src/stores/project.ts frontend/src/types/project.ts
git commit -m "feat(store): 新增 currentScriptId 状态、setCurrentScript、按集分组 getter、copyEntityTo"
```

---

## 阶段 8：前端 UI 层

### Task 13: 顶部集数切换器

**Files:**
- Modify: `frontend/src/components/project/ProjectManagerView.vue`

- [ ] **Step 1: 读取 ProjectManagerView 现有代码**

Run: `cd /Users/skywing/agnes-platform && cat frontend/src/components/project/ProjectManagerView.vue`
了解顶部布局和 Tab 结构。

- [ ] **Step 2: 在顶部新增集数切换器**

在 `<template>` 内 Tab 栏之上新增：

```vue
<template>
  <div class="project-manager">
    <!-- 集数切换器 -->
    <div class="episode-switcher-bar">
      <span class="label">{{ t('project.currentEpisode') }}</span>
      <el-select
        v-model="currentScriptId"
        :placeholder="t('project.selectEpisode')"
        @change="onScriptChange"
        style="width: 260px"
      >
        <el-option :label="t('project.allEpisodes')" :value="null" />
        <el-option
          v-for="script in projectStore.scripts"
          :key="script.id"
          :label="`第${script.episode_no}集：${script.title || ''}`"
          :value="script.id"
        />
      </el-select>
    </div>

    <!-- 原有 Tab 栏 -->
    <el-tabs v-model="activeTab" ...>
      <!-- ... -->
    </el-tabs>
  </div>
</template>
```

- [ ] **Step 3: 在 script setup 增加 currentScriptId 和 onScriptChange**

```vue
<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useProjectStore } from '@/stores/project'
import { useI18n } from 'vue-i18n'

const projectStore = useProjectStore()
const { t } = useI18n()

// ...原有 activeTab 等

const currentScriptId = ref<number | null>(projectStore.currentScriptId)

async function onScriptChange(val: number | null) {
  await projectStore.setCurrentScript(val)
}

onMounted(async () => {
  // 首次进入默认选中第一集，避免一进来就拉全量
  if (projectStore.currentScriptId === null && projectStore.scripts.length > 0) {
    currentScriptId.value = projectStore.scripts[0].id
    await projectStore.setCurrentScript(projectStore.scripts[0].id)
  }
})
</script>
```

- [ ] **Step 4: 增加 scoped CSS**

```vue
<style scoped>
.episode-switcher-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}
.episode-switcher-bar .label {
  font-size: 14px;
  color: var(--el-text-color-regular);
}
</style>
```

- [ ] **Step 5: 类型检查**

Run: `cd /Users/skywing/agnes-platform/frontend && npx vue-tsc --noEmit 2>&1 | grep ProjectManagerView | head -10`
Expected: 无错误

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/project/ProjectManagerView.vue
git commit -m "feat(ui): ProjectManagerView 顶部新增集数切换器"
```

---

### Task 14: ShotsTab 改造

**Files:**
- Modify: `frontend/src/components/project/ShotsTab.vue`

- [ ] **Step 1: 读取 ShotsTab 现有代码**

Run: `cd /Users/skywing/agnes-platform && cat frontend/src/components/project/ShotsTab.vue`

- [ ] **Step 2: 列表数据来源改为按集区分**

把列表 computed（约 L134-135）改为：

```typescript
const isAllEpisodeView = computed(() => projectStore.currentScriptId === null)
const shots = computed(() => projectStore.shots)
const shotsByEpisode = computed(() => projectStore.shotsByEpisode)
const canCreate = computed(() => projectStore.currentScriptId !== null)
```

- [ ] **Step 3: 模板增加全部集分组视图 + 新建按钮禁用**

```vue
<template>
  <div class="shots-tab">
    <div class="toolbar">
      <el-button :disabled="!canCreate" @click="onCreateShot">
        {{ t('project.createShot') }}
      </el-button>
      <el-tooltip v-if="!canCreate" :content="t('project.selectEpisodeFirst')" placement="top">
        <el-icon><InfoFilled /></el-icon>
      </el-tooltip>
      <el-button :disabled="!canCreate" @click="onSplitFromScript">
        {{ t('project.splitFromScript') }}
      </el-button>
    </div>

    <!-- 全部集视图：按集分组 -->
    <template v-if="isAllEpisodeView">
      <el-collapse v-for="(epShots, ep) in shotsByEpisode" :key="ep">
        <el-collapse-item :title="`第${ep}集（${epShots.length} 个分镜）`">
          <ShotCard v-for="shot in epShots" :key="shot.id" :shot="shot" />
        </el-collapse-item>
      </el-collapse>
    </template>

    <!-- 单集视图：直接展示 -->
    <template v-else>
      <ShotCard v-for="shot in shots" :key="shot.id" :shot="shot" />
    </template>
  </div>
</template>
```

- [ ] **Step 4: 增加 onSplitFromScript 使用 currentScriptId**

```typescript
async function onSplitFromScript() {
  if (!projectStore.currentScriptId) return
  await projectStore.splitShotsFromScript(projectStore.currentScriptId)
}
```

- [ ] **Step 5: 顶部 import 增加 InfoFilled 图标**

```typescript
import { InfoFilled } from '@element-plus/icons-vue'
```

- [ ] **Step 6: 类型检查 + Commit**

Run: `cd /Users/skywing/agnes-platform/frontend && npx vue-tsc --noEmit 2>&1 | grep ShotsTab | head -10`

```bash
git add frontend/src/components/project/ShotsTab.vue
git commit -m "feat(ui): ShotsTab 支持按集分组视图、新建/拆分按集禁用"
```

---

### Task 15: CharactersTab 改造（含跨集复制）

**Files:**
- Modify: `frontend/src/components/project/CharactersTab.vue`

- [ ] **Step 1: 读取 CharactersTab 现有代码**

Run: `cd /Users/skywing/agnes-platform && cat frontend/src/components/project/CharactersTab.vue`

- [ ] **Step 2: 修复 onExtractFromScript 使用 currentScriptId**

把 `onExtractFromScript`（约 L141-165）改为：

```typescript
async function onExtractFromScript() {
  if (!projectStore.currentScriptId) {
    ElMessage.warning(t('project.selectEpisodeFirst'))
    return
  }
  await projectStore.extractEntitiesFromScript('character', projectStore.currentScriptId)
}
```

**移除原来的 `const script = projectStore.scripts[0]` 硬编码。**

- [ ] **Step 3: 增加跨集复制按钮和 onCopyTo**

在角色卡片模板内增加：

```vue
<el-dropdown @command="(cmd: number) => onCopyTo(character.id, cmd)">
  <el-button size="small" text>
    <el-icon><CopyDocument /></el-icon>
    {{ t('project.copyToEpisode') }}
  </el-button>
  <template #dropdown>
    <el-dropdown-menu>
      <el-dropdown-item
        v-for="script in otherScripts"
        :key="script.id"
        :command="script.id"
      >
        第{{ script.episode_no }}集：{{ script.title }}
      </el-dropdown-item>
    </el-dropdown-menu>
  </template>
</el-dropdown>
```

```typescript
import { CopyDocument } from '@element-plus/icons-vue'

const otherScripts = computed(() =>
  projectStore.scripts.filter(s => s.id !== projectStore.currentScriptId)
)

async function onCopyTo(entityId: number, targetScriptId: number) {
  if (!projectStore.currentScriptId) return
  try {
    await projectStore.copyEntityTo('character', entityId, targetScriptId)
    ElMessage.success(t('project.copiedToEpisode'))
  } catch (e: any) {
    ElMessage.error(e?.message || '复制失败')
  }
}
```

- [ ] **Step 4: 增加全部集分组视图和新建禁用**

参考 Task 14 Step 3，在模板增加 `isAllEpisodeView` 判断 + `canCreate` 禁用逻辑。

- [ ] **Step 5: 类型检查 + Commit**

Run: `cd /Users/skywing/agnes-platform/frontend && npx vue-tsc --noEmit 2>&1 | grep CharactersTab | head -10`

```bash
git add frontend/src/components/project/CharactersTab.vue
git commit -m "feat(ui): CharactersTab 修复 extract 用 currentScriptId、新增跨集复制、按集分组"
```

---

### Task 16: ScenesTab 改造

**Files:**
- Modify: `frontend/src/components/project/ScenesTab.vue`

- [ ] **Step 1: 读取 ScenesTab 现有代码**

Run: `cd /Users/skywing/agnes-platform && cat frontend/src/components/project/ScenesTab.vue`

- [ ] **Step 2: 修复 onExtractFromScript 使用 currentScriptId**

参考 Task 15 Step 2，把 `onExtractFromScript`（约 L141-164）的 `const script = projectStore.scripts[0]` 移除，改用 `projectStore.currentScriptId`，entityType 传 `'scene'`。

- [ ] **Step 3: 增加跨集复制按钮**

参考 Task 15 Step 3，复制按钮调用 `projectStore.copyEntityTo('scene', scene.id, targetScriptId)`。

- [ ] **Step 4: 增加全部集分组视图和新建禁用**

参考 Task 15 Step 4。

- [ ] **Step 5: 类型检查 + Commit**

Run: `cd /Users/skywing/agnes-platform/frontend && npx vue-tsc --noEmit 2>&1 | grep ScenesTab | head -10`

```bash
git add frontend/src/components/project/ScenesTab.vue
git commit -m "feat(ui): ScenesTab 修复 extract、新增跨集复制、按集分组"
```

---

### Task 17: PropsTab 改造

**Files:**
- Modify: `frontend/src/components/project/PropsTab.vue`

- [ ] **Step 1: 读取 PropsTab 现有代码**

Run: `cd /Users/skywing/agnes-platform && cat frontend/src/components/project/PropsTab.vue`

- [ ] **Step 2: 修复 onExtractFromScript 使用 currentScriptId**

参考 Task 15 Step 2，entityType 传 `'prop'`。

- [ ] **Step 3: 增加跨集复制按钮**

参考 Task 15 Step 3，调用 `projectStore.copyEntityTo('prop', prop.id, targetScriptId)`。

- [ ] **Step 4: 增加全部集分组视图和新建禁用**

参考 Task 15 Step 4。

- [ ] **Step 5: 类型检查 + Commit**

Run: `cd /Users/skywing/agnes-platform/frontend && npx vue-tsc --noEmit 2>&1 | grep PropsTab | head -10`

```bash
git add frontend/src/components/project/PropsTab.vue
git commit -m "feat(ui): PropsTab 修复 extract、新增跨集复制、按集分组"
```

---

### Task 18: i18n

**Files:**
- Modify: `frontend/src/i18n/index.ts`（或现有 i18n 文件结构）

- [ ] **Step 1: 定位 i18n 文件**

Run: `cd /Users/skywing/agnes-platform && ls frontend/src/i18n/`

- [ ] **Step 2: 新增集数切换相关 key**

在中文 locale 文件的 `project` 命名空间下增加：

```typescript
export default {
  project: {
    // ...现有 key
    currentEpisode: '当前集',
    allEpisodes: '全部集',
    selectEpisode: '请选择集',
    selectEpisodeFirst: '请先选择集数后再操作',
    copyToEpisode: '复制到其他集',
    copiedToEpisode: '已复制到目标集',
    splitFromScript: '从剧本拆分',
  },
}
```

英文 locale 对应增加：

```typescript
export default {
  project: {
    currentEpisode: 'Episode',
    allEpisodes: 'All Episodes',
    selectEpisode: 'Select episode',
    selectEpisodeFirst: 'Please select an episode first',
    copyToEpisode: 'Copy to episode',
    copiedToEpisode: 'Copied to target episode',
    splitFromScript: 'Split from script',
  },
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/i18n/
git commit -m "feat(i18n): 新增集数切换相关 i18n key"
```

---

## 阶段 9：验证

### Task 19: 类型检查与手动验证

**Files:**
- 无文件改动

- [ ] **Step 1: 后端类型检查**

Run: `cd /Users/skywing/agnes-platform/backend && mypy app/models/project.py app/schemas/project.py app/services/project/character_service.py app/services/project/scene_service.py app/services/project/prop_service.py app/services/project/shot_service.py app/routes/projects.py --ignore-missing-imports 2>&1 | tail -20`
Expected: 无新增错误

- [ ] **Step 2: 前端类型检查**

Run: `cd /Users/skywing/agnes-platform/frontend && npx vue-tsc --noEmit 2>&1 | tail -30`
Expected: 无新增错误

- [ ] **Step 3: 后端测试全量**

Run: `cd /Users/skywing/agnes-platform/backend && pytest tests/test_episode_isolation.py -v`
Expected: 全部通过

- [ ] **Step 4: 启动后端 + 前端验证**

```bash
# 终端 1
cd /Users/skywing/agnes-platform/backend && uvicorn app.main:app --reload
# 终端 2
cd /Users/skywing/agnes-platform/frontend && npm run dev
```

- [ ] **Step 5: 手动验证清单**

按以下步骤手动验证（来自 spec 9.3 节）：

1. 创建项目，向导生成第一集剧本和分镜——验证向导流程不报错
2. 在剧本 Tab 新增第二集剧本
3. 顶部切换器选"第2集"，进入分镜 Tab，点击"从剧本拆分"——验证第二集分镜序号从 1 开始，不混入第一集
4. 切换到"全部集"视图——验证按集分组展示
5. 在第二集 Tab 点击"从剧本提取角色"——验证用第二集剧本内容（看角色名是否符合第二集剧本）
6. 在第一集角色卡片点击"复制到其他集"选第二集，切换到第二集验证角色出现
7. 删除第二集剧本——验证第二集的分镜/角色/场景/道具全部消失，第一集不受影响
8. 全部集视图下"新建"按钮禁用并显示提示

- [ ] **Step 6: 最终 Commit**

如果有任何修复，提交：

```bash
git add -A
git commit -m "fix(episode_isolation): 手动验证发现的问题修复"
```

---

## 自审记录

**Spec coverage 检查**：
- 四、数据模型层 → Task 1 ✓
- 五、Schema/Service/路由 → Task 3/4/5/6/7/8/9 ✓
- 六、前端 API/Store → Task 11/12 ✓
- 七、前端 UI → Task 13/14/15/16/17 ✓
- 八、错误处理 → Task 4/5/6/7/9（HTTPException）+ Task 12/15（前端拦截）✓
- 九、测试策略 → Task 10/19 ✓
- 十、改动文件清单 → 全部覆盖 ✓
- 十一、风险与权衡 → Task 8 缓解向导风险、Task 5/6/7 copy 缓解复用、Task 19 验证 ✓

**Placeholder 扫描**：Task 4 Step 4 的 split 函数用了 `...` 省略中间 LLM 调用逻辑——这是为了让实现者保留原有逻辑只改三处，已在步骤里明确"保留原有的 LLM 调用和解析逻辑"。Task 6/7 的部分步骤引用"参考 Task N 的模式"并给出了完整代码模板，符合 skill 要求。

**Type consistency**：
- `currentScriptId` 在 Store/UI/API 全链路命名一致
- `script_id` 在后端 Model/Schema/Service/Route 命名一致
- `copyEntityTo` / `copyTo` / `copy_xxx_to_script` 命名风格符合各层约定
- `shotsByEpisode` / `charactersByEpisode` 等 getter 命名一致

---

## 执行选择

计划已保存到 `docs/superpowers/plans/2026-07-07-episode-isolation.md`。两种执行方式：

1. **Subagent-Driven（推荐）**：每个 Task 派发独立 subagent，任务间 review，迭代快
2. **Inline Execution**：在当前会话内按 Task 顺序执行，带 checkpoint 审查

请选择执行方式。
