# =====================================================
# 资产库服务
# =====================================================

from typing import Optional

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import load_only

from app.models.asset import Asset
from app.models.generation import Generation
from app.schemas.assets import AssetSaveFromGenerationRequest
from app.services.asset_archive import ingest_generation_asset

# 允许的资产类型
VALID_ASSET_TYPES = {"character", "prop", "scene", "brand", "material", "clip", "final"}


async def get_asset_by_id(db: AsyncSession, asset_id: int) -> Optional[Asset]:
    """根据 ID 获取资产"""
    result = await db.execute(select(Asset).filter(Asset.id == asset_id))
    return result.scalar_one_or_none()


async def save_asset_from_generation(
    db: AsyncSession,
    data: AssetSaveFromGenerationRequest,
    user_id: int,
) -> Asset:
    """从生成记录保存为资产"""
    if data.type not in VALID_ASSET_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"无效的资产类型: {data.type}",
        )

    gen_result = await db.execute(
        select(Generation).filter(
            Generation.id == data.generation_id,
            Generation.user_id == user_id,
        )
    )
    generation = gen_result.scalar_one_or_none()
    if not generation:
        raise HTTPException(status_code=404, detail="生成记录不存在")

    # 幂等：同一生成记录只保存一份资产（已自动归档或已手动保存时直接返回已有记录）
    existing = (await db.execute(
        select(Asset).filter(
            Asset.source_generation_id == generation.id,
            Asset.user_id == user_id,
        ).limit(1)
    )).scalar_one_or_none()
    if existing:
        return existing

    visual_desc = data.visual_description or generation.prompt
    ref_images = [generation.result_url] if generation.result_url else []

    asset = Asset(
        type=data.type,
        name=data.name,
        description=data.description,
        visual_description=visual_desc,
        reference_images=ref_images,
        style_id=data.style_id,
        user_id=user_id,
        is_public=False,
        tags=data.tags,
        version=1,
        source_generation_id=generation.id,
        kind="video" if generation.type == "video" else "image",
        asset_url=generation.result_url,
    )
    db.add(asset)
    await db.commit()
    await db.refresh(asset)
    return asset


async def delete_asset(
    db: AsyncSession,
    asset_id: int,
    user_id: Optional[int] = None,
    is_admin: bool = False,
) -> None:
    """删除资产"""
    asset = await get_asset_by_id(db, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="资产不存在")

    if not is_admin and asset.user_id != user_id:
        raise HTTPException(status_code=403, detail="无权删除此资产")

    await db.delete(asset)
    await db.commit()


async def increment_use_count(db: AsyncSession, asset_id: int) -> None:
    """增加使用次数"""
    asset = await get_asset_by_id(db, asset_id)
    if asset:
        asset.use_count += 1
        await db.commit()


# =====================================================
# 统一资产层（子批次 2a）：画布素材入库 + 资产列表筛选
# =====================================================

VALID_MEDIA_TYPES = {"image", "video", "audio"}


def asset_to_dict(asset: Asset) -> dict:
    """资产行 → 列表/详情响应 dict（统一资产层字段）"""
    return {
        "id": asset.id,
        "type": asset.type,
        "name": asset.name,
        "description": asset.description,
        "visual_description": asset.visual_description,
        "reference_images": asset.reference_images or [],
        "media_type": asset.kind,
        "asset_url": asset.asset_url,
        "thumb_url": asset.thumb_url,
        "storage_key": asset.storage_key,
        "source": asset.source,
        "work_id": asset.work_id,
        "is_public": asset.is_public,
        "moderation_status": asset.moderation_status,
        "use_count": asset.use_count,
        "container_type": asset.container_type,
        "container_id": asset.container_id,
        "container_name": asset.container_name,
        "created_at": asset.created_at.isoformat() if asset.created_at else None,
        "updated_at": asset.updated_at.isoformat() if asset.updated_at else None,
    }


async def create_asset_from_upload(
    db: AsyncSession,
    *,
    user_id: int,
    url: str,
    media_type: str,
    name: Optional[str] = None,
    work_id: Optional[int] = None,
) -> Asset:
    """
    画布/上传素材建统一资产行（画布素材 uid 退役的入库通道）。

    - url 必须是 /uploads/ 本地地址（前端先经 /api/uploads/canvas 上传）
      或公网 http(s) 地址（远程地址入库即下载转存，根治死链）
    - work_id 需归属当前用户（作品标记），非本人 403
    """
    if media_type not in VALID_MEDIA_TYPES:
        raise HTTPException(status_code=400, detail=f"不支持的媒体类型：{media_type}")

    if work_id is not None:
        from app.models.work import Work
        owned = (
            await db.scalars(
                select(Work.id).where(Work.id == work_id, Work.user_id == user_id)
            )
        ).first()
        if not owned:
            raise HTTPException(status_code=403, detail="无权挂靠该作品")

    storage_key: Optional[str] = None
    final_url = url
    if url.startswith("/uploads/"):
        storage_key = url.removeprefix("/uploads/")
    elif url.startswith(("http://", "https://")):
        from app.services.media_storage import ingest_url
        try:
            ingested = await ingest_url(url, media_type=media_type)
            final_url, storage_key = ingested["url"], ingested["storage_key"]
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"素材地址收口失败：{e}")
    else:
        raise HTTPException(status_code=400, detail="素材地址必须是 /uploads/ 本地路径或公网 http(s) URL")

    asset_type = "clip" if media_type == "video" else "material"
    asset = Asset(
        type=asset_type,
        name=(name or f"素材 {media_type}")[:200],
        description=None,
        visual_description=(name or "")[:500],
        reference_images=[],
        user_id=user_id,
        is_public=False,
        tags=[],
        version=1,
        source="upload",
        storage_key=storage_key,
        work_id=work_id,
        kind=media_type,
        asset_url=final_url,
    )
    db.add(asset)
    await db.commit()
    await db.refresh(asset)
    return asset


async def list_assets(
    db: AsyncSession,
    *,
    user_id: int,
    media_type: Optional[str] = None,
    source: Optional[str] = None,
    work_id: Optional[int] = None,
    asset_type: Optional[str] = None,
    keyword: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
) -> dict:
    """本人资产列表（统一入口：分页 + 类型/来源/作品/分类/关键词筛选，updated_at 倒序）"""
    stmt = select(Asset).where(Asset.user_id == user_id)
    if media_type:
        stmt = stmt.where(Asset.kind == media_type)
    if source:
        stmt = stmt.where(Asset.source == source)
    if work_id is not None:
        stmt = stmt.where(Asset.work_id == work_id)
    if asset_type:
        stmt = stmt.where(Asset.type == asset_type)
    if keyword:
        pattern = f"%{keyword}%"
        stmt = stmt.where(
            or_(
                Asset.name.ilike(pattern),
                Asset.description.ilike(pattern),
                Asset.visual_description.ilike(pattern),
            )
        )
    total = (
        await db.scalars(select(func.count()).select_from(stmt.subquery()))
    ).first() or 0
    rows = (
        await db.scalars(
            stmt.order_by(Asset.updated_at.desc()).offset((page - 1) * page_size).limit(page_size)
        )
    ).all()

    # 生成模式回填（卡片徽标：文生图/图生视频…），按 source_generation_id 从来源生成记录批量取
    gen_ids = [a.source_generation_id for a in rows if a.source_generation_id]
    mode_map: dict = {}
    if gen_ids:
        gen_rows = (
            await db.scalars(
                select(Generation)
                .options(load_only(Generation.id, Generation.mode))
                .where(or_(Generation.id == i for i in gen_ids))
            )
        ).all()
        mode_map = {g.id: g.mode for g in gen_rows}

    items = []
    for a in rows:
        d = asset_to_dict(a)
        d["mode"] = mode_map.get(a.source_generation_id)
        items.append(d)
    return {
        "total": int(total),
        "page": page,
        "page_size": page_size,
        "items": items,
    }


async def backfill_asset_storage(db: AsyncSession, *, limit: int = 200) -> dict:
    """
    存量资产补课（一次性；管理员触发）：
    - kind（media_type）为空：按 type 推导（clip/final → video，其余 → image）
    - storage_key 为空：/uploads/ 本地地址直推导；上游 http(s) URL 下载转存（失败跳过留待重试）
    返回 {processed, migrated, remaining}。幂等：只处理 storage_key 为空的行。
    """
    rows = (
        await db.scalars(
            select(Asset)
            .where(Asset.storage_key.is_(None))
            .order_by(Asset.id.asc())
            .limit(limit)
        )
    ).all()
    migrated = 0
    for asset in rows:
        if not asset.kind:
            asset.kind = "video" if asset.type in ("clip", "final") else "image"
        url = asset.asset_url
        if url and url.startswith("/uploads/"):
            asset.storage_key = url.removeprefix("/uploads/")
        elif url and url.startswith("data:"):
            # b64 兜底图：解码为真实文件入库（消除巨型 data URI）
            try:
                from app.services.media_storage import save_media
                header, _, payload = url.partition(",")
                mime = header[5:].split(";")[0] or "image/png"
                import base64
                data = base64.b64decode(payload)
                result = await save_media(
                    data, ext=mime.split("/")[-1], media_type=asset.kind or "image",
                )
                asset.asset_url = result["url"]
                asset.storage_key = result["storage_key"]
                migrated += 1
            except Exception:  # noqa: BLE001 — 解码失败标记已处理，不阻塞整体
                asset.storage_key = ""
        elif url and url.startswith(("http://", "https://")):
            try:
                from app.services.media_storage import ingest_url
                ingested = await ingest_url(url, media_type=asset.kind or "image")
                asset.asset_url = ingested["url"]
                asset.storage_key = ingested["storage_key"]
                migrated += 1
            except Exception:  # noqa: BLE001 — 上游链接已死（过期 404 等）：保留原 URL，置空串标记已处理防死循环
                asset.storage_key = ""
        else:
            # 空/未知协议地址：无文件键可派生，置空串标记已处理（避免每轮重复捞取）
            asset.storage_key = ""
    await db.commit()
    remaining = (
        await db.scalars(
            select(func.count()).select_from(Asset).where(Asset.storage_key.is_(None))
        )
    ).first() or 0
    return {"processed": len(rows), "migrated": migrated, "remaining": int(remaining)}


async def backfill_generations_to_assets(db: AsyncSession, *, limit: int = 200) -> dict:
    """
    存量生成记录补入库（一次性；管理员触发）：
    成功且有结果 URL 的历史 generation 若还没有对应资产行（影子转正上线前的旧记录），
    逐条走 ingest_generation_asset 建真资产行（幂等，按 source_generation_id 去重）。
    容器信息从 generation 行透传；work_id 无法回溯置空。
    返回 {processed, created, remaining}。
    """
    gen_ids = (
        await db.scalars(
            select(Generation.id)
            .where(
                Generation.status == "success",
                Generation.result_url.is_not(None),
                Generation.result_url != "",
                ~select(Asset.id).where(Asset.source_generation_id == Generation.id).exists(),
            )
            .order_by(Generation.id.desc())
            .limit(limit)
        )
    ).all()
    processed = 0
    created = 0
    for gid in gen_ids:
        gen = (
            await db.scalars(select(Generation).where(Generation.id == gid))
        ).first()
        if not gen:
            continue
        try:
            asset = await ingest_generation_asset(db, gen, {
                "container_type": gen.container_type,
                "container_id": gen.container_id,
            })
            processed += 1
            if asset:
                created += 1
        except Exception:  # noqa: BLE001 — 单条失败留待下次重试
            continue
        if processed >= limit:
            break
    remaining = (
        await db.scalars(
            select(func.count()).select_from(Generation).where(
                Generation.status == "success",
                Generation.result_url.is_not(None),
                Generation.result_url != "",
                ~select(Asset.id).where(Asset.source_generation_id == Generation.id).exists(),
            )
        )
    ).first() or 0
    return {"processed": processed, "created": created, "remaining": int(remaining)}
