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


def build_video_prompt_with_elements(
    base_prompt: str,
    resolved_elements: List[ResolvedStyleElement],
) -> Tuple[str, str]:
    """
    用分层风格元素组合构建视频 prompt（路径 B，视频专用）。

    与 build_prompt_with_elements 的差异：
    1. 不使用 (keyword:weight) SD 加权语法 —— 视频模型对权重的理解弱于图片模型，
       带括号权重的 prompt 容易触发 HTTP 400 "Unable to generate this content"
    2. 直接按层拼接 content（权重<1 的元素也直接拼接，不加权标记）
    3. negative_prompt 做精简：只保留画质类负面（low quality/blurry 等），
       去掉与画面风格冲突的负面（如"color"会与彩色 positive 矛盾）

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
    # 视频只收集画质类负面（避免风格类负面与 positive 矛盾导致 API 拒绝）
    quality_negative_keywords = {
        "low quality", "worst quality", "blurry", "simple", "low detail",
        "low resolution", "amateur", "low budget",
    }
    negative_parts: List[str] = []

    for layer_name in ALL_LAYERS:
        elements = layers.get(layer_name, [])
        if not elements:
            continue
        # 视频不加权，直接拼接 content
        contents = []
        for rse in elements:
            content = (rse.element.content or "").strip()
            if not content:
                continue
            contents.append(content)
            # 只收集画质类负面（避免风格冲突）
            neg = (rse.element.negative_content or "").strip()
            if neg:
                for n in neg.split(","):
                    n = n.strip().lower()
                    if n and n in quality_negative_keywords and n not in negative_parts:
                        negative_parts.append(n)
        if contents:
            parts.append(", ".join(contents))

    positive = ", ".join(parts)
    negative = ", ".join(negative_parts)
    return positive, negative


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
