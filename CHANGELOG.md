# Changelog

本文件记录 Agnes AI Platform 的所有版本变更。格式参考 [Keep a Changelog](https://keepachangelog.com/)。

## [Unreleased]

### 技能生态二期：整包导入 / Agent 处理双模式
- **入口收敛**：推倒技能"手输 + 模板生成"路径——编辑器新建类型不再提供 skill、删除"填入模板"（`utils/skillTemplate.ts` 删除）；技能创建只剩「上传技能」整包导入与对话 Agent 创作/转译（一期链路保留）两种
- **整包导入（ZIP/文件夹）**：`SkillImportDialog` 重写——选择文件夹（webkitdirectory）或 ZIP（新增 `fflate` 解压），须含 SKILL.md（YAML frontmatter name/description）；其余文本文件存为附件资源 `prompt_config.resources`（脚本仅存档不执行；二进制/超限跳过，单文件 10 万字符/总量 30 万字符/最多 50 个）；解析预览（资源清单/警告）确认后**直接落库**并刷技能缓存，导入即用，同名冲突报错
- **渐进披露 L3**：列表接口（tab≠mine）剥离 `prompt_config.resources`（`_to_plaza_item` 加 `slim_skill`），技能缓存只背 L1/L2；新增 `agent_read_skill_file` 工具（画布 read 组 + chat 工具组末位，共享 `readSkillResource`，单次读取 2 万字符截断），`agent_load_skill` 结果附加资源清单引导按需读取；详情接口承载 L3 按需拉取
- **allowed-tools 声明式权限**：frontmatter `allowed-tools` 解析映射到产品工具名（原始值存 import_meta），非空时内核 `beforeToolCall` 强制收窄（两种宿主生效，load/read 技能工具豁免；映射为空不限制）——内核改为始终挂载 beforeToolCall，宿主工具组模式围栏外全放行
- **技能启用开关**：预设中心"我的预设"技能行 el-switch 写 `prompt_config.disabled`，停用后 `buildSkillsSection`/`filterSkills`/load 全部过滤；编辑器保存技能时合并既有 prompt_config，不再抹掉 import_meta/resources/allowed_tools/disabled
- **种子与文档**：`seed_plaza_presets.py` 格式规范段改为"附件资源存档、脚本不执行"边界，「技能转译」资源引用规则更新（整包资源可 agent_read_skill_file 读取辅助转译）；`docs/skill-authoring-guide.md` 重写为双模式指南；i18n 中英同步
- **审核侧可见性加强**：预设审核列表只含索引信息（PresetIndex，无正文/资源），审核者此前只能看到描述一段——新增 `GET /api/admin/review/preset/{item_id}/detail`（reviewer 鉴权，item_id 经 PresetIndex→preset_id 映射回预设本体，返回全文 prompt_text 与完整 prompt_config）；统一审核页详情弹窗对预设类型拉取详情渲染：技能类型显示审核要点警示（诱导越权/伪造系统提示/外链/积分消耗检查项）+ 概览标签（正文字数/资源数/脚本数/工具白名单或"不限制"/来源）+ 全文正文 + 附件资源逐个折叠查看原文（脚本标红）+ 导入溯源 JSON；列表类型列补预设子类型标签（技能/风格/提示词…）便于一眼识别技能条目
- **测试**：skillImport 解析重写为整包断言（frontmatter/资源/二进制跳过/allowed-tools 映射/上限），新增 load/read 工具与内核围栏用例

### 技能生态一期：Agent 技能创作/转译 + 保存工具 + 导出
- **agent_save_skill 共享工具**：技能库共享实现（`skills.ts`：name/description/正文必填校验、正文 2 万字符上限、同名拒重（trim+大小写不敏感）、落库 `source=agent_created`、保存后刷技能缓存当前会话立即可用），画布（write 组，confirm/auto 直通、只读档拒绝）与对话页两处内核注册
- **官方种子技能 ×2**（`seed_plaza_presets.py`，category=元技能）：「技能创作」访谈式起草→草稿确认→落库收尾话术；「技能转译」外部技能（主流 Agent 技能格式）能力映射改写（脚本剔除或改写为方法论步骤、文件引用并入、外部工具引用映射内置工具或删除、外文转中文、description 重写触发句式）+ 转译报告 + `import_meta` 溯源；两者共用格式规范段
- **手动路径引导（去重设计）**：技能创建统一收敛到预设编辑器一个表单——手动填写、"填入模板"（`utils/skillTemplate.ts`，格式规范与种子文案一致）、SKILL.md 导入解析后填入表单三条路共享同一确认点，技能同名查重统一在提交时做；编辑器技能形态加编写引导与三条路径互相指引、description 必填、技能正文专属 label/占位；SKILL.md 导入弹窗精简为"解析预览（来源可信提示、frontmatter 要求、附件并入、脚本跳过→引导 Agent 转译）→ 填入新建表单"，不再直接落库；修复编辑器 `presets.editor.tagLabel/tagPlaceholder` 缺失 key（裸 key 遗留 bug）；预设中心 JSON 批量按钮改名"导入 JSON/导出 JSON"消除双"导入"歧义；i18n 中英同步
- **技能导出**：`utils/skillExport.ts` 技能卡→SKILL.md（yaml 序列化 frontmatter，与导入解析互逆）+ 预设中心"我的预设"技能行导出按钮（useDownload 触发下载）
- **类型放宽**：`prompt_config.import_meta` 放宽为 `Record<string, unknown>`（容纳转译溯源自由结构；原仅导入路径写入、无读取方）
- **测试**：新增 saveAgentSkill/工具执行器/导出互逆单测，前端 vitest 174 例全绿

### 修复：对话模型提示被丢弃 + 运行失败静默（实测三会话并发中暴露）
- **透传 schema 补 `model` 字段**：`AgentCompletionsRequest` 此前没有 `model` 字段，Pydantic 直接丢弃前端的模型提示——`_resolve_stream_model` 的注册表匹配成为死代码，模型胶囊选择从未生效，所有请求走默认解析链；默认链选中"注册表第一个"若上游无通道（如 doubao-seed-2-1-turbo-260628）即 503→502，会话静默死亡。补字段后胶囊选择真实生效
- **错误按会话可见**：`error` 全局字段改为 `errors`（按会话存储，`activeError` getter），消息区尾部新增错误行（画布面板同款）——此前运行失败前端无任何展示，用户只看到"没有回答"
- **内核补齐缺失的 usage**：上游偶发不回传 usage 块时，assistant 消息的 `usage` 为 undefined，机制层下一回合的上下文估算（`calculateContextTokens` 读 `usage.totalTokens`）抛 TypeError，该会话从下一跳起静默停摆（即"多轮对话第二轮必停"）。内核在 message_end/restore/send 收尾三处归一化补零值；实测旧存量会话恢复后可正常续聊
- **坏形状上下文归一化 + 卡死复位**：行重建的上下文（`chatContextFromRows`）此前的 assistant 消息为字符串内容且缺 stopReason/usage，restore 后消息转换/估算读 `.length` 抛错——重建函数改产 pi 内部形状；内核 `normalizeContext` 三处兜底（content 字符串块化、补 stopReason/usage）；pi 异常路径可能把 `isStreaming` 卡在 true 导致该会话后续发送被静默吞掉，send 前置 `abort()` 强制复位
- 实测验收（浏览器自动化）：三会话同时各跑一轮生成全部成功，`runningSessions` 三路并行、各自回复落库

### 多会话并行生成（对话页）
- **per-session 内核池**：`chat store` 从单内核 + serialize/restore 热切换改为每会话一个 `AgentKernel` 实例（模块级 WeakMap 池，上限 8 个 LRU 淘汰非运行内核），各内核独立持有 LLM 上下文——**多会话可同时各跑一轮生成，切换会话纯视图切换**，彻底修复此前"流式中切会话被 abort、回答丢失"
- **状态按会话归属**：`sessionMessages`（各会话内存消息数组，活跃会话与视图同引用）、`runningSessions`（运行态+思考指示，busy/thinking 改为活跃会话维度的 getter）；内核事件按创建时绑定的会话路由；done 按归属落库（`_persist` 参数化）；媒体轮询登记归属会话、跨会话续跑
- **新内核缺席恢复**：被淘汰/首次使用的会话在发送前从后端拉 context（缺省从消息行重建）；删除运行中会话先终止其内核，残余事件由会话存在性检查忽略
- **侧栏生成中角标**：`ChatSessionView.generating` + `isRunning(id)`，正在生成的会话在列表显示转圈标记

### 对话页观感对齐画布 Agent
- **「思考中…」指示行**：消息区尾部在 busy+thinking 时显示转圈指示（复用 agent.thinking 文案），LLM 延迟/思考阶段不再只有空泡；画布面板此前已有，对话页补齐
- **步骤标签文案修复**：工具步骤标签改用画布同款 agent.actGenImage/actGenVideo/actLoadSkill 键（原引用的 chat.tool* 键不存在，界面会露原始 key）；加载技能标签带技能名（与画布同款「加载技能：名称」）

### 三期内核统一：对话页宿主化到前端 Agent 内核
- **内核泛化**：`AgentKernel` deps 增加可选 `tools`/`toolContext`——宿主自带工具组时无阶段门（工具全放行）、ctx 由宿主提供，画布宿主路径不变（16 工具 + 三档权限 + 阶段门）
- **chat 工具组**：generate_image/generate_video 前端执行（images/videos tasks 端点提交 + taskQueue 注册 + 立即返回 pending，不阻塞回合；媒体占位/轮询/media-callback 机制沿用）；参考图经 ChatToolContext 取「最近成功生成媒体」（图生图/图生视频会话连续性）；preset_ref 预设合并（prompt_text 在前）；agent_load_skill 复用技能模块
- **chat 系统提示**：后端 persona 三层/五层级规则原文迁移前端 + 技能清单段组装（渐进披露）——**对话页从此有技能**（清单注入 + agent_load_skill + 输入条 "/" 快速清单）
- **chat store 换内核**：SSE 事件投影 → 内核事件投影（消息 content+steps+media_items）；发送签名 send(text, attachments)（base64 图进内核多模态、URL 类渲染卡片）；落库切 PUT agent-sessions 全量同步（session_type=chat，后端通道放宽 chat/canvas）；存量会话无 context 时从消息行重建内核上下文（文本+附图块）续聊无损；自动总结标题（首轮 done 后标题为空调 summarize）
- **"/" 技能清单抽共享**：useSlashSkills 组合式 + ChatSkillMenu 共享组件（画布面板与对话页同款交互）
- **画布 Agent 补 AI 总结标题**：大面板侧栏菜单复用 summarize 端点（未同步时提示）——**话题总结两端对齐**
- **范围修正**：后端编排端点原计划退役，实施时发现还有画布侧消费者（CanvasNodeComposer 文本节点对话、CanvasView 图片反推），保留为画布节点会话专用，其迁移另行立项
- **测试**：前端 159 例 vitest 全绿（新增 chat 工具/投影/同步/存量重建 13 例）；后端 32 例 pytest 过（agent-sessions 通道放开 chat 类型）

### 画布会话落库与全局对话列表打通（二期·数据层）
- **表结构**：`chat_sessions` 加 `session_type`（chat/canvas）/`workspace_id`/`context`（内核 serializeState 原样，恢复唯一可信源，每轮全量覆盖）三列；`chat_messages` 加 `steps`（画布工具步骤时间线），用户附图复用 attachments。项目未上线，直接改表无迁移
- **端点**：`POST/PUT/GET /api/chat/agent-sessions`——创建 / 全量同步（事务内消息行整体替换，幂等）/ 恢复单请求（context+消息）；未登录 401、他人 404；删除/重命名/AI 总结标题复用现有端点
- **前端同步链路（数据库为准+本地兜底）**：每轮结束静默同步（无 backendId 先创建再 PUT，失败静默降级 localforage、成功回写缓存）；恢复后端优先、失败读缓存；meta 列表后端过滤 canvas+workspace 并合并离线未同步会话；会话 id 后端恢复态为 `b{backendId}` 跨设备稳定；删除/重命名连后端
- **全局列表打通**：对话页列表显示画布会话（Cpu 角标+tooltip），点击跳 `/canvas?workspace&session` 定位工作区并按 backendId 激活 Agent 会话续聊（跨设备工作区缺失静默忽略——画布内容本身落库属后续项目）
- **测试**：后端 5 例 pytest（往返/替换幂等/列表标识/404/401）；前端 10 例新 vitest（投影/meta 合并兜底/创建回填/定位/降级不阻断）；既有音频合并 1 例失败为存量问题与本次无关

### 画布 Agent 与 AI 对话 UI 整合（共享组件库 + 展开态 + 多会话）
- **迭代（用户反馈）**：权限档位对齐专业 Agent 交互——顶部三按钮段控件改为输入行内「模式胶囊」（图标+名称+下划线箭头），点开下拉菜单逐项给图标+名称+描述+对勾（Esc/点外关闭）；新增「对话模型胶囊」——模型配置可见可切换（列表来自 /api/config 的 chat 模型，显示名+供应商+对勾，选择经 localStorage 记忆并热更新内核 model id，BFF 命中 chat 注册表即真实生效，清空回默认解析链）；ChatInputBar 新增 leading/trail 宿主插槽
- **迭代（用户反馈·小面板自适应）**：360px 小面板下模式胶囊图标化（仅图标+tooltip，菜单不变）、模型胶囊限宽 96px 截断，输入框不再被挤瘪；展开态保持图标+全文本
- **迭代（用户反馈·输入区两行布局）**：输入框独占整行全宽，附件/模式/模型胶囊与发送键收进下方第二行（左：附件+模式胶囊，右：模型胶囊+发送），不再与输入框争宽；两宿主（对话页/画布面板）同步生效
- **共享对话组件库 `components/chat/`**：ChatMessageBubble（双形态：对话页完整形态 / 画布 dense 形态；markdown-it 渲染、附件卡、媒体三态、工具步骤时间线）+ ChatMessageList（滚动锚定、上翻不抢滚动）+ ChatInputBar（Enter/Shift+Enter、IME 守卫、粘贴/拖拽附件、停止键）+ ChatSessionSidebar（数据外部驱动的会话列表）；统一视图模型 ChatBubbleItem，组件零业务依赖，配色走 `--cb-*` CSS 变量（对话页默认 / 画布注入 theme token）
- **ChatView 迁移**：1513 行单文件瘦身为布局壳 + chat store 接线，渲染路径换共享组件；SSE/媒体轮询/落库恢复/URL 识别/AI 总结标题等行为不变；markdown 渲染从正则极简升级为 markdown-it（列表/表格/标题从此可用，html 关闭防注入）；消灭硬编码提示行
- **画布 Agent 展开态**：小面板（360px）一键展开为居中悬于画布上方的大界面（86%×86%，画布不被遮罩仍可点选节点配合 Agent），Esc 收起、localStorage 记忆；展开态带会话列表侧栏
- **画布 Agent 多会话**：`lib/agent/session-store`（meta + data 双 key，存储可注入）+ agent store 会话列表/新建/切换/删除/重命名；标题取首条用户消息截断；切换 = 内核序列化/恢复 + 时间线重建，busy 时禁止切换，删除活跃会话自动切最近一条
- **测试**：新增 markdown 渲染（6 例）与多会话（11 例）单测，既有 agent store 测试适配多会话语义，全量 142 例绿

### 技能 L2：SKILL.md 通用导入 + "/" 快速清单
- **通用导入**：预设中心新增「导入 SKILL.md 技能」——多选 .md/.txt 或粘贴文本，frontmatter（yaml 库解析）映射名称/描述、正文入 prompt_text、其余 md 附件按「## 附件：文件名」并入正文、脚本/二进制明确跳过并报告；同名技能拒绝（按名加载不允许歧义）；source='skill_md' 溯源、原始 frontmatter 与跳过清单记入 prompt_config.import_meta
- **"/" 快速调用**：画布 Agent 输入框草稿以 / 开头弹出技能清单（名称/描述子串过滤、↑↓/Enter/Esc 键盘导航、busy 禁用、空态提示），选中把令牌替换为「【使用技能：名称】」标记行不自动发送；系统提示约定该标记=先调 agent_load_skill 再处理其后内容
- **迭代（用户反馈）**：技能短标识 tag（prompt_config.tag：编辑器可填/导入读 frontmatter tag·alias/官方种子 节奏·台词·一致性）；"/" 菜单改紧凑单行（/短标识 加粗 + 名称 + 描述截断）；filterSkills 相关度排序（tag 全等 > tag 前缀 > 名称前缀 > 包含）边输入边收敛；getCachedSkill 兼容 tag 匹配

- **测试**：新增 skillImport 解析器（6 例）与 filterSkills 用例，全量 121 例绿；新增依赖 yaml

### 画布 Agent 技能机制（Skills）
- **技能 = prompt_presets type='skill'**：name=技能名、description=何时使用（模型可见）、prompt_text=正文——零建表，复用广场/审核/收藏既有体系；管理端 PresetCenter 可创建/审核技能卡
- **渐进披露**：系统提示只注入「可用技能」清单（名称+用途），模型按需调新增 `agent_load_skill`（read 组）取全文注入上下文；技能库为空/请求失败时降级为基础提示不阻塞对话（保留旧缓存）
- **种子**：官方技能 3 条入库（分镜节奏与情绪曲线 / 短剧台词打磨 / 角色一致性技巧），幂等脚本追加
- **测试**：新增 skills 模块单测（拉取映射/降级/技能段渲染）与 load_skill 用例，全量 115 例绿

### 分镜管线统一 Phase 2（项目制迁移 + 接库）
- **AI 编排全部迁前端**：项目制向导四步链（剧本生成→实体提取→分镜拆分→帧提示词）改由 `lib/storyboard` 管线在 ProjectLaunchDialog 本地编排执行（幂等可续跑，已有剧本/实体/分镜自动跳过），完成后项目状态 creating→in_progress；后端删除 `wizard.py`/`wizard_chains.py`/`extract_entities.py` 与 wizard/resume/regenerate/extract-from-script×3/shots/split/generate-frame-prompt 端点（`parse_json_loose`/`call_llm` 抽到 `project/_llm.py` 供字幕/画布服务复用）
- **出图统一**：帧图/实体设定图提交统一走 `POST /api/images/tasks`（前端收集绑定角色激活形象图作参考图、携带项目归档 context 与 camera_params），claim 版本认领机制不变；删除 frame_image_service 的 generate/batch（顺带消灭批量帧图 AttributeError bug）与实体三组 generate-image/batch-generate 端点及请求 schema；视频/TTS 仍走后端通道
- **ShotCard 接库**：ShotsTab 新增项目级画面风格选择器（`prompt_presets` 官方风格条目，`projects.style_config` JSON 列随项目持久化）+「按风格重写提示词」批量动作（buildFramePrompt 逐镜重建）；分镜图生成随运镜词值携带 camera_params；删除 ShotCard 遗留英文键映射（管线产出中文直出）
- **修复**：拆分分镜成功提示读不到数量恒显示"多"的 bug（前端编排返回真实 shot_count）
- **测试**：vitest 108 例绿、pytest 26 例绿（既有音频用例失败与本次无关）

### 收尾清理
- **死目录清理**：删除 `backend/app/services/pipeline/`（步骤执行器源码早已删除，目录仅剩 `__pycache__`，全局无引用）
- **官方风格种子补动画条目**：新增「2D 动画」「3D 动画」官方风格卡（动漫游戏类）——此前用户需求"动画"等宽泛表述只能落到"日式动漫"，语义推荐现可命中具体条目；种子脚本幂等，已在本地库执行（新增 2 条）

### 画布 Agent 多模态输入（图片/文件对话）
- **图片双通道**：面板上传/粘贴/拖拽图片走 `agent.prompt(text, images)` 原生入口（openai-compatible 组 image_url 内容块，provider 模型声明升级 `input: ['text','image']`——这也是工具结果图片能否发给模型的门控）；画布图片节点新增 `agent_read_image` 工具（read 组三档可用），前端拉图转 base64（外域自动走 `/api/proxy/image` 绕 CORS），工具结果带图由 openai-compatible 适配转附加用户消息——Agent 可看画布生成结果/参考图内容并回答
- **文件解析为文本**：txt/md 等文本直读；PDF 用 pdfjs-dist 逐页提取（无文本层/扫描版明确提示）；DOCX 用 mammoth 浏览器构建（子路径无自带类型，经 tsconfig paths 映射本地声明）；以「【文件名】+ 提取文本」拼进消息（截断 2 万字符）。新增依赖 pdfjs-dist@6、mammoth@1，均动态 import 懒加载独立 chunk
- **附件体验**：输入区附件按钮 + 预览条（缩略图/文件名/移除），busy 禁用；图片超阈值 canvas 重编码 JPEG（白底、长边 2048，≤1MB 且长边 ≤2048 原样保留 PNG 透明，压后 >4MB 拒绝）；单条消息上限 4 张；允许空文本只发图；用户气泡显示缩略图（el-image 点击预览），会话恢复 `rebuildTimeline` 还原 image 块；上传图仅进对话上下文，不建画布节点
- **边界与门控**：system prompt 补图片理解引导（"看图/分析图/按图改"必须先读图，禁止凭节点名猜画面）；上游非视觉模型报错走现有 error 路径透出，不做模型能力门控；后端零改动（透传清洗原样放行 image_url、图片代理已有）
- **测试**：新增 attachments 单测（分流/错误归一/提取截断/代理拉图），kernel/tools/store 多模态用例扩展（带图 prompt、工具图块、时间线还原、恢复缩略图），全量 104 例绿

### 分镜管线统一 Phase 1（画布域：前端共享管线模块 + Agent 六阶段实体先行 + 能力库收敛）
- **前端共享管线模块**：新增 `frontend/src/lib/storyboard/`（transport/schemas/prompts/pipeline/library）——实体提取、分镜拆分、一枪出（plan）、成品分镜图提示词（buildFramePrompt）与资产设定图提示词（buildAssetPrompt）唯一模板源；LLM 子调用走 `/api/chat/completions` 流式透传（fetch + SSE 增量累积），transport 可注入（浏览器/Node CLI 通用）。单帧约束由三处重复（Agent system prompt / canvas-storyboard / 后端 shot_service）收敛为一处
- **Agent 升级六阶段**：剧本 → 实体设定 → 分镜提示词 → 分镜图 → 分段视频 → 合成；新增 `storyboard_extract_entities` / `storyboard_split` 工具（成品 prompt 由工具产出，LLM 只编排不撰写）；`agent_run_generation` 新增 kind=asset（实体设定图，独立阶段门「实体设定」）；实体卡复用 image 节点（content.kind/entityName/entityDesc），节点徽标 + 描述编辑小窗；分镜图节点连线命中实体卡，参考图自动收入
- **实体先行进向导**：script 节点资产卡升级为角色/场景/物品三类，分镜表带 props 关联，参考图按镜头命中注入；画布级风格选择（workspace styleConfig：库条目或自定义文本）贯穿设定图/分镜图提示词；Composer/向导全部改调前端管线，`/api/storyboard` 端点与后端 `storyboard_service` 删除
- **能力库收敛**：独立 `camera_presets` 表/路由/前端 API 删除，运镜统一走 `prompt_presets`（type=camera 的 `camera_params`），CanvasCameraPanel/CameraPresetSelector 切统一数据源；`prompt_presets` 新增 `source` 列（外接风格包导入预留，本地开发库需一次性 `ALTER TABLE prompt_presets ADD COLUMN source VARCHAR(50)`）；chat_service 修复两处 `app.services.camera_presets` 坏 import（实为 `camera_prompt`）并删除 CameraPreset 回退解析分支；admin_review 摄像机预设审核并入统一预设服务；透传端点 `model` 字段升级为「命中聊天注册表才采用」（保住对话/分镜模型选择语义）
- **首跑排障修复（2026-09-10 全流程验证后）**：能力库降级容错——预设库拉取失败不再阻断分镜管线（返回临时空库不缓存，恢复后自动重试）；分镜图单帧约束补"画面中不出现任何文字/字幕/台词/标语/水印"（修复分镜图渲染台词条幅）；Agent 风格硬门——style_applied=false 时禁止建实体卡与生成，新增 `storyboard_list_styles` 工具 + `storyboard_extract_entities` 接受 `style_preset_id`（对话式选风格直写画布，补齐 Agent 流程无风格选择器的缺口）；官方运镜词表 11 条入种（camera 类型，此前为 0）；管线子调用 transport 补 max_tokens=4096（缺省导致拆分长 JSON 被上游默认上限截断、storyboard_split 两轮重试全败——首跑深夜场 split 持续报错转手写的根因）；新增 `storyboard_set_style` 工具（库外自定义风格正路：写入画布风格配置进所有提示词风格段，system prompt 明令禁止把风格散写进实体 description 代替——人物画风不统一的直接来源）；透传消息清洗兜底——上游推理模型（agnes-3.0-flash）偶发吐出 id/name 全空的 tool_call，内核回填 "Tool not found" 后畸形 assistant 消息随历史重放被上游 400（Invalid JSON data）拒绝、回合卡死，`open_completions_stream` 发送前剔除空 tool_call 与空 tool_call_id 的孤儿结果（有正文降级为纯文本消息，无正文整条丢弃）；风格协商可视化——`storyboard_list_styles` 返回条目描述与封面，Agent 面板在工具步骤下渲染可点选风格卡片（封面图 + 名称 + 末尾"自定义风格"入口），点选/填写后以用户口吻发消息、Agent 经 set_style 落库继续管线；system prompt 细化协商流程：库里没有 → 明确告知 → 给语义最接近的 2-3 条推荐（说明理由）→ 问"添加自定义还是选推荐" → 用户定后推进
- **测试**：管线模块新增 14 例（transport SSE/解析容错/成品提示词/重试），Agent 工具/策略用例扩展；全量 84 例绿

### 画布 Agent 内核改造（引入机制层框架）
- **机制层替换**：自研 LLM function-calling 循环（stores/agent.ts 约 480 行）替换为机制层框架装配层（`lib/agent/kernel.ts`）——获得流式事件驱动、工具并行执行（多分镜图生成提速）、abort 停止、会话状态托管；策略层（三档权限/阶段门/STAGE_FLOW）下沉为纯函数 `lib/agent/policy.ts`，工具层 8 工具与强制兼容逻辑不动，schema 单源化 TypeBox（OpenAI function 格式由其 JSON Schema 直出，供未来 MCP 桥复用）；store 瘦身为 UI 投影层，面板组件零改动
- **LLM 通道升级流式**：后端 `/api/chat/completions` 由非流式 JSON 改为 SSE 流式透传（httpx stream + StreamingResponse，上游断流补 `[DONE]`、异常下发 error 事件）；该端点为 ok() envelope 特例（流式不包装），前端由 openai-completions 适配解析
- **新增依赖**：`@earendil-works/pi-agent-core@0.85.1`、`typebox@1.3.7`（锁版本）
- **会话持久化**：改为内核消息数组序列化（`serializeState`/`restore`），旧会话数据作废不迁移；恢复时由 `rebuildTimeline` 重建时间线
- **测试**：单测 31 例 → 56 例（内核直测 12 + 策略矩阵 12 + store 投影 14 + 工具层 18）

### 优化精简（2026-09-03 全局代码优化，约 -6,400 行）
- **Bug 修复**：水印 Logo 上传改走登录态 token（原读取不存在的 `access_token` key，鉴权必失败且重登后携带旧 token）；删除 auth.py 重复注册的水印/内容安全死路由；`/chat/media-callback` 补会话归属鉴权（原完全无鉴权可改写任意消息）；流式对话第二轮补传 `user_id` 修复偏好模型两轮不一致
- **死代码删除（约 -4,200 行）**：后端 chat_service 非流式 `chat()`（含 NameError 级 bug）、style/script_template/asset_library 未用 CRUD（各仅剩 1-4 个在用函数）、model_registry 兼容层副本、16 处零散死函数、同步 DB 层（engine/SessionLocal/get_db）、main.py 手写迁移、一次性迁移脚本、6 个孤儿 schema、menu_item 死模型；前端 camera 死链路、pipeline 风格元素组件族 5 组件、canvas.ts 死 action/getter（网格/对齐/剪贴板/待创建连线等）、api 层 14+ 死函数、`VideoStatusResponse` 重复定义与孤儿类型、i18n 孤儿 key；顺带恢复 HistoryView 详情图 `@load` 误删绑定
- **重复逻辑收敛（约 -2,100 行）**：后端项目归属校验依赖注入替换 93 处样板、视频 Range 代理合一（`_media_proxy`）、agnes_client 重试循环与 LLM 取文本（`chat_text`）收敛、admin_review 改用权限依赖、时长计算三合一、历史用户隔离过滤收敛、chat `send_message` 365 行瘦身至 43 行（校验/历史/SSE 编排下沉 chat_service）、会话归属依赖注入、moderation 双审核函数合并、history 下载代理/审核后台任务下沉、`get_history` 改 model_validate、character/scene/prop 剧本提取三合一（`extract_entities`）、实体 schema 九合一、帧图/视频/音频 19 条路由接入工厂、双 poller 公共落库逻辑抽 `_generation_persist`；前端 canvas-generation 四个 execute 复用 runMediaTask、双轮询合一（`pollMediaTask`）、taskQueue 图片/视频提交与注册更新合并、项目轮询归一、上游节点编号三处合一、`isMediaSuccess/Failed` 抽取、`formatTime`/`useCopyText`/`useConfirm`/`fetchBlobAsUrl`/`getIconByName`/`usePromptLength` 全库贯彻
- **规范修正**：taskQueue 持久化 localStorage 换 localforage（消除 5MB 配额写失败被静默吞掉的丢任务隐患）；37 处函数体内 import 上移；裸 dict 入参换 Pydantic schema（set_cover / 管理员开关）；video_poller 假防御、security 永假分支、credits 死变量清理
- **响应结构彻底统一**：全部业务端点（231+）改用 `ok()` envelope（`{status:"success", message, data}`），移除 130 处 `response_model`，HTTP 200 `success:false` 表失败处改 `HTTPException`（错误统一 `{"detail": ...}`），前端拦截器对 envelope 透明解包（组件消费零改动），文件流/SSE/预览不包装

### 功能
- 模型生成能力统一配置（gen_params）：`model_definitions` 新增 `gen_params` JSON 列（启动自动迁移），解析链 = DB 显式配置逐键覆盖 > 按模型名自动画像（seedream 系=关闭「AI生成」显式水印 + 尺寸归一化到方舟 2K/4K 合法档；agnes-image-2.1 家族=参考图≤6）> 无特例默认，已知键由 Pydantic `ModelGenParams` 唯一定义（max_ref_images / watermark_param_off / size_rule / image_sizes / default_size）；`agnes_client` / `agn_sdk_client` 原硬编码特例全部改读配置，`/api/config` 模型项携带解析后的 gen_params，前端参考图截断（图片/视频链路）与 ParamSelector 尺寸选项/默认尺寸改读所选模型配置（缺省回退全局），设置页模型编辑弹窗新增参考图上限/「AI生成」水印/尺寸归一化/默认尺寸四字段（i18n 两语言），模型增改接口透传校验；未来同族新模型同步即自动获得配置、特例在弹窗一配即生效，不再改生成代码。覆盖修复：画布分镜图批量生成参考图 7-8 张被上游 400 拒绝、openai 兼容端点（火山 agent plan）seedream 尺寸原样透传低于最小档且带水印（已实测 plan 端点 1024→2048 归一化生效且无水印；发布内容时按平台规则声明 AI 生成的义务由使用方承担）
- 统一预设广场重构：预设中心改造为风格/特效广场式的卡片画廊（广场/我的收藏/最近使用三 tab + 类型/分类导航 + 搜索 + 排序），生图页"风格库"、生视频页"特效库"弹窗即选即用
- 预设挂载式应用：风格/特效/运镜卡片一键"使用"即挂载到生成模块（标签可移除，风格与运镜单选、特效可叠加），提交生成时系统自动拼接提示词片段与负面词，提示词输入框保持纯用户内容；脚本类复制到剪贴板、提示词类追加输入框
- 官方封面维护：管理员可在预设详情一键 AI 生成封面（`POST /api/presets/{id}/generate-cover`），effect/camera 类型自动走视频 API 生成 4s 动态封面（`cover_video`，卡片悬停循环播放），其余生成静态图（`cover_image`）；或运行 `backend/generate_plaza_covers.py` 批量补齐；用户自建卡支持上传图片或从生成记录选图
- 画风不再硬编码：生图/生视频页 13 个硬编码风格与 style_presets 12 个内置风格收编为官方种子（`backend/seed_plaza_presets.py`，共 37 条官方卡），新增 12 个视频特效模板
- 预设五类统一（style/effect/camera/prompt/script）：`prompt_presets` 新增 `cover_image` / `cover_video` / `prompt_config` / `is_official` 字段，camera 类型不再分流 camera_presets 表
- 新增收藏与最近使用（`preset_favorites` / `preset_recent_uses` 表，favorite toggle + use 上报接口）、通用图片上传接口（`POST /api/uploads/image`）
- `/presets` 管理页重构：画廊 + 我的预设管理（编辑/删除/投稿/导入导出），投稿审核沿用现有 admin_review 流

### 安全
- 移除 `jwt_secret` 不安全默认值，启动时强制校验非空、非默认占位值、长度≥32 字节
- 移除 `encryption_key` 默认空兜底，启动时强制校验非空；`security._derive_key` 不再使用内置默认密钥
- 补全 `.env.example` 缺失变量（JWT_SECRET / SMTP_* / CAPTCHA_* / EMAIL_CODE_* / BACKEND_PORT / LOG_* / NEW_USER_DEFAULT_CREDITS）
- 默认 admin 账号与首位注册管理员 `must_change_password=True`，登录响应与 `/auth/me` 返回该标志；新增 `POST /auth/change-password` 接口（旧密码+新密码），修改成功后清除标志；邮箱重置密码后自动清除标志
- S5（/uploads 鉴权代理）经审查后跳过：avatars 目录受广场匿名浏览硬约束必须公开，watermarked 目录因水印下载接口动态处理未被使用，当前无真正需要鉴权的上传文件

### 性能
- 修复 `system_config_service.get_config_value` 缓存永不过期 bug（增加 60 秒 TTL 检查）
- `moderation_service.check_sensitive_text` 添加进程内 60 秒 TTL 缓存，敏感词增删改后自动清除
- `credits_service._get_rule_value` 添加进程内 60 秒 TTL 缓存，积分规则修改/重置后自动清除

### 可观测性
- `admin_review` 统一审核接口的 9 处静默 `except: pass` 改为 `logger.exception`，保留默认 0 值不破坏前端逻辑

### 工程化
- 建立 `VERSION` 文件（0.0.1）与 `CHANGELOG.md`
- 从 `.gitignore` 移除 `docs/`，设计文档纳入版本控制

### 新增（功能）
- 剧本节点分镜资产一体化：`POST /api/storyboard` 一次 LLM 调用同时输出全剧角色/场景清单与分镜数组，镜头携带 `characters`/`location` 与资产按名关联；请求新增 `scenes` 反向通道（已有资产卡回传，分镜沿用已有设定）；向导步骤①新增场景/出场角色列、步骤②资产卡按名去重自动预填（卡片显示"出现镜头"）、资产参考图为纯设定图 prompt（角色三视图立绘：正面/侧面/背面并排；场景空镜无人物，不注入剧情避免提示词污染）；分镜图派生按镜头命中注入设定文本与参考图（未标注镜头保持全量注入，与旧行为一致）
- 创作内容归档与资产激活
  - 生成记录新增来源标记（`source` / `container_type` / `container_id`），历史默认只显示独立生成，提供来源筛选（独立生成 / 画布创作 / 项目创作 / 全部）
  - 画布与项目生成自动归档进资产库（按创作容器分组），新增归档服务 `asset_archive.archive_to_asset` 与成片归档 `archive_final_video`
  - 资产表新增容器归组字段（`container_type` / `container_id` / `container_name` / `source_generation_id`）与 `kind` / `asset_url`；`type` 扩展 `material` / `clip` / `final`
  - 资产页重构为「创作单元 + 我的资产」两区：创作单元按容器分组、支持单元详情（按类型分栏）、预览、分享到广场（复用审核管道）、删除归档影子记录
  - 新增端点：`GET /api/pipeline/assets/containers`、`GET /api/pipeline/assets/container/{type}/{id}`、`PATCH /api/pipeline/assets/{id}/share`、`DELETE /api/pipeline/assets/{id}`；`GET /api/pipeline/assets` 新增 `scope=my` 仅返回当前用户资产
  - 审核逻辑下沉至 `moderation_service.run_async_asset_moderation` 共用（资产分享与历史分享统一走敏感词 + AI 预审管道）
  - 广场新增「创作」Tab（M4）：`GET /api/plaza/creations` 返回已公开且审核通过的资产，支持 `asset_type` / `kind` / `sort(latest|popular)` 筛选与分页；复用 `asset_likes` 表新增 `POST/DELETE /api/plaza/creations/{id}/like` 点赞/取消与 `GET /api/plaza/creations/likes/status` 批量状态查询；`GET /api/plaza/creations/{id}` 详情浏览量自增；前端 `PlazaView` 增加作品/创作双 Tab、类型标签、点赞按钮与创作详情弹窗
  - 资产「用于生成」闭环（M5）：`POST /api/pipeline/assets/{id}/use` 记录使用并递增 `use_count`；资产卡「用于生成」写入 Pinia `pendingUse`，跳转生图/视频页在 `onMounted` 预填参考图/视频并调用 use 接口；替换「功能开发中」占位文案并补充 i18n（zh-CN / en-US）
  - 生成配置下放 Phase A：模型与参数选择从硬编码/默认值下沉到每个生成入口
    - 默认值链统一：`modelsStore.getDefaultModel(type)` 优先级为偏好默认模型（校验存在且类型匹配）> 该类型列表第一个；`defaultImageModel` / `defaultVideoModel` 改为其封装，全链路消费方零改动即获得偏好感知；偏好字段拆分为 `default_image_model_id` / `default_video_model_id`，偏好页新增"默认生图/生视频模型"两个下拉（原 `default_model_id` 从未有 UI 入口）
    - 新增 `ComposerParamBar`：复用 `ParamSelector` 的选项逻辑，只做驼峰↔蛇形字段适配与 content 持久化（支持 `contentKey` 分区）；image / video / config 三类节点 Composer 接入，config 节点原生 select 整体替换后字段名与读写路径不变，`executeMerge*` 零改动
    - script 节点新增分镜聊天模型选择（存 `content.chat_model`）；`POST /api/storyboard` 新增可选 `model`，命中 chat 模型注册表时使用指定模型，未传或未命中回退第一个 chat 模型
    - 剧本向导步骤② 新增资产图参数栏、步骤③ 新增分镜图/分镜视频批量参数区，按 `asset_image_params` / `shot_image_params` / `shot_video_params` 分区持久化到 script 节点；批量派生与单镜头重拍改为同源读取，视频时长优先级为参数栏显式选择 > 镜头表格时长，视频 `aspect_ratio` / `resolution` / `frame_rate` 不再硬编码
- 分镜直出 B1 地基与派生切换：脚本批量派生分镜图不再产生 config 中间节点，每镜头直接创建 1 个可生图的图片节点（prompt/模型/参考图/lineage 内嵌节点，结果就地回填 `content.content`）；**视频派生同样直出**：批量/单镜头直接创建视频节点（参数/源分镜图/lineage 内嵌，视频地址回填节点自身），不再产生"摄像机控制"config 节点，视频节点按行内列位排在分镜网格右侧专属区（B2 改覆盖式布局）；`findDerivedPanels` 同时识别直出节点与存量 config 派生（幂等不重复派生）；`getShotLineageInfo` 兼容直出节点（镜头徽章与派生/重拍按钮可用）；直出节点重试走就地执行（保留模型/参数/参考图/源图）；批量失败汇总提示（补 `batchImagesFailed` / `batchVideosFailed` 文案）
- Provider 协议兼容接入与模型手动停用（配置管理页）：新增 Provider 表单的 Adapter 类型改为分组下拉——「协议兼容接入」组提供 OpenAI 接口协议兼容 / Anthropic 接口协议兼容（自定义端点，走 aibridge `openai` / `anthropic` adapter + 自定义 base_url，已用 mock 服务验证 list_models / image_generate 链路），原厂商列表归入「厂商适配器」组；模型列表新增手动停用/启用（`model_definitions` 新增 `is_disabled` 列，启动自动迁移加列）：停用模型不出现在生成页模型列表（`refresh_models_cache` 过滤 `is_disabled`），模型同步永不修改 `is_disabled`（修复原同步会把手动停用的模型自动重新激活的问题），模型表格状态列三态（已激活/已停用/已下线）、行内停用/启用按钮、默认隐藏已停用模型（「显示已停用」开关控制），编辑弹窗"激活"开关改为"启用模型"（对应 `is_disabled`），`PUT /api/models/{model_id}` 支持 `is_disabled` 参数；模型表格新增多选批量操作（批量停用/启用 `PUT /api/models/batch`、批量删除 `POST /api/models/batch-delete`，单次请求 + 单次缓存刷新）、类型筛选（全部/图片/视频/对话）与模型 ID/显示名称/类型/供应商列排序；Provider 编辑弹窗在输入框下方显示已保存的掩码 API Key（原来编辑时无任何已填充提示），模型表格新增「所属 Provider」列（按 provider_id 反查配置的 Provider 名称，区分多 Provider 接入同一供应商的模型）；修复表格固定操作列半透明底色透出滚动内容的问题（主题色均为半透明，改用「半透明主题色叠层 + 实色底」在固定列上合成不透明背景，普通/斑马纹/悬停/表头四态逐层对齐），统一操作按钮风格（删除改为 plain 描边、停用/启用补充图标，Provider 表格操作补齐图标并加宽到单行布局）；模型同步失败不再静默返回空列表——`AGNSDKClientWrapper.list_models` 失败改为抛出中文错误（认证失败/路径不存在等），同步接口以 502 透出 detail 给前端提示，避免"同步成功但 0 个"无线索的假成功；Provider 表格默认列改为可点击的「设为默认」链接，操作列新增「添加模型」（打开模型弹窗并预选该 Provider，适配方舟 Agent Plan 等不提供 /models 接口、需手动录入模型名的端点）
- 对话模型配置化（消除硬编码，支持模型迭代随时切换）：新增两级配置——用户偏好「默认对话模型」（`generation.default_chat_model_id`，覆盖分镜脚本/剧本聊天/项目向导/镜头/角色/场景/道具/字幕等创作环节，解析链为显式指定 > 用户偏好 > 系统默认 > 注册表第一个）与管理员「模型服务配置」页（`/admin/system-models`，system_configs 新增 `model.chat_default` / `model.moderation_chat` / `model.title_summary_chat`，覆盖审核、标题总结等系统级任务与全局兜底，`PUT /api/admin/system-config/models` 带注册表校验）；清零全部 `agnes-2.0-flash` 硬编码与"第一个 chat 模型"硬依赖（wizard 步骤显式模型仍然优先），非流式遗留 `chat()` 走系统链，流式聊天跟随会话用户偏好；解析链逐级校验模型仍在注册表中（偏好/管理员配置/显式指定指向已停用或已下线的模型时自动落到下一级），全部落空时各调用点快速报中文错误（审核安全降级放行、标题总结静默降级），不再把空模型名或失效模型名发往上游

### 修复（归档功能验收问题）
- 分享审核闭环断裂：资产分享后无人复审则永远无法上广场——统一审核后台（列表/通过/驳回/统计/批量）新增 `asset` 类型，`UnifiedReview` 增加资产 Tab 与图片/视频预览
- 剧本分镜图/分镜视频误归入「画布」容器：画布生成执行器读取节点 `lineage`，有剧本来源时归档到 `canvas_script` 容器并按 `#镜头号` 命名
- 项目制归档丢失产物类型/名称：`submit_image_task` / `submit_video_task` 增加 `asset_type` / `asset_name` 透传，角色/场景/道具参考图、分镜帧图、镜头视频按产物归档
- 历史页「存为资产」放开到所有成功记录（自动归档失败的补存兜底）；手动保存按 `source_generation_id` 幂等去重，重复点击不再产生重复资产
