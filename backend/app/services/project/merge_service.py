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
from datetime import datetime, timedelta
from typing import Optional, List
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import (
    Project,
    ProjectShot,
    ProjectShotVideo,
    ProjectShotAudio,
    ProjectShotFrameImage,  # Phase 2 增强：帧图源（shot_frame_image）
    PROJECT_STATUS_MERGING,
    PROJECT_STATUS_COMPLETED,
)
from app.services.project.sse_manager import project_sse_manager
from app.services.project.project_service import update_status
# ffmpeg 公共能力已抽到 media_compose（画布合成共用），别名保持原内部调用不变
from app.services.media_compose import (
    run_ffmpeg as _run_ffmpeg,
    parse_resolution as _parse_resolution,
    video_normalize_only_cmd as _video_normalize_only_cmd,
    stream_download as _stream_download,
    probe_durations as _probe_durations,
    probe_video_resolution as _probe_video_resolution,
    check_subtitles_filter_available as _check_subtitles_filter_available,
    check_drawtext_filter_available as _check_drawtext_filter_available,
    build_drawtext_subtitles_filter as _build_drawtext_subtitles_filter,
    concat_normalized_videos as _concat_normalized_videos,
    ffmpeg_final_composite as _ffmpeg_final_composite,
)

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

    1. 校验项目状态：阻止 merging 中重复触发，但允许超时（5分钟）自动恢复
       允许 in_progress / completed 重新合成
    2. 清空旧 final_video_url（避免用户看到上次的失败结果）
    3. 切换到 merging
    4. 后台启动 execute_merge / execute_merge_advanced
    """
    project = (
        await db.execute(select(Project).where(Project.id == project_id))
    ).scalar_one_or_none()
    if not project:
        raise ValueError(f"项目 {project_id} 不存在")

    # 合成中重复触发：检查是否超时（5 分钟），超时视为上次合成卡死，自动恢复
    if project.status == PROJECT_STATUS_MERGING:
        if project.updated_at:
            age = datetime.utcnow() - project.updated_at
            if age < timedelta(minutes=5):
                raise ValueError("项目正在合成中，请稍候")
            logger.warning(
                "项目 %s 卡在 merging 状态已 %s 秒，视为上次合成失败，自动恢复以允许重新合成",
                project_id, int(age.total_seconds()),
            )
        else:
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
    from app.models.project import PROJECT_STATUS_IN_PROGRESS

    db = new_async_session()
    try:
        logger.info("[合成] 开始执行 project_id=%s use_timeline=%s", project_id, use_timeline)
        if use_timeline:
            await execute_merge_advanced(
                db, project_id, user_id,
                with_audio=with_audio, with_subtitle=with_subtitle,
                with_bgm=with_bgm, bgm_id=bgm_id,
            )
        else:
            await execute_merge(db, project_id, user_id)
        logger.info("[合成] 执行完成 project_id=%s", project_id)
    except Exception as e:
        logger.error("[合成] 项目合成失败 project_id=%s: %s", project_id, e, exc_info=True)
        # 失败回滚状态：回滚到 in_progress（合成失败后项目可继续编辑/重试）
        # 不用 completed，避免误以为合成成功
        try:
            await update_status(db, project_id, PROJECT_STATUS_IN_PROGRESS)
        except Exception as rollback_err:
            logger.error("[合成] 状态回滚失败 project_id=%s: %s", project_id, rollback_err)
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
                # 流式下载，避免大视频一次性读入内存导致 OOM
                await _stream_download(client, url, local_path)
                local_paths.append(local_path)

                await project_sse_manager.push(
                    project_id,
                    "merge_progress",
                    {
                        "status": "downloading",
                        "progress": 10 + int(20 * (idx + 1) / len(video_urls)),
                    },
                )

        # 视频归一化：分镜视频分辨率/编码/SAR 不一致时直接 concat 会失败或前几秒黑屏
        # 统一分辨率/帧率/SAR/像素格式后再 concat（-c copy 最快）
        width, height = _parse_resolution(project.aspect_ratio or "16:9")
        normalized_paths: list = []
        for idx, p in enumerate(local_paths):
            norm_path = os.path.join(tmp_dir, f"norm_{idx:04d}.mp4")
            cmd_norm = _video_normalize_only_cmd(p, norm_path, width, height)
            await _run_ffmpeg(cmd_norm, timeout=300, error_label=f"ffmpeg 视频归一化（分镜 {idx}）")
            normalized_paths.append(norm_path)

            await project_sse_manager.push(
                project_id,
                "merge_progress",
                {"status": "compositing", "progress": 30 + int(20 * (idx + 1) / len(normalized_paths))},
            )

        # 输出到持久化目录 backend/outputs/projects/{project_id}/final.mp4
        # 通过 /api/projects/{id}/final-video 端点流式返回，避免 file:// 协议被浏览器拦截
        outputs_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "outputs", "projects", str(project_id),
        )
        os.makedirs(outputs_dir, exist_ok=True)
        output_path = os.path.join(outputs_dir, "final.mp4")

        await project_sse_manager.push(
            project_id,
            "merge_progress",
            {"status": "compositing", "progress": 70},
        )

        await _concat_normalized_videos(normalized_paths, output_path)

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

        # 成片自动归档进资产库（旁路，失败仅记日志）
        try:
            from app.services.asset_archive import archive_final_video
            await archive_final_video(db, project.id, project.name, project.user_id, final_url)
        except Exception as fe:
            logger.error("[合成] 成片归档失败: project_id=%s error=%s", project_id, fe, exc_info=True)

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
    from app.services.project.subtitle_service import build_ass, build_srt

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

    logger.info(
        "[合成] project_id=%s 时间线片段: video=%d audio=%d subtitle=%d",
        project_id, len(video_clips), len(audio_clips), len(subtitle_clips),
    )

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
            # 视频归一化目标尺寸（用于 shot_frame_image 静态图转视频流）
            norm_width, norm_height = _parse_resolution(project.aspect_ratio or "16:9")
            # 下载主视频轨（track_index=0）的片段
            for idx, clip in enumerate(video_clips):
                if clip.track_index != 0 or not clip.source_id:
                    continue
                if clip.source_type == "shot_frame_image":
                    # 静态图作视频段：下载后用 ffmpeg -loop 1 -t duration 转视频流
                    frame_img = (
                        await db.execute(
                            select(ProjectShotFrameImage).where(
                                ProjectShotFrameImage.id == clip.source_id
                            )
                        )
                    ).scalar_one_or_none()
                    if not frame_img or not frame_img.file_url:
                        continue
                    # 下载帧图到临时文件
                    img_path = os.path.join(tmp_dir, f"frame_{idx:04d}.png")
                    await _stream_download(client, frame_img.file_url, img_path)
                    # 用 ffmpeg 转视频流：-loop 1 -i image -t duration -r 30 + 归一化
                    normalized_path = await _normalize_frame_image(
                        img_path, float(clip.duration or 3.0),
                        norm_width, norm_height, tmp_dir,
                    )
                    video_paths.append(normalized_path)
                else:
                    # shot_video（默认行为）：下载分镜视频
                    video = (
                        await db.execute(
                            select(ProjectShotVideo).where(ProjectShotVideo.id == clip.source_id)
                        )
                    ).scalar_one_or_none()
                    if not video or not video.file_url:
                        continue
                    local_path = os.path.join(tmp_dir, f"video_{idx:04d}.mp4")
                    # 流式下载，避免大视频一次性读入内存导致 OOM
                    await _stream_download(client, video.file_url, local_path)
                    video_paths.append(local_path)

                await project_sse_manager.push(project_id, "merge_progress", {
                    "status": "downloading",
                    "progress": 5 + int(15 * (idx + 1) / max(len(video_clips), 1)),
                })

            # 下载音频片段（TTS）+ BGM
            if audio_clips:
                for idx, clip in enumerate(audio_clips):
                    if clip.track_index != 0:
                        continue
                    if clip.source_type == "bgm" and clip.source_ref:
                        # BGM：通过 source_ref 取本地文件路径，无需下载
                        from app.services.project.bgm_library import get_bgm_path
                        bgm_path = get_bgm_path(clip.source_ref)
                        if bgm_path:
                            audio_paths.append(bgm_path)
                        continue
                    if not clip.source_id:
                        continue
                    audio = (
                        await db.execute(
                            select(ProjectShotAudio).where(ProjectShotAudio.id == clip.source_id)
                        )
                    ).scalar_one_or_none()
                    if not audio or not audio.file_url:
                        continue
                    local_path = os.path.join(tmp_dir, f"audio_{idx:04d}.mp3")
                    # 流式下载
                    await _stream_download(client, audio.file_url, local_path)
                    audio_paths.append(local_path)

        await project_sse_manager.push(project_id, "merge_progress", {
            "status": "compositing", "progress": 30,
        })

        logger.info(
            "[合成] project_id=%s 下载完成: video=%d audio=%d",
            project_id, len(video_paths), len(audio_paths),
        )

        if not video_paths:
            raise ValueError("时间线视频片段无可用源文件")

        # 3. 拼接视频（含 xfade 转场）
        logger.info("[合成] project_id=%s 开始拼接视频（xfade 转场）", project_id)
        composite_video_path = os.path.join(tmp_dir, "composite_video.mp4")
        await _concat_videos_with_xfade(
            clips=[c for c in video_clips if c.track_index == 0 and c.source_id],
            video_paths=video_paths,
            output_path=composite_video_path,
            aspect_ratio=project.aspect_ratio or "16:9",
        )
        logger.info("[合成] project_id=%s 视频拼接完成: %s", project_id, composite_video_path)

        await project_sse_manager.push(project_id, "merge_progress", {
            "status": "compositing", "progress": 55,
        })

        # 4. 混合音频（TTS 拼接 + 淡入淡出 + BGM amix）
        composite_audio_path: Optional[str] = None
        if audio_paths or (with_bgm and bgm_id):
            logger.info(
                "[合成] project_id=%s 开始混合音频（TTS=%d BGM=%s）",
                project_id, len(audio_paths), bgm_id,
            )
            composite_audio_path = os.path.join(tmp_dir, "composite_audio.aac")
            await _mix_audio_tracks(
                audio_clips=[c for c in audio_clips if c.track_index == 0 and c.source_id],
                audio_paths=audio_paths,
                output_path=composite_audio_path,
                with_bgm=with_bgm,
                bgm_id=bgm_id,
                total_duration=_estimate_total_duration(video_clips),
            )
            logger.info("[合成] project_id=%s 音频混合完成: %s", project_id, composite_audio_path)

        await project_sse_manager.push(project_id, "merge_progress", {
            "status": "compositing", "progress": 75,
        })

        # 5. 生成字幕文件
        # 检测 ffmpeg 能力，按优先级选择字幕模式:
        #   1. subtitles 滤镜可用（libass）→ ASS 硬烧（样式丰富）
        #   2. drawtext 滤镜可用（ffmpeg 内置）→ drawtext 直烧（无需 libass）
        #   3. 两者都不可用 → SRT 软字幕（mov_text 嵌入容器）
        subtitle_path: Optional[str] = None
        subtitle_mode: Optional[str] = None  # "hard" | "drawtext" | "soft" | None
        subtitle_drawtext_filter: Optional[str] = None  # drawtext 模式专用
        if subtitle_clips:
            subtitle_style = await get_subtitle_style(db, project_id)
            clips_data = [
                {
                    "start_time": c.start_time,
                    "duration": c.duration,
                    "text": c.subtitle_text or "",
                }
                for c in subtitle_clips
            ]
            can_hardburn = await _check_subtitles_filter_available()
            if can_hardburn:
                # 模式 1: ASS 硬烧（libass 可用时优先，样式最丰富）
                subtitle_path = os.path.join(tmp_dir, "subtitles.ass")
                ass_content = build_ass(clips_data, subtitle_style)
                with open(subtitle_path, "w", encoding="utf-8") as f:
                    f.write(ass_content)
                subtitle_mode = "hard"
                logger.info("[合成] project_id=%s 字幕模式: 硬烧(ASS) %d 条", project_id, len(clips_data))
            else:
                # libass 不可用，尝试 drawtext 直烧
                can_drawtext = await _check_drawtext_filter_available()
                if can_drawtext:
                    # 模式 2: drawtext 直烧（ffmpeg 内置滤镜，无 libass 依赖）
                    # drawtext 滤镜直接构造在 -vf 链中，不需要外部字幕文件
                    # 获取视频分辨率用于位置计算（从已拼接的 composite_video 读取）
                    vid_w, vid_h = await _probe_video_resolution(composite_video_path)
                    subtitle_drawtext_filter = _build_drawtext_subtitles_filter(
                        clips_data, subtitle_style, vid_w, vid_h,
                    )
                    subtitle_mode = "drawtext"
                    logger.info(
                        "[合成] project_id=%s 字幕模式: drawtext 直烧 %d 条 (resolution=%dx%d)",
                        project_id, len(clips_data), vid_w, vid_h,
                    )
                else:
                    # 模式 3: SRT 软字幕兜底（mov_text 嵌入容器，播放器可选显示）
                    subtitle_path = os.path.join(tmp_dir, "subtitles.srt")
                    srt_content = build_srt(clips_data)
                    with open(subtitle_path, "w", encoding="utf-8") as f:
                        f.write(srt_content)
                    subtitle_mode = "soft"
                    logger.info("[合成] project_id=%s 字幕模式: 软字幕(SRT) %d 条", project_id, len(clips_data))

        # 6. 最终合成：视频 + 音频 + 字幕（硬烧或软字幕嵌入）
        outputs_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "outputs", "projects", str(project_id),
        )
        os.makedirs(outputs_dir, exist_ok=True)
        output_path = os.path.join(outputs_dir, "final.mp4")

        logger.info(
            "[合成] project_id=%s 开始 ffmpeg 最终合成: video=%s audio=%s subtitle_mode=%s → %s",
            project_id, composite_video_path, composite_audio_path,
            subtitle_mode, output_path,
        )
        await _ffmpeg_final_composite(
            video_path=composite_video_path,
            audio_path=composite_audio_path,
            subtitle_path=subtitle_path,
            subtitle_mode=subtitle_mode,
            output_path=output_path,
            drawtext_filter=subtitle_drawtext_filter,
        )
        logger.info("[合成] project_id=%s ffmpeg 最终合成完成: %s", project_id, output_path)

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

        # 成片自动归档进资产库（旁路，失败仅记日志）
        try:
            from app.services.asset_archive import archive_final_video
            await archive_final_video(db, project.id, project.name, project.user_id, final_url)
        except Exception as fe:
            logger.error("[合成] 成片归档失败: project_id=%s error=%s", project_id, fe, exc_info=True)

        logger.info(
            "[合成] project_id=%s 合成成功: final_url=%s total_duration=%.2f",
            project_id, final_url, total_duration,
        )

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


# =====================================================
# 命令构造层：把 clip 字段 → ffmpeg 命令的转换收敛到此
# 后续新增能力（转场、特效、start_time 留白等）只改这里
# =====================================================

def _clip_trim_range(clip) -> tuple:
    """读取片段的裁剪起点与时长，集中默认值和边界处理。

    语义对齐预览端：成片中片段占据 [start_time, start_time+duration]，
    源素材取 [trim_start, trim_start+duration]。
    """
    trim_start = max(0.0, float(getattr(clip, "trim_start", 0.0) or 0.0))
    duration = max(0.1, float(getattr(clip, "duration", 0.0) or 0.0))
    return trim_start, duration


def _video_normalize_cmd(
    clip, src_path: str, out_path: str, width: int, height: int,
) -> List[str]:
    """构造视频归一化 + 裁剪截取命令。

    统一分辨率/帧率/SAR/像素格式（避免拼接失败），并按 trim_start/duration 截取源素材。
    """
    trim_start, duration = _clip_trim_range(clip)
    return [
        "ffmpeg", "-y",
        "-ss", f"{trim_start}",
        "-t", f"{duration}",
        "-i", src_path,
        "-vf", f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
               f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black,setsar=1,fps=30",
        "-c:v", "libx264", "-preset", "medium", "-crf", "23",
        "-pix_fmt", "yuv420p",
        "-an",  # 转场拼接阶段不需要音频，最终合成时再混入
        out_path,
    ]


async def _audio_clip_cmd(clip, src_path: str, out_path: str) -> List[str]:
    """构造音频裁剪截取命令（按 trim_start/duration 截取为 aac）。"""
    trim_start, duration = _clip_trim_range(clip)
    return [
        "ffmpeg", "-y",
        "-ss", f"{trim_start}",
        "-t", f"{duration}",
        "-i", src_path,
        "-c:a", "aac", "-b:a", "128k",
        out_path,
    ]


def _timeline_total_duration(clips: List) -> float:
    """按片段在时间线上的结束位置计算总时长。"""
    return max(
        (float(getattr(c, "start_time", 0.0) or 0.0) + float(getattr(c, "duration", 0.0) or 0.0) for c in clips),
        default=0.0,
    )


def _has_timeline_offsets(clips: List, epsilon: float = 0.05) -> bool:
    """判断片段 start_time 是否存在留白/偏移，存在时不能简单顺序拼接。"""
    cursor = 0.0
    for clip in sorted(clips, key=lambda c: float(getattr(c, "start_time", 0.0) or 0.0)):
        start = float(getattr(clip, "start_time", 0.0) or 0.0)
        duration = float(getattr(clip, "duration", 0.0) or 0.0)
        if abs(start - cursor) > epsilon:
            return True
        cursor = start + duration
    return False


async def _compose_videos_on_timeline(
    clips: List, normalized_paths: List[str], output_path: str, width: int, height: int,
) -> None:
    """用黑底画布按 start_time 放置片段，保留时间线空白。"""
    ordered = sorted(
        zip(clips, normalized_paths),
        key=lambda item: float(getattr(item[0], "start_time", 0.0) or 0.0),
    )
    total_duration = max(_timeline_total_duration(clips), 0.1)

    inputs: List[str] = [
        "-f", "lavfi",
        "-i", f"color=c=black:s={width}x{height}:r=30:d={total_duration}",
    ]
    for _, path in ordered:
        inputs.extend(["-i", path])

    filter_parts: List[str] = []
    base_label = "0:v"
    for idx, (clip, _) in enumerate(ordered, start=1):
        start = max(0.0, float(getattr(clip, "start_time", 0.0) or 0.0))
        duration = max(0.1, float(getattr(clip, "duration", 0.0) or 0.0))
        end = start + duration
        out_label = f"v{idx}"
        filter_parts.append(
            f"[{base_label}][{idx}:v]overlay=x=0:y=0:eof_action=pass:"
            f"enable='between(t,{start:.3f},{end:.3f})'[{out_label}]"
        )
        base_label = out_label

    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", ";".join(filter_parts),
        "-map", f"[{base_label}]",
        "-c:v", "libx264", "-preset", "medium", "-crf", "23",
        "-pix_fmt", "yuv420p",
        "-an",
        output_path,
    ]
    await _run_ffmpeg(cmd, timeout=900, error_label="ffmpeg 时间线视频合成")


async def _concat_videos_with_xfade(
    clips: List, video_paths: List[str], output_path: str, aspect_ratio: str
) -> None:
    """
    拼接视频片段，含 xfade 转场，并应用每个片段的裁剪（trim_start）与时长（duration）。

    策略:
    - 先对每个片段归一化（统一分辨率/帧率/SAR/像素格式）并按 trim_start/duration 截取
    - 单片段: 直接用归一化结果
    - 多片段 + 无转场: concat demuxer（-c copy）
    - 多片段 + 有转场: xfade 滤镜逐对拼接（reencode）

    语义对齐预览端：源素材取 [trim_start, trim_start+duration]。
    """
    if not video_paths:
        raise ValueError("无视频片段可拼接")

    width, height = _parse_resolution(aspect_ratio)

    # 第一步：归一化 + 按 trim_start/duration 截取每个片段（无转场/有转场共用）
    normalized_paths: List[str] = []
    for idx, p in enumerate(video_paths):
        clip = clips[idx] if clips and idx < len(clips) else None
        norm_path = output_path + f".norm_{idx:04d}.mp4"
        cmd = _video_normalize_cmd(clip, p, norm_path, width, height)
        await _run_ffmpeg(cmd, timeout=300, error_label=f"ffmpeg 视频归一化（片段 {idx}）")
        normalized_paths.append(norm_path)

    if _has_timeline_offsets(clips):
        await _compose_videos_on_timeline(clips, normalized_paths, output_path, width, height)
        return

    # 检查是否有转场（clips 和 paths 顺序对应）
    has_transition = any(
        getattr(clips[i], "transition_type", "none") not in ("none", "", None)
        and getattr(clips[i], "transition_duration", 0) > 0
        for i in range(min(len(clips), len(video_paths)))
    )

    # 无转场：归一化后参数一致，用 concat demuxer（-c copy，最快）
    if not has_transition:
        await _concat_normalized_videos(normalized_paths, output_path)
        return

    # 有转场：用 ffprobe 获取每个归一化片段的时长，再 xfade 逐对拼接
    durations = await _probe_durations(normalized_paths)

    # 逐对 xfade 拼接
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


async def _mix_audio_tracks(
    audio_clips: List,
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
    - 仅 TTS: 按每个片段 trim_start/duration 截取后 concat + afade
    - 仅 BGM: 取 BGM 文件，按 total_duration 截取
    - TTS + BGM: TTS 截取 concat + afade → 与 BGM amix（BGM 音量降低到 0.15）

    audio_clips 与 audio_paths 顺序对应，用于按 trim_start/duration 截取每个 TTS 片段。
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
        # 先按每个片段的 trim_start/duration 截取（语义对齐预览端：源素材取 [trim_start, trim_start+duration]）
        clipped_paths: List[str] = []
        for idx, p in enumerate(audio_paths):
            clip = audio_clips[idx] if audio_clips and idx < len(audio_clips) else None
            clipped_path = output_path + f".clip_{idx:04d}.aac"
            cmd_clip = _audio_clip_cmd(clip, p, clipped_path)
            await _run_ffmpeg(cmd_clip, timeout=300, error_label=f"ffmpeg TTS 截取（片段 {idx}）")
            clipped_paths.append(clipped_path)

        inputs: List[str] = []
        for p in clipped_paths:
            inputs.extend(["-i", p])

        filter_parts: List[str] = []
        delayed_labels: List[str] = []
        for idx, _ in enumerate(clipped_paths):
            clip = audio_clips[idx] if audio_clips and idx < len(audio_clips) else None
            start = max(0.0, float(getattr(clip, "start_time", 0.0) or 0.0))
            duration = max(0.1, float(getattr(clip, "duration", 0.0) or 0.0))
            delay_ms = int(start * 1000)
            fade_out_start = max(0, duration - 0.03)
            label = f"a{idx}"
            filter_parts.append(
                f"[{idx}:a]afade=t=in:st=0:d=0.03,"
                f"afade=t=out:st={fade_out_start:.3f}:d=0.03,"
                f"adelay={delay_ms}:all=1[{label}]"
            )
            delayed_labels.append(f"[{label}]")

        if len(delayed_labels) == 1:
            filter_parts.append(f"{delayed_labels[0]}anull[aout]")
        else:
            filter_parts.append(
                f"{''.join(delayed_labels)}amix=inputs={len(delayed_labels)}:"
                "duration=longest:dropout_transition=0[aout]"
            )

        cmd_fade = [
            "ffmpeg", "-y",
            *inputs,
            "-filter_complex", ";".join(filter_parts),
            "-map", "[aout]",
            "-c:a", "aac", "-b:a", "128k",
            output_path,
        ]
        await _run_ffmpeg(cmd_fade, timeout=300, error_label="ffmpeg TTS 时间线混音")
        return

    # TTS + BGM（amix 混音）
    # 1. 先处理 TTS（concat + 淡变）
    tts_processed_path = output_path + ".tts.aac"
    await _mix_audio_tracks(
        audio_clips=audio_clips,
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


async def _normalize_frame_image(
    src_path: str, duration: float,
    target_width: int, target_height: int, tmp_dir: str,
) -> str:
    """
    把静态图归一化为视频流（-loop 1 -i image -t duration -r 30）。

    复用视频归一化参数：scale+pad 到目标尺寸 + setsar=1 + fps=30，libx264 crf=23。
    用于 shot_frame_image 类型的片段：静态图按 duration 时长转成视频流后参与拼接。
    """
    out_path = os.path.join(tmp_dir, f"frame_{uuid4().hex}.mp4")
    # 归一化：scale+pad 到目标尺寸，30fps，libx264 crf=23，-t duration
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", src_path,
        "-t", str(duration),
        "-r", "30",
        "-vf", f"scale={target_width}:{target_height}:force_original_aspect_ratio=decrease,"
               f"pad={target_width}:{target_height}:(ow-iw)/2:(oh-ih)/2,setsar=1",
        "-c:v", "libx264", "-crf", "23", "-pix_fmt", "yuv420p",
        out_path,
    ]
    await _run_ffmpeg(cmd, timeout=300, error_label="ffmpeg 静态图归一化为视频流")
    return out_path
