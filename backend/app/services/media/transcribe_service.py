# =====================================================
# 音频转写服务（faster-whisper 公共域）
#
# 从 project/subtitle_service.py 抽离的转写核心（画布/项目/剪辑器共用）：
#   - is_whisper_available / get_whisper_model：可选依赖与模型缓存
#   - transcribe_audio：本地音频 → [{start, end, text}]（线程池执行，不阻塞事件循环）
#
# faster-whisper 已是正式依赖（requirements.txt）；运行时可用性检查保留作兜底，
# 未装环境下各业务域自行决定回退策略（项目域回退 LLM 拆分；剪辑器返回 503）。
# =====================================================

import asyncio
import logging
from typing import List

logger = logging.getLogger("agnes_platform.media.transcribe")

try:
    import av
    from faster_whisper import WhisperModel  # type: ignore

    # PyAV 19 移除了 av.open 的 metadata_errors 参数（新行为=metadata 一律按 UTF-8 +
    # surrogateescape 字节级无损读取，旧参数"忽略 metadata 错误"的语义已成默认）；
    # faster-whisper 1.2.1 仍传该参数会 TypeError，这里包一层剥掉。
    # 上游适配发版后垫片自然空转（不再有该入参），届时可整体删除。
    if int(av.__version__.split(".", 1)[0]) >= 19:
        _av_open = av.open

        def _av_open_compat(*args, **kwargs):
            kwargs.pop("metadata_errors", None)
            return _av_open(*args, **kwargs)

        av.open = _av_open_compat

    _WHISPER_AVAILABLE = True
except ImportError:
    _WHISPER_AVAILABLE = False


def is_whisper_available() -> bool:
    """检查 faster-whisper 是否已安装"""
    return _WHISPER_AVAILABLE


# 模型缓存（按 model_size:device 复用，避免重复加载）
_whisper_model_cache: dict = {}


def get_whisper_model(model_size: str = "small", device: str = "cpu"):
    """
    获取（必要时加载）whisper 模型实例。

    model_size: tiny/base/small/medium/large-v3 等，默认 small（中文识别效果与性能平衡）
    device: cpu/cuda，默认 cpu（不依赖 GPU）
    """
    if not _WHISPER_AVAILABLE:
        raise RuntimeError("faster-whisper 未安装，请先 pip install faster-whisper")
    cache_key = f"{model_size}:{device}"
    if cache_key not in _whisper_model_cache:
        logger.info(f"加载 whisper 模型: size={model_size}, device={device}")
        # compute_type=int8 默认，CPU 友好；GPU 环境可改 float16
        _whisper_model_cache[cache_key] = WhisperModel(
            model_size, device=device, compute_type="int8"
        )
    return _whisper_model_cache[cache_key]


async def transcribe_audio(
    local_path: str,
    language: str = "zh",
    model_size: str = "small",
    device: str = "cpu",
) -> List[dict]:
    """
    转写本地音频文件 → segment 级时间戳列表 [{start, end, text}]（秒）。

    同步 API 放线程池执行；vad_filter 过滤静音段；空文本段丢弃。
    """
    model = get_whisper_model(model_size, device=device)
    segments_iter, _info = await asyncio.to_thread(
        model.transcribe,
        local_path,
        language=language,
        vad_filter=True,
        word_timestamps=False,  # segment-level 已足够
    )
    segments = []
    for seg in segments_iter:  # generator，需消费
        text = (seg.text or "").strip()
        if not text:
            continue
        segments.append({"start": float(seg.start), "end": float(seg.end), "text": text})
    return segments
