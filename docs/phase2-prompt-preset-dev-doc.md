# Agnes Platform VNext 第二阶段开发文档

## 统一提示词预设系统

---

### 一、需求概述

#### 1.1 背景

Phase 1 实现了摄像机控制 Prompt 注入，CameraPreset 独立存储。Phase 2 的目标是构建统一的提示词预设系统，将摄像机预设、通用文本提示词预设、以及现有的 StylePreset、ScriptTemplate、PipelineTemplate 全部纳入统一管理入口，成为所有「可复用创作配置」的统一管理中心。

借鉴 Open Storyboard Canvas 的提示词库设计，提供分类标签、公开共享、社区预设库、一键应用到画布节点/Chat/Pipeline 的完整闭环。

#### 1.2 核心目标

- 新建通用文本提示词预设（PromptPreset）
- 构建统一预设中心页面 + 使用场景内嵌快捷面板
- 将 CameraPreset、StylePreset、ScriptTemplate、PipelineTemplate 纳入统一入口
- 支持三层分类体系（type + category + tags）
- 管理员审核后的社区预设库
- 导入/导出 JSON 格式
- Chat Tool Calling 预设感知
- Pipeline 步骤预设选择 + 变量替换

#### 1.3 关键决策回顾

| 决策项 | 结论 |
|---|---|
| 类型边界 | 大一统：全部纳入统一入口 |
| 交互形态 | 预设中心页面 + 快捷面板共存 |
| 数据模型 | 分表存储，统一 API 聚合 |
| 分类体系 | 三层结构：type + category + tags |
| 公开共享 | 管理员审核后公开 |
| Phase 1 迁移 | CameraPreset 已在 Phase 1 预建完整结构，Phase 2 无需重建，直接纳入统一 API |
| 开发策略 | 渐进式（4 个子阶段） |

---

### 二、整体架构

```
┌─────────────────────────────────────────────────────────┐
│                    PresetCenter.vue                        │
│              预设中心（独立路由 /presets）                  │
│  ┌──────────┬──────────┬──────────┬──────────┬────────┐ │
│  │ 全部     │ 摄像机   │ 提示词   │  风格    │  脚本   │ │
│  │          │ Camera   │ Prompt   │  Style   │ Script  │ │
│  └──────────┴──────────┴──────────┴──────────┴────────┘ │
│  ┌─────────────────────────────────────────────────┐     │
│  │ 搜索 / 分类筛选 / 标签筛选 / 排序（新建|热门|使用量） │     │
│  └─────────────────────────────────────────────────┘     │
│  ┌─────────────────────────────────────────────────┐     │
│  │              预设卡片网格列表                       │     │
│  └─────────────────────────────────────────────────┘     │
├─────────────────────────────────────────────────────────┤
│                     社区预设库 Tab                         │
│              已审核通过的公开预设（可复制到我的）           │
├─────────────────────────────────────────────────────────┤
│                PresetQuickPanel.vue                        │
│        画布节点 / Chat 输入区 / Pipeline 编辑器内嵌        │
│        最近使用 5 条 + 搜索 + 前往预设中心链接              │
└─────────────────────────────────────────────────────────┘
```

### 数据层架构

```
                  /api/presets（统一聚合 API）
                  ?type=camera|prompt|style|script|pipeline
                  &category=&tags=&search=&sort=&page=&size=
                          │
        ┌─────────────────┼──────────────────┐
        ▼                 ▼                   ▼
  camera_presets    prompt_presets    preset_index
  (Phase 1 预建)    (Phase 2 新建)    (轻量索引表)
        │                 │                   │
        ▼                 ▼                   ▼
  CameraPresetService  PromptPresetService  跨表聚合查询
                                            ↓
                          ┌─────────────────┼──────────────────┐
                          ▼                 ▼                   ▼
                    camera_presets   prompt_presets   style_presets
                    script_templates pipeline_templates
```

---

### 三、数据结构设计

#### 3.1 新建表：prompt_presets

```sql
CREATE TABLE prompt_presets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    type VARCHAR(50) NOT NULL DEFAULT 'prompt',
    category VARCHAR(50) DEFAULT '通用',
    tags JSONB DEFAULT '[]',
    prompt_text TEXT NOT NULL,
    is_public BOOLEAN DEFAULT FALSE,
    is_approved BOOLEAN DEFAULT FALSE,
    usage_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_prompt_presets_user ON prompt_presets(user_id);
CREATE INDEX idx_prompt_presets_type ON prompt_presets(type);
CREATE INDEX idx_prompt_presets_category ON prompt_presets(category);
CREATE INDEX idx_prompt_presets_approved ON prompt_presets(is_approved);
CREATE INDEX idx_prompt_presets_tags ON prompt_presets USING GIN(tags);
```

#### 3.1.1 跨表聚合索引表：`preset_index`

为提升跨表聚合查询性能、避免全表扫描多张预设表，引入轻量索引表：

```sql
CREATE TABLE preset_index (
    preset_id UUID NOT NULL,          -- 原表主键
    type VARCHAR(50) NOT NULL,        -- camera / prompt / style / script / pipeline
    category VARCHAR(50),
    tags JSONB DEFAULT '[]',
    user_id UUID NOT NULL,
    name VARCHAR(255) NOT NULL,
    is_public BOOLEAN DEFAULT FALSE,
    is_approved BOOLEAN DEFAULT FALSE,
    usage_count INTEGER DEFAULT 0,
    updated_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (preset_id, type)
);

CREATE INDEX idx_preset_index_type ON preset_index(type);
CREATE INDEX idx_preset_index_category ON preset_index(category);
CREATE INDEX idx_preset_index_tags ON preset_index USING GIN(tags);
CREATE INDEX idx_preset_index_usage ON preset_index(usage_count DESC);
CREATE INDEX idx_preset_index_updated ON preset_index(updated_at DESC);
```

**写入策略**：各 Preset Service 在 CUD 操作时同步 upsert `preset_index`（通过 DB trigger 或 Service 层钩子）。查询时 `type` 为空（全部类型）直接走 `preset_index`，单一 `type` 走原表。

#### 3.1.2 Category 后台枚举策略

#### 3.1.2 Category 后台枚举策略

`category` 不开放自由填写，由后台预设枚举值控制：

| 枚举值 | 说明 |
|---|---|
| `人像` | 人物肖像、特写、群像 |
| `场景` | 环境、建筑、室内外 |
| `构图` | 视角、布局、画幅 |
| `动作` | 动态、运镜、姿态 |
| `光影` | 灯光、色调、氛围 |
| `风格` | 艺术风格、流派 |
| `通用` | 不归属上述分类的兜底值 |

- 创建预设时，用户从下拉框选择 category（默认"通用"）
- 管理员可在后台增删枚举值
- AI 自动分类仅建议 category，最终以用户选择的为准

#### 3.1.3 Tags 策略

标签**开放自由填写**，不做枚举限制。但前端交互与 AI 辅助有一层过滤规则：

- **AI 自动打标**：创建预设时调 LLM 一次，分析内容后建议 tags（最多 5 个）
- 用户可增删 AI 建议的 tags，也可自由输入自定义标签
- **前端筛选**：标签筛选下拉框仅展示使用频率 Top 50 标签，减少噪音
- 搜索支持按标签全文本匹配

#### 3.2 CameraPreset 表（Phase 1 已预建）

CameraPreset 表已在 Phase 1 按 Phase 2 最终结构预建（含 type/category/tags/is_approved/usage_count），Phase 2 **无需执行任何 DDL 变更**。Phase 2 上线时的迁移脚本仅做数据补齐：

```sql
-- 为 Phase 1 已创建的 CameraPreset 补齐统一字段（如未设置）
UPDATE camera_presets SET type = 'camera' WHERE type IS NULL;
UPDATE camera_presets SET category = '通用' WHERE category IS NULL;
UPDATE camera_presets SET tags = '[]'::jsonb WHERE tags IS NULL;
UPDATE camera_presets SET is_approved = FALSE WHERE is_approved IS NULL;
UPDATE camera_presets SET usage_count = 0 WHERE usage_count IS NULL;
```

表结构参考 Phase 1 开发文档 §3.1.1。

#### 3.3 现有表适配

**style_presets**、**script_templates**、**pipeline_templates** 表不修改结构，通过 API 聚合层在查询时补充虚拟字段 `type`，映射关系：

| 现有表 | type 值 | 现有表自带分类字段 |
|---|---|---|
| style_presets | style | 已有 category |
| script_templates | script | 无 → 聚合层返回默认值 |
| pipeline_templates | pipeline | 无 → 聚合层返回默认值 |

#### 3.4 后端 Model

**新建文件**：`backend/app/models/prompt_preset.py`

```python
from sqlalchemy import Column, String, Integer, Boolean, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.core.database import Base
import uuid

class PromptPreset(Base):
    __tablename__ = "prompt_presets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    type = Column(String(50), nullable=False, default="prompt")
    category = Column(String(50), default="通用")
    tags = Column(JSONB, default=[])
    prompt_text = Column(Text, nullable=False)
    is_public = Column(Boolean, default=False)
    is_approved = Column(Boolean, default=False)
    usage_count = Column(Integer, default=0)
```

**改造文件**：`backend/app/models/camera_preset.py` — 已在 Phase 1 预建完成，Phase 2 无需改造，直接复用。

#### 3.4.1 usage_count 异步统计

`usage_count` 不实时更新（避免高频写入影响预设编辑性能），改为异步定时任务统计：

- **统计来源**：扫描 generation 表（images/videos），提取其中引用的 preset_id
- **统计口径**：仅统计生成成功的记录（status=success）
- **执行频率**：每小时一次（cron `0 * * * *`），通过 Celery Beat 调度
- **写入目标**：更新 `camera_presets.usage_count` / `prompt_presets.usage_count`，并同步 `preset_index.usage_count`
- **前端展示**：预设卡片显示 usage_count 时附带"约 N 次"措辞，不保证实时精确

#### 3.5 前端类型定义

**新建文件**：`frontend/src/types/preset.ts`

```typescript
export type PresetType = 'camera' | 'prompt' | 'style' | 'script' | 'pipeline'

export interface PresetBase {
  id: string
  user_id: string
  name: string
  description?: string
  type: PresetType
  category: string
  tags: string[]
  is_public: boolean
  is_approved: boolean
  usage_count: number
  created_at: string
  updated_at: string
}

export interface CameraPresetData extends PresetBase {
  type: 'camera'
  camera_model?: string
  focal_length?: string
  aperture?: string
  depth_of_field?: string
  shutter_speed?: string
  shutter_angle?: number
  camera_movement?: string
  camera_angle?: string
  aspect_ratio?: string
  visual_style?: string
}

export interface PromptPresetData extends PresetBase {
  type: 'prompt'
  prompt_text: string
}

export type UnifiedPreset = CameraPresetData | PromptPresetData

export interface PresetQueryParams {
  type?: PresetType
  category?: string
  tags?: string[]
  search?: string
  sort?: 'new' | 'hot' | 'usage'
  page?: number
  size?: number
}

export interface PresetExportData {
  version: '1.0'
  type: PresetType
  name: string
  category: string
  tags: string[]
  data: Record<string, unknown>
}
```

---

### 四、API 设计

#### 4.1 统一聚合 API

**新建文件**：`backend/app/routes/presets.py`

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/presets` | 聚合查询，参数 type/category/tags/search/sort/page/size |
| POST | `/api/presets` | 创建预设，body 含 type 和对应字段 |
| PUT | `/api/presets/{id}` | 更新预设 |
| DELETE | `/api/presets/{id}` | 删除预设（检测 Pipeline 引用，弹窗确认后执行，保留 preset_snapshot 兜底） |
| POST | `/api/presets/{id}/submit` | 提交公开审核 |
| POST | `/api/presets/{id}/copy` | 复制（fork）他人的公开预设到我的 |
| GET | `/api/presets/community` | 社区预设库（is_approved=true） |
| POST | `/api/presets/import` | 导入 JSON |
| GET | `/api/presets/{id}/export` | 导出单个预设 JSON |

#### 4.2 聚合查询实现

**新建文件**：`backend/app/services/preset_aggregator.py`

```python
class PresetAggregator:
    """统一聚合查询层：type 为空时走 preset_index，指定 type 时走原表"""

    async def list_presets(self, params: PresetQueryParams) -> PaginatedResult:
        if params.type:
            # 单一类型：直接查询对应原表
            return await self._route_to_service(params)
        else:
            # 全部类型：走 preset_index 轻量索引表
            return await self._list_from_index(params)

    async def create_preset(self, data: dict) -> UnifiedPreset:
        service = self._type_map[data['type']]
        preset = await service.create(data)
        # 同步写入 preset_index
        await self._sync_index(preset)
        return preset

    # update / delete 同理，操作后同步 preset_index
```

#### 4.3 管理员审核 API

**新建文件**：`backend/app/routes/admin_presets.py`

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/admin/presets/pending` | 待审核列表 |
| POST | `/api/admin/presets/{id}/approve` | 审核通过 |
| POST | `/api/admin/presets/{id}/reject` | 驳回（含原因） |

#### 4.4 现有 API 扩展

##### Chat Tool Calling

`chat_service.py` 中消息上下文扩展 `preset_context` 字段，Tool 执行时拼接预设内容：

```python
# 前端发送的消息结构扩展
{
  "message": "...",
  "preset_context": {
    "preset_id": "uuid",
    "preset_snapshot": { "type": "camera", "name": "...", "data": {...} }
  }
}
```

##### Pipeline 步骤

Pipeline 步骤配置增加 `preset_ref` 字段：

```json
{
  "preset_ref": {
    "preset_id": "uuid",
    "preset_type": "prompt",
    "variables": { "frame_index": "auto" }
  }
}
```

执行时 `engine.py` 从 preset_id 加载预设，替换 `{frame_index}` 等变量后拼接到 prompt。

---

### 五、前端组件设计

#### 5.1 组件树

```
views/
├── PresetCenter.vue                    # 预设中心主页面（新建）
└── admin/
    └── PresetAudit.vue                 # 管理员审核页（新建）

components/presets/                     # 预设组件目录（新建）
├── PresetCard.vue                      # 预设卡片（名称/类型标签/使用量/操作菜单）
├── PresetEditorDialog.vue              # 新建/编辑弹窗（根据 type 切换表单）
├── PresetQuickPanel.vue                # 快捷选择面板（Popover）
├── PresetTypeTabs.vue                  # 类型 Tab 切换
├── PresetFilterSidebar.vue             # 分类筛选 + 标签筛选
├── ImportExport.vue                    # 导入/导出按钮 + 对话框
├── CommunityTab.vue                    # 社区预设库 Tab
└── PresetCopyDialog.vue                # 复制（fork）确认弹窗
```

#### 5.2 PresetEditorDialog 表单切换逻辑

```
type=camera  →  CameraPanel（复用 Phase 1 组件）
type=prompt  →  名称 + 分类下拉 + 标签输入 + 文本编辑区
type=style   →  名称 + 分类 + 标签 + 风格编辑（弹窗内嵌或跳转现有编辑页）
type=script  →  名称 + 分类 + 标签 + 弹窗内嵌基本信息编辑
type=pipeline → 名称 + 分类 + 标签 + 跳转 Pipeline 编辑器
```

#### 5.3 PresetQuickPanel 交互

**UI 统一原则**：Phase 1 的 CameraPanel 预设下拉框（PresetSelector.vue）在 Phase 2 上线后被 PresetQuickPanel 统一替换。所有预设选择交互入口（画布节点 / Chat 输入区 / Pipeline 编辑器）均使用同一 PresetQuickPanel 组件。

```
┌──────────────────────┐
│  最近使用              │
│  ┌──────────────────┐│
│  │ 王家卫风格镜头    ││  ← 点击填充摄像机参数
│  │ 🎥 摄像机 · 3次  ││
│  └──────────────────┘│
│  ┌──────────────────┐│
│  │ 赛博朋克夜景      ││  ← 点击填充 prompt 文本
│  │ 📝 提示词 · 5次  ││
│  └──────────────────┘│
│  ... (最多 5 条)     │
│                      │
│  [搜索预设...]        │
│  ────────────────────│
│  📂 前往预设中心      │  ← 链接
└──────────────────────┘
```

#### 5.4 PresetCenter 路由注册

```typescript
// frontend/src/router/index.ts 新增
{
  path: '/presets',
  name: 'PresetCenter',
  component: () => import('@/views/PresetCenter.vue'),
  meta: { requiresAuth: true }
},
{
  path: '/admin/presets',
  name: 'PresetAudit',
  component: () => import('@/views/admin/PresetAudit.vue'),
  meta: { requiresAuth: true, roles: ['admin', 'moderator'] }
}
```

#### 5.5 菜单注册

在管理端菜单配置中新增「预设审核」菜单项。

---

### 六、Chat 集成细节

#### 6.1 前端消息上下文扩展

```typescript
// stores/chat.ts
interface ChatMessageContext {
  preset_context?: {
    preset_id: string
    preset_snapshot: UnifiedPreset  // 当前轮快照
  }
}
```

**关键约束**：`preset_context` 仅当前轮对话有效，不做跨轮持久化。前端在每次发送消息时，将用户当前所选预设的快照数据注入消息体；后端 Tool Calling 执行完成后不持久化该上下文。

#### 6.2 后端 Tool Calling 预设感知

`chat_service.py` 中 Tool 执行前从消息体中提取 preset_context 快照直接使用，无需再次查询数据库：

```python
async def execute_tool_call(tool_name: str, arguments: dict, context: dict):
    preset_ctx = context.get("preset_context")

    if preset_ctx and preset_ctx.get("preset_snapshot"):
        snapshot = preset_ctx["preset_snapshot"]
        if snapshot["type"] == "camera":
            arguments["camera_params"] = camera_service.to_params(snapshot)
        elif snapshot["type"] == "prompt":
            arguments["prompt"] = merge_prompts(arguments.get("prompt", ""), snapshot["data"]["prompt_text"])

    return await tool_executor.execute(tool_name, arguments)
```

#### 6.3 System Prompt 补充

```
如果你发现用户提到了预设名称、或者消息中包含了 preset_context，
请使用预设中配置的提示词和摄像机参数来辅助生成。
```

---

### 七、Pipeline 集成细节

#### 7.1 Pipeline 步骤 preset_ref 结构

```json
{
  "step_type": "image_batch",
  "count": 8,
  "preset_ref": {
    "preset_id": "uuid-xxx",
    "preset_type": "prompt",
    "preset_variables": {
      "frame_index": 0
    }
  }
}
```

#### 7.2 合并优先级：逐帧覆盖 > 预设引用

Pipeline 步骤执行时的 prompt 合并规则：逐帧配置的 `prompt` 字段优先级高于 `preset_ref`。即如果用户在某帧上手动填写了 prompt，直接使用该帧 prompt 忽略预设引用。

#### 7.3 双存兜底（preset_ref + preset_snapshot）

为防止预设被删除后 Pipeline 无法执行，Pipeline 步骤同时存储两份数据：

| 字段 | 说明 |
|---|---|
| `preset_ref` | 预设引用（preset_id + type），执行时实时查询 |
| `preset_snapshot` | 保存时的预设快照，预设被删除后的兜底数据 |

执行逻辑：
1. 优先通过 `preset_ref.preset_id` 查询预设 → 使用最新版本
2. 查询失败（预设已删除）→ 降级使用 `preset_snapshot`
3. 合并时逐帧 prompt 覆盖 `preset_ref`/`preset_snapshot` 的 prompt

#### 7.4 引擎执行时变量替换

`engine.py` 中步骤执行前，支持 Python format spec：

```python
async def _apply_preset_to_step(step: PipelineStep, frame_index: int, frame_count: int):
    if not step.preset_ref and not step.preset_snapshot:
        return step.prompt

    # 优先实时加载，失败则降级快照
    if step.preset_ref:
        preset = await preset_service.get_safe(step.preset_ref["preset_id"])
    else:
        preset = step.preset_snapshot

    prompt = preset.prompt_text or ""

    # 变量替换（仅支持 {frame_index} 和 {frame_count}）
    # 支持 Python format spec，如 {frame_index:04d}、{frame_index:#05d}
    import re
    prompt = re.sub(
        r'\\{frame_index(?::[^}]*)?\\}',
        lambda m: format(frame_index + 1, (m.group(1) or '')[1:]),
        prompt
    )
    prompt = prompt.replace('{frame_count}', str(frame_count))

    return prompt
```

**变量清单**：
| 变量 | 说明 | 示例 |
|---|---|---|
| `{frame_index}` | 当前帧序号（从 1 开始） | 1, 2, 3... |
| `{frame_index:04d}` | 当前帧序号，4 位补零 | 0001, 0002... |
| `{frame_count}` | 总帧数 | 8 |

#### 7.5 预设删除时的 Pipeline 保护

删除预设时检测所有 Pipeline 步骤的 `preset_ref`，若存在引用则弹窗警告"该预设被 N 个 Pipeline 步骤引用，删除后将使用快照数据兜底"。用户确认后删除，Pipeline 步骤的 `preset_ref` 置 null，`preset_snapshot` 保留。

---

### 八、公开审核流程

```
┌─────────┐    ┌─────────────┐    ┌──────────┐
│  用户    │    │  管理员      │    │  社区库   │
└────┬────┘    └──────┬──────┘    └────┬─────┘
     │                │                │
     │ 提交公开申请    │                │
     │───────────────>│                │
     │                │                │
     │                │ 审核通过       │
     │                │───────────────>│
     │                │ is_approved=   │
     │                │ true           │
     │                │                │
     │   驳回（附原因） │                │
     │<───────────────│                │
     │                │                │
     │ 修改后重新提交  │                │
     │───────────────>│                │
```

**管理端审核页**：列表展示预设名称、类型、提交人、提交时间，支持预览预设内容，通过/驳回操作。

---

### 九、导入/导出格式

#### 9.1 导出格式（JSON）

```json
{
  "version": "1.0",
  "exported_at": "2026-06-27T12:00:00Z",
  "presets": [
    {
      "version": "1.0",
      "type": "camera",
      "name": "王家卫风格镜头",
      "description": "适用于人像特写的经典王家卫风格",
      "category": "人像",
      "tags": ["王家卫", "电影感", "暖色调"],
      "data": {
        "camera_model": "ARRI Alexa",
        "focal_length": "50mm",
        "aperture": "f/2.0",
        "depth_of_field": "浅",
        "shutter_speed": "1/60",
        "camera_movement": "手持晃动",
        "camera_angle": "平视",
        "aspect_ratio": "2.35:1",
        "visual_style": "暖色调，胶片颗粒，柔光"
      }
    },
    {
      "version": "1.0",
      "type": "prompt",
      "name": "赛博朋克城市夜景",
      "category": "场景",
      "tags": ["赛博朋克", "夜景", "霓虹灯"],
      "data": {
        "prompt_text": "cyberpunk city at night, neon lights, rain-slicked streets, volumetric fog, 8k, photorealistic"
      }
    }
  ]
}
```

#### 9.2 导入流程与冲突处理

1. 前端拖拽/选择 `.json` 文件
2. 前端解析 JSON，校验 `version`、`type`、`name` 必填
3. 调用 `POST /api/presets/import`，传入预设数组
4. 后端逐条创建，返回成功/失败汇总
5. 前端展示导入结果（成功 N 条，失败 M 条 + 失败原因）

**导入冲突处理规则**：

| 场景 | 处理方式 |
|---|---|
| 同名预设 | 自动重命名（追加 " (2)"、" (3)" 等后缀） |
| 未知 category | 自动降级为 `"通用"` |
| 未知 tags | 自动创建新标签入库（不做拦截） |
| 单条数据错误 | 跳过该条继续导入下一条，不影响其他预设 |
| is_approved | 强制设为 `false`（导入的预设不自动通过审核） |

**AI 自动分类**（同时适用于创建和导入）：

创建或导入预设后，后端异步调用 LLM 一次，分析预设名称 + 描述 + 实际参数/文本内容，自动建议 `type`（仅 prompt/camera 新建时适用）、`category`（枚举值之一）和 `tags`（最多 5 个）。前端在保存预设后展示 AI 建议，用户确认或修改后最终入库。

---

### 十、开发步骤与排期

#### Phase 2-A：通用提示词预设基础（3-4 天）

| 步骤 | 内容 | 涉及文件 |
|---|---|---|
| 1 | 创建 prompt_presets 表 + Model | `models/prompt_preset.py`（新建），迁移脚本 |
| 2 | 实现 PromptPreset CRUD Service + Route | `services/prompt_preset_service.py`（新建），`routes/prompt_presets.py`（新建） |
| 3 | 前端类型定义 + API 封装 | `types/preset.ts`（新建），`api/presets.ts`（新建） |
| 4 | 前端 Pinia store | `stores/presets.ts`（新建） |
| 5 | 预设 Editor 表单（prompt 类型） + 列表页 MVP | `PresetEditorDialog.vue`，`PresetCenter.vue`（MVP） |

#### Phase 2-B：预设中心页面 + 快捷面板（3-4 天）

| 步骤 | 内容 | 涉及文件 |
|---|---|---|
| 1 | PresetCenter 完整页面（布局 + Tab + 搜索 + 排序） | `views/PresetCenter.vue` |
| 2 | PresetCard 卡片组件 + 操作菜单 | `components/presets/PresetCard.vue` |
| 3 | PresetEditorDialog 完善（camera 类型表单切换） | `components/presets/PresetEditorDialog.vue` |
| 4 | 分类筛选侧边栏 + 标签筛选 | `components/presets/PresetFilterSidebar.vue` |
| 5 | PresetQuickPanel 快捷面板 | `components/presets/PresetQuickPanel.vue` |
| 6 | 画布节点集成快捷面板 | `components/canvas/CanvasNode.vue` 改造 |
| 7 | Chat 输入区集成快捷面板 | `components/chat/ChatInput.vue` 改造 |
| 8 | 路由注册 + 菜单注册 | `router/index.ts` |

#### Phase 2-C：统一聚合 + CameraPreset 重建 + 审核（3-4 天）

| 步骤 | 内容 | 涉及文件 |
|---|---|---|
| 1 | CameraPreset 迁移脚本（数据补齐而非重建） | 数据库迁移脚本 |
| 2 | 统一聚合 API `/api/presets` | `routes/presets.py`（新建），`services/preset_aggregator.py`（新建） |
| 3 | CameraPreset CRUD 适配聚合 API | `services/camera_preset_service.py` 改造 |
| 4 | 公开申请 + 审核 API | `routes/presets.py` 扩展，`routes/admin_presets.py`（新建） |
| 5 | 管理员审核页面 | `views/admin/PresetAudit.vue`（新建） |
| 6 | 导入/导出接口 + 前端交互 | `routes/presets.py` 扩展，`components/presets/ImportExport.vue` |

#### Phase 2-D：现有类型迁移 + 社区库 + 联调（3-4 天）

| 步骤 | 内容 | 涉及文件 |
|---|---|---|
| 1 | StylePreset 纳入聚合 API（虚拟映射，不改表） | `routes/presets.py` 扩展 |
| 2 | ScriptTemplate 纳入聚合 API | `routes/presets.py` 扩展 |
| 3 | PipelineTemplate 纳入聚合 API | `routes/presets.py` 扩展 |
| 4 | 社区预设库 Tab + 复制（fork）功能 | `views/PresetCenter.vue` 扩展，`CommunityTab.vue` |
| 5 | Pipeline 编辑器集成预设选择 + 变量替换 | `components/pipeline/` 改造，`engine.py` 改造 |
| 6 | Chat Tool Calling 预设感知 | `services/chat_service.py`，`stores/chat.ts` |
| 7 | 全链路联调测试 | — |

**总计预计：12-16 天**

---

### 十一、文件变更清单

#### 新建文件

| 层次 | 文件 | 说明 |
|---|---|---|
| 后端 Model | `backend/app/models/prompt_preset.py` | PromptPreset ORM |
| 后端 Service | `backend/app/services/prompt_preset_service.py` | 预设 CRUD |
| 后端 Service | `backend/app/services/preset_aggregator.py` | 聚合查询层 |
| 后端 Route | `backend/app/routes/presets.py` | 统一预设 API |
| 后端 Route | `backend/app/routes/admin_presets.py` | 管理员审核 API |
| 前端 Type | `frontend/src/types/preset.ts` | 预设类型定义 |
| 前端 API | `frontend/src/api/presets.ts` | 预设 API 封装 |
| 前端 Store | `frontend/src/stores/presets.ts` | 预设状态管理 |
| 前端 View | `frontend/src/views/PresetCenter.vue` | 预设中心主页 |
| 前端 View | `frontend/src/views/admin/PresetAudit.vue` | 管理员审核页 |
| 前端 Component | `frontend/src/components/presets/PresetCard.vue` | 预设卡片 |
| 前端 Component | `frontend/src/components/presets/PresetEditorDialog.vue` | 新建/编辑弹窗 |
| 前端 Component | `frontend/src/components/presets/PresetQuickPanel.vue` | 快捷选择面板 |
| 前端 Component | `frontend/src/components/presets/PresetFilterSidebar.vue` | 分类标签筛选 |
| 前端 Component | `frontend/src/components/presets/CommunityTab.vue` | 社区预设库 |
| 前端 Component | `frontend/src/components/presets/ImportExport.vue` | 导入导出 |

#### 改造文件

| 文件 | 变更说明 |
|---|---|
| `backend/app/models/camera_preset.py` | 已在 Phase 1 预建完成，Phase 2 无需改造 |
| `backend/app/services/camera_preset_service.py` | 适配统一聚合 API + preset_index 同步 |
| `backend/app/routes/camera_presets.py` | 保留原有 CRUD 端点，聚合 API 内部调用（不必删除，Phase 1 端点继续可用） |
| `backend/app/services/chat_service.py` | Tool Calling 预设感知 + system prompt 扩展 |
| `backend/app/services/pipeline/engine.py` | Pipeline 步骤 preset_ref 加载 + 变量替换 |
| `backend/app/schemas/pipeline.py` | 步骤 schema 扩展 preset_ref |
| `frontend/src/router/index.ts` | 新增预设中心路由 |
| `frontend/src/components/canvas/CanvasNode.vue` | 集成快捷面板 |
| `frontend/src/components/chat/ChatInput.vue` | 集成快捷面板 |
| `frontend/src/stores/canvas.ts` | 快捷面板状态 |
| `frontend/src/stores/chat.ts` | 预设上下文透传 |
| `frontend/src/components/pipeline/ImageBatchStep.vue` | 预设选择 + 变量编辑 |
| `frontend/src/components/pipeline/VideoBatchStep.vue` | 预设选择 + 变量编辑 |
