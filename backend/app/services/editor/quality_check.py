# =====================================================
# 剪辑成片质检（渲染成功后单 pass 分析，best-effort 不阻塞渲染状态）
#
# ffmpeg 三检测器解析：blackdetect（黑场）/ freezedetect（冻结）/ silencedetect（静音）；
# 依渲染快照 document 计算「预期刻意」区间标注 suspect（疑似问题 vs 可能刻意）：
#   - 黑场/静音落在片段 fadeIn/fadeOut 窗口或 fade 转场接缝 → 可能刻意
#   - 冻结落在图片静帧素材覆盖段 → 可能刻意
# 报告挂 editing_projects.quality_report（JSON），render_status_payload 透出。
# =====================================================

import asyncio
import logging
import re

logger = logging.getLogger("agnes_platform.editor.quality")

BLACK_MIN_D = 0.5
FREEZE_MIN_D = 2.0
SILENCE_MIN_D = 3.0
ANALYZE_TIMEOUT = 300


def parse_detection_log(stderr: str) -> list[dict]:
    """解析三检测器 stderr → [{type, start, end}]（blackdetect/freezedetect 单行成对，
    silencedetect 为 silence_start / silence_end 两行配对）。"""
    issues: list[dict] = []
    for m in re.finditer(r"black_start:(\d+(?:\.\d+)?)[^\d]+black_end:(\d+(?:\.\d+)?)", stderr):
        issues.append({"type": "black", "start": float(m.group(1)), "end": float(m.group(2))})
    for m in re.finditer(r"freeze_start:(\d+(?:\.\d+)?)[^\d]+freeze_duration:(\d+(?:\.\d+)?)", stderr):
        start = float(m.group(1))
        issues.append({"type": "freeze", "start": start, "end": start + float(m.group(2))})
    pending_start: float | None = None
    for line in stderr.splitlines():
        m = re.search(r"silence_start:\s*(\d+(?:\.\d+)?)", line)
        if m:
            pending_start = float(m.group(1))
            continue
        m = re.search(r"silence_end:\s*(\d+(?:\.\d+)?)", line)
        if m and pending_start is not None:
            issues.append({"type": "silence", "start": pending_start, "end": float(m.group(1))})
            pending_start = None
    return issues


def build_intentional(document: dict | None, image_asset_ids: set[int]) -> dict:
    """从渲染快照文档汇总「预期刻意」区间（文档时间域）：
    fade_windows=片段淡入淡出（黑场/静音豁免）、transition_windows=fade 黑场转场接缝（黑场豁免）、
    image_windows=图片静帧片段覆盖段（冻结豁免）。"""
    fade_windows: list[tuple[float, float]] = []
    transition_windows: list[tuple[float, float]] = []
    image_windows: list[tuple[float, float]] = []
    clips = {c.get("id"): c for c in (document or {}).get("clips", []) if isinstance(c, dict)}
    for c in clips.values():
        props = c.get("props") or {}
        start = float(c.get("start") or 0)
        dur = float(c.get("duration") or 0)
        fi = float(props.get("fadeIn") or 0)
        fo = float(props.get("fadeOut") or 0)
        if fi > 0:
            fade_windows.append((start, start + fi))
        if fo > 0:
            fade_windows.append((max(0.0, start + dur - fo), start + dur))
        if isinstance(c.get("assetId"), int) and c["assetId"] in image_asset_ids:
            image_windows.append((start, start + dur))
    for track in (document or {}).get("tracks", []):
        if not isinstance(track, dict):
            continue
        for tr in track.get("transitions") or []:
            if not isinstance(tr, dict) or tr.get("type") != "fade":
                continue
            after = clips.get(tr.get("afterClipId"))
            if not after:
                continue
            junction = float(after.get("start") or 0) + float(after.get("duration") or 0)
            d = float(tr.get("duration") or 0)
            transition_windows.append((max(0.0, junction - d), junction + 0.1))
    return {"fade": fade_windows, "transition": transition_windows, "image": image_windows}


def _overlaps(win: tuple[float, float], windows: list[tuple[float, float]]) -> bool:
    return any(a < win[1] and b > win[0] for a, b in windows)


def classify_report(issues: list[dict], intentional: dict, silent_expected: bool = False) -> dict:
    """检测区间 + 刻意区间 → 质检报告（suspect=未命中刻意区间）。"""
    out: list[dict] = []
    for issue in issues:
        kind = issue["type"]
        win = (float(issue["start"]), float(issue["end"]))
        if kind == "black":
            suspect = not (_overlaps(win, intentional["fade"]) or _overlaps(win, intentional["transition"]))
        elif kind == "freeze":
            suspect = not _overlaps(win, intentional["image"])
        else:
            suspect = not silent_expected and not _overlaps(win, intentional["fade"])
        out.append({"type": kind, "start": round(win[0], 3), "end": round(win[1], 3), "suspect": suspect})
    out.sort(key=lambda i: (i["start"], i["type"]))
    return {"available": True, "issues": out}


async def _run_analysis(path: str) -> str:
    """单 pass 分析（-f null 不落产物），返回 stderr 检测日志。

    vf/af 链头部先做 pts 归零（setpts=PTS-STARTPTS / aresample first_pts=0）：
    ffmpeg 8 的 filter graph 时基可能带大偏移（实测 silence_start 输出 5.8e9 级
    绝对时间戳），不归零会让检测区间整体漂出成片时长。"""
    cmd = [
        "ffmpeg", "-nostats", "-i", path,
        "-vf", f"setpts=PTS-STARTPTS,blackdetect=d={BLACK_MIN_D},freezedetect=n=-60dB:d={FREEZE_MIN_D}",
        "-af", f"aresample=async=1:first_pts=0,silencedetect=n=-30dB:d={SILENCE_MIN_D}",
        "-f", "null", "-",
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await asyncio.wait_for(proc.communicate(), timeout=ANALYZE_TIMEOUT)
    return stderr.decode("utf-8", "replace")


async def _has_audio_stream(path: str) -> bool:
    try:
        proc = await asyncio.create_subprocess_exec(
            "ffprobe", "-v", "error", "-select_streams", "a",
            "-show_entries", "stream=index", "-of", "csv=p=0", path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=30)
        return bool(stdout.strip())
    except Exception:  # noqa: BLE001 — 探测失败按无声处理（静音项跳过，少误报）
        return False


async def analyze_quality(path: str, document: dict | None, image_asset_ids: set[int]) -> dict:
    """成片质检：分析 pass → 解析 → 刻意区间分类；任何失败降级 available=False。"""
    try:
        stderr = await _run_analysis(path)
        has_audio = await _has_audio_stream(path)
    except Exception as e:  # noqa: BLE001 — 质检软处理
        logger.warning("[剪辑质检] 分析失败 %s: %s", path, e)
        return {"available": False, "reason": str(e)[-200:]}
    issues = parse_detection_log(stderr)
    if not has_audio:
        issues = [i for i in issues if i["type"] != "silence"]
    return classify_report(issues, build_intentional(document, image_asset_ids))
