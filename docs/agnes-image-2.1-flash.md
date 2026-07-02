# Agnes Image 2.1 Flash

## 模型概述

Agnes Image 2.1 Flash 是 Sapiens AI 升级推出的图像生成模型，支持文生图和图生图两种工作流。
相比之前版本，Agnes Image 2.1 Flash 在高信息密度图像生成方面进行了优化，更适合复杂视觉细节、丰富构图、密集元素和清晰语义对齐等场景。

Agnes Image 2.1 Flash 可用于根据文本提示词生成图像，也可基于已有图片进行风格转换、局部优化、场景重塑或视觉增强，并支持以图片 URL 或 Base64 数据形式返回生成结果。

## 核心能力

| 能力 | 说明 |
|------|------|
| 文生图 | 根据自然语言提示词生成高质量图片 |
| 图生图 | 根据提示词对已有图片进行转换、编辑或优化 |
| 高信息密度图像优化 | 更好处理复杂布局、丰富细节和密集视觉元素 |
| 构图保持 | 图生图时可尽量保持原图构图、主体结构和视角 |
| 灵活尺寸控制 | 支持自定义输出尺寸，例如 1024x768 |
| URL 返回 | 支持将生成结果以可访问图片 URL 返回 |
| Base64 返回 | 支持将生成结果以 Base64 数据返回 |
| URL 或 Data URI 输入 | 图生图支持公网图片 URL 或 Data URI Base64 输入 |

## 适用场景

Agnes Image 2.1 Flash 适用于以下场景：

| 场景 | 示例用途 |
|------|----------|
| 创意设计 | 概念图、视觉探索、海报草图 |
| 营销内容 | 活动图、产品视觉、社交媒体素材 |
| 高密度视觉生成 | 复杂场景、丰富构图、密集元素画面 |
| 图片转换 | 风格迁移、场景重打光、背景转换 |
| 内容生产 | App 素材、缩略图、Banner、叙事视觉 |
| 产品视觉 | 产品图、展示图、商业视觉 |
| 社交媒体素材 | 封面图、横幅图、帖子配图 |

## API 信息

### Base URL
`https://apihub.agnes-ai.com`

### 接口地址

| 项目 | 说明 |
|------|------|
| API Endpoint | `https://apihub.agnes-ai.com/v1/images/generations` |
| 请求方法 | POST |
| Content-Type | application/json |
| 认证方式 | Bearer Token |
| 认证 Header | `Authorization: Bearer YOUR_API_KEY` |

### 模型名称

文生图和图生图均使用以下模型名称：
`agnes-image-2.1-flash`

### 重要说明

- 请使用 `agnes-image-2.1-flash` 作为模型名称。
- 文生图请求中，`model`、`prompt`、`size` 为必填参数。
- 图生图请求中，请将输入图片放在顶层 `image` 数组中。
- `image` 支持公网图片 URL，也支持 Data URI Base64。
- **不要将 `response_format` 放在请求体顶层**，否则可能返回 400 错误。
- 如需 URL 输出，请将 `"response_format": "url"` 放在 `extra_body` 中。
- 如需文生图 Base64 输出，可使用顶层参数 `"return_base64": true`。
- 如需图生图 Base64 输出，请在 `extra_body` 中设置 `"response_format": "b64_json"`。
- 图生图不需要传 `tags: ["img2img"]`。
- 公开文档中不要暴露临时 API Key，请统一使用 `YOUR_API_KEY`。

## 请求参数

| 参数 | 类型 | 是否必填 | 说明 |
|------|------|----------|------|
| `model` | string | 是 | 模型名称，固定使用 `agnes-image-2.1-flash` |
| `prompt` | string | 是 | 图片生成或图片编辑提示词 |
| `size` | string | 是 | 输出图片尺寸，例如 `1024x768` |
| `image` | string[] | 图生图必填 | 输入图片数组，支持公网 URL 或 Data URI Base64 |
| `return_base64` | boolean | 否 | 文生图需要返回 Base64 时使用 |
| `extra_body` | object | 否 | 高级工作流扩展参数 |
| `extra_body.response_format` | string | 否 | 输出格式，常用值为 `url` 或 `b64_json` |

## 调用示例

### 1. 文生图：URL 输出

用于根据文本提示词生成图片，并以图片 URL 形式返回结果。

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

### 2. 文生图：Base64 输出

用于将生成图片以 Base64 数据形式返回。

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

### 3. 图生图：URL 输入，URL 输出

用于基于已有图片进行转换，并尽量保持原图构图。

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

### 4. 图生图：URL 输入，Base64 输出

用于输入图片为公网 URL，输出结果为 Base64 数据的场景。

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

### 5. 图生图：Data URI Base64 输入

图生图也支持使用 Data URI Base64 作为输入图片。

Data URI 格式：
`data:image/png;base64,BASE64_HERE`

请求示例：
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

## 返回格式

### URL 输出

当 `extra_body.response_format` 设置为 `url` 时，返回格式如下：

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

### Base64 输出

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

## 推荐提示词结构

为了获得更好的图像生成效果，建议使用清晰的提示词结构：

`[主体] + [场景 / 环境] + [风格] + [光照] + [构图] + [质量要求]`

示例：
```
A luminous floating city above a misty canyon at sunrise, cinematic realism, wide-angle composition, rich architectural details, soft golden light, high visual density
```

对于图生图任务，需要明确说明"要改变什么"和"要保留什么"。

```
Transform the scene into a rain-soaked cyberpunk night with neon reflections while preserving the original composition and main subject layout.
```

## 最佳实践

### 文生图建议

生成复杂图片时，建议使用更具体的提示词，包含主体、环境、风格、光照、镜头角度和细节要求。

较好示例：
```
A futuristic city marketplace filled with flying vehicles, holographic signs, dense crowds, neon lighting, cinematic realism, ultra-detailed, high-information-density composition
```

推荐包含以下元素：
- 主体
- 场景或环境
- 视觉风格
- 光照
- 镜头角度
- 构图
- 细节密度
- 质量要求

### 图生图建议

编辑已有图片时，建议同时说明转换要求和保留要求。

较好示例：
```
Convert the image into a fantasy winter landscape, add snow, warm window lights, and a magical atmosphere, while preserving the original building structure and camera angle.
```

推荐结构：
`[修改要求] + [新风格 / 新场景] + [需要添加或移除的元素] + [需要保留的元素]`

示例：
```
Change the daytime street scene into a cinematic cyberpunk night scene, add neon signs and wet road reflections, while preserving the original street layout, camera angle, and main building shapes.
```

### 高信息密度图片建议

Agnes Image 2.1 Flash 针对复杂、细节丰富的视觉画面进行了优化。为了获得更好的结果，建议明确描述视觉层级。

推荐包含：
- 主体
- 背景环境
- 重要次要元素
- 风格和光照
- 构图约束
- 图生图时需要保留的内容

较好示例：
```
A large fantasy harbor city built on cliffs, hundreds of small boats, layered stone bridges, glowing windows, distant mountains, cloudy sunset sky, cinematic fantasy realism, wide-angle composition, rich architectural details, high visual density
```

## 常见错误与排查

### 1. response_format 放在顶层导致报错

不要将 `response_format` 放在请求体顶层。

**错误示例：**
```json
{
  "model": "agnes-image-2.1-flash",
  "prompt": "A futuristic city",
  "size": "1024x768",
  "response_format": "url"
}
```

**正确示例：**
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

### 2. 图生图不需要 tags

不要传：
```json
{
  "tags": ["img2img"]
}
```

图生图只需要在 `image` 数组中提供输入图片。

**正确示例：**
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

### 3. 输入图片 URL 不可访问

如果输入图片 URL 无法被服务端访问，请求可能失败。

建议：
- 使用公网可访问的 HTTPS 图片地址。
- 确保图片 URL 不需要登录、Cookie 或私有 Header。
- 如果图片无法公开访问，建议使用 Data URI Base64 输入。

### 4. 请求超时

图片生成可能需要数秒到几十秒，具体取决于提示词复杂度、图片尺寸和服务负载。

建议客户端超时时间设置为：**60s 到 360s**

### 5. 图生图请求缺少 image

图生图请求中，`image` 数组为必填。

**错误示例：**
```json
{
  "model": "agnes-image-2.1-flash",
  "prompt": "Make the image cyberpunk style",
  "size": "1024x768"
}
```

**正确示例：**
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

## 价格

| 类型 | 价格 |
|------|------|
| 生成图片 | 0 ~ $0.003 / 张 |

## 备注

- 模型名称固定使用 `agnes-image-2.1-flash`。
- API Endpoint 使用 `https://apihub.agnes-ai.com/v1/images/generations`。
- 文生图请求中，`model`、`prompt`、`size` 为必填。
- 图生图请求中，请将输入图片 URL 或 Data URI Base64 放在顶层 `image` 数组中。
- 需要图片 URL 输出时，使用 `extra_body.response_format: "url"`。
- 文生图需要 Base64 输出时，使用 `return_base64: true`。
- 图生图需要 Base64 输出时，使用 `extra_body.response_format: "b64_json"`。
- **不要将 `response_format` 放在请求体顶层**。
- 不需要传 `tags: ["img2img"]`。
- 公开文档中不要暴露临时 API Key，请使用 `YOUR_API_KEY`。
