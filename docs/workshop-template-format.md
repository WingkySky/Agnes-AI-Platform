# 创意工坊模板导入格式

本文档说明创意工坊模板导入文件（`.json`）的结构。**获取示例文件**：在工坊导入对话框点"下载示例模板"，或调用 `GET /api/pipeline/templates/sample`。

## 顶层结构

```json
{
  "version": "1.0",
  "exported_at": "2026-06-28T12:00:00Z",
  "templates": [ /* 模板数组，见下 */ ],
  "script_templates": [ /* 关联剧本模板，可选 */ ],
  "style_presets": [ /* 关联风格预设，可选 */ ]
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `version` | string | 格式版本，当前固定 `"1.0"`。旧文件无此字段按 1.0 处理。 |
| `exported_at` | string | 导出时间（ISO 8601）。导入时忽略。 |
| `templates` | array | **必填**。模板数组，至少 1 个。 |
| `script_templates` | array | 可选。关联的剧本模板，按 key 唯一去重。 |
| `style_presets` | array | 可选。关联的风格预设，按 key 唯一去重。 |

## `templates[]` 字段

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `key` | string | 是 | 模板唯一标识。冲突时按 `conflict_strategy` 处理。 |
| `name` | string | 是 | 显示名称。 |
| `description` | string | 否 | 详细描述。 |
| `category` | string | 是 | 分类：`drama` / `ad` / `education` / `art`。 |
| `thumbnail_url` | string | 否 | 缩略图 URL。 |
| `inputs_config` | array | 否 | 用户输入参数定义，见下。 |
| `steps_config` | array | 是 | 步骤定义（有序），见下。 |
| `output_mapping` | object \| null | 否 | 最终产物映射。为 null 时后端自动推断（取最后一个 `ffmpeg_composite` 或 `video_batch` 的输出）。 |
| `script_template_id` | number | 否 | 关联剧本模板 ID（导入时通过 `script_template_key` 重建引用）。 |
| `script_template_key` | string | 否 | 关联剧本模板的 key（导入侧据此重映射 ID）。 |
| `estimated_credits` | number | 否 | 预估积分。为空时后端按 `steps_config` 自动计算。 |
| `estimated_time_minutes` | number | 否 | 预估耗时（分钟）。 |
| `tags` | array | 否 | 标签数组。 |
| `is_public` | boolean | 否 | 是否公开。导入时由 `import_mode` 覆盖。 |

## `inputs_config[]` 字段

定义用户运行模板时需要填的输入参数。

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `key` | string | 是 | 变量名，用于在步骤提示词模板里用 `{{key}}` 引用。 |
| `label` | string | 是 | 显示名。 |
| `type` | string | 是 | 输入类型：`text` / `number` / `style_select` / `boolean`。 |
| `required` | boolean | 否 | 是否必填，默认 false。 |
| `default` | any | 否 | 默认值。 |
| `description` | string | 否 | 字段说明。 |
| `min` / `max` | number | 否 | number 类型的范围。 |

示例：

```json
"inputs_config": [
  { "key": "theme", "label": "主题", "type": "text", "required": true, "default": "" },
  { "key": "count", "label": "分镜数", "type": "number", "default": 8, "min": 1, "max": 32 }
]
```

## `steps_config[]` 字段

定义流水线的执行步骤。**有序**，按数组顺序执行（依赖关系由 `depends_on` 显式声明）。

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `key` | string | 是 | 步骤唯一标识（同模板内唯一）。用于 `depends_on` 和 `from_step` 引用。 |
| `name` | string | 是 | 步骤显示名。 |
| `type` | string | 是 | **步骤类型，必须命中下表权威清单**。 |
| `depends_on` | array | 否 | 依赖的步骤 key 数组。被依赖的步骤必须先完成。 |
| `config` | object | 是 | 步骤配置，字段因 `type` 而异（见下）。 |
| `max_retries` | number | 否 | 最大重试次数，默认 2。 |
| `timeout` | number | 否 | 超时秒数，默认 300。 |

### `type` 权威清单

`type` 必须是以下 5 种之一（后端注册表权威清单，来源 `backend/app/services/pipeline/steps/__init__.py`）：

| type | 用途 | config 必需字段 | config 可选字段 |
|------|------|----------------|-----------------|
| `llm_generate` | LLM 文本生成（剧本、角色、字幕等） | `prompt`（含 `{{var}}` 占位符） | `model`、`temperature`、`max_tokens`、`output_format` |
| `image_batch` | 批量生图 | `prompt_field`（从上游 JSON 取哪个字段）或 `prompt` 字面量 | `from_step`、`model`、`size`、`batch_size` |
| `video_batch` | 批量生视频 | `from_step`（上游 image_batch 的 key） | `model`、`seconds`、`aspect_ratio` |
| `tts_generate` | 文本转语音 | `from_step`（上游 llm_generate 的 key） | `voice`、`speed`、`provider` |
| `ffmpeg_composite` | 视频拼接合成 | `from_step`（上游 video_batch 的 key） | `with_subtitle`、`audio_from_step`、`subtitle_from_step` |

> ⚠️ **常见错误**：旧文档/代码里出现的 `image_gen` / `video_gen` / `audio_gen` / `composite` 都不是有效的 step_type，导入时会被校验拒绝。

### `depends_on` 与 `from_step` 的区别

- `depends_on`：**步骤依赖关系**。声明哪些步骤必须先完成。是 DAG（有向无环图）的边。
- `from_step`：**数据来源引用**。声明从哪个步骤的输出取数据作为本步骤的输入。是 config 内的字段。

两者经常同时存在：`from_step` 引用的 step.key 必须出现在 `depends_on` 中（否则执行器取不到上游输出）。导入校验会检查这一点。

## 最小示例

一份可直接导入的标准漫剧模板（4 步流程）：

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

## 导入校验规则

导入时后端会对每个模板做无副作用校验（不落库）：

1. 每个 `step.type` 必须在权威清单内，否则该模板标记为校验失败。
2. 每个 `step.key` 必须非空且在同模板内唯一。
3. `depends_on` 引用的 key 必须存在于同模板的 steps 内。
4. `from_step` / `audio_from_step` / `subtitle_from_step` 同样校验存在性。

校验失败的模板不会写入数据库，错误明细在导入响应的 `errors` 字段返回：

```json
{
  "imported": 1,
  "errors": [
    {
      "template_key": "bad_template",
      "template_name": "错误模板",
      "reasons": ["[type] 未知步骤类型 'image_gen'，请参考 docs/workshop-template-format.md"]
    }
  ]
}
```

## 相关接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/pipeline/templates/sample` | GET | 下载示例模板 JSON |
| `/api/pipeline/templates/validate` | POST | 无副作用校验模板结构 |
| `/api/pipeline/templates/import` | POST | 批量导入模板 |
| `/api/pipeline/export/templates` | GET | 导出模板为 JSON |
