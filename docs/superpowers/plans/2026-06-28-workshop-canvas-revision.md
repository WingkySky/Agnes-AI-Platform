# 创意工坊与无限画布修订 实施计划

> **For agentic workers:** 按 task 顺序执行，每个 task 带验收用例（Given-When-Then）。完成后勾选 `- [x]`。

**Goal:** 修复创意工坊模板编辑器过度参数化、导入格式无模版、画布→工坊模板转换失败、画布缺少配音/字幕/拼接固化能力四类问题。

**Spec:** [docs/superpowers/specs/2026-06-28-workshop-canvas-revision-design.md](../specs/2026-06-28-workshop-canvas-revision-design.md)

**Tech Stack:** 后端 FastAPI + SQLAlchemy async；前端 Vue 3 + Element Plus + Pinia

**项目约束（来自 AGENTS.md，覆盖 tdd-workflow 默认行为）：**
- 项目当前无后端测试框架（无 pytest、无 tests/ 目录）、无前端测试框架（无 vitest/jest）
- AGENTS.md 明确："不强制 TDD，不执行构建/语法检查，用户自己做"
- 因此本计划把 tdd-workflow 的"测试先行"原则转化为**"验收用例先行"**：每个 task 列出 Given-When-Then 验收清单，用户可手动验证或后续补自动化
- 后端附带一份可选的 pytest 用例骨架文件（`backend/tests/test_workshop_revision.py`），不强制安装 pytest，留给用户决定何时启用
- 前端因完全无测试框架，纯写手动验收清单，不强加 vitest 安装

**后端 step_type 权威清单（所有 task 以此为准）：**
`llm_generate` / `image_batch` / `video_batch` / `tts_generate` / `ffmpeg_composite`
来源：`backend/app/services/pipeline/steps/__init__.py` 的注册表，可用 `list_registered_steps()` 查询。

---

## 文件结构总览

### 新建文件

| 路径 | 职责 |
|------|------|
| `backend/app/services/pipeline/template_validate.py` | 模板预校验逻辑（无副作用，不落库） |
| `backend/tests/__init__.py` | 测试包初始化（可选） |
| `backend/tests/conftest.py` | pytest fixtures（async client、db session） |
| `backend/tests/test_workshop_revision.py` | 本轮修订的后端验收用例（可选） |
| `frontend/src/config/workshop-step-presets.ts` | 7 个预设步骤定义 |
| `frontend/src/components/workshop/StepLibraryPanel.vue` | 左栏预设步骤库 |
| `frontend/src/components/workshop/StepCard.vue` | 中栏单步骤卡片（含折叠高级区） |
| `frontend/src/components/workshop/FlowPreviewPanel.vue` | 右栏实时预览 |
| `frontend/src/components/workshop/InputFieldPicker.vue` | inputs_config 预设类型选择器 |
| `docs/workshop-template-format.md` | 导入格式文档 |

### 修改文件

| 路径 | 修改内容 |
|------|---------|
| `backend/app/routes/pipeline.py` | 新增 `/templates/sample`、`/templates/validate` 路由；导入接口加 step.type 校验；导入响应加 `errors` 字段 |
| `backend/app/services/pipeline/__init__.py` | 导出 `validate_template`、`get_sample_template` |
| `backend/app/services/pipeline/template_service.py` | `estimate_credits` 时 `output_mapping` 为 null 自动推断最终产物 |
| `frontend/src/types/index.ts` | `CanvasPanel.type` 联合类型加 `tts`/`subtitle`/`compose`；新增 `WorkshopStepPreset` 类型 |
| `frontend/src/api/pipeline.ts` | 新增 `getSampleTemplate()`、`validateTemplate()` |
| `frontend/src/views/TemplateWizardView.vue` | 重构为三栏布局，移除参数化项，接入预设步骤库 |
| `frontend/src/components/pipeline/TemplateImportExportDialog.vue` | 导入 Tab 加"下载示例模板"按钮 |
| `frontend/src/components/canvas/SaveAsWorkshopTemplateDialog.vue` | 修正映射/config/depends_on/inputs_config；加"导出为 JSON"按钮 |
| `frontend/src/components/canvas/CanvasToolbar.vue` | 添加节点区加 tts/subtitle/compose 三个按钮 |
| `frontend/src/components/canvas/CanvasNode.vue` | 支持渲染 tts/subtitle/compose 三种新节点 |
| `frontend/src/stores/canvas.ts` | 新节点类型的默认 content；连线类型校验 |
| `frontend/src/i18n/zh-CN.ts` & `en-US.ts` | 新增预设步骤、新节点类型、校验错误等文案 |

---

## Phase 1：后端基础能力（spec 5.1.6、5.2.1、5.2.3、5.3 output_mapping 自动推断）

### Task 1：新增 `GET /api/pipeline/templates/sample` 接口

**依赖：** 无
**文件：**
- 新建 `backend/app/services/pipeline/template_validate.py`（先放 sample 逻辑，后续 validate 也放这）
- 修改 `backend/app/services/pipeline/__init__.py`（导出 `get_sample_template`）
- 修改 `backend/app/routes/pipeline.py`（新增路由）

**实现要点：**
1. `get_sample_template()` 返回一个固定结构的 dict，内容直接用 spec 5.2.1 的 JSON（标准漫剧 4 步流程）。
2. `exported_at` 用 `datetime.utcnow().isoformat() + 'Z'` 动态生成（不要硬编码时间，按 AGENTS.md "日期等通用能力用库"原则）。
3. 路由 `GET /pipeline/templates/sample` 无需鉴权（公开接口，方便用户未登录也能下载示例）。
4. 返回值直接是 dict，FastAPI 自动序列化为 JSON。

**验收用例：**
- Given 后端启动，When 调 `GET /api/pipeline/templates/sample`，Then 返回 200，body 含 `templates` 数组且长度 ≥1。
- Given 返回的 sample，When 检查 `templates[0].steps_config`，Then 每个 step 的 `type` 都在权威清单 `{llm_generate, image_batch, video_batch, tts_generate, ffmpeg_composite}` 内。
- Given 返回的 sample，When 把它作为导入 payload 调 `POST /api/pipeline/templates/import`，Then 该模板被 `imported` 计数（自洽：示例文件能被自己的导入接口接受）。

---

### Task 2：新增 `POST /api/pipeline/templates/validate` 接口

**依赖：** 无
**文件：**
- 扩展 `backend/app/services/pipeline/template_validate.py`（加 `validate_template` 函数）
- 修改 `backend/app/services/pipeline/__init__.py`（导出 `validate_template`）
- 修改 `backend/app/routes/pipeline.py`（新增路由）
- 修改 `backend/app/schemas/pipeline.py`（加 `TemplateValidateRequest` / `TemplateValidateResponse`）

**实现要点：**
1. `validate_template(template_data: dict) -> Tuple[bool, List[Dict]]`：
   - 遍历 `steps_config`，对每个 step：
     - `type` 必须在 `list_registered_steps()` 返回的 key 集合内，否则记错 `unknown_step_type`。
     - `key` 必须非空且在同模板内唯一，否则记错 `duplicate_step_key`。
     - `depends_on` 中每个引用必须存在于同模板的 step.key 集合，否则记错 `dangling_depends_on`。
     - `from_step`/`audio_from_step`/`subtitle_from_step` 同样校验存在性，否则记错 `dangling_from_step`。
   - 不实例化执行器、不调 `validate()`（避免外部依赖），只做结构校验。
   - 返回 `(is_valid, errors)`，errors 形如 `[{step_key, field, reason}]`。
2. 路由 `POST /pipeline/templates/validate` 需鉴权（普通用户即可），请求体为完整模板 JSON（不含 id），返回 `{is_valid, errors}`。
3. 不落库、不启动运行，纯无副作用。

**验收用例：**
- Given 合法的 4 步标准漫剧 steps_config，When 调 validate，Then `is_valid=true`，`errors=[]`。
- Given steps_config 含 `type: "image_gen"`，When 调 validate，Then `is_valid=false`，`errors` 含一条 `unknown_step_type`，reason 含"image_gen"和"参考格式文档"。
- Given steps_config 里 step_1 的 `from_step: "step_99"`（不存在），When 调 validate，Then `is_valid=false`，errors 含一条 `dangling_from_step`。
- Given steps_config 两个 step 都用 `key: "step_0"`，When 调 validate，Then `is_valid=false`，errors 含 `duplicate_step_key`。

---

### Task 3：导入接口增强 step.type 校验 + errors 字段

**依赖：** Task 2（复用 `validate_template`）
**文件：**
- 修改 `backend/app/routes/pipeline.py` 的 `import_pipeline_templates`（第 559 行起）

**实现要点：**
1. 在第三步"导入流水线模板"循环里（第 705 行起），对每个 `tpl_data` 先调 `validate_template(tpl_data)`：
   - 若 `is_valid=false`，该模板跳过，记入新增的 `errors` 列表（`{template_key, template_name, reasons: [...]}`），不计入 `imported`/`skipped`/`renamed`/`overwritten`。
2. 响应体新增 `errors` 字段：`{imported, skipped, renamed, overwritten, items, errors}`。
3. 前端 `TemplateImportExportDialog.vue` 的预览表会在 Task 8 里读取 `errors` 标红。
4. 校验失败的模板不写入数据库。

**验收用例：**
- Given 导入文件含一个 `type: "video_gen"` 的模板，When 调导入接口，Then 响应 `imported=0`，`errors` 含一条，reasons 含"未知步骤类型 video_gen"。
- Given 导入文件含一个合法模板和一个非法模板，When 调导入接口，Then `imported=1`，`errors` 含 1 条（非法那个）。
- Given 导入文件全部合法，When 调导入接口，Then `errors=[]`，行为与改造前一致（不回归）。

---

### Task 4：output_mapping 自动推断

**依赖：** 无
**文件：**
- 修改 `backend/app/services/pipeline/template_service.py` 的积分估算逻辑（第 386 行附近 `_estimate_credits`）

**实现要点：**
1. 在 `_estimate_credits` 或新增的 `_infer_output_mapping(steps_config)` 函数里：
   - 若 `output_mapping` 为 null/空，按 steps 顺序找最后一个 `ffmpeg_composite` 步骤，其输出作为最终产物。
   - 若无 `ffmpeg_composite`，找最后一个 `video_batch`。
   - 都没有则返回 null（纯图片/文本流程，无最终视频）。
2. 序列化模板时（`_serialize_template`）若 `output_mapping` 为 null，调用推断函数填充返回值（不改数据库）。
3. 创建/更新模板时若前端未传 `output_mapping`，后端自动推断后存库（省得每次序列化都算）。

**验收用例：**
- Given steps_config = [llm_generate, image_batch, video_batch, ffmpeg_composite]，output_mapping=null，When 序列化模板，Then 返回的 `output_mapping` 指向 ffmpeg_composite 步骤的输出。
- Given steps_config = [llm_generate, image_batch]（无视频步骤），output_mapping=null，When 序列化，Then `output_mapping` 为 null。
- Given 前端创建模板时不传 output_mapping，When 后端处理，Then 数据库里 output_mapping 字段被自动填充为推断结果。

---

### Task 5：后端可选测试骨架

**依赖：** Task 1-4
**文件：**
- 新建 `backend/tests/__init__.py`（空文件）
- 新建 `backend/tests/conftest.py`（async client + db fixtures）
- 新建 `backend/tests/test_workshop_revision.py`（Task 1-4 的验收用例转成 pytest 函数）
- 修改 `backend/requirements.txt`（追加 `pytest>=8.0`、`pytest-asyncio>=0.23`、`httpx>=0.27`（已有）—— 用注释标注"可选，用于运行 tests/"）

**实现要点：**
1. conftest.py 提供 `async_client` fixture（用 httpx.AsyncClient 起 ASGI transport）和 `db_session` fixture（用 SQLite 内存库）。
2. test_workshop_revision.py 把 Task 1-4 的 Given-When-Then 转成 `async def test_xxx` 函数。
3. requirements.txt 里 pytest 相关依赖加注释 `# 可选：用于运行 backend/tests/`，不强制用户安装。
4. 这一步是**可选交付**——用户可选择不装 pytest，验收用例仍可手动用 curl/Postman 验证。

**验收用例：**
- Given 已安装 pytest + pytest-asyncio，When 运行 `cd backend && pytest tests/test_workshop_revision.py -v`，Then 全部用例通过。
- Given 未安装 pytest，When 跳过本步，Then 不影响后续前端任务（纯可选）。

---

## Phase 2：前端预设步骤库（spec 5.1.4）

### Task 6：新建 `workshop-step-presets.ts`

**依赖：** 无
**文件：**
- 新建 `frontend/src/config/workshop-step-presets.ts`
- 修改 `frontend/src/types/index.ts`（新增 `WorkshopStepPreset`、`AdvancedFieldSpec` 类型）

**实现要点：**
1. 类型定义：
   ```ts
   export interface AdvancedFieldSpec {
     key: string           // config 字段名，如 'model'
     label: string         // 显示名
     type: 'text' | 'number' | 'select' | 'boolean'
     options?: { label: string; value: any }[]  // select 用
     default: any
     min?: number; max?: number  // number 用
   }
   export type WorkshopStepType = 'llm_generate' | 'image_batch' | 'video_batch' | 'tts_generate' | 'ffmpeg_composite'
   export interface WorkshopStepPreset {
     presetKey: string
     name: string          // 中文，i18n 覆盖
     type: WorkshopStepType
     icon: string          // Element Plus Icon 组件名
     color: string         // hex
     defaultName: string
     defaultConfig: Record<string, any>
     defaultPromptTemplate: string
     advancedFields: AdvancedFieldSpec[]
   }
   ```
2. 导出 `WORKSHOP_STEP_PRESETS: WorkshopStepPreset[]`，7 个预设按 spec 5.1.4 表格实现：
   - `script_generate`（llm_generate）：默认提示词"根据主题 {{theme}} 生成 8 个分镜剧本，输出 JSON 数组"，高级字段 model/temperature/max_tokens。
   - `character_design`（llm_generate）：提示词产出角色描述 JSON，高级字段 model/temperature/output_format。
   - `storyboard_draw`（image_batch）：`defaultConfig = { prompt_field: 'prompt', from_step: null, model: 'agnes-image-1.0', size: '1024x1024', batch_size: 8 }`，高级字段 model/size/batch_size。
   - `video_generate`（video_batch）：`defaultConfig = { from_step: null, model: 'agnes-video-1.0', seconds: 5, aspect_ratio: '16:9' }`，高级字段 model/seconds/aspect_ratio。
   - `voiceover`（tts_generate）：`defaultConfig = { from_step: null, voice: 'default', speed: 1.0, provider: 'agnes-tts' }`，高级字段 voice/speed/provider。
   - `subtitle`（llm_generate）：提示词产出 SRT 文本，`defaultConfig = { from_step: null, model: 'agnes-2.0-flash', temperature: 0.5, output_format: 'text' }`，高级字段 model/temperature。
   - `compose`（ffmpeg_composite）：`defaultConfig = { from_step: null, with_subtitle: true, audio_from_step: null, subtitle_from_step: null }`，高级字段 with_subtitle（boolean）。
3. 每个预设的 `type` 必须命中后端权威清单——这是后续所有转换正确性的基石。

**验收用例：**
- Given `WORKSHOP_STEP_PRESETS`，When 遍历每一项，Then `preset.type` 都在 `{llm_generate, image_batch, video_batch, tts_generate, ffmpeg_composite}` 内（编译期 TS 已保证，运行期可用 `console.log` 抽查）。
- Given `storyboard_draw` 预设，When 检查 `defaultConfig`，Then 含 `prompt_field: 'prompt'`、`from_step: null`、`size`、`batch_size`。
- Given `compose` 预设，When 检查 `defaultConfig`，Then 含 `with_subtitle`、`audio_from_step`、`subtitle_from_step`（这三个是 ffmpeg_composite 执行器真实读取的字段）。
- Given 任意预设，When 检查 `advancedFields`，Then 每项的 `key` 都能在 `defaultConfig` 里找到对应字段。

---

## Phase 3：模板编辑器重构（spec 5.1.1、5.1.2、5.1.3、5.1.5、5.1.6）

### Task 7：三栏布局骨架 + 移除参数化项

**依赖：** Task 6
**文件：**
- 修改 `frontend/src/views/TemplateWizardView.vue`（大改）
- 新建 `frontend/src/components/workshop/StepLibraryPanel.vue`
- 新建 `frontend/src/components/workshop/StepCard.vue`
- 新建 `frontend/src/components/workshop/FlowPreviewPanel.vue`

**实现要点：**
1. `TemplateWizardView.vue` 顶部保留基础信息块（名称/描述/分类/标签/公开），下方改为三栏 flex 布局：
   - 左栏 `<StepLibraryPanel>`：props 接收 `presets`，emit `add(presetKey)`。
   - 中栏流程区：`v-for` 渲染 `<StepCard>`，底部"+ 从步骤库添加"按钮（emit `add`，与左栏等价）。
   - 右栏 `<FlowPreviewPanel>`：props 接收 `steps`，纯展示节点链。
2. **移除项**（spec 5.1.1）：删掉"专家模式"开关及 JSON 编辑视图；删掉 `output_mapping` 的 textarea；删掉 `estimated_credits` 和 `estimated_time_minutes` 手填输入框（改为只读展示，值由后端 estimate 接口返回）；删掉 `inputs_config` 原始字段编辑。
3. `StepCard.vue` props：`step`、`index`、`total`。emit：`move-up`、`move-down`、`remove`、`update:step`。
   - 卡片头：序号圆圈 + 步骤名（el-input）+ 类型标签（el-tag）+ `↑↓✕` 按钮。
   - 卡片体：默认显示"提示词模板"textarea（绑 `step.config.prompt` 或 `step.config.prompt_template`，按 type 区分）。
   - "展开高级 ▾"折叠区：`v-if="expanded"`，按 `preset.advancedFields` 动态渲染 el-input/el-input-number/el-select/el-switch。
4. 移动/删除按钮直接操作父组件的 `steps` 数组（splice + 插入），不引入拖拽库（YAGNI）。

**验收用例：**
- Given 进入模板编辑页，When 页面加载完成，Then 看到左中右三栏，左栏列出 7 个预设步骤。
- Given 左栏点击"剧本生成 +"，When 点击，Then 中栏流程区新增一张"剧本生成"卡片，序号为 1。
- Given 中栏有 3 张卡片，When 点第 2 张的 `↑`，Then 第 2 张与第 1 张交换位置，序号重排为 1,2,3。
- Given 点第 2 张的 `✕`，When 点击，Then 第 2 张被删除，剩余卡片序号重排。
- Given 展开某卡片高级区，When 修改 model 字段，Then `step.config.model` 同步更新。
- Given 页面加载，Then 找不到"专家模式"开关、`output_mapping` textarea、`estimated_credits` 输入框（已移除）。

---

### Task 8：inputs_config 简化 + 保存前预校验

**依赖：** Task 2（后端 validate 接口）、Task 7
**文件：**
- 新建 `frontend/src/components/workshop/InputFieldPicker.vue`
- 修改 `frontend/src/views/TemplateWizardView.vue`
- 修改 `frontend/src/api/pipeline.ts`（加 `validateTemplate()`）

**实现要点：**
1. `InputFieldPicker.vue`：一个"添加输入"按钮 + 弹出选择（主题/风格/分镜数/开关四种预设）。选中后向前端 `inputs_config` 数组追加一项，`key/label/type/required` 由预设自动填，用户只改显示名和默认值。
2. 默认初始化 `inputs_config = [{ key: 'theme', label: '主题', type: 'text', required: true, default: '' }]`。
3. `from_step` 等引用字段的自动填充（spec 5.1.5）：保存前扫描 `steps`，对每个 step：
   - `image_batch` 的 `from_step` = 最近的、位置在它之前的 `llm_generate` step.key。
   - `video_batch` 的 `from_step` = 最近的、之前的 `image_batch` step.key。
   - `tts_generate` 的 `from_step` = 最近的、之前的 `llm_generate` step.key。
   - `ffmpeg_composite` 的 `from_step` = 最近的、之前的 `video_batch` step.key；`audio_from_step` = 最近的、之前的 `tts_generate` step.key（可空）；`subtitle_from_step` = 最近的、之前的 `subtitle`（llm_generate）step.key（可空）。
   - 找不到对应上游时，前端 toast 提示"步骤 X 缺少上游 Y 类型步骤"，阻止保存。
4. `depends_on` 自动补全：`from_step` 引用的 key 若不在 `depends_on` 中，自动追加。
5. 保存按钮点击：
   - 先调 `validateTemplate(templateData)`。
   - `is_valid=false` 时，在对应 `StepCard` 上标红（通过 `step._error` 字段传递错误），不调创建接口。
   - `is_valid=true` 时，调 `createTemplate` 或 `updateTemplate`。

**验收用例：**
- Given 编辑页初始状态，When 页面加载，Then `inputs_config` 已含一个 `theme` 项。
- Given 点击"添加输入"→选"分镜数"，When 选中，Then inputs_config 追加 `{type:'number'}` 项，用户可改显示名和默认值。
- Given 流程为 [剧本(llm_generate), 分镜(image_batch), 视频(video_batch), 合成(ffmpeg_composite)]，When 点保存，Then 前端自动填充：分镜.from_step=剧本.key，视频.from_step=分镜.key，合成.from_step=视频.key。
- Given 流程为 [分镜(image_batch)]（无上游 llm_generate），When 点保存，Then toast 提示"分镜绘制步骤缺少上游剧本生成步骤"，不调后端。
- Given 合法流程，When 点保存，Then 先调 validate 接口，通过后再调 create/update。

---

## Phase 4：导入对话框增强（spec 5.2.1 下载按钮、5.2.3 errors 展示）

### Task 9：下载示例模板按钮 + errors 标红

**依赖：** Task 1（后端 sample 接口）、Task 3（后端 errors 字段）
**文件：**
- 修改 `frontend/src/components/pipeline/TemplateImportExportDialog.vue`
- 修改 `frontend/src/api/pipeline.ts`（加 `getSampleTemplate()`）

**实现要点：**
1. 导入 Tab 文件选择区下方新增"下载示例模板"按钮（el-button，text 样式）。
2. 点击调 `getSampleTemplate()`，把返回 JSON 转 Blob 下载，文件名 `agnes-template-example.json`。
3. 导入响应处理：读取 `res.errors`，若非空，在预览表里把对应 `template_key` 的行标红（`row.has_error = true`），并在该行下方展开错误明细（`reasons` 列表）。
4. 导入成功提示里若 `errors.length > 0`，toast 改为 warning："成功导入 N 个，M 个校验失败"，而不是 success。

**验收用例：**
- Given 导入 Tab，When 点击"下载示例模板"，Then 浏览器下载 `agnes-template-example.json`，内容含 `templates` 数组。
- Given 导入文件含一个错误 type 的模板，When 调导入接口，Then 预览表里该行标红，展开显示"未知步骤类型"。
- Given 导入有 1 成功 1 失败，When 导入完成，Then toast 为 warning 级别，文案含"1 个校验失败"。

---

## Phase 5：画布→工坊模板转换修复（spec 5.3）

### Task 10：修正 SaveAsWorkshopTemplateDialog 转换逻辑

**依赖：** Task 2（validate 接口）、Task 6（预设库复用 defaultConfig）
**文件：**
- 修改 `frontend/src/components/canvas/SaveAsWorkshopTemplateDialog.vue`

**实现要点：**
1. **修正映射**（spec 5.3.1）：
   ```ts
   const NODE_TYPE_TO_STEP_TYPE: Record<string, string> = {
     text: 'llm_generate',
     image: 'image_batch',
     video: 'video_batch',
     tts: 'tts_generate',
     subtitle: 'llm_generate',
     compose: 'ffmpeg_composite',
     audio: 'tts_generate',     // 兼容旧节点
     config: 'ffmpeg_composite' // 兼容旧节点
   }
   ```
2. **修正 buildStepConfig**（spec 5.3.2）：按 step_type 用 `WORKSHOP_STEP_PRESETS` 对应预设的 `defaultConfig` 作为基础，再从画布节点 `content` 覆盖可读字段（prompt/voice/size 等）。`from_step` 等引用字段在 5.3.3 统一填充。
3. **修正 depends_on + from_step 推断**（spec 5.3.3）：
   - `depends_on` 仍按画布连线推断（保留现有 `analyzeExecutionOrder` 逻辑）。
   - 转换后遍历 steps，按 Task 8 的"最近上游同类型"规则填充 `from_step`/`audio_from_step`/`subtitle_from_step`。
   - 若 `from_step` 引用的 key 不在 `depends_on` 中，自动追加。
4. **修正 inputs_config 生成**（spec 5.3.4）：正则 `/{{\s*(\w+)\s*}}/g` 扫描所有 `llm_generate` 步骤的 `prompt`，提取占位符，去重后生成 inputs_config。中文名映射：`{theme:'主题', topic:'主题', style:'风格', count:'数量'}`，其余按 key 原样。
5. **保存前预校验**（spec 5.3.5）：调 `validateTemplate`，失败则在对话框步骤预览列表里标红对应步骤，显示 reason，不让保存。
6. **新增"导出为 JSON 文件"按钮**（spec 5.4.6）：与"保存到工坊"并列。点击后走同样的转换，但不调创建接口，而是打包 `{version:'1.0', exported_at, templates:[转换后的单个模板]}` 为 JSON 下载。

**验收用例：**
- Given 画布有 text→image→video→compose 四节点（用新节点类型），When 点"保存到工坊"，Then 转换后 steps_config 的 type 依次是 `llm_generate/image_batch/video_batch/ffmpeg_composite`。
- Given 上述画布，When 转换完成，Then `ffmpeg_composite` 的 `from_step` 指向 `video_batch` 的 step.key。
- Given text 节点 content.prompt 含 `{{theme}}`，When 转换完成，Then `inputs_config` 含 `{key:'theme', label:'主题'}`。
- Given 画布只有 image 节点（无 text 上游），When 点保存，Then 对话框预览里 image 步骤标红，提示"缺少上游 llm_generate 步骤"，保存按钮禁用。
- Given 合法画布，When 点"导出为 JSON 文件"，Then 下载一个 JSON，结构为 `{version, exported_at, templates:[...]}`，可直接拖回导入框导入。
- Given 旧画布含 `audio`/`config` 节点，When 保存，Then 按 `audio→tts_generate`、`config→ffmpeg_composite` 映射转换（兼容）。

---

## Phase 6：画布新增节点类型（spec 5.4.1-5.4.4）

### Task 11：类型定义 + store 默认 content

**依赖：** Task 6
**文件：**
- 修改 `frontend/src/types/index.ts`（`CanvasPanel.type` 加 `tts`/`subtitle`/`compose`）
- 修改 `frontend/src/stores/canvas.ts`（新增节点时按 type 给默认 content）

**实现要点：**
1. `CanvasPanel.type` 联合类型追加 `'tts' | 'subtitle' | 'compose'`。
2. `canvas.ts` 的 `addPanel(type)` 或等价函数里，新增分支：
   - `tts`：默认 content 从 `WORKSHOP_STEP_PRESETS` 的 `voiceover` 预设 `defaultConfig` 拷贝（`{voice, speed, provider, from_node: null}`）。
   - `subtitle`：从 `subtitle` 预设拷贝（`{from_node: null, model, temperature}`）。
   - `compose`：从 `compose` 预设拷贝（`{from_node: null, with_subtitle: true, audio_from_node: null, subtitle_from_node: null}`）。
3. 节点显示名默认用预设的 `defaultName`（配音/字幕/成片合成）。

**验收用例：**
- Given 画布工具栏，When 调 `addPanel('tts')`，Then 新节点 type='tts'，content 含 `voice/speed/provider`。
- Given 调 `addPanel('compose')`，Then content 含 `with_subtitle:true`、`audio_from_node:null`。

---

### Task 12：工具栏按钮 + 节点渲染

**依赖：** Task 11、Task 6
**文件：**
- 修改 `frontend/src/components/canvas/CanvasToolbar.vue`
- 修改 `frontend/src/components/canvas/CanvasNode.vue`
- 修改 `frontend/src/i18n/zh-CN.ts` & `en-US.ts`

**实现要点：**
1. `CanvasToolbar.vue` 添加节点区新增 3 个按钮：
   - 配音：图标用 `Microphone`，颜色用 `voiceover` 预设的 color。
   - 字幕：图标用 `ChatLineSquare`（或 `Document`），颜色用 `subtitle` 预设的 color。
   - 合成：图标用 `Connection`（或 `Pieces`），颜色用 `compose` 预设的 color。
2. `CanvasNode.vue` 新增 3 种 type 的渲染分支：
   - `tts`：节点头显示麦克风图标 + "配音"，节点体显示音色/语速。
   - `subtitle`：节点头显示字幕图标 + "字幕"，节点体显示来源节点名。
   - `compose`：节点头显示拼图图标 + "成片合成"，节点体显示是否烧录字幕、配音来源。
3. 节点配置面板（`CanvasAppearancePanel.vue` 或专用面板）新增 3 种 type 的配置表单：音色下拉、语速滑块、来源节点下拉等。
4. i18n 补全 3 种节点的中英文文案。

**验收用例：**
- Given 画布工具栏，When 页面渲染，Then 看到"配音/字幕/合成"三个新按钮，图标和颜色与工坊预设步骤库一致。
- Given 点击"配音"按钮，When 点击，Then 画布新增一个 tts 节点，显示麦克风图标和"配音"标题。
- Given 选中 tts 节点，When 打开配置面板，Then 看到音色下拉、语速滑块、来源节点下拉。

---

### Task 13：连线类型校验

**依赖：** Task 11
**文件：**
- 修改 `frontend/src/stores/canvas.ts`（`addConnection` 或等价函数加校验）
- 修改 `frontend/src/components/canvas/CanvasConnectionsLayer.vue`（连线时调用校验）

**实现要点：**
1. 定义 `ALLOWED_INPUTS: Record<string, Set<string>>`：
   ```ts
   {
     tts:      new Set(['text']),
     subtitle: new Set(['text']),
     compose:  new Set(['video', 'tts', 'subtitle']),
     // text/image/video 仍按现有规则（或不限制）
   }
   ```
2. `addConnection(source, target)` 前：若 `ALLOWED_INPUTS[target.type]` 存在且 `source.type` 不在集合内，抛错或返回 false，前端 toast"该节点不接受此类型输入"。
3. `compose` 节点特殊：必须有且仅有一个 `video` 入边；`tts` 和 `subtitle` 入边各最多一个。校验时检查已有入边数量。
4. 连线 UI 在校验失败时不画线（拦截 mousedown/up）。

**验收用例：**
- Given 一个 text 节点和一个 tts 节点，When 尝试从 text 连到 tts，Then 连线成功。
- Given 一个 image 节点和一个 tts 节点，When 尝试从 image 连到 tts，Then 连线被拒绝，toast"配音节点不接受 image 类型输入"。
- Given 一个 compose 节点已有 video 入边，When 再连一条 video 入边，Then 被拒绝，toast"成片合成节点只能有一个视频输入"。
- Given 一个 compose 节点，When 连接 video + tts + subtitle 三条入边，Then 全部成功。

---

## Phase 7：文档（spec 5.2.2）

### Task 14：编写导入格式文档

**依赖：** Task 1（sample 接口确定最终格式）
**文件：**
- 新建 `docs/workshop-template-format.md`

**实现要点：**
1. 文档结构：
   - 顶层结构说明（version / exported_at / templates / script_templates / style_presets）。
   - `templates[]` 每个字段的含义（key/name/description/category/tags/inputs_config/steps_config/output_mapping/is_public）。
   - **`steps_config[]` 的 `type` 取值表**：直接引用 spec 第 4 节权威清单，列出 5 种 type 及其 config 必需字段。
   - `inputs_config[]` 的字段类型（text/number/style_select/boolean）。
   - `depends_on` 与 `from_step` 的区别和用法（depends_on 是步骤依赖图，from_step 是数据来源引用）。
   - 一个最小示例（与 Task 1 的 sample JSON 一致，可直接复制）。
2. 文档顶部加"获取示例文件：调用 `GET /api/pipeline/templates/sample` 或在导入对话框点'下载示例模板'"。

**验收用例：**
- Given 一个新用户，When 阅读 `docs/workshop-template-format.md`，Then 能理解 JSON 结构并照着写出可导入的模板文件。
- Given 文档里的最小示例，When 复制保存为 .json 并导入，Then 导入成功（与 Task 1 的 sample 自洽）。

---

## Phase 8：收尾

### Task 15：i18n 补全 + 回归检查

**依赖：** Task 6-14
**文件：**
- 修改 `frontend/src/i18n/zh-CN.ts`、`en-US.ts`

**实现要点：**
1. 补全本轮新增的所有文案：
   - 预设步骤库 7 个预设的 name/defaultName（中英文）。
   - 3 种新画布节点类型的名称、配置面板字段标签。
   - 校验错误信息（"未知步骤类型"、"缺少上游"、"该节点不接受此类型输入"等）。
   - 导入对话框"下载示例模板"按钮、"N 个校验失败"提示。
   - 编辑器"展开高级 ▾"、"从步骤库添加"等。
2. 回归检查：
   - 旧模板（含 output_mapping 手填值的）编辑页能正常打开，output_mapping 字段改为只读展示。
   - 旧画布（含 audio/config 节点）能正常"保存为工坊模板"（走兼容映射）。
   - 工坊运行页（PipelineRunView.vue）不受影响（本轮不改运行逻辑）。

**验收用例：**
- Given 切换到英文，When 进入模板编辑页，Then 所有新增文案显示英文，无 fallback 到中文。
- Given 一个旧内置模板，When 打开编辑页，Then 页面正常加载，三栏布局生效。
- Given 一个含 audio 节点的旧画布，When 点"保存为工坊模板"，Then 按 `audio→tts_generate` 映射转换成功。

---

## 实施顺序总结

```
Phase 1 (后端基础):
  Task 1 (sample) ─┐
  Task 2 (validate)┼─→ Task 3 (导入校验增强) ─→ Task 5 (可选测试骨架)
  Task 4 (output)  ┘

Phase 2 (前端预设):
  Task 6 (presets) ──────────────────────────────┐
                                                  │
Phase 3 (编辑器重构):                              │
  Task 7 (三栏布局) ─→ Task 8 (inputs+预校验) ────┤
                                                  │
Phase 4 (导入增强):                                │
  Task 9 (下载按钮+errors) ───────────────────────┤
                                                  │
Phase 5 (画布转换修复):                            │
  Task 10 (SaveAsWorkshop 修正) ──────────────────┤
                                                  │
Phase 6 (画布新节点):                              │
  Task 11 (类型+store) ─→ Task 12 (工具栏+渲染) ─→ Task 13 (连线校验)
                                                  │
Phase 7 (文档):                                   │
  Task 14 (格式文档) ─────────────────────────────┤
                                                  │
Phase 8 (收尾):                                   │
  Task 15 (i18n+回归) ←──────────────────────────┘
```

**关键路径**：Task 6 → Task 7 → Task 8 → Task 10（前端主线）；Task 1/2/3 可并行（后端主线）。

**风险点：**
- Task 7 是大改 `TemplateWizardView.vue`，需保留现有基础信息块和缩略图块的逻辑，只重构流程编排区。建议先 Read 整个文件再动手。
- Task 10 的转换逻辑是本轮最易出错的地方（4 处修正叠加），务必用 Task 2 的 validate 接口做保存前校验兜底。
- Task 13 的连线校验若改动 `canvas.ts` 的 `addConnection` 签名，需检查所有调用点不回归。
