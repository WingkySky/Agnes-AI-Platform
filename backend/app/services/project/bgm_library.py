# =====================================================
# BGM 内置库 — 按情绪分类的背景音乐管理
#
# 设计:
#   - BGM 文件存放于 backend/assets/bgm/ 目录
#   - 元数据（id/name/mood/duration）在代码中声明（避免 DB 依赖）
#   - get_bgm_path 返回文件绝对路径，文件缺失时返回 None 并记录警告
#   - 按情绪检索：calm / uplifting / dramatic / corporate / sad
#
# 添加新 BGM 文件:
#   1. 将 .mp3 文件放到 backend/assets/bgm/ 目录
#   2. 在 _BGM_REGISTRY 中新增对应元数据条目
#   3. mood 字段决定情绪分类，duration 单位为秒
# 用户自备音源（推荐路径）: POST /projects/{id}/bgms/upload 上传，
#   自定义曲目登记到 custom_bgms.json，与内置清单合并展示。
# =====================================================

import asyncio
import json
import logging
import os
import time
from typing import List, Optional, Dict

logger = logging.getLogger("agnes_platform.project.bgm")

# backend/assets/bgm/ 绝对路径
_BGM_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
    "assets", "bgm",
)

# =====================================================
# BGM 元数据清单
# -------------------------------------------------
# id: 唯一标识（前端用）
# name: 显示名称
# mood: 情绪分类（calm/uplifting/dramatic/corporate/sad）
# duration: 时长（秒）
# filename: 文件名（相对于 _BGM_DIR）
# =====================================================
_BGM_REGISTRY: List[Dict] = [
    {
        "id": "bgm_warm_piano",
        "name": "温暖钢琴",
        "mood": "calm",
        "duration": 60,
        "filename": "bgm_warm_piano.mp3",
    },
    {
        "id": "bgm_corporate",
        "name": "商务科技",
        "mood": "corporate",
        "duration": 45,
        "filename": "bgm_corporate.mp3",
    },
    {
        "id": "bgm_dramatic",
        "name": "戏剧紧张",
        "mood": "dramatic",
        "duration": 90,
        "filename": "bgm_dramatic.mp3",
    },
    {
        "id": "bgm_uplifting",
        "name": "激昂向上",
        "mood": "uplifting",
        "duration": 50,
        "filename": "bgm_uplifting.mp3",
    },
    {
        "id": "bgm_sad",
        "name": "忧伤抒情",
        "mood": "sad",
        "duration": 70,
        "filename": "bgm_sad.mp3",
    },
]


def list_bgms(mood: Optional[str] = None) -> List[Dict]:
    """
    列出所有 BGM 元数据（内置 + 用户上传的自定义曲目）。

    参数:
    - mood: 按情绪过滤（calm/uplifting/dramatic/corporate/sad），None 返回全部

    返回:
    - BGM 字典列表，每个含 id/name/mood/duration/available（文件是否存在）
    """
    result: List[Dict] = []
    for bgm in _BGM_REGISTRY + _load_custom_bgms():
        if mood and bgm["mood"] != mood:
            continue
        file_path = os.path.join(_BGM_DIR, bgm["filename"])
        item = {
            "id": bgm["id"],
            "name": bgm["name"],
            "mood": bgm["mood"],
            "duration": bgm["duration"],
            "available": os.path.isfile(file_path),
        }
        result.append(item)
    return result


def get_bgm_path(bgm_id: str) -> Optional[str]:
    """
    获取 BGM 文件的绝对路径。

    文件不存在时返回 None 并记录警告（便于管理员发现缺失文件）。
    """
    for bgm in _BGM_REGISTRY + _load_custom_bgms():
        if bgm["id"] == bgm_id:
            file_path = os.path.join(_BGM_DIR, bgm["filename"])
            if not os.path.isfile(file_path):
                logger.warning(
                    "[BGM] 文件缺失: bgm_id=%s, 期望路径=%s。"
                    "请将 BGM 文件放到 backend/assets/bgm/ 目录",
                    bgm_id, file_path,
                )
                return None
            return file_path
    logger.warning("[BGM] 未知的 bgm_id: %s", bgm_id)
    return None


def get_bgm_by_id(bgm_id: str) -> Optional[Dict]:
    """获取 BGM 元数据（含 available 字段）"""
    for bgm in _BGM_REGISTRY + _load_custom_bgms():
        if bgm["id"] == bgm_id:
            file_path = os.path.join(_BGM_DIR, bgm["filename"])
            return {
                "id": bgm["id"],
                "name": bgm["name"],
                "mood": bgm["mood"],
                "duration": bgm["duration"],
                "available": os.path.isfile(file_path),
            }
    return None


# =====================================================
# 用户自备音源：自定义 BGM 上传与登记
# 登记持久化到 custom_bgms.json（无 DB 依赖，与内置清单合并展示）
# =====================================================

_CUSTOM_REGISTRY_FILE = os.path.join(_BGM_DIR, "custom_bgms.json")
VALID_MOODS = ("calm", "uplifting", "dramatic", "corporate", "sad")


def _load_custom_bgms() -> List[Dict]:
    try:
        with open(_CUSTOM_REGISTRY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save_custom_bgms(items: List[Dict]) -> None:
    os.makedirs(_BGM_DIR, exist_ok=True)
    with open(_CUSTOM_REGISTRY_FILE, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)


async def _probe_duration_seconds(file_path: str) -> int:
    """ffprobe 探测音频时长（秒），失败回退 60"""
    try:
        proc = await asyncio.create_subprocess_exec(
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", file_path,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        out, _ = await proc.communicate()
        return int(float(out.decode().strip()))
    except Exception as e:
        logger.warning("[BGM] ffprobe 时长探测失败: %s", e)
        return 60


async def save_uploaded_bgm(name: str, mood: str, content: bytes) -> Dict:
    """
    保存用户上传的 BGM（mp3 字节）并登记元数据。

    返回新登记的元数据（含 available=True）。
    """
    os.makedirs(_BGM_DIR, exist_ok=True)
    import secrets
    filename = f"bgm_custom_{int(time.time())}_{secrets.token_hex(4)}.mp3"
    file_path = os.path.join(_BGM_DIR, filename)
    with open(file_path, "wb") as f:
        f.write(content)

    duration = await _probe_duration_seconds(file_path)
    item = {
        "id": f"bgm_custom_{int(time.time() * 1000)}",
        "name": (name or "自定义 BGM")[:50],
        "mood": mood if mood in VALID_MOODS else "calm",
        "duration": duration,
        "filename": filename,
    }
    items = _load_custom_bgms()
    items.append(item)
    _save_custom_bgms(items)
    logger.info("[BGM] 自定义曲目已登记: %s -> %s", item["id"], filename)
    return {**item, "available": True}


def list_moods() -> List[str]:
    """列出所有情绪分类"""
    return list({bgm["mood"] for bgm in _BGM_REGISTRY})
