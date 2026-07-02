# 风格库增强实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现分层风格组合（StyleElement 6 层多选+权重）、用户自建风格、风格/角色参考分离、内置元素缩略图生成

**Architecture:** 新增 StyleElement 表与 StylePreset 并存（两路径互斥），engine 加载 style_elements 并传给步骤执行器，style_service 新增 build_prompt_with_elements 用 SD 语法 (keyword:weight) 加权，独立脚本生成内置元素缩略图，前端新增分层选择器+自建表单。

**Tech Stack:** FastAPI + SQLAlchemy + Alembic + Vue 3 + Element Plus + Agnes Image API

**关联文档：** [2026-06-27-style-library-enhancement-design.md](../specs/2026-06-27-style-library-enhancement-design.md)

**项目约束（AGENTS.md）：** 不写测试、不执行构建、增量修改、保留功能模块备注、文案走 i18n、保留现有 StylePreset 功能不受影响

---

## 文件结构

**后端新增：**
- `backend/app/models/style_element.py` — StyleElement 模型（独立文件避免 pipeline.py 过大）
- `backend/app/schemas/style_element.py` — Pydantic schemas
- `backend/app/services/style_element_service.py` — CRUD + build_prompt_with_elements
- `backend/app/routes/style_elements.py` — API 路由
- `backend/alembic/versions/xxx_add_style_elements.py` — 数据库迁移
- `backend/seed_style_elements.py` — 内置风格元素种子数据
- `backend/generate_style_previews.py` — 缩略图生成脚本（独立手动执行）

**后端修改：**
- `backend/app/models/pipeline.py` — StyleElement 关联（或独立文件导入）
- `backend/app/services/pipeline/engine.py` — 加载 style_elements
- `backend/app/services/pipeline/steps/base.py` — StepExecutionContext 加 style_elements 字段
- `backend/app/services/pipeline/steps/image_batch.py` — 支持 style_elements + style_reference_image
- `backend/app/services/pipeline/steps/video_batch.py` — 支持 style_elements
- `backend/app/services/style_service.py` — 新增 build_negative_prompt_suffix_from_elements
- `backend/app/main.py` — 注册 style_elements 路由

**前端新增：**
- `frontend/src/components/pipeline/StyleElementPicker.vue` — 分层风格选择器
- `frontend/src/components/pipeline/StyleElementEditor.vue` — 用户自建表单
- `frontend/src/api/styleElement.ts` — API 调用

**前端修改：**
- `frontend/src/views/PipelineCreateView.vue`（或对应的创建页）— 集成风格选择器
- `frontend/src/i18n/zh-CN.ts` + `en-US.ts` — 新增文案

---

## Task 1：后端 - StyleElement 模型 + 迁移

**Files:**
- Create: `backend/app/models/style_element.py`
- Modify: `backend/app/models/__init__.py`（导出 StyleElement）
- Create: `backend/alembic/versions/20260627_add_style_elements.py`

- [ ] **Step 1: 创建 StyleElement 模型文件**

创建 `backend/app/models/style_element.py`：

```python
# =====================================================
# StyleElement 模型 — 分层风格元素
# 风格库的分层组合基本单元，用户可在多个视觉维度层
# 独立选择元素，组合出个性化风格。借鉴 Leonardo Elements 设计。
# =====================================================

from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, JSON, Boolean, ForeignKey, Float, Index
from sqlalchemy.orm import relationship

from app.core.database import Base


# 风格层级常量（与前端 Tab 一一对应）
LAYER_VISUAL_STYLE = "visual_style"  # 画风层
LAYER_LIGHTING = "lighting"          # 光影层
LAYER_COLOR = "color"                # 配色层
LAYER_CAMERA = "camera"              # 镜头层
LAYER_MOOD = "mood"                  # 氛围层
LAYER_QUALITY = "quality"            # 品质层

ALL_LAYERS = [
    LAYER_VISUAL_STYLE,
    LAYER_LIGHTING,
    LAYER_COLOR,
    LAYER_CAMERA,
    LAYER_MOOD,
    LAYER_QUALITY,
]


class StyleElement(Base):
    """
    风格元素（分层组合的基本单元）

    一个 StyleElement 聚焦一个视觉维度（如画风、光影、配色等），
    用户可在多个层独立选择元素，组合出个性化风格。

    与 StylePreset 的关系：两条并行路径，互斥使用。
    - StylePreset：完整风格套装，一键应用（简单快速）
    - StyleElement：分层元素，按层组合+权重（灵活定制）

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

    # 索引：按 layer + sort_order 查询常用
    __table_args__ = (
        Index("ix_style_elements_layer_sort", "layer", "sort_order"),
    )
```

- [ ] **Step 2: 在 models/__init__.py 导出 StyleElement**

修改 `backend/app/models/__init__.py`，新增：

```python
from app.models.style_element import StyleElement, ALL_LAYERS
```

- [ ] **Step 3: 创建 Alembic 迁移**

创建 `backend/alembic/versions/20260627_add_style_elements.py`：

```python
"""add style_elements table

Revision ID: 20260627_add_style_elements
Revises: <上一个迁移 ID>
Create Date: 2026-06-27
"""
from alembic import op
import sqlalchemy as sa


revision = "20260627_add_style_elements"
down_revision = None  # TODO: 执行前改为实际的最新 revision ID
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "style_elements",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("key", sa.String(100), nullable=False, unique=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("layer", sa.String(50), nullable=False, index=True),
        sa.Column("category", sa.String(50), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("negative_content", sa.Text(), nullable=True),
        sa.Column("preview_image", sa.String(500), nullable=True),
        sa.Column("weight_default", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("tags", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("is_builtin", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("is_public", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("author_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("use_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.create_index(
        "ix_style_elements_layer_sort",
        "style_elements",
        ["layer", "sort_order"],
    )


def downgrade() -> None:
    op.drop_index("ix_style_elements_layer_sort", table_name="style_elements")
    op.drop_table("style_elements")
```

**注意**：执行迁移前需把 `down_revision` 改为实际的最新 revision ID（用 `alembic history` 查看）。

---

## Task 2：后端 - style_element_service（CRUD + 组合逻辑）

**Files:**
- Create: `backend/app/services/style_element_service.py`
- Modify: `backend/app/services/style_service.py`（新增 build_negative_prompt_suffix_from_elements）

- [ ] **Step 1: 创建 style_element_service.py**

创建 `backend/app/services/style_element_service.py`：

```python
# =====================================================
# 风格元素服务 — StyleElement 的 CRUD + 分层组合逻辑
# =====================================================

from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.style_element import StyleElement, ALL_LAYERS


@dataclass
class ResolvedStyleElement:
    """已解析的风格元素+权重（从 DB 查询并合并用户权重后）"""
    element: StyleElement
    weight: float  # 用户调整后的权重（0.0–1.0）


# =====================================================
# CRUD
# =====================================================

async def get_element_by_id(
    db: AsyncSession, element_id: int
) -> Optional[StyleElement]:
    """按 ID 查询风格元素"""
    result = await db.execute(
        select(StyleElement).filter(StyleElement.id == element_id)
    )
    return result.scalar_one_or_none()


async def get_element_by_key(
    db: AsyncSession, key: str
) -> Optional[StyleElement]:
    """按 key 查询风格元素"""
    result = await db.execute(
        select(StyleElement).filter(StyleElement.key == key)
    )
    return result.scalar_one_or_none()


async def list_elements(
    db: AsyncSession,
    layer: Optional[str] = None,
    category: Optional[str] = None,
    is_builtin: Optional[bool] = None,
    is_public: Optional[bool] = None,
    author_id: Optional[int] = None,
    search: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> Tuple[List[StyleElement], int]:
    """
    列出风格元素（支持按层、分类、内置、公开、作者过滤）

    Returns:
        (elements, total)
    """
    query = select(StyleElement)
    filters = []
    if layer:
        filters.append(StyleElement.layer == layer)
    if category:
        filters.append(StyleElement.category == category)
    if is_builtin is not None:
        filters.append(StyleElement.is_builtin == is_builtin)
    if is_public is not None:
        filters.append(StyleElement.is_public == is_public)
    if author_id is not None:
        filters.append(StyleElement.author_id == author_id)
    if search:
        pattern = f"%{search}%"
        filters.append(
            (StyleElement.name.ilike(pattern))
            | (StyleElement.description.ilike(pattern))
            | (StyleElement.key.ilike(pattern))
        )
    for f in filters:
        query = query.filter(f)

    # 排序：内置优先，然后按 sort_order，最后按 id
    query = query.order_by(
        StyleElement.is_builtin.desc(),
        StyleElement.sort_order.asc(),
        StyleElement.id.asc(),
    )

    # 总数
    from sqlalchemy import func
    count_query = select(func.count()).select_from(StyleElement)
    for f in filters:
        count_query = count_query.filter(f)
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # 分页
    query = query.limit(limit).offset(offset)
    result = await db.execute(query)
    elements = list(result.scalars().all())
    return elements, total


async def create_element(
    db: AsyncSession,
    *,
    key: str,
    name: str,
    layer: str,
    content: str,
    description: Optional[str] = None,
    category: Optional[str] = None,
    negative_content: Optional[str] = None,
    preview_image: Optional[str] = None,
    weight_default: float = 1.0,
    tags: Optional[List[str]] = None,
    is_public: bool = False,
    author_id: Optional[int] = None,
) -> StyleElement:
    """创建风格元素（用户自建）"""
    element = StyleElement(
        key=key,
        name=name,
        description=description,
        layer=layer,
        category=category,
        content=content,
        negative_content=negative_content,
        preview_image=preview_image,
        weight_default=max(0.0, min(1.0, weight_default)),
        tags=tags or [],
        is_builtin=False,
        is_public=is_public,
        author_id=author_id,
        sort_order=999,  # 用户自建默认排在后面
    )
    db.add(element)
    await db.commit()
    await db.refresh(element)
    return element


async def update_element(
    db: AsyncSession,
    element_id: int,
    *,
    name: Optional[str] = None,
    description: Optional[str] = None,
    content: Optional[str] = None,
    negative_content: Optional[str] = None,
    preview_image: Optional[str] = None,
    weight_default: Optional[float] = None,
    tags: Optional[List[str]] = None,
    is_public: Optional[bool] = None,
) -> Optional[StyleElement]:
    """更新风格元素（仅作者或管理员可操作）"""
    element = await get_element_by_id(db, element_id)
    if not element:
        return None
    if name is not None:
        element.name = name
    if description is not None:
        element.description = description
    if content is not None:
        element.content = content
    if negative_content is not None:
        element.negative_content = negative_content
    if preview_image is not None:
        element.preview_image = preview_image
    if weight_default is not None:
        element.weight_default = max(0.0, min(1.0, weight_default))
    if tags is not None:
        element.tags = tags
    if is_public is not None:
        element.is_public = is_public
    await db.commit()
    await db.refresh(element)
    return element


async def delete_element(db: AsyncSession, element_id: int) -> bool:
    """删除风格元素（仅作者或管理员可操作，内置不可删）"""
    element = await get_element_by_id(db, element_id)
    if not element or element.is_builtin:
        return False
    await db.delete(element)
    await db.commit()
    return True


async def increment_element_use_count(db: AsyncSession, element_id: int) -> None:
    """增加使用次数"""
    element = await get_element_by_id(db, element_id)
    if element:
        element.use_count = (element.use_count or 0) + 1
        await db.commit()


# =====================================================
# 分层组合逻辑
# =====================================================

async def resolve_elements(
    db: AsyncSession,
    elements_input: List[Dict[str, Any]],
) -> List[ResolvedStyleElement]:
    """
    将用户输入的 [{element_id, weight}, ...] 解析为 ResolvedStyleElement 列表

    Args:
        elements_input: 用户输入的风格元素组合

    Returns:
        已解析的风格元素列表（过滤掉不存在或权重为 0 的）
    """
    resolved: List[ResolvedStyleElement] = []
    for item in elements_input:
        try:
            elem_id = int(item.get("element_id"))
            weight = float(item.get("weight", 1.0))
        except (ValueError, TypeError):
            continue
        if weight <= 0:
            continue
        element = await get_element_by_id(db, elem_id)
        if element:
            resolved.append(
                ResolvedStyleElement(
                    element=element,
                    weight=max(0.0, min(1.0, weight)),
                )
            )
    return resolved


def build_prompt_with_elements(
    base_prompt: str,
    resolved_elements: List[ResolvedStyleElement],
) -> Tuple[str, str]:
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

    parts: List[str] = [base_prompt] if base_prompt else []
    negative_parts: List[str] = []

    for layer_name in ALL_LAYERS:
        elements = layers.get(layer_name, [])
        if not elements:
            continue
        # 同层元素用逗号拼接，每个元素用 (content:weight) 加权
        weighted_contents = []
        for rse in elements:
            content = (rse.element.content or "").strip()
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


def build_negative_prompt_suffix_from_elements(
    resolved_elements: List[ResolvedStyleElement],
) -> str:
    """
    构建图片负面提示词后缀（路径 B，拼接到 prompt 末尾）。

    Agnes Image API 不支持 negative_prompt 参数，只能用自然语言描述避免内容。
    格式：avoid: xxx, yyy, zzz
    """
    _, negative = build_prompt_with_elements("", resolved_elements)
    if not negative:
        return ""
    return f"avoid: {negative}"


def preview_prompt(
    base_prompt: str,
    resolved_elements: List[ResolvedStyleElement],
) -> Dict[str, str]:
    """
    预览拼接后的完整 prompt（供前端实时展示，不存库）

    Returns:
        {"positive": str, "negative": str, "negative_suffix": str}
    """
    positive, negative = build_prompt_with_elements(base_prompt, resolved_elements)
    suffix = build_negative_prompt_suffix_from_elements(resolved_elements)
    return {
        "positive": positive,
        "negative": negative,
        "negative_suffix": suffix,
        "final_prompt": f"{positive}, {suffix}" if suffix else positive,
    }
```

- [ ] **Step 2: style_service.py 不再新增函数**

`build_negative_prompt_suffix_from_elements` 已在 style_element_service.py 中实现，无需修改 style_service.py。

---

## Task 3：后端 - schemas + routes/style_elements.py

**Files:**
- Create: `backend/app/schemas/style_element.py`
- Create: `backend/app/routes/style_elements.py`
- Modify: `backend/app/main.py`（注册路由）

- [ ] **Step 1: 创建 schemas/style_element.py**

```python
# =====================================================
# StyleElement Schemas — 请求和响应数据结构
# =====================================================

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class StyleElementBase(BaseModel):
    """风格元素基础字段"""
    name: str = Field(..., max_length=200, description="显示名称")
    description: Optional[str] = Field(None, description="描述")
    layer: str = Field(..., description="所属层（visual_style/lighting/color/camera/mood/quality）")
    category: Optional[str] = Field(None, max_length=50, description="细分类")
    content: str = Field(..., description="提示词内容")
    negative_content: Optional[str] = Field(None, description="负面提示词")
    preview_image: Optional[str] = Field(None, description="缩略图 URL")
    weight_default: float = Field(1.0, ge=0.0, le=1.0, description="默认权重")
    tags: List[str] = Field(default_factory=list, description="标签")
    is_public: bool = Field(False, description="是否公开")


class StyleElementCreate(StyleElementBase):
    """创建风格元素请求"""
    key: Optional[str] = Field(None, max_length=100, description="唯一标识（不传则自动生成）")


class StyleElementUpdate(BaseModel):
    """更新风格元素请求（所有字段可选）"""
    name: Optional[str] = Field(None, max_length=200)
    description: Optional[str] = None
    content: Optional[str] = None
    negative_content: Optional[str] = None
    preview_image: Optional[str] = None
    weight_default: Optional[float] = Field(None, ge=0.0, le=1.0)
    tags: Optional[List[str]] = None
    is_public: Optional[bool] = None


class StyleElementResponse(StyleElementBase):
    """风格元素响应"""
    id: int
    key: str
    is_builtin: bool
    author_id: Optional[int] = None
    use_count: int = 0
    sort_order: int = 0

    class Config:
        from_attributes = True


class StyleElementListResponse(BaseModel):
    """风格元素列表响应"""
    items: List[StyleElementResponse]
    total: int


class ResolvedElementItem(BaseModel):
    """用户选择的风格元素项"""
    element_id: int
    weight: float = Field(1.0, ge=0.0, le=1.0)


class PromptPreviewRequest(BaseModel):
    """prompt 预览请求"""
    base_prompt: str = Field("", description="基础 prompt")
    elements: List[ResolvedElementItem] = Field(default_factory=list)


class PromptPreviewResponse(BaseModel):
    """prompt 预览响应"""
    positive: str
    negative: str
    negative_suffix: str
    final_prompt: str
```

- [ ] **Step 2: 创建 routes/style_elements.py**

```python
# =====================================================
# 风格元素路由 — CRUD + prompt 预览
# =====================================================

import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_db
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.style_element import (
    StyleElementCreate,
    StyleElementUpdate,
    StyleElementResponse,
    StyleElementListResponse,
    PromptPreviewRequest,
    PromptPreviewResponse,
)
from app.services import style_element_service as svc


router = APIRouter(prefix="/api/style-elements", tags=["风格元素"])

# 缩略图存放目录
_PREVIEW_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data",
    "style_previews",
)


@router.get("", response_model=StyleElementListResponse, summary="列出风格元素")
async def list_style_elements(
    layer: Optional[str] = Query(None, description="按层过滤"),
    category: Optional[str] = Query(None, description="按分类过滤"),
    is_builtin: Optional[bool] = Query(None, description="是否内置"),
    is_public: Optional[bool] = Query(None, description="是否公开"),
    search: Optional[str] = Query(None, description="搜索关键词"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """列出风格元素（用户可见：内置 + 自己创建的 + 公开的）"""
    elements, total = await svc.list_elements(
        db,
        layer=layer,
        category=category,
        is_builtin=is_builtin,
        is_public=is_public,
        search=search,
        limit=limit,
        offset=offset,
    )
    # 过滤：非内置元素仅返回作者自己的或公开的
    visible = [
        e for e in elements
        if e.is_builtin
        or e.is_public
        or e.author_id == current_user.id
    ]
    return StyleElementListResponse(
        items=[StyleElementResponse.model_validate(e) for e in visible],
        total=len(visible),
    )


@router.get("/layers", summary="获取所有风格层级")
async def list_layers():
    """返回所有可用的风格层级（供前端 Tab 渲染）"""
    from app.models.style_element import ALL_LAYERS
    layer_names = {
        "visual_style": "画风",
        "lighting": "光影",
        "color": "配色",
        "camera": "镜头",
        "mood": "氛围",
        "quality": "品质",
    }
    return {
        "layers": [
            {"key": k, "name": layer_names.get(k, k)}
            for k in ALL_LAYERS
        ]
    }


@router.get("/preview/{key}", summary="获取风格元素缩略图")
async def get_element_preview(key: str):
    """返回风格元素缩略图静态文件"""
    # 防目录穿越
    if "/" in key or "\\" in key or ".." in key:
        raise HTTPException(status_code=400, detail="非法 key")
    # 支持的扩展名
    for ext in (".png", ".jpg", ".webp"):
        path = os.path.join(_PREVIEW_DIR, f"{key}{ext}")
        if os.path.exists(path):
            return FileResponse(path)
    raise HTTPException(status_code=404, detail="缩略图不存在")


@router.post("/preview-prompt", response_model=PromptPreviewResponse, summary="预览拼接后的 prompt")
async def preview_prompt(
    payload: PromptPreviewRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """输入元素ID+权重，返回拼接后的完整 prompt（不存库，实时计算）"""
    elements_input = [
        {"element_id": e.element_id, "weight": e.weight}
        for e in payload.elements
    ]
    resolved = await svc.resolve_elements(db, elements_input)
    result = svc.preview_prompt(payload.base_prompt, resolved)
    return PromptPreviewResponse(**result)


@router.get("/{element_id}", response_model=StyleElementResponse, summary="获取风格元素详情")
async def get_style_element(
    element_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    element = await svc.get_element_by_id(db, element_id)
    if not element:
        raise HTTPException(status_code=404, detail="风格元素不存在")
    # 权限：非内置需作者或公开
    if not element.is_builtin and not element.is_public and element.author_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权查看")
    return StyleElementResponse.model_validate(element)


@router.post("", response_model=StyleElementResponse, summary="创建风格元素")
async def create_style_element(
    payload: StyleElementCreate,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """创建用户自建风格元素"""
    # 自动生成 key（如用户不传）
    key = payload.key or f"user_{current_user.id}_{payload.layer}_{hash(payload.name) & 0xFFFFFF:x}"

    # 校验 key 唯一
    existing = await svc.get_element_by_key(db, key)
    if existing:
        raise HTTPException(status_code=400, detail="key 已存在")

    element = await svc.create_element(
        db,
        key=key,
        name=payload.name,
        layer=payload.layer,
        content=payload.content,
        description=payload.description,
        category=payload.category,
        negative_content=payload.negative_content,
        preview_image=payload.preview_image,
        weight_default=payload.weight_default,
        tags=payload.tags,
        is_public=payload.is_public,
        author_id=current_user.id,
    )
    return StyleElementResponse.model_validate(element)


@router.put("/{element_id}", response_model=StyleElementResponse, summary="更新风格元素")
async def update_style_element(
    element_id: int,
    payload: StyleElementUpdate,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """更新风格元素（仅作者或管理员）"""
    element = await svc.get_element_by_id(db, element_id)
    if not element:
        raise HTTPException(status_code=404, detail="风格元素不存在")
    if element.is_builtin:
        raise HTTPException(status_code=403, detail="内置元素不可修改")
    if element.author_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权修改")

    update_data = payload.model_dump(exclude_unset=True)
    updated = await svc.update_element(db, element_id, **update_data)
    return StyleElementResponse.model_validate(updated)


@router.delete("/{element_id}", summary="删除风格元素")
async def delete_style_element(
    element_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """删除风格元素（仅作者，内置不可删）"""
    element = await svc.get_element_by_id(db, element_id)
    if not element:
        raise HTTPException(status_code=404, detail="风格元素不存在")
    if element.is_builtin:
        raise HTTPException(status_code=403, detail="内置元素不可删除")
    if element.author_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权删除")

    ok = await svc.delete_element(db, element_id)
    if not ok:
        raise HTTPException(status_code=400, detail="删除失败")
    return {"message": "已删除"}
```

- [ ] **Step 3: 在 main.py 注册路由**

修改 `backend/app/main.py`，在现有 router 注册块新增：

```python
from app.routes.style_elements import router as style_elements_router
app.include_router(style_elements_router)
```

---

## Task 4：后端 - engine.py 加载 style_elements + 步骤执行器改造

**Files:**
- Modify: `backend/app/services/pipeline/steps/base.py`（StepExecutionContext 加字段）
- Modify: `backend/app/services/pipeline/engine.py`（加载 style_elements）
- Modify: `backend/app/services/pipeline/steps/image_batch.py`（支持 style_elements + style_reference_image）
- Modify: `backend/app/services/pipeline/steps/video_batch.py`（支持 style_elements）

- [ ] **Step 1: StepExecutionContext 加 style_elements 字段**

定位 `backend/app/services/pipeline/steps/base.py` 的 `StepExecutionContext` 类，新增 `style_elements` 字段：

```python
@dataclass
class StepExecutionContext:
    # ... 现有字段 ...
    style: Optional["StylePreset"] = None
    # 新增：分层风格元素组合（路径 B，与 style 互斥，优先级高于 style）
    style_elements: Optional[List["ResolvedStyleElement"]] = None
```

注意：`ResolvedStyleElement` 从 style_element_service 导入，为避免循环依赖用 TYPE_CHECKING 或字符串注解。

- [ ] **Step 2: engine.py 加载 style_elements**

定位 [engine.py 第 330-333 行](../../../backend/app/services/pipeline/engine.py)（`style_id` 加载块），在其后新增：

```python
        # 加载风格预设（如果输入了 style_id）—— 路径 A
        style_id = run_inputs.get("style_id")
        if style_id:
            self._style = await style_service.get_style_by_id(self._db, int(style_id))

        # 加载分层风格元素组合（如果输入了 style_elements）—— 路径 B
        # 与 style_id 互斥，优先级高于 style_id
        style_elements_input = run_inputs.get("style_elements") or []
        if style_elements_input:
            from app.services.style_element_service import resolve_elements
            self._style_elements = await resolve_elements(self._db, style_elements_input)
            # 路径 B 优先，清空路径 A
            self._style = None
```

然后在构造 StepExecutionContext 时传入：

```python
context = StepExecutionContext(
    # ... 现有字段 ...
    style=self._style,
    style_elements=self._style_elements,  # 新增
)
```

- [ ] **Step 3: image_batch.py 支持 style_elements + style_reference_image**

修改 `_generate_single_image`，在现有路径 A（context.style）之后新增路径 B（context.style_elements）：

```python
        # 路径 A：StylePreset（完整套装）
        if self.context.style:
            prompt, _negative = style_service.build_prompt_with_style(
                prompt, self.context.style
            )
            negative_suffix = style_service.build_negative_prompt_suffix(self.context.style)
            if negative_suffix:
                prompt = f"{prompt}, {negative_suffix}"

        # 路径 B：StyleElement 分层组合（优先级高于 A，engine 已保证互斥）
        if self.context.style_elements:
            from app.services.style_element_service import (
                build_prompt_with_elements,
                build_negative_prompt_suffix_from_elements,
            )
            prompt, _neg = build_prompt_with_elements(prompt, self.context.style_elements)
            neg_suffix = build_negative_prompt_suffix_from_elements(self.context.style_elements)
            if neg_suffix:
                prompt = f"{prompt}, {neg_suffix}"
```

修改 `_build_image_tasks`，新增 style_reference_image 注入：

```python
        # 风格参考图（新增，从 step config 读取风格图 URL）
        # 与角色参考图（reference_images）分离，风格图取视觉氛围，角色图取主体
        style_reference_image = config.get("style_reference_image")
        if style_reference_image:
            for task in tasks:
                task["style_reference_image"] = style_reference_image
```

修改 `_generate_single_image` 的 create_image 调用，合并风格+角色参考图：

```python
        # 参考图：风格参考图（取视觉氛围）+ 角色参考图（取主体）
        all_refs = []
        style_ref = task.get("style_reference_image")
        if style_ref:
            all_refs.append(style_ref)
        all_refs.extend(reference_images)

        try:
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

- [ ] **Step 4: video_batch.py 支持 style_elements**

修改 `_create_single_video`，在现有路径 A 之后新增路径 B：

```python
        # 路径 A：StylePreset
        negative_prompt = ""
        if self.context.style:
            prompt, negative_prompt = style_service.build_prompt_with_style(
                prompt, self.context.style
            )

        # 路径 B：StyleElement 分层组合（优先级高于 A）
        if self.context.style_elements:
            from app.services.style_element_service import build_prompt_with_elements
            prompt, negative_prompt = build_prompt_with_elements(
                prompt, self.context.style_elements
            )
```

视频 API 原生支持 negative_prompt，不用 avoid: 拼接。

---

## Task 5：后端 - seed_style_elements.py（内置风格元素种子数据）

**Files:**
- Create: `backend/seed_style_elements.py`

- [ ] **Step 1: 创建种子数据脚本**

创建 `backend/seed_style_elements.py`，包含约 35 个内置风格元素（6 层）：

```python
# =====================================================
# 风格元素种子数据 — 内置分层风格元素
# 使用方式（在 backend 目录下）：
#   python3 seed_style_elements.py
#
# 幂等性：内置元素按 key 判断，已存在则更新核心字段
# =====================================================

import asyncio
import logging
import os
import sys

script_dir = os.path.dirname(os.path.abspath(__file__))
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session
from app.models.style_element import StyleElement

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [%(levelname)s] %(message)s")
logger = logging.getLogger("seed_style_elements")


# =====================================================
# 内置风格元素数据（6 层 × 每层若干元素）
# =====================================================
BUILTIN_STYLE_ELEMENTS = [
    # ===== 画风层 visual_style =====
    {
        "key": "visual_style.manga_jp",
        "name": "日系漫画",
        "description": "日式黑白漫画风，clean lineart",
        "layer": "visual_style",
        "category": "anime",
        "content": "manga style, japanese comic book art, clean lineart, screentone",
        "negative_content": "color, photorealistic, 3d render, western comic",
        "weight_default": 1.0,
        "tags": ["anime", "comic", "black and white"],
        "sort_order": 10,
    },
    {
        "key": "visual_style.color_manhua",
        "name": "彩色国漫",
        "description": "中式彩色漫画风",
        "layer": "visual_style",
        "category": "comic",
        "content": "chinese manhua style, color comic illustration, soft shading",
        "negative_content": "photorealistic, 3d render, sketch only",
        "weight_default": 1.0,
        "tags": ["comic", "color", "chinese"],
        "sort_order": 20,
    },
    {
        "key": "visual_style.watercolor",
        "name": "水彩",
        "description": "柔和水彩画风",
        "layer": "visual_style",
        "category": "art",
        "content": "watercolor painting style, soft edges, color bleeding, paper texture",
        "negative_content": "sharp lines, digital art, 3d render",
        "weight_default": 1.0,
        "tags": ["art", "painting", "soft"],
        "sort_order": 30,
    },
    {
        "key": "visual_style.pixel_art",
        "name": "像素艺术",
        "description": "复古像素风",
        "layer": "visual_style",
        "category": "retro",
        "content": "pixel art, 16-bit retro game style, limited palette",
        "negative_content": "smooth gradients, photorealistic, high resolution",
        "weight_default": 1.0,
        "tags": ["retro", "game", "pixel"],
        "sort_order": 40,
    },
    {
        "key": "visual_style.pixar_3d",
        "name": "3D皮克斯",
        "description": "Pixar 风格 3D 渲染",
        "layer": "visual_style",
        "category": "3d",
        "content": "3d render, pixar style, smooth shading, stylized character",
        "negative_content": "2d, sketch, photorealistic, horror",
        "weight_default": 1.0,
        "tags": ["3d", "pixar", "animation"],
        "sort_order": 50,
    },
    {
        "key": "visual_style.cyberpunk",
        "name": "赛博朋克",
        "description": "霓虹赛博朋克风",
        "layer": "visual_style",
        "category": "scifi",
        "content": "cyberpunk style, neon lights, futuristic city, high tech low life",
        "negative_content": "medieval, fantasy, pastel colors",
        "weight_default": 1.0,
        "tags": ["scifi", "neon", "futuristic"],
        "sort_order": 60,
    },
    {
        "key": "visual_style.realistic_cine",
        "name": "写实电影",
        "description": "电影级写实风",
        "layer": "visual_style",
        "category": "realistic",
        "content": "cinematic realistic, photorealistic, film grain, depth of field",
        "negative_content": "anime, cartoon, 3d render, low quality",
        "weight_default": 1.0,
        "tags": ["realistic", "cinematic", "film"],
        "sort_order": 70,
    },
    {
        "key": "visual_style.chinese_ink",
        "name": "国风水墨",
        "description": "中国传统水墨画风",
        "layer": "visual_style",
        "category": "traditional",
        "content": "chinese ink painting, traditional brush stroke, xieyi style, monochrome",
        "negative_content": "color photo, 3d render, digital art",
        "weight_default": 1.0,
        "tags": ["traditional", "chinese", "ink"],
        "sort_order": 80,
    },

    # ===== 光影层 lighting =====
    {
        "key": "lighting.dramatic",
        "name": "戏剧光影",
        "description": "高对比度戏剧光",
        "layer": "lighting",
        "category": "dramatic",
        "content": "dramatic lighting, high contrast, strong shadows, chiaroscuro",
        "negative_content": "flat lighting, overexposed",
        "weight_default": 0.9,
        "tags": ["dramatic", "contrast"],
        "sort_order": 10,
    },
    {
        "key": "lighting.soft",
        "name": "柔和光",
        "description": "柔光均匀",
        "layer": "lighting",
        "category": "soft",
        "content": "soft lighting, diffused light, gentle shadows, even illumination",
        "negative_content": "harsh shadows, high contrast",
        "weight_default": 0.9,
        "tags": ["soft", "gentle"],
        "sort_order": 20,
    },
    {
        "key": "lighting.neon",
        "name": "霓虹光",
        "description": "霓虹灯光氛围",
        "layer": "lighting",
        "category": "neon",
        "content": "neon lighting, glowing lights, vibrant colors, night atmosphere",
        "negative_content": "natural daylight, muted colors",
        "weight_default": 0.9,
        "tags": ["neon", "night", "vibrant"],
        "sort_order": 30,
    },
    {
        "key": "lighting.natural",
        "name": "自然光",
        "description": "自然日光",
        "layer": "lighting",
        "category": "natural",
        "content": "natural lighting, sunlight, warm daylight, realistic illumination",
        "negative_content": "artificial neon, studio lighting",
        "weight_default": 0.9,
        "tags": ["natural", "daylight"],
        "sort_order": 40,
    },
    {
        "key": "lighting.backlight",
        "name": "逆光剪影",
        "description": "逆光剪影效果",
        "layer": "lighting",
        "category": "backlight",
        "content": "backlight, silhouette, rim light, glowing edges",
        "negative_content": "front lighting, flat",
        "weight_default": 0.9,
        "tags": ["backlight", "silhouette"],
        "sort_order": 50,
    },

    # ===== 配色层 color =====
    {
        "key": "color.monochrome",
        "name": "黑白单色",
        "description": "黑白单色配色",
        "layer": "color",
        "category": "monochrome",
        "content": "black and white, monochrome, grayscale",
        "negative_content": "colorful, vivid colors",
        "weight_default": 1.0,
        "tags": ["bw", "monochrome"],
        "sort_order": 10,
    },
    {
        "key": "color.warm",
        "name": "暖色调",
        "description": "温暖橙红色调",
        "layer": "color",
        "category": "warm",
        "content": "warm color palette, orange tones, cozy atmosphere",
        "negative_content": "cold blue tones",
        "weight_default": 0.9,
        "tags": ["warm", "orange"],
        "sort_order": 20,
    },
    {
        "key": "color.cold",
        "name": "冷色调",
        "description": "冷蓝绿色调",
        "layer": "color",
        "category": "cold",
        "content": "cold color palette, blue tones, cool atmosphere",
        "negative_content": "warm orange tones",
        "weight_default": 0.9,
        "tags": ["cold", "blue"],
        "sort_order": 30,
    },
    {
        "key": "color.high_contrast",
        "name": "高对比",
        "description": "高饱和高对比",
        "layer": "color",
        "category": "contrast",
        "content": "high contrast colors, vivid saturation, bold palette",
        "negative_content": "muted, desaturated, pastel",
        "weight_default": 0.9,
        "tags": ["contrast", "vivid"],
        "sort_order": 40,
    },
    {
        "key": "color.pastel",
        "name": "低饱和",
        "description": "柔和低饱和粉彩",
        "layer": "color",
        "category": "pastel",
        "content": "pastel colors, soft palette, low saturation, dreamy",
        "negative_content": "high saturation, bold contrast",
        "weight_default": 0.9,
        "tags": ["pastel", "soft", "dreamy"],
        "sort_order": 50,
    },

    # ===== 镜头层 camera =====
    {
        "key": "camera.closeup",
        "name": "特写",
        "description": "面部/物体特写",
        "layer": "camera",
        "category": "closeup",
        "content": "close-up shot, detailed face, shallow depth of field",
        "negative_content": "wide shot, distant",
        "weight_default": 0.9,
        "tags": ["closeup", "detail"],
        "sort_order": 10,
    },
    {
        "key": "camera.wide",
        "name": "广角",
        "description": "广角全景",
        "layer": "camera",
        "category": "wide",
        "content": "wide angle shot, expansive view, establishing shot",
        "negative_content": "close-up, cramped",
        "weight_default": 0.9,
        "tags": ["wide", "panorama"],
        "sort_order": 20,
    },
    {
        "key": "camera.topdown",
        "name": "俯视",
        "description": "俯视鸟瞰角度",
        "layer": "camera",
        "category": "angle",
        "content": "top-down view, bird's eye angle, overhead shot",
        "negative_content": "eye level, low angle",
        "weight_default": 0.9,
        "tags": ["topdown", "overhead"],
        "sort_order": 30,
    },
    {
        "key": "camera.low_angle",
        "name": "低角度",
        "description": "仰视英雄角度",
        "layer": "camera",
        "category": "angle",
        "content": "low angle shot, looking up, heroic perspective",
        "negative_content": "top-down, eye level",
        "weight_default": 0.9,
        "tags": ["lowangle", "heroic"],
        "sort_order": 40,
    },
    {
        "key": "camera.pov",
        "name": "第一人称",
        "description": "第一人称视角",
        "layer": "camera",
        "category": "pov",
        "content": "first person view, POV shot, immersive perspective",
        "negative_content": "third person, distant",
        "weight_default": 0.9,
        "tags": ["pov", "immersive"],
        "sort_order": 50,
    },

    # ===== 氛围层 mood =====
    {
        "key": "mood.warm_cozy",
        "name": "温馨",
        "description": "温馨治愈氛围",
        "layer": "mood",
        "category": "warm",
        "content": "warm cozy atmosphere, heartwarming, gentle mood",
        "negative_content": "dark, horror, tense",
        "weight_default": 0.9,
        "tags": ["warm", "cozy", "healing"],
        "sort_order": 10,
    },
    {
        "key": "mood.mysterious",
        "name": "神秘",
        "description": "神秘悬疑氛围",
        "layer": "mood",
        "category": "mystery",
        "content": "mysterious atmosphere, enigmatic mood, suspenseful",
        "negative_content": "cheerful, bright",
        "weight_default": 0.9,
        "tags": ["mystery", "suspense"],
        "sort_order": 20,
    },
    {
        "key": "mood.tense",
        "name": "紧张",
        "description": "紧张刺激氛围",
        "layer": "mood",
        "category": "tense",
        "content": "tense atmosphere, thrilling mood, high stakes",
        "negative_content": "relaxed, peaceful",
        "weight_default": 0.9,
        "tags": ["tense", "thrilling"],
        "sort_order": 30,
    },
    {
        "key": "mood.epic",
        "name": "史诗感",
        "description": "宏大史诗氛围",
        "layer": "mood",
        "category": "epic",
        "content": "epic atmosphere, grand scale, majestic mood",
        "negative_content": "small scale, mundane",
        "weight_default": 0.9,
        "tags": ["epic", "grand"],
        "sort_order": 40,
    },
    {
        "key": "mood.peaceful",
        "name": "宁静",
        "description": "宁静祥和氛围",
        "layer": "mood",
        "category": "peaceful",
        "content": "peaceful atmosphere, serene mood, tranquil",
        "negative_content": "chaotic, tense",
        "weight_default": 0.9,
        "tags": ["peaceful", "serene"],
        "sort_order": 50,
    },

    # ===== 品质层 quality =====
    {
        "key": "quality.masterpiece",
        "name": "杰作画质",
        "description": "最高品质",
        "layer": "quality",
        "category": "quality",
        "content": "masterpiece, best quality, highly detailed",
        "negative_content": "low quality, worst quality, blurry",
        "weight_default": 1.0,
        "tags": ["quality", "masterpiece"],
        "sort_order": 10,
    },
    {
        "key": "quality.ultra_detail",
        "name": "超精细",
        "description": "极致细节",
        "layer": "quality",
        "category": "detail",
        "content": "ultra detailed, intricate details, fine texture",
        "negative_content": "simple, low detail",
        "weight_default": 1.0,
        "tags": ["detail", "intricate"],
        "sort_order": 20,
    },
    {
        "key": "quality.8k",
        "name": "8K",
        "description": "8K 超高分辨率",
        "layer": "quality",
        "category": "resolution",
        "content": "8k resolution, ultra high definition, sharp focus",
        "negative_content": "low resolution, blurry",
        "weight_default": 1.0,
        "tags": ["8k", "uhd"],
        "sort_order": 30,
    },
    {
        "key": "quality.cinematic",
        "name": "电影级",
        "description": "电影级画质",
        "layer": "quality",
        "category": "cinematic",
        "content": "cinematic quality, film grain, professional color grading",
        "negative_content": "amateur, low budget",
        "weight_default": 1.0,
        "tags": ["cinematic", "film"],
        "sort_order": 40,
    },
]


async def seed_style_elements(db: AsyncSession) -> int:
    """写入内置风格元素（内置支持 upsert）"""
    added = 0
    updated = 0
    for elem_data in BUILTIN_STYLE_ELEMENTS:
        key = elem_data["key"]
        result = await db.execute(select(StyleElement).filter(StyleElement.key == key))
        existing = result.scalar_one_or_none()
        if existing:
            # 内置元素：更新核心字段
            existing.name = elem_data["name"]
            existing.description = elem_data.get("description", "")
            existing.layer = elem_data["layer"]
            existing.category = elem_data.get("category")
            existing.content = elem_data["content"]
            existing.negative_content = elem_data.get("negative_content", "")
            existing.weight_default = elem_data.get("weight_default", 1.0)
            existing.tags = elem_data.get("tags", [])
            existing.sort_order = elem_data.get("sort_order", 0)
            existing.is_builtin = True
            existing.is_public = True
            updated += 1
            logger.info("更新风格元素: %s", key)
            continue

        # 新增
        element = StyleElement(
            **elem_data,
            is_builtin=True,
            is_public=True,
        )
        db.add(element)
        added += 1
        logger.info("新增风格元素: %s (%s)", key, elem_data["name"])

    if added or updated:
        await db.commit()
        logger.info("风格元素写入完成 ✓ 新增 %d 个，更新 %d 个", added, updated)
    else:
        logger.info("风格元素已完整，无需新增")
    return added


async def main():
    print("==== 开始写入风格元素种子数据 ====")
    async with async_session() as session:
        await seed_style_elements(session)
    print("==== 种子数据写入完成 ====")


if __name__ == "__main__":
    asyncio.run(main())
```

---

## Task 6：后端 - generate_style_previews.py（缩略图生成脚本）

**Files:**
- Create: `backend/generate_style_previews.py`

- [ ] **Step 1: 创建缩略图生成脚本**

创建 `backend/generate_style_previews.py`：

```python
# =====================================================
# 风格元素缩略图生成脚本
# 功能：用 Agnes Image API 为每个内置风格元素生成代表性缩略图
# 使用方式（在 backend 目录下）：
#   python3 generate_style_previews.py
#
# 注意：
# - 会消耗 Agnes Image API 额度（每个元素 1 张 512x512）
# - 已存在缩略图的元素会跳过（幂等）
# - 生成的图片保存到 data/style_previews/{key}.png
# =====================================================

import asyncio
import logging
import os
import sys

script_dir = os.path.dirname(os.path.abspath(__file__))
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session
from app.models.style_element import StyleElement
from app.services.agnes_client import agnes_client

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [%(levelname)s] %(message)s")
logger = logging.getLogger("generate_style_previews")

# 缩略图存放目录
PREVIEW_DIR = os.path.join(script_dir, "data", "style_previews")


async def generate_preview_for_element(element: StyleElement, db: AsyncSession) -> bool:
    """为单个风格元素生成缩略图，返回是否生成成功"""
    # 检查是否已有缩略图（幂等）
    for ext in (".png", ".jpg", ".webp"):
        if os.path.exists(os.path.join(PREVIEW_DIR, f"{element.key}{ext}")):
            logger.info("跳过（已存在）: %s", element.key)
            return False

    # 构造生成 prompt：用元素 content + 示意图说明
    prompt = (
        f"{element.content}, a beautiful sample illustration showcasing this {element.layer} style, "
        f"high quality, representative artwork"
    )

    try:
        result = await agnes_client.create_image(
            prompt=prompt,
            model="agnes-image-2.1-flash",
            size="512x512",
            response_format="url",
        )
        image_url = result.get("data", {}).get("url") if isinstance(result, dict) else None
        if not image_url and isinstance(result, dict):
            # 兼容其他返回格式
            image_url = result.get("url") or result.get("image_url")

        if not image_url:
            logger.warning("生成失败（无 URL）: %s", element.key)
            return False

        # 下载图片
        import httpx
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.get(image_url)
            if resp.status_code != 200:
                logger.warning("下载失败: %s status=%d", element.key, resp.status_code)
                return False

            # 保存
            os.makedirs(PREVIEW_DIR, exist_ok=True)
            out_path = os.path.join(PREVIEW_DIR, f"{element.key}.png")
            with open(out_path, "wb") as f:
                f.write(resp.content)

        # 更新 DB 中的 preview_image 字段
        element.preview_image = f"/api/style-elements/preview/{element.key}"
        await db.commit()

        logger.info("生成成功: %s -> %s", element.key, out_path)
        return True

    except Exception as e:
        logger.error("生成异常: %s - %s", element.key, e)
        return False


async def main():
    print("==== 开始生成风格元素缩略图 ====")
    os.makedirs(PREVIEW_DIR, exist_ok=True)

    async with async_session() as session:
        # 查询所有内置元素
        result = await session.execute(
            select(StyleElement).filter(StyleElement.is_builtin == True).order_by(StyleElement.layer, StyleElement.sort_order)
        )
        elements = list(result.scalars().all())

        if not elements:
            print("未找到内置风格元素，请先执行 seed_style_elements.py")
            return

        print(f"共 {len(elements)} 个内置元素待处理")

        # 串行生成（避免并发消耗过多 API 额度）
        success = 0
        skipped = 0
        failed = 0
        for i, element in enumerate(elements, 1):
            print(f"[{i}/{len(elements)}] 处理: {element.key} ({element.name})")
            try:
                generated = await generate_preview_for_element(element, session)
                if generated:
                    success += 1
                else:
                    skipped += 1
            except Exception as e:
                logger.error("处理失败: %s - %s", element.key, e)
                failed += 1
                continue
            # 间隔避免 API 限流
            await asyncio.sleep(1)

        print(f"\n==== 完成 ====")
        print(f"成功生成: {success}")
        print(f"已跳过: {skipped}")
        print(f"失败: {failed}")
        print(f"缩略图目录: {PREVIEW_DIR}")


if __name__ == "__main__":
    asyncio.run(main())
```

---

## Task 7：前端 - API 层 + 类型定义

**Files:**
- Create: `frontend/src/api/styleElement.ts`

- [ ] **Step 1: 创建 styleElement.ts**

```typescript
// =====================================================
// 风格元素 API — 分层风格组合接口
// =====================================================

import client from './client'

/** 风格层级 */
export type StyleLayer = 'visual_style' | 'lighting' | 'color' | 'camera' | 'mood' | 'quality'

/** 风格元素 */
export interface StyleElement {
  id: number
  key: string
  name: string
  description?: string
  layer: StyleLayer
  category?: string
  content: string
  negative_content?: string
  preview_image?: string
  weight_default: number
  tags: string[]
  is_builtin: boolean
  is_public: boolean
  author_id?: number
  use_count: number
  sort_order: number
}

/** 用户选择的风格元素项（带权重） */
export interface ResolvedElementItem {
  element_id: number
  weight: number
}

/** 列表响应 */
export interface StyleElementListResponse {
  items: StyleElement[]
  total: number
}

/** 层级信息 */
export interface LayerInfo {
  key: string
  name: string
}

/** prompt 预览请求 */
export interface PromptPreviewRequest {
  base_prompt: string
  elements: ResolvedElementItem[]
}

/** prompt 预览响应 */
export interface PromptPreviewResponse {
  positive: string
  negative: string
  negative_suffix: string
  final_prompt: string
}

/** 创建风格元素请求 */
export interface StyleElementCreate {
  key?: string
  name: string
  description?: string
  layer: StyleLayer
  category?: string
  content: string
  negative_content?: string
  preview_image?: string
  weight_default?: number
  tags?: string[]
  is_public?: boolean
}

/** 更新风格元素请求 */
export interface StyleElementUpdate {
  name?: string
  description?: string
  content?: string
  negative_content?: string
  preview_image?: string
  weight_default?: number
  tags?: string[]
  is_public?: boolean
}

/**
 * 列出风格元素（支持按层过滤）
 */
export function listStyleElements(params?: {
  layer?: StyleLayer
  category?: string
  is_builtin?: boolean
  is_public?: boolean
  search?: string
  limit?: number
  offset?: number
}): Promise<StyleElementListResponse> {
  return client.get('/api/style-elements', { params })
}

/**
 * 获取所有风格层级
 */
export function listLayers(): Promise<{ layers: LayerInfo[] }> {
  return client.get('/api/style-elements/layers')
}

/**
 * 预览拼接后的 prompt
 */
export function previewPrompt(payload: PromptPreviewRequest): Promise<PromptPreviewResponse> {
  return client.post('/api/style-elements/preview-prompt', payload)
}

/**
 * 创建风格元素（用户自建）
 */
export function createStyleElement(payload: StyleElementCreate): Promise<StyleElement> {
  return client.post('/api/style-elements', payload)
}

/**
 * 更新风格元素
 */
export function updateStyleElement(id: number, payload: StyleElementUpdate): Promise<StyleElement> {
  return client.put(`/api/style-elements/${id}`, payload)
}

/**
 * 删除风格元素
 */
export function deleteStyleElement(id: number): Promise<{ message: string }> {
  return client.delete(`/api/style-elements/${id}`)
}
```

---

## Task 8：前端 - StyleElementPicker.vue（分层选择器）

**Files:**
- Create: `frontend/src/components/pipeline/StyleElementPicker.vue`

- [ ] **Step 1: 创建分层风格选择器组件**

```vue
<template>
  <div class="style-element-picker">
    <!-- 已选风格区（顶部固定） -->
    <div v-if="selectedElements.length > 0" class="selected-area">
      <div class="selected-header">
        <span>{{ t('styleElement.selectedCount', { count: selectedElements.length }) }}</span>
        <el-button text size="small" @click="clearAll">{{ t('styleElement.clearAll') }}</el-button>
      </div>
      <div class="selected-list">
        <div
          v-for="item in selectedElements"
          :key="item.element_id"
          class="selected-item"
        >
          <el-image
            v-if="getElement(item.element_id)?.preview_image"
            :src="getElement(item.element_id)!.preview_image"
            class="selected-thumb"
            fit="cover"
          />
          <div v-else class="selected-thumb placeholder">
            {{ getElement(item.element_id)?.layer.charAt(0).toUpperCase() }}
          </div>
          <div class="selected-info">
            <div class="selected-name">{{ getElement(item.element_id)?.name }}</div>
            <div class="selected-layer">{{ layerName(getElement(item.element_id)?.layer) }}</div>
          </div>
          <el-slider
            v-model="item.weight"
            :min="0"
            :max="1"
            :step="0.1"
            :show-tooltip="false"
            class="weight-slider"
            @input="onWeightChange"
          />
          <span class="weight-value">{{ item.weight.toFixed(1) }}</span>
          <el-button
            text
            size="small"
            type="danger"
            @click="removeElement(item.element_id)"
          >
            <el-icon><Close /></el-icon>
          </el-button>
        </div>
      </div>
      <!-- prompt 预览（可折叠） -->
      <el-collapse v-model="promptPreviewCollapse" class="prompt-preview-collapse">
        <el-collapse-item :title="t('styleElement.promptPreview')" name="preview">
          <div v-if="promptPreview" class="prompt-preview-content">
            <div class="preview-section">
              <div class="preview-label">{{ t('styleElement.finalPrompt') }}:</div>
              <div class="preview-text">{{ promptPreview.final_prompt }}</div>
            </div>
          </div>
          <div v-else class="preview-loading">{{ t('styleElement.loading') }}</div>
        </el-collapse-item>
      </el-collapse>
    </div>

    <!-- Tab 分层 -->
    <el-tabs v-model="activeLayer" class="layer-tabs">
      <el-tab-pane
        v-for="layer in layers"
        :key="layer.key"
        :label="layer.name"
        :name="layer.key"
      />
    </el-tabs>

    <!-- 当前层的元素卡片网格 -->
    <div v-loading="loading" class="element-grid">
      <div
        v-for="element in currentLayerElements"
        :key="element.id"
        class="element-card"
        :class="{ selected: isSelected(element.id) }"
        @click="toggleElement(element)"
      >
        <el-image
          v-if="element.preview_image"
          :src="element.preview_image"
          class="element-thumb"
          fit="cover"
        />
        <div v-else class="element-thumb placeholder">
          <el-icon><Picture /></el-icon>
        </div>
        <div class="element-info">
          <div class="element-name">{{ element.name }}</div>
          <div class="element-desc">{{ element.description }}</div>
          <div class="element-tags">
            <el-tag v-for="tag in element.tags" :key="tag" size="small" type="info">
              {{ tag }}
            </el-tag>
          </div>
        </div>
        <div v-if="isSelected(element.id)" class="selected-badge">
          <el-icon color="#67c23a"><Check /></el-icon>
        </div>
      </div>
    </div>
    <el-empty v-if="!loading && currentLayerElements.length === 0" :description="t('styleElement.noElements')" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import { Close, Check, Picture } from '@element-plus/icons-vue'
import {
  listStyleElements,
  listLayers,
  previewPrompt,
  type StyleElement,
  type StyleLayer,
  type ResolvedElementItem,
  type LayerInfo,
} from '@/api/styleElement'

const props = defineProps<{
  basePrompt?: string
}>()

const emit = defineEmits<{
  (e: 'change', elements: ResolvedElementItem[]): void
}>()

const { t } = useI18n()

// ================ 状态 ================
const loading = ref(false)
const layers = ref<LayerInfo[]>([])
const allElements = ref<StyleElement[]>([])
const activeLayer = ref<StyleLayer>('visual_style')
const selectedElements = ref<ResolvedElementItem[]>([])

// prompt 预览
const promptPreviewCollapse = ref<string[]>([])
const promptPreview = ref<Awaited<ReturnType<typeof previewPrompt>> | null>(null)
const previewTimer = ref<ReturnType<typeof setTimeout> | null>(null)

// ================ 计算属性 ================
const currentLayerElements = computed(() =>
  allElements.value.filter(e => e.layer === activeLayer.value)
)

// ================ 方法 ================
function getElement(id: number): StyleElement | undefined {
  return allElements.value.find(e => e.id === id)
}

function layerName(key?: string): string {
  if (!key) return ''
  const layer = layers.value.find(l => l.key === key)
  return layer?.name || key
}

function isSelected(id: number): boolean {
  return selectedElements.value.some(s => s.element_id === id)
}

function toggleElement(element: StyleElement) {
  if (isSelected(element.id)) {
    removeElement(element.id)
  } else {
    selectedElements.value.push({
      element_id: element.id,
      weight: element.weight_default,
    })
    onWeightChange()
  }
}

function removeElement(id: number) {
  selectedElements.value = selectedElements.value.filter(s => s.element_id !== id)
  onWeightChange()
}

function clearAll() {
  selectedElements.value = []
  onWeightChange()
}

function onWeightChange() {
  emit('change', selectedElements.value)
  // 防抖更新 prompt 预览
  if (previewTimer.value) clearTimeout(previewTimer.value)
  previewTimer.value = setTimeout(updatePromptPreview, 500)
}

async function updatePromptPreview() {
  if (selectedElements.value.length === 0) {
    promptPreview.value = null
    return
  }
  try {
    promptPreview.value = await previewPrompt({
      base_prompt: props.basePrompt || '',
      elements: selectedElements.value,
    })
  } catch (e) {
    // 预览失败不阻断
    console.warn('prompt 预览失败', e)
  }
}

async function loadData() {
  loading.value = true
  try {
    const [layerRes, elementsRes] = await Promise.all([
      listLayers(),
      listStyleElements({ is_builtin: true, limit: 500 }),
    ])
    layers.value = layerRes.layers
    allElements.value = elementsRes.items
  } catch (e: any) {
    ElMessage.error(e?.message || t('styleElement.loadFailed'))
  } finally {
    loading.value = false
  }
}

onMounted(loadData)
</script>

<style scoped>
.style-element-picker {
  width: 100%;
}

.selected-area {
  background: var(--el-fill-color-light);
  border-radius: 8px;
  padding: 12px;
  margin-bottom: 16px;
}

.selected-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.selected-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.selected-item {
  display: flex;
  align-items: center;
  gap: 12px;
  background: var(--el-bg-color);
  border-radius: 6px;
  padding: 8px;
}

.selected-thumb {
  width: 40px;
  height: 40px;
  border-radius: 4px;
  flex-shrink: 0;
}

.selected-thumb.placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--el-color-primary-light-7);
  color: var(--el-color-primary);
  font-weight: bold;
}

.selected-info {
  flex-shrink: 0;
  min-width: 120px;
}

.selected-name {
  font-size: 13px;
  font-weight: 500;
}

.selected-layer {
  font-size: 11px;
  color: var(--el-text-color-secondary);
}

.weight-slider {
  flex: 1;
  min-width: 100px;
}

.weight-value {
  width: 30px;
  text-align: right;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.prompt-preview-collapse {
  margin-top: 8px;
}

.prompt-preview-content {
  font-size: 12px;
  background: var(--el-bg-color);
  padding: 8px;
  border-radius: 4px;
}

.preview-label {
  font-weight: 500;
  margin-bottom: 4px;
}

.preview-text {
  color: var(--el-text-color-secondary);
  word-break: break-all;
  line-height: 1.6;
}

.layer-tabs {
  margin-bottom: 16px;
}

.element-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 12px;
  min-height: 200px;
}

.element-card {
  border: 2px solid var(--el-border-color-light);
  border-radius: 8px;
  overflow: hidden;
  cursor: pointer;
  transition: all 0.2s;
  position: relative;
  background: var(--el-bg-color);
}

.element-card:hover {
  border-color: var(--el-color-primary-light-5);
  transform: translateY(-2px);
}

.element-card.selected {
  border-color: var(--el-color-success);
  background: var(--el-color-success-light-9);
}

.element-thumb {
  width: 100%;
  height: 120px;
}

.element-thumb.placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--el-fill-color-light);
  color: var(--el-text-color-placeholder);
  font-size: 24px;
}

.element-info {
  padding: 8px;
}

.element-name {
  font-size: 13px;
  font-weight: 500;
  margin-bottom: 4px;
}

.element-desc {
  font-size: 11px;
  color: var(--el-text-color-secondary);
  margin-bottom: 4px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.element-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.selected-badge {
  position: absolute;
  top: 8px;
  right: 8px;
  background: var(--el-color-success);
  border-radius: 50%;
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
}
</style>
```

---

## Task 9：前端 - StyleElementEditor.vue（用户自建表单）

**Files:**
- Create: `frontend/src/components/pipeline/StyleElementEditor.vue`

- [ ] **Step 1: 创建用户自建风格表单**

```vue
<template>
  <el-dialog
    v-model="visible"
    :title="t('styleElement.createTitle')"
    width="600px"
    @closed="onClosed"
  >
    <el-form
      ref="formRef"
      :model="form"
      :rules="rules"
      label-width="120px"
      label-position="right"
    >
      <el-form-item :label="t('styleElement.name')" prop="name">
        <el-input v-model="form.name" :placeholder="t('styleElement.namePlaceholder')" />
      </el-form-item>

      <el-form-item :label="t('styleElement.layer')" prop="layer">
        <el-select v-model="form.layer" :placeholder="t('styleElement.layerPlaceholder')">
          <el-option
            v-for="layer in layers"
            :key="layer.key"
            :label="layer.name"
            :value="layer.key"
          />
        </el-select>
      </el-form-item>

      <el-form-item :label="t('styleElement.category')" prop="category">
        <el-input v-model="form.category" :placeholder="t('styleElement.categoryPlaceholder')" />
      </el-form-item>

      <el-form-item :label="t('styleElement.content')" prop="content">
        <el-input
          v-model="form.content"
          type="textarea"
          :rows="3"
          :placeholder="t('styleElement.contentPlaceholder')"
        />
      </el-form-item>

      <el-form-item :label="t('styleElement.negativeContent')" prop="negative_content">
        <el-input
          v-model="form.negative_content"
          type="textarea"
          :rows="2"
          :placeholder="t('styleElement.negativePlaceholder')"
        />
      </el-form-item>

      <el-form-item :label="t('styleElement.weightDefault')" prop="weight_default">
        <el-slider
          v-model="form.weight_default"
          :min="0"
          :max="1"
          :step="0.1"
          show-input
        />
      </el-form-item>

      <el-form-item :label="t('styleElement.tags')" prop="tags">
        <el-input
          v-model="tagInput"
          :placeholder="t('styleElement.tagsPlaceholder')"
          @keyup.enter="addTag"
        />
        <div class="tag-list">
          <el-tag
            v-for="(tag, i) in form.tags"
            :key="i"
            closable
            @close="removeTag(i)"
          >
            {{ tag }}
          </el-tag>
        </div>
      </el-form-item>

      <el-form-item :label="t('styleElement.isPublic')" prop="is_public">
        <el-switch v-model="form.is_public" />
        <span class="form-hint">{{ t('styleElement.isPublicHint') }}</span>
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="visible = false">{{ t('common.cancel') }}</el-button>
      <el-button type="primary" :loading="submitting" @click="handleSubmit">
        {{ t('common.create') }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, reactive, watch, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import {
  listLayers,
  createStyleElement,
  type StyleElementCreate,
  type StyleLayer,
  type LayerInfo,
} from '@/api/styleElement'

const props = defineProps<{
  modelValue: boolean
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'created'): void
}>()

const { t } = useI18n()

const visible = ref(props.modelValue)
watch(() => props.modelValue, v => { visible.value = v })
watch(visible, v => emit('update:modelValue', v))

const formRef = ref<FormInstance>()
const submitting = ref(false)
const layers = ref<LayerInfo[]>([])
const tagInput = ref('')

const form = reactive<StyleElementCreate>({
  name: '',
  layer: 'visual_style',
  category: '',
  content: '',
  negative_content: '',
  weight_default: 1.0,
  tags: [],
  is_public: false,
})

const rules: FormRules = {
  name: [{ required: true, message: t('styleElement.nameRequired'), trigger: 'blur' }],
  layer: [{ required: true, message: t('styleElement.layerRequired'), trigger: 'change' }],
  content: [{ required: true, message: t('styleElement.contentRequired'), trigger: 'blur' }],
}

function addTag() {
  const tag = tagInput.value.trim()
  if (tag && !form.tags?.includes(tag)) {
    form.tags = [...(form.tags || []), tag]
  }
  tagInput.value = ''
}

function removeTag(i: number) {
  form.tags = (form.tags || []).filter((_, idx) => idx !== i)
}

function onClosed() {
  formRef.value?.resetFields()
  form.name = ''
  form.category = ''
  form.content = ''
  form.negative_content = ''
  form.weight_default = 1.0
  form.tags = []
  form.is_public = false
}

async function handleSubmit() {
  if (!formRef.value) return
  await formRef.value.validate(async (valid) => {
    if (!valid) return
    submitting.value = true
    try {
      await createStyleElement({ ...form })
      ElMessage.success(t('styleElement.createSuccess'))
      emit('created')
      visible.value = false
    } catch (e: any) {
      ElMessage.error(e?.message || t('styleElement.createFailed'))
    } finally {
      submitting.value = false
    }
  })
}

async function loadLayers() {
  try {
    const res = await listLayers()
    layers.value = res.layers
  } catch (e) {
    console.warn('加载层级失败', e)
  }
}

onMounted(loadLayers)
</script>

<style scoped>
.tag-list {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 8px;
}

.form-hint {
  margin-left: 8px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
</style>
```

---

## Task 10：前端 - 集成到流水线创建页 + i18n

**Files:**
- Modify: `frontend/src/views/PipelineCreateView.vue`（或对应的流水线创建页）
- Modify: `frontend/src/i18n/zh-CN.ts`
- Modify: `frontend/src/i18n/en-US.ts`

- [ ] **Step 1: 先调研流水线创建页的现有风格选择实现**

Read 流水线创建页（用 Grep 搜索 `style_id` 或 `StylePreset`），了解：
- 现有风格选择器组件位置
- style_id 如何提交到 run inputs
- 在哪里插入 StyleElementPicker

- [ ] **Step 2: 集成风格选择器**

在创建页的风格选择区域，新增模式切换：

```vue
<!-- 风格选择 -->
<el-form-item label="风格">
  <el-radio-group v-model="styleMode" class="style-mode-radio">
    <el-radio-button value="preset">{{ t('pipeline.styleModePreset') }}</el-radio-button>
    <el-radio-button value="elements">{{ t('pipeline.styleModeElements') }}</el-radio-button>
  </el-radio-group>

  <!-- 路径 A：套装预设（保留现有 StylePreset 选择器） -->
  <div v-if="styleMode === 'preset'">
    <!-- 现有的 StylePreset 选择器组件 -->
  </div>

  <!-- 路径 B：分层组合（新增） -->
  <div v-else>
    <StyleElementPicker
      :base-prompt="basePrompt"
      @change="onStyleElementsChange"
    />
    <el-button
      type="primary"
      text
      size="small"
      @click="showElementEditor = true"
    >
      <el-icon><Plus /></el-icon>
      {{ t('styleElement.createCustom') }}
    </el-button>
    <StyleElementEditor
      v-model="showElementEditor"
      @created="onElementCreated"
    />
  </div>
</el-form-item>
```

在 script setup 中新增：

```typescript
import StyleElementPicker from '@/components/pipeline/StyleElementPicker.vue'
import StyleElementEditor from '@/components/pipeline/StyleElementEditor.vue'
import type { ResolvedElementItem } from '@/api/styleElement'

const styleMode = ref<'preset' | 'elements'>('preset')
const styleElements = ref<ResolvedElementItem[]>([])
const showElementEditor = ref(false)

function onStyleElementsChange(elements: ResolvedElementItem[]) {
  styleElements.value = elements
}

function onElementCreated() {
  // 创建成功后可刷新选择器（重新加载元素列表）
  // 通过 key 强制重载 StyleElementPicker
}

// 提交流水线时
function buildRunInputs() {
  const inputs = { ...baseInputs }
  if (styleMode.value === 'preset') {
    inputs.style_id = selectedStyleId.value
  } else {
    inputs.style_elements = styleElements.value
  }
  return inputs
}
```

- [ ] **Step 3: i18n 文案补充**

在 `zh-CN.ts` 新增：

```typescript
styleElement: {
  selectedCount: '已选 {count} 个风格元素',
  clearAll: '清空',
  promptPreview: 'Prompt 预览',
  finalPrompt: '最终 prompt',
  loading: '加载中...',
  noElements: '该层暂无元素',
  loadFailed: '加载失败',
  createCustom: '创建自定义风格',
  createTitle: '创建风格元素',
  name: '名称',
  namePlaceholder: '如：日系漫画',
  layer: '层级',
  layerPlaceholder: '选择层级',
  category: '细分类',
  categoryPlaceholder: '可选，如 anime',
  content: '提示词内容',
  contentPlaceholder: '如：manga style, japanese comic book art',
  negativeContent: '负面提示词',
  negativePlaceholder: '如：photorealistic, 3d render',
  weightDefault: '默认权重',
  tags: '标签',
  tagsPlaceholder: '输入标签后回车',
  isPublic: '是否公开',
  isPublicHint: '公开后其他用户可见',
  nameRequired: '请输入名称',
  layerRequired: '请选择层级',
  contentRequired: '请输入提示词内容',
  createSuccess: '创建成功',
  createFailed: '创建失败',
},
pipeline: {
  // ... 现有
  styleModePreset: '套装预设',
  styleModeElements: '分层组合',
},
```

在 `en-US.ts` 同步英文。

---

## Task 11：端到端验证

**Files:** 无代码改动

- [ ] **Step 1: 执行数据库迁移**

```bash
cd backend && alembic upgrade head
```

- [ ] **Step 2: 执行风格元素种子**

```bash
cd backend && python3 seed_style_elements.py
```

- [ ] **Step 3: 生成缩略图（可选，消耗 API 额度）**

```bash
cd backend && python3 generate_style_previews.py
```

- [ ] **Step 4: 启动后端 + 前端，验证**
  1. 流水线创建页风格选择器：可切换"套装预设"/"分层组合"模式
  2. 分层组合模式：6 个 Tab 正常显示，每个 Tab 下有元素卡片
  3. 点击卡片选中/取消，权重滑块可调
  4. 已选元素区显示 prompt 预览
  5. 创建自定义风格：表单提交成功后可在选择器看到新元素
  6. 创建流水线运行：选分层组合后，生成的图片风格符合所选元素组合

---

## Self-Review 检查

**Spec 覆盖：**
- ✅ 分层组合 + 权重 → Task 1（模型）+ Task 2（组合逻辑）+ Task 4（步骤执行器）+ Task 8（前端选择器）
- ✅ 用户自建 → Task 3（CRUD 路由）+ Task 9（前端表单）+ Task 10（集成）
- ✅ 风格/角色参考分离 → Task 4 Step 3（image_batch style_reference_image）
- ✅ 缩略图生成 → Task 5（seed）+ Task 6（generate_previews）
- ✅ 两路径共存 → Task 4 Step 2（engine 优先级）+ Task 10（前端模式切换）

**类型一致性：**
- StyleElement 模型（Task 1）与 schema（Task 3）字段一致
- ResolvedElementItem（Task 7 前端）与后端 [{element_id, weight}] 一致
- build_prompt_with_elements 签名（Task 2）与步骤执行器调用（Task 4）一致

**Agnes 模型能力边界：**
- ✅ 图片权重用 (keyword:weight) SD 语法
- ✅ 图片负面用 avoid: 拼接
- ✅ 视频负面用 negative_prompt 原生参数
- ✅ 风格参考图 + 角色参考图合并用 image_urls

---

## 执行选择

Plan 已保存到 `docs/superpowers/plans/2026-06-27-style-library-enhancement.md`。

**建议 Subagent-Driven 执行**（11 个 Task，多数独立可并行）：
- Task 1+2 可并行（模型 vs 服务，但 Task 2 依赖 Task 1 的 StyleElement 模型，需顺序）
- Task 3+5 可并行（schema/路由 vs 种子数据，都依赖 Task 1）
- Task 4 依赖 Task 1+2
- Task 6 依赖 Task 5
- Task 7-10 前端顺序依赖
- Task 11 最后验证

**选哪种执行方式？**
