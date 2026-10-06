# =====================================================
# 无限画布三节点（tts / subtitle / compose）Pydantic Schema
# 无状态接口：按节点 content 传参，不建表
# =====================================================

from typing import List, Optional
from pydantic import BaseModel, Field


class CanvasTtsRequest(BaseModel):
    """画布 TTS 请求（text 上游节点内容 + 音色/语速）"""
    text: str = Field(..., min_length=1, description="配音文本")
    voice: str = Field(default="default", description="音色：default/female/male 或 Edge 音色名")
    speed: float = Field(default=1.0, ge=0.5, le=2.0, description="语速倍率")


class CanvasTtsResponse(BaseModel):
    audio_url: str
    duration_ms: Optional[int] = None


class CanvasSubtitleRequest(BaseModel):
    """画布字幕请求（text 上游节点内容；audio_url 提供时走 whisper 真实时间戳）"""
    text: str = Field(..., min_length=1, description="待拆分的文案")
    max_chars: int = Field(default=20, ge=5, le=50, description="每条字幕最大字数")
    prompt: Optional[str] = Field(None, max_length=500, description="拆分补充要求（风格/节奏/禁用词等）")
    audio_url: Optional[str] = Field(None, max_length=2048, description="上游 TTS 音频 URL：提供时 whisper 转写出真实时间戳字幕，失败回退 LLM 拆分")


class CanvasSubtitleSegment(BaseModel):
    start_time: float
    duration: float
    text: str


class CanvasSubtitleResponse(BaseModel):
    srt: str
    segments: List[CanvasSubtitleSegment]
    total_duration: float


class CanvasComposeRequest(BaseModel):
    """画布合成请求（compose 节点连线收集的上游内容）"""
    video_urls: List[str] = Field(..., min_length=1, description="按顺序拼接的视频 URL")
    audios: Optional[List[str]] = Field(None, description="多段配音 URL（与视频段顺序对应，顺序拼接成单轨）")
    audio_url: Optional[str] = None
    subtitles: Optional[List[CanvasSubtitleSegment]] = None
    with_subtitle: bool = True
    bgm_id: Optional[str] = None
    aspect_ratio: str = Field(default="16:9", description="16:9 / 9:16 / 1:1 等")
    transition: str = Field(default="none", pattern="^(none|fade|dissolve|wipe|slide)$",
                            description="段间转场（非 none 且多段时走 xfade 重编码）")


class CanvasComposeResponse(BaseModel):
    video_url: str
    duration_ms: Optional[int] = None
