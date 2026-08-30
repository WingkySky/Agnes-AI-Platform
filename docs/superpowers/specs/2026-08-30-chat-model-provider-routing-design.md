# 文本对话模型按 Provider 路由 · 设计建议稿

## 背景

- 多 Provider 支持上线后，chat 类型模型可来自任意 Provider（Agnes 官方、OpenAI 兼容中转、火山方舟 Agent Plan 等）。
- 图片 / 视频已按「模型 → Provider」自动路由（`provider_registry.get_client_for_model`），但 LLM 文本对话的调用点全部固定走 `agnes_client` 单例（默认 Provider 的 base_url + key）。选择非默认 Provider 的对话模型时，请求会发错端点。
- 非 Agnes Provider 的对话链路已实测可用：火山方舟 Agent Plan（OpenAI 协议，`https://ark.cn-beijing.volces.com/api/plan/v3`）`chat/completions` 返回 200。注意该端点不提供 `/models` 列表接口，模型需手动添加（自定义模型机制已支持）。

## 现状调用点清单（全部固定走 `agnes_client`）

| 位置 | 用途 | 是否跟随用户选择的模型 |
| --- | --- | --- |
| `storyboard_service.generate_storyboard`（:119） | 分镜脚本生成 | 是（请求可选 `model`） |
| `chat_service`（:315 / :836 / :921 / :965 流式） | 分镜聊天对话 + 会话标题总结 | 是（会话绑定模型） |
| `project/wizard.py`（:88） | 项目向导 | 是 |
| `project/shot_service.py`（:560 / :654） | 镜头改写 / 扩写 | 是 |
| `project/character_service.py`（:427） | 角色设定 | 是 |
| `project/prop_service.py`（:380） | 道具设定 | 是 |
| `moderation_service.py`（:367 / :435） | 内容审核 | 否（平台内部治理，建议保持默认 Provider） |

## 方案对比

### 方案 A：按模型路由（推荐，与图片/视频一致）

**client 层**——两个 client 实现补统一对话方法：

- `AgnesAIClient.chat_completions(body)`：即现有 `self._post(f"{self.base_url}/chat/completions", body)` 的具名封装，行为不变。
- `AGNSDKClientWrapper.chat_completions(body)`：调 aibridge `Client.chat(model, messages, ...)`（aibridge 已归一化为 OpenAI 风格结果），重新包装为 `{"choices": [{"message": {"content": ...}}], "usage": ...}`；失败抛中文 `RuntimeError`（与 `list_models` 同模式）。aibridge `chat` 返回的 `choices[0].message.content` 为标准字符串（方舟 auto 模式已实测）。

**路由**——所有跟随模型的调用点统一改为：

```python
client = await provider_registry.get_client_for_model(model)  # 未命中回退 agnes_client
result = await client.chat_completions(body)
```

`get_client_for_model` 对未注册模型 / 空 model_id 回退默认单例，现网行为完全兼容。

**范围控制**：

- `moderation_service` 保持 `agnes_client`（审核是平台治理行为，不跟随用户模型；后续可做成后台配置项）。
- 流式对话（`chat_service:965`，自管 httpx SSE）一期保持默认 Provider；aibridge `chat_stream` 的归一化成本较高，二期单独评估。

**改动量**：client 层 2 个方法（约 30 行）+ 7 个跟随模型的调用点各改 2 行 + `chat_service` 内部把会话模型传入 4 个私有方法（结构性改动，约 20 行）。

### 方案 B：全局默认对话 Provider（粗粒度）

`system_config` 增加「默认对话 Provider」，所有 chat 走它。实现最简，但不能按模型选择，无法满足"不同任务用更强文本模型"的诉求。可作为 A 的兜底开关，不单独推荐。

### 方案 C：维持现状

chat 只能用默认 Provider 的模型，多 Provider 对话能力名存实亡。

**推荐 A，分两期落地**：

- 一期：client 层基础设施 + `storyboard_service`（模型选择器前端已存在，用户最常用）。
- 二期：`chat_service` 对话与标题总结 + `project` 四个服务；流式对话单独评估。

## 错误与超时

- wrapper `chat_completions` 失败抛中文错误（"API Key 无效或已过期（对话失败）"等），沿用现有 `RuntimeError` → HTTPException 链路，前端弹窗可见。
- 超时：非流式走 aibridge 内部 httpx 管理；`chat_service` 流式分支自管的 120s 超时保持不变。

## 测试要点

1. 回归：默认 Provider（agnes）chat 模型行为不变——路由命中 provider 1，`AgnesAIClient.chat_completions` 与原 `_post` 路径等价。
2. 端到端：选 `ark-code-latest` 生成一次分镜 / 标题总结，请求应落在 `/api/plan/v3/chat/completions`。
3. 未注册模型 / Provider 已停用：回退默认 client，行为与现状一致。
4. 失败透出：非默认 Provider 的 key 失效时，前端能收到中文错误提示。

## 前端

无需改动。分镜聊天模型选择器已存在（`ComposerParamBar` / `ScriptWizard` 对话模型下拉），选项来自 `/api/config`；Provider 没有 `/models` 接口时，在配置页用 Provider 行的「添加模型」（或「新增自定义模型」）手动录入即可，`is_custom=True` 的模型不会被同步覆盖。

## 风险

- `chat_service` 四个调用点共享 `chat_url` property，一期若只改 storyboard，其余不受影响；二期重构时需一并迁移。
- aibridge 归一化需覆盖 `content` 为分段数组的情况（当前方舟与 OpenAI 兼容端点均返回标准字符串，风险低）。

---

## 落地记录（2026-08-30）

配置体系已随本次迭代实现，分级如下：

### 用户偏好（创作类，偏好设置页 → 生成偏好 → 默认对话模型）

- `generation.default_chat_model_id`：分镜脚本、剧本聊天（含流式）、项目向导、镜头改写、角色/场景/道具提取等创作环节的默认模型。
- 解析链：调用点显式指定 > 用户偏好 > 系统默认（管理员）> 注册表第一个 chat 模型。

### 管理员配置（系统级，管理后台 → 模型服务配置 `/admin/system-models`）

| 配置项 | system_configs key | 用途 |
| --- | --- | --- |
| 系统默认对话模型 | `model.chat_default` | 用户未设置偏好、各环节未单独配置时的全局兜底 |
| 内容审核模型 | `model.moderation_chat` | 图片/视频 AI 审核（不跟随用户偏好） |
| 会话标题总结模型 | `model.title_summary_chat` | 会话标题自动生成（建议低成本模型） |

### 改造的调用点

- 分镜脚本（`storyboard_service`，路由层按当前用户解析兜底）
- 分镜聊天 `chat_stream` 一/二次调用（会话用户偏好）+ 非流式 `chat()`（无用户上下文，走系统链）
- 会话标题总结（系统链 title_summary）
- 内容审核 ×2（系统链 moderation）
- 项目向导 4 步（step_config 显式 model > 项目所有者偏好 > 系统默认）
- 字幕拆分 ×2、镜头帧 prompt、镜头拆分、角色提取、场景提取、道具提取、剧本重生成（项目所有者偏好链）
- 全部 `agnes-2.0-flash` 硬编码与"注册表第一个"硬依赖已清零；wizard_chains 模板默认 model 改为空（存量种子数据如仍存旧模型名，可重新播种或编辑流水线步骤）

### 待办（二期）

- 流式对话之外，`chat()` 非流式遗留方法无调用方，如启用再接入用户链
- 审核模型可选是否跟随"低成本优先"策略（当前纯管理员指定）

### 错误处理（未配置 / 模型失效场景，已验证）

- 解析链每一级都校验模型仍在注册表中：用户偏好、管理员配置、显式指定指向已停用/已下线模型时自动落到下一级，不会把失效模型名发往上游。
- 全部落空（注册表无任何可用 chat 模型）时各调用点行为：
  - 分镜脚本：HTTP 400「未配置聊天模型」
  - 剧本聊天 / 项目向导 / 字幕：HTTP 500「未配置可用的对话模型，请先在配置页同步或添加对话模型」
  - 镜头帧 prompt / 镜头拆分 / 角色 / 场景 / 道具提取 / 剧本重生成：HTTP 400 同上
  - 内容审核：安全降级为通过（不误伤），记录 warning 日志
  - 会话标题总结：静默降级（取首条用户消息前 30 字或「新对话」）
