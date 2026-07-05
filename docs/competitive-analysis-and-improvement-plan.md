# 竞品对比分析与精进方案

> 本文对三个开源 AI 视频生成项目（OpenMontage / MoneyPrinterTurbo / Pixelle-Video）进行深度分析，对比 agnes-platform 现有能力，提出分阶段的精进路线图。

---

## 目录

- [一、三个项目对比速览](#一三个项目对比速览)
- [二、OpenMontage 项目深度分析](#二openmontage-项目深度分析)
- [三、MoneyPrinterTurbo 项目深度分析](#三moneyprinterturbo-项目深度分析)
- [四、Pixelle-Video 项目深度分析](#四pixelle-video-项目深度分析)
- [五、agnes-platform 现有能力盘点](#五agnes-platform-现有能力盘点)
- [六、明显缺失或简陋的功能点](#六明显缺失或简陋的功能点)
- [七、精进建议（按优先级排序）](#七精进建议按优先级排序)
- [八、落地路线图](#八落地路线图)
- [九、最值得立刻借鉴的 5 个点](#九最值得立刻借鉴的-5-个点)

---

## 一、三个项目对比速览

| 维度 | **OpenMontage** | **MoneyPrinterTurbo** | **Pixelle-Video** |
|---|---|---|---|
| **项目定位** | Agent 驱动的端到端视频生产工作室 | 全自动短视频生成（主题→成品一条龙） | ComfyUI 驱动的 AI 短视频引擎 |
| **核心理念** | "AI 编码助手即编排器"——无 Python 编排层 | 关键词→文案→素材→配音→字幕→合成→发布 | 模板方法 Pipeline + 工作流插件机制 |
| **技术栈** | Python 工具 + Remotion/HyperFrames + FFmpeg + AI Agent | FastAPI + Streamlit + FFmpeg + Edge TTS | FastAPI + Streamlit + Playwright + ComfyKit |
| **编排方式** | YAML manifest + Markdown skill（指令驱动） | 硬编码 services/task.py 流程 | LinearVideoPipeline 模板方法 + PipelineContext |
| **素材来源** | 真实素材库（Archive/NASA/Wikimedia）+ AI 生成 | Pexels/Pixabay/Coverr 多源聚合 | ComfyUI 工作流 + 直连 API 双后端 |
| **TTS** | ElevenLabs / Google / OpenAI / 本地 Piper | Edge TTS（免费默认）/ Azure V2 / MiMo | Edge TTS / Index-TTS（支持声音克隆） |
| **字幕** | Remotion 数据驱动字幕 | edge/whisper 双模式（快/准） | HTML 模板字幕（Playwright 截图） |
| **独特亮点** | 7 维度评分选型 + 预算治理 + Pre/Post 质量门 | 跨平台发布（TikTok/IG/YouTube）+ 视频理解 | ComfyUI 原生 JSON 占位符约定 + 工作流自动扫描 |

---

## 二、OpenMontage 项目深度分析

### 2.1 项目定位

**OpenMontage 是首个开源的"智能体驱动（Agent-orchestrated）视频生产系统"**，采用 AGPLv3 协议。

**解决的核心问题：**
- 传统 AI 视频工具大多只能"从一个提示词生成一段短视频片段"，无法完成端到端的完整制作流程
- OpenMontage 把 AI 编码助手（Claude Code / Cursor / Copilot / Windsurf / Codex）变成一个**完整的视频制作工作室**，用自然语言描述需求，Agent 自动完成调研、剧本、资产生成、剪辑、合成全流程
- **关键差异化**：既能做"基于图片的动画视频"，也能做**真正的实拍视频**——从免费/开放素材源（Archive.org、NASA、Wikimedia Commons、Pexels 等）建立 CLIP 检索语料库，检索真实运动镜头，剪辑成片

### 2.2 核心功能模块

#### 12 条生产流水线（Pipelines）

每条都是端到端的完整制作工作流：

| 流水线 | 用途 |
|---|---|
| Animated Explainer | AI 解说视频（教育/教程） |
| Animation | 动效图形、动态排版 |
| Avatar Spokesperson | 数字人讲解视频 |
| Cinematic | 电影预告片/品牌片 |
| Clip Factory | 长视频批量切短视频 |
| Documentary Montage | 真实素材纪录片剪辑 |
| Hybrid | 真实素材 + AI 生成合成 |
| Localization & Dub | 字幕/配音/多语言翻译 |
| Podcast Repurpose | 播客精华转视频 |
| Screen Demo | 软件演示/录屏 |
| Talking Head | 真人讲述视频 |
| Character Animation | 本地 SVG 角色动画（HyperFrames 渲染） |

#### 52+ 生产工具（按类别组织在 `tools/` 下）

- **视频生成（18 个）**：Kling、Runway Gen-4、Google Veo 3、Grok Imagine Video、Higgsfield、MiniMax、HeyGen，以及本地 GPU 方案（WAN 2.1、Hunyuan、CogVideo、LTX-Video）+ 免费素材源（Pexels/Pixabay/Wikimedia）
- **图像生成（13 个）**：FLUX、Google Imagen、Grok、GPT Image 2、Recraft、本地 Stable Diffusion、ManimCE 数学动画等
- **TTS（4 个供应商）**：ElevenLabs、Google TTS（700+ 声音）、OpenAI TTS、本地 Piper（完全免费）
- **音乐/音效**：Suno AI、ElevenLabs Music/SFX
- **后处理**：FFmpeg 合成/编码/字幕烧录、Video Stitch、Audio Mixer、Color Grade（LUT）
- **增强**：Real-ESRGAN 超分、rembg 抠图、CodeFormer/GFPGAN 人脸修复
- **分析**：WhisperX 转写、Scene Detect、Frame Sampler、CLIP/BLIP-2 视频理解
- **数字人**：SadTalker/MuseTalk、Wav2Lip 唇形同步

#### 三层渲染引擎

- **Remotion**（React/Node.js）：数据驱动解说器、动态字幕、TalkingHead 合成
- **HyperFrames**（HTML/CSS/GSAP）：动态排版、产品宣传、SVG 角色动画、网站转视频
- **FFmpeg**：核心视频组装、编码、字幕烧录、音频混合

#### 400+ Agent Skills 知识包

Markdown 指令文件，教 Agent 像专家一样使用每个工具。

### 2.3 功能优势

#### 1. Agent-First 架构——没有 Python 编排器

> "There is no code orchestrator. Your AI coding assistant IS the orchestrator."

这是最大创新点。Python 只提供工具和持久化，所有编排逻辑、创意决策、审查、阶段切换都活在**可读的指令文件**（YAML manifest + Markdown skill）里。这意味着：
- 用户可以审查和定制每一条规则
- 不依赖黑盒后端
- 任何能读文件、执行 Python 的 AI 助手都能驱动它

#### 2. 零 API Key 也能产出真实视频

开箱即用 `make setup` 即获得：Piper TTS、Archive.org/NASA/Wikimedia 公共素材、Remotion/HyperFrames 渲染、FFmpeg 后期。三条"免费路径"：
- 基于图片的动画视频
- 本地角色动画（SVG 骨骼 + GSAP）
- 真实素材纪录片（免费素材 + CLIP 语义检索）

#### 3. 真实素材纪录片模式（独家）

不是"静态图片 Ken Burns 效果冒充视频"，而是从 Archive.org、NASA、Wikimedia Commons 建立 CLIP 语义检索语料库，按主题检索真实运动镜头，刻意剪辑成片。

#### 4. 参考视频驱动创作（Reference-Driven）

粘贴 YouTube/Reel/TikTok/本地视频作为参考，Agent 会分析转写、节奏、场景、关键帧、风格，产出：
- 保留什么（节奏、Hook 风格、结构）
- 改变什么（主题、视觉处理、解说）
- 在目标时长下的成本预估
- 在当前可用工具下实际效果

#### 5. 生产级质量治理（Production Governance）

这是工程化最亮眼的部分：
- **Pre-compose 校验门**：违反交付承诺（如"motion-led"视频 80% 是静态图）、PPT 风险评分过高、渲染器缺失 → 阻断渲染
- **Post-render 自审查**：ffprobe 校验、4 处抽帧检测黑帧/破图、音频静音/爆音分析、字幕检查，不过审不输出
- **6 维度 PPT 风险评分**：防止"动态 PPT"式输出

#### 6. 7 维度评分式供应商选择（Scored Provider Selection）

所有工具选择都跑过评分引擎：任务契合度（30%）+ 输出质量（20%）+ 控制能力（15%）+ 可靠性（15%）+ 成本效率（10%）+ 延迟（5%）+ 连续性（5%）。备选方案、置信度、推理全记入可审计决策日志。

#### 7. 预算治理内置

estimate → reserve → reconcile 三段式；支持 observe/warn/cap 三种模式；默认单次操作超 $0.50 暂停审批；总预算默认 $10。**告别意外账单**。

#### 8. 无供应商锁定

每个能力同时支持云 API 和本地开源替代；selector 自动路由到当前可用项。

#### 9. Web 调研作为一等公民

写剧本前先跑 15-25+ 次 web 搜索（YouTube、Reddit、HN、新闻、学术源），引用全部进入结构化研究简报，**避免幻觉事实**。

### 2.4 实现原理

#### 技术栈

| 层 | 技术 |
|---|---|
| 编排层 | AI 编码助手（无独立 Python 编排器） |
| 工具层 | Python 3.10+（57+ 个 BaseTool 实现） |
| 配置/校验 | Pydantic、JSON Schema、YAML manifest |
| 视频合成 | Remotion（React/Node.js 18+）、HyperFrames（HTML/CSS/GSAP，Node.js 22+） |
| 后处理 | FFmpeg |
| 转写 | WhisperX（word-level 时间戳） |
| 视觉理解 | CLIP / BLIP-2（用于素材语义检索） |
| GPU 本地推理 | WAN 2.1、Hunyuan、CogVideo、LTX-Video、Stable Diffusion、Real-ESRGAN、SadTalker、Wav2Lip |
| 数字人 | SadTalker / MuseTalk / Wav2Lip / CodeFormer / GFPGAN |
| 数学动画 | ManimCE |

#### 架构设计：三层知识架构

```
Layer 1: tools/ + pipeline_defs/      "有什么" —— 可执行能力 + 编排定义
Layer 2: skills/                       "怎么用" —— OpenMontage 项目约定
Layer 3: .agents/skills/               "原理是什么" —— 通用技术知识包（FFmpeg/Remotion/GSAP 等）
```

每个工具通过 `agent_skills[]` 字段桥接 Layer 1 → Layer 3。

#### 核心抽象：BaseTool 契约

所有工具继承 `BaseTool`，声明 `name/version/tier/capability/provider/runtime/stability/dependencies/input_schema/output_schema/fallback_tools/agent_skills/resource_profile/retry_policy`，实现 `execute(inputs) -> ToolResult`。

`ToolRegistry` 单例通过 `pkgutil.walk_packages()` 自动发现，无需手动注册。

#### Selector Pattern（选择器模式）

每个能力族暴露一个 selector + 多个具体 provider 工具，例如：
- `tts_selector` + `elevenlabs_tts / google_tts / openai_tts / piper_tts`
- `video_selector` + `heygen_video / wan_video / hunyuan_video / ltx_video_local / ltx_video_modal / cogvideo_video`

Selector 在输入 schema 之间透明适配。

#### 标准流水线 8 阶段

```
research → proposal → script → scene_plan → assets → edit → compose → publish
```

每个阶段：
1. 有一份 stage-director skill（Markdown 指令）
2. 声明 `tools_available`
3. 产出规范化 artifact（JSON Schema 校验）
4. 有 `review_focus` 和 `success_criteria`
5. 可配置 `human_approval` 门

#### 11 类规范化 Artifact

`research_brief / proposal_packet / brief / script / scene_plan / asset_manifest / edit_decisions / render_report / publish_log / review / cost_log`，全部 JSON Schema 校验。

#### Checkpoint 系统

JSON 持久化在 `pipeline/` 目录，状态值：`pending / in_progress / awaiting_human / completed / failed`。三种策略：
- `guided`：创意阶段 checkpoint，机械阶段自动推进
- `manual_all`：每阶段都要人工审批
- `auto_noncreative`：仅 assets/edit 阶段需要人工

#### 预算治理生命周期

`estimate → reserve（锁定）→ reconcile（实际花费）`，持久化到 `cost_log.json`。

#### 工作流（How It Works）

```
用户给主题
↓
Agent 读 YAML pipeline manifest
↓
逐阶段：读 stage-director skill → 调 Python 工具 → 写 checkpoint → meta/reviewer skill 自审 → （可选）人工审批
↓
Pre-compose 校验门（交付承诺/幻灯片风险/渲染器治理）
↓
渲染（Remotion 或 FFmpeg）
↓
Post-render 自审查（ffprobe + 抽帧 + 音频分析 + 承诺核验）
↓
通过才输出最终视频
```

### 2.5 可借鉴亮点

1. **指令驱动而非代码驱动的编排**：将业务编排逻辑写成 YAML manifest + Markdown skill，而非硬编码在 Python 里
2. **规范化 Artifact + JSON Schema 校验**：每阶段产出有契约的 artifact，前后阶段通过 schema 解耦
3. **评分式供应商选择 + 可审计决策日志**：7 维度评分 + 备选与置信度入日志
4. **预算三段式治理**：estimate → reserve → reconcile，避免"先花后惊"
5. **多层质量门**：Pre-compose + Post-render 双重校验
6. **Selector + Provider 模式**：一个能力路由工具 + 多个具体 provider 工具
7. **真实素材 + CLIP 语义检索**
8. **参考视频驱动创作**
9. **零门槛入门路径**
10. **三层知识架构**：工具层/项目约定层/技术原理层

---

## 三、MoneyPrinterTurbo 项目深度分析

### 3.1 项目定位

**MoneyPrinterTurbo** 是一个**全自动短视频生成工具**。用户只需提供一个视频**主题**或**关键词**，系统就会自动完成：
- 视频文案生成
- 视频素材匹配与下载
- 字幕生成
- 背景音乐匹配
- 最终合成高清短视频

核心解决的是"短视频内容创作门槛高、流程长"的问题，把"选题→写文案→找素材→配音→配字幕→配乐→剪辑合成"这一整条流水线压缩成一次输入即可完成，主要面向**短视频创作者（TikTok / YouTube Shorts / Instagram 等平台）**，可一键跨平台发布。

### 3.2 核心功能模块

| 模块 | 对应文件/配置 | 说明 |
|------|--------------|------|
| **LLM 文案生成** | `app/services/llm.py` | 支持自动生成视频文案，也支持自定义文案；支持中英文 |
| **素材匹配与下载** | `app/services/material.py` | 从 Pexels / Pixabay / Coverr 拉取高清无版权素材；支持本地素材；支持"按脚本顺序匹配素材"模式 |
| **视频理解/语义重排** | `app/services/twelvelabs.py` | 接入 TwelveLabs：Marengo 多模态向量按主题语义重排素材关键词；Pegasus 对素材做内容 QA/描述 |
| **语音合成 TTS** | `app/services/voice.py` | 默认 Edge TTS（免费）；可选 Azure TTS V2（付费，更自然）、小米 MiMo TTS 等 |
| **字幕生成** | `app/services/subtitle.py` | 两种模式：`edge`（基于 TTS 时间戳，快）和 `whisper`（基于 faster-whisper 本地转写，更准） |
| **视频合成** | `app/services/video.py` | 基于 FFmpeg，支持竖屏 9:16 / 横屏 16:9；支持字幕字体/位置/颜色/大小/描边；支持背景音乐音量 |
| **任务调度与状态** | `app/services/task.py`、`app/services/state.py` | 支持批量生成；并发任务数控制（`max_concurrent_tasks`）；排队上限（`max_queued_tasks`）；可选 Redis 做任务状态管理 |
| **跨平台发布** | `app/services/upload_post.py` | 生成完成后自动上传至 TikTok / Instagram / YouTube Shorts（需 Upload-Post 账号，YouTube 自动标注 AI 生成内容） |

### 3.3 功能优势

1. **端到端全自动**：从主题输入到最终视频合成一条龙，省去多工具切换
2. **零成本启动门槛**：默认 Edge TTS 免费、Pexels 素材免费、FFmpeg 自动下载，可不配任何付费 API Key 直接跑通
3. **LLM 供应商覆盖极广**：原生支持 OpenAI、AIHubMix、AIML API、Moonshot、Azure、通义千问、Gemini、Ollama、DeepSeek、MiniMax、文心一言、Pollinations、ModelScope、火山引擎、小米 MiMo、Grok、Groq、EvoLink、one-api、cloudflare、gpt4free、LiteLLM（再扩展 100+ provider）等 20+ 家
4. **多种部署形态**：Windows 一键启动包、Docker（预构建镜像 `ghcr.io/harry0703/moneyprinterturbo:latest`）、`uv sync --frozen` 本地部署、Google Colab 在线体验、纯 CLI（`cli.py`）无浏览器模式
5. **MVC 架构清晰**：`app/controllers` / `app/models` / `app/services` 分层，同时提供 **WebUI（Streamlit）** 和 **API（FastAPI，带 /docs 与 /redoc）** 两套界面
6. **可选视频 AI 增强**：TwelveLabs 的 Marengo 能在素材预算紧张时把最贴题的 B-roll 排到最前面，Pegasus 能对单个 clip 做内容 QA
7. **一键跨平台发布**：原生集成 Upload-Post，自动上传三大短视频平台

### 3.4 实现原理

#### 技术栈

- **语言**：Python 3.11
- **依赖管理**：`uv` + `pyproject.toml` + `uv.lock`（兼容 `requirements.txt`）
- **Web 框架（API）**：FastAPI（`app/asgi.py`、`app/router.py`）
- **WebUI**：Streamlit（`webui/Main.py`）
- **视频处理**：FFmpeg（自动下载，支持 libx264 / h264_nvenc / h264_amf / h264_qsv / h264_videotoolbox 等硬件编码器，失败自动回退）
- **图像处理**：ImageMagick（字幕渲染）
- **TTS**：edge-tts（默认）、Azure Speech SDK（V2）、小米 MiMo TTS
- **字幕**：faster-whisper（large-v3-turbo 约 250MB / large-v3 约 3GB）
- **任务状态**：可选 Redis（`enable_redis`），默认本地状态管理
- **配置**：TOML（`config.toml`，由 `config.example.toml` 复制）
- **TLS 校验**：默认开启 `tls_verify=true`，防中间人攻击篡改 API Key 和素材

#### 架构分层

```
app/
├── controllers/   # HTTP 入参处理（API 路由层）
├── models/        # 数据模型（含 VideoAspect 等校验）
├── services/      # 核心业务逻辑
│   ├── llm.py          # LLM 文案生成（多 provider 适配）
│   ├── material.py     # 素材搜索/下载/匹配
│   ├── voice.py        # TTS 合成
│   ├── subtitle.py     # 字幕生成（edge / whisper）
│   ├── video.py        # FFmpeg 视频合成
│   ├── task.py         # 任务编排与流程
│   ├── state.py        # 任务状态管理（含 Redis）
│   ├── twelvelabs.py   # 视频理解增强
│   └── upload_post.py  # 跨平台发布
├── utils/
└── config/
```

#### 关键流程

1. **文案生成**：根据主题/关键词调用配置的 LLM provider 生成中文或英文视频文案
2. **素材匹配**：从文案中提取搜索词 → 调用 Pexels/Pixabay/Coverr API 搜索 → 下载高清无版权素材到 `material_directory`。可选 TwelveLabs Marengo 按主题语义重排搜索词顺序；支持 `match_materials_to_script` 让素材顺序严格对齐脚本叙事顺序
3. **配音**：将文案送入 Edge TTS / Azure TTS V2 / MiMo TTS 合成语音，拿到音频和时间戳
4. **字幕**：`edge` 模式直接用 TTS 时间戳对齐；`whisper` 模式用 faster-whisper 对合成音频做本地转写，生成更细粒度、更准确的 SRT
5. **配乐**：从 `resource/songs` 目录随机或指定背景音乐，可设音量
6. **合成**：FFmpeg 拼接素材片段 → 叠加音频 → 渲染字幕 → 混入背景音乐 → 输出 1080×1920 或 1920×1080 高清视频；支持硬件编码器加速
7. **发布**：通过 Upload-Post 自动上传到 TikTok / Instagram / YouTube Shorts

#### 并发与可靠性设计

- `max_concurrent_tasks`（默认 5）控制并发上限
- `max_queued_tasks`（默认 100）超过返回 429，防止匿名请求无限堆积
- `edge_tts_timeout`（默认 30s）避免 edge_tts 在网络异常/限流时长期卡住
- 视频编码器失败自动回退 libx264
- 任务状态可选 Redis 持久化，便于分布式部署

### 3.5 可借鉴亮点

1. **自动化流程编排**：把 LLM、TTS、素材、字幕、合成串成一条不可中断的流水线，对用户暴露的只是"主题"和少量参数
2. **素材管理**：多源聚合 + 多 Key 轮询；素材目录策略可配置（默认共享/指定目录/任务隔离）；语义重排素材关键词；素材顺序对齐脚本
3. **字幕系统**：双模式可切换（edge 快/whisper 准）+ 字幕样式完全可控 + 国内兜底下载
4. **配音与 TTS**：默认免费方案 + 分级方案（免费→付费→厂商）+ WebUI 实时试听 + 超时保护 + 支持无配音模式
5. **配乐**：本地素材库 + 默认自带音乐
6. **LLM Provider 抽象**：统一 `llm_provider` 字段 + 各 provider 独立配置段 + OpenAI 兼容协议优先 + LiteLLM 兜底
7. **工程化与运维**：MVC 分层清晰 + 配置驱动 + 安全默认值（tls_verify）+ 并发与背压 + 状态可外置 + Docker 预构建镜像 + 多形态入口

---

## 四、Pixelle-Video 项目深度分析

### 4.1 项目定位

**Pixelle-Video —— AI 全自动短视频引擎**

- **核心问题**：降低短视频创作门槛。用户只需输入一个主题（或现成文案），系统即可自动完成「文案 → 配图/视频 → 配音 → BGM → 合成」的全流程，无需任何剪辑经验
- **目标用户**：知识科普、人文纪实、个人成长、小说解说等类型视频创作者，以及希望做数字人口播、图生视频、动作迁移扩展玩法的进阶用户
- **零门槛理念**：「让视频创作成为一句话的事」；支持完全免费运行（Ollama + 本地 ComfyUI = 0 元）

### 4.2 核心功能模块

#### 四种生成流水线（`pixelle_video/pipelines/`）

| Pipeline | 文件 | 用途 |
|---|---|---|
| `StandardPipeline` | standard.py | 标准模式：输入主题，AI 写稿 + AI 配图/视频 + TTS + 合成 |
| `CustomPipeline` | custom.py | 自定义素材：用户上传照片/视频，AI 用 VLM 智能分析后生成脚本 |
| `AssetBasedPipeline` | asset_based.py | 扩展场景：数字人口播、图生视频、动作迁移 |
| `LinearVideoPipeline` | linear.py | 模板方法基类，定义统一生命周期 |

#### ComfyUI / RunningHub 工作流集成

- 通过 `ComfyKit` 库封装 ComfyUI API 调用
- `workflows/` 目录按来源分两个子目录：
  - `selfhost/`：本地 ComfyUI 工作流（image_flux、image_qwen、image_nano_banana、tts_edge、tts_index2、video_wan2.1_fusionx、analyse_image、analyse_video 等）
  - `runninghub/`：云端 RunningHub 工作流
- 工作流文件是 ComfyUI **API 原生 JSON 格式**，通过节点 `_meta.title` 中的特殊命名约定标记可变参数（如 `$prompt.value!`、`$width.value`、`$height.value`），程序可动态注入
- `ComfyBaseService` 基类用 `WORKFLOW_PREFIX`（`image_` / `tts_` / `video_`）区分服务类型，子类只需覆盖 prefix 与默认工作流

#### 直连 API 媒体模型

不依赖 ComfyUI，直接调用模型供应商：
- **图像**：OpenAI/GPT Image、DashScope/通义万象、Volcengine ARK/Seedream、Qwen
- **视频**：DashScope Wan/HappyHorse、Kling、Seedance
- **VLM 素材分析**：用于 CustomPipeline 的素材评估

#### 集中化 Prompt 管理（`pixelle_video/prompts/`）

| 模块 | 作用 |
|---|---|
| `topic_narration.py` | 主题→解说词 |
| `content_narration.py` | 固定文案→分割 |
| `title_generation.py` | 标题生成 |
| `image_generation.py` | 图像 prompt 生成 + 风格预设（`IMAGE_STYLE_PRESETS`） |
| `style_conversion.py` | 风格转换 |
| `asset_script_generation.py` | 自定义素材脚本生成 |
| `video_generation.py` | 视频 prompt 生成 |

#### 帧渲染与视频合成

- `frame_processor.py` + `frame_html.py`：基于 **HTML 模板 + Playwright 截图**渲染单帧
- `templates/` 目录按命名约定分类模板：
  - `static_*.html`：纯文字静态模板
  - `image_*.html`：AI 图片背景模板
  - `video_*.html`：AI 视频背景模板
- `video.py`：视频拼接、BGM 混音

#### 双入口架构

- **Web UI**：`web/app.py`（Streamlit，http://localhost:8501）
- **API 服务**：`api/app.py`（FastAPI，端口 8000），路由分 health/llm/tts/image/content/video/tasks/files/resources/frame，支持同步与异步（task tracking）两种生成模式
- `api/tasks/` 独立任务管理器，避免长任务阻塞

### 4.3 功能优势

1. **原子能力灵活组合**：图像、视频、TTS、VLM 任一环节都可在 ComfyUI 工作流 / 直连 API 两种模式间切换，互不绑定
2. **零剪辑门槛**：HTML 模板 + Playwright 截图方案，让"视频画面布局"完全代码化、可定制，绕开了传统 NLE 剪辑工具
3. **可扩展工作流插件机制**：用户丢一个 ComfyUI 原生 JSON 到 `workflows/selfhost/` 即被自动扫描注册，零代码接入新模型
4. **多语言 TTS 与声音克隆**：支持 Edge-TTS、Index-TTS，可上传参考音频做声音克隆
5. **内容审核失败重试**：API 视频生成支持「提示词中性化重试」
6. **跨平台部署**：Windows 一键整合包（含 ffmpeg）、Docker、源码三种方式
7. **学术背景**：项目方有 SIGGRAPH Asia / ACL 论文支撑（FilmAgent、Anim-Director、ComfyUI-Copilot、AniMaker）

### 4.4 实现原理

#### 技术栈

- **后端**：Python 3 + FastAPI + uvicorn（ASGI 异步）
- **Web UI**：Streamlit（端口 8501）
- **包管理**：uv（Astral 出品）
- **视频处理**：ffmpeg
- **帧渲染**：Playwright（无头浏览器截图 HTML 模板）
- **ComfyUI 集成**：`comfykit` 库（项目方自己的 ComfyUI 工作流封装库）
- **日志**：loguru
- **配置**：YAML（`config.example.yaml`）

#### 核心架构 —— 模板方法模式的 Pipeline

`pixelle_video/pipelines/linear.py` 定义了 8 步生命周期：

```
Phase 1 准备     → setup_environment
Phase 2 内容创作 → generate_content → determine_title
Phase 3 视觉规划 → plan_visuals → initialize_storyboard
Phase 4 资产生成 → produce_assets（核心：TTS + 图像/视频 + 帧渲染）
Phase 5 后期     → post_production（视频拼接 + BGM）
Phase 6 收尾     → finalize
```

- `PipelineContext` dataclass 在步骤间传递状态（input_text、narrations、image_prompts、storyboard、final_video_path 等），避免了"参数地狱"
- 子类按需覆写单个步骤，整体骨架不变
- 异常通过 `handle_exception` 钩子统一处理

#### 关键流程

**Prompt 自动化流程**：
1. 主题输入 → `build_topic_narration_prompt` 生成结构化解说词（含分镜）
2. 每句旁白 → `build_image_prompt_prompt` 生成对应英文图像 prompt
3. `IMAGE_STYLE_PRESETS` 提供风格预设注入到 prompt 前缀
4. LLM 输出强制结构化

**ComfyUI Workflow 编排机制**：
1. 启动时扫描 `workflows/{selfhost,runninghub}/*.json`
2. 按 `WORKFLOW_PREFIX` 分桶（image_/tts_/video_）
3. 调用时通过 `comfykit` 加载 JSON → 用节点 `_meta.title` 中的 `$xxx.value` 占位符定位可变参数 → 注入运行时值 → 提交 ComfyUI/RunningHub API → 轮询结果
4. `comfy_base_service.py` 中的 `_prepare_comfykit_config` 统一处理 comfyui_url、runninghub_api_key、instance_type 的优先级（param > config > env > default）

### 4.5 可借鉴亮点

1. **Pipeline 模板方法 + Context 模式**（强烈推荐）：用 `LinearVideoPipeline` + `PipelineContext` 把复杂多步流程拆成可独立覆写的生命周期钩子，比 if/else 串联更易扩展
2. **原子能力 + 双后端抽象**：每个"能力"（image/video/tts/vlm）都同时支持 ComfyUI 工作流和直连 API 两种实现
3. **ComfyUI Workflow 的"占位符约定"**：用 `_meta.title: "$prompt.value!"` 在原生 ComfyUI JSON 中标记可变节点，兼容 ComfyUI 原生格式
4. **集中化 Prompt 包**：按用途拆分到独立 Python 模块，可单元测试、可版本化
5. **HTML 模板 + Playwright 截图**：把"视频画面布局"从 NLE 剪辑工具下沉到 HTML/CSS 层
6. **API/Web 双入口 + 任务管理器**：Streamlit 用于交互式生成，FastAPI 用于编程式调用
7. **工作流自动扫描注册**：启动时扫描 `workflows/` 目录，按前缀自动归类、缓存

---

## 五、agnes-platform 现有能力盘点

### 5.1 整体架构

```
agnes-platform/
├── backend/        # FastAPI（Python，全异步）
├── frontend/       # Vue 3 + Vite + Element Plus + Pinia + Vue Router
├── mobile/         # React Native（移动端）
├── docs/           # 设计文档
├── alembic/        # 数据库迁移
```

### 5.2 后端分层（FastAPI）

| 目录 | 职责 |
|---|---|
| `backend/app/routes/` | HTTP 入参、调用 service、返回响应（轻量路由层） |
| `backend/app/services/` | 业务逻辑、外部 API 调用、鉴权、ID 生成 |
| `backend/app/models/` | SQLAlchemy 异步 ORM 模型 |
| `backend/app/schemas/` | Pydantic 请求/响应结构 |
| `backend/app/core/` | 配置、数据库连接、日志、安全 |
| `backend/app/services/pipeline/` | 创意流水线子系统（engine + 7 个 step executor + sse_manager + run_service + template_service + post_process_video） |

### 5.3 关键技术栈

- **全异步**：SQLAlchemy 2.0 async + AsyncSession + httpx.AsyncClient（持久化连接池）
- **BFF 模式**：API Key 仅存于后端 `.env`，前端通过 BFF 间接调用 Agnes AI API
- **数据库**：默认 SQLite 零配置，支持 PostgreSQL
- **SSE 推送**：实时回传流水线进度
- **FFmpeg 子进程**：`asyncio.create_subprocess_exec` 做视频合成

### 5.4 已完整实现的能力（生产级）

| 能力 | 实现位置 | 完整度 |
|---|---|---|
| LLM 剧本生成（一键生成分镜 JSON） | `llm_generate.py` | 完整 |
| 图像批量生成（含角色参考图传递） | `image_batch.py` | 完整 |
| 视频批量生成（含 LLM 提示词改写） | `video_batch.py` | 完整 |
| 流水线 DAG 编排 + 断点续跑 + 暂停/恢复 | `engine.py` | 完整 |
| 字幕烧入 + SRT/VTT 双格式输出 | `ffmpeg_composite.py` | 完整 |
| 字幕重新烧入（recompose，不重跑流水线） | `recompose_pipeline_video` | 完整 |
| TTS 配音（多音色 + 性别映射 + 离线兜底） | `tts_generate.py` | 完整 |
| BGM 混音（amix） | `ffmpeg_composite.py` | 完整 |
| 音轨替换（从 TTS 步骤替换原音轨） | `ffmpeg_composite.py` | 完整 |
| 调色（4 预设 + 自定义滤镜链） | `color_grade.py` | 完整 |
| 视频剪辑（trim/cut，区间并集减切割） | `video_edit.py` | 完整 |
| 视频拼接（concat demuxer + reencode 兜底） | `ffmpeg_composite.py` | 完整 |
| 30ms 音频淡入淡出（避免切点爆音） | `ffmpeg_composite.py` | 完整 |
| 模板市场（内置 + 公开 + 我的） | `pipeline.py` 路由 + `WorkshopView` | 完整 |
| 模板修订草稿（编辑已审核模板走 draft 流程） | `template_service` | 完整 |
| 模板导入导出（rename/skip/overwrite + private/public/builtin） | `pipeline.py` 路由 | 完整 |
| 双阶段审核（AI 预筛 + 管理员审核） | `moderation_service.py` | 完整 |
| 统一审核页（作品/预设/模板共享逻辑） | `UnifiedReview.vue` | 完整 |
| 敏感词进程内缓存（60s TTL） | `moderation_service.py` | 完整 |
| SSE 实时进度推送 | `sse_manager.py` | 完整 |
| 积分预扣/退款 | `engine.py` | 完整 |
| 前端任务队列（独立轮询 + 持久化 + 可见性感知） | `taskQueue.ts` | 完整 |
| 3D 场景编辑器（相机/灯光/主体摆放） | `Scene3DEditor.vue` | 完整 |
| 国际化（zh-CN + en-US） | `i18n/` | 完整 |
| AI 模板缩略图生成 | `pipeline.py` 路由 | 完整 |
| 视频水印（302 重定向 / 缓存版本） | `watermark_service.py` | 完整 |
| 后处理 API（对历史生成做 color_grade / video_edit） | `post_process_video` | 完整 |
| 资产库（character/prop/scene/brand + 版本管理） | `asset_library.py` | 完整 |

### 5.5 用户特别关注的"边界能力"评估

| 用户关注点 | 现状 | 完整度 |
|---|---|---|
| **长视频 / 多场景拼接** | `ffmpeg_composite.py` 支持 concat demuxer（`-c copy`）+ reencode 兜底；可串联多段 `video_batch` 输出 | 部分：拼接完整，但**无片段间转场**（无 xfade / crossfade），仅硬切或淡入淡出 |
| **字幕 / 配音 / 配乐完整链路** | 三者均完整实现：`SubtitleEditor` + `tts_generate` + BGM amix，且 `ffmpeg_composite` 一次性合成 | 完整（但 BGM 仅外部 URL） |
| **自动化脚本生成（LLM 一键视频）** | `llm_generate` + `ScriptTemplate`（Jinja2 + JSON Schema），整条流水线 end-to-end 跑通 | 完整 |
| **素材智能匹配** | 仅角色参考图从上游 step 显式 `reference_from_step` 传递；无 embedding 语义检索、无自动素材推荐 | 简陋 |
| **完整视频后期处理（剪辑 / 转场 / 字幕烧入）** | `color_grade` + `video_edit`（trim/cut）+ `ffmpeg_composite`（字幕烧入 + BGM + 音轨替换 + 调色）+ `recompose` 单独重烧字幕 | 部分：剪辑 + 字幕 + 调色完整，但**无转场特效**、**无多轨编辑** |

---

## 六、明显缺失或简陋的功能点

### 6.1 视频后期处理相关

1. **无转场特效**（重要缺口）
   - 位置：`ffmpeg_composite.py`
   - 现状：concat demuxer 仅做硬拼接或简单 reencode
   - 缺失：xfade（crossfade）、wipe、slide、zoom 等转场效果
   - 影响：长视频观感不连贯

2. **无多轨编辑**
   - 现状：单视频轨 + 单音频轨
   - 缺失：画中画、分屏、多层视频叠加、关键帧动画

3. **调色 `auto` 模式简化**
   - 位置：`color_grade.py` `resolve_grade_filter`
   - 现状：`auto` 直接降级为 `neutral_punch`（不实现 video-use 的 signalstats 逐帧分析）
   - 影响：无智能调色

### 6.2 素材与配乐相关

4. **BGM 无内置库**
   - 位置：`ffmpeg_composite.py` BGM 输入仅接受 URL
   - 缺失：项目内 BGM 素材库、按情绪/节奏智能推荐 BGM

5. **素材智能匹配缺失**
   - 现状：仅 `reference_from_step` 显式传递角色参考图
   - 缺失：基于 embedding 的语义检索、按剧本自动匹配道具/场景素材

6. **无语音克隆**
   - 位置：`tts_generate.py`
   - 现状：依赖 edge-tts 固定音色
   - 缺失：用户自定义音色、声音克隆

### 6.3 字幕相关

7. **字幕时间轴无音频驱动对齐**
   - 现状：依赖 LLM 输出的时间字段
   - 缺失：forced alignment（音频驱动字幕对齐）、自动语音识别（ASR）补全字幕

### 6.4 3D 编辑器相关

8. **3D 编辑器无渲染输出**
   - 位置：`Scene3DEditor.vue`
   - 现状：仅元素摆放 + 视角预览
   - 缺失：3D 渲染出图、相机运动关键帧动画、GLB/FBX 模型导入

### 6.5 任务队列相关

9. **任务失败无自动重试**
   - 位置：`taskQueue.ts`
   - 现状：失败后需用户手动触发
   - 缺失：指数退避自动重试机制

### 6.6 长视频生产相关

10. **无长视频分集管理**
    - 现状：单条流水线产出单个最终视频
    - 缺失：分集/章节管理、跨流水线的素材复用、统一时间线编排

---

## 七、精进建议（按优先级排序）

### P0 —— 高价值、可快速落地

#### 1. 引入转场特效系统（参考 OpenMontage 的 edit_decisions + Pixelle 的 HTML 模板）

**问题**：长视频观感不连贯，硬切明显

**方案**：
- 在 `ffmpeg_composite.py` 中扩展 `concat` 逻辑，新增 `transition` 字段
- 支持 FFmpeg `xfade` 滤镜（crossfade / wipeleft / slideup / zoomin 等十几种）
- 在 `PipelineStep` 的 `input_data` 中新增 `transitions: [{type, duration, between: [scene_a, scene_b]}]`
- 前端 `TimelinePreview.vue` 增加转场选择 UI

**工作量**：1-2 个执行器改造 + 前端编辑器扩展

**关键文件**：
- `backend/app/services/pipeline/steps/ffmpeg_composite.py`
- `frontend/src/components/pipeline/TimelinePreview.vue`

#### 2. 字幕双模式（参考 MoneyPrinterTurbo 的 edge/whisper 分级降级）

**问题**：当前字幕依赖 LLM 输出时间字段，与实际配音时间轴可能错位

**方案**：
- `edge` 模式：复用现有 TTS 时间戳（快）
- `whisper` 模式：用 faster-whisper 对合成音频做本地转写（准），支持大模型 large-v3-turbo（250MB）
- 在 `tts_generate.py` 之后增加可选的 `subtitle_align` 子步骤
- 国内网络兜底：提供 whisper 模型镜像下载说明

**关键文件**：
- `backend/app/services/pipeline/steps/tts_generate.py`
- 新增 `backend/app/services/pipeline/steps/subtitle_align.py`

#### 3. 任务失败指数退避自动重试（参考 MoneyPrinterTurbo 的 `edge_tts_timeout` 防卡死）

**问题**：前端 taskQueue 失败需用户手动触发，体验差

**方案**：
- 在 `taskQueue.ts` 增加 `autoRetry` 选项
- 指数退避：3s → 9s → 27s，最多 3 次
- 区分错误类型：网络错误自动重试，内容审核错误不重试
- 用户可在设置中关闭自动重试

**关键文件**：
- `frontend/src/stores/taskQueue.ts`

---

### P1 —— 中等价值、需一定改造

#### 4. Selector + Provider 模式重构（参考 OpenMontage 的 BaseTool + Selector Pattern）

**问题**：当前图片/视频生成各对接多个模型（FLUX/Seedream/Z-Image/Veo/Seedance），但缺少统一抽象

**方案**：
- 抽象 `MediaSelector` 基类，每个能力族（image/video/tts）一个 selector
- Selector 内部按"任务契合度 + 可用性 + 成本"路由到具体 provider
- 决策日志写入 `PipelineRun.output_summary`，便于审计
- 与现有 `provider_registry.get_client_for_model(model_id)` 兼容，不破坏 BFF 架构

**关键文件**：
- `backend/app/services/provider_registry.py`（新增）
- 各 step executor（适配新接口）

#### 5. 规范化 Artifact + JSON Schema 校验（参考 OpenMontage 的 11 类 Artifact）

**问题**：步骤间数据传递靠 `output_data` JSON 字段，无 schema 约束，容易"幻觉"

**方案**：
- 在 `schemas/` 下定义每类 step 的输出 schema：`LLMOutputSchema` / `ImageBatchOutputSchema` / `VideoBatchOutputSchema` / `CompositeOutputSchema`
- `BaseStepExecutor` 在 `complete_step` 时自动校验
- 上下游通过 schema 字段名解耦，避免硬编码字段名

**关键文件**：
- `backend/app/schemas/pipeline_artifacts.py`（新增）
- `backend/app/services/pipeline/steps/base.py`

#### 6. BGM 内置库 + 情绪推荐（参考 MoneyPrinterTurbo 的 `resource/songs`）

**问题**：BGM 仅外部 URL，新用户首次使用门槛高

**方案**：
- 后端新增 `bgm_library/` 目录，按情绪分类（epic / calm / upbeat / sad / corporate）
- `ffmpeg_composite` 步骤增加 `bgm_mood` 字段，未指定 URL 时按情绪从内置库随机选
- 管理员后台支持上传/管理 BGM（接入现有 `asset_library` 模块）

**关键文件**：
- `backend/app/services/bgm_library.py`（新增）
- `backend/app/services/pipeline/steps/ffmpeg_composite.py`

#### 7. Pipeline 模板方法 + Context 模式重构（参考 Pixelle-Video）

**问题**：当前 engine.py 1447 行，7 个执行器并行注册，但缺少"生命周期钩子"抽象

**方案**：
- 引入 `PipelineContext` dataclass，跨步骤传递状态（替代散落的 `output_data` 读取）
- `BaseStepExecutor` 增加 `pre_execute` / `post_execute` / `on_skip` / `on_retry` 钩子
- 子类按需覆写，整体骨架不变
- 与现有 DAG 引擎兼容，不破坏断点续跑

**关键文件**：
- `backend/app/services/pipeline/context.py`（新增）
- `backend/app/services/pipeline/steps/base.py`

---

### P2 —— 长期演进、需架构调整

#### 8. 素材智能匹配（参考 OpenMontage 的 CLIP 语义检索 + MoneyPrinterTurbo 的 TwelveLabs Marengo）

**问题**：当前仅 `reference_from_step` 显式传递，无自动素材推荐

**方案**：
- 接入 CLIP 模型，对资产库的图片/视频做 embedding 入库
- LLM 生成分镜时，每场景产出 `asset_query`（描述所需素材）
- 新增 `asset_match` 步骤执行器，按语义相似度从资产库检索 top-K 素材
- 与现有 `asset_library.py` 集成，复用 character/prop/scene/brand 分类

**关键文件**：
- `backend/app/services/asset_embedding.py`（新增）
- `backend/app/services/pipeline/steps/asset_match.py`（新增）

#### 9. 预算治理三段式（参考 OpenMontage 的 estimate → reserve → reconcile）

**问题**：当前积分预扣/退款只有"扣/退"两态，无预估和对账

**方案**：
- `estimate`：流水线启动前按 step 类型预估总积分（image_batch × N + video_batch × M + tts × K）
- `reserve`：预扣预估额度，记入 `PipelineRun.reserved_credits`
- `reconcile`：实际消耗后补扣或退款，差异写入 `cost_log`
- 用户可在模板配置中设 `budget_cap`，超限暂停

**关键文件**：
- `backend/app/services/pipeline/budget_service.py`（新增）
- `backend/app/models/pipeline.py`（增加字段）

#### 10. 长视频分集管理（参考 OpenMontage 的 Clip Factory + Hybrid Pipeline）

**问题**：当前单流水线产单视频，长视频（>3 分钟）生成质量下降

**方案**：
- 新增 `Episode` 实体：一个 Episode 包含多个 PipelineRun
- 每个 PipelineRun 产出 1-3 分钟片段，最后通过 `EpisodeComposer` 合成
- 复用现有 `ffmpeg_composite`，新增转场步骤串联各片段
- 前端新增分集管理页（接入现有 `WorkshopView` 模式）

**关键文件**：
- `backend/app/models/episode.py`（新增）
- `backend/app/services/episode_service.py`（新增）
- `frontend/src/views/EpisodeView.vue`（新增）

#### 11. 多后端能力适配（参考 Pixelle-Video 的 ComfyUI/API 双后端）

**问题**：当前图片/视频生成仅对接 Agnes AI API，无 ComfyUI 等本地后端

**方案**：
- 抽象 `MediaBackend` 接口：`generate_image` / `generate_video` / `tts`
- 实现 `AgnesAIBackend`（现有）+ `ComfyUIBackend`（新）
- ComfyUI 后端复用 Pixelle 的占位符约定（`_meta.title` 中的 `$xxx.value`）
- 用户在配置中选择后端，selector 自动路由

**关键文件**：
- `backend/app/services/media_backends/`（新增目录）
- 各 step executor 适配新接口

---

## 八、落地路线图

| 阶段 | 内容 | 价值 |
|---|---|---|
| **第 1 阶段** | 转场特效 + 字幕双模式 + 任务自动重试 | 立刻提升用户体验，3 个独立小改造 |
| **第 2 阶段** | Selector 抽象 + Artifact Schema + BGM 库 | 工程化升级，为多模型扩展铺路 |
| **第 3 阶段** | Pipeline Context 重构 + 素材智能匹配 | 架构演进，引入 AI 智能化 |
| **第 4 阶段** | 预算治理 + 长视频分集 + 多后端适配 | 平台化升级，支撑规模化生产 |

### 路线图详细说明

#### 第 1 阶段：用户体验快速提升（P0 三项）

**目标**：解决用户最直接感受到的痛点，三项改造相互独立，可并行开发。

1. **转场特效系统**
   - 后端：扩展 `ffmpeg_composite.py` 的 concat 逻辑，支持 xfade 滤镜
   - 数据模型：`PipelineStep.input_data` 增加 `transitions` 字段
   - 前端：`TimelinePreview.vue` 增加转场选择 UI
   - 预期效果：长视频观感显著提升，告别硬切

2. **字幕双模式**
   - 后端：新增 `subtitle_align.py` 步骤执行器
   - 依赖：引入 faster-whisper（large-v3-turbo 250MB）
   - 国内兜底：提供百度网盘/夸克网盘镜像下载说明
   - 预期效果：字幕与配音时间轴精准对齐

3. **任务自动重试**
   - 前端：`taskQueue.ts` 增加 `autoRetry` 选项
   - 策略：指数退避（3s → 9s → 27s，最多 3 次）
   - 错误分类：网络错误自动重试，内容审核错误不重试
   - 预期效果：减少用户手动干预，提升任务成功率

#### 第 2 阶段：工程化升级（P1 四项）

**目标**：为多模型扩展、多场景适配铺路，提升代码可维护性。

1. **Selector + Provider 模式**
   - 抽象 `MediaSelector` 基类
   - 与现有 `provider_registry` 兼容
   - 决策日志写入 `PipelineRun.output_summary`

2. **规范化 Artifact + JSON Schema 校验**
   - 定义每类 step 的输出 schema
   - `BaseStepExecutor` 在 `complete_step` 时自动校验
   - 上下游通过 schema 字段名解耦

3. **BGM 内置库 + 情绪推荐**
   - 后端新增 `bgm_library/` 目录
   - 按情绪分类（epic / calm / upbeat / sad / corporate）
   - 接入现有 `asset_library` 模块管理

4. **Pipeline Context 重构**
   - 引入 `PipelineContext` dataclass
   - `BaseStepExecutor` 增加生命周期钩子
   - 与现有 DAG 引擎兼容

#### 第 3 阶段：AI 智能化（P2 前半）

**目标**：引入 AI 智能化能力，提升自动化程度。

1. **素材智能匹配**
   - 接入 CLIP 模型做 embedding
   - 新增 `asset_match` 步骤执行器
   - 按语义相似度检索 top-K 素材

2. **Pipeline Context 重构（深化）**
   - 完成第 2 阶段未完成的部分
   - 子类按需覆写钩子

#### 第 4 阶段：平台化升级（P2 后半）

**目标**：支撑规模化生产，完善治理体系。

1. **预算治理三段式**
   - estimate → reserve → reconcile
   - 用户可设 `budget_cap`
   - 差异写入 `cost_log`

2. **长视频分集管理**
   - 新增 `Episode` 实体
   - `EpisodeComposer` 合成多片段
   - 前端分集管理页

3. **多后端能力适配**
   - 抽象 `MediaBackend` 接口
   - 实现 `AgnesAIBackend` + `ComfyUIBackend`
   - 用户配置选择后端

---

## 九、最值得立刻借鉴的 5 个点

1. **OpenMontage 的 Pre/Post 质量门** —— 渲染前阻断"看起来就废"的计划，渲染后 ffprobe + 抽帧黑屏检测。这是降低用户看到废片比例的最直接手段。

2. **MoneyPrinterTurbo 的字幕双模式（edge/whisper）** —— 分级降级策略，先用快的，质量不够再切慢的。

3. **Pixelle-Video 的 PipelineContext 模式** —— 解决 AGENTS.md 中提到的 `self.config.get("config", {})` 嵌套问题的最佳方案，把"步骤配置 vs 全局配置"分离。

4. **OpenMontage 的 Selector + 评分式供应商选择** —— agnes-platform 已有 `provider_registry`，再加一层"评分 + 决策日志"就能解决多模型路由的混乱。

5. **MoneyPrinterTurbo 的 `max_concurrent_tasks` + `max_queued_tasks` + 429 背压** —— 生产级任务队列的标准做法，agnes-platform 的 taskQueue 当前并发上限 5 是写死的，可借鉴其配置化 + 背压策略。

---

## 十、总结

三个项目各有所长：

- **OpenMontage** 的工程化方法论最先进（Agent 驱动 + 契约化 + 质量门 + 预算治理）
- **MoneyPrinterTurbo** 的短视频流水线最完整（端到端 + 多 provider + 跨平台发布）
- **Pixelle-Video** 的工作流编排最灵活（双后端 + 模板方法 + ComfyUI 集成）

agnes-platform 当前完成度已较高，**最需要补齐的是"视频后期处理的高级能力"（转场 + BGM 库 + 素材智能匹配）和"工程化治理"（Selector 抽象 + 质量门 + 预算治理）**。

建议从 P0 三项（转场 + 字幕双模式 + 自动重试）入手，快速见效后再推进 P1/P2 的架构演进。每个阶段完成后进行回顾，根据实际效果调整下一阶段优先级。

---

## 附：相关文件索引

### agnes-platform 后端 - 流水线核心

- `backend/app/services/pipeline/engine.py` — 执行引擎（DAG + 状态机）
- `backend/app/services/pipeline/steps/__init__.py` — 执行器注册表
- `backend/app/services/pipeline/steps/base.py` — BaseStepExecutor + StepExecutionContext
- `backend/app/services/pipeline/steps/llm_generate.py` — LLM 剧本生成
- `backend/app/services/pipeline/steps/image_batch.py` — 图像批量生成
- `backend/app/services/pipeline/steps/video_batch.py` — 视频批量生成 + LLM 改写
- `backend/app/services/pipeline/steps/ffmpeg_composite.py` — FFmpeg 合成（字幕 + BGM + 调色）
- `backend/app/services/pipeline/steps/tts_generate.py` — TTS 配音
- `backend/app/services/pipeline/steps/color_grade.py` — 调色
- `backend/app/services/pipeline/steps/video_edit.py` — 视频剪辑
- `backend/app/services/pipeline/run_service.py` — 运行管理 + `recompose_video`
- `backend/app/services/pipeline/template_service.py` — 模板 CRUD + 修订草稿
- `backend/app/services/pipeline/post_process_video.py` — 后处理 API
- `backend/app/services/pipeline/sse_manager.py` — SSE 推送

### agnes-platform 后端 - 模型与路由

- `backend/app/models/pipeline.py` — PipelineTemplate / ScriptTemplate / StylePreset / PipelineRun / PipelineStep
- `backend/app/routes/pipeline.py` — 流水线 REST API

### agnes-platform 后端 - 其他服务

- `backend/app/services/moderation_service.py` — 双阶段审核
- `backend/app/services/asset_library.py` — 资产库
- `backend/app/services/asset_storage.py` — 资产存储
- `backend/app/services/watermark_service.py` — 视频水印
- `backend/app/main.py` — FastAPI 入口

### agnes-platform 前端

- `frontend/src/stores/taskQueue.ts` — 任务队列 store
- `frontend/src/components/scene/Scene3DEditor.vue` — 3D 场景编辑器
- `frontend/src/components/pipeline/SubtitleEditor.vue` — 字幕编辑器
- `frontend/src/components/pipeline/TimelinePreview.vue` — 时间线预览
- `frontend/src/components/pipeline/StyleElementPicker.vue` — 风格元素选择器
- `frontend/src/i18n/index.ts` — i18n 入口（轻量方案，零依赖）

### 参考项目链接

- OpenMontage: https://github.com/calesthio/OpenMontage
- MoneyPrinterTurbo: https://github.com/harry0703/MoneyPrinterTurbo
- Pixelle-Video: https://github.com/ATH-MaaS/Pixelle-Video
