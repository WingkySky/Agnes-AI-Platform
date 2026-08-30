# 统一预设广场（风格库 + 特效库）重构设计

对标 LiblibAI 风格广场 / 特效广场的产品形态，把"画风硬编码 + 手输提示词 + 形同虚设的预设中心"重构为可沉淀、可收藏、可复用的统一预设广场：卡片画廊 + 分类导航 + 搜索 + 我的收藏 + 最近使用，生成页弹窗即选即用，独立页做管理。

## 一、背景与问题

### 1.1 本项目现状

- **画风靠硬编码**：生图页 `frontend/src/views/ImageView.vue:367-375`（`imageTemplates` 7 个风格）、生视频页 `frontend/src/views/VideoView.vue:355-362`（6 个），点击后前端 `appendStylePrompt` 把中文后缀拼进提示词输入框，渲染组件为 `frontend/src/components/PromptTemplates.vue`。
- **预设中心形同虚设**：`frontend/src/views/presets/PresetCenter.vue` + `prompt_presets` 表（`backend/app/models/prompt_preset.py`，5 类：camera/prompt/style/script/pipeline）存在四个问题：
  1. 卡片纯文字，无封面图字段；
  2. "使用"动作是空函数（`PresetCenter.vue:685-687`）；
  3. 生成页快速面板 `PresetQuickPanel.vue` 选中后把 `prompt_text` **整段覆盖**输入框，不是追加；
  4. `style_params` 自由 JSON，与后端另外两套风格体系互不联通。
- **三套风格体系互不联通**：前端硬编码 / `style_presets`（12 个内置风格带 preview_image，唯一消费方是画布 `StyleSelector.vue`）/ `style_elements`（6 层结构化拼 prompt，preview-prompt 接口无人用于生成页）。
- **无收藏、无最近使用**：只有作品点赞（asset_like/plaza_like），预设没有收藏机制；`usage_count` 注释为"异步定时统计，非实时"。
- **特效无体系**：视频"特效感"只靠生视频页硬编码模板；运镜预设（camera_presets 表 + `build_camera_prompt_suffix` 后端拼接）只在画布使用。
- **脚本类预设无消费场景**：type=script 只有编辑和详情查看，无任何应用入口。

### 1.2 对标形态（LiblibAI 截图）

弹窗式广场：主 tab（风格广场 / 我的收藏 / 最近使用）+ 搜索（名称、作者）+ 分类导航（推荐/摄影写真/动漫游戏/风格插画…）+ 卡片网格（封面大图、名称、作者头像昵称、使用数、星标收藏）+ 点击卡片进详情应用。

## 二、目标

1. **统一预设广场**：风格 / 特效（新增类型）/ 运镜 / 提示词 / 脚本五类预设进同一个卡片画廊，分类 tab 区分，每类有明确"应用"行为；
2. **双入口共用画廊**：生图页、生视频页弹窗即选即用；`/presets` 独立页改造为管理视图（编辑、导入导出、投稿、管理员审核）；
3. **我的收藏 + 最近使用**：收藏表 + 使用记录表，广场三个主 tab；
4. **三层供给**：官方运营种子 + 用户自建（默认私有）+ 投稿公开（沿用现有 is_public/is_approved 审核流）；
5. **封面图**：上传图片 / 从自己生成记录选图 / 官方种子脚本批量产出；
6. **硬编码收编**：生图/生视频页硬编码风格与 `style_presets` 内置风格迁为官方种子，删除硬编码代码。

## 三、非目标

- 画布 `StyleSelector` 的 `style_presets` / `style_elements` 分层体系**保持不动**（画布需要逐层组合与权重，与广场的"整卡应用"是不同场景，强行合并两败俱伤）；
- pipeline 类预设不进广场（画布工作流配置，非生成素材）；
- 商用授权标记、作者主页、评论、下载量——不做；
- AI 自动生成封面——后续可选增强（现用 `backend/generate_style_previews.py` 思路离线批量产出官方封面）；
- 聊天内生成为后续可接入弹窗的场景，本次不做；
- mobile/ 端不在本次范围。

## 四、方案对比（决策记录）

| 方案 | 做法 | 取舍 |
| --- | --- | --- |
| **A. 扩展 prompt_presets（采用）** | prompt_presets 加封面/提示词配置字段，新增收藏、最近使用两张小表；审核流/导入导出/Fork/热度全部复用 | 工作量最小；五类共表本来就是该表设计意图；风格与特效的差异本质是"分类+应用行为"，不值得分表 |
| B. 全新统一预设表 | 从零设计新表，旧表与约 600 行路由重写 | 模型最干净，但重写审核/导入导出/Fork 不产生新价值 |
| C. 分类型多表+聚合 | 风格表/特效表独立，广场层聚合（preset_aggregator 思路） | 每类可深度定制，但列表/搜索/收藏/审核全部跨表，聚合层越积越厚 |

## 五、数据模型

### 5.1 prompt_presets 扩展（直接按新设计改，不写旧数据兼容）

新增字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `cover_image` | VARCHAR(500) NULL | 封面图 URL（`/uploads/preset-covers/…` 或用户生成记录的 result_url） |
| `prompt_config` | JSON NULL | 提示词配置 `{ prefix, suffix, negative_prompt }`，style / effect / prompt 三类共用 |
| `is_official` | BOOLEAN 默认 0 | 官方卡标记：种子数据与管理员创建置 1，广场"推荐"排序官方优先，卡片带官方角标 |

类型体系：`type` 在原有 camera/prompt/style/script/pipeline 基础上**新增 `effect`**（特效与风格语义不同：视频镜头效果 vs 画面风格，分类导航与应用上下文都不同，值得独立类型）。

### 5.2 新表 preset_favorites

`id, user_id, preset_id, created_at`，UNIQUE(user_id, preset_id)。

### 5.3 新表 preset_recent_uses

`id, user_id, preset_id, last_used_at, use_count(默认 1)`，UNIQUE(user_id, preset_id)。

同步更新 alembic 迁移 / init_db 建表流程；`frontend/src/types/preset.ts` 的 `PresetType` 与字段同步。

## 六、后端 API（`backend/app/routes/prompt_presets.py` 扩展）

| 接口 | 说明 |
| --- | --- |
| `GET /api/presets` | 新增查询参数：`tab=plaza(默认)\|favorites\|recent`、`type`（支持逗号分隔多类型）、`category`、`q`（名称/描述/标签/作者昵称模糊匹配）、`sort=new\|hot\|name`、分页。plaza 仅返回 `is_public=1 AND is_approved=1`；favorites 联表 preset_favorites；recent 联表 preset_recent_uses 按 last_used_at 倒序。响应附 `is_favorite`、`cover_image`、`author_nickname`（联 users） |
| `POST /api/presets/{id}/favorite` | 收藏/取消收藏 toggle，返回 `{is_favorite}` |
| `POST /api/presets/{id}/use` | upsert preset_recent_uses（use_count+1、last_used_at=now）+ `usage_count+1` |
| `POST /api/uploads/image`（新增） | 通用图片上传：multipart，登录即可用，限 jpg/png/webp、≤5MB，存 `backend/uploads/preset-covers/`，返回 `{url}`（沿用 auth.py 头像上传的存储写法） |

- 创建/编辑预设的 schema（`schemas/`）补 `cover_image`、`prompt_config` 字段；
- 投稿（submit）/ 审核（admin_review）/ Fork / 导入导出：沿用现有逻辑不动；
- 分类候选值不做字典表：category 仍是自由字符串，候选列表由前端常量（i18n）提供，筛选 chips 从返回数据的 distinct category 生成。

## 七、应用行为（核心交互）

弹窗中点击卡片 → 详情层（大封面、名称、作者、描述、提示词预览、应用、收藏、Fork）→ 点"应用"：

| 类型 | 生图页（ImageView） | 生视频页（VideoView） |
| --- | --- | --- |
| style | `prefix + suffix` 追加到 prompt 输入框 | 同左 |
| effect | 不展示（context=image 时 effect 类型隐藏） | 追加到 prompt 输入框 |
| prompt | `prompt_text` 追加（不再整段覆盖） | 同左 |
| camera | 不展示 | `camera_params` 回填为"已选运镜"标签（可清除），提交时随请求发送，后端 `build_camera_prompt_suffix` 拼接（已有能力） |
| script | `script_text` 复制到剪贴板并提示（当前无脚本消费场景） | 同左 |

- **追加规则**：输入框为空直接填入；非空用中文逗号衔接；不做片段去重（简单直接，避免误删用户内容）；
- **负面词**：`negative_prompt` 仅生视频页填入负面词输入框（Agnes Video 支持）；生图侧忽略（Agnes Image 无负面词参数，见风格库增强设计 1.3 的能力边界）；
- 应用成功即调 `POST /use` 记录使用；生成请求仍按现状透传 `preset_id` 落 `generations` 表；
- `PresetQuickPanel.vue` 由新弹窗取代并删除。

## 八、前端结构

| 文件 | 动作 | 职责 |
| --- | --- | --- |
| `components/presets/PresetGallery.vue` | 新增 | 核心画廊组件：主 tab（广场/我的收藏/最近使用）+ 类型 chips + 分类 chips + 搜索框 + 排序 + 卡片网格（封面、名称、作者、使用数、星标收藏、hover 快速应用）。props：`context: 'image' \| 'video' \| 'admin'`（决定默认选中类型与类型可见性：image→默认 style，可见 style/prompt/script；video→默认 effect，可见 effect/style/camera/prompt/script；admin→默认 style，可见除 pipeline 外全部五类；pipeline 任何入口都不进广场） |
| `components/presets/PresetDetailDialog.vue` | 新增 | 卡片详情 + 应用按钮（按类型渲染不同应用动作） |
| `components/presets/PresetPlazaDialog.vue` | 新增 | el-dialog 包装 Gallery，生成页弹出 |
| `views/presets/PresetCenter.vue` | 重构 | 上半区 Gallery（context=admin）+ 管理区（我的预设：编辑/删除/投稿/导出；管理员：待审核列表，沿用 admin_review） |
| `stores/presets.ts` | 扩展 | fetchPlaza / fetchFavorites / fetchRecent / toggleFavorite / applyPreset（应用动作收敛在 store，页面只接结果） |
| `views/ImageView.vue` | 改造 | 删除 `imageTemplates` / `appendStylePrompt`；工具栏加"风格库"按钮 → PresetPlazaDialog(context=image)，应用结果写入输入框 |
| `views/VideoView.vue` | 改造 | 删除 `videoTemplates`；加"特效库"按钮 → PresetPlazaDialog(context=video)；增加"已选运镜"标签展示与清除 |
| `components/PromptTemplates.vue`、`components/presets/PresetFilterSidebar.vue`、`PresetQuickPanel.vue` | 删除 | 职责被 Gallery 取代 |

- 全部新文案进 i18n（`zh-CN.ts` / `en-US.ts`），不硬编码；
- 封面"从生成记录选图"：编辑器内拉取当前用户 `GET /api/history`（图片类）缩略图列表供点选。

## 九、种子数据（`backend/seed_plaza_presets.py`，幂等：按 type+name 存在即跳过）

- **官方风格约 20 个**：生图/生视频页 13 个硬编码风格 + `style_presets` 12 个内置风格（visual_prefix/lighting/color_palette/quality_suffix 合成 `prompt_config.suffix`，negative_prompt 保留），按语义去重；
- **官方特效约 12 个**：对标 LiblibAI 特效广场命名转成中文视频 prompt 模板（穿云而入、俯冲地球、环绕运镜、希区柯克变焦、子弹时间、慢动作推近、无人机俯瞰…）；
- 官方卡统一 `is_official=1, is_public=1, is_approved=1`，user_id 置空或系统管理员（以现有列 nullable 实情为准，官方判定只看 is_official）；
- 封面：优先复用 `generate_style_previews.py` 产物；无图卡片前端按类型图标 + 渐变底占位；
- 管理员在管理页创建/编辑预设时自动置 is_official=1，可持续运营官方内容。

## 十、错误处理

- 封面缺失 / 加载失败：卡片回退为类型图标 + 渐变底占位，不阻塞列表；
- 收藏 / 使用记录接口失败：不阻塞"应用"主动作，静默降级（控制台告警）；
- 剪贴板复制失败（script 类）：弹窗内展示全文 + "手动复制"提示；
- 封面上传超限 / 格式错误：编辑器表单内即时提示；
- 未登录收藏 / 使用：沿用现有 401 → 跳登录流程。

## 十一、测试

- 后端 pytest（`backend/tests/`）：favorite toggle 幂等且互斥、use 的 upsert 计数正确、列表接口 tab/type/category/q/sort 组合过滤、plaza 不泄漏未审核内容、投稿审核流回归；
- 前端：类型检查 + 构建 + 手动验收清单（弹窗三 tab、收藏同步、五类应用行为、管理页编辑/投稿/导入导出、管理员审核）。

## 十二、文档同步

- `API.md`：补预设列表新参数、favorite/use/uploads 三个新接口；
- `CHANGELOG.md` Unreleased 追加；
- 数据库表结构变更同步到相关文档。

## 十三、关联文档

- [风格库增强设计（画布侧，本次不动）](2026-06-27-style-library-enhancement-design.md)
- [phase2-prompt-preset-dev-doc](../../phase2-prompt-preset-dev-doc.md)
