# =====================================================
# 统一资产路由（/api/assets，登录级）
#
# - POST /api/assets             画布/上传素材建统一资产行（画布素材 uid 退役入库通道）
# - GET  /api/assets             本人资产列表（分页 + media_type/source/work_id/keyword 筛选）
# - GET  /api/assets/{asset_id}  本人资产详情
# - PATCH /api/assets/{asset_id} 编辑资产元数据（name/type/description/visual_description）
# - PATCH /api/assets/batch-share    批量设置分享状态（复用审核管道）
# - POST  /api/assets/batch-delete   批量删除资产
# - GET   /api/assets/batch-download 批量下载（打包 zip）
#
# 语义：素材生命周期归资产层；画布节点/剪辑片段只持有 asset_id 引用。
# =====================================================

import asyncio
import io
import logging
import zipfile
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response as FastAPIResponse
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_db
from app.core.response import ok
from app.core.security import get_current_user
from app.models.asset import Asset
from app.models.work import Work
from app.models.asset_like import AssetLike
from app.models.user import User
from app.schemas.assets import ASSET_TYPE_CHOICES, AssetUpdateRequest
from app.services import asset_library
from app.services.upload_service import UPLOADS_DIR

logger = logging.getLogger("agnes_platform")

router = APIRouter(prefix="/assets", tags=["资产库"], dependencies=[Depends(get_current_user)])


class AssetCreateRequest(BaseModel):
    """画布/上传素材建资产行请求体"""
    url: str = Field(..., min_length=1, description="素材地址（/uploads/ 本地路径或公网 http(s) URL）")
    media_type: str = Field(..., description="image / video / audio")
    name: Optional[str] = Field(None, max_length=200, description="素材名")
    work_id: Optional[int] = Field(None, description="所属作品标记（需归属当前用户）")


@router.post("", summary="创建素材资产（画布素材入库通道）")
async def create_asset(
    payload: AssetCreateRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    asset = await asset_library.create_asset_from_upload(
        db,
        user_id=current_user.id,
        url=payload.url,
        media_type=payload.media_type,
        name=payload.name,
        work_id=payload.work_id,
    )
    return ok(data=asset_library.asset_to_dict(asset))


@router.get("", summary="本人资产列表（统一入口）")
async def list_assets(
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
    media_type: Optional[str] = Query(None, description="image / video / audio"),
    source: Optional[str] = Query(None, description="generation / upload / canvas / compose / archive"),
    work_id: Optional[int] = Query(None, description="按所属作品筛选"),
    type: Optional[str] = Query(None, description="资产分类筛选：character / prop / scene / brand / material / clip / final"),
    keyword: Optional[str] = Query(None, max_length=100, description="关键词（匹配名称/描述/视觉描述）"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    data = await asset_library.list_assets(
        db,
        user_id=current_user.id,
        media_type=media_type,
        source=source,
        work_id=work_id,
        asset_type=type,
        keyword=keyword,
        page=page,
        page_size=page_size,
    )
    return ok(data=data)


@router.post("/backfill", summary="存量补课（资产行字段回填 + 历史生成批量入库；仅管理员）")
async def backfill_assets(
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
    limit: int = Query(200, ge=1, le=1000, description="每阶段单次处理上限"),
):
    """两阶段一次性补课，幂等可重复调用：
    ①资产行补 storage_key/media_type（上游 URL 转存）；
    ②历史成功生成批量入库（影子转正上线前的旧记录建真资产行）"""
    if not current_user.is_admin and current_user.role not in ("admin", "moderator"):
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="仅管理员/审核员可访问")
    rows = await asset_library.backfill_asset_storage(db, limit=limit)
    generations = await asset_library.backfill_generations_to_assets(db, limit=limit)
    return ok(data={"rows": rows, "generations": generations})


# =====================================================
# 批量操作（对齐历史记录页的批量处理能力）
# =====================================================

class AssetBatchShareRequest(BaseModel):
    """资产批量设置分享状态请求体"""
    ids: List[int] = Field(..., description="资产 ID 列表")
    is_public: bool = Field(..., description="true=公开（进入审核），false=私有")


class AssetBatchDeleteRequest(BaseModel):
    """资产批量删除请求体"""
    ids: List[int] = Field(..., description="资产 ID 列表")


# URL 后缀 → 扩展名嗅探规则
_ASSET_URL_EXT_RULES: Tuple[Tuple[str, str], ...] = (
    (".png", ".png"), (".jpg", ".jpg"), (".jpeg", ".jpg"), (".webp", ".webp"),
    (".gif", ".gif"), (".mp4", ".mp4"), (".webm", ".webm"), (".mp3", ".mp3"),
    (".wav", ".wav"), (".m4a", ".m4a"),
)


def _asset_file_ext(url: str) -> str:
    """从 URL/存储键路径中提取文件扩展名，未命中返回空串（调用方按媒体类型兜底）"""
    path = urlparse(url).path.lower()
    for suffix, ext in _ASSET_URL_EXT_RULES:
        if path.endswith(suffix):
            return ext
    return ""


@router.patch("/batch-share", summary="批量设置分享状态（复用审核管道）")
async def batch_share_assets(
    body: AssetBatchShareRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """
    批量设置资产的公开/私有状态（按用户隔离，不属于自己的 ID 计入 failed_ids）。
    设为公开时进入待审核（pending），先做敏感词快速筛查，再异步触发 AI 内容审核；
    被管理员屏蔽（rejected）的资产跳过，不可再次公开。
    """
    ids = list(set(body.ids or []))
    if not ids:
        raise HTTPException(status_code=400, detail="请提供至少一个资产 ID")

    rows = (
        await db.scalars(
            select(Asset).where(or_(Asset.id == i for i in ids), Asset.user_id == current_user.id)
        )
    ).all()

    now = datetime.utcnow()
    updated_ids: List[int] = []
    newly_public: List[Asset] = []
    for asset in rows:
        # 被管理员屏蔽的资产不可再次公开
        if body.is_public and asset.moderation_status == "rejected":
            continue
        was_public = asset.is_public
        asset.is_public = body.is_public
        if body.is_public and not was_public and not asset.public_shared_at:
            asset.public_shared_at = now
        if body.is_public and not was_public:
            asset.moderation_status = "pending"
            asset.moderation_reason = "审核中：等待系统预审"
            try:
                from app.services.moderation_service import check_sensitive_text
                hit, hit_words = await check_sensitive_text(
                    db, f"{asset.name or ''} {asset.description or ''}"
                )
                if hit:
                    asset.moderation_reason = (
                        f"审核中：文本命中敏感词（{', '.join(hit_words[:3])}），等待内容审核"
                    )
            except Exception as mod_err:  # noqa: BLE001 — 预检失败不阻塞分享
                logger.warning("[资产] 批量分享敏感词检测失败 id=%d: %s", asset.id, mod_err)
            newly_public.append(asset)
        updated_ids.append(asset.id)

    await db.commit()

    # 异步触发 AI 内容审核（不阻塞接口响应）
    for asset in newly_public:
        gen_type = "video" if (asset.kind == "video" or asset.type in ("clip", "final")) else "image"
        result_url = asset.asset_url or (asset.reference_images[0] if asset.reference_images else None)
        try:
            from app.services.moderation_service import run_async_asset_moderation
            asyncio.create_task(run_async_asset_moderation(asset.id, gen_type, result_url, asset.name))
        except Exception as task_err:  # noqa: BLE001 — 审核任务启动失败不影响主流程
            logger.warning("[资产] 启动 AI 异步审核失败 id=%d: %s", asset.id, task_err)

    failed_ids = [rid for rid in ids if rid not in updated_ids]
    msg = (
        f"已提交 {len(updated_ids)} 条资产分享，正在审核中，审核通过后将展示到广场"
        if body.is_public
        else f"已将 {len(updated_ids)} 条资产设为仅自己可见"
    )
    logger.info("[资产] 用户 %s 批量切换 %d 条资产分享状态: %s", current_user.id, len(updated_ids), body.is_public)
    return ok(data={"updated_count": len(updated_ids), "failed_ids": failed_ids}, message=msg)


@router.post("/batch-delete", summary="批量删除资产")
async def batch_delete_assets(
    body: AssetBatchDeleteRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """
    按 ID 列表批量删除资产（按用户隔离，不属于自己的 ID 计入 failed_ids）。
    归档影子记录（container 非空）仅删除资产库影子记录，不影响画布/项目本体。
    """
    ids = list(set(body.ids or []))
    if not ids:
        raise HTTPException(status_code=400, detail="请提供至少一个资产 ID")

    rows = (
        await db.scalars(
            select(Asset).where(or_(Asset.id == i for i in ids), Asset.user_id == current_user.id)
        )
    ).all()

    deleted_ids = [a.id for a in rows]
    if deleted_ids:
        # 清理点赞关系（SQLite 未启用外键 CASCADE，防孤儿行）；逐条 ORM 删除
        like_rows = (
            await db.scalars(
                select(AssetLike).where(or_(AssetLike.asset_id == i for i in deleted_ids))
            )
        ).all()
        for like in like_rows:
            await db.delete(like)
        for asset in rows:
            await db.delete(asset)
        await db.commit()

    failed_ids = [rid for rid in ids if rid not in deleted_ids]
    logger.info("[资产] 用户 %s 批量删除 %d 条资产", current_user.id, len(deleted_ids))
    return ok(
        data={"deleted_count": len(deleted_ids), "failed_ids": failed_ids},
        message=f"已删除 {len(deleted_ids)} 条资产",
    )


@router.get("/batch-download", summary="批量下载资产（打包 zip）")
async def batch_download_assets(
    ids: str = Query(..., description="资产 ID 列表，逗号分隔"),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """将多个资产文件打包为 zip 下载（按用户隔离）。/uploads/ 本地文件直读磁盘，远程地址服务端抓取。"""
    # 复用历史记录批量下载的响应头/内容判定工具（同款打包行为）
    from app.routes.history import _download_response_headers, _is_html_content_type

    try:
        id_list = [int(i.strip()) for i in ids.split(",") if i.strip()]
    except ValueError:
        raise HTTPException(status_code=400, detail="ids 格式错误，应为逗号分隔的数字")
    if not id_list:
        raise HTTPException(status_code=400, detail="ids 不能为空")
    if len(id_list) > 100:
        raise HTTPException(status_code=400, detail="单次最多下载 100 个文件")

    rows = (
        await db.scalars(
            select(Asset).where(or_(Asset.id == i for i in id_list), Asset.user_id == current_user.id)
        )
    ).all()
    if not rows:
        raise HTTPException(status_code=404, detail="未找到对应资产")

    zip_buffer = io.BytesIO()
    async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as http:
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for asset in rows:
                if not asset.asset_url:
                    continue
                ext = _asset_file_ext(asset.asset_url) or (".mp4" if asset.kind == "video" else ".png")
                filename = f"asset-{asset.kind or 'file'}-{asset.id}{ext}"
                try:
                    if asset.asset_url.startswith("/uploads/"):
                        # 本地存储：直读磁盘（/uploads/ 后即相对路径），线程池读避免阻塞事件循环
                        rel = asset.asset_url.removeprefix("/uploads/")
                        file_path = Path(UPLOADS_DIR) / rel
                        if not file_path.is_file():
                            logger.warning("[资产] 批量下载跳过缺失文件: id=%d path=%s", asset.id, rel)
                            continue
                        content = await asyncio.to_thread(file_path.read_bytes)
                    elif asset.asset_url.startswith(("http://", "https://")):
                        resp = await http.get(asset.asset_url, headers={"User-Agent": "Agnes-Platform-Download"})
                        if resp.status_code != 200 or _is_html_content_type(resp.headers.get("content-type", "")):
                            logger.warning("[资产] 批量下载跳过失败文件: id=%d status=%d", asset.id, resp.status_code)
                            continue
                        content = resp.content
                    else:
                        continue
                    zf.writestr(filename, content)
                except Exception as e:  # noqa: BLE001 — 单个文件失败跳过，不阻塞整体打包
                    logger.warning("[资产] 批量下载跳过异常文件: id=%d error=%s", asset.id, e)

    zip_buffer.seek(0)
    zip_filename = f"agnes-assets-batch-{int(asyncio.get_event_loop().time())}.zip"
    return FastAPIResponse(
        content=zip_buffer.read(),
        media_type="application/zip",
        headers=_download_response_headers(zip_filename),
    )


# =====================================================
# 单资产详情 / 编辑（动态路由置于静态 batch-* 路由之后，避免路径吞并）
# =====================================================

@router.get("/{asset_id}", summary="本人资产详情")
async def get_asset_detail(
    asset_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    asset = await asset_library.get_asset_by_id(db, asset_id)
    if not asset or asset.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="未找到对应资产或无权操作")
    return ok(data=asset_library.asset_to_dict(asset))


@router.patch("/{asset_id}", summary="编辑资产元数据")
async def update_asset_metadata(
    asset_id: int,
    payload: AssetUpdateRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """编辑名称/类型/描述/视觉描述（仅更新提交的字段；不触碰公开/审核状态）"""
    updates = payload.model_dump(exclude_unset=True)
    if "name" in updates and not (updates["name"] or "").strip():
        raise HTTPException(status_code=400, detail="名称不能为空")
    if "type" in updates and updates["type"] not in ASSET_TYPE_CHOICES:
        raise HTTPException(status_code=400, detail=f"不支持的资产类型：{updates['type']}")

    # 作品归属校验（换/挂归属须是本人作品；-1 语义=清除归属）
    if "work_id" in updates and updates["work_id"] is not None:
        owned = (
            await db.scalars(
                select(Work.id).where(Work.id == updates["work_id"], Work.user_id == current_user.id)
            )
        ).first()
        if not owned:
            raise HTTPException(status_code=403, detail="无权挂靠此作品")

    asset = await asset_library.get_asset_by_id(db, asset_id)
    if not asset or asset.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="未找到对应资产或无权操作")

    for field, value in updates.items():
        setattr(asset, field, value)
    await db.commit()
    await db.refresh(asset)
    logger.info("[资产] 用户 %s 编辑资产 %s 元数据", current_user.id, asset_id)
    return ok(data=asset_library.asset_to_dict(asset))
