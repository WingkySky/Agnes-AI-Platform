# =====================================================
# 画布字幕 whisper 模式测试（audio_url → 转写真实时间戳 / 失败回退 LLM）
# 服务层直测（mock 转写与下载），不依赖 faster-whisper 安装
# =====================================================

import pytest

from app.services import canvas_media_service

pytestmark = pytest.mark.asyncio


async def test_whisper_mode_real_timestamps(monkeypatch):
    """audio_url + 转写成功：片段时间戳与文本来自转写结果"""
    async def fake_from_audio(audio_url: str):
        assert audio_url == "/uploads/a.wav"
        return [
            {"start_time": 0.0, "duration": 1.2, "text": "你来了。"},
            {"start_time": 1.2, "duration": 0.8, "text": "我等你好久了。"},
        ]
    monkeypatch.setattr(canvas_media_service, "_subtitles_from_audio", fake_from_audio)

    result = await canvas_media_service.generate_subtitles("台词", audio_url="/uploads/a.wav")
    assert result["total_duration"] == 2.0
    assert [s["text"] for s in result["segments"]] == ["你来了。", "我等你好久了。"]
    # SRT 时间码来自真实转写（非 0.24s/字估算）；毫秒受浮点截断影响允许 ±1ms
    assert "00:00:00,000 --> 00:00:01,19" in result["srt"]


async def test_whisper_fallback_to_llm(monkeypatch):
    """转写抛错/返回空：回退 LLM 拆分路径"""
    async def boom(audio_url: str):
        raise RuntimeError("download failed")
    monkeypatch.setattr(canvas_media_service, "_subtitles_from_audio", boom)

    async def fake_llm(text, max_chars=20, style_hint=None):
        return {
            "srt": "srt-from-llm", "segments": [{"start_time": 0.0, "duration": 1.0, "text": text}],
            "total_duration": 1.0,
        }
    monkeypatch.setattr(canvas_media_service, "_subtitles_from_llm", fake_llm)
    result = await canvas_media_service.generate_subtitles("台词兜底", audio_url="/uploads/a.wav")
    assert result["srt"] == "srt-from-llm"
    assert result["segments"][0]["text"] == "台词兜底"


async def test_no_audio_uses_llm(monkeypatch):
    """无 audio_url：直接走 LLM 拆分（原路径不变）"""
    async def fake_llm(text, max_chars=20, style_hint=None):
        return {"srt": "llm-only", "segments": [], "total_duration": 0.0}
    monkeypatch.setattr(canvas_media_service, "_subtitles_from_llm", fake_llm)
    result = await canvas_media_service.generate_subtitles("普通文案")
    assert result["srt"] == "llm-only"
