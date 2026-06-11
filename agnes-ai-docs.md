# Agnes AI 文档合集

> 来源：https://agnes-ai.com/doc/
> 抓取日期：2026 年 6 月 11 日

---

## 目录

- [概览](#概览)
- [Agnes 1.5 Flash](#agnes-15-flash)
- [Agnes 2.0 Flash](#agnes-20-flash)
- [Agnes Image 2.0 Flash](#agnes-image-20-flash)
- [Agnes Image 2.1 Flash](#agnes-image-21-flash)
- [Agnes Video V2.0](#agnes-video-v20)
- [隐私政策](#隐私政策)
- [服务条款](#服务条款)

---

## 概览

> 原始页面：https://agnes-ai.com/doc/overview

### 一、关于 Sapiens AI

Sapiens AI 是 Agnes AI 的母公司，专注于研发先进的多模态 AI 模型与基础设施，致力于为下一代智能应用、创意应用和交互式产品提供强大的 AI 能力支持。

我们的使命是：**让世界级 AI 属于每一个人。**

通过 Agnes AI，我们希望降低高质量 AI 技术的使用门槛，让开发者、创作者、创业团队和企业都能够以更简单、更稳定、更低成本的方式，将先进的 AI 能力接入自己的产品与业务中。

我们相信，世界级 AI 不应该只属于少数大型机构，而应该成为每一位开发者都能使用、每一个产品都能集成、每一个用户都能受益的基础能力。

**Agnes AI，让世界级 AI 属于每一个人。**

### 二、Agnes AI API 简介

Agnes AI API 为开发者提供统一、稳定、易接入的多模态 AI 模型服务，支持文本、图像、视频等多种生成与理解能力。

开发者可以通过 Agnes AI API 快速构建 AI 原生应用，包括但不限于：

- AI 对话与文本生成
- 逻辑推理与内容理解
- 文生图与图像编辑
- 图生视频与视频生成
- 音视频同步生成
- Agent 工具与自动化工作流
- 创意内容生成与多模态交互应用

Agnes AI API 兼容 OpenAI 风格接口，方便开发者基于现有代码快速迁移和接入，减少开发成本，提高集成效率。

### 三、核心能力

Agnes AI API 目前主要支持以下核心能力：

#### 1. 文本生成与推理

支持高质量文本生成、内容续写、摘要提取、逻辑推理、问答对话、代码辅助和 Agent 任务处理等场景。

适用场景包括：

- AI 聊天助手
- 内容创作
- 文档总结
- 智能问答
- 代码生成
- Agent 自动化任务

#### 2. 图像生成与编辑

支持根据文本提示词生成高清图像，也支持对已有图片进行修改、优化和风格化处理。

适用场景包括：

- 文生图
- 图像编辑
- 商品图生成
- 创意海报生成
- 角色形象生成
- 社交媒体素材制作

#### 3. 视频与音视频同步生成

支持生成高质量视频内容，并可支持音频与画面同步生成，减少后期制作流程，提升内容生产效率。

适用场景包括：

- AI 视频生成
- 图生视频
- 短视频创作
- 创意广告素材
- 角色动画
- 音视频同步内容生成

#### 4. 多模态理解与创作

支持文本、图像、视频等多种模态能力组合，帮助开发者构建更智能、更自然的交互体验。

适用场景包括：

- 多模态 AI 助手
- 图片理解
- 视频理解
- 创意工作流
- AI 社交互动
- 教育、娱乐与生产力工具

### 四、模型能力概览

Agnes AI 提供多类型模型能力，包括文本模型、图像模型、视频模型和多模态模型。

其中，Sapiens AI 的模型体系包括高精度的 Claw 系列模型，以及面向创意生成场景的图像、视频和音视频模型。

这些模型可以帮助开发者快速完成从内容理解、文本生成，到图像生成、图像编辑、视频生成的完整 AI 能力接入。

### 五、接口兼容性

Agnes AI API 兼容 OpenAI 风格接口。

如果你已经使用过 OpenAI-Compatible API，通常只需要修改以下配置即可完成接入：

- Base URL
- API Key
- Model Name

这种兼容方式可以帮助开发者快速迁移现有项目，降低接入成本，并减少重复开发工作。

### 六、Base URL

所有 API 请求都应基于以下 Base URL 发起：

```
https://apihub.agnes-ai.com/v1
```

请确保请求路径基于该地址拼接，避免因路径错误导致接口请求失败。

### 七、身份认证

所有 API 请求都需要通过 API Key 进行身份认证。

请在请求 Header 中携带以下参数，并将 `YOUR_API_KEY` 替换为你自己的有效 API Key：

```
Authorization: Bearer YOUR_API_KEY
```

### 八、安全提醒

API Key 属于敏感信息，请妥善保管。

请勿将 API Key 暴露在以下位置：

- 公开代码仓库
- 前端客户端代码
- 截图或录屏内容
- 公开文档
- 可被他人访问的配置文件

如发现 API Key 泄露，建议立即在控制台删除或重置该 Key，以避免产生非授权调用。

### 九、快速开始

你可以按照以下步骤快速开始使用 Agnes AI API：

#### 第一步：创建 API Key

登录 Agnes AI 控制台，进入 API Key 管理页面，创建并复制你的 API Key。

#### 第二步：选择模型

根据你的使用场景选择对应模型，例如文本模型、图像模型、视频模型或多模态模型。

#### 第三步：配置请求地址

将 API Base URL 配置为：

```
https://apihub.agnes-ai.com/v1
```

#### 第四步：发起 API 请求

在请求 Header 中加入 API Key，并按照 OpenAI-Compatible API 格式发起请求。

### 十、适用开发场景

Agnes AI API 适合用于以下产品和业务场景：

- AI 聊天应用
- AI 搜索与研究工具
- AI 写作与办公工具
- AI 图片生成工具
- AI 视频生成工具
- AI 角色与互动应用
- AI 社交产品
- Agent 自动化平台
- 创意内容生产平台
- 教育、娱乐、电商与营销工具

### 十一、文档说明

本文档用于帮助开发者快速了解 Agnes AI API 的基础能力、接入方式和使用规范。

如需查看具体模型参数、请求示例、返回格式和错误码说明，请继续阅读对应模型的详细接入文档。

---

## Agnes 1.5 Flash

> 原始页面：https://agnes-ai.com/doc/agnes-15-flash

### 模型概述

Agnes-1.5-Flash 是一款轻量、高效的大语言模型，针对低延迟、高并发和低成本部署场景进行了优化。

**Agnes-1.5-Flash 具备以下特点：**

- 采用先进的量化技术，显著降低计算资源需求
- 在模型性能与推理速度之间取得良好平衡，适合生产环境中的实时应用场景
- 支持文本 + 图像的多模态输入

### 适用场景

Agnes-1.5-Flash 适用于以下场景：

- 实时交互类应用
- 高并发服务系统
- 成本敏感型业务负载
- 轻量化智能接口

### API 信息

| 项目 | 说明 |
|------|------|
| API Endpoint | https://apihub.agnes-ai.com/v1/chat/completions |
| Request Method | POST |
| Content-Type | application/json |
| Authentication Method | Bearer Token |
| Authentication Header | Authorization: Bearer YOUR_API_KEY |

### 请求参数

| 参数 | 类型 | 是否必填 | 说明 |
|------|------|----------|------|
| model | string | 是 | 模型名称，固定为 `agnes-1.5-flash` |
| messages | array | 是 | 对话消息数组 |
| temperature | number | 否 | 采样温度，用于控制生成内容的随机性 |
| top_p | number | 否 | 核采样概率 |
| max_tokens | integer | 否 | 最大生成 token 数 |
| frequency_penalty | number | 否 | 频率惩罚，用于减少重复内容 |
| presence_penalty | number | 否 | 存在惩罚，用于鼓励模型引入新话题 |
| repetition_penalty | number | 否 | 重复控制系数 |
| stop | string / array | 否 | 自定义停止序列 |
| seed | integer | 否 | 随机种子，用于保证结果可复现 |

### 调用示例

#### 1. 纯文本对话请求

```bash
curl https://apihub.agnes-ai.com/v1/chat/completions \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "agnes-1.5-flash",
    "messages": [
      {
        "role": "user",
        "content": "what'\''s this?"
      }
    ],
    "temperature": 0.5,
    "max_tokens": 1024
  }'
```

#### 2. 多模态请求（文本 + 图像）

```bash
curl https://apihub.agnes-ai.com/v1/chat/completions \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "agnes-1.5-flash",
    "messages": [
      {
        "role": "user",
        "content": [
          {
            "type": "text",
            "text": "Describe this image"
          },
          {
            "type": "image_url",
            "image_url": {
              "url": "https://example.com/image.jpg"
            }
          }
        ]
      }
    ]
  }'
```

### 响应格式

```json
{
  "id": "chatcmpl-xxx",
  "object": "chat.completion",
  "created": 1773803415,
  "model": "agnes-1.5-flash",
  "choices": [
    {
      "index": 0,
      "finish_reason": "stop",
      "message": {
        "role": "assistant",
        "content": "This image shows..."
      }
    }
  ],
  "usage": {
    "prompt_tokens": 120,
    "completion_tokens": 300,
    "total_tokens": 420
  }
}
```

### 响应字段说明

- **id**：本次对话请求的唯一 ID
- **created**：请求时间戳
- **choices[0].message.content**：模型返回的内容
- **finish_reason**：生成结束原因，例如 stop、length 等
- **usage**：Token 消耗统计

### 模型限制

| 项目 | 数值 |
|------|------|
| Context | 256K |
| Max Output | 65.5K |

### 价格

| 类型 | 价格 | 现价 |
|------|------|------|
| Input Tokens | $0.07 / 1M tokens | $0 / 1M tokens |
| Output Tokens | $0.15 / 1M tokens | $0 / 1M tokens |

### 功能与兼容性

- 支持文本 + 图像多模态输入
- 针对低延迟和高吞吐场景优化
- 兼容 OpenAI Chat Completions API
- 兼容 OpenAI Responses API
- 适合低成本生产环境部署

---

## Agnes 2.0 Flash

> 原始页面：https://agnes-ai.com/doc/agnes-20-flash

### 模型概述

Agnes-2.0-Flash 是由 Sapiens AI 开发的一款快速、高效的语言模型，面向智能体工作流、工具调用、编程任务、推理、多轮对话、图片理解以及高频生产环境应用场景设计。

Agnes-2.0-Flash 在 Claw-Eval 基准测试中取得了强劲表现，在 General Leaderboard 中排名第 9，Pass^3 分数为 60.9%，展现出在主流语言模型中较强的自主智能体能力。

**该模型支持以下能力：**

| 能力 | 说明 |
|------|------|
| Chat Completion | 为对话和应用生成高质量回复 |
| 多轮对话 | 在多轮交互中保持上下文连续性 |
| 图片 URL 输入 | 支持通过公网图片 URL 传入图片内容 |
| 图片理解 | 支持基于图片的内容理解、截图分析和信息提取 |
| 工具调用 | 调用外部工具和函数，支持智能体工作流 |
| 智能体工作流 | 支持规划、执行和多步骤任务完成 |
| 编程任务 | 辅助代码生成、调试、解释和重构 |
| 推理 | 处理结构化推理、任务拆解和决策 |
| 流式输出 | 实时返回响应，提升用户体验 |
| OpenAI 兼容 API | 使用兼容 OpenAI Chat Completions API 的结构 |

### 适用场景

| 场景 | 示例用例 |
|------|---------|
| AI 助手 | 通用问答、日常助手、效率支持 |
| 自主智能体 | 多步骤任务执行、规划和工具使用 |
| 编程助手 | 代码生成、调试、重构和解释 |
| 工作流自动化 | 任务拆解、流程自动化和执行规划 |
| 客户支持 | FAQ 问答、客服聊天机器人、服务自动化 |
| 搜索与问答 | 基于搜索的回答、摘要生成、信息提取 |
| 内容生成 | 营销文案、文章、产品描述、脚本 |
| 开发者工具 | API 助手、文档助手、编程 Copilot |
| AI 原生应用 | 消费级应用、效率工具、智能体应用 |
| 图片理解 | 图片描述、截图分析、视觉问答、信息提取 |

### API 信息

| 项目 | 说明 |
|------|------|
| API Endpoint | https://apihub.agnes-ai.com/v1/chat/completions |
| Request Method | POST |
| Content-Type | application/json |
| Authentication | Bearer Token |
| Authentication Header | Authorization: Bearer YOUR_API_KEY |

### 请求参数

| 参数 | 类型 | 是否必填 | 说明 |
|------|------|----------|------|
| model | string | 是 | 模型名称，固定为 `agnes-2.0-flash` |
| messages | array | 是 | 对话消息数组，包括 system、user 和 assistant 消息 |
| messages[].content | string / array | 是 | 消息内容。可为纯文本字符串，也可为包含 text、image_url 的内容数组 |
| temperature | number | 否 | 控制输出随机性。较低值会生成更确定性的结果 |
| top_p | number | 否 | 控制核采样。较低值会使输出更加聚焦 |
| max_tokens | number | 否 | 响应中最多生成的 token 数 |
| stream | boolean | 否 | 是否启用流式响应输出 |
| tools | array | 否 | 用于工具调用工作流的工具定义 |
| tool_choice | string / object | 否 | 控制模型是否以及如何使用工具 |
| chat_template_kwargs | object | 否 | OpenAI 兼容请求中用于开启 Thinking 等扩展能力 |
| thinking | object | 否 | Anthropic 兼容请求中用于开启 Thinking 模式 |

### 图片 URL 输入支持

Agnes-2.0-Flash 支持通过图片 URL 输入图片内容。开发者可以在同一个 messages 请求中同时传入文本指令和图片 URL，让模型基于图片进行理解、分析、问答或信息提取。

**支持的输入类型包括：**

| 输入类型 | 支持方式 | 说明 |
|---------|---------|------|
| 文本 | text | 普通文本指令或问题 |
| 图片 URL | image_url | 通过公网可访问的图片链接传入图片 |

**图片内容结构示例：**

```json
{
  "role": "user",
  "content": [
    {
      "type": "text",
      "text": "Describe the content of this image."
    },
    {
      "type": "image_url",
      "image_url": {
        "url": "https://example.com/image.jpg"
      }
    }
  ]
}
```

### 调用示例

#### 1. 基础 Chat Completion 请求

```bash
curl https://apihub.agnes-ai.com/v1/chat/completions \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "agnes-2.0-flash",
    "messages": [
      {
        "role": "system",
        "content": "You are a helpful AI assistant."
      },
      {
        "role": "user",
        "content": "Explain how autonomous agents use tools to complete tasks."
      }
    ],
    "temperature": 0.7,
    "max_tokens": 1024
  }'
```

#### 2. 流式输出请求

```bash
curl https://apihub.agnes-ai.com/v1/chat/completions \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "agnes-2.0-flash",
    "messages": [
      {
        "role": "user",
        "content": "Write a short product introduction for an AI assistant app."
      }
    ],
    "stream": true
  }'
```

#### 3. 工具调用请求

```bash
curl https://apihub.agnes-ai.com/v1/chat/completions \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "agnes-2.0-flash",
    "messages": [
      {
        "role": "user",
        "content": "What is the weather like in Singapore today?"
      }
    ],
    "tools": [
      {
        "type": "function",
        "function": {
          "name": "get_weather",
          "description": "Get the current weather for a location",
          "parameters": {
            "type": "object",
            "properties": {
              "location": {
                "type": "string",
                "description": "The city and country"
              }
            },
            "required": ["location"]
          }
        }
      }
    ]
  }'
```

#### 4. 图片 URL 输入请求

```bash
curl https://apihub.agnes-ai.com/v1/chat/completions \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "agnes-2.0-flash",
    "messages": [
      {
        "role": "user",
        "content": [
          {
            "type": "text",
            "text": "Describe the content of this image."
          },
          {
            "type": "image_url",
            "image_url": {
              "url": "https://example.com/image.jpg"
            }
          }
        ]
      }
    ]
  }'
```

### 响应格式

```json
{
  "id": "chatcmpl_xxx",
  "object": "chat.completion",
  "created": 1774432125,
  "model": "agnes-2.0-flash",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "Autonomous agents use tools by understanding the user's goal, breaking it into steps, selecting the right tools, executing actions, and using the results to complete the task."
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 35,
    "completion_tokens": 58,
    "total_tokens": 93
  }
}
```

### 响应字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| id | string | 本次补全请求的唯一 ID |
| object | string | 对象类型，通常为 chat.completion |
| created | integer | 请求时间戳 |
| model | string | 本次请求使用的模型 |
| choices | array | 生成的响应结果列表 |
| choices[].index | integer | 响应结果的索引 |
| choices[].message | object | Assistant 消息对象 |
| choices[].message.role | string | 消息发送者角色 |
| choices[].message.content | string | 模型生成的响应内容 |
| choices[].finish_reason | string | 生成停止原因 |
| usage | object | Token 使用信息 |
| usage.prompt_tokens | integer | 输入 token 数量 |
| usage.completion_tokens | integer | 输出 token 数量 |
| usage.total_tokens | integer | 使用的 token 总数 |

### 为编码任务启用 Thinking

对于代码编写、调试、推理和 Agent 工作流，建议开启 Thinking 模式，以提升代码质量、任务拆解能力和问题解决效果。

**OpenAI 兼容请求方式：**

```json
{
  "model": "agnes-2.0-flash",
  "messages": [
    {
      "role": "user",
      "content": "Help me write a Python script to process a CSV file."
    }
  ],
  "chat_template_kwargs": {
    "enable_thinking": true
  }
}
```

**Anthropic 兼容请求方式：**

```json
{
  "model": "agnes-2.0-flash",
  "messages": [
    {
      "role": "user",
      "content": "Help me refactor this TypeScript function and explain the changes."
    }
  ],
  "thinking": {
    "type": "enabled",
    "budget_tokens": 2048
  }
}
```

`budget_tokens` 用于控制最大 Thinking token 预算。对于常见编码任务，建议从 2048 开始设置。对于更复杂的调试、重构或多步骤 Agent 任务，可以根据需要适当提高该值。

### 功能与兼容性

- Chat Completion
- 多轮对话
- System Prompt
- 图片 URL 输入
- 图片理解
- 流式输出
- 工具调用
- 智能体工作流
- 编程任务
- 推理任务
- JSON 风格输出
- 兼容 OpenAI Chat Completions API 的请求结构

### 最佳实践

#### Prompt 编写建议

为了获得更好的结果，建议提供清晰的指令、上下文和期望的输出格式。

**示例：产品文案生成**

> You are a product marketing expert. Write a concise App Store description for an AI assistant app. The tone should be clear, professional, and user-friendly.

**示例：编程任务**

> 对于编程任务，建议提供编程语言、框架、错误信息和期望行为。

> Help me debug this React component. The issue is that the button state does not update after clicking. Explain the cause and provide the corrected code.

**示例：智能体工作流**

> You are an autonomous research agent. Search for relevant information, summarize the key findings, and return the result in a structured format with source links.

**示例：图片理解任务**

> Analyze this screenshot. Identify the main UI elements, explain the possible issue, and provide suggestions to improve the user experience.

#### 推荐 Prompt 结构

建议使用以下结构组织 Prompt：

```
[Role] + [Task] + [Context] + [Requirements] + [Output Format]
```

**示例**

> You are a senior product manager. Analyze this feature idea for an AI assistant app. Consider user value, implementation complexity, risks, and return the result in a structured table.

#### 图片理解 Prompt 示例

> You are an image analysis assistant. Analyze the provided image URL, summarize the key information, identify potential issues, and return the result in a structured table.

#### 图片 URL 使用建议

- 图片 URL 必须可公网访问
- 如果图片 URL 需要登录、鉴权或存在防盗链，模型可能无法读取
- 建议使用标准图片格式，例如 JPG、JPEG、PNG 或 WebP
- 对于截图、报错图、产品界面图，建议在文本中补充你希望模型重点关注的问题
- 图片 URL 输入可以与工具调用、流式输出和 Agent 工作流结合使用

### 模型限制

| 项目 | 数值 |
|------|------|
| Context | 256K |
| Max Output | 65.5K |

### 价格

| 类型 | 价格 | 现价 |
|------|------|------|
| Input Tokens | $0.03 / 1M tokens | $0 / 1M tokens |
| Output Tokens | $0.15 / 1M tokens | $0 / 1M tokens |

### 说明

使用 `agnes-2.0-flash` 作为模型名称。

基础 Chat Completion 请求必须包含 model 和 messages。

messages[].content 可使用纯文本字符串，也可使用包含文本和图片 URL 的内容数组。

如需输入图片，请使用 image_url 并提供公网可访问的图片 URL。

如需启用流式响应，请将 stream 设置为 true。

对于工具调用工作流，请提供 tools，并可按需提供 tool_choice。

temperature 用于控制随机性。较低值更适合确定性任务，较高值更适合创意生成。

Agnes-2.0-Flash 适合需要快速响应、强任务完成能力、图片理解能力和可靠智能体表现的生产级应用。

---

## Agnes Image 2.0 Flash

> 原始页面：https://agnes-ai.com/doc/agnes-image-20-flash

### 一、模型简介

Agnes-Image-2.0-Flash 是由 Sapiens AI 开发的一款高性能图像生成与图像编辑模型。

该模型支持文生图、图生图和多图合成工作流，适用于快速创意生产、图像优化、营销视觉设计、电商产品图、社交内容生成以及专业视觉内容生产等场景。

Agnes-Image-2.0-Flash 已登上 Artificial Analysis Image Editing Leaderboard，取得 ELO 1,184【动态调整】的成绩，并进入 Top 20 区间，展现出在主流图像模型中较强的图像编辑能力。

### 二、模型概述

Agnes-Image-2.0-Flash 针对快速、高质量的图像生成与图像编辑任务进行了优化。

**该模型支持以下能力：**

| 能力 | 说明 |
|------|------|
| Text-to-Image | 根据文本 Prompt 生成图像 |
| Image-to-Image | 基于输入图像进行编辑、转换或增强 |
| Multi-Image Input | 支持输入多张参考图并合成为一张新图像 |
| Image Editing | 修改构图、风格、对象、背景、场景和视觉细节 |
| Style Control | 调整艺术风格、光照、布局和视觉方向 |
| Fast Generation | 针对快速、低成本的生产工作流进行优化 |
| OpenAI-Compatible API | 使用兼容 OpenAI Images API 的请求结构 |

### 三、适用场景

| 场景 | 示例用例 |
|------|---------|
| 创意设计 | 海报、概念艺术、社交媒体视觉图 |
| 营销内容 | 产品广告、活动创意、Banner |
| 文生图 | 通过 Prompt 生成产品图、插画、场景图、概念图 |
| 图像编辑 | 对象替换、背景更换、风格转换、局部改图 |
| 角色合成 | 将多个角色或参考图组合到同一场景中 |
| 视觉生产 | 为 App、网站、游戏和视频生成素材 |
| 电商 | 产品图优化、场景化产品图、营销主图 |
| 社交内容 | Meme、头像、缩略图、生活方式视觉图 |

### 四、API 基础信息

| 项目 | 内容 |
|------|------|
| Base URL | https://apihub.agnes-ai.com |
| Endpoint | POST https://apihub.agnes-ai.com/v1/images/generations |
| Headers | Authorization: Bearer YOUR_API_KEY / Content-Type: application/json |

### 五、模型名称

**agnes-image-2.0-flash**

| 模型 | 用途 |
|------|------|
| agnes-image-2.0-flash | 文生图、图生图、多图合成、图像编辑 |

### 六、请求参数

| 参数 | 类型 | 是否必填 | 说明 |
|------|------|----------|------|
| model | string | 是 | 模型名称，固定为 `agnes-image-2.0-flash` |
| prompt | string | 是 | 描述目标图像或编辑需求的文本提示词 |
| size | string | 是 | 输出图像尺寸，例如 `1024x768` |
| image | string[] | 图生图必填 | 输入图片数组，支持公网 URL 或 Data URI Base64 |
| return_base64 | boolean | 否 | 文生图返回 Base64 时使用 |
| extra_body.response_format | string | 否 | 输出格式，常用 `url` 或 `b64_json` |

### 七、重要说明

#### 1. 文生图不需要传 image

文生图只需要传入：

```json
{
  "model": "agnes-image-2.0-flash",
  "prompt": "A clean product photo of a glass cube on a white studio background, soft shadows, high detail",
  "size": "1024x768"
}
```

#### 2. 图生图需要传 image

图生图或多图合成时，需要在顶层传入 image 数组：

```json
{
  "image": [
    "https://example.com/input.png"
  ]
}
```

多图合成时可以传入多个图片 URL：

```json
{
  "image": [
    "https://example.com/character-1.png",
    "https://example.com/character-2.png"
  ]
}
```

#### 3. 图生图不需要传 tags

当前接入方式中，图生图请求不需要传：

```json
{
  "tags": ["img2img"]
}
```

只需要传入 model、prompt、size 和 image。

#### 4. response_format 不要放在顶层

不要这样写：

```json
{
  "response_format": "url"
}
```

推荐写法：

```json
{
  "extra_body": {
    "response_format": "url"
  }
}
```

如果将 response_format 放在顶层，可能会返回 400 错误。

### 八、调用示例

#### 1. 文生图：URL 输出

```bash
curl https://apihub.agnes-ai.com/v1/images/generations \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "agnes-image-2.0-flash",
    "prompt": "A clean product photo of a glass cube on a white studio background, soft shadows, high detail",
    "size": "1024x768",
    "extra_body": {
      "response_format": "url"
    }
  }'
```

生成图片 URL 位于：`data[0].url`

#### 2. 文生图：Base64 输出

```bash
curl https://apihub.agnes-ai.com/v1/images/generations \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "agnes-image-2.0-flash",
    "prompt": "A clean product photo of a glass cube on a white studio background, soft shadows, high detail",
    "size": "1024x768",
    "return_base64": true
  }'
```

生成图片 Base64 位于：`data[0].b64_json`

#### 3. 图生图：URL 输入，URL 输出

```bash
curl https://apihub.agnes-ai.com/v1/images/generations \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "agnes-image-2.0-flash",
    "prompt": "Transform this image into a cinematic cyberpunk style while preserving the main subject and composition",
    "size": "1024x768",
    "extra_body": {
      "image": [
        "https://example.com/input-image.png"
      ],
      "response_format": "url"
    }
  }'
```

生成图片 URL 位于：`data[0].url`

#### 4. 图生图：URL 输入，Base64 输出

```bash
curl https://apihub.agnes-ai.com/v1/images/generations \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "agnes-image-2.0-flash",
    "prompt": "Make the object orange while preserving the original composition",
    "size": "1024x768",
    "extra_body": {
      "image": [
        "https://example.com/input-image.png"
      ],
      "response_format": "b64_json"
    }
  }'
```

生成图片 Base64 位于：`data[0].b64_json`

#### 5. 图生图：Data URI Base64 输入

```bash
curl https://apihub.agnes-ai.com/v1/images/generations \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "agnes-image-2.0-flash",
    "prompt": "Make the object matte black while preserving the original composition",
    "size": "1024x768",
    "extra_body": {
      "image": [
        "data:image/png;base64,BASE64_HERE"
      ],
      "response_format": "b64_json"
    }
  }'
```

#### 6. 多图合成请求

```bash
curl https://apihub.agnes-ai.com/v1/images/generations \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "agnes-image-2.0-flash",
    "prompt": "Combine the two characters into an intense fantasy battle scene, dynamic lighting, detailed background, cinematic composition",
    "size": "1024x768",
    "extra_body": {
      "image": [
        "https://example.com/character-1.png",
        "https://example.com/character-2.png"
      ],
      "response_format": "url"
    }
  }'
```

### 九、响应格式

#### 1. URL 输出

```json
{
  "created": 1780000000,
  "data": [
    {
      "url": "https://storage.googleapis.com/agnes-aigc/xxx.png",
      "b64_json": null,
      "revised_prompt": null
    }
  ]
}
```

#### 2. Base64 输出

```json
{
  "created": 1780000000,
  "data": [
    {
      "url": null,
      "b64_json": "iVBORw0KGgoAAAANSUhEUgAA...",
      "revised_prompt": null
    }
  ]
}
```

### 十、响应字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| created | integer | 请求创建时间戳 |
| data | array | 生成图片结果列表 |
| data[].url | string / null | 生成图片 URL，Base64 输出时通常为 null |
| data[].b64_json | string / null | Base64 图片数据，URL 输出时通常为 null |
| data[].revised_prompt | string / null | 修订后的 Prompt，如无则为 null |

### 十一、价格

| 类型 | 原价 | 当前价格 |
|------|------|----------|
| Generated Images | $0.003 / image | $0 / image |

### 十二、功能与兼容性

- 文生图生成
- 图生图编辑
- 多图输入与合成
- 基于 Prompt 的图像转换
- 稳定的风格与构图控制
- 支持公网 URL 图片输入
- 支持 Data URI Base64 图片输入
- 支持 URL 或 Base64 输出
- 面向生产工作流的快速生成
- 兼容 OpenAI Images API 的请求结构

### 十三、最佳实践

#### 1. 文生图 Prompt 编写建议

为了获得更好的生成效果，建议在 Prompt 中提供清晰的视觉指令，包括主体、场景、风格、光照、构图和质量要求。

**示例：**

> A professional product photo of a wireless headphone on a clean white background, soft studio lighting, sharp details, commercial photography style

#### 2. 图像编辑 Prompt 编写建议

对于编辑任务，建议明确描述需要改变的内容，以及需要保持不变的内容。

**示例：**

> Change the background to a futuristic city at night while keeping the person's face, outfit, and pose unchanged

#### 3. 多图合成 Prompt 编写建议

对于多图合成任务，建议描述不同输入图像之间的关系。

**示例：**

> Place the person from the first image beside the robot from the second image in a cinematic sci-fi battle scene

### 十四、推荐 Prompt 结构

**文生图 Prompt 结构**

```
[Main subject] + [Scene / background] + [Style] + [Lighting] + [Composition] + [Quality requirements]
```

**示例：**

> A young explorer standing in an ancient temple, cinematic fantasy style, warm dramatic lighting, wide-angle composition, ultra detailed, high quality

**图生图 Prompt 结构**

```
[Editing instruction] + [Elements to preserve] + [Target style / scene] + [Lighting] + [Composition] + [Quality requirements]
```

**示例：**

> Change the background into a cinematic fantasy temple while preserving the person's face, outfit, and pose, warm dramatic lighting, wide-angle composition, ultra detailed, high quality

### 十五、常见问题

#### 1. Agnes-Image-2.0-Flash 是否支持文生图？

支持。文生图请求不需要传入 image，只需要传入 model、prompt 和 size。

#### 2. Agnes-Image-2.0-Flash 是否支持图生图？

支持。

#### 3. 输入图片 URL 不可访问怎么办？

如果输入图片 URL 不能被服务端访问，可能导致请求失败。

建议使用：

- 公网可访问的 HTTPS 图片地址
- Data URI Base64 输入

#### 4. 请求超时怎么办？

图片生成可能需要数秒到几十秒。

客户端建议设置较长超时时间，例如：60s - 360s

### 十六、接入检查清单

接入前建议确认：

- 已获得有效 API Key
- 请求地址为 https://apihub.agnes-ai.com/v1/images/generations
- Header 中已添加 `Authorization: Bearer YOUR_API_KEY`
- Header 中已添加 `Content-Type: application/json`
- 模型名称为 `agnes-image-2.0-flash`
- response_format 放在 extra_body 中

---

## Agnes Image 2.1 Flash

> 原始页面：https://agnes-ai.com/doc/agnes-image-21-flash

### 模型概述

Agnes Image 2.1 Flash 是 Sapiens AI 升级推出的图像生成模型，支持文生图和图生图两种工作流。

相比之前版本，Agnes Image 2.1 Flash 在高信息密度图像生成方面进行了优化，更适合复杂视觉细节、丰富构图、密集元素和清晰语义对齐等场景。

Agnes Image 2.1 Flash 可用于根据文本提示词生成图像，也可基于已有图片进行风格转换、局部优化、场景重塑或视觉增强，并支持以图片 URL 或 Base64 数据形式返回生成结果。

### 核心能力

| 能力 | 说明 |
|------|------|
| 文生图 | 根据自然语言提示词生成高质量图片 |
| 图生图 | 根据提示词对已有图片进行转换、编辑或优化 |
| 高信息密度图像优化 | 更好处理复杂布局、丰富细节和密集视觉元素 |
| 构图保持 | 图生图时可尽量保持原图构图、主体结构和视角 |
| 灵活尺寸控制 | 支持自定义输出尺寸，例如 `1024x768` |
| URL 返回 | 支持将生成结果以可访问图片 URL 返回 |
| Base64 返回 | 支持将生成结果以 Base64 数据返回 |
| URL 或 Data URI 输入 | 图生图支持公网图片 URL 或 Data URI Base64 输入 |

### 适用场景

| 场景 | 示例用途 |
|------|---------|
| 创意设计 | 概念图、视觉探索、海报草图 |
| 营销内容 | 活动图、产品视觉、社交媒体素材 |
| 高密度视觉生成 | 复杂场景、丰富构图、密集元素画面 |
| 图片转换 | 风格迁移、场景重打光、背景转换 |
| 内容生产 | App 素材、缩略图、Banner、叙事视觉 |
| 产品视觉 | 产品图、展示图、商业视觉 |
| 社交媒体素材 | 封面图、横幅图、帖子配图 |

### API 信息

| 项目 | 说明 |
|------|------|
| Base URL | https://apihub.agnes-ai.com |
| API Endpoint | https://apihub.agnes-ai.com/v1/images/generations |
| 请求方法 | POST |
| Content-Type | application/json |
| 认证方式 | Bearer Token |
| 认证 Header | Authorization: Bearer YOUR_API_KEY |

### 模型名称

文生图和图生图均使用以下模型名称：

**agnes-image-2.1-flash**

### 重要说明

- 请使用 `agnes-image-2.1-flash` 作为模型名称
- 文生图请求中，model、prompt、size 为必填参数
- 图生图请求中，请将输入图片放在顶层 image 数组中
- image 支持公网图片 URL，也支持 Data URI Base64
- 不要将 response_format 放在请求体顶层，否则可能返回 400 错误
- 如需 URL 输出，请将 `"response_format": "url"` 放在 extra_body 中
- 如需文生图 Base64 输出，可使用顶层参数 `"return_base64": true`
- 如需图生图 Base64 输出，请在 extra_body 中设置 `"response_format": "b64_json"`
- 图生图不需要传 `tags: ["img2img"]`
- 公开文档中不要暴露临时 API Key，请统一使用 `YOUR_API_KEY`

### 请求参数

| 参数 | 类型 | 是否必填 | 说明 |
|------|------|----------|------|
| model | string | 是 | 模型名称，固定使用 `agnes-image-2.1-flash` |
| prompt | string | 是 | 图片生成或图片编辑提示词 |
| size | string | 是 | 输出图片尺寸，例如 `1024x768` |
| image | string[] | 图生图必填 | 输入图片数组，支持公网 URL 或 Data URI Base64 |
| return_base64 | boolean | 否 | 文生图需要返回 Base64 时使用 |
| extra_body | object | 否 | 高级工作流扩展参数 |
| extra_body.response_format | string | 否 | 输出格式，常用值为 `url` 或 `b64_json` |

### 调用示例

#### 1. 文生图：URL 输出

```bash
curl https://apihub.agnes-ai.com/v1/images/generations \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "agnes-image-2.1-flash",
    "prompt": "A luminous floating city above a misty canyon at sunrise, cinematic realism",
    "size": "1024x768",
    "extra_body": {
      "response_format": "url"
    }
  }'
```

生成图片 URL 位于：`data[0].url`

#### 2. 文生图：Base64 输出

```bash
curl https://apihub.agnes-ai.com/v1/images/generations \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "agnes-image-2.1-flash",
    "prompt": "A clean product photo of a glass cube on a white studio background, soft shadows, high detail",
    "size": "1024x768",
    "return_base64": true
  }'
```

生成图片 Base64 位于：`data[0].b64_json`

#### 3. 图生图：URL 输入，URL 输出

```bash
curl https://apihub.agnes-ai.com/v1/images/generations \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "agnes-image-2.1-flash",
    "prompt": "Transform the scene into a rain-soaked cyberpunk night with neon reflections while preserving the original composition",
    "size": "1024x768",
    "extra_body": {
      "image": [
        "https://example.com/input-image.png"
      ],
      "response_format": "url"
    }
  }'
```

生成图片 URL 位于：`data[0].url`

#### 4. 图生图：URL 输入，Base64 输出

```bash
curl https://apihub.agnes-ai.com/v1/images/generations \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "agnes-image-2.1-flash",
    "prompt": "Make the object orange while preserving the original composition",
    "size": "1024x768",
    "extra_body": {
      "image": [
        "https://example.com/input-image.png"
      ],
      "response_format": "b64_json"
    }
  }'
```

生成图片 Base64 位于：`data[0].b64_json`

#### 5. 图生图：Data URI Base64 输入

```bash
curl https://apihub.agnes-ai.com/v1/images/generations \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "agnes-image-2.1-flash",
    "prompt": "Make the object matte black while preserving the original composition",
    "size": "1024x768",
    "extra_body": {
      "image": [
        "data:image/png;base64,BASE64_HERE"
      ],
      "response_format": "b64_json"
    }
  }'
```

### 返回格式

#### URL 输出

当 `extra_body.response_format` 设置为 url 时，返回格式如下：

```json
{
  "created": 1780000000,
  "data": [
    {
      "url": "https://storage.googleapis.com/agnes-aigc/xxx.png",
      "b64_json": null,
      "revised_prompt": null
    }
  ]
}
```

生成图片 URL：`data[0].url`

#### Base64 输出

当启用 Base64 输出时，返回格式如下：

```json
{
  "created": 1780000000,
  "data": [
    {
      "url": null,
      "b64_json": "iVBORw0KGgoAAAANSUhEUgAA...",
      "revised_prompt": null
    }
  ]
}
```

生成图片 Base64：`data[0].b64_json`

### 推荐提示词结构

为了获得更好的图像生成效果，建议使用清晰的提示词结构：

```
[主体] + [场景 / 环境] + [风格] + [光照] + [构图] + [质量要求]
```

**示例**

> A luminous floating city above a misty canyon at sunrise, cinematic realism, wide-angle composition, rich architectural details, soft golden light, high visual density

对于图生图任务，需要明确说明"要改变什么"和"要保留什么"。

> Transform the scene into a rain-soaked cyberpunk night with neon reflections while preserving the original composition and main subject layout.

### 最佳实践

#### 文生图建议

生成复杂图片时，建议使用更具体的提示词，包含主体、环境、风格、光照、镜头角度和细节要求。

**较好示例：**

> A futuristic city marketplace filled with flying vehicles, holographic signs, dense crowds, neon lighting, cinematic realism, ultra-detailed, high-information-density composition

推荐包含以下元素：

- 主体
- 场景或环境
- 视觉风格
- 光照
- 镜头角度
- 构图
- 细节密度
- 质量要求

#### 图生图建议

编辑已有图片时，建议同时说明转换要求和保留要求。

**较好示例：**

> Convert the image into a fantasy winter landscape, add snow, warm window lights, and a magical atmosphere, while preserving the original building structure and camera angle.

推荐结构：

```
[修改要求] + [新风格 / 新场景] + [需要添加或移除的元素] + [需要保留的元素]
```

**示例：**

> Change the daytime street scene into a cinematic cyberpunk night scene, add neon signs and wet road reflections, while preserving the original street layout, camera angle, and main building shapes.

#### 高信息密度图片建议

Agnes Image 2.1 Flash 针对复杂、细节丰富的视觉画面进行了优化。为了获得更好的结果，建议明确描述视觉层级。

推荐包含：

- 主体
- 背景环境
- 重要次要元素
- 风格和光照
- 构图约束
- 图生图时需要保留的内容

**较好示例：**

> A large fantasy harbor city built on cliffs, hundreds of small boats, layered stone bridges, glowing windows, distant mountains, cloudy sunset sky, cinematic fantasy realism, wide-angle composition, rich architectural details, high visual density

### 常见错误与排查

#### 1. response_format 放在顶层导致报错

不要将 response_format 放在请求体顶层。

错误示例：

```json
{
  "model": "agnes-image-2.1-flash",
  "prompt": "A futuristic city",
  "size": "1024x768",
  "response_format": "url"
}
```

正确示例：

```json
{
  "model": "agnes-image-2.1-flash",
  "prompt": "A futuristic city",
  "size": "1024x768",
  "extra_body": {
    "response_format": "url"
  }
}
```

#### 2. 图生图不需要 tags

不要传：

```json
{
  "tags": ["img2img"]
}
```

图生图只需要在 image 数组中提供输入图片。

正确示例：

```json
{
  "model": "agnes-image-2.1-flash",
  "prompt": "Make the object blue while preserving the original composition",
  "size": "1024x768",
  "extra_body": {
    "image": [
      "https://example.com/input.png"
    ],
    "response_format": "url"
  }
}
```

#### 3. 输入图片 URL 不可访问

如果输入图片 URL 无法被服务端访问，请求可能失败。

建议：

- 使用公网可访问的 HTTPS 图片地址
- 确保图片 URL 不需要登录、Cookie 或私有 Header
- 如果图片无法公开访问，建议使用 Data URI Base64 输入

#### 4. 请求超时

图片生成可能需要数秒到几十秒，具体取决于提示词复杂度、图片尺寸和服务负载。

建议客户端超时时间设置为：60s 到 360s

#### 5. 图生图请求缺少 image

图生图请求中，image 数组为必填。

错误示例：

```json
{
  "model": "agnes-image-2.1-flash",
  "prompt": "Make the image cyberpunk style",
  "size": "1024x768"
}
```

正确示例：

```json
{
  "model": "agnes-image-2.1-flash",
  "prompt": "Make the image cyberpunk style while preserving the original composition",
  "size": "1024x768",
  "extra_body": {
    "image": [
      "https://example.com/input.png"
    ],
    "response_format": "url"
  }
}
```

### 价格

| 类型 | 价格 |
|------|------|
| 生成图片 | $0.003 / 张 |

### 备注

- 模型名称固定使用 `agnes-image-2.1-flash`
- API Endpoint 使用 `https://apihub.agnes-ai.com/v1/images/generations`
- 文生图请求中，model、prompt、size 为必填
- 图生图请求中，请将输入图片 URL 或 Data URI Base64 放在顶层 image 数组中
- 需要图片 URL 输出时，使用 `extra_body.response_format: "url"`
- 文生图需要 Base64 输出时，使用 `return_base64: true`
- 图生图需要 Base64 输出时，使用 `extra_body.response_format: "b64_json"`
- 不要将 response_format 放在请求体顶层
- 不需要传 `tags: ["img2img"]`
- 公开文档中不要暴露临时 API Key，请使用 `YOUR_API_KEY`

---

## Agnes Video V2.0

> 原始页面：https://agnes-ai.com/doc/agnes-video-v20

### 一、模型概述

Agnes-Video-V2.0 是 Sapiens AI 开发的文生视频与图生视频模型。

它支持以下生成方式：

| 生成方式 | 说明 |
|---------|------|
| 文生视频 | 仅通过文本 Prompt 生成视频 |
| 图生视频 | 通过 1 张图片 + 文本 Prompt 生成视频 |
| 图生视频（首尾帧） | 通过 2 张首尾帧图片 + 文本 Prompt 生成视频 |

### 二、模型工作流

Agnes-Video-V2.0 采用任务式工作流，视频生成过程包含以下阶段：

1. **创建视频任务**：调用创建接口，传入提示词与图片，返回任务 ID
2. **查询视频状态**：通过任务 ID 轮询获取任务状态和结果
3. **获取视频结果**：任务完成后获取生成视频 URL 与封面图

### 三、适用场景

| 场景 | 示例 |
|------|------|
| 创意短视频 | 营销素材、短片预告、故事片段 |
| 内容生产辅助 | 为已有图片增加动态效果 |
| 产品展示视频 | 产品 360 度展示与使用场景动画 |
| 教学内容 | 实验过程、概念演示、步骤动画 |
| AI 故事视频 | 通过图片首尾帧构建故事片段 |
| 社交媒体素材 | 短视频平台发布用动态内容 |

### 四、API 基础信息

| 项目 | 说明 |
|------|------|
| Base URL | https://apihub.agnes-ai.com |
| 内容类型 | application/json |
| 认证方式 | Bearer Token |
| 认证 Header | Authorization: Bearer YOUR_API_KEY |

### 五、创建视频任务

#### 1. 请求信息

| 项目 | 内容 |
|------|------|
| 请求方法 | POST |
| Endpoint | https://apihub.agnes-ai.com/v1/videos/generations |
| 请求头 | Authorization: Bearer YOUR_API_KEY / Content-Type: application/json |

#### 2. 请求参数

| 参数 | 类型 | 是否必填 | 说明 |
|------|------|----------|------|
| model | string | 是 | 模型名称，固定为 `agnes-video-v2.0` |
| prompt | string | 是 | 描述视频内容的文本提示词 |
| image | string | 图生视频必填 | 起始帧图片 URL 或 Data URI Base64 |
| image_end | string | 否 | 结束帧图片 URL 或 Data URI Base64，用于首尾帧控制 |
| aspect_ratio | string | 否 | 视频宽高比，默认 16:9 |
| duration | number | 否 | 视频时长（秒） |
| fps | integer | 否 | 帧率 |
| seed | integer | 否 | 随机种子，用于复现结果 |
| extra_body | object | 否 | 扩展参数，用于传入图生视频所需的图片输入 |
| extra_body.image | string | 图生视频必填 | 起始帧图片 |
| extra_body.image_end | string | 否 | 结束帧图片 |

#### 3. 模型名称

**agnes-video-v2.0**

#### 4. 调用示例

##### 4.1 文生视频（仅文本）

```bash
curl https://apihub.agnes-ai.com/v1/videos/generations \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "agnes-video-v2.0",
    "prompt": "A cinematic wide shot of a futuristic coastal city at sunset, flying vehicles gliding between glowing towers, calm ocean reflecting the warm sky, gentle camera pan, high detail, smooth motion"
  }'
```

##### 4.2 图生视频（单张图片）

```bash
curl https://apihub.agnes-ai.com/v1/videos/generations \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "agnes-video-v2.0",
    "prompt": "The character walks forward confidently, cape fluttering in wind, background mountains moving slowly, dramatic lighting and dust particles, cinematic camera dolly in",
    "extra_body": {
      "image": "https://example.com/start-character.png"
    }
  }'
```

##### 4.3 图生视频（首尾帧）

```bash
curl https://apihub.agnes-ai.com/v1/videos/generations \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "agnes-video-v2.0",
    "prompt": "The character walks confidently from a fantasy mountainside to a glowing castle, cape flowing, mist drifting across the ground, cinematic camera following the subject",
    "extra_body": {
      "image": "https://example.com/start-character.png",
      "image_end": "https://example.com/end-character.png"
    }
  }'
```

##### 4.4 图生视频：Data URI Base64 输入

```bash
curl https://apihub.agnes-ai.com/v1/videos/generations \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "agnes-video-v2.0",
    "prompt": "A gentle breeze moves the fabric of the character cape, leaves and dust particles swirling around, soft natural daylight, subtle camera parallax",
    "extra_body": {
      "image": "data:image/png;base64,BASE64_HERE"
    }
  }'
```

##### 4.5 文生视频带高级参数

```bash
curl https://apihub.agnes-ai.com/v1/videos/generations \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "agnes-video-v2.0",
    "prompt": "A cinematic wide shot of a futuristic coastal city at sunset, flying vehicles gliding between glowing towers, calm ocean reflecting the warm sky, gentle camera pan, high detail, smooth motion",
    "aspect_ratio": "16:9",
    "duration": 6,
    "fps": 24,
    "seed": 42
  }'
```

#### 5. 创建任务响应格式

```json
{
  "created": 1780000000,
  "data": [
    {
      "id": "task_xxx",
      "prompt": "...",
      "status": "pending",
      "created_at": "2026-01-01T00:00:00Z",
      "updated_at": "2026-01-01T00:00:00Z"
    }
  ]
}
```

#### 6. 响应字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| created | integer | 请求创建时间戳 |
| data | array | 任务结果列表 |
| data[].id | string | 视频任务 ID |
| data[].prompt | string | 本次任务使用的文本提示词 |
| data[].status | string | 任务状态，例如 pending、processing、succeeded、failed |
| data[].created_at | string | 任务创建时间 |
| data[].updated_at | string | 任务更新时间 |

### 六、查询视频任务

#### 1. 请求信息

| 项目 | 内容 |
|------|------|
| 请求方法 | GET |
| Endpoint | https://apihub.agnes-ai.com/v1/videos/generations/{id} |
| 请求头 | Authorization: Bearer YOUR_API_KEY |
| URL 参数 | `{id}` 替换为创建任务返回的任务 ID |

#### 2. 调用示例

```bash
curl https://apihub.agnes-ai.com/v1/videos/generations/task_xxx \
  -H "Authorization: Bearer YOUR_API_KEY"
```

#### 3. 查询任务响应格式

```json
{
  "created": 1780000000,
  "data": [
    {
      "id": "task_xxx",
      "prompt": "...",
      "status": "succeeded",
      "url": "https://storage.googleapis.com/agnes-aigc/xxx.mp4",
      "cover_image_url": "https://storage.googleapis.com/agnes-aigc/xxx.png",
      "error": null,
      "created_at": "2026-01-01T00:00:00Z",
      "updated_at": "2026-01-01T00:00:30Z"
    }
  ]
}
```

#### 4. 查询响应字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| created | integer | 请求创建时间戳 |
| data | array | 任务结果列表 |
| data[].id | string | 视频任务 ID |
| data[].prompt | string | 文本提示词 |
| data[].status | string | 任务状态：pending / processing / succeeded / failed |
| data[].url | string / null | 生成视频 URL，任务成功后返回 |
| data[].cover_image_url | string / null | 封面图 URL |
| data[].error | object / null | 错误信息 |
| data[].created_at | string | 任务创建时间 |
| data[].updated_at | string | 任务更新时间 |

#### 5. 任务状态说明

| 状态 | 说明 |
|------|------|
| pending | 任务已创建，等待处理 |
| processing | 任务处理中 |
| succeeded | 任务成功，可获取视频 URL 和封面 URL |
| failed | 任务失败，可查看 error 字段 |

#### 6. 轮询建议

- 建议轮询间隔：5 秒
- 建议最大等待时间：600 秒
- 视频生成时间受模型负载、时长和提示词复杂度影响
- 客户端建议超时时间：600 秒

### 七、最佳实践

#### 1. Prompt 编写建议

为了获得更好的视频生成效果，建议使用以下结构组织 Prompt：

```
[画面主体] + [场景 / 环境] + [动作 / 运动] + [镜头语言] + [风格 / 光照] + [质量与细节]
```

**示例：**

> A cinematic wide shot of a futuristic coastal city at sunset, flying vehicles gliding between glowing towers, calm ocean reflecting the warm sky, gentle camera pan, high detail, smooth motion

#### 2. 图生图 Prompt 编写建议

对于图生视频任务，建议明确描述动作和镜头语言，以获得更好的运动和构图一致性。

**示例：**

> The character walks forward confidently, cape fluttering in wind, background mountains moving slowly, dramatic lighting and dust particles, cinematic camera dolly in, high motion detail

#### 3. 首尾帧控制建议

使用首尾帧时，建议：

- 两张图片的主体与构图保持一致
- 提示词中明确描述从起始帧到结束帧之间的动作或变化
- 主体、服装、颜色在首尾帧之间保持一致

**示例：**

> The character walks confidently from a fantasy mountainside to a glowing castle, cape flowing, mist drifting across the ground, cinematic camera following the subject

### 八、常见问题

#### 1. Agnes-Video-V2.0 是否支持文生视频？

支持。仅需要传入 model 和 prompt。

#### 2. Agnes-Video-V2.0 是否支持图生视频？

支持。可以通过一张图片，或两张首尾帧图片进行生成。

#### 3. 如何输入图片？

通过 extra_body.image 与 extra_body.image_end 传入：

- 支持公网图片 URL
- 支持 Data URI Base64

#### 4. 生成时间大约是多久？

视频生成时间取决于模型负载、提示词复杂度与视频时长。

一般建议将客户端超时设置为 600 秒。

#### 5. 任务失败了怎么办？

可以在查询接口返回结果中查看 error 字段，并根据错误信息调整提示词后重试。

### 九、价格

| 类型 | 价格 |
|------|------|
| 生成视频 | $0.45 / video |

---

## 隐私政策

> 原始页面：https://agnes-ai.com/doc/privacy-policy

### 一、概述

Sapiens AI, Inc.（以下简称"本公司"或"我们"）非常重视您的隐私。本隐私政策旨在帮助您了解我们如何收集、使用、存储、共享和保护您在使用产品、网站、应用程序、API、开发者服务和相关服务（以下合称"服务"）时提供或通过服务自动收集的信息。

使用 Agnes AI 服务前，请仔细阅读本隐私政策。如果您不同意本政策条款，请不要使用我们的服务。继续使用即表示您同意本政策描述的信息处理方式。

本政策适用于所有使用 Agnes AI 服务的用户，包括个人用户、开发者、企业客户、API 用户以及通过集成或插件间接使用服务的用户。

### 二、我们收集的信息

为提供并改进我们的服务，我们可能会在法律允许的范围内收集以下类型的信息：

| 信息类型 | 说明 | 是否必须 |
|---------|------|---------|
| 账户信息 | 用于创建账户、管理登录权限和计费 | 是 |
| 使用信息 | 帮助我们改进服务和排查问题 | 自动收集 |
| API 与服务内容 | 包括请求参数、提示词、生成的图片和视频 | 自动 |
| 设备与日志信息 | 用于安全检测和故障排查 | 自动收集 |
| Cookies 与类似技术 | 用于保持登录状态和提供个性化体验 | 部分可关闭 |
| 客户支持信息 | 您主动提供的沟通内容 | 可选 |

**账户信息包括：**

- 姓名或昵称
- 邮箱地址
- 登录凭据（密码哈希或第三方登录标识）
- 账户标识与 API Key

**使用信息包括：**

- 请求时间
- 使用的模型
- 消耗次数
- 计费信息

**API 与服务内容包括：**

- Prompt
- 输入图片
- 生成结果（文本、图片、视频）
- 其他请求参数

### 三、信息使用目的

我们收集的信息仅在必要范围内用于以下目的：

| 使用目的 | 说明 | 是否可关闭 |
|---------|------|-----------|
| 提供和维护服务 | 包括认证、计费、生成内容和返回结果 | 否 |
| 改进服务质量 | 包括理解用户需求和提升模型表现 | 是（可选择不参与） |
| 安全与合规 | 包括反滥用、防欺诈和遵守法律要求 | 否 |
| 客户支持 | 包括排查故障、回应反馈 | 是（取决于您是否联系我们） |
| 计费与交易 | 处理付款、开具发票 | 否（仅针对付费用户） |
| 功能与体验优化 | 个性化体验、产品运营分析 | 是 |
| 与您沟通 | 包括功能更新、重要通知和营销内容 | 是 |

### 四、信息共享与披露

我们不会将您的个人信息出售给任何第三方。

仅在以下场景下，我们可能与第三方共享您的信息：

| 场景 | 说明 |
|------|------|
| 服务提供商 | 与云服务、支付、分析等基础设施提供商共享必要信息 |
| 法律要求 | 在满足法律程序、法院命令或政府要求时 |
| 业务转让 | 合并、收购、资产出售等交易中，在信息保密的前提下转移 |
| 保护权利 | 为保护本公司、用户或公众的合法权益 |
| 您的同意 | 在您明确同意的情况下 |

**特别说明：**

- 默认情况下，我们不会将您的 API 请求内容用于训练公开分享的模型
- 您在公共界面、社区或开放评测中提交的内容，可能被用于公开示例、演示或模型改进
- 若您不希望请求内容被用于模型改进，可以通过控制参数、隐私选项或联系客服进行设置

### 五、信息存储与保留期限

我们按照以下原则存储您的信息：

- 存储位置：主要存储于美国及符合同等数据保护标准的地区
- 存储期限：仅保留到实现使用目的所需的最短期限
- 日志与安全记录：通常保留 6 个月到 2 年
- 账单与税务记录：通常保留 3 到 7 年，具体取决于法律要求
- 账户数据：在账户存续期间保留，并在注销后合理期限内删除或匿名化
- 生成内容：默认在一定期限内保留以便您访问，可通过设置或 API 控制提前删除

### 六、信息安全

我们采取以下技术与管理措施保护您的信息安全：

| 措施 | 说明 |
|------|------|
| 访问控制 | 严格控制内部员工对您数据的访问权限 |
| 加密传输 | 使用 HTTPS 等加密协议传输信息 |
| 加密存储 | 对敏感信息进行加密存储 |
| 最小化原则 | 仅收集实现功能所需的最少信息 |
| 审计与监控 | 记录和监控关键系统访问行为 |
| 安全测试 | 定期进行安全评估、渗透测试与漏洞修复 |

尽管我们采取了合理措施保护您的信息，互联网传输和存储并非绝对安全，我们无法保证绝对安全。

### 七、您的权利

您对个人信息享有以下权利：

- 查询与访问权
- 更正与更新权
- 删除权
- 限制与反对处理权
- 数据可携带权
- 撤回同意权
- 投诉权

如需行使以上权利，可以通过以下方式联系我们：

- 控制台自助管理
- 发送邮件至 privacy@sapiens-ai.com

我们将在法律规定的时间内回应您的请求。

### 八、Cookie 与类似技术

为确保服务正常运行并优化用户体验，我们可能使用 Cookie、Local Storage、Web Storage 以及类似技术。

您可以通过浏览器设置控制或禁用部分 Cookie。禁用后，部分功能可能无法正常使用。

### 九、国际数据传输

我们可能将您的信息传输到您所在司法管辖区以外的地区进行处理。在进行此类传输时，我们会确保遵守适用的法律要求，并采取充分的保障措施。

### 十、未成年人保护

我们的服务面向年满 18 岁或以上的用户，或在具有相应行为能力的年龄段使用。

如果您未满法定成年年龄，请在法定监护人同意和监督下使用本服务。

如发现我们在不知情的情况下收集了未成年人的个人信息，我们会尽快采取合理措施予以删除。

### 十一、第三方内容与链接

服务中可能包含第三方提供的内容、链接、插件或集成。当您访问或使用第三方服务时，适用第三方自身的隐私政策与条款。本公司不对第三方信息处理方式承担责任。

### 十二、政策更新

我们可能根据法律要求或产品变更，不时更新本隐私政策。更新后我们会在相关页面上公布最新版本并注明生效日期。

重大变更时，我们会通过显眼的方式通知您。

**本政策最近更新时间：** 2026 年 6 月 11 日

### 十三、联系我们

如对本隐私政策、信息处理或您的权利有任何疑问，欢迎通过以下方式联系我们：

- Email：privacy@sapiens-ai.com
- Agnes AI 官网：https://agnes-ai.com

---

## 服务条款

> 原始页面：https://agnes-ai.com/doc/terms-of-service

### 一、概述

欢迎使用 Agnes AI（以下简称"本服务"）。本服务由 Sapiens AI, Inc.（以下简称"本公司"或"我们"）提供。

在使用本服务前，请您仔细阅读并理解本《服务条款》（以下简称"本条款"）。一旦您开始使用本服务，即表示您理解并同意本条款的全部内容。

本条款适用于所有通过网页、API、集成、插件、开发者工具或其他方式使用 Agnes AI 服务的用户，包括个人用户、开发者和企业客户。

如果您代表公司或其他组织使用本服务，则您声明并保证您有权代表该组织接受本条款。

### 二、服务范围

本服务包括但不限于：

| 服务项目 | 说明 |
|---------|------|
| AI 文本生成 | 基于大语言模型的对话、补全、推理与工具调用 |
| AI 图像生成与编辑 | 文生图、图生图与多图合成 |
| AI 视频生成 | 文生视频、图生视频与首尾帧生成视频 |
| API 服务 | 用于开发者集成的编程接口 |
| Web 控制台 | 用户可通过网页界面创建任务、管理账户与使用模型 |
| 开发者工具 | SDK、文档、示例代码与集成指南 |
| 相关功能 | 计费、认证、用量管理、客户支持与相关增值功能 |

本公司保留在合理范围内调整服务内容、发布新版本、变更模型名称或调整能力参数的权利。

### 三、账户与使用规范

#### 1. 账户注册

您需要创建账户并获得相应凭据后方可使用部分功能。

账户信息包括：

- 基本注册信息
- 登录凭据
- API Key

请您妥善保管 API Key 和账户密码，并对在您账户下发生的所有使用行为负责。

**账户使用要求：**

- 不得使用虚假信息注册账户
- 不得将账户或 API Key 出售、转让、共享给第三方违规使用
- 不得从事任何损害服务稳定性或其他用户体验的行为
- 如发现账户异常或凭据泄露，请立即停止使用并采取安全措施

#### 2. 可接受使用政策

您在使用本服务时，不得违反以下要求：

- 违反适用法律法规
- 传播有害、非法、欺诈、骚扰、歧视或侵权内容
- 未经授权访问他人系统或数据
- 生成深度伪造或可能对他人造成伤害的内容
- 冒充他人或使用虚假身份
- 破坏服务安全、反滥用机制或稳定性
- 未经许可进行大规模自动化抓取、攻击或流量刷取
- 以未经授权的方式绕过限流、计费或安全机制
- 违反本条款、附属政策或任何适用的社区规范

我们有权在发现违规行为时，暂停、限制或终止相关账户或服务访问权限，并保留追究法律责任的权利。

### 四、知识产权

#### 1. 我们的知识产权

除另有约定外，本服务中提供的所有内容、商标、Logo、文本、图像、代码、文档、API 设计以及相关技术成果，均归本公司及其关联方所有。

未经本公司书面许可，您不得以任何形式进行复制、修改、再分发、反向工程或用于商业目的。

#### 2. 您提供的内容

您在使用本服务时提供的输入内容（包括 Prompt、图片和其他请求内容）的知识产权仍归您所有或由您依法持有。

您声明并保证：

- 您已合法取得相关内容的使用权
- 您的使用不会侵犯任何第三方的合法权益
- 您授权本公司在必要范围内使用这些内容以提供和维护服务

#### 3. 生成内容的归属

在您遵守本条款和适用法律的前提下，对于您通过本服务生成的结果（文本、图片、视频等）：

- 您享有使用、复制、修改、分发和进行商业使用的权利
- 您对使用生成内容的后果独立承担责任
- 您不得以违反本条款或适用法律的方式使用生成内容
- 我们不对第三方因您使用生成内容而遭受的损失承担责任

### 五、费用与计费

#### 1. 付费服务

本服务中部分功能可能需要付费使用。相关费用标准以当时有效的价格页面或书面约定为准。

付费服务的计费方式包括：

- 按生成次数计费
- 按 token 或图像 / 视频生成量计费
- 订阅或套餐方式计费
- 其他约定的计费方式

#### 2. 支付与退款

- 除非另有约定，费用通过第三方支付渠道处理
- 支付相关的税费与第三方手续费由用户承担
- 除另有明确规定或法律要求外，已支付费用通常不予退款
- 如因服务故障导致您的任务失败或未成功生成内容，我们会根据情况进行补偿或免单

#### 3. 价格与能力调整

我们可能根据业务情况调整价格、模型能力、模型名称或功能范围，并在合理期限内通知您。

### 六、免责声明与风险提示

#### 1. "按现状"提供

本服务按"现状"和"可用状态"提供。在法律允许的最大范围内：

- 我们不对服务的连续性、可用性或结果准确性作出明示或暗示的保证
- 生成结果的完整性、准确性、安全性或适用性由您独立判断并承担风险
- 我们不对间接损失、利润损失、数据损失或业务中断承担责任

#### 2. 生成内容风险

AI 模型生成的结果可能存在以下问题：

- 不完全准确或存在错误
- 与事实不符或产生幻觉
- 输出不稳定
- 因随机 seed 不同而产生差异
- 对相同输入产生不同输出

因此，生成内容仅供参考，不得直接作为医学、法律、财务或专业建议使用。

#### 3. 安全与合规风险

您使用本服务的行为和您发布的内容需遵守所有适用法律。

以下行为或内容是禁止的：

- 违反法律法规、公共秩序或道德规范
- 侵犯他人权利，包括知识产权、隐私权和肖像权
- 生成涉及歧视、仇恨、暴力、色情或其他有害内容
- 可能对未成年人造成伤害或引发危险的用途

### 七、免责声明的适用范围

本免责声明在法律允许的最大范围内适用。

如本条款中任何部分被认定为无效或不可执行，该部分应视为可分割，不影响其他条款的效力。

### 八、责任限制

在法律允许的最大范围内：

- 本公司的总赔偿责任以您在过去 12 个月内为本服务支付的费用总额为上限
- 本公司不对间接损失、附带损失、后果性损失、利润损失或数据损失承担责任
- 本公司不对第三方提供的服务、链接或内容承担责任

### 九、终止与暂停

#### 1. 用户终止

您可以通过主动停止使用本服务或在控制台注销账户的方式终止使用。

#### 2. 服务暂停或终止

在发生以下情形时，我们有权在合理范围内暂停或终止您对本服务的全部或部分访问权限：

- 违反本条款或附属政策
- 未按时支付相关费用
- 涉嫌违法、违规或损害他方利益
- 接到法律或监管机构的要求

在可行情况下，我们会提前通知您并为您保留合理时间以导出数据。

### 十、适用法律与争议解决

- 本条款的签订、履行、解释和争议解决适用美国法律
- 与本条款相关的争议，各方应首先尝试友好协商解决
- 协商不成的，任一方可向本公司主要注册所在地具有管辖权的法院提起诉讼

### 十一、条款更新

我们可能根据业务发展、法律变化或产品调整，不时更新本条款。

- 更新后的条款将在官网或相关页面公布，并注明最新更新日期
- 重大变更时，我们会通过显眼的方式进行通知
- 更新后继续使用本服务，视为您同意新的条款内容

**本条款最近更新时间：** 2026 年 6 月 11 日

### 十二、联系方式

如对本条款或本服务有任何疑问、意见或举报，欢迎通过以下方式联系我们：

- Email：support@sapiens-ai.com
- Agnes AI 官网：https://agnes-ai.com

---
