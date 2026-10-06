# =====================================================
# 作品实体库服务：实体/版本 CRUD、采用切换、产图自动入版本
# 查询统一 db.scalars(select(...)) 写法（项目惯例）
# =====================================================

import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset import Asset
from app.models.work import Work
from app.models.work_entity import IMAGE_ROLES, WorkEntity, WorkEntityVersion

logger = logging.getLogger("agnes_platform")


async def get_entity_owned(
    db: AsyncSession, entity_id: int, user_id: int
) -> tuple[Optional[WorkEntity], Optional[Work], bool]:
    """返回 (实体, 所属作品, 是否本人)；实体不存在时前两值为 None（路由层转 404）"""
    entity = (
        await db.scalars(select(WorkEntity).where(WorkEntity.id == entity_id))
    ).first()
    if entity is None:
        return None, None, False
    work = (
        await db.scalars(select(Work).where(Work.id == entity.work_id))
    ).first()
    return entity, work, work is not None and work.user_id == user_id


async def list_entity_dicts(
    db: AsyncSession, work_id: int, kind: Optional[str] = None
) -> list[dict]:
    """作品实体列表（含版本列表 + 采用图 url），按更新时间倒序"""
    query = select(WorkEntity).where(WorkEntity.work_id == work_id)
    if kind:
        query = query.where(WorkEntity.kind == kind)
    entities = list((await db.scalars(query.order_by(WorkEntity.updated_at.desc()))).all())
    if not entities:
        return []

    entity_ids = [e.id for e in entities]
    versions = list(
        (
            await db.scalars(
                select(WorkEntityVersion)
                .where(WorkEntityVersion.entity_id.in_(entity_ids))
                .order_by(WorkEntityVersion.created_at.asc(), WorkEntityVersion.id.asc())
            )
        ).all()
    )
    versions_by_entity: dict[int, list[WorkEntityVersion]] = {}
    for v in versions:
        versions_by_entity.setdefault(v.entity_id, []).append(v)

    asset_ids = {
        img["asset_id"]
        for v in versions for img in (v.images or [])
        if isinstance(img, dict) and isinstance(img.get("asset_id"), int)
    }
    url_map: dict[int, Optional[str]] = {}
    if asset_ids:
        assets = (
            await db.scalars(select(Asset).where(Asset.id.in_(asset_ids)))
        ).all()
        url_map = {a.id: a.asset_url for a in assets}

    return [
        _entity_dict(e, versions_by_entity.get(e.id, []), url_map) for e in entities
    ]


def _entity_dict(
    entity: WorkEntity,
    versions: list[WorkEntityVersion],
    url_map: dict[int, Optional[str]],
) -> dict:
    version_dicts = [
        {
            "id": v.id,
            "images": [
                {
                    "asset_id": img["asset_id"],
                    "role": img.get("role", "design"),
                    "url": url_map.get(img["asset_id"]),
                }
                for img in (v.images or [])
                if isinstance(img, dict) and isinstance(img.get("asset_id"), int)
            ],
            "is_active": v.is_active,
            "created_at": v.created_at,
        }
        for v in versions
    ]
    active_url = next(
        (
            img["url"]
            for vd in version_dicts if vd["is_active"]
            for img in vd["images"] if img["role"] == "design"
        ),
        None,
    )
    # 采用版本无 design 表现图时兜底取任意一张
    if active_url is None:
        active_url = next(
            (
                img["url"]
                for vd in version_dicts if vd["is_active"]
                for img in vd["images"]
            ),
            None,
        )
    return {
        "id": entity.id,
        "work_id": entity.work_id,
        "kind": entity.kind,
        "name": entity.name,
        "description": entity.description,
        "versions": version_dicts,
        "active_image_url": active_url,
        "created_at": entity.created_at,
        "updated_at": entity.updated_at,
    }


async def find_by_name(
    db: AsyncSession, work_id: int, kind: str, name: str
) -> Optional[WorkEntity]:
    """按作品+类型+名称查实体（向导/Agent 落卡按名 upsert 用）"""
    return (
        await db.scalars(
            select(WorkEntity).where(
                WorkEntity.work_id == work_id,
                WorkEntity.kind == kind,
                WorkEntity.name == name,
            )
        )
    ).first()


async def asset_owned(db: AsyncSession, asset_id: int, user_id: int) -> bool:
    """表现图引用的资产必须存在且属于本人"""
    asset = (
        await db.scalars(select(Asset).where(Asset.id == asset_id))
    ).first()
    return asset is not None and asset.user_id == user_id


async def create_entity(
    db: AsyncSession, work_id: int, kind: str, name: str,
    description: Optional[str] = None, asset_id: Optional[int] = None,
) -> dict:
    entity = WorkEntity(work_id=work_id, kind=kind, name=name, description=description)
    db.add(entity)
    await db.flush()
    first_version = None
    if asset_id:
        first_version = WorkEntityVersion(
            entity_id=entity.id, images=[{"asset_id": asset_id, "role": "design"}], is_active=True,
        )
        db.add(first_version)
    await db.commit()
    await db.refresh(entity)
    versions = [first_version] if first_version else []
    return _entity_dict(entity, versions, {asset_id: await _asset_url(db, asset_id)} if asset_id else {})


async def _asset_url(db: AsyncSession, asset_id: Optional[int]) -> Optional[str]:
    if not asset_id:
        return None
    return (
        await db.scalars(select(Asset.asset_url).where(Asset.id == asset_id))
    ).first()


async def update_entity(
    db: AsyncSession, entity: WorkEntity,
    name: Optional[str] = None, description: Optional[str] = None,
) -> None:
    if name is not None:
        entity.name = name
    if description is not None:
        entity.description = description
    await db.commit()
    await db.refresh(entity)


async def delete_entity(db: AsyncSession, entity: WorkEntity) -> None:
    """删实体（versions 级联删除；不动资产，挂链卡片由前端脱钩保留当前图）"""
    await db.delete(entity)
    await db.commit()


async def _active_version(db: AsyncSession, entity_id: int) -> Optional[WorkEntityVersion]:
    return (
        await db.scalars(
            select(WorkEntityVersion)
            .where(WorkEntityVersion.entity_id == entity_id, WorkEntityVersion.is_active.is_(True))
            .order_by(WorkEntityVersion.created_at.desc(), WorkEntityVersion.id.desc())
        )
    ).first()


async def add_version(
    db: AsyncSession, entity: WorkEntity, asset_id: int, role: str = "design",
    source_generation_id: Optional[int] = None,
) -> WorkEntityVersion:
    """
    新增表现图：
    - role=design：新开版本并自动采用（旧版本保留可回切）
    - role=angle/turnaround：追加进当前采用版本 images（不新开版本）；
      无采用版本时落为首版本并采用
    """
    if role in ("angle", "turnaround"):
        active = await _active_version(db, entity.id)
        if active:
            images = list(active.images or [])
            images.append({"asset_id": asset_id, "role": role})
            active.images = images  # JSON 整体替换赋值触发变更检测
            active.source_generation_id = source_generation_id or active.source_generation_id
            await db.commit()
            await db.refresh(active)
            return active
    versions = (
        await db.scalars(select(WorkEntityVersion).where(WorkEntityVersion.entity_id == entity.id))
    ).all()
    for v in versions:
        v.is_active = False
    version = WorkEntityVersion(
        entity_id=entity.id,
        images=[{"asset_id": asset_id, "role": role if role in IMAGE_ROLES else "design"}],
        source_generation_id=source_generation_id,
        is_active=True,
    )
    db.add(version)
    await db.commit()
    await db.refresh(version)
    return version


async def adopt_version(db: AsyncSession, entity: WorkEntity, version_id: int) -> bool:
    """切换采用版本；version_id 不属于该实体返回 False"""
    versions = (
        await db.scalars(select(WorkEntityVersion).where(WorkEntityVersion.entity_id == entity.id))
    ).all()
    if not any(v.id == version_id for v in versions):
        return False
    for v in versions:
        v.is_active = v.id == version_id
    await db.commit()
    return True


async def add_version_from_generation(
    db: AsyncSession, entity_id: int, asset_id: int,
    source_generation_id: Optional[int], role: Optional[str] = None,
    work_id: Optional[int] = None,
) -> Optional[WorkEntityVersion]:
    """
    产图自动入版本钩子（persist_generation 成功后调用，best-effort）：
    work_id 不匹配（生成上下文与实体归属作品不一致）时拒绝，防串库。
    """
    entity = (
        await db.scalars(select(WorkEntity).where(WorkEntity.id == entity_id))
    ).first()
    if entity is None:
        return None
    if work_id is not None and entity.work_id != work_id:
        logger.warning(
            "[实体版本] 生成上下文与实体作品不一致，跳过: entity_id=%s entity_work=%s ctx_work=%s",
            entity_id, entity.work_id, work_id,
        )
        return None
    return await add_version(
        db, entity, asset_id,
        role if role in IMAGE_ROLES else "design",
        source_generation_id,
    )
