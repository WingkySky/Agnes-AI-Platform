# =====================================================
# 合成服务 — 按分镜顺序拼接视频 + 简单转场 / 高级多轨合成
#
# 两套合成入口:
#   1. execute_merge（简单合成）: 按分镜顺序 concat demuxer 拼接视频，无音频/字幕
#   2. execute_merge_advanced（高级合成，Phase 2）: 按时间线多轨合成
#      - 视频轨: xfade 转场（fade/slide/wipe/dissolve）+ PIP 画中画叠加
#      - 音频轨: TTS 拼接（30ms 淡入淡出避免爆音）+ BGM amix 混音
#      - 字幕轨: ASS 烧录
#
# merge_project 根据 use_timeline 参数路由到对应实现。
#
# 复用现有能力:
#   - timeline_service.list_clips / get_subtitle_style
#   - subtitle_service.build_ass
#   - bgm_library（Task 6.5 新增）
#   - ffmpeg subprocess（concat demuxer + xfade + subtitles 滤镜）
# =====================================================

import asyncio
import logging
import os
import tempfile
from typing import Optional, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import (
    Project,
    ProjectShot,
    ProjectShotVideo,
    ProjectShotAudio,
    PROJECT_STATUS_MERGING,
    PROJECT_STATUS_COMPLETED,
)
from app.services.project.sse_manager import project_sse_manager
from app.services.project.project_service import update_status

logger = logging.getLogger("agnes_platform.project.merge")


async def merge_project(
    db: AsyncSession, project_id: int, user_id: int,
    with_audio: bool = True, with_subtitle: bool = True,
    with_bgm: bool = False, bgm_id: Optional[str] = None,
    use_timeline: bool = True,
) -> Project:
    """
    触发项目合成（异步执行）

    参数:
    - with_audio: 是否混入音频轨（TTS 配音），仅 use_timeline=True 时生效
    - with_subtitle: 是否烧录字幕，仅 use_timeline=True 时生效
    - with_bgm: 是否混入 BGM 背景音乐，仅 use_timeline=True 时生效
    - bgm_id: 指定 BGM ID（从内置库选），未指定则按项目氛围自动选
    - use_timeline: True=按时间线高级合成，False=按分镜顺序简单拼接

    1. 校验项目状态：只阻止 merging 中重复触发，允许 in_progress / completed 重新合成
    2. 清空旧 final_video_url（避免用户看到上次的失败结果）
    3. 切换到 merging
    4. 后台启动 execute_merge / execute_merge_advanced
    """
    project = (
        await db.execute(select(Project).where(Project.id == project_id))
    ).scalar_one_or_none()
    if not project:
        raise ValueError(f"项目 {project_id} 不存在")

    if project.status == PROJECT_STATUS_MERGING:
        raise ValueError("项目正在合成中，请稍候")

    # 重新合成时清空旧的成片 URL（避免用户点"播放成片"看到上次的失败结果）
    if project.final_video_url:
        project.final_video_url = None
        await db.commit()

    # 切换到 merging 状态
    project = await update_status(db, project_id, PROJECT_STATUS_MERGING)

    await project_sse_manager.push(
        project_id,
        "merge_progress",
        {"status": "started", "progress": 0, "message": "合成任务已启动"},
    )

    # 后台执行合成（独立 session）
    asyncio.create_task(_execute_merge_wrapper(
        project_id, user_id,
        with_audio=with_audio, with_subtitle=with_subtitle,
        with_bgm=with_bgm, bgm_id=bgm_id,
        use_timeline=use_timeline,
    ))
    return project


async def _execute_merge_wrapper(
    project_id: int, user_id: int,
    with_audio: bool = True, with_subtitle: bool = True,
    with_bgm: bool = False, bgm_id: Optional[str] = None,
    use_timeline: bool = True,
) -> None:
    """execute_merge / execute_merge_advanced 的包装器，使用独立 session"""
    from app.core.database import new_async_session

    db = new_async_session()
    try:
        if use_timeline:
            await execute_merge_advanced(
                db, project_id, user_id,
                with_audio=with_audio, with_subtitle=with_subtitle,
                with_bgm=with_bgm, bgm_id=bgm_id,
            )
        else:
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


# =====================================================
# 高级合成（Phase 2）— 多轨视频/音频/字幕合成
# -------------------------------------------------
# 流程:
#   1. 取时间线片段（video/audio/subtitle 三类轨道）
#   2. 下载所有视频/音频片段到临时目录
#   3. 按时间线顺序拼接视频（含 xfade 转场）+ PIP 画中画叠加
#   4. 混合音频轨：TTS 拼接（30ms 淡入淡出）+ BGM amix
#   5. 生成 ASS 字幕文件
#   6. ffmpeg 最终合成：视频 + 音频 + 字幕烧录
#   7. 上传最终成片 + 推送 SSE
#
# 转场实现（xfade 滤镜）:
#   - fade/slide/wipe/dissolve 四种
#   - 逐对拼接：[0:v][1:v]xfade=transition=fade:duration=0.5:offset=T0[v01]
#   - offset = 前一个片段时长 - transition_duration
#   - 多段串联：[v01][2:v]xfade=...:offset=T01[v012]
#   - 所有片段需先统一分辨率和帧率（scale + setsar + fps）
#
# 音频淡变（afade 滤镜）:
#   - 30ms 淡入淡出，避免拼接点爆音
#   - afade=t=in:st=0:d=0.03,afade=t=out:st={dur-0.03}:d=0.03
# =====================================================

async def execute_merge_advanced(
    db: AsyncSession, project_id: int, user_id: int,
    with_audio: bool = True, with_subtitle: bool = True,
    with_bgm: bool = False, bgm_id: Optional[str] = None,
) -> Optional[Project]:
    """
    高级合成（多轨 + 音频混入 + 字幕烧录 + BGM + 转场）

    参数:
    - with_audio: 是否混入音频轨（TTS 配音）
    - with_subtitle: 是否烧录字幕
    - with_bgm: 是否混入 BGM
    - bgm_id: 指定 BGM ID，未指定则不混入 BGM（避免误选）
    """
    from app.services.project.timeline_service import list_clips, get_subtitle_style
    from app.services.project.subtitle_service import build_ass

    project = (
        await db.execute(select(Project).where(Project.id == project_id))
    ).scalar_one_or_none()
    if not project:
        return None

    # 1. 取时间线片段
    video_clips = await list_clips(db, project_id, track_type="video")
    audio_clips = await list_clips(db, project_id, track_type="audio") if with_audio else []
    subtitle_clips = await list_clips(db, project_id, track_type="subtitle") if with_subtitle else []

    if not video_clips:
        raise ValueError("时间线无视频片段，请先初始化时间线或生成视频")

    await project_sse_manager.push(project_id, "merge_progress", {
        "status": "downloading", "progress": 5,
        "total_videos": len(video_clips), "total_audios": len(audio_clips),
    })

    # 2. 下载视频和音频片段到临时目录
    import httpx

    tmp_dir = tempfile.mkdtemp(prefix=f"project_merge_adv_{project_id}_")
    video_paths: List[str] = []
    audio_paths: List[str] = []
    try:
        async with httpx.AsyncClient(timeout=300) as client:
            # 下载主视频轨（track_index=0）的片段
            for idx, clip in enumerate(video_clips):
                if clip.track_index != 0 or not clip.source_id:
                    continue
                video = (
                    await db.execute(
                        select(ProjectShotVideo).where(ProjectShotVideo.id == clip.source_id)
                    )
                ).scalar_one_or_none()
                if not video or not video.file_url:
                    continue
                local_path = os.path.join(tmp_dir, f"video_{idx:04d}.mp4")
                resp = await client.get(video.file_url)
                resp.raise_for_status()
                with open(local_path, "wb") as f:
                    f.write(resp.content)
                video_paths.append(local_path)

                await project_sse_manager.push(project_id, "merge_progress", {
                    "status": "downloading",
                    "progress": 5 + int(15 * (idx + 1) / max(len(video_clips), 1)),
                })

            # 下载音频片段（TTS）
            if audio_clips:
                for idx, clip in enumerate(audio_clips):
                    if clip.track_index != 0 or not clip.source_id:
                        continue
                    audio = (
                        await db.execute(
                            select(ProjectShotAudio).where(ProjectShotAudio.id == clip.source_id)
                        )
                    ).scalar_one_or_none()
                    if not audio or not audio.file_url:
                        continue
                    local_path = os.path.join(tmp_dir, f"audio_{idx:04d}.mp3")
                    resp = await client.get(audio.file_url)
                    resp.raise_for_status()
                    with open(local_path, "wb") as f:
                        f.write(resp.content)
                    audio_paths.append(local_path)

        await project_sse_manager.push(project_id, "merge_progress", {
            "status": "compositing", "progress": 30,
        })

        if not video_paths:
            raise ValueError("时间线视频片段无可用源文件")

        # 3. 拼接视频（含 xfade 转场）
        composite_video_path = os.path.join(tmp_dir, "composite_video.mp4")
        await _concat_videos_with_xfade(
            clips=[c for c in video_clips if c.track_index == 0 and c.source_id],
            video_paths=video_paths,
            output_path=composite_video_path,
            aspect_ratio=project.aspect_ratio or "16:9",
        )

        await project_sse_manager.push(project_id, "merge_progress", {
            "status": "compositing", "progress": 55,
        })

        # 4. 混合音频（TTS 拼接 + 淡入淡出 + BGM amix）
        composite_audio_path: Optional[str] = None
        if audio_paths or (with_bgm and bgm_id):
            composite_audio_path = os.path.join(tmp_dir, "composite_audio.aac")
            await _mix_audio_tracks(
                audio_paths=audio_paths,
                output_path=composite_audio_path,
                with_bgm=with_bgm,
                bgm_id=bgm_id,
                total_duration=_estimate_total_duration(video_clips),
            )

        await project_sse_manager.push(project_id, "merge_progress", {
            "status": "compositing", "progress": 75,
        })

        # 5. 生成 ASS 字幕文件
        subtitle_path: Optional[str] = None
        if subtitle_clips:
            subtitle_path = os.path.join(tmp_dir, "subtitles.ass")
            subtitle_style = await get_subtitle_style(db, project_id)
            clips_data = [
                {
                    "start_time": c.start_time,
                    "duration": c.duration,
                    "text": c.subtitle_text or "",
                }
                for c in subtitle_clips
            ]
            ass_content = build_ass(clips_data, subtitle_style)
            with open(subtitle_path, "w", encoding="utf-8") as f:
                f.write(ass_content)

        # 6. 最终合成：视频 + 音频 + 字幕烧录
        outputs_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "outputs", "projects", str(project_id),
        )
        os.makedirs(outputs_dir, exist_ok=True)
        output_path = os.path.join(outputs_dir, "final.mp4")

        await _ffmpeg_final_composite(
            video_path=composite_video_path,
            audio_path=composite_audio_path,
            subtitle_path=subtitle_path,
            output_path=output_path,
        )

        # 7. 更新项目
        import time as _time
        final_url = f"/api/projects/{project_id}/final-video?v={int(_time.time())}"

        # 计算总时长（取所有视频片段 end_time 的最大值）
        total_duration = max(
            (c.start_time + c.duration for c in video_clips),
            default=0.0,
        )

        project.final_video_url = final_url
        project.total_duration = total_duration
        project.status = PROJECT_STATUS_COMPLETED
        await db.commit()
        await db.refresh(project)

        await project_sse_manager.push(project_id, "merge_completed", {
            "status": "completed", "progress": 100,
            "final_video_url": final_url,
            "total_duration": total_duration,
        })
        return project

    finally:
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _estimate_total_duration(video_clips: List) -> float:
    """估算视频总时长（取所有片段 end_time 的最大值）"""
    if not video_clips:
        return 0.0
    return max((c.start_time + c.duration for c in video_clips), default=0.0)


async def _run_ffmpeg(cmd: List[str], timeout: int = 900, error_label: str = "ffmpeg") -> None:
    """运行 ffmpeg 子进程，失败抛出可读错误"""
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    if proc.returncode != 0:
        err_msg = stderr.decode("utf-8", errors="ignore")[:500]
        raise RuntimeError(f"{error_label} 失败: {err_msg}")


def _parse_resolution(aspect_ratio: str) -> tuple:
    """从 aspect_ratio 字符串解析 (width, height)，默认 1280x720"""
    # 支持 "16:9" / "9:16" / "1:1" / "1280x720" 等
    if "x" in aspect_ratio:
        parts = aspect_ratio.split("x")
        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
            w, h = int(parts[0]), int(parts[1])
            # 强制 8 倍数（视频编码要求）
            return (w - w % 8, h - h % 8)
    ratio_map = {"16:9": (1280, 720), "9:16": (720, 1280), "1:1": (720, 720), "4:3": (960, 720)}
    return ratio_map.get(aspect_ratio, (1280, 720))


async def _concat_videos_with_xfade(
    clips: List, video_paths: List[str], output_path: str, aspect_ratio: str
) -> None:
    """
    拼接视频片段，含 xfade 转场。

    策略:
    - 单个片段: 直接 copy
    - 多个片段 + 所有 transition_type=none: 用 concat demuxer（-c copy，最快）
    - 多个片段 + 有转场: 用 xfade 滤镜逐对拼接（需 reencode，较慢）
    """
    if not video_paths:
        raise ValueError("无视频片段可拼接")

    # 单个片段：直接 copy
    if len(video_paths) == 1:
        import shutil
        shutil.copy2(video_paths[0], output_path)
        return

    # 检查是否有转场（clips 和 paths 顺序对应）
    has_transition = any(
        getattr(clips[i], "transition_type", "none") not in ("none", "", None)
        and getattr(clips[i], "transition_duration", 0) > 0
        for i in range(min(len(clips), len(video_paths)))
    )

    # 无转场：用 concat demuxer（快速，-c copy）
    if not has_transition:
        concat_list_path = output_path + ".concat.txt"
        with open(concat_list_path, "w") as f:
            for p in video_paths:
                f.write(f"file '{os.path.abspath(p)}'\n")
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", concat_list_path,
            "-c", "copy",
            output_path,
        ]
        await _run_ffmpeg(cmd, timeout=600, error_label="ffmpeg 视频拼接（concat）")
        return

    # 有转场：用 xfade 滤镜逐对拼接（reencode）
    width, height = _parse_resolution(aspect_ratio)

    # 第一步：统一每个片段的分辨率、帧率、sar（避免 xfade 失败）
    normalized_paths: List[str] = []
    for idx, p in enumerate(video_paths):
        norm_path = output_path + f".norm_{idx:04d}.mp4"
        cmd = [
            "ffmpeg", "-y", "-i", p,
            "-vf", f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
                   f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black,setsar=1,fps=30",
            "-c:v", "libx264", "-preset", "medium", "-crf", "23",
            "-an",  # 转场拼接阶段不需要音频，最终合成时再混入
            norm_path,
        ]
        await _run_ffmpeg(cmd, timeout=300, error_label=f"ffmpeg 视频归一化（片段 {idx}）")
        normalized_paths.append(norm_path)

    # 第二步：用 ffprobe 获取每个归一化片段的时长
    durations = await _probe_durations(normalized_paths)

    # 第三步：逐对 xfade 拼接
    # xfade 滤镜链：[0:v][1:v]xfade=transition=X:duration=D:offset=O[v01]
    # offset = 累积时长 - 转场时长
    filter_parts: List[str] = []
    prev_label = "0:v"
    accumulated = 0.0
    for i in range(1, len(normalized_paths)):
        # 当前转场参数（取当前片段 i-1 的 transition 配置，即 clips[i-1]）
        clip_idx = min(i - 1, len(clips) - 1) if clips else 0
        transition_type = getattr(clips[clip_idx], "transition_type", "fade") if clips else "fade"
        transition_duration = getattr(clips[clip_idx], "transition_duration", 0.5) if clips else 0.5
        if transition_type in ("none", "", None) or transition_duration <= 0:
            transition_type = "fade"
            transition_duration = 0.5

        # offset = 前一段时长 - 转场时长（累积时长需减去之前重叠的转场）
        accumulated += durations[i - 1]
        offset = max(0, accumulated - transition_duration)
        # 累积时长在转场后变成 offset（因为转场期间两段重叠）
        accumulated = offset

        out_label = f"[v{i:02d}]"
        filter_parts.append(
            f"[{prev_label}][{i}:v]xfade=transition={transition_type}"
            f":duration={transition_duration}:offset={offset}{out_label}"
        )
        prev_label = out_label.lstrip("[").rstrip("]")

    filter_complex = ";".join(filter_parts)

    cmd = [
        "ffmpeg", "-y",
        *sum([["-i", p] for p in normalized_paths], []),
        "-filter_complex", filter_complex,
        "-map", f"[{prev_label}]" if prev_label.startswith("v") else "[v01]",
        "-c:v", "libx264", "-preset", "medium", "-crf", "23",
        "-an",
        output_path,
    ]
    await _run_ffmpeg(cmd, timeout=900, error_label="ffmpeg 视频拼接（xfade 转场）")


async def _probe_durations(video_paths: List[str]) -> List[float]:
    """用 ffprobe 获取每个视频的时长（秒）"""
    durations: List[float] = []
    for p in video_paths:
        cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            p,
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=60)
        try:
            dur = float(stdout.decode("utf-8", errors="ignore").strip())
        except (ValueError, AttributeError):
            dur = 3.0  # 默认 3 秒
        durations.append(dur)
    return durations


async def _mix_audio_tracks(
    audio_paths: List[str],
    output_path: str,
    with_bgm: bool = False,
    bgm_id: Optional[str] = None,
    total_duration: float = 0.0,
) -> None:
    """
    混合音频轨：TTS 拼接（30ms 淡入淡出）+ BGM amix

    策略:
    - 无 TTS 且无 BGM: 不生成音频文件（调用方应判断）
    - 仅 TTS: concat + afade
    - 仅 BGM: 取 BGM 文件，按 total_duration 截取
    - TTS + BGM: TTS concat + afade → 与 BGM amix（BGM 音量降低到 0.15）
    """
    if not audio_paths and not (with_bgm and bgm_id):
        return

    # 解析 BGM 文件路径（如果启用）
    bgm_path: Optional[str] = None
    if with_bgm and bgm_id:
        from app.services.project.bgm_library import get_bgm_path
        bgm_path = get_bgm_path(bgm_id)

    # 仅 BGM（无 TTS）
    if not audio_paths and bgm_path:
        dur = total_duration if total_duration > 0 else 60.0
        cmd = [
            "ffmpeg", "-y",
            "-i", bgm_path,
            "-t", str(dur),
            "-af", f"afade=t=in:st=0:d=0.5,afade=t=out:st={max(0, dur-0.5)}:d=0.5",
            "-c:a", "aac", "-b:a", "128k",
            output_path,
        ]
        await _run_ffmpeg(cmd, timeout=300, error_label="ffmpeg BGM 截取")
        return

    # 仅 TTS（无 BGM）
    if audio_paths and not bgm_path:
        # concat + 30ms 淡入淡出（避免拼接点爆音）
        concat_list_path = output_path + ".concat.txt"
        with open(concat_list_path, "w") as f:
            for p in audio_paths:
                f.write(f"file '{os.path.abspath(p)}'\n")

        # 先 concat，再对整体加淡入淡出
        merged_path = output_path + ".merged.aac"
        cmd_concat = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", concat_list_path,
            "-c", "copy",
            merged_path,
        ]
        await _run_ffmpeg(cmd_concat, timeout=300, error_label="ffmpeg TTS 拼接")

        # 获取拼接后总时长
        durations = await _probe_durations([merged_path])
        total_dur = durations[0] if durations else 3.0
        fade_out_start = max(0, total_dur - 0.03)

        cmd_fade = [
            "ffmpeg", "-y", "-i", merged_path,
            "-af", f"afade=t=in:st=0:d=0.03,afade=t=out:st={fade_out_start}:d=0.03",
            "-c:a", "aac", "-b:a", "128k",
            output_path,
        ]
        await _run_ffmpeg(cmd_fade, timeout=300, error_label="ffmpeg TTS 淡变")
        return

    # TTS + BGM（amix 混音）
    # 1. 先处理 TTS（concat + 淡变）
    tts_processed_path = output_path + ".tts.aac"
    await _mix_audio_tracks(
        audio_paths=audio_paths,
        output_path=tts_processed_path,
        with_bgm=False,
        bgm_id=None,
        total_duration=total_duration,
    )

    # 2. BGM 按总时长截取 + 淡入淡出
    bgm_processed_path = output_path + ".bgm.aac"
    dur = total_duration if total_duration > 0 else 60.0
    cmd_bgm = [
        "ffmpeg", "-y",
        "-i", bgm_path,
        "-t", str(dur),
        "-af", f"afade=t=in:st=0:d=0.5,afade=t=out:st={max(0, dur-0.5)}:d=0.5,volume=0.15",
        "-c:a", "aac", "-b:a", "128k",
        bgm_processed_path,
    ]
    await _run_ffmpeg(cmd_bgm, timeout=300, error_label="ffmpeg BGM 预处理")

    # 3. amix 混音（TTS 1.0 + BGM 1.0 → 总音量归一化）
    cmd_mix = [
        "ffmpeg", "-y",
        "-i", tts_processed_path,
        "-i", bgm_processed_path,
        "-filter_complex", "amix=inputs=2:duration=first:dropout_transition=0",
        "-c:a", "aac", "-b:a", "128k",
        output_path,
    ]
    await _run_ffmpeg(cmd_mix, timeout=300, error_label="ffmpeg TTS+BGM 混音")


async def _ffmpeg_final_composite(
    video_path: str,
    audio_path: Optional[str],
    subtitle_path: Optional[str],
    output_path: str,
) -> None:
    """最终合成：视频 + 音频 + 字幕烧录"""
    cmd: List[str] = ["ffmpeg", "-y", "-i", video_path]

    if audio_path:
        cmd.extend(["-i", audio_path])

    # 视频滤镜（字幕烧录）
    vf_filters: List[str] = []
    if subtitle_path:
        # subtitles 滤镜路径需转义冒号（Windows 路径问题，Linux 也要转义）
        escaped_path = subtitle_path.replace(":", "\\:")
        vf_filters.append(f"subtitles='{escaped_path}'")

    if vf_filters:
        cmd.extend(["-vf", ",".join(vf_filters)])

    # 映射流
    if audio_path:
        cmd.extend(["-map", "0:v", "-map", "1:a"])
    else:
        cmd.extend(["-map", "0:v"])

    # 编码参数
    cmd.extend([
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "23",
    ])
    if audio_path:
        cmd.extend(["-c:a", "aac", "-b:a", "128k"])

    cmd.append(output_path)

    await _run_ffmpeg(cmd, timeout=900, error_label="ffmpeg 最终合成")
