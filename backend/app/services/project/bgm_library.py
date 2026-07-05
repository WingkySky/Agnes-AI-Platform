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
# =====================================================

import logging
import os
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
    列出所有 BGM 元数据。

    参数:
    - mood: 按情绪过滤（calm/uplifting/dramatic/corporate/sad），None 返回全部

    返回:
    - BGM 字典列表，每个含 id/name/mood/duration/available（文件是否存在）
    """
    result: List[Dict] = []
    for bgm in _BGM_REGISTRY:
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
    for bgm in _BGM_REGISTRY:
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
    for bgm in _BGM_REGISTRY:
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


def list_moods() -> List[str]:
    """列出所有情绪分类"""
    return list({bgm["mood"] for bgm in _BGM_REGISTRY})
