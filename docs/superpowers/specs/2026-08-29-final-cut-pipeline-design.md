# 成片闭环打通设计（TTS 配音 → 字幕 → 合成）

> 打通"一句话 → 成片"的最后一公里：TTS 执行体接线（唯一硬断点）+ BGM 音源 + 画布三节点执行链路

## 1. 背景与现状

产出目前止步于"一堆片段"：画布的 tts/subtitle/compose 三类节点只有设置 UI 无执行链路，项目制配音因 TTS 空壳不可用。调研结论（2026-08-29，逐文件核实）：

| 环节 | 状态 |
| --- | --- |
| TTS 执行 | **唯一硬断点**：`audio_service._call_tts_provider`（audio_service.py:148）抛 NotImplementedError；`agnes_client.create_tts_task`（agnes_client.py:1333）同为 stub。其上游（路由/多版本写入/SSE/批量循环/音色解析）全部完整 |
| TTS 能力 | `aibridge-sdk[edge-tts]` 已在环境（Rust 包 + edge_tts 7.2.8）：`Client(provider="edge-tts")` → `speech(model, input, voice)` → `SpeechResult{audio_data, duration,...}`，免 API Key；同接口还有 elevenlabs/cartesia 可后续接 |
| 音色 | 8 个内置音色常量（audio_service.py:45）+ 角色映射表 + 解析链完整；缺与 edge-tts 实际音色名（zh-CN 短名）的映射 |
| 字幕 | 项目制 subtitle_service 完整（LLM 拆分 / faster-whisper 对齐双模式 + SRT/ASS 构建）；merge 三档字幕烧录完整 |
| 合成 | merge_service 完整（concat/xfade/TTS+BGM 混音/三档字幕烧录/5 分钟超时自恢复）；advanced 路由 + SSE/轮询齐全 |
| BGM | 元数据注册表 5 首 + 混音逻辑 + 选择器 UI 完整；`backend/assets/bgm/` 目录为空（音源缺） |
| 画布三节点 | UI/默认 content/连线校验（tts:['text']、subtitle:['text']、compose:['video','tts','subtitle']）全就绪；无生成 handler、无后端路由、无积分预估 |
| 死代码待激活 | `VoicePickerDialog.vue` 已写好无引用；ProjectHeader"合成视频"按钮只走不带音频字幕的简单 merge |

## 2. 目标与非目标

**目标**：项目制"生成配音"可用（M1）；BGM 可用 + 合成入口一键到位（M2）；画布 tts/subtitle/compose 三节点跑通成片链路（M3）。

**非目标**：不做 elevenlabs/cartesia 接入（保留 provider 抽象即可）；不做 PIP 画中画（merge 注释有但无实现，另立项）；画布成片不做独立剪辑时间线（复用 merge 既有编排）；Agent/分享入口（roadmap Phase C）。

## 3. 方案设计

### 3.1 M1：TTS 执行体接线（后端单点，项目制配音立即可用）

`audio_service._call_tts_provider` 实现（签名不变，返回 `(audio_url, duration_ms, file_size)`）：

1. `Client(provider="edge-tts")` → `await client.start()` → `speech(model=<edge 默认模型>, input=text, voice=<映射后音色>)` → `audio_data`（bytes）。
2. **音色映射**：`BUILTIN_VOICES` 每项加 `edge_voice` 字段（8 个 zh-CN 短名，如 narrator_male_zh→zh-CN-YunxiNeural、young_female_zh→zh-CN-XiaoyiNeural 等，实施时按 edge-tts 实际音色列表核对）；`_resolve_voice_for_shot` 选出的 voice_id 经映射表换算，未命中回退 zh-CN-YunxiNeural。
3. **落盘与 URL**：对齐 `upload_audio` 的现状路径（项目 outputs 目录 + FileResponse 通道），文件名 `{project_id}/audio_v{version}_{ts}.mp3`；duration 优先取 `SpeechResult.duration`，缺失时 ffprobe 探测。
4. **生命周期**：每次合成新建 Client 用完即关（TTS 频率低，无需常驻连接池）；异常包装为 HTTPException 502 透传原因。
5. provider 留痕：`ProjectShotAudio.provider='edge-tts'` 字段已有，直接写入。

交付验收：ShotCard"生成配音"→ 音频可播放、版本入库、SSE `tts_completed` 触发、批量配音循环可用。

### 3.2 M2：BGM 音源 + 合成入口整理

1. **BGM 音源（版权诚实方案）**：内置 5 首保持 `available=false` 直到放入音频文件；新增 `POST /projects/{id}/bgms/upload`（管理员/用户上传 mp3 入 `_BGM_DIR` 并登记元数据），**用户自备音源为推荐路径**；不用 ffmpeg 程序化合成垫乐（质量不可用）。
2. **合成入口**：ProjectHeader"合成视频"按钮改调 `mergeProjectAdvanced`（默认 with_audio/with_subtitle=true、with_bgm 跟随当前选择）——零后端改动。
3. **音色选择器**：`VoicePickerDialog` 挂到 ShotCard 配音入口（替换裸下拉），角色音色分配走既有 `assign_character_voice`。

### 3.3 M3：画布成片链路（tts / subtitle / compose 三节点执行）

**后端**新增画布维度路由（`/api/canvas/*`，无状态、按节点 content 传参，不建表）：

- `POST /api/canvas/tts`：`{ text, voice, speed }` → 复用 `_call_tts_provider` → 返回 `{ audio_url, duration_ms }`。
- `POST /api/canvas/subtitle`：`{ text, model, max_chars }` → 复用 subtitle_service 的 LLM 拆分逻辑 → 返回 SRT 文本 + 片段数组 `[{start_time,duration,text}]`。
- `POST /api/canvas/compose`：`{ video_urls[], audio_url?, subtitles[]?, with_subtitle, bgm_id? }` → 新 `canvas_compose_service` 直接调 ffmpeg（复用 merge_service 的 `_concat_videos_with_xfade` / `_mix_audio_tracks` / 字幕烧录函数——需把这三块从 project 上下文抽成可传参调用，或抽公共模块 `media_compose.py`），输出到 `outputs/canvas/{node_id}.mp4` 并转存。

**前端**：

- tts 节点：Composer 发送 → text 上游内容 + 音色/语速 → 音频**节点**（type='audio' 直出形态，URL 回填节点，可预览播放）；连线校验 tts:['text'] 已限制输入。
- subtitle 节点：text 上游 → SRT 文本节点（type='text' 直出，内容为 SRT）。
- compose 节点：收集上游 video 节点（按连线）+ 可选 tts/subtitle 上游 → 生成中/成功态同直出节点模式；产物为 type='video' 结果展示。
- 积分预估：TTS/compose 接入 `checkCreditsBeforeGenerate`（TTS 按字符数、compose 按 segments 数，积分规则缺省时 0 成本放行）。
- retryGeneration 扩展 audio/compose 直出分支（同 image/video 模式）。

### 3.4 顺序与依赖

M1（独立，半天量级）→ M2（独立，小）→ M3（依赖 M1 的 `_call_tts_provider`，量级最大）。M1/M2 交付后项目制即达成全流程闭环；M3 补齐画布侧。

## 4. 验证方式

- M1：任一镜头点"生成配音"→ 音频可播放、`project_shot_audios` 新版本、8 音色各生成一次抽查音色正确；断网/edge 服务异常 → 502 带原因、无脏版本记录。
- M2：上传 BGM → 列表 available 翻转 → 高级合成带 BGM 混音；ProjectHeader 合成按钮 → 产物含配音与字幕。
- M3：画布 text→tts→audio 播放；text→subtitle→SRT 内容正确（≤20 字/条）；3 个视频节点 + tts + subtitle → compose → 成片节点可播放、含混音与烧录字幕；积分预估弹窗金额合理。
- 惯例：`vue-tsc` + `py_compile` + 手动冒烟以上述清单为准。

## 5. 风险与对策

| 风险 | 对策 |
| --- | --- |
| edge-tts 依赖微软免费服务，可能限流/失效 | provider 抽象保留（aibridge 同接口可切 elevenlabs）；失败 502 带原因，节点可重试 |
| 8 音色 ↔ edge 音色映射效果不佳（性别/年龄气质不符） | 映射表集中一处可调；VoicePicker 播放试听后再确认（M2 挂上后自然获得） |
| BGM 版权 | 用户自备上传为推荐路径，内置曲目录入前保持 unavailable |
| merge 底层函数与 project DB 耦合，抽取有回归风险 | M3 抽取时以"只挪不改"为原则，项目制 advanced 合成回归冒烟兜底 |
| 画布 compose 长耗时阻塞 | 沿用 merge 的后台任务 + 轮询模式，节点 loading 态 |
