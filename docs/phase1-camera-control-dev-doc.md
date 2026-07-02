# Agnes Platform VNext 第一阶段开发文档

## 摄像机控制 Prompt 注入

---

### 一、需求概述

#### 1.1 背景

借鉴 Open Storyboard Canvas 的摄像机控制体系，在 Agnes Platform 的图片/视频生成流程中引入专业摄像机参数描述能力。用户在生成时可通过开关启用摄像机参数面板，选择或自定义摄像机配置，系统自动将参数以自然语言形式注入 prompt，提升生成画面与分镜意图的匹配度。

#### 1.2 核心目标

- 覆盖完整专业级摄像机参数体系（对标 OSC）
- 三个生成入口全部支持：画布节点、AI Chat（Tool Calling）、Creative Pipeline
- 支持摄像机预设方案的保存与复用
- Pipeline 支持帧级差异参数（逐图/逐视频可不同）
- 默认关闭，对现有用户零侵入

#### 1.3 关键决策回顾

| 决策项 | 结论 |
|---|---|
| 参数范围 | 完整专业级（对标 OSC） |
| 注入入口 | 全部覆盖（画布 + Chat + Pipeline） |
| 交互形态 | 独立开关控制（默认关闭） |
| Pipeline 策略 | 帧级差异参数（逐图/逐视频可不同） |
| 预设存储 | CameraPreset 表按 Phase 2 最终结构预建（含 type/category/tags/is_approved），Phase 2 零迁移 |
| Prompt 格式 | 自然语言描述追加到 prompt 末尾 |

---

### 二、功能规格

#### 2.1 摄像机参数体系

##### 2.1.1 参数定义

| 参数组 | 参数名 | 字段名 | 类型 | 可选范围/说明 |
|---|---|---|---|---|
| 机身 | 相机型号 | camera_model | string | 例：Sony FX3 / ARRI Alexa Mini / RED Komodo / Blackmagic Ursa |
| 镜头 | 焦距 | focal_length | string | 例：24mm / 35mm / 50mm / 85mm / 135mm / 变焦 |
| 镜头 | 光圈 | aperture | string | 例：f/1.4 / f/2.0 / f/2.8 / f/4 / f/5.6 / f/8 / f/11 / f/16 |
| 镜头 | 景深 | depth_of_field | string | 极浅 / 浅 / 中等 / 深 |
| 曝光 | 快门速度 | shutter_speed | string | 例：1/30 / 1/60 / 1/125 / 1/250 / 1/500 / 1/1000 |
| 曝光 | 快门角度 | shutter_angle | number | 例：180° / 90° / 45° / 360° |
| 运动 | 运镜方式 | camera_movement | string | 固定 / 推 / 拉 / 摇 / 移 / 跟 / 升 / 降 / 手持晃动 |
| 构图 | 视角 | camera_angle | string | 平视 / 俯视 / 仰视 / 鸟瞰 / 虫眼视角 / 荷兰角 |
| 构图 | 画幅比例 | aspect_ratio | string | 1:1 / 4:3 / 3:2 / 16:9 / 2.35:1 / 21:9 |
| 画质 | 画面风格 | visual_style | string | 例：暖色调 / 冷色调 / 高对比度 / 低饱和 / 胶片颗粒 / 柔光 |

##### 2.1.2 Prompt 拼接规则

摄像机参数以自然语言描述追加到用户原始 prompt 末尾，格式如下：

```
{原始prompt}。摄像机采用{camera_model}，{focal_length}焦段，光圈{aperture}，{depth_of_field}景深，快门{shutter_speed}。运镜采用{camera_movement}方式，{camera_angle}视角，画幅{aspect_ratio}。
```

**示例**：

> 一个女孩在雨中奔跑。摄像机采用 Sony FX3，85mm 焦段，光圈 f/2.8，浅景深，快门 1/500。运镜采用跟方式，平视视角，画幅 16:9。

**仅拼接用户实际填写的字段**。未填写的字段不出现在最终 prompt 中。

#### 2.2 各入口行为规格

##### 2.2.1 画布节点入口

**位置**：画布图片节点的生成参数区域

**交互流程**：
1. 生成参数区底部新增「摄像机控制」开关（Toggle），默认关闭
2. 开启后展开摄像机参数面板（内嵌或侧滑）
3. 面板顶部提供预设选择下拉框（「无预设」+ 已保存的预设列表）
4. 选择预设后自动填充各参数，用户可覆盖修改
5. 用户也可不选预设，直接手动填写参数
6. 点击「生成」时，系统拼接完整 prompt 并发起请求

**涉及文件**：
- `frontend/src/components/canvas/CanvasNode.vue` — 节点内面板嵌入
- `frontend/src/components/camera/CameraPanel.vue` — 新建独立组件
- `frontend/src/stores/canvas.ts` — 节点数据模型扩展

##### 2.2.2 AI Chat 入口

**位置**：聊天输入区域附近或对话消息内的生成参数区

**交互流程**：
1. 输入框上方或侧边新增「摄像机控制」开关
2. 开启后展开参数面板
3. 用户配置参数后发起对话
4. 当模型调用 `generate_image` / `generate_video` Tool 时，摄像机参数作为 tool arguments 的扩展字段传入
5. 后端在 `chat_service.py` 的 Tool Calling 处理逻辑中提取参数并拼接 prompt

**涉及文件**：
- `frontend/src/components/chat/ChatInput.vue` — 输入区集成
- `frontend/src/stores/chat.ts` — 消息上下文扩展
- `backend/app/services/chat_service.py` — Tool Calling 参数扩展

##### 2.2.3 Pipeline 入口

**位置**：Pipeline 编辑器中图片步骤 / 视频步骤的配置面板

**交互流程**：
1. 图片批量步骤 / 视频批量步骤的配置面板新增「摄像机控制」开关
2. 开启后，面板展示 N 组摄像机参数（N = 生成数量），每组可独立配置
3. 提供「应用到全部」批量填充快捷操作
4. 参数随步骤配置一起保存到 PipelineTemplate
5. 执行时引擎按索引将每组参数拼接到对应帧的 prompt

**涉及文件**：
- `frontend/src/components/pipeline/ImageBatchStep.vue` — 图片步骤配置
- `frontend/src/components/pipeline/VideoBatchStep.vue` — 视频步骤配置
- `frontend/src/stores/pipeline.ts` — 步骤数据模型扩展
- `backend/app/services/pipeline/engine.py` — 执行时参数注入
- `backend/app/models/pipeline.py` — PipelineStep 数据模型扩展

#### 2.3 摄像机预设管理

##### 2.3.1 预设数据结构

```python
class CameraPreset:
    id: UUID
    user_id: UUID  # 创建者
    name: str  # 预设名称，如「王家卫风格镜头」
    description: str | None  # 描述
    # 统一分类字段（Phase 2 兼容预埋）
    type: str  # 固定值 "camera"
    category: str  # 大类，默认 "通用"
    tags: list[str]  # 自由标签，AI 自动打标
    # 摄像机参数
    camera_model: str | None
    focal_length: str | None
    aperture: str | None
    depth_of_field: str | None
    shutter_speed: str | None
    shutter_angle: int | None
    camera_movement: str | None
    camera_angle: str | None
    aspect_ratio: str | None
    visual_style: str | None
    # 元数据
    is_public: bool  # 是否公开
    is_approved: bool  # 管理员审核状态（默认 false）
    usage_count: int  # 使用次数（异步统计）
    created_at: datetime
    updated_at: datetime
```

##### 2.3.2 预设管理功能

| 功能 | 说明 |
|---|---|
| 创建预设 | 在摄像机面板中将当前参数保存为新预设 |
| 编辑预设 | 修改已有预设的名称和参数 |
| 删除预设 | 删除自己的预设 |
| 列表查询 | 查询自己的预设 + 公开预设 |
| 应用预设 | 选择预设后自动填充参数面板 |
| 导入/导出 | JSON 格式导出预设文件，支持分享（V2） |

**Phase 2 兼容性**：CameraPreset 表已预埋 type/category/tags/is_approved 字段，Phase 2 上线后直接纳入统一预设聚合 API（`/api/presets?type=camera`），无需迁移。

---

### 三、数据结构设计

#### 3.1 数据库变更

##### 3.1.1 新建表：`camera_presets`

```sql
CREATE TABLE camera_presets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    -- 统一分类字段（Phase 2 兼容预埋）
    type VARCHAR(50) NOT NULL DEFAULT 'camera',
    category VARCHAR(50) DEFAULT '通用',
    tags TEXT[] DEFAULT '{}',  -- PostgreSQL 数组
    -- 摄像机参数
    camera_model VARCHAR(100),
    focal_length VARCHAR(50),
    aperture VARCHAR(20),
    depth_of_field VARCHAR(50),
    shutter_speed VARCHAR(20),
    shutter_angle INTEGER,
    camera_movement VARCHAR(100),
    camera_angle VARCHAR(100),
    aspect_ratio VARCHAR(20),
    visual_style VARCHAR(200),
    is_public BOOLEAN DEFAULT FALSE,
    is_approved BOOLEAN DEFAULT FALSE,
    usage_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_camera_presets_user ON camera_presets(user_id);
CREATE INDEX idx_camera_presets_public ON camera_presets(is_public);
CREATE INDEX idx_camera_presets_type ON camera_presets(type);
CREATE INDEX idx_camera_presets_category ON camera_presets(category);
```

##### 3.1.2 Pipeline 步骤扩展

`pipeline_steps` 表增加 JSON 字段 `camera_params`：

```sql
ALTER TABLE pipeline_steps ADD COLUMN camera_params JSONB DEFAULT NULL;
```

字段值结构：
```json
{
  "enabled": true,
  "frames": [
    {
      "index": 0,
      "camera_model": "Sony FX3",
      "focal_length": "85mm",
      "aperture": "f/2.8",
      "depth_of_field": "浅",
      "shutter_speed": "1/500",
      "camera_movement": "跟",
      "camera_angle": "平视",
      "aspect_ratio": "16:9",
      "visual_style": "冷色调"
    },
    {
      "index": 1,
      "camera_model": "ARRI Alexa",
      "focal_length": "35mm",
      "aperture": "f/5.6",
      "depth_of_field": "中等",
      "shutter_speed": "1/250",
      "camera_movement": "推",
      "camera_angle": "仰视",
      "aspect_ratio": "2.35:1",
      "visual_style": "高对比度"
    }
  ]
}
```

#### 3.2 后端 Model

**新建文件**：`backend/app/models/camera_preset.py`

```python
from sqlalchemy import Column, String, Integer, Boolean, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base
import uuid

class CameraPreset(Base):
    __tablename__ = "camera_presets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    camera_model = Column(String(100), nullable=True)
    focal_length = Column(String(50), nullable=True)
    aperture = Column(String(20), nullable=True)
    depth_of_field = Column(String(50), nullable=True)
    shutter_speed = Column(String(20), nullable=True)
    shutter_angle = Column(Integer, nullable=True)
    camera_movement = Column(String(100), nullable=True)
    camera_angle = Column(String(100), nullable=True)
    aspect_ratio = Column(String(20), nullable=True)
    visual_style = Column(String(200), nullable=True)
    is_public = Column(Boolean, default=False)
```

#### 3.3 前端类型定义

**新建文件**：`frontend/src/types/camera.ts`

```typescript
export interface CameraParams {
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

export interface CameraPreset extends CameraParams {
  id: string
  user_id: string
  name: string
  description?: string
  is_public: boolean
  created_at: string
  updated_at: string
}

export interface PipelineCameraConfig {
  enabled: boolean
  frames: Array<{ index: number } & CameraParams>
}
```

---

### 四、API 设计

#### 4.1 摄像机预设 CRUD

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/camera-presets` | 查询预设列表（自己的 + 公开的） |
| POST | `/api/camera-presets` | 创建预设 |
| PUT | `/api/camera-presets/{id}` | 更新预设 |
| DELETE | `/api/camera-presets/{id}` | 删除预设 |

**新建文件**：`backend/app/routes/camera_presets.py`
**新建文件**：`backend/app/services/camera_preset_service.py`

**创建/更新字段规则**：
- `type`：服务端自动设为 `"camera"`，不接受前端传参
- `category`：默认 `"通用"`，用户可选改
- `tags`：默认空数组 `[]`，用户自由填写
- `is_approved`：管理员字段，创建时强制 `false`，不在普通用户可见 schema 中
- `usage_count`：默认 `0`，异步定时任务统计更新

#### 4.2 现有 API 扩展

##### 4.2.1 图片生成

`POST /api/images/generate` 请求体新增可选字段：

```json
{
  "camera_params": {
    "enabled": true,
    "camera_model": "Sony FX3",
    "focal_length": "85mm",
    "aperture": "f/2.8"
  }
}
```

##### 4.2.2 视频生成

`POST /api/videos/generate` 请求体新增可选字段（同上结构）。

##### 4.2.3 Chat Tool Calling 扩展

`generate_image` 和 `generate_video` tool 的 parameters schema 新增 `camera_params` 字段。

**修改文件**：`backend/app/services/chat_service.py` 中 tool 定义部分。

##### 4.2.4 Pipeline 步骤配置

`POST/PUT /api/pipelines/templates` 的步骤配置中 `camera_params` 字段。

**修改文件**：`backend/app/schemas/pipeline.py`

---

### 五、前端组件设计

#### 5.1 组件树

```
CameraPanel.vue                         # 摄像机参数面板（独立组件，三个入口复用）
├── CameraToggle.vue                    # 开关按钮
├── PresetSelector.vue                  # 预设选择下拉框
│   ├── PresetSaveDialog.vue            # 保存预设对话框
│   └── PresetManageDialog.vue          # 管理预设对话框
├── ParamForm.vue                       # 参数表单
│   ├── CameraModelSelector.vue         # 相机型号选择（含常用型号列表）
│   ├── FocalLengthSelector.vue         # 焦距选择（预设值 + 自定义）
│   ├── ApertureSelector.vue            # 光圈选择
│   ├── DepthOfFieldSelector.vue        # 景深选择
│   ├── ShutterSpeedSelector.vue        # 快门速度选择
│   ├── ShutterAngleSelector.vue        # 快门角度滑块
│   ├── MovementSelector.vue            # 运镜方式选择
│   ├── AngleSelector.vue               # 视角选择
│   ├── AspectRatioSelector.vue         # 画幅比例选择
│   └── VisualStyleSelector.vue         # 画面风格选择（多选标签）
└── PromptPreview.vue                   # Prompt 预览（实时显示拼接结果）
```

**Canvas 入口**：
```
CanvasNode.vue（图片节点）
└── GeneratePanel.vue
    └── CameraPanel.vue（嵌入式）
```

**Chat 入口**：
```
ChatInput.vue
└── CameraPanel.vue（侧滑/弹出式）
```

**Pipeline 入口**：
```
ImageBatchStep.vue / VideoBatchStep.vue
├── StepConfigPanel.vue
│   └── CameraPanel.vue（帧级参数列）
└── FrameCameraEditor.vue # 逐帧编辑
```

#### 5.2 CameraPanel 核心状态

```typescript
// 使用 Pinia store 管理面板状态
const useCameraStore = defineStore('camera', () => {
  const enabled = ref(false)           // 开关状态
  const params = ref<CameraParams>({}) // 当前参数
  const presets = ref<CameraPreset[]>([]) // 预设列表
  const activePresetId = ref<string | null>(null)

  const promptSuffix = computed(() => {
    // 根据 params 拼接自然语言描述
    return buildCameraPrompt(params.value)
  })

  function toggle(enabled: boolean) { ... }
  function setParams(p: CameraParams) { ... }
  function applyPreset(preset: CameraPreset) { ... }
  function saveAsPreset(name: string) { ... }
  function resetParams() { ... }
})
```

#### 5.3 关键交互细节

| 场景 | 行为 |
|---|---|
| 开关关闭 → 开启 | 展开面板，保留上次配置的参数 |
| 选择预设 | 覆盖当前参数（确认提示：是否覆盖当前填写内容） |
| 修改参数（已有预设选中） | 预设选中状态置空，提示「已偏离预设」 |
| 保存预设 | 弹出命名对话框，将当前参数保存为预设 |
| 首次打开（无任何配置） | 所有参数为空，预设列表加载默认空状态 |
| Prompt 预览 | 面板底部实时显示拼接后的摄像机描述文本 |

---

### 六、Prompt 拼接逻辑

#### 6.1 后端统一处理

**新建/扩展函数**：在 `backend/app/services/agnes_client.py` 或新建 `backend/app/services/camera_prompt.py`：

```python
def build_camera_prompt_suffix(camera_params: dict | None) -> str:
    """将摄像机参数转为自然语言描述，追加到 prompt 末尾"""
    if not camera_params or not camera_params.get("enabled"):
        return ""

    parts = []
    mapping = {
        "camera_model": "摄像机采用{}",
        "focal_length": "{}焦段",
        "aperture": "光圈{}",
        "depth_of_field": "{}景深",
        "shutter_speed": "快门{}",
        "shutter_angle": "快门角度{}°",
        "camera_movement": "运镜采用{}方式",
        "camera_angle": "{}视角",
        "aspect_ratio": "画幅{}",
        "visual_style": "{}画面风格",
    }

    for key, template in mapping.items():
        value = camera_params.get(key)
        if value:
            parts.append(template.format(value))

    if parts:
        return "。" + "，".join(parts) + "。"

    return ""
```

#### 6.2 拼接位置

| 入口 | 拼接时机 |
|---|---|
| 画布节点 | 后端 `images.py` / `videos.py` 路由中，调用 agnes_client 前拼接 |
| Chat Tool Calling | `chat_service.py` 中 tool 执行时，获取参数后拼接 |
| Pipeline | `pipeline/engine.py` 中步骤执行前，按帧索引取对应参数拼接 |

---

### 七、Chat Tool Calling 集成方案

#### 7.1 Tool 定义扩展

在 `chat_service.py` 的 `generate_image` 和 `generate_video` tool 定义中，增加 `camera_params` 可选参数。

模型通过 system prompt 引导（新增约 2-3 句），告知当用户表达了摄像机/镜头/运镜相关意图时，将参数填入 `camera_params`：

```
如果用户提到了摄像机、镜头、焦距、光圈、运镜方式等拍摄相关描述，
请提取并填入 camera_params 参数，字段均为可选。
```

#### 7.2 用户侧触发方式

用户在 Chat 中开启摄像机面板并配置参数后，与当前对话上下文一起发送。两种模式：

| 模式 | 行为 |
|---|---|
| 面板已配置参数 | 参数直接作为 `camera_params` 注入到本轮 tool call 参数中（前端直传） |
| 用户自然语言描述摄像机 | 模型从对话中提取参数填入 `camera_params` |

---

### 八、开发步骤与排期

#### Phase 1-A：后端基础设施（预计 3-4 天）

| 步骤 | 内容 | 涉及文件 |
|---|---|---|
| 1 | 创建 CameraPreset 数据模型 + 数据库迁移 | `models/camera_preset.py`，迁移脚本 |
| 2 | 实现 preset CRUD Service + Route | `services/camera_preset_service.py`，`routes/camera_presets.py` |
| 3 | 实现 `build_camera_prompt_suffix` 拼接函数 | `services/camera_prompt.py`（新建） |
| 4 | 扩展图片生成 API 支持 `camera_params` | `routes/images.py`，`schemas/images.py` |
| 5 | 扩展视频生成 API 支持 `camera_params` | `routes/videos.py`，`schemas/videos.py` |
| 6 | 扩展 Pipeline 步骤 schema 支持 `camera_params` | `schemas/pipeline.py`，`models/pipeline.py` |
| 7 | Pipeline 引擎注入摄像机参数逻辑 | `services/pipeline/engine.py` |

#### Phase 1-B：前端组件开发（预计 5-6 天）

| 步骤 | 内容 | 涉及文件 |
|---|---|---|
| 1 | 创建前端类型定义 | `types/camera.ts` |
| 2 | 实现 CameraPanel 基础组件 + 所有子组件 | `components/camera/` 目录（新建） |
| 3 | 实现 useCameraStore | `stores/camera.ts` |
| 4 | 实现预设管理 API 封装 | `api/cameraPresets.ts` |
| 5 | 画布节点集成 CameraPanel | `components/canvas/CanvasNode.vue` 改造 |
| 6 | Chat 输入区集成 CameraPanel | `components/chat/ChatInput.vue` 改造 |
| 7 | Pipeline 步骤编辑器集成帧级摄像机编辑 | `components/pipeline/ImageBatchStep.vue`，`VideoBatchStep.vue` |

#### Phase 1-C：Chat Tool Calling 集成（预计 2-3 天）

| 步骤 | 内容 | 涉及文件 |
|---|---|---|
| 1 | Tool 定义扩展 camera_params 参数 | `services/chat_service.py` |
| 2 | System prompt 补充摄像机参数提取引导 | `services/chat_service.py` |
| 3 | Tool 执行时拼接摄像机 prompt | `services/chat_service.py` |
| 4 | 前端 Chat 摄像机参数透传逻辑 | `stores/chat.ts`，`api/chat.ts` |

#### Phase 1-D：联调测试（预计 2-3 天）

| 步骤 | 内容 |
|---|---|
| 1 | 画布节点: 开启摄像机 → 配置参数 → 生成 → 验证 prompt 拼接正确 |
| 2 | Chat: 开启摄像机 → 对话 → 模型调用 tool → 验证参数透传正确 |
| 3 | Pipeline: 配置帧级参数 → 执行 → 验证每帧 prompt 拼接正确 |
| 4 | 预设: 创建 / 应用 / 编辑 / 删除 → 验证全流程 |
| 5 | 边界: 空参数 / 全参数 / 部分参数 / 开关关闭 / 无预设 |

**总计预计：12-16 天**

---

### 九、第二阶段预告：提示词预设系统

Phase 2 将在第一阶段 CameraPreset 的基础上建立统一提示词预设体系：

- 将 CameraPreset 与通用 PromptPreset 纳入统一管理入口
- 支持分类标签（摄像机 / 角色 / 风格 / 场景 / 构图）
- 预设广场（公开共享）
- 一键应用到画布节点 / Chat / Pipeline

---

### 附录 A：文件变更清单

#### 新建文件

| 文件 | 说明 |
|---|---|
| `backend/app/models/camera_preset.py` | CameraPreset ORM 模型 |
| `backend/app/services/camera_preset_service.py` | 预设 CRUD 服务 |
| `backend/app/services/camera_prompt.py` | Prompt 拼接函数 |
| `backend/app/routes/camera_presets.py` | 预设 API 路由 |
| `frontend/src/types/camera.ts` | 前端类型定义 |
| `frontend/src/api/cameraPresets.ts` | 预设 API 封装 |
| `frontend/src/stores/camera.ts` | 摄像机参数 Pinia Store |
| `frontend/src/components/camera/CameraPanel.vue` | 摄像机面板主组件 |
| `frontend/src/components/camera/PresetSelector.vue` | 预设选择器 |
| `frontend/src/components/camera/ParamForm.vue` | 参数表单 |
| `frontend/src/components/camera/PromptPreview.vue` | Prompt 实时预览 |
| `frontend/src/components/camera/PresetManageDialog.vue` | 预设管理对话框 |

#### 修改文件

| 文件 | 变更说明 |
|---|---|
| `backend/app/routes/images.py` | 支持 camera_params |
| `backend/app/routes/videos.py` | 支持 camera_params |
| `backend/app/schemas/images.py` | 扩展请求 schema |
| `backend/app/schemas/videos.py` | 扩展请求 schema |
| `backend/app/schemas/pipeline.py` | 扩展步骤 schema |
| `backend/app/models/pipeline.py` | PipelineStep 增加 camera_params JSON 字段 |
| `backend/app/services/chat_service.py` | Tool 定义扩展 + system prompt 补充 |
| `backend/app/services/pipeline/engine.py` | 步骤执行时参数注入 |
| `frontend/src/components/canvas/CanvasNode.vue` | 集成 CameraPanel |
| `frontend/src/components/chat/ChatInput.vue` | 集成 CameraPanel |
| `frontend/src/components/pipeline/ImageBatchStep.vue` | 帧级摄像机编辑器 |
| `frontend/src/components/pipeline/VideoBatchStep.vue` | 帧级摄像机编辑器 |
| `frontend/src/stores/canvas.ts` | 节点数据模型扩展 |
| `frontend/src/stores/chat.ts` | 消息上下文扩展 |
| `frontend/src/stores/pipeline.ts` | 步骤数据模型扩展 |
