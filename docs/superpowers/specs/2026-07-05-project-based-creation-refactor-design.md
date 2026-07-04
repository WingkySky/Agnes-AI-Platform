# 项目制创作重构设计文档

> **版本**: 1.0
> **日期**: 2026-07-05
> **状态**: 设计稿（待评审）
> **作者**: brainstorming session 产出

## 摘要

本设计将 agnes-platform 的"流水线实例"抽象替换为"项目（Project）"抽象，借鉴 LingGuo-Drama 的"引导性生成 + 逐个适配"范式，同时保留 agnes 现有的 DAG 引擎元素级重试、无限画布、预设中心、模板市场、资产库、内容审核、积分体系等优势。

重构后，**项目成为顶层载体**，承载剧本、角色、场景、道具、分镜等独立实体。每个实体都是独立持久化资源，可单独编辑/重生/上传替换/删除。生成动作从"整条 DAG 流水线"降级为"项目内的局部操作"。

---

## 1. 背景与动机

### 1.1 LingGuo-Drama 的优势

通过研读 [LingGuo-Drama](https://github.com/LingGuoAI/LingGuo-Drama) 的前后端实现，识别出两个核心优势：

1. **引导性生成**：AI 先从剧本"提取"实体清单（角色/场景/道具），用户可在生成前编辑清单，再决定哪些生成、哪些手动上传。这是"AI 提案 + 人工确认"的范式。
2. **逐个适配**：每个实体都是独立资源，挂载 AI 生成/编辑/上传/批量/重排等操作，互不阻塞。

### 1.2 agnes-platform 现状

- 流水线实例（PipelineRun）为顶层载体，结果压在 step.output_data JSON 里
- 实体无独立 CRUD 入口，只能在流水线运行中操作
- 已有 DAG 引擎 + 元素级重试 + 编辑 + apply stale + ignore stale 等精细能力
- 已有无限画布、预设中心、模板市场、资产库、内容审核、积分等

### 1.3 重构目标

把 LingGuo-Drama 的"引导性生成 + 逐个适配"范式引入 agnes-platform，同时保留 agnes 独有优势。

---

## 2. 关键决策汇总

| 决策点 | 选择 | 说明 |
|--------|------|------|
| 项目与 PipelineRun 关系 | **A1** | 项目替代 PipelineRun，模板保留为创建向导 |
| 实体表数量 | **B1** | 完整 7 张表（scripts/characters/scenes/props/shots/frame_images/videos） |
| 项目实体与公共资产库关系 | **C2** | 引用模式：项目实体记录 asset_id，可双向互转 |
| 引导性生成交互形态 | **D2** | 模板向导式：选模板→填参数→AI 一次性产出→进入项目逐个调整 |
| 分镜生成输入边界 | **E2** | 分镜基于"已确认的角色/场景/道具清单"生成，绑定关系更准 |
| 分镜帧图/视频多版本管理 | **F1** | 多版本 + 当前采用版（is_active） |
| 素材上传替换 | **G1** | 上传作为新版本（is_manual=true），保留 AI 生成历史 |
| 成片合成形态 | **H1** | 完整多轨时间线编辑器 |
| 字幕和配音 | **I1** | 字幕 + TTS 配音都做 |
| 无限画布定位 | **J4** | 双视图：管理视图（卡片/表格）+ 画布视图（节点式）切换 |
| 现有 PipelineRun 历史数据 | **K1** | 直接废弃不迁移（项目未上线） |
| PipelineTemplate 处理 | **L1** | 模板保留为"项目创建向导"，steps_config 语义改为 wizard_chain |
| 实施范围 | **M1** | 完整设计，分阶段实施（Phase 1 核心 + Phase 2 时间线 + Phase 3 生态） |
| 重构影响范围 | **N1** | 允许大范围重构（前端路由/菜单/API 大改） |

---

## 3. 架构概览

### 3.1 体系结构

```
模板市场（WorkshopView）
   │ 选模板 + 填参数
   ▼
项目创建向导（D2：AI 一次性产出 剧本+实体清单+分镜）
   │ 创建完成
   ▼
┌─────────────────────────────────────────────────┐
│ 项目详情页（ProjectDetail）                       │
│ ┌────────────┐  ┌──────────────────────────┐   │
│ │ 管理视图    │  │ 画布视图（J4）            │   │
│ │ 卡片/表格   │◄►│ 节点式编辑                │   │
│ │ LingGuo风格 │  │ agnes 独有优势            │   │
│ └────────────┘  └──────────────────────────┘   │
│                                                 │
│ Tab：剧本 / 角色 / 场景 / 道具 / 分镜 / 时间线    │
└─────────────────────────────────────────────────┘
```

### 3.2 核心模块边界

| 模块 | 职责 | 处理方式 |
|------|------|---------|
| `services/project/` | 项目 CRUD、实体协调、生成动作调度 | **新增**，替代 `services/pipeline/` |
| `services/project/wizard.py` | 模板向导式创建：执行 LLM 链产出初始实体 | **新增** |
| `services/project/entities/` | 角色/场景/道具/分镜/帧图/视频的 CRUD + 重生 + 上传 | **新增** |
| `services/project/timeline.py` | 时间线编辑、合成调度 | **新增**（Phase 2） |
| `services/project/canvas_bridge.py` | 项目 ↔ 画布双视图同步 | **新增**（Phase 3） |
| `models/project.py` | Project + 7 张实体表 | **新增** |
| `services/pipeline/` | 旧流水线引擎 | **删除**（K1） |
| `models/pipeline.py` 中的 Run/Step | 旧流水线实例 | **删除**（K1） |
| `models/pipeline.py` 中的 Template | 保留，语义改为"项目创建向导模板"（L1） | **改造** |
| `services/agnes_client.py` `services/agn_sdk_client.py` | AI 调用层 | **保留复用** |
| `services/asset_library.py` | 公共资产库 | **保留**，新增"项目实体 ↔ 资产"互转（C2） |
| `services/moderation_service.py` | 内容审核 | **保留复用** |
| `services/credits_service.py` | 积分扣减 | **保留复用** |
| 无限画布（`InfiniteCanvas.vue` / `stores/canvas.ts`） | 画布编辑器 | **保留**，新增"项目画布视图"模式（J4） |

### 3.3 生成动作清单

| 动作 | 输入 | 输出 | 调用方式 |
|------|------|------|---------|
| `generate_script` | 主题/参数 | scripts 记录 | 同步 LLM |
| `extract_entities` | script | characters/scenes/props 批量记录 | 同步 LLM |
| `generate_storyboard` | script + 已确认实体清单 | shots 批量记录 | 同步 LLM |
| `generate_frame_image` | shot | shot_frame_image 记录（多版本） | 异步图片生成 |
| `generate_video` | shot_frame_image | shot_generate_video 记录（多版本） | 异步视频生成 |
| `generate_tts` | shot 对白 | audio 记录（Phase 2） | 异步 TTS |
| `merge_video` | 时间线配置 | 最终成片 | 异步 ffmpeg |

每个动作支持：单个触发 / 批量触发（多选）/ 全部触发。

### 3.4 与现有体系的关系定位

- **PipelineTemplate（模板市场）**：保留，`steps_config` 字段语义改为"向导 LLM 链定义"。WorkshopView 改造为"模板市场入口"。
- **Asset（资产库）**：保留为公共资产池。项目实体有可选 `asset_id` 字段引用资产库来源；项目完成后用户可"沉淀"实体为 assets 表新版本。
- **无限画布**：保留，新增"项目画布视图"模式。项目实体同步为画布节点，画布上的编辑可回写到实体。
- **广场**：保留，最终成片可发布到广场，走现有审核流程。
- **TaskQueue**：保留，项目内的异步生成动作作为任务进队列。
- **PipelineRun / PipelineStep / PipelineStepOutputRevision**：删除，不再使用。
- **PipelineHistoryView / PipelineRunView / PipelineResultView**：废弃或重写为 ProjectHistoryView / ProjectDetailView。

---

## 4. 数据模型

### 4.1 表清单总览

Phase 1 新增 11 张表（projects + 7 张实体表 + project_entity_assets + 2 张多对多关联表），Phase 2 新增 3 张表（audios / character_voices / timeline_clips），删除 3 张旧表，保留并改造 pipeline_templates。

| 表名 | 说明 | 阶段 |
|------|------|------|
| `projects` | 项目主表 | Phase 1 |
| `project_scripts` | 剧本（一项目多分集） | Phase 1 |
| `project_characters` | 角色实体 | Phase 1 |
| `project_scenes` | 场景实体 | Phase 1 |
| `project_props` | 道具实体 | Phase 1 |
| `project_shots` | 分镜实体 | Phase 1 |
| `project_shot_frame_images` | 分镜帧图（多版本） | Phase 1 |
| `project_shot_videos` | 分镜视频（多版本） | Phase 1 |
| `project_shot_audios` | 分镜配音（多版本） | Phase 2 |
| `project_timeline_clips` | 时间线轨道片段 | Phase 2 |
| `project_entity_assets` | 实体素材多版本（统一表） | Phase 1 |
| `project_shot_characters` | 分镜-角色多对多关联 | Phase 1 |
| `project_shot_props` | 分镜-道具多对多关联 | Phase 1 |
| `project_character_voices` | 角色-音色映射 | Phase 2 |
| `pipeline_templates` | 改造：项目创建向导模板 | Phase 1 改造 |
| ~~`pipeline_runs`~~ | 删除 | K1 |
| ~~`pipeline_steps`~~ | 删除 | K1 |
| ~~`pipeline_step_output_revisions`~~ | 删除 | K1 |

### 4.2 表结构详细设计

#### 4.2.1 projects — 项目主表

```sql
CREATE TABLE projects (
    id              SERIAL PRIMARY KEY,
    title           VARCHAR(200) NOT NULL,
    description     TEXT,
    template_id     INTEGER REFERENCES pipeline_templates(id),
    user_id         INTEGER NOT NULL REFERENCES users(id),
    status          VARCHAR(30) DEFAULT 'draft',  -- draft/creating/in_progress/merging/completed/archived
    cover_url       VARCHAR(500),
    aspect_ratio    VARCHAR(20) DEFAULT '16:9',
    resolution      VARCHAR(20) DEFAULT '1280x720',
    wizard_inputs   JSON DEFAULT '{}'::json,
    active_view     VARCHAR(20) DEFAULT 'manager',  -- manager/canvas
    canvas_data     JSON DEFAULT '{}'::json,
    timeline_data   JSON DEFAULT '{}'::json,
    final_video_url VARCHAR(500),
    total_duration  FLOAT DEFAULT 0,
    started_at      TIMESTAMP,
    finished_at     TIMESTAMP,
    created_at      TIMESTAMP DEFAULT NOW(),
    updated_at      TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_projects_user ON projects(user_id);
CREATE INDEX idx_projects_status ON projects(status);
```

`status` 状态机：
```
draft → creating（向导运行中）→ in_progress（项目已创建，可逐个适配）→ merging（合成中）→ completed → archived
```

#### 4.2.2 project_scripts — 剧本表（含分集）

```sql
CREATE TABLE project_scripts (
    id              SERIAL PRIMARY KEY,
    project_id      INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    episode_no      INTEGER DEFAULT 1,
    title           VARCHAR(200),
    content         TEXT,
    outline         TEXT,
    model           VARCHAR(100),
    prompt_template TEXT,
    tokens_used     INTEGER DEFAULT 0,
    status          VARCHAR(30) DEFAULT 'draft',
    created_at      TIMESTAMP DEFAULT NOW(),
    updated_at      TIMESTAMP DEFAULT NOW(),
    UNIQUE(project_id, episode_no)
);
CREATE INDEX idx_project_scripts_project ON project_scripts(project_id);
```

#### 4.2.3 project_characters — 角色实体表

```sql
CREATE TABLE project_characters (
    id              SERIAL PRIMARY KEY,
    project_id      INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name            VARCHAR(100) NOT NULL,
    description     TEXT,
    appearance_desc TEXT,
    role_type       VARCHAR(20) DEFAULT 'supporting',  -- main/supporting/minor
    asset_id        INTEGER REFERENCES assets(id),     -- C2 引用模式
    active_image_id INTEGER,                           -- 指向 project_entity_assets
    sort_order      INTEGER DEFAULT 0,
    created_at      TIMESTAMP DEFAULT NOW(),
    updated_at      TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_project_characters_project ON project_characters(project_id);
```

#### 4.2.4 project_entity_assets — 实体素材多版本表（统一）

```sql
CREATE TABLE project_entity_assets (
    id              SERIAL PRIMARY KEY,
    project_id      INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    entity_type     VARCHAR(20) NOT NULL,  -- character/scene/prop
    entity_id       INTEGER NOT NULL,      -- 多态引用：指向 project_characters/scenes/props 的 id（应用层保证一致性，不设外键）
    version         INTEGER DEFAULT 1,
    is_active       BOOLEAN DEFAULT FALSE,
    is_manual       BOOLEAN DEFAULT FALSE,
    file_url        VARCHAR(500),
    thumbnail_url   VARCHAR(500),
    prompt          TEXT,
    model           VARCHAR(100),
    generation_id   INTEGER REFERENCES generations(id),
    file_type       VARCHAR(20),
    file_size       BIGINT,
    duration_ms     INTEGER,
    width           INTEGER,
    height          INTEGER,
    created_by      VARCHAR(20) DEFAULT 'ai',  -- ai/manual/import
    created_at      TIMESTAMP DEFAULT NOW(),
    UNIQUE(entity_type, entity_id, version)
);
CREATE INDEX idx_pea_project ON project_entity_assets(project_id);
CREATE INDEX idx_pea_entity ON project_entity_assets(entity_type, entity_id);
CREATE INDEX idx_pea_active ON project_entity_assets(entity_type, entity_id, is_active);
```

#### 4.2.5 project_scenes / project_props

```sql
CREATE TABLE project_scenes (
    id              SERIAL PRIMARY KEY,
    project_id      INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name            VARCHAR(100) NOT NULL,
    description     TEXT,
    location        VARCHAR(200),
    time_of_day     VARCHAR(50),
    atmosphere      TEXT,
    asset_id        INTEGER REFERENCES assets(id),
    active_image_id INTEGER,
    sort_order      INTEGER DEFAULT 0,
    created_at      TIMESTAMP DEFAULT NOW(),
    updated_at      TIMESTAMP DEFAULT NOW()
);

CREATE TABLE project_props (
    id              SERIAL PRIMARY KEY,
    project_id      INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name            VARCHAR(100) NOT NULL,
    description     TEXT,
    visual_desc     TEXT,
    asset_id        INTEGER REFERENCES assets(id),
    active_image_id INTEGER,
    sort_order      INTEGER DEFAULT 0,
    created_at      TIMESTAMP DEFAULT NOW(),
    updated_at      TIMESTAMP DEFAULT NOW()
);
```

#### 4.2.6 project_shots — 分镜表

```sql
CREATE TABLE project_shots (
    id              SERIAL PRIMARY KEY,
    project_id      INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    script_id       INTEGER REFERENCES project_scripts(id),
    sequence_no     INTEGER NOT NULL,
    title           VARCHAR(200),
    shot_type       VARCHAR(50),       -- 景别
    camera_movement VARCHAR(50),       -- 运镜
    angle           VARCHAR(50),       -- 视角
    dialogue        TEXT,              -- 台词/旁白（用于 TTS）
    visual_desc     TEXT,
    atmosphere      TEXT,
    image_prompt    TEXT,              -- 绘画 prompt
    duration_ms     INTEGER DEFAULT 3000,
    scene_id        INTEGER REFERENCES project_scenes(id),
    active_frame_image_id INTEGER,
    active_video_id        INTEGER,
    active_audio_id        INTEGER,   -- Phase 2
    status          VARCHAR(30) DEFAULT 'draft',
    sort_order      INTEGER DEFAULT 0,
    created_at      TIMESTAMP DEFAULT NOW(),
    updated_at      TIMESTAMP DEFAULT NOW(),
    UNIQUE(project_id, sequence_no)
);
CREATE INDEX idx_project_shots_project ON project_shots(project_id);
```

#### 4.2.7 分镜-角色/道具关联表

```sql
CREATE TABLE project_shot_characters (
    shot_id         INTEGER NOT NULL REFERENCES project_shots(id) ON DELETE CASCADE,
    character_id    INTEGER NOT NULL REFERENCES project_characters(id) ON DELETE CASCADE,
    sort_order      INTEGER DEFAULT 0,
    PRIMARY KEY (shot_id, character_id)
);

CREATE TABLE project_shot_props (
    shot_id         INTEGER NOT NULL REFERENCES project_shots(id) ON DELETE CASCADE,
    prop_id         INTEGER NOT NULL REFERENCES project_props(id) ON DELETE CASCADE,
    sort_order      INTEGER DEFAULT 0,
    PRIMARY KEY (shot_id, prop_id)
);
```

#### 4.2.8 project_shot_frame_images — 分镜帧图多版本

```sql
CREATE TABLE project_shot_frame_images (
    id              SERIAL PRIMARY KEY,
    shot_id         INTEGER NOT NULL REFERENCES project_shots(id) ON DELETE CASCADE,
    version         INTEGER DEFAULT 1,
    is_active       BOOLEAN DEFAULT FALSE,
    is_manual       BOOLEAN DEFAULT FALSE,
    file_url        VARCHAR(500),
    thumbnail_url   VARCHAR(500),
    prompt          TEXT,
    model           VARCHAR(100),
    generation_id   INTEGER REFERENCES generations(id),
    reference_character_ids JSON DEFAULT '[]'::json,
    width           INTEGER,
    height          INTEGER,
    file_size       BIGINT,
    created_by      VARCHAR(20) DEFAULT 'ai',
    created_at      TIMESTAMP DEFAULT NOW(),
    UNIQUE(shot_id, version)
);
CREATE INDEX idx_psf_shot ON project_shot_frame_images(shot_id);
```

#### 4.2.9 project_shot_videos — 分镜视频多版本

```sql
CREATE TABLE project_shot_videos (
    id              SERIAL PRIMARY KEY,
    shot_id         INTEGER NOT NULL REFERENCES project_shots(id) ON DELETE CASCADE,
    version         INTEGER DEFAULT 1,
    is_active       BOOLEAN DEFAULT FALSE,
    is_manual       BOOLEAN DEFAULT FALSE,
    file_url        VARCHAR(500),
    thumbnail_url   VARCHAR(500),
    frame_image_id  INTEGER REFERENCES project_shot_frame_images(id),
    prompt          TEXT,
    model           VARCHAR(100),
    generation_id   INTEGER REFERENCES generations(id),
    duration_ms     INTEGER,
    width           INTEGER,
    height          INTEGER,
    file_size       BIGINT,
    created_by      VARCHAR(20) DEFAULT 'ai',
    created_at      TIMESTAMP DEFAULT NOW(),
    UNIQUE(shot_id, version)
);
CREATE INDEX idx_psv_shot ON project_shot_videos(shot_id);
```

#### 4.2.10 project_shot_audios — 分镜配音多版本（Phase 2）

```sql
CREATE TABLE project_shot_audios (
    id              SERIAL PRIMARY KEY,
    shot_id         INTEGER NOT NULL REFERENCES project_shots(id) ON DELETE CASCADE,
    version         INTEGER DEFAULT 1,
    is_active       BOOLEAN DEFAULT FALSE,
    is_manual       BOOLEAN DEFAULT FALSE,
    file_url        VARCHAR(500),
    text            TEXT,
    voice_id        VARCHAR(100),
    character_id    INTEGER REFERENCES project_characters(id),
    model           VARCHAR(100),
    duration_ms     INTEGER,
    file_size       BIGINT,
    created_by      VARCHAR(20) DEFAULT 'ai',
    created_at      TIMESTAMP DEFAULT NOW(),
    UNIQUE(shot_id, version)
);
```

#### 4.2.11 project_character_voices — 角色-音色映射（Phase 2）

```sql
CREATE TABLE project_character_voices (
    id              SERIAL PRIMARY KEY,
    project_id      INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    character_id    INTEGER NOT NULL REFERENCES project_characters(id) ON DELETE CASCADE,
    voice_id        VARCHAR(100) NOT NULL,
    voice_name      VARCHAR(200),
    assigned_at     TIMESTAMP DEFAULT NOW(),
    UNIQUE(project_id, character_id)
);
```

#### 4.2.12 project_timeline_clips — 时间线片段（Phase 2）

```sql
CREATE TABLE project_timeline_clips (
    id              SERIAL PRIMARY KEY,
    project_id      INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    track_type      VARCHAR(20) NOT NULL,  -- video/pip/audio/subtitle
    track_index     INTEGER DEFAULT 0,
    source_type     VARCHAR(20),           -- shot_video/shot_audio/bgm/subtitle
    source_id       INTEGER,
    shot_id         INTEGER REFERENCES project_shots(id),
    start_time      FLOAT NOT NULL,
    duration        FLOAT NOT NULL,
    trim_start      FLOAT DEFAULT 0,
    trim_end        FLOAT,
    transition_type VARCHAR(50),           -- fade/slide/wipe/dissolve/none
    transition_duration FLOAT DEFAULT 0,
    subtitle_text   TEXT,
    sort_order      INTEGER DEFAULT 0,
    created_at      TIMESTAMP DEFAULT NOW(),
    updated_at      TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_ptc_project ON project_timeline_clips(project_id);
CREATE INDEX idx_ptc_track ON project_timeline_clips(project_id, track_type, track_index);
```

### 4.3 pipeline_templates 改造（L1）

`pipeline_templates` 表结构保留，但 `steps_config` 字段语义从"DAG 步骤定义"改为"项目创建向导 LLM 链定义"：

```json
{
  "wizard_chain": [
    {
      "key": "script_generation",
      "name": "剧本生成",
      "type": "llm_generate",
      "prompt_template": "根据主题{topic}生成剧本...",
      "output_target": "project_scripts"
    },
    {
      "key": "entity_extraction",
      "name": "实体提取",
      "type": "llm_generate",
      "prompt_template": "从剧本提取角色/场景/道具清单...",
      "output_target": "project_characters+project_scenes+project_props",
      "depends_on": ["script_generation"]
    },
    {
      "key": "storyboard_split",
      "name": "分镜拆分",
      "type": "llm_generate",
      "prompt_template": "基于剧本+实体清单拆分分镜...",
      "output_target": "project_shots",
      "depends_on": ["entity_extraction"]
    },
    {
      "key": "frame_prompt_extract",
      "name": "帧 prompt 提取",
      "type": "llm_generate",
      "prompt_template": "为每个分镜提取帧级绘画 prompt...",
      "output_target": "project_shots.image_prompt",
      "depends_on": ["storyboard_split"]
    }
  ]
}
```

模板只负责"创建项目时的一次性 LLM 链"，项目创建完成后所有操作都在项目详情页内独立触发。

### 4.4 关键设计决策

1. **多版本统一表**：project_entity_assets 统一存放角色/场景/道具的多版本素材，避免 3 张子表
2. **分镜素材独立表**：帧图/视频/音频作为分镜的子表，因为是分镜独有概念
3. **active_*_id 字段**：分镜/实体表都记录"当前采用版"指针，避免每次查询都扫描版本表
4. **is_manual 标识**：所有多版本表都有此字段，区分 AI 生成与用户上传（G1）
5. **canvas_data JSON 字段**：画布视图状态存在 projects 表，不单独建表（J4）
6. **timeline_data JSON + project_timeline_clips 表双存**：JSON 存草稿，clips 表存最终时间线

---

## 5. 引导式生成流程

### 5.1 整体流程

```
┌─────────────────────────────────────────────────────────────────┐
│ 阶段一：项目创建向导（D2 - 自动 LLM 链）                          │
│                                                                 │
│  1. 选模板 + 填参数                                              │
│  2. LLM: 生成剧本 → 写入 project_scripts                        │
│  3. LLM: 从剧本提取实体清单 → 写入 characters/scenes/props       │
│  4. LLM: 基于剧本+实体清单拆分分镜 (E2) → 写入 shots + 关联表    │
│  5. LLM: 为每个分镜提取帧级绘画 prompt → 更新 shots.image_prompt │
│                                                                 │
│  → 项目状态: creating → in_progress                              │
│  → 跳转项目详情页，进入阶段二                                      │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 阶段二：项目内逐个适配（手动触发 - 见第 6 节）                     │
└─────────────────────────────────────────────────────────────────┘
```

### 5.2 项目创建向导执行器

新增 `services/project/wizard.py`：

```python
class ProjectWizard:
    """项目创建向导：按模板的 wizard_chain 顺序执行 LLM 链"""
    
    async def create_project(self, template_id: int, user_id: int, inputs: dict) -> Project:
        # 1. 创建 project 记录（status=creating）
        project = await self._create_project_record(template_id, user_id, inputs)
        
        # 2. 加载模板的 wizard_chain
        chain = template.wizard_chain
        
        # 3. 按 depends_on 拓扑序执行 LLM 链
        context = {"inputs": inputs}
        for step in topological_sort(chain):
            result = await self._execute_wizard_step(step, project, context)
            context[step["key"]] = result
            await sse_manager.push(project.id, "wizard_step_done", step)
        
        # 4. 项目状态: creating → in_progress
        project.status = "in_progress"
        return project
```

### 5.3 各步骤详细逻辑

#### 步骤 1：剧本生成（script_generation）

LLM 接收主题参数，输出剧本正文 + 大纲，写入 `project_scripts`。

#### 步骤 2：实体提取（entity_extraction）

LingGuo-Drama 的核心"引导性"——AI **提取**而非凭空生成。LLM 接收剧本，输出结构化的角色/场景/道具清单（JSON 格式），批量写入对应表。

**关键点**：实体清单写入后就是项目内的独立资源，用户可在项目详情页编辑（改描述、删减、手动添加）。

#### 步骤 3：分镜拆分（storyboard_split）

E2 的核心：分镜基于"已确认实体清单"生成，绑定关系更准。Prompt 里注入实体清单（参考 LingGuo-Drama `ai_shots_job.go` 的 charInfoStr/sceneInfoStr/propInfoStr 做法）：

```python
char_info = json.dumps(entities["characters"], ensure_ascii=False)
scene_info = json.dumps(entities["scenes"], ensure_ascii=False)
prop_info = json.dumps(entities["props"], ensure_ascii=False)

prompt = render_template(step["prompt_template"], {
    "script": script_content,
    "characters": char_info,
    "scenes": scene_info,
    "props": prop_info
})
```

LLM 输出分镜列表，每镜绑定 characterIds/sceneId/propIds，批量写入 `project_shots` + 关联表。

#### 步骤 4：帧级 prompt 提取（frame_prompt_extract）

参考 LingGuo-Drama 的 `extract_frame_prompt_job`。可选步骤——如果步骤 3 的 LLM 已经给出 `image_prompt`，可以跳过。对于复杂分镜，单独跑一次 prompt 提取能得到更精细的画面描述。

### 5.4 向导进度推送

向导链是同步 LLM 链（每步等上一步完成），但前端需要实时进度。复用现有 sse_manager 改造为 `project_sse_manager`：

```
POST /api/projects/wizard
  ↓ 立即返回 project_id（status=creating）
  ↓ 后台异步执行 wizard_chain

GET /api/projects/{id}/events (SSE)
event: wizard_step_started
data: {"step": "script_generation", "name": "剧本生成"}

event: wizard_step_completed
data: {"step": "entity_extraction", "stats": {"characters": 5, "scenes": 3, "props": 2}}

event: wizard_completed
data: {"project_id": 123, "status": "in_progress"}
```

### 5.5 容错策略

1. **JSON 解析容错**：`parse_json_loose()` 支持代码块包裹、字段缺失、类型不符等
2. **字段补全**：必填字段缺失时用默认值
3. **重试**：单步 LLM 失败时重试 2 次
4. **部分成功保留**：即使某步失败，已写入的实体保留，用户可在项目详情页继续手动操作
5. **向导失败可重入**：项目卡在 `creating` 状态时，可调用 `POST /api/projects/{id}/wizard/resume` 从失败步骤继续

### 5.6 空白创建路径

支持"空白创建"作为兜底——用户不选模板，直接创建空项目，手动添加剧本/角色/场景/道具/分镜。覆盖以下场景：
- 用户已有剧本，只想用 agnes 的逐个适配能力
- 用户想从资产库挑选角色/场景组成项目
- 向导失败后用户手动补全

```
POST /api/projects
  body: {title, description, aspect_ratio, template_id: null}
  → 创建空项目，status=in_progress
  → 跳转项目详情页，所有 Tab 为空
```

### 5.7 关键设计决策

1. **向导链是同步 LLM 链，非 DAG**：向导目的是"一次性产出初始实体"，无并行需求，顺序更可控
2. **每步产出立即落库**：LLM 每步完成立即写入对应表，即使后续步骤失败也不丢失
3. **实体提取是"结构化提取"而非"自由生成"**：要求 LLM 输出 JSON，字段对应实体表结构
4. **分镜拆分注入实体清单**（E2）：让 LLM 在拆分镜时直接绑定 characterIds/sceneId/propIds
5. **帧级 prompt 提取作为可选步骤**：模板可配置是否单独跑这一步

---

## 6. 逐个适配机制

### 6.1 能力矩阵

| 实体 | 编辑 | 单个生成 | 批量生成 | 上传替换 | 删除 | 添加 | 重排 | 版本切换 | 沉淀到资产库 |
|------|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| 剧本 | ✓ | (重生成) | - | (上传文本) | - | (新分集) | - | - | - |
| 角色 | ✓ | ✓ 生图 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| 场景 | ✓ | ✓ 生图 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| 道具 | ✓ | ✓ 生图 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| 分镜 | ✓ | ✓ 帧图/视频/TTS | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | - |
| 帧图版本 | - | ✓ 重生 | - | ✓ | ✓ | ✓ | - | ✓ 设采用 | - |
| 视频版本 | - | ✓ 重生 | - | ✓ | ✓ | ✓ | - | ✓ 设采用 | - |

所有操作都是**独立 API 调用**，互不阻塞。复用现有 `taskQueue.ts` 异步任务管理。

### 6.2 服务层结构

```
backend/app/services/project/
├── __init__.py
├── wizard.py              # 项目创建向导
├── project_service.py     # 项目 CRUD
├── script_service.py      # 剧本 CRUD + 重生成
├── character_service.py   # 角色 CRUD + 生成 + 上传 + 沉淀
├── scene_service.py       # 场景（同上）
├── prop_service.py        # 道具（同上）
├── shot_service.py        # 分镜 CRUD + 绑定实体 + 重排
├── frame_image_service.py # 帧图多版本管理 + 生成 + 上传
├── video_service.py       # 视频多版本管理 + 生成 + 上传
├── audio_service.py       # TTS 配音（Phase 2）
├── timeline_service.py    # 时间线编辑 + 合成（Phase 2）
├── asset_bridge.py        # 项目实体 ↔ 公共资产库互转（C2）
└── sse_manager.py         # 项目级 SSE 推送
```

### 6.3 角色生成详细流程（其他实体同理）

#### 6.3.1 单个角色生图

```python
async def generate_character_image(
    character_id: int,
    user_id: int,
    style_config: dict = None
) -> ProjectEntityAsset:
    """为单个角色生成形象图"""
    char = await ProjectCharacter.get(id=character_id)
    
    # 1. 构造 prompt
    prompt = build_character_prompt(char, style_config)
    
    # 2. 调用图片生成 API（复用 agnes_client）
    gen_result = await agnes_client.generate_image(
        prompt=prompt,
        model="agnes-image-1.0",
        size="1024x1024",
        reference_images=get_asset_reference_images(char.asset_id)  # C2
    )
    
    # 3. 写入 generations 表
    generation = await create_generation_record(...)
    
    # 4. 创建新版本记录（F1，默认 is_active=False）
    next_version = await get_next_version("character", char.id)
    new_asset = await ProjectEntityAsset.create(
        project_id=char.project_id,
        entity_type="character",
        entity_id=char.id,
        version=next_version,
        is_active=False,  # 用户手动切换
        is_manual=False,
        file_url=gen_result.url,
        prompt=prompt,
        model="agnes-image-1.0",
        generation_id=generation.id,
        file_type="image",
        created_by="ai"
    )
    
    # 5. 推送 SSE
    await project_sse_manager.push(char.project_id, "entity_image_generated", {...})
    
    return new_asset
```

#### 6.3.2 批量生图

每个角色生成作为独立任务进队列，**项目级并发控制**：单个项目同时运行的图片任务上限 5 个、视频任务上限 2 个（全局并发上限由 task_queue 配置决定）。

#### 6.3.3 上传替换（G1）

```python
async def upload_entity_image(entity_type, entity_id, user_id, file):
    """用户上传图片替代 AI 生成结果"""
    file_url = await asset_storage.upload(file)
    
    next_version = await get_next_version(entity_type, entity_id)
    new_asset = await ProjectEntityAsset.create(
        entity_type=entity_type,
        entity_id=entity_id,
        version=next_version,
        is_active=False,
        is_manual=True,  # 标记为手动上传
        file_url=file_url,
        file_type="image",
        created_by="manual"
        # prompt/model/generation_id 为空
    )
    return new_asset
```

#### 6.3.4 设为采用版（F1）

```python
async def set_active_version(entity_type, entity_id, version_id):
    """切换实体的当前采用版本"""
    # 1. 取消同实体其他版本的 is_active
    await ProjectEntityAsset.filter(
        entity_type=entity_type, entity_id=entity_id, is_active=True
    ).update(is_active=False)
    
    # 2. 设置目标版本为 active
    await ProjectEntityAsset.filter(id=version_id).update(is_active=True)
    
    # 3. 更新实体表的 active_image_id 指针
    # 4. 推送 SSE（影响下游可用性）
```

#### 6.3.5 从剧本重新提取（LingGuo-Drama 范式）

参考 LingGuo-Drama `detail.vue` 的 `openExtractCharDialog`：

```python
async def extract_entities_from_script(project_id, entity_type):
    """从剧本重新提取实体清单（不覆盖已有，追加新发现的）"""
    script = await ProjectScript.get(project_id=project_id)
    prompt = f"""从以下剧本中提取{entity_type}清单..."""
    result = await agnes_client.chat(...)
    parsed = parse_json_loose(result.text)
    
    # 追加新实体（同名跳过）
    existing_names = await get_existing_names(project_id, entity_type)
    for e in parsed.get("items", []):
        if e["name"] not in existing_names:
            await create_entity(project_id, entity_type, e)
```

### 6.4 分镜逐个适配

#### 6.4.1 分镜帧图生成（带角色参考图）

复用现有 [template_scenarios.py](file:///Users/skywing/agnes-platform/backend/app/services/pipeline/template_scenarios.py#L114) `reference_from_step` 机制，改为直接读取分镜绑定的角色 active_image：

```python
async def generate_frame_image(shot_id, user_id, style_config=None):
    shot = await ProjectShot.get(id=shot_id)
    
    # 1. 获取分镜绑定的角色的当前采用图（参考图）
    char_refs = await get_shot_character_active_images(shot.id)
    
    # 2. 构造 prompt
    prompt = build_frame_prompt(shot.image_prompt, style_config)
    
    # 3. 调用图生图 API（reference_images 注入角色参考图）
    gen_result = await agnes_client.generate_image(
        prompt=prompt,
        model="agnes-image-1.0",
        size=get_size_from_aspect_ratio(shot.project.aspect_ratio),
        reference_images=char_refs  # 角色参考图保持人物一致性
    )
    
    # 4. 写入 generations 表 + 创建新版本
    # ...
```

#### 6.4.2 分镜视频生成（基于采用帧图）

```python
async def generate_shot_video(shot_id, user_id, frame_image_id=None):
    shot = await ProjectShot.get(id=shot_id)
    
    # 1. 确定来源帧图（默认用 active）
    if frame_image_id:
        frame = await ProjectShotFrameImage.get(id=frame_image_id)
    else:
        frame = await get_active_frame_image(shot.id)
        if not frame:
            raise BusinessError("分镜尚未有采用的帧图，请先生成或上传")
    
    # 2. 构造 prompt + 调用视频生成 API（图生视频）
    # 3. 写入 generations 表 + 创建新版本
```

#### 6.4.3 分镜编辑

```python
async def update_shot(shot_id, update_data):
    shot = await ProjectShot.get(id=shot_id)
    
    # 记录编辑前的字段，判断是否影响下游
    affected_fields = []
    if "image_prompt" in update_data and update_data["image_prompt"] != shot.image_prompt:
        affected_fields.append("image_prompt")  # 影响帧图生成
    if "dialogue" in update_data and update_data["dialogue"] != shot.dialogue:
        affected_fields.append("dialogue")  # 影响 TTS
    
    await shot.update(**update_data)
    
    # 推送 SSE：提示用户哪些下游素材可能需要重生
    if affected_fields:
        await project_sse_manager.push(shot.project_id, "shot_edited", {
            "shot_id": shot_id,
            "affected_fields": affected_fields,
            "message": "分镜已修改，相关素材可能需要重新生成"
        })
```

#### 6.4.4 分镜重排

```python
async def reorder_shots(project_id, shot_ids_in_order):
    for idx, sid in enumerate(shot_ids_in_order):
        await ProjectShot.filter(id=sid).update(sequence_no=idx + 1, sort_order=idx)
    
    # 推送 SSE：影响时间线顺序
    await project_sse_manager.push(project_id, "shots_reordered", {...})
```

### 6.5 项目实体 ↔ 公共资产库互转（C2）

#### 6.5.1 资产库 → 项目实体

```python
async def import_asset_to_project(asset_id, project_id, user_id):
    """从公共资产库导入实体到项目"""
    asset = await Asset.get(id=asset_id)
    
    # 1. 创建项目实体，记录 asset_id 引用
    entity = await ProjectCharacter.create(
        project_id=project_id,
        name=asset.name,
        description=asset.description,
        appearance_desc=asset.visual_description,
        asset_id=asset_id  # C2 引用
    )
    
    # 2. 复制资产的参考图作为初始版本
    if asset.reference_images:
        for idx, img_url in enumerate(asset.reference_images):
            await ProjectEntityAsset.create(
                project_id=project_id,
                entity_type=asset.type,
                entity_id=entity.id,
                version=idx + 1,
                is_active=(idx == 0),
                is_manual=True,
                file_url=img_url,
                created_by="import"
            )
    
    return entity
```

#### 6.5.2 项目实体 → 资产库（沉淀）

```python
async def promote_entity_to_asset(entity_type, entity_id, user_id):
    """把项目实体沉淀为公共资产库的新资产"""
    entity = await get_entity(entity_type, entity_id)
    active_image = await get_active_image(entity_type, entity_id)
    
    # 1. 创建资产记录（走审核）
    asset = await Asset.create(
        type=entity_type,
        name=entity.name,
        description=entity.description,
        visual_description=entity.appearance_desc or entity.visual_desc,
        reference_images=[active_image.file_url] if active_image else [],
        user_id=user_id,
        is_public=False,
        moderation_status="pending"  # 走审核
    )
    
    # 2. 回填 entity.asset_id
    await update_entity_asset_id(entity_type, entity_id, asset.id)
    
    return asset
```

### 6.6 实时状态推送（SSE）

```
GET /api/projects/{id}/events

event: entity_image_generated
data: {"entity_type": "character", "entity_id": 5, "version": 2, "url": "..."}

event: active_version_changed
data: {"entity_type": "scene", "entity_id": 3, "version_id": 8}

event: frame_image_generated
data: {"shot_id": 12, "version": 3, "url": "..."}

event: shot_video_generated
data: {"shot_id": 12, "version": 2, "url": "...", "duration_ms": 3000}

event: shot_edited
data: {"shot_id": 12, "affected_fields": ["image_prompt"], "message": "..."}

event: shots_reordered
data: {"shot_ids": [12, 13, 14, 15]}

event: generation_failed
data: {"entity_type": "character", "entity_id": 5, "error": "..."}
```

前端在收到事件后**局部更新对应卡片**，不需要刷新整个页面。

### 6.7 卡片 UI 范式

参考 LingGuo-Drama `detail.vue`，每张实体卡片统一挂载：

- **预览图**：当前采用版素材
- **生成中遮罩**：`generatingIds.includes(id)` 时显示 loading
- **AI 生成按钮**：单个重生
- **编辑按钮**：改描述/prompt
- **上传按钮**：手动上传替代
- **删除按钮**：移除实体
- **多选 checkbox**：批量操作
- **版本切换器**：展开所有版本，点击切换采用版
- **资产库关联标识**：显示 `asset_id` 引用状态

分镜卡片额外有：景别/运镜/视角标签、绑定角色/场景/道具的 chips、帧图+视频+音频三个素材槽、拖拽手柄。

### 6.8 关键设计决策

1. **所有操作独立 API**：每个生成/编辑/上传/切换都是单独接口，互不阻塞
2. **多版本默认不自动设采用**：新生成的版本默认 `is_active=False`，用户手动选择。避免覆盖之前的采用版
3. **生成中遮罩 + SSE 局部更新**：每个卡片独立 loading，不阻塞其他操作
4. **编辑分镜推送 affected_fields 提示**：用户改了 prompt 后主动提示"下游素材可能需要重生"
5. **资产库引用不复制素材**：导入资产时记录 `asset_id`，但参考图作为版本复制到项目内
6. **沉淀走审核**：项目实体沉淀为公共资产时走 `moderation_status=pending`

---

## 7. 时间线 + TTS/字幕（Phase 2）

### 7.1 时间线编辑器整体架构

```
┌──────────────────────────────────────────────────────────┐
│ 时间线编辑器（ProjectTimelineEditor.vue）                  │
│                                                          │
│ ┌─ 工具栏 ─────────────────────────────────────────────┐ │
│ │ [播放] [暂停] [停止]  时间: 00:12.5 / 01:30.0        │ │
│ │ [添加片段] [添加转场] [添加字幕] [添加BGM] [导出]    │ │
│ └─────────────────────────────────────────────────────┘ │
│                                                          │
│ ┌─ 轨道区 ────────────────────────────────────────────┐ │
│ │ │ 视频轨 0 (主) │ [分镜1]─xfade─[分镜2]─[分镜3]   │ │
│ │ │ 视频轨 1 (PIP)│     [画中画片段]                  │ │
│ │ │ 音频轨 0 (主) │ [TTS1]──[TTS2]──[TTS3]           │ │
│ │ │ 音频轨 1 (BGM)│ [════════背景音乐════════]       │ │
│ │ │ 字幕轨 0      │ "你好"  "我是..."  "今天..."    │ │
│ │ └──────────────────────────────────────────────────  │ │
│ │           ▲ 播放头（红色竖线）                        │ │
│ │ 0s    5s    10s    15s    20s    25s    30s          │ │
│ └─────────────────────────────────────────────────────┘ │
│                                                          │
│ ┌─ 属性面板（选中片段时显示）─────────────────────────┐ │
│ │ 起始: 5.0s  时长: 3.2s  裁剪: 0.5s~3.7s              │ │
│ │ 来源: 分镜2 视频 v3                                  │ │
│ │ 转场: fade (0.5s)                                    │ │
│ └─────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────┘
```

### 7.2 轨道类型

| 轨道类型 | 数量 | 内容 | 来源 |
|---------|------|------|------|
| `video` 视频轨 | 多轨（H1） | 分镜视频片段、画中画 | project_shot_videos |
| `audio` 音频轨 | 多轨 | TTS 配音、BGM | project_shot_audios + 内置 BGM 库 |
| `subtitle` 字幕轨 | 多轨 | 字幕片段 | 手动或从对白生成 |

### 7.3 时间线片段生命周期

#### 7.3.1 自动初始化

项目首次进入时间线编辑器时，自动从分镜数据初始化时间线：
- 视频轨 0：每个分镜的采用视频
- 音频轨 0：每个分镜的采用 TTS
- 字幕轨 0：从分镜对白生成

#### 7.3.2 拖拽编辑

- **拖动片段整体**：改变 `start_time`
- **拖动左右边缘**：调整 `trim_start` / `trim_end`（裁剪源视频）
- **跨轨道拖动**：改变 `track_index`
- **拖动排序**：改变 `sort_order`，自动重算 `start_time`

所有拖拽操作前端实时更新本地状态，松手时调 `PATCH /api/projects/{id}/timeline/clips/{clip_id}` 持久化。

#### 7.3.3 转场配置

支持的转场类型（ffmpeg xfade 滤镜子集）：
- `fade` 淡入淡出
- `slide` 滑动
- `wipe` 擦除
- `dissolve` 溶解
- `none` 无转场

### 7.4 TTS 配音生成（I1）

#### 7.4.1 音色分配策略

参考 LingGuo-Drama 的"同角色同声音，性别匹配"：

```python
async def generate_shot_audio(shot_id, user_id, voice_id=None):
    shot = await ProjectShot.get(id=shot_id)
    
    if not shot.dialogue:
        raise BusinessError("分镜无对白，无法生成配音")
    
    # 自动分配音色（同角色同声音）
    if not voice_id:
        characters = await get_shot_characters(shot.id)
        if characters:
            main_char = next((c for c in characters if c.role_type == "main"), characters[0])
            voice_id = await get_or_assign_voice(main_char)
        else:
            voice_id = "default_narrator"
    
    # 调用 TTS API
    audio_result = await agnes_client.generate_tts(
        text=shot.dialogue,
        voice_id=voice_id,
        model="agnes-tts-1.0"
    )
    
    # 创建新版本
    # ...
```

#### 7.4.2 内置音色库

| voice_id | 名称 | 性别 | 适用角色 |
|----------|------|------|---------|
| `narrator_male_zh` | 男声旁白 | 男 | 旁白、男主 |
| `narrator_female_zh` | 女声旁白 | 女 | 旁白、女主 |
| `young_male_zh` | 年轻男声 | 男 | 年轻男主 |
| `young_female_zh` | 年轻女声 | 女 | 年轻女主 |
| `mature_male_zh` | 成熟男声 | 男 | 成熟男性 |
| `mature_female_zh` | 成熟女声 | 女 | 成熟女性 |
| `child_zh` | 童声 | 中 | 儿童 |
| `elder_zh` | 老年声 | 中 | 老年 |

### 7.5 字幕生成与编辑（I1）

#### 7.5.1 自动生成字幕

字幕从分镜对白字段自动生成，作为 `subtitle` 轨道的片段。

#### 7.5.2 字幕编辑

用户可在时间线上直接双击字幕片段编辑文本，或调整时长。

#### 7.5.3 字幕样式

字幕样式存在 `projects.timeline_data` JSON 字段：

```json
{
  "subtitle_style": {
    "font_family": "Microsoft YaHei",
    "font_size": 48,
    "font_color": "#FFFFFF",
    "outline_color": "#000000",
    "outline_width": 2,
    "position": "bottom",
    "margin_vertical": 60
  }
}
```

合成时 ffmpeg subtitles 滤镜应用此样式生成 ASS 字幕文件烧录到视频。

### 7.6 视频合成（merge_video）

```python
async def merge_video(project_id, user_id):
    """根据时间线合成最终视频"""
    # 1. 校验时间线非空
    # 2. 校验所有片段有有效源
    # 3. 入队异步合成任务
    # 4. 更新项目状态为 merging


async def execute_merge(project_id, user_id):
    """实际执行 ffmpeg 合成"""
    # 1. 下载所有视频片段到临时目录
    # 2. 按轨道顺序拼接视频（含转场）
    video_track_path = await composite_video_track(video_clips, project.aspect_ratio)
    # 3. 混合音频轨（TTS + BGM）
    audio_track_path = await composite_audio_track(audio_clips, video_duration)
    # 4. 生成 ASS 字幕文件
    subtitle_path = await generate_ass_subtitle(subtitle_clips, project.timeline_data["subtitle_style"])
    # 5. ffmpeg 最终合成：视频 + 音频 + 字幕烧录
    final_path = await ffmpeg_final_composite(
        video_path=video_track_path,
        audio_path=audio_track_path,
        subtitle_path=subtitle_path,
        output_format="mp4"
    )
    # 6. 上传到资产存储 + 更新项目
    # 7. 推送 SSE
```

ffmpeg 合成策略复用现有 [ffmpeg_composite.py](file:///Users/skywing/agnes-platform/backend/app/services/pipeline/steps/ffmpeg_composite.py) 和 [transition_compose.py](file:///Users/skywing/agnes-platform/backend/app/services/pipeline/steps/transition_compose.py) 改造。

### 7.7 内置 BGM 库

新增内置 BGM 库（存放 `backend/assets/bgm/` 目录）：

| bgm_id | 名称 | 风格 | 时长 |
|--------|------|------|------|
| `bgm_warm_piano` | 温暖钢琴 | 治愈、温馨 | 60s |
| `bgm_corporate` | 商务科技 | 广告、企业 | 45s |
| `bgm_dramatic` | 戏剧紧张 | 剧情、悬疑 | 90s |
| `bgm_uplifting` | 激昂向上 | 励志、广告 | 50s |

### 7.8 关键设计决策

1. **时间线是独立编辑层，不直接修改分镜数据**：分镜的采用视频是"源"，时间线片段是"引用+裁剪+转场配置"
2. **自动初始化时间线**：首次进入时间线编辑器时从分镜数据自动生成初始片段
3. **多轨支持**（H1）：视频支持主轨+PIP轨，音频支持 TTS轨+BGM轨，字幕支持多语种轨
4. **音色按角色固定**：通过 `project_character_voices` 表保证同角色同声音
5. **字幕从对白自动生成 + 可编辑**
6. **合成走异步队列**：ffmpeg 合成耗时长，入队异步执行，SSE 推送完成事件

---

## 8. 画布双视图（J4）

### 8.1 双视图整体架构

```
┌─────────────────────────────────────────────────────────────┐
│ 项目详情页（ProjectDetailView.vue）                          │
│ ┌─ 顶部工具栏 ──────────────────────────────────────────┐   │
│ │ [← 返回] 项目标题  状态:进行中  [管理视图|画布视图]    │   │
│ │                              [时间线] [导出] [发布]    │   │
│ └─────────────────────────────────────────────────────┘   │
│                                                             │
│ ┌─ 视图切换区 ─────────────────────────────────────────┐   │
│ │  ▼ 管理视图（ManagerView）                            │   │
│ │    Tab：剧本 | 角色 | 场景 | 道具 | 分镜              │   │
│ │    卡片网格 + 多选批量 + 单个操作                      │   │
│ │                                                       │   │
│ │  ▼ 画布视图（CanvasView）                             │   │
│ │    节点式编辑：分镜/角色/场景/道具作为节点             │   │
│ │    连线表示生成依赖                                   │   │
│ │    节点可拖拽/可右键操作（重生/编辑/上传）             │   │
│ └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

`projects.active_view` 字段记录用户上次使用的视图，下次进入时恢复。

### 8.2 管理视图（ManagerView）

参考 LingGuo-Drama `detail.vue` 的 Tab + 卡片网格结构。每个 Tab 内的能力与第 6 节"逐个适配"完全一致，只是 UI 范式为卡片网格。

### 8.3 画布视图（CanvasView）

复用现有 [InfiniteCanvas.vue](file:///Users/skywing/agnes-platform/frontend/src/components/canvas/InfiniteCanvas.vue) 能力，新增"项目画布"模式。

#### 8.3.1 节点类型

| 节点类型 | 数据来源 | 节点内容 |
|---------|---------|---------|
| `script` | project_scripts | 剧本文本预览 |
| `character` | project_characters | 角色采用图 + 名称 |
| `scene` | project_scenes | 场景采用图 + 名称 |
| `prop` | project_props | 道具采用图 + 名称 |
| `shot` | project_shots | 分镜采用帧图 + 序号 + 台词 |
| `video` | project_shot_videos | 视频缩略图 + 时长 |
| `final` | projects.final_video_url | 最终成片 |

#### 8.3.2 自动布局

项目首次切换到画布视图时，自动按生成依赖布局节点：

```
       ┌──────────┐
       │  剧本    │
       └────┬─────┘
            │
   ┌────────┼────────┐
   ▼        ▼        ▼
┌─────┐ ┌─────┐ ┌─────┐
│角色1│ │场景1│ │道具1│
└──┬──┘ └──┬──┘ └─────┘
   │       │
   └───┬───┘
       ▼
   ┌────────┐
   │ 分镜1  │
   └───┬────┘
       ▼
   ┌────────┐
   │ 视频1  │
   └───┬────┘
       ▼
   ┌────────┐
   │ 最终片 │
   └────────┘
```

#### 8.3.3 节点交互

画布节点支持所有逐个适配操作（与第 6 节管理视图一致）：

- **单击节点**：选中，右侧显示属性面板
- **双击节点**：打开详情对话框
- **右键节点**：弹出上下文菜单（复用现有 [CanvasContextMenu.vue](file:///Users/skywing/agnes-platform/frontend/src/components/canvas/CanvasContextMenu.vue)）
- **拖拽节点**：改变位置（保存到 canvas_data）
- **节点连线**：自动按依赖生成，用户不可手动连线

### 8.4 视图同步

管理视图和画布视图共享同一份项目数据，**任一视图的操作都立即反映到另一视图**。切换视图时不需要重新加载数据，仅切换渲染组件。

### 8.5 画布视图的独特价值

1. **依赖关系可视化**：剧本→角色→分镜→视频的生成链路一目了然
2. **大屏创作**：无限画布适合大屏操作
3. **节点式重生**：右键某分镜节点 → "重新生成帧图"，只影响该节点及下游
4. **画布原生能力复用**：现有 CanvasToolbar/CanvasMinimap/CanvasZoomControls 直接复用
5. **与独立画布打通**：项目画布可"导出为独立画布"

### 8.6 与现有 CanvasView 的关系

- **独立画布**（现有 [CanvasView.vue](file:///Users/skywing/agnes-platform/frontend/src/views/CanvasView.vue)）：保留，用户可自由创建节点做单图/单视频生成
- **项目画布**（新增 `ProjectCanvasView.vue`）：是项目详情页的一个视图，节点数据来自项目实体，自动布局

两者共用 InfiniteCanvas 等底层组件，但数据源不同。

### 8.7 关键设计决策

1. **共享数据，独立渲染**：两个视图操作同一份 store
2. **画布节点不可手动连线**：依赖关系由项目结构决定
3. **自动布局 + 可手动调整**：首次进入画布视图自动布局，用户拖拽后位置持久化
4. **画布视图复用现有组件**：减少开发量
5. **导出为独立画布**：项目画布可作为独立画布的"模板"

---

## 9. API 设计

### 9.1 项目 CRUD

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/projects` | 创建空项目 |
| POST | `/api/projects/wizard` | 创建项目（模板向导式） |
| POST | `/api/projects/{id}/wizard/resume` | 恢复中断的向导 |
| GET | `/api/projects` | 项目列表（分页、筛选） |
| GET | `/api/projects/{id}` | 项目详情 |
| PATCH | `/api/projects/{id}` | 更新项目 |
| DELETE | `/api/projects/{id}` | 删除项目 |
| POST | `/api/projects/{id}/archive` | 归档项目 |
| GET | `/api/projects/{id}/events` | SSE 实时事件流 |
| PATCH | `/api/projects/{id}/active-view` | 切换活动视图 |

### 9.2 剧本

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/projects/{id}/scripts` | 剧本列表 |
| POST | `/api/projects/{id}/scripts` | 新增分集 |
| GET | `/api/projects/{id}/scripts/{sid}` | 剧本详情 |
| PATCH | `/api/projects/{id}/scripts/{sid}` | 编辑剧本 |
| POST | `/api/projects/{id}/scripts/{sid}/regenerate` | 重生成剧本 |
| DELETE | `/api/projects/{id}/scripts/{sid}` | 删除分集 |

### 9.3 角色/场景/道具（统一模式）

以角色为例（场景/道具路径替换 `characters` 为 `scenes`/`props`）：

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/projects/{id}/characters` | 角色列表 |
| POST | `/api/projects/{id}/characters` | 添加角色 |
| POST | `/api/projects/{id}/characters/extract` | 从剧本提取 |
| POST | `/api/projects/{id}/characters/import-asset` | 从资产库导入 |
| GET | `/api/projects/{id}/characters/{cid}` | 角色详情 |
| PATCH | `/api/projects/{id}/characters/{cid}` | 编辑角色 |
| DELETE | `/api/projects/{id}/characters/{cid}` | 删除角色 |
| POST | `/api/projects/{id}/characters/{cid}/generate-image` | 单个 AI 生图 |
| POST | `/api/projects/{id}/characters/batch-generate` | 批量生图 |
| POST | `/api/projects/{id}/characters/{cid}/upload-image` | 上传替换 |
| POST | `/api/projects/{id}/characters/{cid}/versions/{vid}/activate` | 设为采用版 |
| GET | `/api/projects/{id}/characters/{cid}/versions` | 版本列表 |
| DELETE | `/api/projects/{id}/characters/{cid}/versions/{vid}` | 删除某版本 |
| POST | `/api/projects/{id}/characters/{cid}/promote-asset` | 沉淀到资产库 |
| PATCH | `/api/projects/{id}/characters/reorder` | 重排顺序 |

### 9.4 分镜

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/projects/{id}/shots` | 分镜列表 |
| POST | `/api/projects/{id}/shots` | 添加分镜 |
| POST | `/api/projects/{id}/shots/split` | AI 拆分分镜（E2） |
| GET | `/api/projects/{id}/shots/{sid}` | 分镜详情 |
| PATCH | `/api/projects/{id}/shots/{sid}` | 编辑分镜 |
| DELETE | `/api/projects/{id}/shots/{sid}` | 删除分镜 |
| PATCH | `/api/projects/{id}/shots/reorder` | 重排顺序 |
| POST | `/api/projects/{id}/shots/{sid}/bind-character` | 绑定角色 |
| POST | `/api/projects/{id}/shots/{sid}/bind-prop` | 绑定道具 |
| POST | `/api/projects/{id}/shots/{sid}/generate-frame-prompt` | AI 提取帧级 prompt |

### 9.5 分镜素材（帧图/视频/音频）

以帧图为例：

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/projects/{id}/shots/{sid}/frame-images` | 帧图版本列表 |
| POST | `/api/projects/{id}/shots/{sid}/frame-images/generate` | 生成新版本 |
| POST | `/api/projects/{id}/shots/frame-images/batch-generate` | 批量生成 |
| POST | `/api/projects/{id}/shots/{sid}/frame-images/upload` | 上传替换 |
| POST | `/api/projects/{id}/shots/{sid}/frame-images/{vid}/activate` | 设为采用版 |
| DELETE | `/api/projects/{id}/shots/{sid}/frame-images/{vid}` | 删除某版本 |

### 9.6 时间线（Phase 2）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/projects/{id}/timeline` | 时间线数据 |
| POST | `/api/projects/{id}/timeline/init` | 从分镜初始化 |
| POST | `/api/projects/{id}/timeline/clips` | 添加片段 |
| PATCH | `/api/projects/{id}/timeline/clips/{cid}` | 更新片段 |
| DELETE | `/api/projects/{id}/timeline/clips/{cid}` | 删除片段 |
| PATCH | `/api/projects/{id}/timeline/subtitle-style` | 更新字幕样式 |
| POST | `/api/projects/{id}/timeline/generate-subtitles` | 从对白生成字幕 |
| POST | `/api/projects/{id}/timeline/merge` | 触发合成 |
| GET | `/api/projects/{id}/timeline/merge-status` | 合成状态 |

### 9.7 画布视图

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/projects/{id}/canvas` | 获取画布布局 |
| POST | `/api/projects/{id}/canvas/init` | 自动生成画布布局 |
| PATCH | `/api/projects/{id}/canvas` | 保存画布布局 |
| POST | `/api/projects/{id}/canvas/export-standalone` | 导出为独立画布 |

### 9.8 统一响应格式

遵循 [AGENTS.md](file:///Users/skywing/agnes-platform/AGENTS.md) 规范：

```json
{
  "status": "success",
  "message": "...",
  "data": {...}
}
```

异步任务返回任务 ID：
```json
{
  "status": "queued",
  "data": {"task_id": 123, "estimated_duration": 30}
}
```

---

## 10. 前端架构

### 10.1 路由结构

```
/workshop                  → 模板市场（改造现有 WorkshopView）
/projects                  → 项目列表（新增）
/projects/:id              → 项目详情（新增，含双视图）
/projects/:id/timeline     → 时间线编辑器（Phase 2）
/history                   → 历史记录（保留）
/canvas                    → 独立画布（保留）
/plaza                     → 广场（保留）
```

废弃路由：`/pipeline/runs/:id`、`/pipeline/history`、`/pipeline/results/:id`。

### 10.2 新增 Store

```typescript
// frontend/src/stores/project.ts
export const useProjectStore = defineStore('project', () => {
  const project = ref<Project | null>(null)
  const activeView = ref<'manager' | 'canvas'>('manager')
  
  const scripts = ref<Script[]>([])
  const characters = ref<Character[]>([])
  const scenes = ref<Scene[]>([])
  const props = ref<Prop[]>([])
  const shots = ref<Shot[]>([])
  
  const loading = ref({...})
  const generatingIds = ref<{...}>({...})
  const sseConnection = ref<EventSource | null>(null)
  
  // 所有逐个适配动作
  async function loadProject(id: number) {...}
  async function generateCharacterImage(id: number) {...}
  async function batchGenerateCharacters(ids: number[]) {...}
  async function setActiveVersion(...) {...}
  
  return { project, activeView, characters, scenes, props, shots, ... }
})
```

### 10.3 组件结构

```
frontend/src/
├── views/
│   ├── projects/
│   │   ├── ProjectListView.vue
│   │   ├── ProjectDetailView.vue
│   │   └── ProjectTimelineView.vue      # Phase 2
│   └── workshop/
│       └── WorkshopView.vue             # 改造
│
├── components/project/
│   ├── ProjectHeader.vue
│   ├── ProjectManagerView.vue
│   ├── ProjectCanvasView.vue
│   ├── ScriptTab.vue
│   ├── CharactersTab.vue
│   ├── ScenesTab.vue
│   ├── PropsTab.vue
│   ├── ShotsTab.vue
│   ├── CharacterCard.vue
│   ├── SceneCard.vue
│   ├── PropCard.vue
│   ├── ShotCard.vue
│   ├── EntityVersionSwitcher.vue
│   ├── EntityEditDialog.vue
│   ├── ExtractEntitiesDialog.vue
│   ├── ImportAssetDialog.vue
│   ├── PromoteAssetDialog.vue
│   ├── FrameImageGallery.vue
│   ├── VideoGallery.vue
│   ├── TimelineEditor.vue               # Phase 2
│   ├── TimelineClip.vue                 # Phase 2
│   ├── TimelineTrack.vue                # Phase 2
│   └── ProjectLaunchDialog.vue          # 改造自 PipelineLaunchDialog
│
├── stores/
│   └── project.ts
│
├── api/
│   └── projects.ts
│
├── composables/
│   ├── useProjectSSE.ts
│   └── useEntityActions.ts
│
└── types/
    └── project.ts
```

### 10.4 与现有组件的关系

| 现有组件 | 处理方式 |
|---------|---------|
| [StepList.vue](file:///Users/skywing/agnes-platform/frontend/src/components/pipeline/StepList.vue) | 废弃 |
| [StepPanel.vue](file:///Users/skywing/agnes-platform/frontend/src/components/pipeline/StepPanel.vue) | 废弃 |
| [ItemCard.vue](file:///Users/skywing/agnes-platform/frontend/src/components/pipeline/ItemCard.vue) | 改造为 ShotCard.vue 基础 |
| [PipelineProgress.vue](file:///Users/skywing/agnes-platform/frontend/src/components/pipeline/PipelineProgress.vue) | 改造为 ProjectWizardProgress.vue |
| [PipelineLaunchDialog.vue](file:///Users/skywing/agnes-platform/frontend/src/components/pipeline/PipelineLaunchDialog.vue) | 改造为 ProjectLaunchDialog.vue |
| [PipelineHistoryView.vue](file:///Users/skywing/agnes-platform/frontend/src/views/PipelineHistoryView.vue) | 废弃，替换为 ProjectListView.vue |
| [PipelineRunView.vue](file:///Users/skywing/agnes-platform/frontend/src/views/PipelineRunView.vue) | 废弃，替换为 ProjectDetailView.vue |
| [PipelineResultView.vue](file:///Users/skywing/agnes-platform/frontend/src/views/PipelineResultView.vue) | 废弃 |
| [InfiniteCanvas.vue](file:///Users/skywing/agnes-platform/frontend/src/components/canvas/InfiniteCanvas.vue) | 保留，被 ProjectCanvasView 复用 |
| [CanvasNode.vue](file:///Users/skywing/agnes-platform/frontend/src/components/canvas/CanvasNode.vue) | 保留，新增 project 节点类型 |
| [CanvasContextMenu.vue](file:///Users/skywing/agnes-platform/frontend/src/components/canvas/CanvasContextMenu.vue) | 保留，新增项目操作菜单项 |
| [AssetDetailModal.vue](file:///Users/skywing/agnes-platform/frontend/src/components/pipeline/AssetDetailModal.vue) | 保留用于资产库 |
| [StyleSelector.vue](file:///Users/skywing/agnes-platform/frontend/src/components/pipeline/StyleSelector.vue) | 保留，向导里用 |
| [usePipelineSSE.ts](file:///Users/skywing/agnes-platform/frontend/src/composables/usePipelineSSE.ts) | 改造为 useProjectSSE.ts |

### 10.5 任务队列集成

复用现有 [taskQueue.ts](file:///Users/skywing/agnes-platform/frontend/src/stores/taskQueue.ts)，新增任务类型：

```typescript
type TaskType = 
  | 'project_wizard'        // 向导 LLM 链
  | 'project_entity_image'  // 角色/场景/道具生图
  | 'project_frame_image'   // 分镜帧图生成
  | 'project_video'         // 分镜视频生成
  | 'project_tts'           // TTS 生成（Phase 2）
  | 'project_merge'         // 时间线合成（Phase 2）
```

---

## 11. 后端模块映射

```
backend/app/
├── models/
│   ├── project.py                # 新增
│   ├── pipeline.py               # 改造：保留 Template，删除 Run/Step/Revision
│   └── ...
│
├── schemas/
│   ├── project.py                # 新增
│   └── ...
│
├── routes/
│   ├── projects.py               # 新增
│   ├── pipeline.py               # 改造：保留模板路由
│   └── ...
│
├── services/
│   ├── project/                  # 新增
│   │   ├── __init__.py
│   │   ├── wizard.py
│   │   ├── project_service.py
│   │   ├── script_service.py
│   │   ├── character_service.py
│   │   ├── scene_service.py
│   │   ├── prop_service.py
│   │   ├── shot_service.py
│   │   ├── frame_image_service.py
│   │   ├── video_service.py
│   │   ├── audio_service.py      # Phase 2
│   │   ├── timeline_service.py   # Phase 2
│   │   ├── canvas_bridge.py
│   │   ├── asset_bridge.py
│   │   └── sse_manager.py
│   ├── pipeline/                 # 改造
│   │   ├── template_service.py   # 保留
│   │   ├── template_scenarios.py # 改造为 wizard_chain 定义
│   │   └── ...
│   └── ...
│
└── ...
```

---

## 12. 迁移策略（K1：直接废弃不迁移）

### 12.1 数据库迁移

按 [AGENTS.md](file:///Users/skywing/agnes-platform/AGENTS.md) 规则"项目尚未上线，不需要兼容旧数据"，直接删除旧表、新建新表：

```bash
# 1. 删除旧表
alembic revision --autogenerate -m "drop pipeline_runs_steps_revisions"

# 2. 新建项目相关表
alembic revision --autogenerate -m "add project tables"
```

删除的表：
- `pipeline_runs`
- `pipeline_steps`
- `pipeline_step_output_revisions`

新增的表：见第 4 节。

### 12.2 代码清理

#### 删除的后端代码

- `backend/app/services/pipeline/engine.py`
- `backend/app/services/pipeline/run_service.py`
- `backend/app/services/pipeline/integration.py`
- `backend/app/services/pipeline/post_process_service.py`
- `backend/app/services/pipeline/moderation_service.py`
- `backend/app/services/pipeline/steps/`（整个目录，ffmpeg_composite 和 transition_compose 移到 project 服务下）
- `backend/app/services/pipeline/template_validate.py`
- `backend/app/routes/pipeline.py` 中的 runs/steps 相关路由
- `backend/app/schemas/pipeline.py` 中的 Run/Step schema
- `backend/app/models/pipeline.py` 中的 PipelineRun/PipelineStep/PipelineStepOutputRevision

#### 保留并改造的后端代码

- `backend/app/services/pipeline/template_service.py`（语义改为向导模板）
- `backend/app/services/pipeline/template_scenarios.py`（改为 wizard_chain 定义）
- `backend/app/services/pipeline/sse_manager.py`（移到 `services/project/`）
- `backend/app/services/pipeline/steps/ffmpeg_composite.py`（移到 `services/project/`，被 timeline_service 复用）
- `backend/app/services/pipeline/steps/transition_compose.py`（同上）

#### 删除的前端代码

- `frontend/src/views/PipelineHistoryView.vue`
- `frontend/src/views/PipelineRunView.vue`
- `frontend/src/views/PipelineResultView.vue`
- `frontend/src/components/pipeline/StepList.vue`
- `frontend/src/components/pipeline/StepPanel.vue`
- `frontend/src/components/pipeline/PipelineProgress.vue`（改造为新组件）
- `frontend/src/stores/pipeline.ts`
- `frontend/src/composables/usePipelineSSE.ts`
- `frontend/src/api/pipeline.ts` 中的 runs/steps 相关

#### 保留并改造的前端代码

- `frontend/src/views/WorkshopView.vue`（改造为模板市场入口）
- `frontend/src/components/pipeline/PipelineLaunchDialog.vue` → `ProjectLaunchDialog.vue`
- `frontend/src/components/pipeline/ItemCard.vue`（改造为 ShotCard.vue 基础）
- `frontend/src/components/pipeline/StyleSelector.vue`（保留）
- `frontend/src/components/pipeline/AssetDetailModal.vue`（保留用于资产库）

### 12.3 菜单调整

参考 [menus.ts](file:///Users/skywing/agnes-platform/frontend/src/config/menus.ts)，菜单结构调整为：

```
- 创作工坊
  - 模板市场 (/workshop)
  - 我的项目 (/projects)        ← 新增
  - 资产库 (/assets)
- 创作工具
  - 无限画布 (/canvas)
  - 图片生成 (/images)
  - 视频生成 (/videos)
- 社区
  - 广场 (/plaza)
- 管理（管理员可见）
  - 内容审核 (/admin/review)
```

废弃"创意流水线"菜单项。

---

## 13. 分阶段实施计划（M1）

### 13.1 Phase 1：基础项目制 + 引导式生成 + 逐个适配

**目标**：完成项目制重构的核心，跑通"创建项目 → 引导生成 → 逐个适配 → 简单合成"的完整链路。

**工作内容**：

1. **数据库 & 模型层**
   - 创建 11 张新表（projects + 7 张实体表 + project_entity_assets + 2 张多对多关联表）
   - 删除 3 张旧表（pipeline_runs / pipeline_steps / pipeline_step_output_revisions）
   - 编写 Pydantic Schema
   - Alembic 迁移脚本

2. **后端服务层**
   - `services/project/` 模块骨架
   - `wizard.py`：项目创建向导（4 步 LLM 链）
   - `project_service.py`：项目 CRUD
   - `script_service.py`：剧本 CRUD
   - `character_service.py` / `scene_service.py` / `prop_service.py`：实体 CRUD + 生成 + 上传 + 版本管理
   - `shot_service.py`：分镜 CRUD + 绑定 + 重排
   - `frame_image_service.py`：帧图多版本 + 生成 + 上传
   - `video_service.py`：视频多版本 + 生成 + 上传
   - `asset_bridge.py`：项目实体 ↔ 资产库互转
   - `sse_manager.py`：项目级 SSE
   - `canvas_bridge.py`：画布布局生成（基础版）
   - 删除 `services/pipeline/` 中废弃代码
   - 改造 `template_service.py` 和 `template_scenarios.py`

3. **后端路由**
   - `routes/projects.py`：所有项目 API
   - 改造 `routes/pipeline.py`：保留模板路由

4. **前端**
   - `views/projects/ProjectListView.vue`
   - `views/projects/ProjectDetailView.vue`（含管理视图）
   - `views/projects/ProjectCanvasView.vue`（基础画布视图）
   - `components/project/` 目录所有组件
   - `stores/project.ts`
   - `api/projects.ts`
   - `composables/useProjectSSE.ts`
   - 改造 `WorkshopView.vue` 和 `PipelineLaunchDialog.vue`
   - 删除废弃的 Pipeline 组件和视图
   - 路由和菜单调整

5. **集成测试**
   - 完整流程：选模板 → 创建项目 → 引导生成 → 逐个适配 → 简单合成
   - 多版本管理：生成 → 切换 → 上传 → 设采用
   - 资产互转：导入资产 → 项目使用 → 沉淀回资产
   - 画布视图：自动布局 + 节点操作

**交付物**：
- 用户可通过模板创建项目，AI 一次性产出剧本+实体+分镜
- 用户可在管理视图逐个生成/编辑/上传/切换版本
- 用户可在画布视图查看项目结构并操作节点
- 简单的自动合成（无时间线编辑，按分镜顺序拼接 + 默认转场）

### 13.2 Phase 2：时间线 + TTS + 字幕

**目标**：完整时间线编辑器 + 配音 + 字幕烧录。

**工作内容**：

1. **数据库**：新增 `project_shot_audios` / `project_character_voices` / `project_timeline_clips` 表
2. **后端**：
   - `audio_service.py`：TTS 生成 + 音色分配
   - `timeline_service.py`：时间线 CRUD + 合成调度
   - 改造 `ffmpeg_composite.py` 支持时间线配置
   - 内置 BGM 库 + 音色库
3. **前端**：
   - `TimelineEditor.vue` + `TimelineClip.vue` + `TimelineTrack.vue`
   - 时间线属性面板
   - 字幕编辑器
   - `ProjectTimelineView.vue`（独立全屏页）
4. **集成**：时间线合成 → 最终成片 → 发布到广场

### 13.3 Phase 3：画布视图增强 + 生态完善

**目标**：画布视图深度编辑能力 + 资产生态。

**工作内容**：

1. **画布增强**：节点拖拽生成、画布内重生、画布导出为独立画布
2. **资产生态**：项目实体发布到广场、从广场收藏到项目
3. **协作**（可选）：项目分享、多人查看
4. **性能优化**：大项目（100+ 分镜）的画布渲染、SSE 性能

---

## 14. 风险与缓解

### 14.1 LLM 输出不稳定

**风险**：向导链中 LLM 输出的 JSON 可能格式错误、字段缺失。

**缓解**：
- `parse_json_loose()` 多层容错解析
- 字段补全默认值
- 单步重试 2 次
- 部分成功保留，向导失败可重入

### 14.2 大项目性能

**风险**：100+ 分镜的项目在画布视图渲染、SSE 推送时可能卡顿。

**缓解**：
- Phase 3 专门做性能优化
- 画布节点虚拟化渲染
- SSE 事件批量推送

### 14.3 ffmpeg 合成耗时

**风险**：长时间视频合成可能超时。

**缓解**：
- 异步队列执行，不阻塞 API
- SSE 推送合成进度
- 合成失败可重试

### 14.4 迁移期间功能断档

**风险**：K1 直接废弃旧表，迁移期间用户无法访问历史记录。

**缓解**：
- 项目未上线，无生产数据
- 一次性完成迁移，避免长期断档
- 迁移前全量备份

---

## 15. 验收标准

### 15.1 Phase 1 验收

- [ ] 用户可通过模板市场选模板创建项目
- [ ] 向导链 4 步执行：剧本 → 实体提取 → 分镜拆分 → 帧 prompt 提取
- [ ] SSE 实时推送向导进度
- [ ] 项目详情页管理视图：剧本/角色/场景/道具/分镜 5 个 Tab
- [ ] 每个实体支持：编辑/单个生成/批量生成/上传替换/删除/添加/重排/版本切换
- [ ] 角色/场景/道具支持沉淀到资产库
- [ ] 分镜可绑定角色/场景/道具
- [ ] 分镜帧图生成注入角色参考图
- [ ] 分镜视频生成基于采用帧图
- [ ] 简单合成（按分镜顺序拼接 + 默认转场）
- [ ] 画布视图自动布局 + 节点右键操作
- [ ] 双视图切换不丢失状态

### 15.2 Phase 2 验收

- [ ] TTS 配音生成 + 音色按角色固定
- [ ] 时间线编辑器：多轨视频/音频/字幕
- [ ] 拖拽片段、裁剪、转场配置
- [ ] 字幕从对白自动生成 + 可编辑
- [ ] ffmpeg 合成：视频 + 音频 + 字幕烧录
- [ ] 内置 BGM 库

### 15.3 Phase 3 验收

- [ ] 画布节点拖拽生成
- [ ] 画布导出为独立画布
- [ ] 项目实体发布到广场
- [ ] 大项目性能优化（100+ 分镜流畅）

---

## 附录 A：LingGuo-Drama 参考实现

- 仓库：https://github.com/LingGuoAI/LingGuo-Drama
- 项目详情页：[projects/detail.vue](https://github.com/LingGuoAI/LingGuo-Drama/blob/main/web/src/pages/projects/detail.vue)
- 分镜编辑：[scriptEditor.vue](https://github.com/LingGuoAI/LingGuo-Drama/blob/main/web/src/pages/projects/scriptEditor.vue)
- 分镜管理：[shots/index.vue](https://github.com/LingGuoAI/LingGuo-Drama/blob/main/web/src/pages/shots/index.vue)
- 时间线编辑器：[VideoTimelineEditor.vue](https://github.com/LingGuoAI/LingGuo-Drama/blob/main/web/src/components/editor/VideoTimelineEditor.vue)
- 后端任务：[jobs/registry.go](https://github.com/LingGuoAI/LingGuo-Drama/blob/main/server/app/jobs/registry.go)
- AI 分镜：[ai_shots_job.go](https://github.com/LingGuoAI/LingGuo-Drama/blob/main/server/app/jobs/ai_shots_job.go)

