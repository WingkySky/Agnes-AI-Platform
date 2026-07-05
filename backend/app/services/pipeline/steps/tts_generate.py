# =====================================================
# TTS 语音合成步骤执行器
# 功能：
#   1. 从上游 LLM 步骤的 parsed_result.scenes 中提取每场戏的对白/旁白
#   2. 按角色分配不同声音（zh-CN 多角色 Neuron 声音）
#   3. 通过 TTS 适配层合成语音（优先 AGN-SDK，回退 edge-tts）
#   4. 输出音频文件路径供下游 ffmpeg_composite 步骤使用
#
# 适配层策略（_TTSProvider）：
#   - 优先用 AGN-SDK 的 Client(provider="edge-tts").speech()（用户自研统一 SDK，
#     https://github.com/WingkySky/AGN-SDK，已内置 Edge TTS adapter，免费无需 API Key）
#   - AGN-SDK 未安装时回退到直接使用 edge-tts 库（功能等价）
#   - 二者都不可用时抛错
#
# 依赖：agn-sdk[edge-tts]（requirements.txt 已声明）
#   - agn-sdk 会自动安装 edge-tts 作为依赖
#   - 也可单独安装 edge-tts 作为回退
# 声音列表：https://learn.microsoft.com/zh-cn/azure/ai-services/speech-service/language-support
#
# 输出：
#   {
#     "audios": [
#       {
#         "index": 0,
#         "audio_path": "/.../tts_run_1_seg_000.mp3",
#         "audio_url": "/api/pipeline/outputs/tts_run_1_seg_000.mp3",
#         "text": "对白内容",
#         "voice": "zh-CN-XiaoxiaoNeural",
#         "duration_seconds": 3.5,
#         "success": true,
#         "provider": "agn-sdk",
#         "words": [{"word": "对白", "start": 0.0, "end": 0.5}, ...]
#       }
#     ],
#     "total": 8,
#     "success_count": 8,
#     "failed_count": 0,
#     "subtitle_srt": "1\n00:00:00,000 --> 00:00:01,500\n对白内容\n...",
#     "subtitle_words": [{"word": "对白", "start": 0.0, "end": 0.5}, ...]
#   }
#
# 词级字幕（P0 视频后期处理增强）：
#   - edge-tts provider 调用时收集 WordBoundary 事件（offset/duration 单位 100ns，转秒）
#   - 按句末标点（。！？.!?）切分，单段超 7 词时按二分切分（保证不超过 7 词）
#   - subtitle_words: 全局时间轴的词级时间戳（按音频时长累计偏移）
#   - subtitle_srt: 按分组规则生成的细粒度 SRT 字符串
#   - 非 edge-tts provider（如 pyttsx3 离线兜底）跳过词级收集，沿用 duration_seconds 生成兜底字幕
# =====================================================

import asyncio
import logging
import os
import re
import sys
from typing import Dict, Any, List, Optional

from app.services.pipeline.steps import register_step_executor
from app.services.pipeline.steps.base import (
    BaseStepExecutor,
    SingleItemContext,
    ItemResult,
)

logger = logging.getLogger("agnes_platform.pipeline")

# ---------- TTS 提供方探测 ----------
# 优先用 AGN-SDK（用户自研统一 SDK，已内置 Edge TTS adapter）
# AGN-SDK 安装后会自动带入 edge-tts 作为依赖，无需单独装 edge-tts
# 自 AGN-SDK 1.1.0 起，Client 对 edge-tts 这类免费 provider 不再强制校验 api_key
try:
    from agn import Client as _AgnesSDKClient  # noqa: F401
    _HAS_AGN_SDK = True
    logger.info("[TTS] 检测到 AGN-SDK，将优先使用其 Edge TTS adapter")
except ImportError:
    _HAS_AGN_SDK = False
    logger.debug("[TTS] AGN-SDK 未安装，将尝试直接使用 edge-tts 回退方案")

# 回退方案：直接使用 edge-tts（与 AGN-SDK 的 edge-tts adapter 功能等价）
try:
    import edge_tts
    _HAS_EDGE_TTS = True
except ImportError:
    _HAS_EDGE_TTS = False
    logger.warning("[TTS] edge-tts 未安装；如 AGN-SDK 也未安装，tts_generate 步骤将无法执行")

# 最终音频输出目录（与 ffmpeg_composite 共用，通过 /api/pipeline/outputs/ 路由访问）
_OUTPUT_BASE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))),
    "data", "pipeline_outputs",
)
os.makedirs(_OUTPUT_BASE, exist_ok=True)

# 默认中文角色声音池（按性别分组）
# 参考：https://learn.microsoft.com/zh-cn/azure/ai-services/speech-service/language-support
#
# 注意：edge-tts 服务端会动态下线声音，可用声音以 edge_tts.list_voices() 实时返回为准。
#   截至 2026-06-26，以下声音已被微软官方下线（调用会抛 NoAudioReceived）：
#     - zh-CN-XiaochenNeural（女，成熟）
#     - zh-CN-XiaohanNeural（女，甜美）
#     - zh-CN-YunfengNeural（男，低沉）
#   当前 zh-CN 可用标准声音（非方言）共 6 个：4 男 2 女。
#   女声偏少，多女性角色场景会自动轮换复用（_build_voice_mapping 中的模运算）。
_DEFAULT_MALE_VOICES = [
    "zh-CN-YunxiNeural",      # 男，年轻，温柔
    "zh-CN-YunyangNeural",    # 男，成熟，播音
    "zh-CN-YunjianNeural",    # 男，运动，阳光
    "zh-CN-YunxiaNeural",     # 男，少年，清澈
]
_DEFAULT_FEMALE_VOICES = [
    "zh-CN-XiaoxiaoNeural",   # 女，温柔，主播音
    "zh-CN-XiaoyiNeural",     # 女，活泼
]
# 旁白/叙述默认声音（用最稳定的主播音女声，避免下线风险）
_DEFAULT_NARRATOR_VOICE = "zh-CN-XiaoxiaoNeural"

# pyttsx3 离线 TTS 兜底（可选依赖）
_HAS_PYTTSX3 = False
_pyttsx3: Any = None  # 模块级引用，auto-install 后注入
try:
    import pyttsx3 as _pyttsx3
    _HAS_PYTTSX3 = True
except ImportError:
    pass

# 单例锁，保证 pyttsx3 引擎只初始化一次
_pyttsx3_lock = asyncio.Lock()
_pyttsx3_engine: Optional[Any] = None
# pip install 串行锁，防止多个协程同时 pip install 导致竞争失败
_pyttsx3_install_lock = asyncio.Lock()


async def _get_pyttsx3_engine():
    """惰性初始化 pyttsx3 引擎（线程安全）"""
    global _pyttsx3_engine
    if _pyttsx3_engine is not None:
        return _pyttsx3_engine
    async with _pyttsx3_lock:
        if _pyttsx3_engine is not None:
            return _pyttsx3_engine
        if not _HAS_PYTTSX3 or _pyttsx3 is None:
            raise RuntimeError("pyttsx3 未安装，无法使用离线 TTS 兜底")
        # pyttsx3.init() 是同步阻塞调用，在线程池中运行避免阻塞事件循环
        _pyttsx3_engine = await asyncio.to_thread(_pyttsx3.init)
        # 降低比特率加快合成速度（默认 200，降到 150 可接受）
        _pyttsx3_engine.setProperty('rate', 150)
        logger.info("[TTS] pyttsx3 离线引擎初始化完成")
        return _pyttsx3_engine


async def _ensure_pyttsx3() -> bool:
    """确保 pyttsx3 可用，不可用时尝试自动安装（串行锁防竞争）"""
    global _HAS_PYTTSX3, _pyttsx3
    if _HAS_PYTTSX3 and _pyttsx3 is not None:
        return True
    async with _pyttsx3_install_lock:
        # 双重检查：可能在上一个协程安装完成后释放锁
        if _HAS_PYTTSX3 and _pyttsx3 is not None:
            return True
        logger.info("[TTS] pyttsx3 未安装，尝试自动安装...")
        try:
            proc = await asyncio.create_subprocess_exec(
                sys.executable, "-m", "pip", "install", "pyttsx3",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=30.0)
            if proc.returncode == 0:
                # 注入到模块全局，确保所有函数都能访问
                import pyttsx3 as _installed
                _pyttsx3 = _installed
                _HAS_PYTTSX3 = True
                logger.info("[TTS] pyttsx3 安装成功")
                return True
            else:
                err_text = stderr.decode(errors="replace")[:200] if stderr else ""
                logger.warning(f"[TTS] pyttsx3 安装失败 (code={proc.returncode}): {err_text}")
                return False
        except Exception as e:
            logger.warning(f"[TTS] pyttsx3 安装异常: {e}")
            return False


# =====================================================
# 词级字幕生成工具
# 用于将 edge-tts WordBoundary 事件转为 SRT 字幕段落
# =====================================================

# 句末标点（中英文）：用于将词列表切分为字幕段落
_SENTENCE_END_PUNCT = "。！？.!?"


def _split_long_segment(
    words: List[Dict[str, Any]],
    max_words: int = 7,
) -> List[List[Dict[str, Any]]]:
    """将超长词列表二分切分，保证每段不超过 max_words

    递归二分：每次从中点切分，直到每段长度 <= max_words。
    用于在按标点切分后仍有段落超过 7 词时进行二次切分。
    """
    if len(words) <= max_words:
        return [words]
    mid = len(words) // 2
    left = words[:mid]
    right = words[mid:]
    return _split_long_segment(left, max_words) + _split_long_segment(right, max_words)


def _group_words_to_subtitles(
    words: List[Dict[str, Any]],
    max_words: int = 7,
) -> List[Dict[str, Any]]:
    """将词级时间戳分组为字幕段落

    分组规则：
    1. 按句末标点（。！？.!?）切分为初段
    2. 单段超过 max_words 时按二分切分，保证每段不超过 max_words

    每段字幕：
    - start = 第一个词的 start
    - end = 最后一个词的 end
    - text = 拼接所有词
    """
    if not words:
        return []

    # 步骤1：按句末标点切分
    segments: List[List[Dict[str, Any]]] = []
    current: List[Dict[str, Any]] = []
    for w in words:
        current.append(w)
        word_text = w.get("word", "")
        # 词尾含句末标点时切分
        if word_text and word_text[-1] in _SENTENCE_END_PUNCT:
            segments.append(current)
            current = []
    if current:
        segments.append(current)

    # 步骤2：超长段落二分切分
    final_segments: List[List[Dict[str, Any]]] = []
    for seg in segments:
        final_segments.extend(_split_long_segment(seg, max_words))

    # 步骤3：生成字幕段落（start/end 来自词级时间戳）
    subtitles: List[Dict[str, Any]] = []
    for seg in final_segments:
        if not seg:
            continue
        text = "".join(w.get("word", "") for w in seg)
        start = float(seg[0].get("start", 0.0))
        end = float(seg[-1].get("end", start))
        subtitles.append({
            "start": start,
            "end": end,
            "text": text,
        })
    return subtitles


def _format_srt_time(seconds: float) -> str:
    """格式化秒数为 SRT 时间格式 HH:MM:SS,mmm"""
    if seconds < 0:
        seconds = 0.0
    total_ms = int(round(seconds * 1000))
    hours = total_ms // 3_600_000
    minutes = (total_ms % 3_600_000) // 60_000
    secs = (total_ms % 60_000) // 1000
    millis = total_ms % 1000
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def _build_srt(subtitles: List[Dict[str, Any]]) -> str:
    """从字幕段落生成 SRT 格式字符串

    SRT 格式：
        1
        HH:MM:SS,mmm --> HH:MM:SS,mmm
        字幕文本

        2
        ...
    """
    if not subtitles:
        return ""
    lines: List[str] = []
    for i, sub in enumerate(subtitles, 1):
        lines.append(str(i))
        start_str = _format_srt_time(float(sub.get("start", 0.0)))
        end_str = _format_srt_time(float(sub.get("end", 0.0)))
        lines.append(f"{start_str} --> {end_str}")
        lines.append(str(sub.get("text", "")))
        lines.append("")  # 空行分隔
    return "\n".join(lines).strip()


async def _collect_edge_tts_audio_and_words(
    text: str,
    voice: str,
    rate: str,
    output_path: str,
) -> tuple:
    """通过 edge-tts.stream() 同时收集音频和 WordBoundary 词级时间戳

    edge-tts 的 WordBoundary 事件携带 offset + duration（单位 100ns），
    转为秒后返回。当 edge-tts 服务未返回 WordBoundary 事件时，
    返回空列表（不报错，沿用现有时间字段生成字幕）。

    Returns:
        (success, word_boundaries)
        word_boundaries: [{"word": str, "start": float, "end": float}, ...]
        start/end 单位为秒，相对本段 TTS 起始
    """
    communicate = edge_tts.Communicate(text, voice, rate=rate)
    word_boundaries: List[Dict[str, Any]] = []
    audio_chunks: List[bytes] = []
    try:
        async for event in communicate.stream():
            ev_type = event.get("type")
            if ev_type == "audio":
                audio_chunks.append(event.get("data", b""))
            elif ev_type == "WordBoundary":
                # edge-tts offset/duration 单位为 100ns，需转为秒
                offset_ns = int(event.get("offset", 0))
                duration_ns = int(event.get("duration", 0))
                offset_sec = offset_ns / 10_000_000
                duration_sec = duration_ns / 10_000_000
                word_boundaries.append({
                    "word": event.get("text", ""),
                    "start": offset_sec,
                    "end": offset_sec + duration_sec,
                })
    except Exception as e:
        # stream 异常时已收集的部分仍可使用，但需标记失败
        logger.warning(f"[TTS] edge-tts stream 异常: {e}")
        return False, word_boundaries

    # 写入音频文件
    try:
        with open(output_path, "wb") as f:
            for chunk in audio_chunks:
                f.write(chunk)
    except Exception as e:
        logger.warning(f"[TTS] 写入音频文件失败: {e}")
        return False, word_boundaries

    success = os.path.exists(output_path) and os.path.getsize(output_path) > 0
    return success, word_boundaries


# =====================================================
# TTS 提供方抽象（适配层）
# 统一接口：synthesize(text, voice, rate, output_path)
# 子类：_AgnSdkTTSProvider / _EdgeTTSProvider
# 未来切换 AGN-SDK 只需保证它满足此接口即可
# =====================================================

class _TTSProvider:
    """TTS 提供方抽象基类"""

    name = "base"

    async def synthesize(
        self,
        text: str,
        voice: str,
        rate: str,
        output_path: str,
    ) -> bool:
        """
        合成语音并保存到 output_path。

        Args:
            text: 待合成文本
            voice: 声音 ID（如 zh-CN-XiaoxiaoNeural）
            rate: 语速（如 "+0%"、"-10%"）
            output_path: 输出文件路径（.mp3）

        Returns:
            是否合成成功
        """
        raise NotImplementedError

    async def synthesize_with_subtitles(
        self,
        text: str,
        voice: str,
        rate: str,
        output_path: str,
    ) -> tuple:
        """
        合成语音并同时收集词级时间戳（用于生成 SRT 字幕）

        默认实现：调用 synthesize 并返回空词列表。
        支持 WordBoundary 事件的 provider（如 edge-tts）重写此方法。

        Returns:
            (success, word_boundaries)
            word_boundaries: [{"word": str, "start": float, "end": float}, ...]
            start/end 单位为秒，相对本段 TTS 起始
        """
        success = await self.synthesize(text, voice, rate, output_path)
        return success, []


class _AgnSdkTTSProvider(_TTSProvider):
    """
    AGN-SDK TTS 提供方（使用 Edge TTS adapter，免费无需 API Key）

    通过 AGN-SDK 的统一 Client 接口调用 Edge TTS：
        Client(provider="edge-tts").speech(...)
    底层使用 edge-tts 库，与直接调 edge-tts 功能等价，
    但统一在 AGN-SDK 体系下，便于未来扩展其他 TTS Provider（ElevenLabs 等）。

    注意：自 AGN-SDK 1.1.0 起，Client 才对 edge-tts 这类免费 provider 跳过 api_key 校验。
    """
    name = "agn-sdk"

    def __init__(self):
        # 延迟初始化 client，避免在导入时就触发 edge-tts 依赖检查
        self._client: Optional[_AgnesSDKClient] = None
        self._started: bool = False

    async def _ensure_client(self) -> _AgnesSDKClient:
        """惰性初始化并启动 client（首次调用时触发）"""
        if self._client is None:
            # Edge TTS 免费，无需 API Key（AGN-SDK >=1.1.0 已正确处理）
            self._client = _AgnesSDKClient(provider="edge-tts")
        if not self._started:
            await self._client.start()
            self._started = True
        return self._client

    async def synthesize(
        self,
        text: str,
        voice: str,
        rate: str,
        output_path: str,
    ) -> bool:
        """
        调用 AGN-SDK 合成语音

        Client.speech() 签名：
            speech(model, input, voice='', **kwargs) -> SpeechResult
        通过 **kwargs 传 rate（格式如 "+0%" / "-10%"），与直接调
        edge_tts.Communicate(rate=...) 完全一致。

        返回 SpeechResult，有 save_to_file(path) 方法可直接保存。
        """
        client = await self._ensure_client()
        result = await client.speech(
            model="edge-tts",
            input=text,
            voice=voice,            # 完整 ID 如 "zh-CN-XiaoxiaoNeural"
            response_format="mp3",
            rate=rate,              # 通过 **kwargs 透传给 edge-tts adapter
        )
        # SpeechResult.save_to_file() 内部调用 get_audio_bytes() 并写文件
        result.save_to_file(output_path)
        return os.path.exists(output_path) and os.path.getsize(output_path) > 0

    async def synthesize_with_subtitles(
        self,
        text: str,
        voice: str,
        rate: str,
        output_path: str,
    ) -> tuple:
        """
        合成语音并收集词级时间戳

        AGN-SDK 的 SpeechResult 未直接暴露 WordBoundary 事件，
        因此在需要词级字幕时直接走 edge-tts 路径收集
        （底层与 AGN-SDK 等价，仅音频来源切换为直连 edge-tts）。
        edge-tts 不可用时回退到默认实现（无词级时间戳）。
        """
        if _HAS_EDGE_TTS:
            return await _collect_edge_tts_audio_and_words(
                text, voice, rate, output_path
            )
        # edge-tts 不可用时，回退到默认实现（无词级时间戳）
        return await super().synthesize_with_subtitles(text, voice, rate, output_path)

    async def close(self) -> None:
        """关闭 client 释放资源（应用退出时调用）"""
        if self._client is not None and self._started:
            try:
                await self._client.close()
            except Exception:
                pass
            self._started = False


class _EdgeTTSProvider(_TTSProvider):
    """edge-tts TTS 提供方（当前可用的回退方案）"""

    name = "edge-tts"

    async def synthesize(
        self,
        text: str,
        voice: str,
        rate: str,
        output_path: str,
    ) -> bool:
        """调用 edge-tts 合成语音"""
        communicate = edge_tts.Communicate(text, voice, rate=rate)
        await communicate.save(output_path)
        return os.path.exists(output_path) and os.path.getsize(output_path) > 0

    async def synthesize_with_subtitles(
        self,
        text: str,
        voice: str,
        rate: str,
        output_path: str,
    ) -> tuple:
        """通过 edge-tts.stream() 同时收集音频和 WordBoundary 词级时间戳

        edge-tts 的 WordBoundary 事件携带 offset + duration（单位 100ns），
        转为秒后返回。当 edge-tts 服务未返回 WordBoundary 事件时，
        返回空列表（不报错）。
        """
        return await _collect_edge_tts_audio_and_words(
            text, voice, rate, output_path
        )


# TTS 提供方单例（避免每次合成都新建 client，未来 AGN-SDK client 可复用连接）
_tts_provider_instance: Optional[_TTSProvider] = None


def _get_tts_provider() -> _TTSProvider:
    """
    按优先级获取可用的 TTS 提供方（单例）：
    1. AGN-SDK（如果已安装且 TTS 已实现）
    2. edge-tts（回退方案）

    返回的 provider 满足统一的 synthesize(text, voice, rate, output_path) 接口。
    """
    global _tts_provider_instance
    if _tts_provider_instance is not None:
        return _tts_provider_instance

    if _HAS_AGN_SDK:
        _tts_provider_instance = _AgnSdkTTSProvider()
    elif _HAS_EDGE_TTS:
        _tts_provider_instance = _EdgeTTSProvider()
    else:
        raise RuntimeError(
            "没有可用的 TTS 提供方：AGN-SDK 未安装/未实现 TTS，edge-tts 也未安装。"
            "请安装 edge-tts: pip install edge-tts"
        )
    logger.info(f"[TTS] 使用 TTS 提供方: {_tts_provider_instance.name}")
    return _tts_provider_instance


@register_step_executor
class TTSGenerateExecutor(BaseStepExecutor):
    """
    TTS 语音合成步骤执行器

    从上游 LLM 步骤的 parsed_result.scenes 中提取每场戏的对白，
    按角色分配声音，通过 TTS 适配层合成每个分镜对应的 MP3 音频文件。

    适配层优先用 AGN-SDK（用户自研统一 SDK），不可用时回退到 edge-tts。
    """

    step_type = "tts_generate"

    async def validate(self) -> None:
        """验证输入：必须指定 from_step，至少有一个 TTS 提供方可用"""
        config = self.config.get("config", {})
        from_step = config.get("from_step")
        if not from_step:
            raise ValueError("tts_generate 必须指定 from_step（上游 LLM 步骤）")

        # 检查是否有可用的 TTS 提供方
        if not _HAS_AGN_SDK and not _HAS_EDGE_TTS:
            raise ValueError(
                "没有可用的 TTS 提供方。"
                "请安装 edge-tts: pip install edge-tts"
            )

    async def execute(self) -> Dict[str, Any]:
        """执行 TTS 合成"""
        config = self.config.get("config", {})
        from_step = config.get("from_step")
        text_field = config.get("text_field", "dialogue")  # 取哪个字段作为 TTS 文本
        default_voice = config.get("default_voice", _DEFAULT_NARRATOR_VOICE)
        rate = config.get("rate", "+0%")  # 语速调整
        max_concurrent = config.get("max_concurrent", 2)  # 并发合成数（edge-tts 偶发限流，2 较稳）

        # 1. 从上游步骤获取解析结果
        step_output = self.context.steps_output.get(from_step, {})
        parsed_result = step_output.get("parsed_result")

        if parsed_result is None:
            raw_response = step_output.get("raw_response", "")
            raise ValueError(
                f"上游步骤 '{from_step}' 的 parsed_result 为空，"
                f"无法提取 TTS 文本（raw_response 长度={len(raw_response)}）。"
                f"可能是 LLM 输出 JSON 解析失败。"
            )

        if not isinstance(parsed_result, dict):
            raise ValueError(f"上游步骤 '{from_step}' 的 parsed_result 不是字典")

        # 2. 提取场景列表
        scenes = parsed_result.get("scenes", []) or []
        if not scenes:
            logger.warning(f"[TTS] 上游步骤没有 scenes，跳过: step_key={self.step_key}")
            return {
                "audios": [],
                "total": 0,
                "success_count": 0,
                "failed_count": 0,
                "subtitle_srt": "",
                "subtitle_words": [],
            }

        # 3. 提取角色列表（用于声音分配）
        characters = parsed_result.get("characters", []) or []
        voice_mapping = self._build_voice_mapping(characters, config)

        # 4. 构建每场戏的 TTS 任务
        tts_tasks: List[Dict[str, Any]] = []
        for idx, scene in enumerate(scenes):
            if not isinstance(scene, dict):
                continue
            # 获取 TTS 文本（优先 dialogue，其次 description/narration）
            text = scene.get(text_field) or scene.get("description") or scene.get("narration") or ""
            if not text.strip():
                logger.warning(f"[TTS] 场景 #{idx} 没有可合成文本，跳过")
                continue

            # 识别说话者并分配声音
            speaker, clean_text = self._parse_speaker(text)
            voice = self._select_voice(speaker, voice_mapping, default_voice)

            tts_tasks.append({
                "index": idx,
                "text": clean_text,
                "speaker": speaker,
                "voice": voice,
                "rate": rate,
            })

        if not tts_tasks:
            logger.warning(f"[TTS] 没有可合成的任务: step_key={self.step_key}")
            return {
                "audios": [],
                "total": 0,
                "success_count": 0,
                "failed_count": 0,
                "subtitle_srt": "",
                "subtitle_words": [],
            }

        logger.info(f"[TTS] 开始合成 {len(tts_tasks)} 个音频片段")
        self._total = len(tts_tasks)
        self._completed_count = 0

        # 5. 并发生成音频文件
        results = await self._generate_all_audios(tts_tasks, max_concurrent)

        success_audios = [r for r in results if r.get("success")]
        failed_audios = [r for r in results if not r.get("success")]

        logger.info(
            f"[TTS] 完成: 成功 {len(success_audios)}/{len(results)}, "
            f"失败 {len(failed_audios)}"
        )

        # 6. 按 index 排序
        success_audios.sort(key=lambda x: x.get("index", 0))

        # 7. 生成 word-level 时间戳的细粒度 SRT 字幕
        # 收集所有成功音频段的词级时间戳，按音频时长累计偏移到全局时间轴
        subtitle_words, subtitle_srt = self._build_subtitle_from_audios(success_audios)

        return {
            "audios": success_audios,
            "total": len(results),
            "success_count": len(success_audios),
            "failed_count": len(failed_audios),
            "failed_audios": failed_audios,
            # 词级字幕（P0 视频后期处理增强）：
            # - subtitle_words: 全局时间轴的词级时间戳数组
            # - subtitle_srt: 按句末标点或 3-7 词分组生成的 SRT 字符串
            "subtitle_srt": subtitle_srt,
            "subtitle_words": subtitle_words,
        }

    async def estimate_credits(self) -> int:
        """TTS 使用免费 edge-tts，不消耗积分"""
        return 5

    async def get_progress(self) -> Dict[str, Any]:
        """返回合成进度"""
        total = getattr(self, "_total", 0)
        if total == 0:
            return {}
        completed = getattr(self, "_completed_count", 0)
        return {
            "current": completed,
            "total": total,
            "percent": round(completed / total, 3) if total > 0 else 0,
            "phase": "synthesizing",
            "phase_text": "语音合成中",
        }

    async def execute_single(self, ctx: SingleItemContext) -> ItemResult:
        """
        单条 TTS 重生成

        复用 execute() 中的 _generate_single_audio 逻辑，
        仅处理 ctx.item 这一条 TTS 元素。

        Args:
            ctx: 单元素执行上下文，item 含 index/text/speaker/voice/rate 等字段

        Returns:
            ItemResult: 单元素执行结果，含更新后的 audio_url 和 status
        """
        item = ctx.item or {}

        # 构建 TTS 任务（用 prompt_override 替换原 text，若提供）
        text = ctx.prompt_override if ctx.prompt_override else item.get("text", "")
        task = {
            "index": item.get("index", 0),
            "text": text,
            "speaker": item.get("speaker"),
            "voice": item.get("voice", _DEFAULT_NARRATOR_VOICE),
            "rate": item.get("rate", "+0%"),
        }

        if not task["text"].strip():
            error = "TTS 文本为空"
            logger.warning(f"[TTS-单元素] {error}: index={task['index']}")
            return ItemResult(
                status="failed",
                item={**item, "audio_url": "", "status": "failed", "error": error},
                error=error,
            )

        logger.info(
            f"[TTS-单元素] 重生音频: index={task['index']}, "
            f"voice={task['voice']}, text={task['text'][:30]}..."
        )

        # 初始化进度计数器（_generate_single_audio 内部会自增 _completed_count）
        self._total = 1
        self._completed_count = 0

        # 调用与 execute() 相同的合成逻辑（含重试 + pyttsx3 离线兜底）
        result = await self._generate_single_audio(task)

        if result.get("success"):
            logger.info(f"[TTS-单元素] 合成成功: index={task['index']}")
            return ItemResult(
                status="success",
                item={
                    **item,
                    "audio_url": result.get("audio_url", ""),
                    "audio_path": result.get("audio_path", ""),
                    "duration_seconds": result.get("duration_seconds", 0),
                    "provider": result.get("provider", ""),
                    "voice": task["voice"],
                    "text": task["text"],
                    "status": "success",
                    "error": None,
                },
            )
        else:
            error = result.get("error", "TTS 合成失败")
            logger.error(f"[TTS-单元素] 合成失败: index={task['index']}, error={error}")
            return ItemResult(
                status="failed",
                item={
                    **item,
                    "audio_url": "",
                    "status": "failed",
                    "error": error,
                },
                error=error,
            )

    # ---------- 内部方法 ----------

    def _build_voice_mapping(
        self,
        characters: List[Dict[str, Any]],
        config: Dict[str, Any],
    ) -> Dict[str, str]:
        """
        为角色列表构建 角色名 → 声音ID 的映射

        优先级：
        1. config.voice_mapping（用户自定义）
        2. 按 gender 字段分配（male → 男声池，female → 女声池）
        3. 按角色顺序轮换默认声音池
        """
        # 用户自定义映射优先
        custom_mapping = config.get("voice_mapping", {})
        if custom_mapping and isinstance(custom_mapping, dict):
            return custom_mapping

        mapping: Dict[str, str] = {}
        male_idx = 0
        female_idx = 0

        for char in characters:
            if not isinstance(char, dict):
                continue
            name = char.get("name") or char.get("character_name") or ""
            if not name:
                continue

            gender = (char.get("gender") or "").lower()
            if gender in ("male", "男", "m"):
                mapping[name] = _DEFAULT_MALE_VOICES[male_idx % len(_DEFAULT_MALE_VOICES)]
                male_idx += 1
            elif gender in ("female", "女", "f"):
                mapping[name] = _DEFAULT_FEMALE_VOICES[female_idx % len(_DEFAULT_FEMALE_VOICES)]
                female_idx += 1
            else:
                # 没有性别信息，用默认叙述声音
                mapping[name] = _DEFAULT_NARRATOR_VOICE

        return mapping

    def _parse_speaker(self, text: str) -> tuple:
        """
        从对白文本中解析说话者

        支持格式：
        - "角色名：对白内容"
        - "角色名: 对白内容"
        - "角色名：对白内容" （中文冒号）

        返回: (speaker_name, clean_text)
        如果无法解析，返回 (None, 原文)
        """
        # 匹配 "角色名：对白" 或 "角色名: 对白"（支持中英文冒号）
        # 角色名限制为 2-10 个中英文字符
        match = re.match(r'^([^\s:：]{1,15})[：:]\s*(.+)$', text.strip(), re.DOTALL)
        if match:
            speaker = match.group(1).strip()
            clean = match.group(2).strip()
            return speaker, clean
        return None, text.strip()

    def _select_voice(
        self,
        speaker: Optional[str],
        voice_mapping: Dict[str, str],
        default_voice: str,
    ) -> str:
        """根据说话者选择声音"""
        if speaker and speaker in voice_mapping:
            return voice_mapping[speaker]
        return default_voice

    async def _generate_all_audios(
        self,
        tasks: List[Dict[str, Any]],
        max_concurrent: int,
    ) -> List[Dict[str, Any]]:
        """并发合成所有音频"""
        semaphore = asyncio.Semaphore(max_concurrent)
        results: List[Dict[str, Any]] = [{}] * len(tasks)

        async def generate_one(task: Dict[str, Any], idx: int) -> None:
            async with semaphore:
                results[idx] = await self._generate_single_audio(task)

        await asyncio.gather(
            *(generate_one(t, i) for i, t in enumerate(tasks))
        )
        return results

    async def _validate_voice(self, voice: str) -> tuple[bool, str]:
        """验证目标声音是否在 edge-tts 当前可用列表中（5s 超时）"""
        try:
            voices = await asyncio.wait_for(
                asyncio.to_thread(edge_tts.list_voices),
                timeout=5.0,
            )
            # list_voices() 返回 List[Dict] 或 Dict 结构，统一提取 ShortName
            available = set()
            raw_keys: list = []
            if isinstance(voices, list):
                for v in voices:
                    if isinstance(v, dict):
                        raw_keys.append(v.get("ShortName", v.get("Name", str(v))))
                        if "ShortName" in v:
                            available.add(v["ShortName"])
            elif isinstance(voices, dict):
                for k, v in voices.items():
                    raw_keys.append(k)
                    if isinstance(v, dict) and "ShortName" in v:
                        available.add(v["ShortName"])
                    elif isinstance(v, str):
                        available.add(v)
            if voice in available:
                return True, "ok"
            else:
                nearby = [v for v in available if v.startswith("zh-CN-")] if available else []
                logger.warning(
                    f"[TTS] 声音 '{voice}' 不在可用列表中。"
                    f"zh-CN 可用: {nearby[:8]}, "
                    f"总声音数: {len(available)}/{len(raw_keys)}, "
                    f"首 5 个: {raw_keys[:5]}"
                )
                return False, f"声音 '{voice}' 不在可用列表中（当前可用 zh-CN 声音: {nearby[:8]}）"
        except asyncio.TimeoutError:
            return False, "验证声音可用性超时（5s），edge-tts 服务可能不可达"
        except Exception as e:
            return False, f"验证声音可用性失败: {e}"

    async def _synthesize_with_pyttsx3(
        self,
        text: str,
        output_path: str,
        index: int,
    ) -> bool:
        """使用 pyttsx3 离线合成占位音频"""
        try:
            if not await _ensure_pyttsx3():
                logger.warning(f"[TTS] #{index} pyttsx3 不可用，跳过离线兜底")
                return False
            engine = await _get_pyttsx3_engine()
            # pyttsx3 save_to_file 是同步阻塞调用，在线程池执行
            def _save():
                engine.save_to_file(text, output_path)
            await asyncio.to_thread(_save)
            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                logger.info(f"[TTS] #{index} pyttsx3 兜底合成成功（{os.path.getsize(output_path)} bytes）")
                return True
            return False
        except Exception as e:
            logger.warning(f"[TTS] #{index} pyttsx3 兜底合成失败: {e}")
            return False

    async def _generate_single_audio(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """合成单个音频文件（通过 TTS 适配层）

        容错策略：
        1. 先验证声音可用性（5s 超时）
        2. 在线 TTS：2 次重试 + 指数退避
        3. 在线全部失败 → pyttsx3 离线兜底
        """
        index = task["index"]
        text = task["text"]
        voice = task["voice"]
        rate = task["rate"]

        # 生成输出文件路径
        run_id = self.context.run_id or "tmp"
        filename = f"tts_run_{run_id}_seg_{index:03d}.mp3"
        audio_path = os.path.join(_OUTPUT_BASE, filename)
        audio_url = f"/api/pipeline/outputs/{filename}"

        # 阶段 0：验证声音可用性（仅验证一次，不重试）
        voice_valid, voice_reason = await self._validate_voice(voice)
        if not voice_valid:
            logger.warning(f"[TTS] #{index} 声音验证失败: {voice_reason}")

        # 阶段 1：在线 TTS（重试 2 次，指数退避）
        max_retries = 2
        last_error: Optional[Exception] = None
        last_error_type: str = "unknown"

        for attempt in range(max_retries + 1):
            try:
                provider = _get_tts_provider()
                # 使用 synthesize_with_subtitles 同时收集 edge-tts WordBoundary 词级时间戳
                # 非 edge-tts provider（如 pyttsx3 兜底）不经过此路径，自然跳过词级收集
                success, word_boundaries = await provider.synthesize_with_subtitles(
                    text=text,
                    voice=voice,
                    rate=rate,
                    output_path=audio_path,
                )
                if not success:
                    raise RuntimeError(f"TTS 合成返回失败（provider={provider.name}）")

                if not os.path.exists(audio_path) or os.path.getsize(audio_path) == 0:
                    raise RuntimeError("生成的音频文件为空")

                duration = await self._get_audio_duration(audio_path)

                logger.debug(
                    f"[TTS] 合成成功 #{index}: provider={provider.name}, voice={voice}, "
                    f"duration={duration}s, words={len(word_boundaries)}, "
                    f"attempt={attempt+1}, text={text[:30]}..."
                )

                self._completed_count += 1

                return {
                    **task,
                    "success": True,
                    "audio_path": audio_path,
                    "audio_url": audio_url,
                    "duration_seconds": duration,
                    "provider": provider.name,
                    # 词级时间戳（相对本段 TTS 起始；非 edge-tts 路径为空数组）
                    "words": word_boundaries,
                }
            except Exception as e:
                last_error = e
                err_str = str(e)
                if "No audio was received" in err_str or "NoAudioReceived" in err_str:
                    last_error_type = "no_audio_received"
                elif "timeout" in err_str.lower() or "timed out" in err_str.lower():
                    last_error_type = "timeout"
                elif isinstance(e, (ConnectionError, OSError)):
                    last_error_type = "network"
                else:
                    last_error_type = "unknown"

                if attempt < max_retries:
                    wait = 2 ** attempt
                    logger.warning(
                        f"[TTS] #{index} 第{attempt+1}次尝试失败 [{last_error_type}]: {e}，"
                        f"{wait}s 后重试"
                    )
                    await asyncio.sleep(wait)
                else:
                    break

        # 阶段 2：在线全部失败，尝试 pyttsx3 离线兜底
        logger.warning(
            f"[TTS] #{index} 在线 TTS 全部失败（error_type={last_error_type}），"
            f"尝试 pyttsx3 离线兜底..."
        )
        fallback_success = await self._synthesize_with_pyttsx3(text, audio_path, index)

        if fallback_success:
            duration = await self._get_audio_duration(audio_path)
            self._completed_count += 1
            return {
                **task,
                "success": True,
                "audio_path": audio_path,
                "audio_url": audio_url,
                "duration_seconds": duration,
                "provider": "pyttsx3-fallback",
                "warning": f"在线 TTS 失败 [{last_error_type}]，使用离线语音兜底",
            }

        # 阶段 3：全部失败
        error_detail = (
            f"在线TTS({last_error_type}): {last_error}"
            if last_error
            else "未知错误"
        )
        logger.error(f"[TTS] #{index} 全部合成方案失败: {error_detail}")
        self._completed_count += 1
        return {
            **task,
            "success": False,
            "error": error_detail,
            "error_type": last_error_type,
            "audio_path": "",
            "audio_url": "",
        }

    async def _get_audio_duration(self, audio_path: str) -> float:
        """用 ffprobe 获取音频时长（秒）"""
        try:
            cmd = [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                audio_path,
            ]
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10.0)
            return float(stdout.decode().strip())
        except Exception:
            return 0.0

    def _build_subtitle_from_audios(
        self,
        audios: List[Dict[str, Any]],
    ) -> tuple:
        """从音频列表构建全局字幕（P0 视频后期处理增强）

        将每段音频的词级时间戳（相对本段起始）按音频时长累计偏移到全局时间轴，
        然后按句末标点或 3-7 词分组生成 SRT 字幕段落。

        回退策略：
        - edge-tts 路径：使用 WordBoundary 词级时间戳，按句末标点/3-7 词分组
        - 非 edge-tts 路径（如 pyttsx3 离线兜底）：无词级时间戳，
          沿用现有 duration_seconds 字段生成整段兜底字幕
        - edge-tts 调用未产生 WordBoundary 事件：返回空字段，不报错

        Args:
            audios: 已按 index 排序的成功音频列表

        Returns:
            (subtitle_words, subtitle_srt)
            - subtitle_words: [{"word": str, "start": float, "end": float}, ...]
              全局时间轴的词级时间戳（仅 edge-tts 路径有数据）
            - subtitle_srt: SRT 格式字符串（含 edge-tts 词级字幕与 pyttsx3 兜底字幕）
        """
        all_words: List[Dict[str, Any]] = []
        fallback_subtitles: List[Dict[str, Any]] = []
        cumulative_time = 0.0

        for audio in audios:
            seg_words = audio.get("words") or []
            seg_duration = float(audio.get("duration_seconds", 0.0) or 0.0)

            if seg_words:
                # edge-tts 路径：使用词级时间戳，累计偏移到全局时间轴
                for w in seg_words:
                    all_words.append({
                        "word": w.get("word", ""),
                        "start": float(w.get("start", 0.0)) + cumulative_time,
                        "end": float(w.get("end", 0.0)) + cumulative_time,
                    })
            else:
                # 非 edge-tts 路径（如 pyttsx3 兜底）：用整段时长生成兜底字幕
                text = audio.get("text", "")
                if text and seg_duration > 0:
                    fallback_subtitles.append({
                        "start": cumulative_time,
                        "end": cumulative_time + seg_duration,
                        "text": text,
                    })

            # 累计下一段的起始时间（基于本段音频时长）
            cumulative_time += seg_duration

        # 主体字幕：词级时间戳按句末标点或 3-7 词分组
        subtitles = _group_words_to_subtitles(all_words)
        # 合并兜底字幕（pyttsx3 等无词级时间戳的段落）
        subtitles.extend(fallback_subtitles)
        # 按起始时间排序，保证 SRT 时间顺序正确
        subtitles.sort(key=lambda x: float(x.get("start", 0.0)))

        # 生成 SRT 字符串
        subtitle_srt = _build_srt(subtitles)
        return all_words, subtitle_srt
