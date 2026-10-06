# =====================================================
# 剪辑语义 Plan 派生（document → Plan，纯函数）
#
# 三层渲染的第一层：document（前端权威） → Plan（渲染语义中间表示）；
# lowering（render_service）把 Plan 变成单条 ffmpeg 命令。本模块零 IO，
# 素材路径经 resolver 回调注入，方便黄金测试。
#
# 关键派生规则：
# - 时间线 gap 保留黑场（合成基座为黑底画布；整轨全帧链内除外——链内按连续压缩）
# - 同轨相邻片段转场配对：transition 挂在前一片段，与紧随其后的同轨片段生效
# - 输出时间窗：整轨全帧链锚定首片段文档位置（轨内转场压缩）；PIP 片段按文档
#   位置绝对开窗——多轨片段互不遮盖，视频与音频轴（adelay）同源
# - 音频图来源：音频轨片段 + 未静音视频片段的自带音频（音画分离：
#   detachAudio 后源片段 muted=true 剔出音频图）；无声视频由 lowering 层 ffprobe 过滤
# - 轨道开关（flags）：hidden 整轨剔除（画面/声音/字幕全不进成片）；muted 只剔声音；
#   solo 是前端预览监听态，渲染端刻意不读
# - 合成策略：全帧片段轨走 xfade 链整轨叠加；带 rect 的片段逐个按窗口 overlay
#   （PIP 片段间为硬切，转场仅在整轨 xfade 路径生效——v1 明确边界）
# =====================================================

from typing import Callable, Optional

from app.models.editing_project import EditingProject  # noqa: F401 — 语义引用（Plan 属剪辑工程域）

# Plan 片段
def _num(v, default=0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def build_plan(
    document: dict,
    resolve_path: Callable[[int], Optional[str]],
    resolve_asset_kind: Optional[Callable[[int], Optional[str]]] = None,
) -> Optional[dict]:
    """
    document → Plan。

    resolve_path(asset_id) → 本地路径或 None（None = 素材不可用，片段剔除；
    全部剔除时返回 None 表示无可渲染内容）。
    resolve_asset_kind(asset_id) → 素材类型（"video"/"audio"/"image"）；提供时，
    未静音的视频片段自带音频也进音频图（音画分离：分离后源片段标记 muted 剔出音频图）。
    """
    tracks = document.get("tracks") or []
    clips = document.get("clips") or []
    kind_of = {t.get("id"): t.get("kind") for t in tracks if isinstance(t, dict)}
    order_of = {t.get("id"): _num(t.get("order"), 0) for t in tracks if isinstance(t, dict)}
    # 轨道开关（前端 flags 字典，缺省全关）：hidden 整轨不进成片；
    # muted 只剔声音（视频轨画面照常）；solo 是预览监听态，渲染端刻意不读
    flags_of = {t.get("id"): (t.get("flags") or {}) for t in tracks if isinstance(t, dict)}

    video_tracks: dict[str, list[dict]] = {}
    audio_clips: list[dict] = []

    for clip in clips:
        if not isinstance(clip, dict):
            continue
        track_id = clip.get("trackId")
        flags = flags_of.get(track_id) or {}
        if flags.get("hidden") is True:
            continue  # 隐藏轨整轨剔除（视频/音频画面与声音都不进成片）
        asset_id = clip.get("assetId") if isinstance(clip.get("assetId"), int) else None
        path = resolve_path(asset_id) if asset_id is not None else None
        if not path:
            continue
        props = clip.get("props") or {}
        duration = _num(clip.get("duration"))
        if duration <= 0:
            continue  # 草稿占位（duration=0）不可渲染，剔除
        base = {
            "clip_id": clip.get("id"),
            "asset_id": asset_id,
            "asset_path": path,
            "start": _num(clip.get("start")),
            "duration": duration,
            "trim_start": _num(clip.get("trimStart")),
            "speed": _num(props.get("speed"), 1.0) or 1.0,
            "volume": _num(props.get("volume"), 1.0),
            "fade_in": _num(props.get("fadeIn")),
            "fade_out": _num(props.get("fadeOut")),
            "muted": props.get("muted") is True,
            "rect": props.get("rect") if isinstance(props.get("rect"), dict) else None,
            "transition": props.get("transition") if isinstance(props.get("transition"), dict) else None,
        }
        if kind_of.get(track_id) == "audio":
            if flags.get("muted") is True:
                continue  # 静音音频轨不进音频图
            audio_clips.append(base)
        elif kind_of.get(track_id) == "video":
            video_tracks.setdefault(track_id, []).append(base)
            # 音画分离：视频自带音频与音频轨同链混音；静音标记/轨静音/图片素材不进音频图
            if not base["muted"] and flags.get("muted") is not True \
                    and resolve_asset_kind is not None and resolve_asset_kind(asset_id) == "video":
                audio_clips.append({**base, "from_video": True})
        # subtitle clips 不进 Plan（字幕事件单独派生）

    # 视频轨：排序 + 输出时间窗派生
    # - 整轨全帧链：轨内连续（转场压缩生效），锚定首片段的文档时间线位置
    # - 含 PIP 片段的轨：逐片段按文档位置绝对开窗（PIP 硬切，无转场，轨内 gap 保留）
    # - total = 轨内容相对链锚点 chain_start 的跨度（timeline_total = chain_start + total）
    plan_tracks: list[dict] = []
    for track_id in sorted(video_tracks, key=lambda tid: order_of.get(tid, 0)):
        segs = sorted(video_tracks[track_id], key=lambda s: s["start"])
        full_frame_chain = all(
            (not s["rect"]) or (s["rect"].get("w", 1) >= 1 and s["rect"].get("h", 1) >= 1)
            for s in segs
        )
        if full_frame_chain:
            anchor = segs[0]["start"]
            cursor = anchor
            for i, seg in enumerate(segs):
                seg["render_start"] = round(cursor, 6)
                cursor += seg["duration"]
                nxt = segs[i + 1] if i + 1 < len(segs) else None
                if nxt and seg.get("transition"):
                    seg["transition_applied"] = {
                        "type": seg["transition"].get("type", "crossfade"),
                        "duration": min(_num(seg["transition"].get("duration"), 0.5),
                                        seg["duration"], nxt["duration"]),
                    }
                    cursor -= seg["transition_applied"]["duration"]
                else:
                    seg["transition_applied"] = None
            plan_tracks.append({
                "track_id": track_id,
                "order": order_of.get(track_id, 0),
                "chain_start": round(anchor, 6),
                "total": round(cursor - anchor, 6),
                "segments": segs,
            })
        else:
            for seg in segs:
                seg["render_start"] = round(seg["start"], 6)
                seg["transition_applied"] = None
            chain_start = segs[0]["render_start"] if segs else 0.0
            end = max((s["render_start"] + s["duration"] for s in segs), default=chain_start)
            plan_tracks.append({
                "track_id": track_id,
                "order": order_of.get(track_id, 0),
                "chain_start": round(chain_start, 6),
                "total": round(end - chain_start, 6),
                "segments": segs,
            })

    # 音频：按时间线 start 排（adelay 定位，转场不影响音频轴）
    audio_clips.sort(key=lambda s: s["start"])
    for seg in audio_clips:
        seg["render_start"] = seg["start"]

    # 字幕事件（text 片段；隐藏字幕轨不出字幕）
    subtitle_events = sorted(
        (
            {"start": _num(c.get("start")), "end": _num(c.get("start")) + _num(c.get("duration")),
             "text": str(c.get("text") or "").strip()}
            for c in clips
            if isinstance(c, dict) and c.get("text")
            and kind_of.get(c.get("trackId")) == "subtitle"
            and (flags_of.get(c.get("trackId")) or {}).get("hidden") is not True
        ),
        key=lambda e: e["start"],
    )

    if not plan_tracks and not audio_clips:
        return None

    return {
        "width": int(_num(document.get("width"), 1280)) or 1280,
        "height": int(_num(document.get("height"), 720)) or 720,
        "timebase": int(_num(document.get("timebase"), 30)) or 30,
        "video_tracks": plan_tracks,
        "audio_clips": audio_clips,
        "subtitle_events": subtitle_events,
        "subtitle_style": document.get("subtitleStyle") or {},
    }


def timeline_total(plan: dict) -> float:
    """成片总时长 = 各视频轨（锚点+跨度）与音频结束时间的最大值（下限 0.1）"""
    candidates = [t["chain_start"] + t["total"] for t in plan["video_tracks"]]
    candidates += [s["render_start"] + s["duration"] for s in plan["audio_clips"]]
    return max(candidates + [0.1])
