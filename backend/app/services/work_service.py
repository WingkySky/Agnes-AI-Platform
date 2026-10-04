# =====================================================
# 作品（轻容器）服务：CRUD 与归属校验
# 查询统一 db.scalars(select(...)) 写法（项目惯例）
# =====================================================

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.canvas_workspace import CanvasWorkspace
from app.models.work import Work


async def list_works(db: AsyncSession, user_id: int) -> list[Work]:
    """本人作品列表（updated_at 倒序）"""
    return list(
        (
            await db.scalars(
                select(Work)
                .where(Work.user_id == user_id)
                .order_by(Work.updated_at.desc())
            )
        ).all()
    )


async def get_work(db: AsyncSession, work_id: int, user_id: int) -> Work | None:
    """取本人作品；不存在或非本人返回 None（路由层区分 404/403 需二次查询时不用此函数）"""
    return (
        await db.scalars(
            select(Work).where(Work.id == work_id, Work.user_id == user_id)
        )
    ).first()


async def get_work_owned(db: AsyncSession, work_id: int, user_id: int) -> tuple[Work | None, bool]:
    """返回 (作品, 是否存在)；存在但非本人时 is_owner=False（路由层转 403）"""
    work = (
        await db.scalars(select(Work).where(Work.id == work_id))
    ).first()
    if work is None:
        return None, False
    return work, work.user_id == user_id


async def create_work(
    db: AsyncSession, user_id: int, title: str,
    description: str | None = None, cover_url: str | None = None,
) -> Work:
    work = Work(user_id=user_id, title=title, description=description, cover_url=cover_url)
    db.add(work)
    await db.commit()
    await db.refresh(work)
    return work


async def update_work(
    db: AsyncSession, work: Work,
    title: str | None = None, description: str | None = None, cover_url: str | None = None,
) -> Work:
    if title is not None:
        work.title = title
    if description is not None:
        work.description = description
    if cover_url is not None:
        work.cover_url = cover_url
    await db.commit()
    await db.refresh(work)
    return work


async def delete_work(db: AsyncSession, work: Work) -> None:
    """删除作品并解绑名下画布（work_id 置空，画布本体保留为自由画布）"""
    canvases = (
        await db.scalars(select(CanvasWorkspace).where(CanvasWorkspace.work_id == work.id))
    ).all()
    for canvas in canvases:
        canvas.work_id = None
    await db.delete(work)
    await db.commit()


async def maybe_auto_fill_cover(db: AsyncSession, work_id: int, workspace_data: dict) -> None:
    """
    作品封面自动回填（首图即封面，行业共识默认）：
    画布保存时取该画布第一个图片节点的 URL；仅 cover_url 为空时回填，手动设置后不再覆盖。
    best-effort：任何异常不阻塞画布保存主流程。
    """
    try:
        panels = (workspace_data or {}).get("panels")
        if not isinstance(panels, list):
            return
        cover = None
        for panel in panels:
            if not isinstance(panel, dict) or panel.get("type") != "image":
                continue
            content = panel.get("content")
            url = content.get("content") if isinstance(content, dict) else None
            if isinstance(url, str) and url:
                cover = url
                break
        if not cover:
            return
        work = (await db.scalars(select(Work).where(Work.id == work_id))).first()
        if work and not work.cover_url:
            work.cover_url = cover
            await db.commit()
    except Exception:  # noqa: BLE001 — 封面回填失败不影响保存
        return
