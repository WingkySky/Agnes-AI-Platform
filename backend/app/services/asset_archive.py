# =====================================================
# 创作内容归档服务
# -------------------------------------------------
# 把画布 / 项目里的生成结果自动归档进资产库（assets 表），
# 让历史页只保留独立生成，资产库成为创作产物的统一载体。
#
# 调用时机：
#   1. 图片/视频 poller 落库成功后（由 task.context 决定是否需要归档）
#   2. 项目合成成片写入 final_video_url 处（archive_final_video）
#
# 容错约定：
#   所有归档入口内部 try/except，失败仅记日志，绝不阻塞生成主流程。
#   归档漏掉的记录可在历史页通过「存为资产」手动补存。
# =====================================================

import logging
from typing import Any, Dict, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset import Asset
from app.models.generation import Generation

logger = logging.getLogger("agnes_platform")

# 资产类型：传统手动资产 + 创作归档产物
ARCHIVE_ASSET_TYPES = (
    "character",   # 角色
    "prop",        # 道具
    "scene",       # 场景
    "brand",       # 品牌
    "material",    # 素材图（含分镜图）
    "clip",        # 视频片段
    "final",       # 成片
)

# 创作容器类型
CONTAINER_PROJECT = "project"
CONTAINER_CANVAS_SCRIPT = "canvas_script"
CONTAINER_CANVAS = "canvas"

# 容器类型 → 展示徽标分类（前端渲染用）
CONTAINER_LABELS = {
    CONTAINER_PROJECT: "项目",
    CONTAINER_CANVAS_SCRIPT: "剧本",
    CONTAINER_CANVAS: "画布",
}

# 资产类型 → 默认归档产物类型（context 未指定时按生成类型推导）
_DEFAULT_TYPE_BY_GENERATION = {
    "image": "material",
    "video": "clip",
}


def _fallback_name(generation: Generation) -> str:
    """归档资产名兜底：取提示词前 50 字符"""
    prompt = (generation.prompt or "").strip().replace("\n", " ")
    if prompt:
        return prompt[:50]
    return f"素材 {generation.id}"


async def archive_to_asset(
    db: AsyncSession,
    generation: Generation,
    context: Optional[Dict[str, Any]] = None,
) -> Optional[Asset]:
    """
    把一条生成记录归档为资产库中的一条影子记录。

    归档条件（任一不满足则跳过，返回 None）：
      - context 带 container_type 与 container_id（独立生成不归档）
      - 生成成功且 result_url 非空（失败/取消不归档）

    去重：按 source_generation_id 查重，已归档直接跳过（poller 重试安全）。

    注意：本函数会 commit，调用方无需再提交；异常由调用方 try/except 兜住。
    """
    ctx = context or {}
    container_type = ctx.get("container_type")
    container_id = ctx.get("container_id")
    if not container_type or not container_id:
        return None
    if generation.status != "success" or not generation.result_url:
        return None

    existing = await db.execute(
        select(Asset.id).where(Asset.source_generation_id == generation.id).limit(1)
    )
    if existing.first():
        logger.debug(
            "[创作归档] 已归档，跳过: generation_id=%s", generation.id,
        )
        return None

    kind = "video" if generation.type == "video" else "image"
    asset_type = ctx.get("asset_type") or _DEFAULT_TYPE_BY_GENERATION.get(generation.type, "material")
    if asset_type not in ARCHIVE_ASSET_TYPES:
        asset_type = _DEFAULT_TYPE_BY_GENERATION.get(generation.type, "material")

    asset = Asset(
        type=asset_type,
        name=(ctx.get("asset_name") or _fallback_name(generation))[:200],
        description=None,
        # visual_description 非空约束：归档记录直接用生成提示词兜底
        visual_description=generation.prompt or "",
        reference_images=[],
        user_id=generation.user_id,
        is_public=False,
        moderation_status="approved",
        tags=[],
        version=1,
        # ===== 创作归档字段 =====
        container_type=container_type,
        container_id=str(container_id),
        container_name=(ctx.get("container_name") or None),
        source_generation_id=generation.id,
        kind=kind,
        asset_url=generation.result_url,
    )
    db.add(asset)
    await db.commit()
    await db.refresh(asset)

    logger.info(
        "[创作归档] 已归档: generation_id=%s asset_id=%s container=%s:%s type=%s",
        generation.id, asset.id, container_type, container_id, asset_type,
    )
    return asset


async def archive_final_video(
    db: AsyncSession,
    project_id: int,
    project_name: str,
    user_id: Optional[int],
    final_video_url: str,
) -> Optional[Asset]:
    """
    项目合成成片归档：一个项目只保留一条 type=final 记录，重复合成时覆盖 URL。

    成片不经过 generations（没有对应的单次生成记录），因此按容器 + 类型去重，
    而非按 source_generation_id。
    """
    if not final_video_url:
        return None

    container_id = str(project_id)
    result = await db.execute(
        select(Asset).where(
            Asset.container_type == CONTAINER_PROJECT,
            Asset.container_id == container_id,
            Asset.type == "final",
        ).limit(1)
    )
    asset = result.scalar_one_or_none()

    if asset:
        asset.asset_url = final_video_url
        asset.container_name = project_name
        await db.commit()
        await db.refresh(asset)
        logger.info(
            "[创作归档] 成片已更新: project_id=%s asset_id=%s", project_id, asset.id,
        )
        return asset

    asset = Asset(
        type="final",
        name=f"{project_name} 成片"[:200],
        description=None,
        visual_description=f"项目《{project_name}》合成成片",
        reference_images=[],
        user_id=user_id,
        is_public=False,
        moderation_status="approved",
        tags=[],
        version=1,
        container_type=CONTAINER_PROJECT,
        container_id=container_id,
        container_name=project_name,
        source_generation_id=None,
        kind="video",
        asset_url=final_video_url,
    )
    db.add(asset)
    await db.commit()
    await db.refresh(asset)

    logger.info(
        "[创作归档] 成片已归档: project_id=%s asset_id=%s", project_id, asset.id,
    )
    return asset
