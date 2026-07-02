# 漫剧生成质量增强实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 解决漫剧生成的负面提示词失效、画面风格不稳定、人物一致性差三个问题

**Architecture:** 基于 Agnes Image API（不支持 negative_prompt，用 prompt 拼接）和 Video API（支持 negative_prompt）的实际能力，修复负面提示词传递链路；通过角色图参考图传递（image_urls 多图参考）解决人物一致性；通过 LLM schema + 风格强制前置解决画面风格稳定。

**Tech Stack:** FastAPI（async/await）+ SQLAlchemy + Vue 3（前端无改动）

**关联文档：** [2026-06-27-comic-quality-enhancement-design.md](../specs/2026-06-27-comic-quality-enhancement-design.md)

**项目约束（AGENTS.md）：** 不写测试、不执行构建、增量修改、保留功能模块备注、文案走 i18n、保留现有功能

---

## 文件结构

**后端修改：**
- `backend/app/services/style_service.py` — 新增 `build_negative_prompt_suffix`
- `backend/app/services/pipeline/steps/image_batch.py` — 接收 negative + 角色参考图传递
- `backend/app/services/pipeline/steps/video_batch.py` — 接收 negative + 传给 API
- `backend/seed_pipeline_data.py` — 剧本模板加 characters_in_scene + scene_images 步骤加 reference_from_step

**前端：** 无改动

---

## Task 1：style_service 新增 build_negative_prompt_suffix

**Files:**
- Modify: `backend/app/services/style_service.py`

- [ ] **Step 1: 在 build_prompt_with_style 函数之后新增 build_negative_prompt_suffix**

在 [style_service.py](../../../backend/app/services/style_service.py) 的 `build_prompt_with_style` 函数之后（文件末尾），新增：

```python
def build_negative_prompt_suffix(style: StylePreset) -> str:
    """
    构建图片负面提示词后缀（拼接到 prompt 末尾）。

    Agnes Image API 不支持 negative_prompt 参数（官方文档参数表无此字段），
    只能用自然语言描述避免内容。格式：avoid: xxx, yyy, zzz

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

---

## Task 2：image_batch 改造（接收 negative + 角色参考图）

**Files:**
- Modify: `backend/app/services/pipeline/steps/image_batch.py`

- [ ] **Step 1: 修改 _generate_single_image，接收 negative 并拼接到 prompt**

定位 [image_batch.py _generate_single_image](../../../backend/app/services/pipeline/steps/image_batch.py) 方法（约第 249-312 行）。

修改前（第 249-259 行）：

```python
    async def _generate_single_image(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """生成单张图片"""
        prompt = task.get("prompt", "")
        size = task.get("size", "1024x1024")
        index = task.get("index", 0)

        # 应用风格预设
        if self.context.style:
            prompt = style_service.build_prompt_with_style(
                prompt, self.context.style
            )
```

修改后：

```python
    async def _generate_single_image(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """生成单张图片"""
        prompt = task.get("prompt", "")
        size = task.get("size", "1024x1024")
        index = task.get("index", 0)
        # 角色参考图 URL 列表（来自上游 character_images 步骤，用于保持人物一致性）
        reference_images = task.get("reference_images", []) or []

        # 应用风格预设（返回 positive + negative 元组）
        # 注意：Agnes Image API 不支持 negative_prompt 参数，负面提示词拼接到 prompt 末尾
        if self.context.style:
            prompt, _negative = style_service.build_prompt_with_style(
                prompt, self.context.style
            )
            # 拼接负面提示词后缀（avoid: xxx, yyy）
            negative_suffix = style_service.build_negative_prompt_suffix(self.context.style)
            if negative_suffix:
                prompt = f"{prompt}, {negative_suffix}"
```

- [ ] **Step 2: 修改 _generate_single_image 的 create_image 调用，支持参考图**

定位同方法的 create_image 调用（约第 274-280 行）。

修改前：

```python
        try:
            result = await agnes_client.create_image(
                prompt=prompt,
                model=model,
                size=size,
                response_format="url",
            )
```

修改后：

```python
        try:
            # 如有角色参考图，走图生图模式（多图参考，保持人物一致性）；否则文生图
            if reference_images:
                result = await agnes_client.create_image(
                    prompt=prompt,
                    model=model,
                    size=size,
                    response_format="url",
                    image_urls=reference_images,
                )
            else:
                result = await agnes_client.create_image(
                    prompt=prompt,
                    model=model,
                    size=size,
                    response_format="url",
                )
```

- [ ] **Step 3: 修改 _build_image_tasks，构建角色参考图映射**

定位 [image_batch.py _build_image_tasks](../../../backend/app/services/pipeline/steps/image_batch.py) 方法（约第 138-154 行）。

修改前：

```python
    def _build_image_tasks(self) -> List[Dict[str, Any]]:
        """构建图片生成任务列表"""
        config = self.config.get("config", {})
        source = config.get("source", "parsed_result")

        if source == "parsed_result":
            tasks = self._build_tasks_from_parsed_result(config)
        elif source == "input_list":
            tasks = self._build_tasks_from_input(config)
        elif source == "custom":
            tasks = config.get("tasks", [])
        else:
            tasks = []

        # 缓存任务列表供进度查询
        self._image_tasks_cache = tasks
        return tasks
```

修改后：

```python
    def _build_image_tasks(self) -> List[Dict[str, Any]]:
        """构建图片生成任务列表"""
        config = self.config.get("config", {})
        source = config.get("source", "parsed_result")

        if source == "parsed_result":
            tasks = self._build_tasks_from_parsed_result(config)
        elif source == "input_list":
            tasks = self._build_tasks_from_input(config)
        elif source == "custom":
            tasks = config.get("tasks", [])
        else:
            tasks = []

        # 角色参考图传递：从上游 character_images 步骤构建 {角色名: image_url} 映射，
        # 为每个 scene 注入 reference_images，保持人物一致性
        reference_from_step = config.get("reference_from_step")
        if reference_from_step and tasks:
            character_image_map = self._build_character_image_map(reference_from_step)
            if character_image_map:
                for task in tasks:
                    scene_data = task.get("scene_data") or {}
                    characters_in_scene = scene_data.get("characters_in_scene") or []
                    if characters_in_scene:
                        # 根据场景出现的角色名，找到对应角色图 URL
                        refs = [
                            character_image_map[name]
                            for name in characters_in_scene
                            if name in character_image_map
                        ]
                        if refs:
                            task["reference_images"] = refs

        # 缓存任务列表供进度查询
        self._image_tasks_cache = tasks
        return tasks
```

- [ ] **Step 4: 新增 _build_character_image_map 方法**

在 `_build_tasks_from_input` 方法之后（约第 210 行）、`_build_single_task` 之前，新增：

```python
    def _build_character_image_map(self, from_step_key: str) -> Dict[str, str]:
        """
        从上游 character_images 步骤构建 {角色名: image_url} 映射。

        用于 scene_images 步骤的参考图传递：每个 scene 根据 characters_in_scene
        字段找到对应角色图，作为图生图的参考图，保持人物一致性。

        Args:
            from_step_key: 上游角色图步骤的 step_key（如 "character_images"）

        Returns:
            {角色名: image_url} 字典；
            如上游步骤无输出、无角色名、或角色图 URL 为空，返回空字典
        """
        step_output = self.context.steps_output.get(from_step_key, {})
        images = step_output.get("images", [])

        mapping: Dict[str, str] = {}
        for img_data in images:
            # character_images 步骤的 scene_data 是角色对象（含 name 字段）
            scene_data = img_data.get("scene_data") or {}
            name = scene_data.get("name", "")
            image_url = img_data.get("image_url", "")
            if name and image_url:
                mapping[name] = image_url

        return mapping
```

- [ ] **Step 5: 在 _generate_single_image 返回值中记录 reference_images（便于调试）**

定位同方法的 return 语句（约第 294-302 行）。

修改前：

```python
            return {
                "success": True,
                "index": index,
                "prompt": prompt,
                "size": size,
                "image_url": image_url,
                "scene_data": task.get("scene_data"),
                "model": model,
            }
```

修改后：

```python
            return {
                "success": True,
                "index": index,
                "prompt": prompt,
                "size": size,
                "image_url": image_url,
                "scene_data": task.get("scene_data"),
                "model": model,
                "reference_images": reference_images,  # 记录使用的参考图（便于调试）
            }
```

---

## Task 3：video_batch 改造（接收 negative + 传给 API）

**Files:**
- Modify: `backend/app/services/pipeline/steps/video_batch.py`

- [ ] **Step 1: 修改 _create_single_video，接收 negative 并传给 create_video_task**

定位 [video_batch.py _create_single_video](../../../backend/app/services/pipeline/steps/video_batch.py) 方法（约第 323-395 行）。

修改前（第 338-355 行）：

```python
        # 应用风格预设
        if self.context.style and mode == "text2video":
            prompt = style_service.build_prompt_with_style(
                prompt, self.context.style
            )

        # 获取视频模型：优先用 step config 中的 model，否则从 model_registry 取第一个可用模型
        # 复用项目原有的 model_registry 机制（与 chat_service.py 一致），避免不传 model 导致 API 拒绝
        config = self.config.get("config", {})
        model = config.get("model", "")
```

修改后：

```python
        # 应用风格预设（返回 positive + negative 元组）
        # 注意：原代码只在 text2video 时应用风格，本次改造 image2video 也应用，
        # 因为 prompt 仍会传给视频 API，风格关键词有助于保持视频画面与图片风格一致
        negative_prompt = ""
        if self.context.style:
            prompt, negative_prompt = style_service.build_prompt_with_style(
                prompt, self.context.style
            )

        # 获取视频模型：优先用 step config 中的 model，否则从 model_registry 取第一个可用模型
        # 复用项目原有的 model_registry 机制（与 chat_service.py 一致），避免不传 model 导致 API 拒绝
        config = self.config.get("config", {})
        model = config.get("model", "")
```

- [ ] **Step 2: 修改 create_video_task 调用，传 negative_prompt**

定位同方法的 create_video_task 调用（约第 364-376 行）。

修改前：

```python
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
            )
```

修改后：

```python
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
                negative_prompt=negative_prompt or None,  # Agnes Video API 原生支持负面提示词
            )
```

---

## Task 4：seed_pipeline_data 改造（剧本模板 + 步骤配置）

**Files:**
- Modify: `backend/seed_pipeline_data.py`

- [ ] **Step 1: 修改 short_story_comic 模板的 prompt_template，加 characters_in_scene 字段**

定位 [seed_pipeline_data.py 第 280-309 行](../../../backend/seed_pipeline_data.py) 的 short_story_comic 模板 prompt。

在 scenes 字段说明中增加 characters_in_scene：

修改前（第 291-302 行）：

```python
  "scenes": [
    {
      "scene_num": 1,
      "description": "场景描述",
      "dialogue": "角色对话（可选）",
      "camera_angle": "镜头角度（如：正面、侧面、俯视、特写等）",
      "image_prompt": "用于生成分镜图的英文提示词（详细描述画面内容、构图、光影）",
      "video_prompt": "用于生成动态视频的英文提示词（描述动作和镜头运动）",
      "duration": 5,
      "transition": "转场方式（如：淡入淡出、切镜、推进等）"
    }
  ]
}
```

修改后：

```python
  "scenes": [
    {
      "scene_num": 1,
      "description": "场景描述",
      "dialogue": "角色对话（可选）",
      "camera_angle": "镜头角度（如：正面、侧面、俯视、特写等）",
      "characters_in_scene": ["本场景出现的角色名1", "角色名2"],
      "image_prompt": "用于生成分镜图的英文提示词（详细描述画面内容、构图、光影）",
      "video_prompt": "用于生成动态视频的英文提示词（描述动作和镜头运动）",
      "duration": 5,
      "transition": "转场方式（如：淡入淡出、切镜、推进等）"
    }
  ]
}
```

并在"注意"部分增加一条：

```python
注意：
- characters_in_scene 必须与 characters 数组中的 name 完全一致
- image_prompt 和 video_prompt 必须用英文
- 提示词要详细，包含：主体、环境、动作、构图、光影、风格
- 严格输出JSON，不要有多余的文字说明
```

- [ ] **Step 2: 修改 short_story_comic 模板的 output_schema，加 characters_in_scene**

定位 [seed_pipeline_data.py 第 329-345 行](../../../backend/seed_pipeline_data.py) 的 scenes.items.properties。

在 `camera_angle` 之后增加：

```json
"characters_in_scene": {
  "type": "array",
  "items": {"type": "string"},
  "description": "本场景出现的角色名列表（必须与 characters.name 一致）"
},
```

- [ ] **Step 3: 修改标准漫剧模板的 scene_images 步骤，加 reference_from_step 和 character_images 依赖**

定位 [seed_pipeline_data.py 第 640-655 行](../../../backend/seed_pipeline_data.py) 的标准漫剧模板 scene_images 步骤。

修改前：

```python
            {
                "key": "scene_images",
                "name": "分镜图片",
                "type": "image_batch",
                "depends_on": ["script_generation"],
                "config": {
                    "source": "parsed_result",
                    "from_step": "script_generation",
                    "items_path": "scenes",
                    "prompt_field": "image_prompt",
                    "size": "1024x768",
                    "max_concurrent": 5,
                },
                "max_retries": 1,
                "timeout": 600,
            },
```

修改后：

```python
            {
                "key": "scene_images",
                "name": "分镜图片",
                "type": "image_batch",
                "depends_on": ["script_generation", "character_images"],
                "config": {
                    "source": "parsed_result",
                    "from_step": "script_generation",
                    "items_path": "scenes",
                    "prompt_field": "image_prompt",
                    "size": "1024x768",
                    "max_concurrent": 5,
                    "reference_from_step": "character_images",
                },
                "max_retries": 1,
                "timeout": 600,
            },
```

- [ ] **Step 4: 同步修改 product_ad_video 和 science_short 模板**

如果这两个模板也有 character_images + scene_images 流程，同样：
1. prompt_template 加 characters_in_scene
2. output_schema 加 characters_in_scene
3. scene_images 步骤加 reference_from_step + depends_on character_images

先 Read 这两个模板的结构确认是否有 character_images 步骤。如果有则改，如果没有则跳过。

---

## Task 5：端到端验证

**Files:** 无代码改动，仅手动验证

- [ ] **Step 1: 用户重新 seed 数据库**

提醒用户执行：
```bash
cd backend && python seed_pipeline_data.py
```

- [ ] **Step 2: 用户启动后端 + 前端**

- [ ] **Step 3: 验证负面提示词生效**

1. 创建标准漫剧运行，选择风格预设（如日系漫画风）
2. 等待 character_images 和 scene_images 完成
3. 检查生成的图片：
   - 应为黑白漫画风（无 color/photorealistic）
   - 日系漫画风不应出现 western comic 风格

- [ ] **Step 4: 验证人物一致性**

1. 检查生成的 scene_images：
   - 同一角色在不同场景中应保持外貌一致
   - LLM 输出的 characters_in_scene 字段正确指向角色名

- [ ] **Step 5: 验证视频负面提示词**

1. 等待 scene_videos 完成
2. 检查视频画面风格与图片一致
3. 不应出现 negative_prompt 中描述的元素

---

## Self-Review 检查

**Spec 覆盖：**
- ✅ 负面提示词生效（图片）→ Task 1 + Task 2 Step 1
- ✅ 负面提示词生效（视频）→ Task 3
- ✅ 画面风格稳定 → Task 2（style_service.build_prompt_with_style 已强制前置 visual_prefix）+ Task 4（LLM schema）
- ✅ 人物一致性 → Task 2 Step 3/4 + Task 4（characters_in_scene + reference_from_step）

**类型一致性：**
- `build_negative_prompt_suffix(style)` 在 Task 1 定义，Task 2 调用，签名一致
- `reference_images` 在 Task 2 Step 3 注入到 task，Step 2 读取，字段名一致
- `_build_character_image_map` 在 Task 2 Step 4 定义，Step 3 调用，签名一致
- `negative_prompt` 在 Task 3 Step 1 定义，Step 2 传给 API，字段名一致

**Placeholder 扫描：** 无 TBD/TODO，所有代码块完整。

**Agnes 模型能力边界确认：**
- ✅ Image API negative_prompt 拼接到 prompt（avoid: xxx）
- ✅ Video API negative_prompt 用原生参数
- ✅ Image API 多图参考用 image_urls 参数（create_image 已支持）
- ✅ 不引入 API 不支持的参数

---

## 执行选择

Plan 已保存到 `docs/superpowers/plans/2026-06-27-comic-quality-enhancement.md`。两种执行方式：

1. **Subagent-Driven（推荐）** — 每个 Task 派发独立 subagent
2. **Inline Execution** — 在当前会话顺序执行

**选哪种？**
