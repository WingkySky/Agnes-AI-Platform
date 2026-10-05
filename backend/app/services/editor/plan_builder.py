# =====================================================
# 剪辑语义 Plan 派生（document → Plan，纯函数）
#
# 三层渲染的第一层：document（前端权威） → Plan（渲染语义中间表示）；
# lowering（render_service）把 Plan 变成单条 ffmpeg 命令。本模块零 IO，
# 素材路径经 resolver 回调注入，方便黄金测试。
#
# 关键派生规则：
# - 时间线 gap 保留黑场（合成基座为黑底画布）
# - 同轨相邻片段转场配对：transition 挂在前一片段，与紧随其后的同轨片段生效
# - render_start：轨内前序片段时长累计减去与前序转场重叠（转场压缩时间线）
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


def build_plan(document: dict, resolve_path: Callable[[int], Optional[str]]) -> Optional[dict]:
    """
    document → Plan。

    resolve_path(asset_id) → 本地路径或 None（None = 素材不可用，片段剔除；
    全部剔除时返回 None 表示无可渲染内容）。
    """
    tracks = document.get("tracks") or []
    clips = document.get("clips") or []
    kind_of = {t.get("id"): t.get("kind") for t in tracks if isinstance(t, dict)}
    order_of = {t.get("id"): _num(t.get("order"), 0) for t in tracks if isinstance(t, dict)}

    video_tracks: dict[str, list[dict]] = {}
    audio_clips: list[dict] = []

    for clip in clips:
        if not isinstance(clip, dict):
            continue
        track_id = clip.get("trackId")
        path = resolve_path(clip["assetId"]) if isinstance(clip.get("assetId"), int) else None
        if not path:
            continue
        props = clip.get("props") or {}
        duration = _num(clip.get("duration"))
        if duration <= 0:
            continue  # 草稿占位（duration=0）不可渲染，剔除
        base = {
            "clip_id": clip.get("id"),
            "asset_path": path,
            "start": _num(clip.get("start")),
            "duration": duration,
            "trim_start": _num(clip.get("trimStart")),
            "speed": _num(props.get("speed"), 1.0) or 1.0,
            "volume": _num(props.get("volume"), 1.0),
            "fade_in": _num(props.get("fadeIn")),
            "fade_out": _num(props.get("fadeOut")),
            "rect": props.get("rect") if isinstance(props.get("rect"), dict) else None,
            "transition": props.get("transition") if isinstance(props.get("transition"), dict) else None,
        }
        if kind_of.get(track_id) == "audio":
            audio_clips.append(base)
        elif kind_of.get(track_id) == "video":
            video_tracks.setdefault(track_id, []).append(base)
        # subtitle clips 不进 Plan（字幕事件单独派生）

    # 视频轨：排序 + render_start 派生（转场压缩）
    plan_tracks: list[dict] = []
    for track_id in sorted(video_tracks, key=lambda tid: order_of.get(tid, 0)):
        segs = sorted(video_tracks[track_id], key=lambda s: s["start"])
        cursor = 0.0
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
            "total": round(cursor, 6),
            "segments": segs,
        })

    # 音频：按时间线 start 排（adelay 定位，转场不影响音频轴）
    audio_clips.sort(key=lambda s: s["start"])
    for seg in audio_clips:
        seg["render_start"] = seg["start"]

    # 字幕事件（text 片段）
    subtitle_events = sorted(
        (
            {"start": _num(c.get("start")), "end": _num(c.get("start")) + _num(c.get("duration")),
             "text": str(c.get("text") or "").strip()}
            for c in clips
            if isinstance(c, dict) and c.get("text") and kind_of.get(c.get("trackId")) == "subtitle"
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
    """成片总时长 = 各视频轨 total 与音频结束时间的最大值（下限 0.1）"""
    candidates = [t["total"] for t in plan["video_tracks"]]
    candidates += [s["render_start"] + s["duration"] for s in plan["audio_clips"]]
    return max(candidates + [0.1])
