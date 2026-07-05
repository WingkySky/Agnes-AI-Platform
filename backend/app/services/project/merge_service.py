# =====================================================
# 合成服务 — 按分镜顺序拼接视频 + 简单转场
#
# 流程:
#   1. merge_project: 入口，校验项目状态 → 切到 merging → 后台执行 execute_merge
#   2. execute_merge: 取所有分镜的采用视频 → 下载到临时目录 → ffmpeg concat →
#      上传最终成片 → 更新 project.final_video_url → 推送 SSE
#
# 复用现有能力:
#   - agn_sdk client 的文件下载（直接 httpx）
#   - 现有项目的文件上传接口（若有）或本地临时 URL
#   - ffmpeg concat demuxer（与 pipeline/steps/ffmpeg_composite.py 相同思路）
# =====================================================

import asyncio
import logging
import os
import tempfile
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import (
    Project,
    ProjectShot,
    ProjectShotVideo,
    PROJECT_STATUS_MERGING,
    PROJECT_STATUS_COMPLETED,
)
from app.services.project.sse_manager import project_sse_manager
from app.services.project.project_service import update_status

logger = logging.getLogger("agnes_platform.project.merge")


async def merge_project(
    db: AsyncSession, project_id: int, user_id: int
) -> Project:
    """
    触发项目合成（异步执行）

    1. 校验项目状态
    2. 切换到 merging
    3. 后台启动 execute_merge
    """
    project = (
        await db.execute(select(Project).where(Project.id == project_id))
    ).scalar_one_or_none()
    if not project:
        raise ValueError(f"项目 {project_id} 不存在")

    if project.status == PROJECT_STATUS_MERGING:
        raise ValueError("项目正在合成中，请稍候")

    # 切换到 merging 状态
    project = await update_status(db, project_id, PROJECT_STATUS_MERGING)

    await project_sse_manager.push(
        project_id,
        "merge_progress",
        {"status": "started", "progress": 0},
    )

    # 后台执行合成（独立 session）
    asyncio.create_task(_execute_merge_wrapper(project_id, user_id))
    return project


async def _execute_merge_wrapper(project_id: int, user_id: int) -> None:
    """execute_merge 的包装器，使用独立 session"""
    from app.core.database import new_async_session

    db = new_async_session()
    try:
        await execute_merge(db, project_id, user_id)
    except Exception as e:
        logger.error(f"项目合成失败 project_id={project_id}: {e}")
        # 失败回滚状态
        await update_status(db, project_id, PROJECT_STATUS_COMPLETED)
        await project_sse_manager.push(
            project_id,
            "merge_progress",
            {"status": "failed", "error": str(e)},
        )
    finally:
        await db.close()


async def execute_merge(
    db: AsyncSession, project_id: int, user_id: int
) -> Optional[Project]:
    """
    实际执行合成:
    1. 取所有分镜的采用视频
    2. 下载到临时目录
    3. 用 ffmpeg concat 拼接
    4. 上传最终成片（暂存为本地 URL 或调用上传接口）
    5. 更新 project.final_video_url
    6. 切换到 completed
    """
    project = (
        await db.execute(select(Project).where(Project.id == project_id))
    ).scalar_one_or_none()
    if not project:
        return None

    # 取所有分镜的采用视频
    shots = (
        await db.execute(
            select(ProjectShot)
            .where(ProjectShot.project_id == project_id)
            .order_by(ProjectShot.sort_order)
        )
    ).scalars().all()

    if not shots:
        raise ValueError("项目没有分镜，无法合成")

    video_urls: list = []
    total_duration_ms = 0
    for shot in shots:
        if not shot.active_video_id:
            continue
        video = (
            await db.execute(
                select(ProjectShotVideo).where(
                    ProjectShotVideo.id == shot.active_video_id
                )
            )
        ).scalar_one_or_none()
        if video and video.file_url:
            video_urls.append(video.file_url)
            if video.duration_ms:
                total_duration_ms += video.duration_ms

    if not video_urls:
        raise ValueError("没有任何分镜有可用视频")

    await project_sse_manager.push(
        project_id,
        "merge_progress",
        {"status": "downloading", "progress": 10, "total_videos": len(video_urls)},
    )

    # 下载视频到临时目录
    import httpx

    tmp_dir = tempfile.mkdtemp(prefix=f"project_merge_{project_id}_")
    local_paths: list = []
    try:
        async with httpx.AsyncClient(timeout=300) as client:
            for idx, url in enumerate(video_urls):
                local_path = os.path.join(tmp_dir, f"shot_{idx:04d}.mp4")
                resp = await client.get(url)
                resp.raise_for_status()
                with open(local_path, "wb") as f:
                    f.write(resp.content)
                local_paths.append(local_path)

                await project_sse_manager.push(
                    project_id,
                    "merge_progress",
                    {
                        "status": "downloading",
                        "progress": 10 + int(40 * (idx + 1) / len(video_urls)),
                    },
                )

        # ffmpeg concat demuxer
        concat_list_path = os.path.join(tmp_dir, "concat_list.txt")
        with open(concat_list_path, "w") as f:
            for p in local_paths:
                # ffmpeg concat demuxer 要求绝对路径，单引号转义
                abs_path = os.path.abspath(p)
                f.write(f"file '{abs_path}'\n")

        # 输出到持久化目录 backend/outputs/projects/{project_id}/final.mp4
        # 通过 /api/projects/{id}/final-video 端点流式返回，避免 file:// 协议被浏览器拦截
        outputs_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "outputs", "projects", str(project_id),
        )
        os.makedirs(outputs_dir, exist_ok=True)
        output_path = os.path.join(outputs_dir, "final.mp4")
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", concat_list_path,
            "-c", "copy",
            output_path,
        ]

        await project_sse_manager.push(
            project_id,
            "merge_progress",
            {"status": "compositing", "progress": 60},
        )

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=600)
        if proc.returncode != 0:
            err_msg = stderr.decode("utf-8", errors="ignore")[:500]
            raise RuntimeError(f"ffmpeg 合成失败: {err_msg}")

        # final_video_url 存储为后端可访问的相对 URL
        # 前端通过 baseURL + 此路径访问 /api/projects/{id}/final-video 流式端点
        # 加版本时间戳避免缓存
        import time as _time
        final_url = f"/api/projects/{project_id}/final-video?v={int(_time.time())}"

        # 更新项目
        project.final_video_url = final_url
        project.total_duration = total_duration_ms / 1000.0
        project.status = PROJECT_STATUS_COMPLETED
        await db.commit()
        await db.refresh(project)

        await project_sse_manager.push(
            project_id,
            "merge_completed",
            {
                "status": "completed",
                "progress": 100,
                "final_video_url": final_url,
                "total_duration_ms": total_duration_ms,
            },
        )
        return project
    finally:
        # 清理临时下载目录（final.mp4 已持久化到 outputs/projects/{id}/）
        # 保留 outputs 下的成片供前端访问，不在此清理
        try:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)
        except Exception:
            pass


async def get_merge_status(
    db: AsyncSession, project_id: int
) -> dict:
    """查询合成状态"""
    project = (
        await db.execute(select(Project).where(Project.id == project_id))
    ).scalar_one_or_none()
    if not project:
        return {"status": "unknown"}
    return {
        "status": project.status,
        "final_video_url": project.final_video_url,
        "total_duration": project.total_duration,
    }
