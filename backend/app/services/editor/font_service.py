# =====================================================
# 服务端可用字体枚举（字幕烧录用：libass 按 fontconfig 匹配，
# 字体必须真实存在于服务器，写了不存在的会被静默回退——
# 字体下拉只列 fc-list 枚举到的族名，进程内缓存 10 分钟）
# =====================================================

import asyncio
import time

_CACHE: tuple[float, list[str]] | None = None
_CACHE_TTL = 600.0


def _parse_fc_list(raw: str) -> list[str]:
    """fc-list : family 输出 → 去重排序的族名列表（每行可含逗号分隔的本地化别名）"""
    out: set[str] = set()
    for line in raw.splitlines():
        for name in line.split(","):
            name = name.strip()
            if name:
                out.add(name)
    return sorted(out)


async def list_fonts() -> list[str]:
    """枚举服务器 fontconfig 可用字体族（fc-list 不可用返回空列表，前端退化为自由填写）"""
    global _CACHE
    now = time.monotonic()
    if _CACHE is not None and now - _CACHE[0] < _CACHE_TTL:
        return _CACHE[1]
    try:
        proc = await asyncio.create_subprocess_exec(
            "fc-list", ":", "family",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=15)
        fonts = _parse_fc_list(stdout.decode("utf-8", "replace"))
    except Exception:  # noqa: BLE001 — 字体枚举失败退化为空列表
        fonts = []
    _CACHE = (now, fonts)
    return fonts
