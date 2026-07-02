# 创意流水线系统 — 设计文档

> 版本：v1.0  
> 日期：2026-06-25  
> 状态：设计中

---

## 目录

1. [系统概述](#1-系统概述)
2. [核心概念](#2-核心概念)
3. [数据模型设计](#3-数据模型设计)
4. [后端架构](#4-后端架构)
5. [流水线执行引擎](#5-流水线执行引擎)
6. [资产库设计](#6-资产库设计)
7. [前端架构](#7-前端架构)
8. [API 接口设计](#8-api-接口设计)
9. [与现有模块集成](#9-与现有模块集成)
10. [分阶段实施计划](#10-分阶段实施计划)
11. [风险与注意事项](#11-风险与注意事项)

---

## 1. 系统概述

### 1.1 项目背景

当前平台已具备：
- 单张图片生成（文生图 / 图生图 / 局部编辑）
- 单段视频生成（文生视频 / 图生视频 / 关键帧）
- 多模态对话
- 无限画布（节点式创作）
- 社区广场

但缺乏**流程化、模板化、可复用**的多步骤创意生成能力。用户生成一个完整的视频作品（如漫剧、产品广告）需要手动逐张图、逐段视频地生成，效率低下且难以保证一致性。

### 1.2 项目目标

打造一套**可扩展的创意流水线（Creative Pipeline）系统**：

1. **流程化**：将复杂的多步骤创作封装为流水线，一键执行
2. **模板化**：内置多种创作模板（漫剧、广告、科普、MV...），用户开箱即用
3. **资产化**：角色、风格、剧本等创意元素可沉淀为可复用的资产
4. **可视化**：与无限画布深度融合，支持可视化编排和交互式调整
5. **可扩展**：新增一种内容类型 ≈ 新增一个模板 + 必要的步骤类型

### 1.3 设计原则

| 原则 | 说明 |
|------|------|
| **配置优于代码** | 模板、风格、剧本结构都通过配置定义，不写死在代码里 |
| **资产可复用** | 角色、风格、场景等创意元素独立存储，可跨流水线复用 |
| **断点续跑** | 长任务支持中断恢复，失败不重做已完成步骤 |
| **渐进式融合** | 先做独立功能验证，再逐步与画布深度集成 |
| **向后兼容** | 所有现有功能不受影响，新功能增量添加 |

---

## 2. 核心概念

### 2.1 核心实体关系图

```
┌─────────────────┐     ┌─────────────────┐
│ PipelineTemplate │────→│  ScriptTemplate │  剧本模板
│  (制作流模板)    │     │  (剧本模板)     │
└────────┬────────┘     └─────────────────┘
         │
         │ 包含 N 个步骤定义
         ▼
┌─────────────────┐     ┌─────────────────┐
│  StepDefinition │     │   StylePreset   │  风格预设
│  (步骤定义)      │     │  (风格预设)     │
└─────────────────┘     └─────────────────┘
         │
         │ 实例化
         ▼
┌─────────────────┐     ┌─────────────────┐
│  PipelineRun    │────→│   Asset (角色)   │  资产库
│  (流水线实例)    │     │  (可复用创意资产)│
└────────┬────────┘     └─────────────────┘
         │
         │ 包含 N 个步骤实例
         ▼
┌─────────────────┐
│   PipelineStep  │
│  (步骤执行记录)  │
└─────────────────┘
```

### 2.2 核心概念详解

#### 流水线模板（PipelineTemplate）

预定义的多步骤生成流程，描述「一件作品是怎么一步步做出来的」。

**属性：**
- `id`: 唯一标识
- `name`: 显示名称（如「标准漫剧生成」）
- `description`: 详细描述
- `category`: 分类（剧情类 / 广告类 / 科普类 / 艺术类）
- `thumbnail`: 缩略图 URL
- `inputs`: 用户输入参数定义（主题、风格、分镜数...）
- `steps`: 步骤定义数组（有序）
- `is_builtin`: 是否内置模板
- `is_public`: 是否公开（用户分享的模板）
- `author_id`: 作者用户 ID（内置模板为 NULL）

#### 剧本模板（ScriptTemplate）

LLM 生成剧本的提示词模板与输出结构定义。

**属性：**
- `id`: 唯一标识
- `name`: 模板名称
- `category`: 分类
- `structure`: 叙事结构（三幕式 / 五幕式 / 起承转合...）
- `prompt_template`: 提示词模板（Jinja2 风格变量：`{{theme}}`、`{{style}}`...）
- `output_schema`: 期望的 JSON 输出结构（JSON Schema）
- `scenes_count_min / max`: 推荐分镜数量范围
- `default_scene_duration`: 默认单镜时长（秒）

#### 风格预设（StylePreset）

视觉风格的可复用配置。

**属性：**
- `id`: 唯一标识
- `name`: 风格名称（如「赛博朋克 · 霓虹夜」）
- `category`: 分类（画风 / 氛围 / 镜头...）
- `visual_prefix`: 视觉风格前缀
- `lighting`: 光影风格
- `color_palette`: 配色方案
- `quality_suffix`: 品质增强词
- `negative_prompt`: 负面提示词
- `camera_language`: 镜头语言偏好
- `mood_keywords`: 氛围关键词
- `preview_image`: 预览图 URL

#### 资产（Asset）

可复用的创意素材单元。

**属性：**
- `id`: 唯一标识
- `type`: 类型（character 角色 / prop 道具 / scene 场景 / brand 品牌）
- `name`: 名称
- `description`: 详细描述
- `visual_description`: 外观描述文本（用于图生图提示词）
- `reference_images`: 参考图 URL 数组
- `style_id`: 关联的风格预设 ID（可选）
- `user_id`: 创建者用户 ID
- `is_public`: 是否公开到广场
- `tags`: 标签数组
- `version`: 版本号

#### 流水线实例（PipelineRun）

一次具体的流水线执行，有状态，可断点续跑。

**属性：**
- `id`: 唯一标识
- `template_id`: 使用的模板 ID
- `user_id`: 所属用户
- `name`: 本次运行的名称（用户可自定义）
- `inputs`: 用户输入的参数值（JSON）
- `status`: 整体状态（pending / running / success / failed / cancelled / waiting_review）
- `current_step_id`: 当前执行到的步骤 ID
- `started_at / finished_at`: 开始/结束时间
- `total_credits_consumed`: 累计消耗积分
- `output_summary`: 输出摘要（最终成片 URL 等）

#### 步骤实例（PipelineStep）

流水线中的一个执行步骤。

**属性：**
- `id`: 唯一标识
- `run_id`: 所属流水线实例 ID
- `step_key`: 步骤定义的 key（如 'script_generation'）
- `name`: 步骤显示名称
- `type`: 步骤类型（llm_generate / image_batch / video_batch / ffmpeg_composite / ...）
- `status`: 状态（pending / running / success / failed / skipped / waiting_review）
- `input_data`: 步骤输入数据（JSON）
- `output_data`: 步骤输出数据（JSON）
- `error_message`: 错误信息（失败时）
- `started_at / finished_at`: 开始/结束时间
- `credits_consumed`: 本步骤消耗积分
- `retry_count`: 重试次数
- `depends_on`: 依赖的步骤 key 数组

---

## 3. 数据模型设计

### 3.1 数据库表清单

| 表名 | 说明 | Phase |
|------|------|-------|
| `pipeline_templates` | 制作流模板 | Phase 1 |
| `pipeline_runs` | 流水线执行实例 | Phase 1 |
| `pipeline_steps` | 步骤执行记录 | Phase 1 |
| `assets` | 资产库（角色/道具/场景/品牌） | Phase 1 |
| `style_presets` | 风格预设 | Phase 1 |
| `script_templates` | 剧本模板 | Phase 1 |
| `asset_likes` | 资产点赞 | Phase 4 |
| `template_favorites` | 模板收藏 | Phase 4 |

### 3.2 详细表结构

---

#### 3.2.1 pipeline_templates — 制作流模板表

```sql
CREATE TABLE pipeline_templates (
    id              SERIAL PRIMARY KEY,
    key             VARCHAR(100) UNIQUE NOT NULL,    -- 模板唯一 key（如 'comic_drama_standard'）
    name            VARCHAR(200) NOT NULL,           -- 显示名称
    description     TEXT,                             -- 详细描述
    category        VARCHAR(50) NOT NULL,            -- 分类：drama / ad / education / art
    thumbnail_url   VARCHAR(500),                     -- 缩略图 URL
    inputs_config   JSON NOT NULL,                    -- 用户输入参数定义（JSON 数组）
    steps_config    JSON NOT NULL,                    -- 步骤定义（JSON 数组，有序）
    script_template_id INTEGER REFERENCES script_templates(id),  -- 关联的剧本模板
    is_builtin      BOOLEAN DEFAULT FALSE,            -- 是否内置模板
    is_public       BOOLEAN DEFAULT FALSE,            -- 是否公开
    author_id       INTEGER REFERENCES users(id),     -- 作者用户 ID（内置为 NULL）
    use_count       INTEGER DEFAULT 0,                -- 使用次数统计
    likes_count     INTEGER DEFAULT 0,                -- 点赞数
    created_at      TIMESTAMP DEFAULT NOW(),
    updated_at      TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_pipeline_templates_category ON pipeline_templates(category);
CREATE INDEX idx_pipeline_templates_is_public ON pipeline_templates(is_public);
CREATE INDEX idx_pipeline_templates_author ON pipeline_templates(author_id);
```

**inputs_config 示例：**
```json
[
  {
    "key": "theme",
    "label": "主题/故事梗概",
    "type": "textarea",
    "required": true,
    "placeholder": "描述你想生成的故事...",
    "max_length": 2000
  },
  {
    "key": "style_id",
    "label": "视觉风格",
    "type": "style_select",
    "required": true
  },
  {
    "key": "scenes_count",
    "label": "分镜数量",
    "type": "number",
    "min": 3,
    "max": 20,
    "default": 8
  }
]
```

**steps_config 示例：**
```json
[
  {
    "key": "script_generation",
    "name": "剧本生成",
    "type": "llm_generate",
    "timeout": 60,
    "max_retries": 2,
    "depends_on": []
  },
  {
    "key": "character_design",
    "name": "角色设计",
    "type": "image_batch",
    "timeout": 300,
    "max_retries": 1,
    "depends_on": ["script_generation"],
    "config": {
      "images_per_character": 3,
      "views": ["full_body", "close_up", "chibi"]
    }
  },
  {
    "key": "storyboard",
    "name": "分镜绘制",
    "type": "image_batch",
    "timeout": 600,
    "max_retries": 1,
    "depends_on": ["script_generation", "character_design"],
    "config": {
      "use_character_refs": true,
      "one_per_scene": true
    }
  }
]
```

---

#### 3.2.2 script_templates — 剧本模板表

```sql
CREATE TABLE script_templates (
    id              SERIAL PRIMARY KEY,
    key             VARCHAR(100) UNIQUE NOT NULL,
    name            VARCHAR(200) NOT NULL,
    description     TEXT,
    category        VARCHAR(50) NOT NULL,            -- drama / ad / education / art
    structure       VARCHAR(50) NOT NULL,            -- three_act / five_act / kishotenketsu
    prompt_template TEXT NOT NULL,                    -- 提示词模板（Jinja2 风格）
    output_schema   JSON NOT NULL,                    -- 期望的 JSON 输出结构（JSON Schema）
    scenes_min      INTEGER DEFAULT 3,
    scenes_max      INTEGER DEFAULT 20,
    default_scene_duration FLOAT DEFAULT 5.0,         -- 默认单镜时长（秒）
    is_builtin      BOOLEAN DEFAULT FALSE,
    is_public       BOOLEAN DEFAULT FALSE,
    author_id       INTEGER REFERENCES users(id),
    created_at      TIMESTAMP DEFAULT NOW(),
    updated_at      TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_script_templates_category ON script_templates(category);
```

**prompt_template 设计要点：**
- 使用 Jinja2 风格变量：`{{theme}}`、`{{style.name}}`、`{{scenes_count}}`
- 内置系统提示 + 用户主题 + 输出格式要求
- 不同剧本类型有完全不同的叙事结构和输出字段

---

#### 3.2.3 style_presets — 风格预设表

```sql
CREATE TABLE style_presets (
    id              SERIAL PRIMARY KEY,
    key             VARCHAR(100) UNIQUE NOT NULL,
    name            VARCHAR(200) NOT NULL,
    description     TEXT,
    category        VARCHAR(50) NOT NULL,            -- art_style / mood / cinematography
    visual_prefix   TEXT,                             -- 视觉风格前缀
    lighting        VARCHAR(500),                     -- 光影风格
    color_palette   VARCHAR(500),                     -- 配色方案
    quality_suffix  TEXT,                             -- 品质增强词
    negative_prompt TEXT,                             -- 负面提示词
    camera_language VARCHAR(500),                     -- 镜头语言偏好
    mood_keywords   VARCHAR(500),                     -- 氛围关键词
    preview_image   VARCHAR(500),                     -- 预览图 URL
    is_builtin      BOOLEAN DEFAULT FALSE,
    is_public       BOOLEAN DEFAULT FALSE,
    author_id       INTEGER REFERENCES users(id),
    use_count       INTEGER DEFAULT 0,
    created_at      TIMESTAMP DEFAULT NOW(),
    updated_at      TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_style_presets_category ON style_presets(category);
```

---

#### 3.2.4 assets — 资产库表

```sql
CREATE TABLE assets (
    id              SERIAL PRIMARY KEY,
    type            VARCHAR(30) NOT NULL,             -- character / prop / scene / brand
    name            VARCHAR(200) NOT NULL,
    description     TEXT,
    visual_description TEXT NOT NULL,                 -- 外观描述（用于生成提示词）
    reference_images JSON DEFAULT '[]'::json,         -- 参考图 URL 数组
    style_id        INTEGER REFERENCES style_presets(id),  -- 关联风格预设
    user_id         INTEGER REFERENCES users(id),
    is_public       BOOLEAN DEFAULT FALSE,
    moderation_status VARCHAR(20) DEFAULT 'approved', -- 审核状态
    moderation_reason VARCHAR(255),
    tags            JSON DEFAULT '[]'::json,          -- 标签数组
    version         INTEGER DEFAULT 1,                -- 版本号
    parent_id       INTEGER REFERENCES assets(id),    -- 父版本 ID
    likes_count     INTEGER DEFAULT 0,
    views_count     INTEGER DEFAULT 0,
    use_count       INTEGER DEFAULT 0,                -- 被使用次数
    created_at      TIMESTAMP DEFAULT NOW(),
    updated_at      TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_assets_type ON assets(type);
CREATE INDEX idx_assets_user ON assets(user_id);
CREATE INDEX idx_assets_is_public ON assets(is_public);
CREATE INDEX idx_assets_style ON assets(style_id);
```

---

#### 3.2.5 pipeline_runs — 流水线执行实例表

```sql
CREATE TABLE pipeline_runs (
    id                  SERIAL PRIMARY KEY,
    template_id         INTEGER NOT NULL REFERENCES pipeline_templates(id),
    user_id             INTEGER REFERENCES users(id),
    name                VARCHAR(200),                 -- 本次运行名称
    inputs              JSON NOT NULL,                -- 用户输入参数值
    status              VARCHAR(30) DEFAULT 'pending', -- pending/running/success/failed/cancelled/waiting_review
    current_step_key    VARCHAR(100),                 -- 当前执行步骤的 key
    started_at          TIMESTAMP,
    finished_at         TIMESTAMP,
    total_credits       INTEGER DEFAULT 0,             -- 累计消耗积分
    output_summary      JSON DEFAULT '{}'::json,      -- 输出摘要
    error_message       TEXT,                          -- 整体错误信息
    canvas_export_data  JSON,                          -- 导出到画布的数据（Phase 3）
    created_at          TIMESTAMP DEFAULT NOW(),
    updated_at          TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_pipeline_runs_user ON pipeline_runs(user_id);
CREATE INDEX idx_pipeline_runs_status ON pipeline_runs(status);
CREATE INDEX idx_pipeline_runs_template ON pipeline_runs(template_id);
```

**status 状态机：**
```
pending → running → success
     ↓       ↓
  cancelled  failed → retrying → ...
                ↓
           waiting_review （人工审核节点）
```

---

#### 3.2.6 pipeline_steps — 步骤执行记录表

```sql
CREATE TABLE pipeline_steps (
    id              SERIAL PRIMARY KEY,
    run_id          INTEGER NOT NULL REFERENCES pipeline_runs(id) ON DELETE CASCADE,
    step_key        VARCHAR(100) NOT NULL,            -- 步骤定义的 key
    name            VARCHAR(200) NOT NULL,            -- 步骤显示名称
    step_type       VARCHAR(50) NOT NULL,             -- 步骤类型
    status          VARCHAR(30) DEFAULT 'pending',    -- pending/running/success/failed/skipped/waiting_review
    input_data      JSON DEFAULT '{}'::json,          -- 步骤输入数据
    output_data     JSON DEFAULT '{}'::json,          -- 步骤输出数据
    error_message   TEXT,                              -- 错误信息
    started_at      TIMESTAMP,
    finished_at     TIMESTAMP,
    credits_consumed INTEGER DEFAULT 0,               -- 本步消耗积分
    retry_count     INTEGER DEFAULT 0,                 -- 重试次数
    max_retries     INTEGER DEFAULT 1,                 -- 最大重试次数
    timeout_sec     INTEGER DEFAULT 300,               -- 超时时间（秒）
    depends_on      JSON DEFAULT '[]'::json,          -- 依赖的步骤 key 数组
    sort_order      INTEGER NOT NULL,                  -- 排序序号
    created_at      TIMESTAMP DEFAULT NOW(),
    updated_at      TIMESTAMP DEFAULT NOW(),

    UNIQUE(run_id, step_key)
);

CREATE INDEX idx_pipeline_steps_run ON pipeline_steps(run_id);
CREATE INDEX idx_pipeline_steps_status ON pipeline_steps(status);
```

**output_data 按步骤类型的结构：**

- **llm_generate:**
  ```json
  {
    "raw_response": "...",
    "parsed_result": { ... },
    "tokens_used": 1024
  }
  ```

- **image_batch:**
  ```json
  {
    "images": [
      {
        "index": 0,
        "prompt": "...",
        "url": "https://...",
        "generation_id": 123
      }
    ],
    "total_count": 10
  }
  ```

- **video_batch:**
  ```json
  {
    "videos": [
      {
        "index": 0,
        "prompt": "...",
        "url": "https://...",
        "duration": 5.0,
        "generation_id": 456
      }
    ],
    "total_count": 8
  }
  ```

- **ffmpeg_composite:**
  ```json
  {
    "final_video_url": "https://...",
    "duration": 40.0,
    "subtitles_url": "https://...",
    "has_tts": true
  }
  ```

---

### 3.3 与现有表的关联

| 现有表 | 关联方式 | 说明 |
|--------|---------|------|
| `generations` | 加 `pipeline_run_id` + `pipeline_step_id` 字段 | 流水线产生的图片/视频仍写入 generations 表，便于统一管理和审核 |
| `users` | `user_id` 外键 | 流水线、资产都归属用户 |
| `plaza_likes` | 可复用到资产/模板点赞 | 或新建独立的点赞表 |

---

## 4. 后端架构

### 4.1 目录结构

```
backend/app/
├── models/
│   ├── pipeline.py          # 新增：流水线相关模型
│   ├── asset.py             # 新增：资产库模型
│   └── ...                  # 现有模型保持不变
│
├── schemas/
│   ├── pipeline.py          # 新增：流水线 Pydantic Schema
│   ├── asset.py             # 新增：资产库 Pydantic Schema
│   └── ...
│
├── services/
│   ├── pipeline/            # 新增：流水线服务模块
│   │   ├── __init__.py
│   │   ├── engine.py        # 执行引擎（DAG + 状态机 + 调度）
│   │   ├── template_service.py   # 模板管理
│   │   ├── run_service.py   # 流水线实例管理
│   │   ├── progress.py      # SSE 进度推送
│   │   └── steps/           # 步骤执行器
│   │       ├── __init__.py
│   │       ├── base.py      # 步骤执行器基类（抽象）
│   │       ├── llm_generate.py    # LLM 文本生成
│   │       ├── image_batch.py     # 批量图片生成
│   │       ├── video_batch.py     # 批量视频生成
│   │       ├── ffmpeg_composite.py  # FFmpeg 合成（Phase 2）
│   │       ├── tts_generate.py     # TTS 语音生成（Phase 2）
│   │       └── human_review.py     # 人工审核节点（Phase 3）
│   │
│   ├── asset_library.py     # 新增：资产库服务
│   ├── style_service.py     # 新增：风格预设服务
│   ├── script_service.py    # 新增：剧本模板服务
│   └── ...                  # 现有服务保持不变
│
├── routes/
│   ├── pipeline.py          # 新增：流水线 API 路由
│   ├── assets.py            # 新增：资产库 API 路由
│   ├── styles.py            # 新增：风格预设 API 路由
│   └── ...
│
└── core/
    └── ...
```

### 4.2 模块职责

#### pipeline/engine.py — 执行引擎

核心职责：
1. 解析模板的 steps_config，构建 DAG（有向无环图）
2. 拓扑排序，确定执行顺序
3. 管理状态机（pipeline 级别 + step 级别）
4. 调度步骤执行（串行 / 可并行的并行）
5. 处理失败重试
6. 断点续跑（从数据库恢复状态后继续）
7. 积分预扣 & 实扣

关键方法：
```python
class PipelineEngine:
    async def start_run(self, run_id: int) -> None:
        """启动一个流水线实例"""

    async def resume_run(self, run_id: int) -> None:
        """从断点恢复执行"""

    async def cancel_run(self, run_id: int) -> None:
        """取消执行"""

    async def _execute_step(self, step: PipelineStep) -> None:
        """执行单个步骤"""

    async def _get_ready_steps(self, run_id: int) -> List[PipelineStep]:
        """获取所有依赖已满足、可以开始执行的步骤"""
```

#### pipeline/steps/base.py — 步骤执行器基类

```python
from abc import ABC, abstractmethod
from typing import Any, Dict

class BaseStepExecutor(ABC):
    """步骤执行器抽象基类"""

    step_type: str = ""  # 子类必须声明

    def __init__(self, step_config: Dict[str, Any], run_context: Dict[str, Any]):
        self.config = step_config
        self.context = run_context  # 流水线全局上下文（各步骤的输出等）

    @abstractmethod
    async def validate_input(self) -> None:
        """验证输入数据"""

    @abstractmethod
    async def execute(self) -> Dict[str, Any]:
        """执行步骤，返回输出数据"""

    @abstractmethod
    async def estimate_credits(self) -> int:
        """预估消耗积分"""

    async def cleanup(self) -> None:
        """清理资源（可选）"""
```

#### pipeline/steps/llm_generate.py — LLM 文本生成步骤

职责：
1. 从剧本模板获取 prompt_template
2. 用 Jinja2 渲染变量（inputs + 上游步骤输出）
3. 调用 LLM（对话模型）生成文本
4. 解析输出 JSON（多层容错）
5. 返回结构化结果

#### pipeline/steps/image_batch.py — 批量图片生成步骤

职责：
1. 根据上游输出（剧本、角色列表）构建每张图的 prompt
2. 应用风格预设（visual_prefix + lighting + quality_suffix + negative_prompt）
3. 批量提交生成任务（可并发）
4. 轮询所有任务直到完成
5. 收集结果 URL 并返回

#### pipeline/steps/video_batch.py — 批量视频生成步骤

职责：
1. 类似 image_batch，但调用视频生成 API
2. 每个分镜对应一段视频
3. 使用分镜图作为参考图（图生视频）

---

## 5. 流水线执行引擎

### 5.1 DAG 执行模型

```
  剧本生成
      │
      ▼
  角色设计 ────┐
      │        │
      ▼        │
  分镜绘制 ◄───┘
      │
      ▼
  视频生成
      │
      ▼
  成片合成
```

**执行规则：**
- 一个步骤的所有依赖（depends_on）都成功后，才能开始执行
- 无依赖的步骤可以并行执行（如多个角色的设计可以同时生成）
- 某步骤失败时：
  - 若 retry_count < max_retries：自动重试
  - 否则：整个流水线标记为 failed，已完成的步骤保留结果
- 人工审核步骤（human_review）：执行到该步时暂停，状态改为 waiting_review，用户确认后继续

### 5.2 上下文传递机制

每个步骤执行时，可以访问：
- `inputs`: 用户输入的参数
- `steps.{step_key}.output_data`: 上游步骤的输出数据
- `assets`: 使用的资产数据（角色、风格等）

**示例（分镜绘制步骤访问上游数据）：**
```python
# 从上下文中获取剧本
script = self.context["steps"]["script_generation"]["output_data"]["parsed_result"]

# 获取角色设计的图片
char_images = self.context["steps"]["character_design"]["output_data"]["images"]

# 获取风格预设
style = self.context["style_preset"]
```

### 5.3 断点续跑机制

**触发场景：**
- 服务器重启
- 用户主动暂停
- 某步骤失败后，用户修复并重试
- 人工审核节点等待后继续

**恢复流程：**
1. 从 `pipeline_runs` 表读取流水线状态
2. 从 `pipeline_steps` 表读取所有步骤状态
3. 重建 DAG 和上下文（从已完成步骤的 output_data 恢复）
4. 找到第一个未完成的步骤，继续执行
5. 已完成的步骤直接跳过

### 5.4 并发控制

**限制策略：**
- 同一用户同时运行的流水线数：最多 2 个
- 单个流水线内同时执行的图片任务：最多 5 个并发
- 单个流水线内同时执行的视频任务：最多 2 个并发
- 全局并发上限：按系统容量配置

**目的：**
- 避免耗尽 Agnes AI API 额度
- 防止单用户占用过多资源
- 保证系统稳定性

### 5.5 进度推送

使用 **SSE（Server-Sent Events）** 实时推送进度：

```
GET /api/pipeline/runs/{run_id}/stream

事件流：
event: step_started
data: {"step_key": "script_generation", "name": "剧本生成", "timestamp": "..."}

event: step_progress
data: {"step_key": "character_design", "progress": 0.6, "current": 3, "total": 5}

event: step_completed
data: {"step_key": "script_generation", "output_summary": {...}}

event: step_failed
data: {"step_key": "storyboard", "error": "...", "retryable": true}

event: pipeline_completed
data: {"status": "success", "output_summary": {...}}
```

---

## 6. 资产库设计

### 6.1 资产类型

| 类型 | 说明 | 典型用途 |
|------|------|---------|
| `character` 角色 | 人物、动物、拟人化角色 | 漫剧、动画、故事 |
| `prop` 道具 | 产品、物品、符号 | 广告、电商、展示 |
| `scene` 场景 | 背景环境、室内外场景 | 所有类型的背景 |
| `brand` 品牌 | Logo、产品图、VI 元素 | 品牌宣传、广告 |

### 6.2 资产创建方式

1. **手动创建**：用户填写描述 + 上传参考图
2. **从生成结果保存**：在历史记录 / 画布中，右键图片 → 「保存到资产库」
3. **从流水线提取**：流水线生成的角色/场景，可以一键提取为资产
4. **从广场收藏**：看到别人分享的好资产，收藏到自己的库

### 6.3 资产版本管理

- 每个资产有 `version` 字段（整数，从 1 开始）
- 修改资产描述/参考图时，创建新版本（不覆盖旧版本）
- `parent_id` 指向前一个版本，形成版本链
- 用户可以查看历史版本、回退到旧版本
- 流水线使用资产时，记录使用的版本号

### 6.4 风格预设的应用方式

风格预设作用于提示词的构建：

```
最终 prompt = visual_prefix + 主体描述 + lighting + color_palette + camera_language + mood_keywords + quality_suffix
negative_prompt = style.negative_prompt
```

**层级覆盖：**
1. 全局默认风格（系统配置）
2. 用户选择的风格预设（覆盖默认）
3. 具体步骤的配置（覆盖风格预设的某些字段）

---

## 7. 前端架构

### 7.1 页面结构

```
创意工坊（/workshop）
├── 模板市场（首页）
│   ├── 分类侧边栏
│   ├── 搜索框
│   └── 模板卡片网格
│
├── 模板配置 & 运行（/workshop/templates/{key}）
│   ├── 左侧：参数配置表单
│   └── 右侧：实时进度 + 步骤列表
│
├── 结果页（/workshop/runs/{id}）
│   ├── 成片播放区
│   ├── 步骤详情 Tab（可展开看每步结果）
│   ├── 操作按钮（重跑/导出画布/发布/保存作品）
│   └── 时间轴预览（分镜 + 字幕 + 配音）
│
└── 我的资产库（/assets）
    ├── Tab：角色 / 道具 / 场景 / 品牌 / 风格 / 我的模板
    ├── 网格视图
    └── 详情弹窗（查看/编辑/版本历史）
```

### 7.2 状态管理

新增 Store：

| Store | 职责 |
|-------|------|
| `pipeline.ts` | 当前流水线实例、步骤状态、SSE 连接管理 |
| `assets.ts` | 资产库列表、当前选中资产、筛选条件 |
| `styles.ts` | 风格预设列表、当前风格 |

对现有 Store 的扩展：
- `taskQueue.ts`：新增 `type='pipeline'` 的任务类型，点击可展开查看子步骤

### 7.3 关键组件

| 组件 | 职责 |
|------|------|
| `TemplateCard.vue` | 模板卡片（缩略图 + 名称 + 分类 + 使用次数） |
| `PipelineProgress.vue` | 流水线进度展示（步骤列表 + 当前步骤详情） |
| `StepImagesGallery.vue` | 步骤结果图片/视频画廊（支持分页、放大查看） |
| `StyleSelector.vue` | 风格选择器（网格 + 预览） |
| `AssetCard.vue` | 资产卡片（图 + 名称 + 类型标签） |
| `AssetDetailModal.vue` | 资产详情弹窗（查看/编辑/版本） |
| `TimelinePreview.vue` | 时间轴预览（分镜 + 字幕 + 配音的时间关系） |

### 7.4 与画布的集成（Phase 3）

#### 导出到画布

流水线完成后，点击「导出到画布」：
1. 前端调用 API 获取画布导出数据（节点 + 连线的位置和内容）
2. 跳转到画布页面，URL 带参数 `?import=pipeline:{run_id}`
3. 画布加载时检测到 import 参数，自动导入节点和连线

**节点布局：**
```
  剧本(文本)   角色1(图)  角色2(图)  ...
      │           │          │
      └───────────┴──────────┘
                  │
            分镜1(图)  分镜2(图)  ...  分镜N(图)
                  │
            成片(视频)
```

#### 从画布启动流水线

右键画布上的节点 → 「用选中资产启动流水线」：
1. 用户选择一个模板
2. 系统自动填充能用的输入（选中的图片 → 角色/风格，选中的文本 → 主题）
3. 跳转到模板配置页，预填参数

---

## 8. API 接口设计

### 8.1 流水线模板 API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/pipeline/templates` | 获取模板列表（支持分类筛选、搜索、分页） |
| GET | `/api/pipeline/templates/{id}` | 获取模板详情 |
| POST | `/api/pipeline/templates` | 创建自定义模板（用户） |
| PUT | `/api/pipeline/templates/{id}` | 更新模板 |
| DELETE | `/api/pipeline/templates/{id}` | 删除模板 |
| POST | `/api/pipeline/templates/{id}/duplicate` | 复制模板 |

### 8.2 流水线运行 API

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/pipeline/runs` | 创建并启动流水线实例 |
| GET | `/api/pipeline/runs` | 获取我的流水线列表（分页） |
| GET | `/api/pipeline/runs/{id}` | 获取流水线详情（含所有步骤状态） |
| POST | `/api/pipeline/runs/{id}/cancel` | 取消流水线 |
| POST | `/api/pipeline/runs/{id}/retry` | 失败后重试 |
| POST | `/api/pipeline/runs/{id}/resume` | 从人工审核节点继续 |
| GET | `/api/pipeline/runs/{id}/events` | SSE 实时进度流 |
| GET | `/api/pipeline/runs/{id}/steps/{stepKey}` | 获取单步详情 |
| POST | `/api/pipeline/runs/{id}/steps/{stepKey}/retry` | 单独重试某一步 |
| POST | `/api/pipeline/runs/{id}/export-canvas` | 导出到画布数据 |

### 8.3 资产库 API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/pipeline/assets` | 获取资产列表（筛选：type、tag、search、mine/public） |
| GET | `/api/pipeline/assets/{id}` | 获取资产详情 |
| POST | `/api/pipeline/assets` | 创建资产 |
| PUT | `/api/pipeline/assets/{id}` | 更新资产（创建新版本） |
| DELETE | `/api/pipeline/assets/{id}` | 删除资产 |
| GET | `/api/pipeline/assets/{id}/versions` | 获取版本历史 |
| POST | `/api/pipeline/assets/{id}/like` | 点赞/取消点赞 |
| POST | `/api/pipeline/assets/{id}/save-from-generation` | 从生成记录保存为资产 |

### 8.4 风格预设 API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/pipeline/styles` | 获取风格列表 |
| GET | `/api/pipeline/styles/{id}` | 获取风格详情 |
| POST | `/api/pipeline/styles` | 创建自定义风格 |
| PUT | `/api/pipeline/styles/{id}` | 更新风格 |
| DELETE | `/api/pipeline/styles/{id}` | 删除风格 |

### 8.5 剧本模板 API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/pipeline/script-templates` | 获取剧本模板列表 |
| GET | `/api/pipeline/script-templates/{id}` | 获取详情 |
| POST | `/api/pipeline/script-templates` | 创建 |
| PUT | `/api/pipeline/script-templates/{id}` | 更新 |
| DELETE | `/api/pipeline/script-templates/{id}` | 删除 |

---

## 9. 与现有模块集成

### 9.1 生成历史（generations 表）

**新增字段：**
- `pipeline_run_id` (Integer, nullable) — 关联的流水线实例 ID
- `pipeline_step_id` (Integer, nullable) — 关联的步骤 ID

**影响：**
- 流水线产生的每张图片、每段视频，都正常写入 generations 表
- 历史记录页可以筛选「只看非流水线的」或「全部」
- 内容审核流程完全复用现有机制

### 9.2 任务队列（TaskQueue Store）

**新增流水线任务类型：**
- 类型：`type = 'pipeline'`
- 显示：在队列面板中显示为特殊样式，带进度条和步骤数
- 点击展开：显示子步骤列表（类似文件夹展开）
- 右键菜单：取消、查看详情、重试

### 9.3 积分系统

**积分消耗：**
- 流水线创建时：预估总积分，做预扣（或不预扣，按实际消耗逐步扣）
- 每步完成时：按实际生成量扣减
- 流水线失败：已消耗的积分不退（但失败的步骤如果重试会再扣）

**预估积分 API：**
- `POST /api/pipeline/templates/{key}/estimate` — 根据输入参数预估总积分
- 在配置页实时显示预估积分

### 9.4 内容审核

**审核策略：**
- 流水线产生的每张图片/视频，走现有审核流程
- 若某步骤的输出被审核拒绝：
  - 该步骤标记为 failed
  - 整个流水线暂停（状态：failed）
  - 用户可以：替换该步的输出（手动上传）后继续，或整步重试
- 最终成片发布到广场：走现有的广场审核流程

### 9.5 广场

**新增内容类型：**
- `type = 'pipeline'` — 流水线作品
- 展示：封面图 + 标题 + 作者 + 步骤数 + 时长
- 详情页：播放成片 + 步骤概览 + 角色/风格标签 + 「使用同款模板」按钮

**「使用同款模板」流程：**
1. 点击按钮 → 跳转到模板配置页
2. 自动加载该作品使用的模板和参数
3. 用户修改主题等参数后一键生成

### 9.6 菜单 & 权限

**新增菜单项：**
- 「创意工坊」（Workshop）— 所有用户可见
  - 子菜单：模板市场 / 我的作品 / 我的资产

**权限：**
- 普通用户：使用内置模板、管理自己的资产、创建私有模板
- 管理员：管理内置模板、审核公开模板/资产、配置系统默认风格

---

## 10. 分阶段实施计划

### Phase 1：基础骨架（MVP）

**目标：** 跑通一个完整的流水线，验证架构可行性

**工作内容：**

1. **数据库 & 模型层**
   - 创建 6 张新表（pipeline_templates / pipeline_runs / pipeline_steps / assets / style_presets / script_templates）
   - generations 表加 pipeline_run_id 和 pipeline_step_id 字段
   - 编写 Pydantic Schema
   - 编写数据库迁移脚本

2. **资产库基础服务**
   - StylePreset CRUD + 内置 10 种常用风格
   - Asset CRUD（角色/道具/场景/品牌）
   - ScriptTemplate CRUD + 内置 2-3 个剧本模板
   - 对应 API 路由

3. **流水线执行引擎**
   - DAG 解析 + 拓扑排序
   - 步骤执行器框架（BaseStepExecutor）
   - 实现 3 种步骤：llm_generate / image_batch / video_batch
   - 状态机管理
   - 断点续跑
   - 失败重试
   - 积分逐步扣减

4. **第一个流水线模板：标准漫剧（4 步）**
   - 剧本生成 → 角色设计 → 分镜绘制 → 视频生成
   - 内置剧本模板 + 风格预设
   - 提示词工程（自行设计，不抄对方的）

5. **SSE 进度推送**
   - 服务端 SSE 实现
   - 前端 SSE 客户端封装

6. **前端页面**
   - 创意工坊落地页（模板市场）
   - 模板配置 & 运行页
   - 结果展示页
   - 资产库管理页（风格 + 角色 + 剧本模板）
   - 路由配置 + 菜单配置

7. **与现有系统集成**
   - TaskQueue 展示流水线任务
   - generations 表关联
   - 积分扣减
   - 内容审核复用

**交付物：**
- 用户可以选择「标准漫剧」模板，输入主题，一键生成完整的分镜视频
- 有基本的资产库（角色、风格、剧本模板）
- 支持断点续跑和失败重试

**预估时间：** 2-3 周

---

### Phase 2：成片合成 & 配音

**目标：** 实现最终成片输出，完整闭环

**工作内容：**

1. **FFmpeg 合成步骤**
   - ffmpeg_composite 步骤执行器
   - 视频拼接：xfade 转场 + concat 简单拼接回退
   - 字幕生成：SRT 格式 + 字幕样式配置
   - 字幕烧录：ffmpeg subtitles 滤镜
   - 背景音乐（可选，先内置几首免费 BGM）

2. **TTS 配音步骤**
   - tts_generate 步骤执行器
   - 复用 agn-sdk 的 TTS 能力（Edge-TTS 优先）
   - 角色声音分配（同角色同声音，性别匹配）
   - 时间轴对齐（按分镜时间分布对白）
   - 音频混音（多对白 + BGM）

3. **前端增强**
   - 时间轴预览组件（显示分镜、字幕、配音的时间关系）
   - 字幕编辑器（生成后可手动修改）
   - 成片播放器（带字幕切换、倍速等）

4. **更新流水线模板**
   - 「标准漫剧」模板增加成片合成步骤
   - 新增 1-2 个模板（产品广告、科普短片）

**交付物：**
- 流水线可以生成带字幕、带配音、带转场的完整视频
- 支持在线预览和下载

**预估时间：** 1-2 周

---

### Phase 3：画布深度融合

**目标：** 发挥无限画布独特优势，拉开与竞品差距

**工作内容：**

1. **流水线 → 画布导出**
   - 导出数据结构（节点 + 连线 + 位置）
   - 画布导入功能（URL 参数触发）
   - 自动布局算法（按流程排列节点）

2. **画布 → 流水线输入**
   - 右键菜单：「用选中资产启动流水线」
   - 智能参数填充（图片 → 角色/风格，文本 → 主题）
   - 跳转到配置页并预填

3. **画布内选择性重跑**
   - 导出到画布后，节点带流水线元数据
   - 右键某分镜节点 → 「重新生成分镜」
   - 只重跑该步骤及其下游步骤

4. **可视化流水线编辑器**
   - 拖拽式编辑模板（类似画布节点）
   - 步骤节点 + 连线定义依赖
   - 每个步骤节点可配置参数
   - 保存为自定义模板

**交付物：**
- 流水线和画布双向打通
- 用户可以用画布做可视化创意编排
- 支持自定义流水线模板

**预估时间：** 2-3 周

---

### Phase 4：资产生态 & 社区

**目标：** 让用户贡献内容，形成资产生态

**工作内容：**

1. **资产分享 & 广场**
   - 资产发布到广场（走审核流程）
   - 广场新增「资产」分类
   - 「收藏到我的资产库」功能
   - 资产评分、评论、使用量统计

2. **模板市场**
   - 用户分享模板
   - 模板广场（分类、搜索、推荐）
   - 「使用此模板」一键创建
   - 模板评分和评论

3. **从作品提取资产**
   - 广场作品详情页：「提取角色」「提取风格」按钮
   - 提取后保存到我的资产库

4. **资产版本管理完善**
   - 版本对比（diff 可视化）
   - 版本回滚
   - 分支版本（从某版本分叉）

**交付物：**
- 完整的资产生态系统
- UGC 内容闭环

**预估时间：** 2-3 周

---

## 11. 风险与注意事项

### 11.1 技术风险

| 风险 | 影响 | 应对措施 |
|------|------|---------|
| Agnes AI 额度不足 | 流水线大批量生成时容易触发限流 | 1. 并发控制 2. 速率限制 3. 队列缓冲 |
| 长任务容易中断 | 服务器重启、用户关闭页面 | 断点续跑机制，状态持久化到数据库 |
| FFmpeg 资源消耗高 | 合成时 CPU 占用高，影响其他服务 | 1. 队列化处理 2. 限制并发合成数 3. 考虑异步 worker |
| LLM 输出不稳定 | 剧本生成可能返回格式不对的 JSON | 多层容错解析 + 重试 + 系统提示加固 |

### 11.2 产品风险

| 风险 | 影响 | 应对措施 |
|------|------|---------|
| 模板太少 | 用户觉得功能单一 | Phase 1 先做 2-3 个核心模板，验证需求后再扩展 |
| 生成质量不可控 | 流水线出来的效果可能参差不齐 | 1. 高质量内置模板 2. 允许用户中途调整 3. 画布融合后可手动修改 |
| 用户学习成本高 | 新概念太多（资产、模板、流水线） | 1. 渐进式引导 2. 默认配置开箱即用 3. 示例和教程 |

### 11.3 注意事项

1. **积分计算要准确**：每步实际消耗的积分必须正确统计，不能多扣也不能少扣
2. **审核不能漏**：所有生成的图片和视频都要走审核流程，不能因为是流水线就跳过
3. **数据库性能**：pipeline_steps 表会增长很快，注意索引和分区
4. **向前兼容**：模板配置的结构可能变化，要考虑版本兼容性
5. **用户数据隔离**：不同用户的资产、流水线必须严格隔离

---

## 附录 A：内置模板清单（Phase 1-2）

### Phase 1 内置模板

| 模板 Key | 名称 | 分类 | 步骤数 | 说明 |
|----------|------|------|--------|------|
| `comic_drama_standard` | 标准漫剧生成 | drama | 4 | 剧本→角色→分镜→视频 |
| `product_ad_simple` | 产品展示短片 | ad | 3 | 产品描述→多场景图→视频 |

### Phase 2 内置模板

| 模板 Key | 名称 | 分类 | 步骤数 | 说明 |
|----------|------|------|--------|------|
| `comic_drama_full` | 完整漫剧（含配音） | drama | 6 | 加 TTS + 成片合成 |
| `edu_short` | 科普短片 | education | 5 | 知识点→分镜脚本→画面→配音→合成 |

---

## 附录 B：内置风格预设（Phase 1）

| 风格 Key | 名称 | 分类 | 说明 |
|----------|------|------|------|
| `anime_warm` | 温暖二次元 | art_style | 日系动漫风，暖色调 |
| `cyberpunk_neon` | 赛博朋克·霓虹夜 | art_style | 赛博朋克，霓虹灯光 |
| `chinese_ink` | 国风水墨 | art_style | 中国风水墨画 |
| `realistic_cine` | 写实电影感 | art_style | 照片级写实，电影构图 |
| `watercolor_soft` | 柔和水彩 | art_style | 水彩画风格，柔和色调 |
| `3d_render_pixar` | 3D 皮克斯风 | art_style | 3D 卡通渲染，皮克斯质感 |
| `warm_healing` | 温暖治愈 | mood | 暖色调，柔光，治愈感 |
| `dark_suspense` | 暗黑悬疑 | mood | 暗调，阴影，悬疑氛围 |
| `cinematic_wide` | 宽银幕电影感 | cinematography | 2.39:1 宽画幅，电影镜头 |
| `mv_dynamic` | MV 动感 | cinematography | 快速剪辑感，动态构图 |

---

*文档结束*
