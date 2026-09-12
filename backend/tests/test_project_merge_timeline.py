from types import SimpleNamespace

from app.services.project.merge_service import (
    _audio_clip_cmd,
    _has_timeline_offsets,
    _timeline_total_duration,
    _video_normalize_cmd,
)


def _clip(start=0.0, duration=2.0, trim_start=0.0):
    return SimpleNamespace(
        start_time=start,
        duration=duration,
        trim_start=trim_start,
    )


def test_video_normalize_cmd_uses_trim_start_and_clip_duration():
    cmd = _video_normalize_cmd(
        _clip(start=5.0, duration=1.5, trim_start=0.75),
        "/tmp/source.mp4",
        "/tmp/out.mp4",
        1280,
        720,
    )

    assert "-ss" in cmd
    assert cmd[cmd.index("-ss") + 1] == "0.75"
    assert "-t" in cmd
    assert cmd[cmd.index("-t") + 1] == "1.5"


def test_audio_clip_cmd_uses_trim_start_and_clip_duration():
    cmd = _audio_clip_cmd(
        _clip(start=3.0, duration=2.25, trim_start=0.5),
        "/tmp/source.mp3",
        "/tmp/out.aac",
    )

    assert cmd[cmd.index("-ss") + 1] == "0.5"
    assert cmd[cmd.index("-t") + 1] == "2.25"


def test_timeline_offsets_detect_gaps_and_non_zero_start():
    assert _has_timeline_offsets([_clip(start=1.0, duration=2.0)])
    assert _has_timeline_offsets([
        _clip(start=0.0, duration=2.0),
        _clip(start=4.0, duration=2.0),
    ])
    assert not _has_timeline_offsets([
        _clip(start=0.0, duration=2.0),
        _clip(start=2.0, duration=3.0),
    ])


def test_timeline_total_duration_uses_track_end():
    assert _timeline_total_duration([
        _clip(start=0.0, duration=2.0),
        _clip(start=5.0, duration=1.5),
    ]) == 6.5
