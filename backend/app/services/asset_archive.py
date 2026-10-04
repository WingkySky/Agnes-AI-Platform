# =====================================================
# 创作内容资产入库服务（子批次 2a 影子转正）
# -------------------------------------------------
# 把生成结果自动入库进资产库（assets 表真资产行）：
#   - 画布 / 项目 / 独立生成的成功结果全部入库（不再只归档容器内生成）
#   - 容器信息（画布/剧本/项目）降级为来源筛选维度，保留在 container_* 字段
#   - work_id 由前端 context 携带（画布所属作品），素材跨作品复用走用户级资产库
#
# 调用时机：
#   1. 图片/视频 poller 落库成功后（ingest_generation_asset）
#   2. 项目合成成片写入 final_video_url 处（archive_final_video，项目域遗留）
#
# 容错约定：
#   所有入库入口内部 try/except 或由调用方兜住，失败仅记日志，绝不阻塞生成主流程。
#   漏掉的记录可在历史页通过「存为资产」手动补存（幂等）。
# =====================================================

import logging
from datetime import datetime
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


async def ingest_generation_asset(
    db: AsyncSession,
    generation: Generation,
    context: Optional[Dict[str, Any]] = None,
) -> Optional[Asset]:
    """
    生成结果统一入库（影子转正）：所有成功生成都建真资产行（含独立生成）。

    - 去重：按 source_generation_id 查重（poller 重试 / 手动补存安全），已存在返回 None
    - 存储：/uploads/ 直推导 storage_key；已 S3 迁移按 key 规则推导；
      上游未迁移 URL 用 media_storage.ingest_url 下载转存并回写 generation.result_url（根治死链）
    - work_id：画布生成由 context 携带（作品归属标记），其余为空

    本函数会 commit，调用方无需再提交；异常由调用方 try/except 兜住。
    """
    ctx = context or {}
    if generation.status != "success" or not generation.result_url:
        return None

    existing = (
        await db.scalars(
            select(Asset.id).where(Asset.source_generation_id == generation.id).limit(1)
        )
    ).first()
    if existing:
        logger.debug("[资产入库] 已入库，跳过: generation_id=%s", generation.id)
        return None

    kind = "video" if generation.type == "video" else "image"
    asset_type = ctx.get("asset_type") or _DEFAULT_TYPE_BY_GENERATION.get(generation.type, "material")
    if asset_type not in ARCHIVE_ASSET_TYPES:
        asset_type = _DEFAULT_TYPE_BY_GENERATION.get(generation.type, "material")

    url = generation.result_url
    storage_key: Optional[str] = None
    if url.startswith("/uploads/"):
        storage_key = url.removeprefix("/uploads/")
    elif getattr(generation, "migrate_status", None) == "migrated":
        # S3 转存 key 规则：generated/{type}/{yyyy-mm}/{record_id}.{ext}（asset_storage._build_object_key）
        ext = (url.rsplit(".", 1)[-1].split("?")[0] or "bin").lower()[:5]
        created = generation.created_at or datetime.utcnow()
        storage_key = f"generated/{kind}/{created.strftime('%Y-%m')}/{generation.id}.{ext}"
    elif url.startswith(("http://", "https://")):
        # 上游临时 URL：下载转存（失败保留原 URL，仅告警）
        try:
            from app.services.media_storage import ingest_url
            ingested = await ingest_url(url, folder="assets/generated", media_type=kind)
            url = ingested["url"]
            storage_key = ingested["storage_key"]
            generation.result_url = url
            await db.commit()
        except Exception as e:
            logger.warning(
                "[资产入库] 上游 URL 转存失败（保留原 URL）: generation_id=%s error=%s",
                generation.id, e,
            )

    asset = Asset(
        type=asset_type,
        name=(ctx.get("asset_name") or _fallback_name(generation))[:200],
        description=None,
        # visual_description 非空约束：入库记录直接用生成提示词兜底
        visual_description=generation.prompt or "",
        reference_images=[],
        user_id=generation.user_id,
        is_public=False,
        moderation_status="approved",
        tags=[],
        version=1,
        source="generation",
        storage_key=storage_key,
        work_id=ctx.get("work_id") if isinstance(ctx.get("work_id"), int) else None,
        # ===== 创作归属字段（来源/容器降级为筛选维度，保留用于历史分组） =====
        container_type=ctx.get("container_type"),
        container_id=str(ctx["container_id"]) if ctx.get("container_id") else None,
        container_name=ctx.get("container_name") or None,
        source_generation_id=generation.id,
        kind=kind,
        asset_url=url,
    )
    db.add(asset)
    await db.commit()
    await db.refresh(asset)

    logger.info(
        "[资产入库] generation_id=%s asset_id=%s work_id=%s type=%s kind=%s",
        generation.id, asset.id, asset.work_id, asset_type, kind,
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
