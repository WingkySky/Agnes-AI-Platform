# =====================================================
# 帧图服务 — 分镜帧图多版本管理 + 生成 + 上传
#
# 对应 project_shot_frame_images 表。
# 生成时注入角色参考图（reference_character_ids），
# 通过 agnes_client.create_image 调用图生图。
# =====================================================

import logging
from typing import List, Optional

from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import (
    ProjectShot,
    ProjectShotFrameImage,
    ProjectShotCharacter,
    ProjectCharacter,
    ProjectEntityAsset,
)
from app.services.agnes_client import agnes_client
from app.services.project.sse_manager import project_sse_manager

logger = logging.getLogger("agnes_platform.project.frame_image")


# =====================================================
# 内部工具
# =====================================================

async def _next_version(db: AsyncSession, shot_id: int) -> int:
    """计算下一个版本号"""
    result = await db.execute(
        select(func.max(ProjectShotFrameImage.version)).where(
            ProjectShotFrameImage.shot_id == shot_id
        )
    )
    cur = result.scalar()
    return (cur or 0) + 1


async def _reset_active_flags(db: AsyncSession, shot_id: int) -> None:
    """将该分镜所有帧图的 is_active 置为 False"""
    await db.execute(
        update(ProjectShotFrameImage)
        .where(ProjectShotFrameImage.shot_id == shot_id)
        .values(is_active=False)
    )


async def _get_character_ref_urls(
    db: AsyncSession, character_ids: List[int]
) -> List[str]:
    """获取角色参考图 URL（取每个角色的激活形象图）"""
    if not character_ids:
        return []
    urls: List[str] = []
    for cid in character_ids:
        result = await db.execute(
            select(ProjectEntityAsset)
            .where(
                ProjectEntityAsset.entity_type == "character",
                ProjectEntityAsset.entity_id == cid,
                ProjectEntityAsset.is_active.is_(True),
            )
            .limit(1)
        )
        asset = result.scalar_one_or_none()
        if asset and asset.file_url:
            urls.append(asset.file_url)
    return urls


# =====================================================
# 帧图版本查询
# =====================================================

async def list_frame_images(
    db: AsyncSession, shot_id: int
) -> List[ProjectShotFrameImage]:
    """列出分镜所有帧图版本（按版本号倒序）"""
    result = await db.execute(
        select(ProjectShotFrameImage)
        .where(ProjectShotFrameImage.shot_id == shot_id)
        .order_by(ProjectShotFrameImage.version.desc())
    )
    return result.scalars().all()


async def get_frame_image(
    db: AsyncSession, frame_image_id: int
) -> Optional[ProjectShotFrameImage]:
    """获取帧图版本"""
    result = await db.execute(
        select(ProjectShotFrameImage).where(
            ProjectShotFrameImage.id == frame_image_id
        )
    )
    return result.scalar_one_or_none()


# =====================================================
# 帧图生成
# =====================================================

async def generate_frame_image(
    db: AsyncSession,
    shot_id: int,
    user_id: int,
    style_config: Optional[dict] = None,
    model: str = "",
    size: str = "1024x1024",
    reference_character_ids: Optional[List[int]] = None,
) -> Optional[ProjectShotFrameImage]:
    """
    生成分镜帧图（基于分镜的 image_prompt + 角色参考图）

    Args:
        reference_character_ids: 参考角色 ID 数组，不传则取该分镜已绑定的所有角色
    """
    shot = (
        await db.execute(select(ProjectShot).where(ProjectShot.id == shot_id))
    ).scalar_one_or_none()
    if not shot:
        return None

    # 确定参考角色
    if reference_character_ids is None:
        # 取该分镜已绑定的角色
        chars_result = await db.execute(
            select(ProjectShotCharacter.character_id).where(
                ProjectShotCharacter.shot_id == shot_id
            )
        )
        reference_character_ids = list(chars_result.scalars().all())

    # 拼接 prompt
    prompt_parts = [shot.image_prompt or shot.visual_desc or shot.title or "scene"]
    if style_config:
        for k, v in style_config.items():
            if v:
                prompt_parts.append(f"{k}: {v}")
    prompt = ", ".join(prompt_parts)

    # 获取参考图 URL
    ref_urls = await _get_character_ref_urls(db, reference_character_ids)

    await project_sse_manager.push(
        shot.project_id,
        "generation_started",
        {
            "target": f"shot:{shot_id}:frame_image",
            "version_type": "frame_image",
            "user_id": user_id,
            "reference_character_ids": reference_character_ids,
        },
    )

    try:
        kwargs = {
            "prompt": prompt,
            "model": model or "agnes-image-2.0-flash",
            "size": size,
            "response_format": "url",
        }
        if ref_urls:
            kwargs["image_urls"] = ref_urls

        result = await agnes_client.create_image(**kwargs)
        data_list = result.get("data", [])
        if not data_list:
            raise RuntimeError("图片生成返回空数据")
        image_url = data_list[0].get("url", "")
        if not image_url:
            raise RuntimeError("图片生成未返回 URL")

        # 创建新版本
        version_no = await _next_version(db, shot_id)
        await _reset_active_flags(db, shot_id)

        frame_image = ProjectShotFrameImage(
            shot_id=shot_id,
            version=version_no,
            is_active=True,
            is_manual=False,
            file_url=image_url,
            thumbnail_url=image_url,
            prompt=prompt,
            model=model or "agnes-image-2.0-flash",
            reference_character_ids=reference_character_ids,
            file_type="image",
            created_by="ai",
        )
        db.add(frame_image)
        await db.flush()

        shot.active_frame_image_id = frame_image.id
        await db.commit()
        await db.refresh(frame_image)

        await project_sse_manager.push(
            shot.project_id,
            "generation_completed",
            {
                "target": f"shot:{shot_id}:frame_image",
                "version_id": frame_image.id,
                "file_url": image_url,
            },
        )
        return frame_image
    except Exception as e:
        await project_sse_manager.push(
            shot.project_id,
            "generation_failed",
            {
                "target": f"shot:{shot_id}:frame_image",
                "error": str(e),
            },
        )
        raise


async def batch_generate_frame_images(
    db: AsyncSession,
    shot_ids: List[int],
    user_id: int,
    style_config: Optional[dict] = None,
    model: str = "",
    size: str = "1024x1024",
) -> List[dict]:
    """批量生成帧图"""
    results = []
    for sid in shot_ids:
        try:
            fi = await generate_frame_image(
                db, sid, user_id, style_config, model, size
            )
            results.append(
                {"shot_id": sid, "success": bool(fi), "file_url": fi.file_url if fi else None}
            )
        except Exception as e:
            results.append({"shot_id": sid, "success": False, "error": str(e)})
    return results


# =====================================================
# 上传帧图
# =====================================================

async def upload_frame_image(
    db: AsyncSession,
    shot_id: int,
    user_id: int,
    file_url: str,
    thumbnail_url: str = "",
    file_size: Optional[int] = None,
    width: Optional[int] = None,
    height: Optional[int] = None,
) -> Optional[ProjectShotFrameImage]:
    """用户手动上传帧图作为新版本（G1）"""
    shot = (
        await db.execute(select(ProjectShot).where(ProjectShot.id == shot_id))
    ).scalar_one_or_none()
    if not shot:
        return None

    version_no = await _next_version(db, shot_id)
    await _reset_active_flags(db, shot_id)

    frame_image = ProjectShotFrameImage(
        shot_id=shot_id,
        version=version_no,
        is_active=True,
        is_manual=True,
        file_url=file_url,
        thumbnail_url=thumbnail_url or file_url,
        prompt="(用户上传)",
        reference_character_ids=[],
        file_type="image",
        file_size=file_size,
        width=width,
        height=height,
        created_by="manual",
    )
    db.add(frame_image)
    await db.flush()

    shot.active_frame_image_id = frame_image.id
    await db.commit()
    await db.refresh(frame_image)

    await project_sse_manager.push(
        shot.project_id,
        "active_version_changed",
        {
            "target": f"shot:{shot_id}:frame_image",
            "version_id": frame_image.id,
            "file_url": file_url,
        },
    )
    return frame_image


# =====================================================
# 切换激活版 / 删除版本
# =====================================================

async def set_active_frame_image(
    db: AsyncSession, shot_id: int, version_id: int
) -> Optional[ProjectShotFrameImage]:
    """设为激活版"""
    fi = await get_frame_image(db, version_id)
    if not fi or fi.shot_id != shot_id:
        return None

    await _reset_active_flags(db, shot_id)
    fi.is_active = True

    shot = (
        await db.execute(select(ProjectShot).where(ProjectShot.id == shot_id))
    ).scalar_one_or_none()
    if shot:
        shot.active_frame_image_id = fi.id
        project_id = shot.project_id
    else:
        project_id = None

    await db.commit()
    await db.refresh(fi)

    if project_id:
        await project_sse_manager.push(
            project_id,
            "active_version_changed",
            {
                "target": f"shot:{shot_id}:frame_image",
                "version_id": version_id,
                "file_url": fi.file_url,
            },
        )
    return fi


async def delete_frame_image(
    db: AsyncSession, shot_id: int, version_id: int
) -> bool:
    """删除版本（不允许删除激活版）"""
    fi = await get_frame_image(db, version_id)
    if not fi or fi.shot_id != shot_id:
        return False
    if fi.is_active:
        return False

    await db.delete(fi)

    # 若分镜指针指向该版本，置空
    shot = (
        await db.execute(select(ProjectShot).where(ProjectShot.id == shot_id))
    ).scalar_one_or_none()
    if shot and shot.active_frame_image_id == version_id:
        shot.active_frame_image_id = None

    await db.commit()
    return True
