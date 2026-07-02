# 风格库增强 — 分层组合 + 用户自建 + 风格图分离

> 版本：v1.0
> 日期：2026-06-27
> 状态：设计中
> 关联文档：
> - [01-creative-pipeline-overview.md](../../01-creative-pipeline-overview.md)
> - [2026-06-27-comic-quality-enhancement-design.md](./2026-06-27-comic-quality-enhancement-design.md)

---

## 1. 背景

### 1.1 现状问题

当前 [StylePreset](../../../backend/app/models/pipeline.py#L139) 是"全有或全无"的完整风格套装，存在 4 个问题：

1. **不能组合**：一个 StylePreset 包含全部 7 个字段（visual_prefix/lighting/color_palette/camera_language/mood_keywords/quality_suffix/negative_prompt），只能单选。用户无法实现"水彩画风 + 电影镜头 + 暖色氛围"的组合。
2. **无权重控制**：选了就 100% 生效，不能调节某种风格的强度。
3. **preview_image 闲置**：字段存在但无数据，风格选择器没有缩略图预览。
4. **用户不能自建**：只有 is_builtin 字段，无前端创建入口。
5. **风格/角色参考混淆**：[image_batch.py](../../../backend/app/services/pipeline/steps/image_batch.py) 把 character_images 作为 reference_images，但风格图和角色图语义不同。

### 1.2 市面产品调研结论

调研了 9 款产品（Midjourney / SD / Leonardo / Firefly / Runway / Pika / SeaArt / 即梦 / Canva），共识设计模式：

- **风格 = 多层组合**：画风 + 光影 + 配色 + 镜头 + 氛围 + 品质，每层独立选择（Leonardo Elements）
- **权重滑块是标配**：每个被选中的风格元素带 0–1 权重滑块（SD LoRA / MJ `--sw`）
- **缩略图预览必备**：所有产品的风格卡都带 preview_image
- **风格/角色/结构参考分离**：风格图取视觉氛围、角色图取主体（Firefly 三参考分离）
- **用户自建风格**：表单填写 + 从作品反推（A1111 styles.csv / MJ Style Creator）

### 1.3 设计目标

基于 Agnes Image API（不支持 negative_prompt 参数，用 prompt 拼接）和 Video API（支持 negative_prompt）的实际能力，实现：

1. **分层风格组合**：新增 StyleElement 表，按 6 层独立多选 + 权重
2. **缩略图预览**：用 Agnes Image API 为每个内置风格元素生成代表性缩略图
3. **用户自建风格**：前端表单创建个人风格元素
4. **风格/角色参考分离**：image_batch 区分 style_reference 和 character_reference

---

## 2. Agnes 模型能力边界

### 2.1 Agnes Image 2.1 Flash

- **支持**：文生图（prompt/size）、图生图（image 数组多图参考）、URL/Base64 输出
- **不支持**：negative_prompt 参数、seed 参数
- **权重实现**：API 不支持权重参数，通过 prompt 中 `(keyword:1.2)` 语法实现（SD 兼容语法，Agnes Image 模型支持）

### 2.2 Agnes Video V2.0

- **支持**：negative_prompt 参数（顶层）、seed、单图 image2video、多图参考
- **不支持**：prompt 中 `(keyword:weight)` 语法（视频模型对权重的理解弱于图片模型）

**结论**：
- 图片：风格权重通过 `(keyword:weight)` 语法实现
- 视频：风格不使用权重（直接拼接 positive + negative_prompt 参数）

---

## 3. 架构设计

### 3.1 数据模型

#### 3.1.1 保留 StylePreset（完整风格套装）

不变。用于"一键应用整套风格"的快速选择场景。StylePreset 与 StyleElement 是**两条并行路径**，用户可选其一：
- 路径 A：选一个 StylePreset（套装），简单快速
- 路径 B：在 6 层中各自挑选 StyleElement（元素），灵活组合

#### 3.1.2 新增 StyleElement 表（分层风格元素）

```python
class StyleElement(Base):
    """
    风格元素（分层组合的基本单元）

    一个 StyleElement 聚焦一个视觉维度，用户可在多个层独立选择元素，
    组合出个性化风格。借鉴 Leonardo Elements 设计。

    字段说明:
    - id: 主键
    - key: 元素唯一标识（如 "visual_style.manga_jp"）
    - name: 显示名称（如 "日系漫画"）
    - description: 描述
    - layer: 所属层（visual_style / lighting / color / camera / mood / quality）
    - category: 细分类（如 visual_style 下分 anime/realistic/watercolor...）
    - content: 该层提示词内容（如 "manga style, japanese comic book art, clean lineart"）
    - negative_content: 该层负面提示词（如 "photorealistic, 3d render"）
    - preview_image: 缩略图 URL（用 Agnes Image API 生成）
    - weight_default: 默认权重 0.0–1.0（用户可调）
    - tags: 标签（JSON 数组）
    - is_builtin: 是否内置
    - is_public: 是否公开
    - author_id: 作者用户 ID
    - use_count: 使用次数
    - sort_order: 排序权重
    """
    __tablename__ = "style_elements"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(100), unique=True, nullable=False, index=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    layer = Column(String(50), nullable=False, index=True)
    category = Column(String(50), nullable=True)
    content = Column(Text, nullable=False)
    negative_content = Column(Text, nullable=True)
    preview_image = Column(String(500), nullable=True)
    weight_default = Column(Float, default=1.0, nullable=False)
    tags = Column(JSON, default=list, nullable=False)
    is_builtin = Column(Boolean, default=False, nullable=False)
    is_public = Column(Boolean, default=False, nullable=False)
    author_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    use_count = Column(Integer, default=0, nullable=False)
    sort_order = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
```

#### 3.1.3 PipelineRun.inputs 扩展

```python
# 现有
inputs = {
    "style_id": 5,  # StylePreset ID（路径 A）
}

# 扩展后（兼容）
inputs = {
    "style_id": 5,              # 路径 A：StylePreset（可选）
    "style_elements": [          # 路径 B：StyleElement 组合（可选）
        {"element_id": 1, "weight": 1.0},   # visual_style.manga_jp
        {"element_id": 12, "weight": 0.8},  # lighting.dramatic
        {"element_id": 20, "weight": 1.0},  # color.monochrome
    ],
}
```

两条路径互斥（前端 UI 二选一），后端 engine 优先级：style_id > style_elements。

#### 3.1.4 StepExecutionContext 扩展

```python
class StepExecutionContext:
    # 现有
    style: Optional[StylePreset]           # 路径 A
    # 新增
    style_elements: Optional[List[ResolvedStyleElement]]  # 路径 B（已解析的元素+权重）
```

`ResolvedStyleElement` 是已从 DB 查询并合并权重的结构：

```python
@dataclass
class ResolvedStyleElement:
    element: StyleElement
    weight: float  # 用户调整后的权重（0.0–1.0）
```

### 3.2 风格组合机制

#### 3.2.1 新增 style_service.build_prompt_with_elements

```python
def build_prompt_with_elements(
    base_prompt: str,
    resolved_elements: List[ResolvedStyleElement],
) -> tuple[str, str]:
    """
    用分层风格元素组合构建 prompt（路径 B）。

    组合规则：
    1. 按 layer 分组（visual_style / lighting / color / camera / mood / quality）
    2. 每层内多个元素按 weight 加权拼接：SD 语法 (keyword:weight)
    3. 层间按固定顺序拼接：visual_style → lighting → color → camera → mood → quality
    4. negative_prompt 合并所有元素的 negative_content（去重）

    Args:
        base_prompt: 用户原始 prompt
        resolved_elements: 已解析的风格元素+权重列表

    Returns:
        (positive_prompt, negative_prompt)
    """
    # 按 layer 分组
    layers: Dict[str, List[ResolvedStyleElement]] = defaultdict(list)
    for rse in resolved_elements:
        layers[rse.element.layer].append(rse)

    # 层级固定顺序
    layer_order = ["visual_style", "lighting", "color", "camera", "mood", "quality"]

    parts: List[str] = [base_prompt]
    negative_parts: List[str] = []

    for layer_name in layer_order:
        elements = layers.get(layer_name, [])
        if not elements:
            continue
        # 同层元素用逗号拼接，每个元素用 (content:weight) 加权
        weighted_contents = []
        for rse in elements:
            content = rse.element.content.strip()
            if not content:
                continue
            weight = max(0.0, min(1.0, rse.weight))
            if weight >= 0.99:
                weighted_contents.append(content)
            else:
                weighted_contents.append(f"({content}:{weight:.2f})")
            # 收集负面
            neg = (rse.element.negative_content or "").strip()
            if neg:
                for n in neg.split(","):
                    n = n.strip()
                    if n and n not in negative_parts:
                        negative_parts.append(n)
        if weighted_contents:
            parts.append(", ".join(weighted_contents))

    positive = ", ".join(parts)
    negative = ", ".join(negative_parts)
    return positive, negative
```

#### 3.2.2 build_negative_prompt_suffix 扩展

```python
def build_negative_prompt_suffix_from_elements(
    resolved_elements: List[ResolvedStyleElement],
) -> str:
    """构建图片负面提示词后缀（路径 B，拼接到 prompt 末尾）"""
    _, negative = build_prompt_with_elements("", resolved_elements)
    if not negative:
        return ""
    return f"avoid: {negative}"
```

### 3.3 步骤执行器改造

#### 3.3.1 image_batch.py

```python
async def _generate_single_image(self, task: Dict[str, Any]) -> Dict[str, Any]:
    prompt = task.get("prompt", "")
    reference_images = task.get("reference_images", []) or []  # 角色参考图
    style_reference_image = task.get("style_reference_image")  # 新增：风格参考图

    # 路径 A：StylePreset
    if self.context.style:
        prompt, _ = style_service.build_prompt_with_style(prompt, self.context.style)
        prompt += ", " + style_service.build_negative_prompt_suffix(self.context.style)

    # 路径 B：StyleElement 组合（优先级高于 A）
    if self.context.style_elements:
        prompt, _ = style_service.build_prompt_with_elements(prompt, self.context.style_elements)
        prompt += ", " + style_service.build_negative_prompt_suffix_from_elements(self.context.style_elements)

    # 参考图：风格参考图 + 角色参考图合并
    all_refs = []
    if style_reference_image:
        all_refs.append(style_reference_image)
    all_refs.extend(reference_images)

    if all_refs:
        result = await agnes_client.create_image(
            prompt=prompt, model=model, size=size,
            response_format="url", image_urls=all_refs,
        )
    else:
        result = await agnes_client.create_image(
            prompt=prompt, model=model, size=size, response_format="url",
        )
```

#### 3.3.2 video_batch.py

类似改造，但 negative_prompt 直接传 API 参数（不用 avoid: 拼接）。

#### 3.3.3 image_batch 的风格/角色参考分离

```python
def _build_image_tasks(self) -> List[Dict[str, Any]]:
    # ... 原有逻辑 ...

    # 角色参考图（保持现有逻辑，从 character_images 步骤获取）
    reference_from_step = config.get("reference_from_step")
    if reference_from_step and tasks:
        character_image_map = self._build_character_image_map(reference_from_step)
        # ... 注入 reference_images ...

    # 风格参考图（新增，从 step config 读取风格图 URL）
    style_reference_image = config.get("style_reference_image")
    if style_reference_image:
        for task in tasks:
            task["style_reference_image"] = style_reference_image

    return tasks
```

### 3.4 缩略图生成（preview_image）

#### 3.4.1 新增 seed 脚本 generate_style_previews.py

独立脚本，用 Agnes Image API 为每个内置 StyleElement 生成代表性缩略图：

```python
# 调用示例
result = await agnes_client.create_image(
    prompt=f"{element.content}, a beautiful sample illustration showcasing this style",
    model="agnes-image-2.1-flash",
    size="512x512",
    response_format="url",
)
# 下载到 data/style_previews/{element.key}.png
# 更新 element.preview_image = f"/api/style-elements/preview/{element.key}"
```

每个内置元素生成 1 张 512x512 缩略图，保存到本地 `data/style_previews/`。

#### 3.4.2 内置风格元素清单（6 层 × 每层 4-8 个）

| 层 | 元素示例 |
|---|---|
| visual_style | 日系漫画、国风水墨、水彩、像素艺术、3D皮克斯、赛博朋克、写实电影、油画 |
| lighting | 戏剧光影、柔和光、霓虹光、自然光、逆光剪影 |
| color | 黑白单色、暖色调、冷色调、高对比、低饱和 |
| camera | 特写、广角、俯视、低角度、第一人称 |
| mood | 温馨、神秘、紧张、史诗感、宁静 |
| quality | 杰作画质、超精细、8K、电影级 |

共约 30-40 个内置元素。

### 3.5 前端风格选择器 UI

#### 3.5.1 风格选择器组件 StyleElementPicker.vue

```
风格选择器
  ├─ 模式切换：[套装预设] | [分层组合]   ← Radio 切换两条路径
  │
  ├─ 套装预设模式（路径 A，复用现有 StylePreset 选择器）
  │   └─ 卡片网格（单选）
  │
  └─ 分层组合模式（路径 B，新增）
      ├─ Tab 行：画风 | 光影 | 配色 | 镜头 | 氛围 | 品质
      ├─ 当前 Tab 的元素卡片网格（preview_image + name + 已选标记）
      ├─ 点击卡片：切换选中/取消
      └─ 已选风格区（底部固定）：
          ├─ 每个已选元素：缩略图 + name + 权重滑块(0.0-1.0) + 移除按钮
          └─ 实时预览拼接后的完整 prompt（可折叠）
```

#### 3.5.2 用户自建风格表单 StyleElementEditor.vue

```
创建风格元素
  ├─ 名称
  ├─ 层级（下拉：visual_style/lighting/color/camera/mood/quality）
  ├─ 细分类（可选）
  ├─ 提示词内容（textarea，必填）
  ├─ 负面提示词（textarea，可选）
  ├─ 默认权重（滑块 0-1）
  ├─ 预览图上传（可选，不上传则用文字占位）
  └─ 标签（多选输入）
```

### 3.6 API 路由

```
# 风格元素 CRUD
GET    /api/style-elements                    # 列表（支持 layer/category 过滤）
GET    /api/style-elements/{id}               # 详情
POST   /api/style-elements                    # 创建（用户自建）
PUT    /api/style-elements/{id}               # 更新（仅作者）
DELETE /api/style-elements/{id}               # 删除（仅作者）
GET    /api/style-elements/preview/{key}      # 缩略图静态文件

# 风格元素组合预览（不存库，实时计算）
POST   /api/style-elements/preview-prompt     # 输入元素ID+权重，返回拼接后的 prompt
```

### 3.7 engine.py 改造

```python
# 现有：加载 style_id
style_id = run_inputs.get("style_id")
if style_id:
    self._style = await style_service.get_style_by_id(self._db, int(style_id))

# 新增：加载 style_elements
style_elements_input = run_inputs.get("style_elements") or []
if style_elements_input:
    resolved = []
    for item in style_elements_input:
        elem_id = int(item.get("element_id"))
        weight = float(item.get("weight", 1.0))
        element = await style_service.get_element_by_id(self._db, elem_id)
        if element:
            resolved.append(ResolvedStyleElement(element=element, weight=weight))
    self._style_elements = resolved
```

---

## 4. 数据模型变更

| 表 | 变更 |
|---|---|
| `style_elements` | **新增表**（见 3.1.2） |
| `pipeline_runs.inputs` | JSON 字段，新增 `style_elements` 子键（无需改表结构） |
| `style_presets` | 不变 |

需要 Alembic 迁移创建 `style_elements` 表。

---

## 5. 风险与回退

| 风险 | 应对 |
|---|---|
| Agnes Image API 的 `(keyword:weight)` 语法不支持 | 降级为不加权重，直接拼接 |
| 缩略图生成消耗 API 额度 | 每个元素只生成 1 张 512x512，约 35 张总量可控 |
| 用户自建风格质量参差 | is_public 默认 false，仅作者可见；不进广场 |
| 分层组合 prompt 过长 | 限制每层最多选 3 个元素 |
| 两条路径互斥逻辑出错 | 后端 engine 强制 style_id 优先，前端 UI 二选一 |

---

## 6. 实施顺序

1. 后端：StyleElement 模型 + 迁移
2. 后端：style_service 扩展（CRUD + build_prompt_with_elements）
3. 后端：routes/style_elements.py（API 路由）
4. 后端：engine.py 加载 style_elements + 步骤执行器改造
5. 后端：seed_style_elements.py（内置元素 + 缩略图生成）
6. 前端：StyleElementPicker.vue（分层选择器）
7. 前端：StyleElementEditor.vue（用户自建表单）
8. 前端：集成到流水线创建页
9. 端到端验证

---

*文档结束*
