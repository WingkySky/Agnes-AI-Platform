# =====================================================
# 剪辑渲染服务（Plan → media_compose lowering → 成片）
#
# 三层渲染的第二/三层：Plan → 单条 ffmpeg filter_complex 命令 → run_ffmpeg。
# 提交时快照（render_document）+ client_operation_id 幂等 + asyncio 后台任务，
# 进度写 render_progress（归一化 "k/n" / "composing"），前端轮询读取。
#
# 输入序模型（filter 里按序号引用）：
#   输入 0 = 黑底画布（lavfi color，仅有视频轨时存在）
#   随后 = 全部视频片段归一化文件（轨序 → 轨内片段序）
#   随后 = 全部音频源文件（audio_clips 序；含未静音视频片段的自带音频）
#
# 合成策略（v1 明确边界，与 plan_builder 对应）：
# - 全帧片段轨（rect 空/全帧）→ 轨内 xfade/concat 链后作为一层 overlay，
#   整链按轨锚点时间窗 enable（多轨互不遮盖）
# - 带 rect 的片段（PIP）→ 归一化时已缩放到 rect 尺寸，按文档位置窗口
#   enable overlay（PIP 片段间硬切，转场不生效）
# - 音频：逐段截取/atempo/volume/afade → adelay 定位 → amix；全帧轨自带音频按
#   压缩 render_start 开窗并以 acrossfade 融合转场衔接（audio_chains）；
#   视频自带音频（音画分离未分离时默认携带）需 ffprobe 确认真实含音流
# - 效果器：归一化阶段施加 hue=s=0（黑白）/ gblur（模糊，sigma=strength×20）
# - 字幕：build_ass + subtitles 滤镜硬烧
# - 成片落 uploads/editor/，final_url 挂工程并自动入资产库（source=compose）
# =====================================================

import asyncio
import logging
import os
import shutil
import uuid
from pathlib import Path
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session
from app.models.asset import Asset
from app.models.editing_project import (
    RENDER_FAILED,
    RENDER_RENDERING,
    RENDER_SUCCEEDED,
    EditingProject,
)
from app.services.editor.media_source import resolve_asset_local_file
from app.services.editor.plan_builder import build_plan, timeline_total
from app.services.media.subtitle_format import build_ass
from app.services.media_compose import run_ffmpeg
from app.services.upload_service import UPLOADS_DIR

logger = logging.getLogger("agnes_platform.editor.render")

EDITOR_OUTPUTS_DIR = os.path.join(UPLOADS_DIR, "editor")


def render_status_payload(project: EditingProject) -> dict:
    return {
        "render_status": project.render_status,
        "render_progress": project.render_progress,
        "final_url": project.final_url,
        "render_error": project.render_error,
    }


async def submit_render(db: AsyncSession, project: EditingProject, body: dict) -> dict:
    """提交渲染：rendering 中幂等返回；写快照后起后台任务。"""
    client_op = body.get("client_operation_id")
    if project.render_status == RENDER_RENDERING:
        return render_status_payload(project)
    if client_op and project.render_client_op_id == client_op and project.render_status == RENDER_SUCCEEDED:
        return render_status_payload(project)  # 同 op 重试：返回上次结果（幂等）

    if not (project.document or {}).get("clips"):
        raise HTTPException(status_code=400, detail="时间线为空，没有可渲染内容")

    project.render_document = project.document
    project.render_status = RENDER_RENDERING
    project.render_error = None
    project.render_progress = "0/0"
    project.render_client_op_id = client_op
    await db.commit()

    asyncio.create_task(_render_task(project.uid))
    return render_status_payload(project)


async def reset_stale_rendering(db: Optional[AsyncSession] = None) -> None:
    """应用启动时把上次进程中断遗留的 rendering 复位为 failed（lifespan 调用；可注入会话便于测试）。"""
    if db is None:
        async with async_session() as db:
            await reset_stale_rendering(db)
        return
    rows = (
        await db.scalars(select(EditingProject).where(EditingProject.render_status == RENDER_RENDERING))
    ).all()
    for project in rows:
        project.render_status = RENDER_FAILED
        project.render_error = "渲染进程中断，请重新导出"
        project.render_progress = None
    if rows:
        await db.commit()


async def _render_task(project_uid: str) -> None:
    """后台渲染（自建 session；任何异常落 failed + 错误尾部）。"""
    async with async_session() as db:
        project = (
            await db.scalars(select(EditingProject).where(EditingProject.uid == project_uid))
        ).first()
        if not project or project.render_status != RENDER_RENDERING:
            return
        try:
            await _render_project(db, project)
        except Exception as e:  # noqa: BLE001 — 后台任务兜底：失败态落库
            logger.exception("[剪辑渲染] 任务失败 uid=%s", project_uid)
            project.render_status = RENDER_FAILED
            project.render_error = str(e)[-2000:]
            project.render_progress = None
            await db.commit()


async def _render_project(db: AsyncSession, project: EditingProject) -> None:
    snapshot = project.render_document or project.document
    # 归一化/字幕/成片都写 uploads/editor/，缺目录会直接打不开输出文件
    os.makedirs(EDITOR_OUTPUTS_DIR, exist_ok=True)
    # 1. 素材本地化（远程先收口转存；失效片段剔除）
    asset_ids = {c["assetId"] for c in snapshot.get("clips", []) if isinstance(c.get("assetId"), int)}
    assets = {
        a.id: a
        for a in (
            await db.scalars(select(Asset).where(Asset.id.in_(asset_ids)))
        ).all()
        if a.user_id == project.user_id
    }
    paths: dict[int, str] = {}
    for asset in assets.values():
        local = await resolve_asset_local_file(asset, EDITOR_OUTPUTS_DIR)
        if local:
            paths[asset.id] = local
    plan = build_plan(
        snapshot,
        lambda aid: paths.get(aid),
        lambda aid: assets[aid].kind if aid in assets else None,
    )
    if plan is None:
        raise RuntimeError("没有可用素材片段（素材缺失或时长为 0）")

    # 音频候选过滤：视频自带音频需文件真实含音流（无声视频/纯画面素材剔除）
    probe_paths = sorted(
        {s["asset_path"] for s in plan["audio_clips"] if s.get("from_video")}
        | {m["asset_path"] for ch in plan.get("audio_chains", []) for m in ch["members"]}
    )
    probe_results = {p: await _has_audio_stream(p) for p in probe_paths}
    plan["audio_clips"] = [
        s for s in plan["audio_clips"]
        if not s.get("from_video") or probe_results.get(s["asset_path"], False)
    ]
    for chain in plan.get("audio_chains", []):
        chain["members"] = [
            m for m in chain["members"]
            if not m.get("from_video") or probe_results.get(m["asset_path"], False)
        ]

    # 2. 片段归一化（进度 k/n）
    plan, normalized = await _normalize_segments(db, project, plan)

    # 3. 字幕 ASS（有事件才烧录；document subtitleStyle → build_ass style 键映射）
    ass_path = None
    if plan["subtitle_events"]:
        style = plan.get("subtitle_style") or {}
        ass_events = [
            {"start_time": e["start"], "duration": e["end"] - e["start"], "text": e["text"]}
            for e in plan["subtitle_events"]
        ]
        ass_style = {
            "font_family": style.get("font") or "Noto Sans CJK SC",
            "font_size": int(style.get("size") or 48),
            "font_color": style.get("color") or "#FFFFFF",
            "outline_width": 2 if style.get("outline") else 0,
            "position": style.get("position") or "bottom",
        }
        ass_path = os.path.join(EDITOR_OUTPUTS_DIR, f"subs_{uuid.uuid4().hex[:12]}.ass")
        Path(ass_path).write_text(build_ass(ass_events, ass_style), encoding="utf-8")

    # 4. 终版合成
    project.render_progress = "composing"
    await db.commit()
    tmp_out = os.path.join(EDITOR_OUTPUTS_DIR, f".render_{uuid.uuid4().hex[:12]}.mp4")
    cmd = build_render_command(plan, normalized, ass_path, tmp_out)
    await run_ffmpeg(cmd, timeout=1800, error_label="剪辑渲染")

    # 5. 成片归属：落 uploads/editor + assets 入库 + final_url
    storage_key = f"editor/{uuid.uuid4().hex}.mp4"
    final_path = os.path.join(UPLOADS_DIR, storage_key)
    shutil.move(tmp_out, final_path)
    if ass_path and os.path.exists(ass_path):
        os.remove(ass_path)
    asset = Asset(
        type="final", name=f"{project.title} 成片", description=None, visual_description="",
        user_id=project.user_id, is_public=False, tags=[], version=1,
        source="compose", kind="video",
        asset_url=f"/uploads/{storage_key}", storage_key=storage_key,
        work_id=project.work_id,
    )
    db.add(asset)
    project.final_url = f"/uploads/{storage_key}"
    project.render_status = RENDER_SUCCEEDED
    project.render_progress = None
    project.render_error = None
    await db.commit()
    logger.info("[剪辑渲染] 完成 uid=%s → %s", project.uid, storage_key)


async def _has_audio_stream(path: str) -> bool:
    """ffprobe 探测文件是否含音频流（无声视频/纯画面素材不进音频图）"""
    try:
        proc = await asyncio.create_subprocess_exec(
            "ffprobe", "-v", "error", "-select_streams", "a",
            "-show_entries", "stream=index", "-of", "csv=p=0", path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=30)
        return bool(stdout.strip())
    except Exception:  # noqa: BLE001 — 探测失败按无声处理，不阻塞渲染
        logger.warning("[剪辑渲染] ffprobe 音流探测失败 %s", path)
        return False


async def _normalize_segments(db: AsyncSession, project: EditingProject, plan: dict) -> tuple[dict, dict[str, str]]:
    """逐片段截取+变速+归一化；进度写 render_progress。"""
    segs = [s for t in plan["video_tracks"] for s in t["segments"]]
    total = len(segs)
    normalized: dict[str, str] = {}
    for i, seg in enumerate(segs):
        out = os.path.join(EDITOR_OUTPUTS_DIR, f".norm_{uuid.uuid4().hex[:12]}.mp4")
        await run_ffmpeg(
            _segment_normalize_cmd(seg, plan["width"], plan["height"], plan["timebase"], out),
            timeout=900,
            error_label=f"片段归一化（{seg['clip_id']}）",
        )
        normalized[seg["clip_id"]] = out
        project.render_progress = f"{i + 1}/{total}"
        await db.commit()
    return plan, normalized


# =====================================================
# lowering：Plan → ffmpeg 命令（纯函数，黄金测试直测）
# =====================================================

def _even(v: float) -> int:
    return max(2, int(round(v / 2)) * 2)


def _is_full_frame(rect: Optional[dict]) -> bool:
    return not rect or (float(rect.get("w", 1)) >= 1 and float(rect.get("h", 1)) >= 1)


def _segment_normalize_cmd(seg: dict, width: int, height: int, fps: int, out_path: str) -> list[str]:
    """单片段截取 + 变速 + 效果器滤镜 + 归一化（无声，统一分辨率/帧率供 xfade/overlay）"""
    speed = seg["speed"]
    src_span = seg["duration"] * speed
    # 效果器在缩放前施加（避免模糊/去色波及 pad 出的黑边）
    vf: list[str] = [f"setpts=PTS/{speed}"]
    for e in seg.get("effects") or []:
        if not isinstance(e, dict):
            continue
        strength = min(max(float(e.get("strength") or 0), 0), 1)
        f = _effect_filter(str(e.get("type")), strength)
        if f:
            vf.append(f)
    vf.append(f"fps={fps}")
    rect = seg.get("rect")
    if rect and not _is_full_frame(rect):
        w = _even(width * float(rect.get("w", 1)))
        h = _even(height * float(rect.get("h", 1)))
        vf.append(f"scale={w}:{h}:force_original_aspect_ratio=decrease")
        vf.append(f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:black")
    else:
        vf.append(f"scale={width}:{height}:force_original_aspect_ratio=decrease")
        vf.append(f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black")
    vf.append("setsar=1")
    return [
        "ffmpeg", "-y",
        "-ss", f"{seg['trim_start']}",
        "-t", f"{src_span:.6f}",
        "-i", seg["asset_path"],
        "-vf", ",".join(vf),
        "-an",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-pix_fmt", "yuv420p",
        out_path,
    ]


def _xfade_name(transition_type: str) -> str:
    """Plan 转场类型 → ffmpeg xfade transition 名（与前端 editor-fx-registry 的 ffmpegName 对齐，新增转场两处各加一行）"""
    return {"crossfade": "fade", "fade": "fadeblack", "wipe": "wipeleft"}.get(transition_type, "fade")


def _effect_filter(effect_type: str, strength: float) -> Optional[str]:
    """效果器 → 归一化 vf 滤镜片段（与前端 editor-fx-registry 的 ffmpegFilter 对齐，新增效果器两处各加一行）"""
    if effect_type == "grayscale":
        return "hue=s=0"
    if effect_type == "blur":
        return f"gblur=sigma={strength * 20:.2f}" if strength > 0 else None
    return None


def _atempo_chain(speed: float) -> list[str]:
    """atempo 仅支持 0.5~2，链式拆分实现任意变速"""
    if speed == 1.0:
        return []
    factors: list[float] = []
    remaining = speed
    while remaining > 2.0:
        factors.append(2.0)
        remaining /= 2.0
    while remaining < 0.5:
        factors.append(0.5)
        remaining /= 0.5
    factors.append(round(remaining, 6))
    return [f"atempo={f}" for f in factors]


def _audio_filter_for(seg: dict) -> str:
    """单音频段滤镜：变速 → 音量 → fade"""
    parts: list[str] = []
    parts += _atempo_chain(seg["speed"])
    if seg["volume"] != 1.0:
        parts.append(f"volume={seg['volume']}")
    if seg["fade_in"] > 0:
        parts.append(f"afade=t=in:st=0:d={seg['fade_in']}")
    if seg["fade_out"] > 0:
        st = max(0.0, seg["duration"] - seg["fade_out"])
        parts.append(f"afade=t=out:st={st:.3f}:d={seg['fade_out']}")
    return ",".join(parts) if parts else "anull"


def build_render_command(
    plan: dict,
    normalized: dict[str, str],
    ass_path: Optional[str],
    output_path: str,
) -> list[str]:
    """Plan + 归一化产物 → 单条 ffmpeg 命令（黄金测试直测，不执行）。"""
    width, height, fps = plan["width"], plan["height"], plan["timebase"]
    total = timeline_total(plan)
    has_video = bool(plan["video_tracks"])

    cmd: list[str] = ["ffmpeg", "-y"]
    filters: list[str] = []
    input_index = 0

    # —— 视频输入与轨链 ——
    # 黑底基座在走 overlay 合成时需要；单条全帧轨直接作为成片视频流
    def _track_is_single_layer(track: dict) -> bool:
        segs = track["segments"]
        return bool(segs) and all(_is_full_frame(s.get("rect")) for s in segs)

    def _enable(start: float, end: float) -> str:
        return f":enable='between(t,{start:.3f},{end:.3f})'"

    overlay_layer_count = sum(
        1 if _track_is_single_layer(track) else len(track["segments"])
        for track in plan["video_tracks"]
    )
    direct_single = has_video and overlay_layer_count == 1
    needs_base = has_video and not direct_single

    overlay_items: list[tuple[str, int, int, str]] = []  # (label, x, y, enable)
    if needs_base:
        cmd += ["-f", "lavfi", "-i", f"color=c=black:s={width}x{height}:d={total:.6f}:r={fps}"]
        input_index += 1

    for track in plan["video_tracks"]:
        segs = track["segments"]
        if segs and all(_is_full_frame(s.get("rect")) for s in segs):
            # 整轨一条链：xfade（有转场）/ concat；整链按轨锚点的时间线窗口开合，
            # 多轨互不遮盖（上层轨只在自身窗口内可见）
            chain_in: Optional[str] = None
            consumed = 0.0
            for i, seg in enumerate(segs):
                cmd += ["-i", normalized[seg["clip_id"]]]
                label = f"[{input_index}:v]"
                input_index += 1
                if chain_in is None:
                    chain_in = label
                    consumed = seg["duration"]
                    continue
                trans = segs[i - 1].get("transition_applied")
                out_label = f"[trk{track['track_id']}_{i}]"
                if trans:
                    offset = max(consumed - trans["duration"], 0)
                    filters.append(
                        f"{chain_in}{label}xfade=transition={_xfade_name(trans['type'])}"
                        f":duration={trans['duration']:.3f}:offset={offset:.3f}{out_label}"
                    )
                    consumed = offset + seg["duration"]
                else:
                    filters.append(f"{chain_in}{label}concat=n=2:v=1:a=0{out_label}")
                    consumed += seg["duration"]
                chain_in = out_label
            chain_start = track["chain_start"]
            layer_label = chain_in
            if chain_start > 0:
                # overlay 副输入按 pts 对位主时间轴：链内容 pts 从 0 起，
                # 必须平移到轨锚点，否则窗口内只剩 eof 后的冻结末帧
                layer_label = f"[trk{track['track_id']}ts]"
                filters.append(f"{chain_in}setpts=PTS+{chain_start:.3f}/TB{layer_label}")
            overlay_items.append((layer_label, 0, 0, _enable(chain_start, chain_start + track["total"])))
        else:
            # PIP 轨：逐片段按绝对时间线窗口 overlay（同样先平移 pts）
            for seg in segs:
                cmd += ["-i", normalized[seg["clip_id"]]]
                label = f"[{input_index}:v]"
                input_index += 1
                rect = seg.get("rect") or {}
                x = int(width * float(rect.get("x", 0)))
                y = int(height * float(rect.get("y", 0)))
                if seg["render_start"] > 0:
                    shifted = f"[pip{input_index}]"
                    filters.append(f"{label}setpts=PTS+{seg['render_start']:.3f}/TB{shifted}")
                    label = shifted
                overlay_items.append((label, x, y, _enable(seg["render_start"], seg["render_start"] + seg["duration"])))

    # —— 音频输入 ——
    # 平铺段（音频轨 + PIP 轨自带音频）在前，各全帧轨压缩链成员随后（链序）
    flat_entries: list[tuple[int, dict]] = []
    for seg in plan["audio_clips"]:
        flat_entries.append((input_index, seg))
        cmd += ["-ss", f"{seg['trim_start']}", "-t", f"{seg['duration'] * seg['speed']:.6f}", "-i", seg["asset_path"]]
        input_index += 1
    chain_entries: list[list[tuple[int, dict]]] = []
    for chain in plan.get("audio_chains", []):
        entries: list[tuple[int, dict]] = []
        for m in chain["members"]:
            entries.append((input_index, m))
            cmd += ["-ss", f"{m['trim_start']}", "-t", f"{m['duration'] * m['speed']:.6f}", "-i", m["asset_path"]]
            input_index += 1
        chain_entries.append(entries)

    # —— overlay 链 ——
    final_v: Optional[str] = None
    if has_video:
        if direct_single:
            current = overlay_items[0][0]  # 单条全帧轨：直接作为成片视频
        else:
            current = "[0:v]"
            for i, (label, x, y, enable) in enumerate(overlay_items):
                out_label = f"[ov{i}]"
                filters.append(f"{current}{label}overlay={x}:{y}{enable}{out_label}")
                current = out_label
        # 字幕硬烧（挂在最终视频链上）
        if ass_path:
            escaped = ass_path.replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
            filters.append(f"{current}subtitles=filename='{escaped}'[vout]")
            final_v = "[vout]"
        else:
            final_v = current
    # 兜底：无视频轨但 needs_base 误判不应发生；空内容在上方已抛错

    # —— 音频混音 ——
    # 平铺段：滤镜 → adelay(文档位)；压缩链：相邻存活成员 acrossfade 融合为子链
    # （transition_in.from_clip_id 指向的前一成员须存活且相邻，否则切子链），
    # 子链起点按压缩 render_start adelay；全部汇入 amix
    delayed: list[str] = []
    audio_seq = 0

    def _member_filter_parts(seg: dict) -> list[str]:
        chain = _audio_filter_for(seg)
        parts = chain.split(",") if chain != "anull" else []
        # amix/acrossfade 要求各输入采样率/格式/声道一致（视频音轨 48k 与音频文件
        # 44.1k 混音前统一重采样，否则整条 filter graph 报错）
        parts.append("aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo")
        return parts

    for iidx, seg in flat_entries:
        parts = _member_filter_parts(seg)
        delay_ms = int(seg["render_start"] * 1000)
        if delay_ms > 0:
            parts.append(f"adelay={delay_ms}:all=1")
        out_label = f"[ad{audio_seq}]"
        filters.append(f"[{iidx}:a]{','.join(parts)}{out_label}")
        delayed.append(out_label)
        audio_seq += 1

    for entries in chain_entries:
        # 按成员顺序切子链
        subchains: list[list[tuple[int, dict]]] = []
        current: list[tuple[int, dict]] = []
        prev_member: Optional[dict] = None
        for iidx, m in entries:
            linked = (
                prev_member is not None
                and isinstance(m.get("transition_in"), dict)
                and m["transition_in"].get("from_clip_id") == prev_member.get("clip_id")
            )
            if current and linked:
                current.append((iidx, m))
            else:
                if current:
                    subchains.append(current)
                current = [(iidx, m)]
            prev_member = m
        if current:
            subchains.append(current)

        for sub in subchains:
            start_ms = int(sub[0][1]["render_start"] * 1000)
            if len(sub) == 1:
                iidx, seg = sub[0]
                parts = _member_filter_parts(seg)
                if start_ms > 0:
                    parts.append(f"adelay={start_ms}:all=1")
                out_label = f"[ad{audio_seq}]"
                filters.append(f"[{iidx}:a]{','.join(parts)}{out_label}")
                delayed.append(out_label)
            else:
                cur_label: Optional[str] = None
                for k, (iidx, seg) in enumerate(sub):
                    mid = f"[am{audio_seq}_{k}]"
                    filters.append(f"[{iidx}:a]{','.join(_member_filter_parts(seg))}{mid}")
                    if cur_label is None:
                        cur_label = mid
                        continue
                    trans = seg.get("transition_in") or {}
                    out = f"[ac{audio_seq}_{k}]"
                    filters.append(
                        f"{cur_label}{mid}acrossfade=d={float(trans.get('duration', 0)):.3f}"
                        f":c1=tri:c2=tri{out}"
                    )
                    cur_label = out
                if start_ms > 0:
                    out = f"[ac{audio_seq}_shift]"
                    filters.append(f"{cur_label}adelay={start_ms}:all=1{out}")
                    cur_label = out
                delayed.append(cur_label)
            audio_seq += 1

    if len(delayed) > 1:
        filters.append(f"{''.join(delayed)}amix=inputs={len(delayed)}:normalize=0[aout]")
        final_a = "[aout]"
    elif delayed:
        final_a = delayed[0]
    else:
        final_a = None

    if final_v:
        cmd += ["-map", final_v]
    if final_a:
        cmd += ["-map", final_a]
    if filters:
        cmd += ["-filter_complex", ";".join(filters)]
    if not final_v:
        cmd += ["-vn"]
    if final_v:
        cmd += ["-c:v", "libx264", "-preset", "medium", "-crf", "23", "-pix_fmt", "yuv420p"]
    if final_a:
        cmd += ["-c:a", "aac", "-b:a", "128k"]
    if not final_v and not final_a:
        raise RuntimeError("无可渲染内容")
    cmd += [output_path]
    return cmd
