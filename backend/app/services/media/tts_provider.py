# =====================================================
# TTS provider 公共层（原 project/audio_service 内嵌实现转正公共域）
#
# 可插拔 provider:
#   - call_tts_provider 当前实现为 Edge TTS（免费直连，经 edge_tts 包）
#   - 后续可接入 Agnes 自有 TTS 或第三方（阿里云 / 字节火山 / ElevenLabs）
# =====================================================

import asyncio
import logging
import os
from typing import List, Optional

import edge_tts

from app.services.upload_service import UPLOADS_DIR, save_audio_bytes

logger = logging.getLogger("agnes_platform.media.tts")


# =====================================================
# 内置音色库
# 实际 provider 支持的音色 ID 在运行时由 provider 决定，
# 此处仅作为"默认分配策略"的候选清单与前端音色选择器数据源。
# =====================================================
BUILTIN_VOICES = [
    {"voice_id": "narrator_male_zh",   "name": "男声旁白",   "gender": "male",    "suitable_for": "旁白、男主"},
    {"voice_id": "narrator_female_zh", "name": "女声旁白",   "gender": "female",  "suitable_for": "旁白、女主"},
    {"voice_id": "young_male_zh",      "name": "年轻男声",   "gender": "male",    "suitable_for": "年轻男主"},
    {"voice_id": "young_female_zh",    "name": "年轻女声",   "gender": "female",  "suitable_for": "年轻女主"},
    {"voice_id": "mature_male_zh",     "name": "成熟男声",   "gender": "male",    "suitable_for": "成熟男性"},
    {"voice_id": "mature_female_zh",   "name": "成熟女声",   "gender": "female",  "suitable_for": "成熟女性"},
    {"voice_id": "child_zh",           "name": "童声",       "gender": "neutral", "suitable_for": "儿童"},
    {"voice_id": "elder_zh",           "name": "老年声",     "gender": "neutral", "suitable_for": "老年"},
]


def list_builtin_voices() -> List[dict]:
    """返回内置音色清单（供前端音色选择器）"""
    return BUILTIN_VOICES.copy()


# 内置音色 → Edge TTS 实际音色名映射（经 list_voices 实测，集中在此外可调）
EDGE_VOICE_MAP = {
    "narrator_male_zh":   "zh-CN-YunxiNeural",     # 阳光男声
    "narrator_female_zh": "zh-CN-XiaoxiaoNeural",  # 标准女声
    "young_male_zh":      "zh-CN-YunjianNeural",   # 年轻有力男声
    "young_female_zh":    "zh-CN-XiaoyiNeural",    # 年轻女声
    "mature_male_zh":     "zh-CN-YunyangNeural",   # 沉稳新闻男声
    "mature_female_zh":   "zh-CN-XiaoxiaoNeural",  # 暂无成熟女声音色，回落标准女声
    "child_zh":           "zh-CN-YunxiaNeural",    # 少年音（最接近童声）
    "elder_zh":           "zh-CN-YunyangNeural",   # 暂无老年音色，回落沉稳男声
}


def resolve_edge_voice(voice_id: str) -> str:
    """内置音色 → Edge TTS 音色名；已是 Edge 音色名（含 Neural）直接透传"""
    if "Neural" in voice_id:
        return voice_id
    return EDGE_VOICE_MAP.get(voice_id, "zh-CN-YunxiNeural")


async def _probe_duration_ms(file_path: str) -> Optional[int]:
    """ffprobe 探测音频时长（毫秒），失败返回 None 不阻塞入库"""
    try:
        proc = await asyncio.create_subprocess_exec(
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", file_path,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        out, _ = await proc.communicate()
        return int(float(out.decode().strip()) * 1000)
    except Exception as e:
        logger.warning("[TTS] ffprobe 时长探测失败: %s", e)
        return None


async def call_tts_provider(
    text: str,
    voice_id: str,
    model: Optional[str] = None,
    provider: Optional[str] = None,
    save_folder: Optional[str] = None,
    speed: float = 1.0,
) -> tuple:
    """
    调用 TTS provider 生成音频

    当前实现：Edge TTS（免费、无需 API Key，经 edge_tts 包直连）。
    音频落盘到 uploads 目录，返回可访问 URL。

    speed: 语速倍率（1.0 正常，0.5-2.0），经 Edge TTS rate 参数生效

    返回: (audio_url, duration_ms, file_size)
    """
    edge_voice = resolve_edge_voice(voice_id)
    rate = f"{int(round((speed - 1) * 100)):+d}%" if speed and abs(speed - 1.0) > 0.01 else None
    communicate = edge_tts.Communicate(text, edge_voice, rate=rate) if rate else edge_tts.Communicate(text, edge_voice)
    chunks: List[bytes] = []
    try:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                chunks.append(chunk["data"])
    except Exception as e:
        raise RuntimeError(f"Edge TTS 合成失败: {e}") from e

    audio_data = b"".join(chunks)
    if not audio_data:
        raise RuntimeError("Edge TTS 未返回音频数据")

    audio_url = await save_audio_bytes(
        audio_data,
        folder=save_folder or "projects/tts",
        ext=".mp3",
    )
    file_path = os.path.join(UPLOADS_DIR, audio_url.removeprefix("/uploads/"))
    duration_ms = await _probe_duration_ms(file_path)
    logger.info(
        "[TTS] Edge TTS 合成完成: voice=%s bytes=%s duration=%sms url=%s",
        edge_voice, len(audio_data), duration_ms, audio_url,
    )
    return audio_url, duration_ms, len(audio_data)
