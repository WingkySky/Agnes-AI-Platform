# 创意工坊与无限画布修订设计

- 日期：2026-06-28
- 范围：创意工坊模板编辑器简化、模板导入格式补全、画布→工坊模板转换修复、无限画布固化配音/字幕/视频拼接能力
- 关联代码：
  - 后端：`backend/app/services/pipeline/steps/`、`backend/app/routes/pipeline.py`、`backend/app/services/pipeline/run_service.py`、`backend/app/services/pipeline/template_service.py`
  - 前端：`frontend/src/views/TemplateWizardView.vue`、`frontend/src/views/PipelineRunView.vue`、`frontend/src/components/pipeline/TemplateImportExportDialog.vue`、`frontend/src/components/canvas/SaveAsWorkshopTemplateDialog.vue`、`frontend/src/components/canvas/*`、`frontend/src/stores/canvas.ts`、`frontend/src/types/index.ts`

## 1. 问题陈述

当前创意工坊与无限画布存在四类问题：

1. **模板编辑器过度参数化**：模板编辑页（`TemplateWizardView.vue` 等）暴露 `output_mapping` JSON、`estimated_credits/time` 手填、`inputs_config` 原始字段（key/label/type/required）、`depends_on` 概念等开发者级配置。普通用户做"加流程/删流程/流程排序"时被这些参数淹没。
2. **导入格式无模版**：导入对话框只接 `.json`，用户不知道字段长什么样，没有示例文件可下载，自己写不出来。`step.type` 校验也不严格，错误的 type 会静默创建、运行时才报错。
3. **画布→工坊模板转换后无法运行**：`SaveAsWorkshopTemplateDialog.vue` 的 `NODE_TYPE_TO_STEP_TYPE` 映射错误（`image_gen`/`video_gen`/`audio_gen`/`composite` 在后端均无对应执行器），`buildStepConfig` 产出的字段名与执行器期望不符，`ffmpeg_composite` 的 `from_step`/`audio_from_step` 未正确指向上游 step.key，`inputs_config` 只生成 `prompt` 字段而 `llm_generate` 的提示词模板通常引用 `{{theme}}`。结果：保存的模板启动即报"未知步骤类型"或"缺少上游"。
4. **画布缺少配音/字幕/视频拼接固化能力**：画布只有 `text/image/video/audio/config` 五种节点，`audio` 节点只是放音频文件不做 TTS，`config` 节点不做 ffmpeg 合成，字幕没有独立节点。工坊已有 `tts_generate`/`ffmpeg_composite` 执行器，但画布无法可视化地编排这两类步骤。

## 2. 目标

- 模板编辑器只暴露"加流程/删流程/排序/改提示词"四件事，参数折叠在"展开高级"里，普通用户开箱即用。
- 任何用户都能拿到一份官方示例文件并照着做出可导入的模板 JSON。
- 画布"保存为工坊模板"产出的模板可直接运行，无需用户手动修配置。
- 画布原生支持配音、字幕、成片合成三类节点，与工坊预设步骤库视觉和语义一致。

## 3. 非目标

- 不重构工坊运行引擎本身（`run_service.py` 的执行模型保持不变）。
- 不新增 step 执行器类型（仍只支持 `llm_generate`/`image_batch`/`video_batch`/`tts_generate`/`ffmpeg_composite` 五种）。
- 不改后端模板表结构。
- 不做模板版本迁移（项目未上线，旧模板按新规则直接改）。
- 不做画布节点直接执行（画布节点仍通过"转工坊模板 → 工坊运行"路径执行，不在画布内直接调用执行器）。

## 4. 后端 step_type 权威清单

本设计的所有转换、校验、UI 命名都以这张表为准。来源：`backend/app/services/pipeline/steps/`。

| step_type | 执行器文件 | 输入要求 | 关键 config 字段 |
|---|---|---|---|
| `llm_generate` | `llm_generate.py` | `prompt` 模板（含 `{{var}}`） | `model`、`temperature`、`max_tokens`、`output_format` |
| `image_batch` | `image_batch.py` | `prompt_field`（上游字段名）或 `prompt` 字面量 | `model`、`size`、`batch_size`、`from_step` |
| `video_batch` | `video_batch.py` | `from_step`（上游 image_batch step.key） | `model`、`seconds`、`aspect_ratio` |
| `tts_generate` | `tts_generate.py` | `from_step`（上游 text/llm_generate step.key） | `voice`、`speed`、`provider` |
| `ffmpeg_composite` | `ffmpeg_composite.py` | `from_step`（上游 video_batch step.key） | `with_subtitle`、`audio_from_step`、`subtitle_from_step` |

任何前端/转换层产出的 `step.type` 必须命中这张表，否则后端找不到执行器。

## 5. 设计

### 5.1 模板编辑器简化

#### 5.1.1 移除项

- 移除"专家模式"开关及其切换的 JSON 原始编辑视图。
- 移除 `output_mapping` 的 JSON textarea。`output_mapping` 由后端按步骤类型自动推断（最后一个 `ffmpeg_composite` 或 `video_batch` 的输出作为最终产物）。
- 移除 `estimated_credits` 和 `estimated_time_minutes` 的手填输入框。两者由后端 `estimate_credits` 接口按 steps_config 自动计算，前端编辑器只读展示。
- 移除 `inputs_config` 的原始字段编辑（key/label/type/required/description/min/max）。改为从预设类型中选（见 5.1.3）。

#### 5.1.2 三栏布局

模板编辑页重构为三栏：

- **左栏 · 预设步骤库**（约 180px）：列出 7 种预设步骤（见 5.1.4），每项显示图标 + 名称 + `+` 按钮，点击 `+` 追加到当前流程末尾。
- **中栏 · 流程编排**（自适应）：
  - 顶部基础信息块：模板名称、描述、分类、标签、是否公开（保留现有控件）。
  - 缩略图上传块（保留）。
  - 流程步骤列表：每个步骤是一张卡片，卡片头显示序号、步骤名、类型标签、`↑↓✕`（上移/下移/删除）按钮。卡片体默认只显示"提示词模板"输入框（用户最常改的），下方"展开高级 ▾"折叠区放该步骤类型的高级参数。
  - 列表底部"+ 从步骤库添加"按钮（与左栏点击等价，给习惯从中栏操作的用户）。
- **右栏 · 实时预览**（约 200px）：按当前步骤顺序显示节点链，用户运行模板时所见即所得。

#### 5.1.3 inputs_config 简化

- 默认只生成一个"主题（theme）"输入项。
- 用户要加输入时，点击"添加输入"按钮，从预设类型中选：主题（text）、风格（style_select）、分镜数（number）、开关（boolean）。选中后由前端预设自动填好 `key/label/type/required`，用户只改显示名和默认值。
- 不暴露 `description`、`min`、`max` 的原始字段——`number` 类型用一个步进组件配范围，`text` 类型用 textarea 配默认值和 placeholder。

#### 5.1.4 预设步骤库

新增前端常量文件 `frontend/src/config/workshop-step-presets.ts`，导出 `WORKSHOP_STEP_PRESETS` 数组。每个预设结构：

```ts
interface WorkshopStepPreset {
  presetKey: string         // 'script_generate' | 'character_design' | ...
  name: string              // 显示名（中文，i18n 覆盖）
  type: StepType            // 后端 step_type，必须命中第 4 节清单
  icon: string              // Element Plus Icon 组件名
  color: string             // 主题色 hex
  defaultName: string       // 步骤默认名（追加到流程时用）
  defaultConfig: Record<string, any>   // 该步骤类型的合理默认 config
  defaultPromptTemplate: string        // 默认提示词模板（含 {{}} 占位符）
  advancedFields: AdvancedFieldSpec[]  // 高级折叠区要渲染的字段规格
}
```

7 个预设：

| presetKey | name | type | 说明 |
|---|---|---|---|
| `script_generate` | 剧本生成 | `llm_generate` | 默认提示词"根据主题 {{theme}} 生成 8 个分镜剧本"，高级：模型/温度/max_tokens |
| `character_design` | 角色设计 | `llm_generate` | 产出角色描述 JSON，高级：模型/温度/output_format=json |
| `storyboard_draw` | 分镜绘制 | `image_batch` | `prompt_field: "prompt"`，`from_step` 自动指向上游剧本步骤，高级：模型/尺寸/批量 |
| `video_generate` | 视频生成 | `video_batch` | `from_step` 自动指向上游 image_batch，高级：模型/秒数/比例 |
| `voiceover` | 配音 | `tts_generate` | `from_step` 自动指向上游 text/llm_generate，高级：音色/语速/provider |
| `subtitle` | 字幕 | `llm_generate` | 产出 SRT 文本，`from_step` 指向上游剧本或视频描述，高级：模型/温度 |
| `compose` | 成片合成 | `ffmpeg_composite` | `from_step` 自动指向上游 video_batch，`with_subtitle: true`，`audio_from_step` 指向 tts 步骤，高级：是否烧录字幕/BGM |

#### 5.1.5 depends_on 自动推断

- 默认每个新步骤的 `depends_on` = `[上一个步骤的 key]`（线性流程）。
- 高级折叠区提供"依赖步骤"多选下拉，用户可改（例如让"字幕"和"配音"并行依赖同一个"剧本"步骤）。
- `from_step`、`audio_from_step`、`subtitle_from_step` 这类引用上游的 config 字段，由前端在保存时根据当前流程顺序自动填充为最近的对应类型步骤的 key。若找不到对应类型的上游步骤，保存时给出明确提示（如"配音步骤需要上游有文本/剧本步骤"）。

#### 5.1.6 保存前预校验

- 新增无副作用接口 `POST /api/pipeline/templates/validate`，请求体为完整的模板 JSON（不含 id），后端对每个步骤执行 `validate()` 但不落库、不启动运行。
- 保存模板前，前端先调用该接口。若任何步骤配置不全（缺 from_step、缺 prompt 等），返回 422 + 详细错误。
- 前端拦截错误，在对应步骤卡片上标红显示错误信息，不让保存。

### 5.2 导入格式补全

#### 5.2.1 官方示例文件下载

- 新增后端接口 `GET /api/pipeline/templates/sample`，返回一份最小可用的示例 JSON。结构：

```json
{
  "version": "1.0",
  "exported_at": "2026-06-28T12:00:00Z",
  "templates": [
    {
      "key": "example_standard_drama",
      "name": "示例 · 标准漫剧",
      "description": "剧本 → 分镜 → 视频 → 合成",
      "category": "drama",
      "tags": ["示例", "漫剧"],
      "inputs_config": [
        { "key": "theme", "label": "主题", "type": "text", "required": true, "default": "" }
      ],
      "steps_config": [
        {
          "key": "step_0",
          "name": "剧本生成",
          "type": "llm_generate",
          "depends_on": [],
          "config": {
            "prompt": "根据主题 {{theme}} 生成 8 个分镜剧本，输出 JSON 数组",
            "model": "agnes-2.0-flash",
            "temperature": 0.8,
            "output_format": "json"
          }
        },
        {
          "key": "step_1",
          "name": "分镜绘制",
          "type": "image_batch",
          "depends_on": ["step_0"],
          "config": {
            "from_step": "step_0",
            "prompt_field": "prompt",
            "model": "agnes-image-1.0",
            "size": "1024x1024",
            "batch_size": 8
          }
        },
        {
          "key": "step_2",
          "name": "视频生成",
          "type": "video_batch",
          "depends_on": ["step_1"],
          "config": {
            "from_step": "step_1",
            "model": "agnes-video-1.0",
            "seconds": 5,
            "aspect_ratio": "16:9"
          }
        },
        {
          "key": "step_3",
          "name": "成片合成",
          "type": "ffmpeg_composite",
          "depends_on": ["step_2"],
          "config": {
            "from_step": "step_2",
            "with_subtitle": false,
            "audio_from_step": null
          }
        }
      ],
      "output_mapping": null,
      "is_public": false
    }
  ],
  "script_templates": [],
  "style_presets": []
}
```

- 导入对话框 `TemplateImportExportDialog.vue` 的导入 Tab 文件选择区下方新增"下载示例模板"按钮，点击调用该接口并下载 `agnes-template-example.json`。

#### 5.2.2 格式文档

- 新增 `docs/workshop-template-format.md`，内容包括：
  - 顶层结构说明（version / exported_at / templates / script_templates / style_presets）。
  - `templates[]` 每个字段的含义。
  - `steps_config[]` 的 `type` 取值表（直接引用第 4 节权威清单）。
  - `inputs_config[]` 的字段类型（text/number/style_select/boolean）。
  - `depends_on` 与 `from_step` 的区别和用法。
  - 一个最小示例（与 5.2.1 的 JSON 一致）。

#### 5.2.3 导入校验增强

- 后端 `POST /api/pipeline/templates/import` 在写入前对每个模板的 `steps_config` 做校验：
  - 每个 `step.type` 必须在第 4 节清单内，否则该模板标记为 `skipped`，错误信息为"未知步骤类型 `{type}`，请参考格式文档 docs/workshop-template-format.md"。
  - 每个 `step.key` 必须唯一。
  - `depends_on` 引用的 key 必须存在于同模板的 steps 内。
  - `from_step`/`audio_from_step`/`subtitle_from_step` 同样校验。
- 校验失败的模板不计入 `imported` 计数，错误明细随响应返回（响应体新增 `errors: [{template_key, reason}]` 字段）。

#### 5.2.4 兼容画布导出

- 第 5.4 节会新增画布的"导出为工坊模板 JSON 文件"能力，导出格式与本节导入格式完全一致（顶层 `{version, exported_at, templates:[...]}`），画布导出的文件可直接拖进导入框。

### 5.3 画布 → 工坊模板转换修复

#### 5.3.1 修正 NODE_TYPE_TO_STEP_TYPE 映射

`SaveAsWorkshopTemplateDialog.vue` 的映射改为：

```ts
const NODE_TYPE_TO_STEP_TYPE: Record<string, string> = {
  text:     'llm_generate',
  image:    'image_batch',
  video:    'video_batch',
  tts:      'tts_generate',      // 新节点类型，见 5.4
  subtitle: 'llm_generate',      // 字幕用 llm_generate 产出 SRT 文本
  compose:  'ffmpeg_composite',  // 新节点类型
  audio:    'tts_generate',      // 兼容旧 audio 节点
  config:   'ffmpeg_composite',  // 兼容旧 config 节点
}
```

#### 5.3.2 修正 buildStepConfig 字段

按执行器真实读取的字段填充：

- `llm_generate`：`{ prompt, model, temperature, max_tokens, output_format? }`
- `image_batch`：`{ from_step: <上游 text/llm_generate step.key>, prompt_field: 'prompt', model, size, batch_size }`
- `video_batch`：`{ from_step: <上游 image_batch step.key>, model, seconds, aspect_ratio }`
- `tts_generate`：`{ from_step: <上游 text/llm_generate step.key>, voice, speed, provider }`
- `ffmpeg_composite`：`{ from_step: <上游 video_batch step.key>, with_subtitle, audio_from_step: <上游 tts_generate step.key or null>, subtitle_from_step: <上游 subtitle step.key or null> }`

`from_step` 等引用字段在转换时按"最近的同类型上游节点"填充；找不到则填 `null` 并在保存前提示。

#### 5.3.3 修正 depends_on 推断

- `depends_on` 仍按画布连线推断（保留现有 `analyzeExecutionOrder` 逻辑）。
- 额外保证：`from_step`/`audio_from_step`/`subtitle_from_step` 引用的 step.key 必须出现在 `depends_on` 列表里（否则执行器取不到上游输出）。转换时若发现引用的 key 不在 `depends_on` 中，自动补进去。

#### 5.3.4 修正 inputs_config 生成

- 扫描所有 `llm_generate` 步骤的 `prompt` 模板，正则提取 `{{xxx}}` 占位符。
- 对每个占位符生成一个 `inputs_config` 项：`{ key: xxx, label: 中文名, type: 'text', required: true, default: '' }`。
- 中文名映射表（前端常量）：`theme→主题`、`topic→主题`、`style→风格`、`count→数量`、其余按 key 原样显示。
- 去重：同一个 key 只生成一项。

#### 5.3.5 保存前预校验

- 与 5.1.6 一致，保存前调校验接口，失败则在对话框内显示错误列表，不让保存。

### 5.4 画布固化配音/字幕/视频拼接

#### 5.4.1 新增 3 种画布节点类型

在 `frontend/src/types/index.ts` 的 `CanvasPanel.type` 联合类型中新增：

- `tts`：配音节点。配置面板字段：音色（下拉）、语速（滑块）、上游文本来源（从某个 `text` 节点取内容，下拉选）。
- `subtitle`：字幕节点。配置面板字段：上游文本来源（从某个 `text` 节点取内容，下拉选）、字幕样式（预设几套）。产出 SRT 文本，对应工坊的 `llm_generate` 步骤（提示词模板让 LLM 生成 SRT 格式字幕）。不接受 `video` 入边——视频转字幕（ASR）后端无对应执行器，本次不做。
- `compose`：成片合成节点。配置面板字段：上游视频（`video` 节点，下拉选）、是否烧录字幕（开关）、配音来源（`tts` 节点，下拉选，可空）、字幕来源（`subtitle` 节点，下拉选，可空）。

#### 5.4.2 节点连线类型校验

- `tts` 只接受来自 `text` 节点的入边。
- `subtitle` 只接受来自 `text` 节点的入边（产出 SRT 文本，不做视频 ASR）。
- `compose` 接受来自 `video` 的入边（必须），可选来自 `tts` 和 `subtitle` 的入边。
- 连线时若类型不匹配，前端拦截并提示"该节点不接受此类型输入"。

#### 5.4.3 工具栏新增

`CanvasToolbar.vue` 的"添加节点"区新增 3 个按钮：配音（麦克风图标）、字幕（字幕图标）、合成（拼图图标）。图标和颜色直接复用 `workshop-step-presets.ts` 里对应预设的 `icon`/`color`，保证两边视觉一致。

#### 5.4.4 节点默认配置复用预设

新增画布节点时，其默认 `content` 直接从 `WORKSHOP_STEP_PRESETS` 里对应预设的 `defaultConfig` 拷贝。例如新增 `tts` 节点时，`content.voice = 'default'`、`content.speed = 1.0`、`content.provider = 'agnes-tts'`。

#### 5.4.5 画布运行路径（不变）

画布节点仍不直接执行。运行路径保持：

1. 用户在画布搭好流程。
2. 点"保存为工坊模板" → 走 5.3 修正后的转换 → 创建工坊模板。
3. 或点"运行此流程" → 同样转换 → 调工坊运行接口 → 结果回填到画布节点的 `content.result`。

不在本次范围内做画布内直接执行。

#### 5.4.6 画布"导出为工坊模板 JSON 文件"

`SaveAsWorkshopTemplateDialog.vue` 新增"导出为 JSON 文件"按钮（与"保存到工坊"并列）。点击后走 5.3 的转换逻辑，但不调创建接口，而是把转换后的 `{version, exported_at, templates:[...]}` 打包成 JSON 下载。导出的文件可直接拖进 5.2 的导入框，格式完全一致。

## 6. 数据流

```
[预设步骤库] --点击+--> [流程卡片] --保存--> [预校验接口] --通过--> [创建模板接口]
                              |
                              +--> [inputs_config 自动生成]
                              +--> [from_step 自动填充]
                              +--> [depends_on 自动补全]

[画布节点] --保存为工坊模板--> [修正后的转换器] --预校验--> [创建模板接口]
            |
            +--> [导出为JSON] --> [导入对话框] --> [校验增强的导入接口]
```

## 7. 错误处理

- 预校验失败：前端在对应步骤卡片标红，显示后端返回的字段级错误，不让保存。
- 导入校验失败：后端返回 `errors: [{template_key, reason}]`，前端在预览表里标红对应行，显示 reason。
- 画布转换时缺上游：前端在 `SaveAsWorkshopTemplateDialog` 的步骤预览列表里标红对应步骤，提示"缺少上游 X 类型节点"，不让保存/导出。
- 运行时步骤报错（已有）：保留现有 SSE 错误推送和重试机制，本次不改。

## 8. 测试策略

遵循 TDD：每个改动先写测试再实现。

### 8.1 后端测试

- `test_templates_sample_endpoint`：`GET /api/pipeline/templates/sample` 返回的 JSON 能通过自身的导入校验。
- `test_templates_import_rejects_unknown_step_type`：导入含 `type: "image_gen"` 的模板，该模板被标记 `skipped`，错误信息含"未知步骤类型"。
- `test_templates_import_rejects_dangling_depends_on`：`depends_on` 引用不存在的 key 时拒绝。
- `test_templates_import_rejects_dangling_from_step`：`from_step` 引用不存在的 key 时拒绝。
- `test_templates_validate_endpoint`：`POST /api/pipeline/templates/validate` 对合法 steps_config 返回 200，对缺 `from_step` 的 `video_batch` 返回 422。
- `test_estimate_credits_auto_infers_output`：`output_mapping` 为 null 时，后端按最后一个 `ffmpeg_composite`/`video_batch` 推断最终产物。

### 8.2 前端测试

- `workshop-step-presets.spec.ts`：7 个预设的 `type` 都命中第 4 节清单；`defaultConfig` 含对应执行器必需字段。
- `SaveAsWorkshopTemplateDialog.spec.ts`：
  - 给定画布 `text→image→video→compose` 四节点，转换后 `steps_config` 的 type 依次是 `llm_generate/image_batch/video_batch/ffmpeg_composite`。
  - `ffmpeg_composite` 的 `from_step` 指向 `video_batch` 的 key。
  - `inputs_config` 含 `theme`（从 llm_generate 的 `{{theme}}` 提取）。
- `TemplateImportExportDialog.spec.ts`：点击"下载示例模板"触发下载，文件名含 `agnes-template-example`。
- 画布新节点类型：`tts/subtitle/compose` 节点能创建、能连线、连线类型校验生效。

## 9. 兼容性

- 项目未上线，旧模板按新规则直接改，不写迁移。
- 旧的 `audio`/`config` 画布节点仍能"保存为工坊模板"（按 5.3.1 的兼容映射转成 `tts_generate`/`ffmpeg_composite`），但新建节点时工具栏不再提供这两种类型，改提供 `tts`/`compose`。
- 导入接口对旧导出文件（无 `version` 字段）仍兼容，按 `version: "1.0"` 处理。

## 10. 实施顺序建议

1. 后端：新增 `GET /templates/sample`、`POST /templates/validate`，增强导入校验，`output_mapping` 自动推断。配套测试。
2. 前端：新增 `workshop-step-presets.ts`。
3. 前端：重构模板编辑页为三栏布局，移除参数化项，接入预设步骤库。
4. 前端：修复 `SaveAsWorkshopTemplateDialog` 的映射、config、depends_on、inputs_config。
5. 前端：导入对话框加"下载示例模板"按钮。
6. 前端：画布新增 `tts/subtitle/compose` 三种节点类型 + 工具栏按钮 + 连线校验。
7. 前端：画布"导出为 JSON 文件"按钮。
8. 文档：`docs/workshop-template-format.md`。
