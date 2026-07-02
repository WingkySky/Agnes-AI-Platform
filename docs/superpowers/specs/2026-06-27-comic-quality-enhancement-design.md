# 漫剧生成质量增强 — 设计文档

> 版本：v1.0
> 日期：2026-06-27
> 状态：设计中
> 关联文档：
> - [01-creative-pipeline-overview.md](../../01-creative-pipeline-overview.md)
> - [agnes-image-2.1-flash.md](../../agnes-image-2.1-flash.md)
> - [agnes-video-v2.0.md](../../agnes-video-v2.0.md)

---

## 1. 背景

漫剧生成存在三个影响产出质量的关键问题：

### 1.1 负面提示词完全失效（最严重）

**根因链**：
1. [style_service.py:189](../../../backend/app/services/style_service.py#L189) `build_prompt_with_style` 返回 `(positive, negative)` 元组
2. [image_batch.py:257-259](../../../backend/app/services/pipeline/steps/image_batch.py#L257) 调用时只接收 `prompt = build_prompt_with_style(...)`，**negative 被丢弃**
3. [video_batch.py:340-342](../../../backend/app/services/pipeline/steps/video_batch.py#L340) 同样问题
4. 即使接收了 negative，[agnes_client.py:481 create_image](../../../backend/app/services/agnes_client.py#L481) 也没有 negative_prompt 参数
5. `create_video_task` 支持 negative_prompt，但 video_batch 调用时也没传

**结果**：8 个内置风格预设配置的 negative_prompt 全部浪费，画面出现 photorealistic、3d render、western comic 等不想要的风格。

### 1.2 画面风格不稳定

**根因**：
- LLM 生成的 image_prompt 没有强制带上风格关键词
- 同一次运行的不同分镜画面风格随机漂移
- 缺少全局风格种子

### 1.3 人物一致性差（用户感知最强）

**根因**：
- character_images（角色图）和 scene_images（场景图）完全独立生成
- scene_images 不会参考 character_images 的角色图作为参考图
- 即使想参考，image_batch 没有把角色图作为 reference image 传入

---

## 2. Agnes 模型能力边界（基于官方文档）

### 2.1 Agnes Image 2.1 Flash

**支持**：
- 文生图（model/prompt/size）
- 图生图（extra_body.image 数组，支持多图参考）
- URL / Base64 输出

**不支持**：
- ❌ negative_prompt 参数（官方文档参数表无此字段，extra_body 也只用于 image/response_format/mask）
- ❌ seed 参数
- ❌ 任何其他控制参数

**结论**：图片的"负面提示词"只能以自然语言拼接到 prompt 中（如 `"avoid: photorealistic, 3d render"`）。

### 2.2 Agnes Video V2.0

**支持**：
- negative_prompt 参数（顶层）
- seed 参数
- 单图 image2video（顶层 image 字段）
- 多图参考 / 关键帧模式（extra_body.image 数组）
- width/height/num_frames/frame_rate

**结论**：视频的负面提示词可正常用 API 参数传递。

---

## 3. 目标

基于 Agnes 模型实际能力，解决三个问题：

1. **负面提示词生效**：
   - 图片：拼接到 prompt 中（自然语言描述避免内容）
   - 视频：用 API 原生 negative_prompt 参数

2. **画面风格稳定**：
   - LLM 提示词增强，强制在 image_prompt 中带上风格关键词
   - 风格预设的 visual_prefix 强制前置到每个图片 prompt

3. **人物一致性**：
   - scene_images 步骤把对应角色图作为 reference image 传给 Agnes Image API
   - LLM 在 scenes 中标注每个场景出现哪些角色（characters_in_scene 字段）

**不做**：
- 自定义模型参数调优（Agnes API 不支持）
- 多模型对比/切换（保持用 model_registry 机制）
- 手动绘制角色参考（保持全自动流程）

---

## 4. 架构设计

### 4.1 整体数据流

```
[LLM 剧本生成]
  ├─ characters: [{name, description, image_prompt, ...}]
  └─ scenes: [{scene_num, description, image_prompt, video_prompt,
              characters_in_scene: ["角色名1", "角色名2"], ...}]   ← 新增字段

[character_images 步骤]（文生图，带风格+负面拼接到 prompt）
  └─ images: [{index, image_url, scene_data: {name, ...}}, ...]

[scene_images 步骤]（图生图，带角色参考图 + 风格 + 负面）
  ├─ 从 character_images 步骤获取角色图 URL 映射 {角色名: image_url}
  ├─ 对每个 scene：
  │   ├─ 根据 characters_in_scene 找到对应角色图
  │   ├─ 调 create_image(image_urls=[角色图1, 角色图2], prompt=风格+场景描述+负面)
  │   └─ 生成保持角色一致性的场景图
  └─ images: [{index, image_url, scene_data, reference_images: [...]}, ...]

[scene_videos 步骤]（image2video，带 negative_prompt 参数）
  └─ 对每个 scene：调 create_video_task(image=scene_image, prompt=..., negative_prompt=风格负面)
```

### 4.2 负面提示词拼接策略（图片）

由于 Agnes Image API 不支持 negative_prompt 参数，采用自然语言拼接：

```
[原 prompt], [风格 visual_prefix], [风格 lighting/color/mood/quality], avoid: [风格 negative_prompt]
```

示例：
```
A girl standing in a rainy street, manga style, japanese comic book art, clean lineart,
dramatic lighting, high contrast black and white, masterpiece, best quality, highly detailed,
avoid: color, photorealistic, 3d render, anime, western comic
```

**为什么不直接用 negative 关键词**：Agnes Image API 是自然语言理解模型，"avoid: xxx" 这种自然语言描述比裸关键词更有效（参考官方提示词最佳实践：`[修改要求] + [需要添加或移除的元素]`）。

### 4.3 负面提示词传递策略（视频）

视频 API 原生支持 negative_prompt，直接作为顶层参数传递：

```python
result = await agnes_client.create_video_task(
    prompt=positive_prompt,
    negative_prompt=negative_prompt,  # 风格预设的 negative_prompt
    ...
)
```

### 4.4 角色参考图映射

**LLM schema 改动**：scenes 数组的每个 scene 新增 `characters_in_scene` 字段：

```json
{
  "scene_num": 1,
  "description": "小猫在雨中迷路",
  "image_prompt": "...",
  "video_prompt": "...",
  "characters_in_scene": ["小猫", "老猫"],  // 新增：本场景出现的角色名
  "dialogue": "...",
  "duration": 5
}
```

**scene_images 步骤逻辑**：
1. 从 `character_images` 步骤输出构建 `{角色名: image_url}` 映射
2. 对每个 scene：
   - 读取 `scene_data.characters_in_scene`
   - 从映射中找到对应角色图 URL
   - 调 `create_image(image_urls=[角色图URLs], prompt=增强prompt)` 进入图生图模式
3. 如果某个 scene 没有 characters_in_scene 或角色图缺失，回退到纯文生图

### 4.5 风格 prompt 增强策略

**LLM 提示词增强**（修改剧本模板）：
- 在 image_prompt 生成要求中明确：每个 image_prompt 必须以风格关键词开头
- 风格关键词从 style_preset.visual_prefix 获取，通过模板变量传给 LLM

**image_batch 强制前置风格**：
- 即使 LLM 没带风格关键词，image_batch 在调 API 前强制把 `style.visual_prefix` 前置到 prompt
- 保证风格一致性不依赖 LLM 的自觉性

### 4.6 模块职责

#### 后端

| 文件 | 改动 |
|------|------|
| [style_service.py](../../../backend/app/services/style_service.py) | 新增 `build_negative_prompt_suffix(style)` 函数，把 negative_prompt 包装为 "avoid: xxx" 后缀 |
| [image_batch.py](../../../backend/app/services/pipeline/steps/image_batch.py) | ① 接收 `(positive, negative)` 元组；② 新增角色参考图传递逻辑（从上游 character_images 步骤获取）；③ 调 create_image 时传 image_urls；④ prompt 末尾拼 "avoid: negative" |
| [video_batch.py](../../../backend/app/services/pipeline/steps/video_batch.py) | ① 接收 `(positive, negative)` 元组；② 调 create_video_task 时传 negative_prompt 参数 |
| [agnes_client.py](../../../backend/app/services/agnes_client.py) | 无改动（create_image 已支持 image_urls，create_video_task 已支持 negative_prompt） |
| [seed_pipeline_data.py](../../../backend/seed_pipeline_data.py) | ① 剧本模板 prompt 增加 characters_in_scene 字段要求；② 剧本模板 output_schema 加 characters_in_scene；③ scene_images 步骤配置加 reference_from_step: "character_images" |

#### 前端

无需改动。角色图映射、参考图传递都是后端步骤执行器内部逻辑，前端只展示最终结果。

---

## 5. 详细设计

### 5.1 style_service 新增 build_negative_prompt_suffix

```python
def build_negative_prompt_suffix(style: StylePreset) -> str:
    """
    构建图片负面提示词后缀（拼接到 prompt 末尾）。

    Agnes Image API 不支持 negative_prompt 参数，只能用自然语言描述避免内容。
    格式：avoid: xxx, yyy, zzz

    Args:
        style: 风格预设

    Returns:
        负面提示词后缀字符串（如 "avoid: color, photorealistic, 3d render"）；
        如风格无 negative_prompt，返回空字符串
    """
    negative = (style.negative_prompt or "").strip()
    if not negative:
        return ""
    return f"avoid: {negative}"
```

### 5.2 image_batch 改造

#### 5.2.1 接收 negative + 拼接到 prompt

修改 [_generate_single_image](../../../backend/app/services/pipeline/steps/image_batch.py#L249)：

```python
async def _generate_single_image(self, task: Dict[str, Any]) -> Dict[str, Any]:
    """生成单张图片"""
    prompt = task.get("prompt", "")
    size = task.get("size", "1024x1024")
    index = task.get("index", 0)
    reference_images = task.get("reference_images", [])  # 新增：角色参考图 URL 列表

    # 应用风格预设（返回 positive + negative）
    negative_suffix = ""
    if self.context.style:
        prompt, negative = style_service.build_prompt_with_style(
            prompt, self.context.style
        )
        # Agnes Image API 不支持 negative_prompt 参数，拼接到 prompt 末尾
        negative_suffix = style_service.build_negative_prompt_suffix(self.context.style)
    
    if negative_suffix:
        prompt = f"{prompt}, {negative_suffix}"

    # ... 获取 model 逻辑不变 ...

    try:
        # 如有参考图，走图生图模式；否则文生图
        if reference_images:
            result = await agnes_client.create_image(
                prompt=prompt,
                model=model,
                size=size,
                response_format="url",
                image_urls=reference_images,  # 多图参考
            )
        else:
            result = await agnes_client.create_image(
                prompt=prompt,
                model=model,
                size=size,
                response_format="url",
            )
        # ... 解析结果逻辑不变 ...
```

#### 5.2.2 角色参考图传递

修改 `_build_image_tasks` / `_build_single_task`，新增从上游 character_images 步骤获取角色图映射的逻辑：

```python
def _build_image_tasks(self) -> List[Dict[str, Any]]:
    """构建图片生成任务列表"""
    config = self.config.get("config", {})
    source = config.get("source", "parsed_result")

    # ... 原有逻辑 ...

    # 新增：如果是 scene_images 步骤，构建角色参考图映射
    reference_from_step = config.get("reference_from_step")
    character_image_map: Dict[str, str] = {}  # {角色名: image_url}
    if reference_from_step:
        character_image_map = self._build_character_image_map(reference_from_step)

    # 把角色图映射注入到每个 task
    for task in tasks:
        scene_data = task.get("scene_data", {})
        characters_in_scene = scene_data.get("characters_in_scene", [])
        if characters_in_scene and character_image_map:
            task["reference_images"] = [
                character_image_map[name]
                for name in characters_in_scene
                if name in character_image_map
            ]

    self._image_tasks_cache = tasks
    return tasks

def _build_character_image_map(self, from_step_key: str) -> Dict[str, str]:
    """
    从上游 character_images 步骤构建 {角色名: image_url} 映射。
    
    Args:
        from_step_key: 上游角色图步骤的 step_key（如 "character_images"）
    
    Returns:
        {角色名: image_url} 字典；如上游步骤无输出或无角色名，返回空字典
    """
    step_output = self.context.steps_output.get(from_step_key, {})
    images = step_output.get("images", [])
    
    mapping = {}
    for img_data in images:
        scene_data = img_data.get("scene_data") or {}
        name = scene_data.get("name", "")
        image_url = img_data.get("image_url", "")
        if name and image_url:
            mapping[name] = image_url
    
    return mapping
```

### 5.3 video_batch 改造

修改 [_create_single_video](../../../backend/app/services/pipeline/steps/video_batch.py#L323)：

```python
async def _create_single_video(self, task: Dict[str, Any]) -> Dict[str, Any]:
    """创建单个视频任务"""
    # ... 原有逻辑 ...
    
    # 应用风格预设（返回 positive + negative）
    negative_prompt = ""
    if self.context.style and mode == "text2video":
        prompt, negative_prompt = style_service.build_prompt_with_style(
            prompt, self.context.style
        )
    elif self.context.style and mode == "image2video":
        # image2video 也应用风格 positive（原代码只在 text2video 时应用，这里补上）
        prompt, negative_prompt = style_service.build_prompt_with_style(
            prompt, self.context.style
        )

    # ... 获取 model 逻辑不变 ...

    try:
        result = await agnes_client.create_video_task(
            prompt=prompt,
            model=model,
            mode=mode,
            image=image_url if mode == "image2video" else None,
            seconds=seconds,
            aspect_ratio=aspect_ratio,
            width=width,
            height=height,
            num_frames=num_frames,
            frame_rate=frame_rate,
            negative_prompt=negative_prompt or None,  # 新增：传递负面提示词
        )
        # ... 原有逻辑 ...
```

注意：原代码 `if self.context.style and mode == "text2video":` 只在文生视频时应用风格，图生视频不应用。本次改造**图生视频也应用风格**（因为 prompt 仍会传给视频 API，风格关键词有助于保持视频画面与图片风格一致）。

### 5.4 剧本模板改造（seed_pipeline_data.py）

#### 5.4.1 修改 prompt_template

在 [short_story_comic 模板](../../../backend/seed_pipeline_data.py#L280) 的 prompt 中，scenes 字段说明增加 characters_in_scene：

```
"scenes": [
  {
    "scene_num": 1,
    "description": "场景描述",
    "dialogue": "角色对话（可选）",
    "camera_angle": "镜头角度",
    "characters_in_scene": ["本场景出现的角色名1", "角色名2"],
    "image_prompt": "用于生成分镜图的英文提示词（详细描述画面内容、构图、光影）",
    "video_prompt": "用于生成动态视频的英文提示词（描述动作和镜头运动）",
    "duration": 5,
    "transition": "转场方式"
  }
]

注意：
- characters_in_scene 必须与 characters 数组中的 name 完全一致
- image_prompt 和 video_prompt 必须用英文
- image_prompt 要详细，包含：主体、环境、动作、构图、光影、风格
- 严格输出JSON，不要有多余的文字说明
```

#### 5.4.2 修改 output_schema

scenes.items.properties 增加：

```json
"characters_in_scene": {
  "type": "array",
  "items": {"type": "string"},
  "description": "本场景出现的角色名列表"
}
```

#### 5.4.3 修改 scene_images 步骤配置

[标准漫剧模板的 scene_images 步骤](../../../backend/seed_pipeline_data.py#L641) 增加 `reference_from_step`：

```python
{
    "key": "scene_images",
    "name": "分镜图片",
    "type": "image_batch",
    "depends_on": ["script_generation", "character_images"],  # 新增 character_images 依赖
    "config": {
        "source": "parsed_result",
        "from_step": "script_generation",
        "items_path": "scenes",
        "prompt_field": "image_prompt",
        "size": "1024x768",
        "max_concurrent": 5,
        "reference_from_step": "character_images",  # 新增：从角色图步骤获取参考图
    },
    "max_retries": 1,
    "timeout": 600,
},
```

注意：`depends_on` 增加 `character_images`，保证角色图先生成。

### 5.5 其他漫剧模板同步改造

[product_ad_video](../../../backend/seed_pipeline_data.py#L722) 和 [science_short](../../../backend/seed_pipeline_data.py#L777) 模板如果也有 character_images + scene_images 流程，同样增加 characters_in_scene schema 和 reference_from_step 配置。

---

## 6. 数据模型变更

**无表结构变更**。所有改动都在：
- `pipeline_templates.steps_config`（JSON）：增加 reference_from_step
- `script_templates.prompt_template`（Text）：增加 characters_in_scene 要求
- `script_templates.output_schema`（JSON）：增加 characters_in_scene 字段

---

## 7. 风险与回退

| 风险 | 应对 |
|------|------|
| 图生图比文生图慢，scene_images 耗时增加 | max_concurrent 保持 5，timeout 保持 600s；监控实际耗时 |
| Agnes Image API 多图参考效果不达预期 | reference_images 为空时自动回退文生图（代码已处理） |
| LLM 不按 schema 输出 characters_in_scene | 字段非必填，缺失时 scene_images 回退文生图 |
| "avoid: xxx" 拼接效果不如预期 | 可配置开关，后续可关闭负面拼接 |
| 已有流水线运行数据无 characters_in_scene | 不影响：新运行会用新 schema，旧数据不受影响 |

---

## 8. 测试要点

| 场景 | 预期 |
|------|------|
| 标准漫剧运行，style=comic_manga_jp | 图片为黑白漫画风，无 color/photorealistic |
| 标准漫剧运行，style=watercolor_soft | 图片为水彩风，无 anime/cartoon |
| 同一次运行的不同分镜 | 角色外貌保持一致（同一角色图作为参考） |
| scene 无 characters_in_scene | 回退文生图，不报错 |
| 视频生成 | 视频画面风格与图片一致，无负面风格元素 |
| character_images 步骤失败 | scene_images 回退文生图（无参考图） |

---

## 9. 实施顺序

1. **style_service 新增 build_negative_prompt_suffix**（独立，最简单）
2. **image_batch 改造**（接收 negative + 角色参考图传递）
3. **video_batch 改造**（接收 negative + 传给 API）
4. **seed_pipeline_data 改造**（剧本模板 + 步骤配置）
5. **重新 seed 数据库**（用户手动执行）
6. **端到端验证**（用户手动）

---

*文档结束*
