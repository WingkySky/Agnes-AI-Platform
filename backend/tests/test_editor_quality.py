# =====================================================
# 剪辑成片质检单测
# - 三检测器 stderr 解析（canned 日志，不执行 ffmpeg）
# - 刻意区间构建与 suspect 分类（fade/转场/图片静帧豁免）
# - 真实分析链路集成（skipif 守护：ffmpeg 生成纯黑+静音小视频全链）
# =====================================================

import asyncio
import shutil
import subprocess

import pytest

from app.services.editor.quality_check import (
    analyze_quality,
    build_intentional,
    classify_report,
    parse_detection_log,
)


def test_parse_blackdetect_and_freezedetect():
    log = (
        "[blackdetect @ 0x1] black_start:12 black_end:15.2 black_duration:3.2\n"
        "[freezedetect @ 0x1] freeze_start:5 freeze_duration:2.1\n"
    )
    issues = parse_detection_log(log)
    assert {"type": "black", "start": 12.0, "end": 15.2} in issues
    assert {"type": "freeze", "start": 5.0, "end": 7.1} in issues
    assert len(issues) == 2


def test_parse_silencedetect_pairs():
    log = (
        "[silencedetect @ 0x1] silence_start: 1.2\n"
        "[silencedetect @ 0x1] silence_end: 3.4 | silence_duration: 2.2\n"
        "[silencedetect @ 0x1] silence_start: 8\n"
    )
    issues = parse_detection_log(log)
    # 未配对的尾部 silence_start（到文件末尾）保守丢弃
    assert issues == [{"type": "silence", "start": 1.2, "end": 3.4}]


def test_parse_empty_log():
    assert parse_detection_log("frame= 100 fps=0.0 q=-1.0 Lsize=     1024kB time=00:00:04.00") == []


def _doc() -> dict:
    return {
        "tracks": [
            {"id": "v1", "kind": "video", "order": 0, "flags": {}, "transitions": [
                {"id": "t1", "afterClipId": "c1", "type": "fade", "duration": 1.0},
            ]},
        ],
        "clips": [
            {"id": "c1", "trackId": "v1", "assetId": 1, "start": 0, "duration": 4,
             "trimStart": 0, "props": {"fadeOut": 1.0}},
            {"id": "c2", "trackId": "v1", "assetId": 7, "start": 4, "duration": 3,
             "trimStart": 0, "props": {}},
            {"id": "c3", "trackId": "v1", "assetId": 9, "start": 7, "duration": 3,
             "trimStart": 0, "props": {}},
        ],
    }


IMAGE_ASSETS = {9}  # c3 为图片静帧


def test_build_intentional_windows():
    w = build_intentional(_doc(), IMAGE_ASSETS)
    # c1 fadeOut 1s → (3,4)；fade 转场接缝在 c1 末尾 4 → (3, 4.1)
    assert (3.0, 4.0) in w["fade"]
    assert (3.0, 4.1) in w["transition"]
    # 图片静帧 c3 → (7,10)
    assert (7.0, 10.0) in w["image"]


def test_classify_fade_black_not_suspect():
    w = build_intentional(_doc(), IMAGE_ASSETS)
    report = classify_report([{"type": "black", "start": 3.2, "end": 5.0}], w)
    assert report["available"] is True
    assert report["issues"][0]["suspect"] is False  # 落在 fadeOut/转场窗口


def test_classify_suspect_and_image_freeze():
    w = build_intentional(_doc(), IMAGE_ASSETS)
    report = classify_report([
        {"type": "black", "start": 10.0, "end": 12.0},
        {"type": "freeze", "start": 7.5, "end": 10.0},
        {"type": "freeze", "start": 0.5, "end": 3.0},
    ], w)
    by = {(i["type"], i["start"]): i["suspect"] for i in report["issues"]}
    assert by[("black", 10.0)] is True      # 刻意窗口外 → 疑似
    assert by[("freeze", 7.5)] is False     # 图片静帧覆盖 → 可能刻意
    assert by[("freeze", 0.5)] is True


def test_classify_silence_expected_and_fade():
    w = build_intentional(_doc(), IMAGE_ASSETS)
    issues = [{"type": "silence", "start": 3.5, "end": 6.0}, {"type": "silence", "start": 1.0, "end": 2.0}]
    report = classify_report(issues, w)
    by = {i["start"]: i["suspect"] for i in report["issues"]}
    assert by[3.5] is False   # fadeOut 窗口内
    assert by[1.0] is True
    # 无可听片段：静音全部可能刻意
    report2 = classify_report(issues, w, silent_expected=True)
    assert all(not i["suspect"] for i in report2["issues"])


FFMPEG = shutil.which("ffmpeg")


@pytest.mark.skipif(not FFMPEG, reason="ffmpeg 不可用")
def test_analyze_quality_real(tmp_path):
    """纯黑 + 静音小视频全链：报告可用且检出黑场/静音（无刻意区间 → suspect）。"""
    out = tmp_path / "qc.mp4"
    # 4 秒（> SILENCE_MIN_D=3）：纯黑 + 静音全片
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error",
         "-f", "lavfi", "-i", "color=black:s=64x64:d=4",
         "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
         "-shortest", "-c:v", "libx264", "-preset", "ultrafast", str(out)],
        check=True, capture_output=True, timeout=60,
    )
    report = asyncio.run(analyze_quality(str(out), None, set()))
    assert report["available"] is True
    types = {i["type"] for i in report["issues"]}
    assert "black" in types
    assert "silence" in types
    assert all(i["suspect"] for i in report["issues"])
