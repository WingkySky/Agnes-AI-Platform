# =====================================================
# 剪辑工程 document 骨架校验
#
# document 语义权威在前端命令表（lib/editor），后端只校验骨架：
# 形状合法、数值域、assetId 属主存在；不解释转场/变速等深语义。
# =====================================================

from typing import Any

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models.asset import Asset

# document 体积上限（JSON 序列化字节数）
MAX_DOCUMENT_BYTES = 2 * 1024 * 1024

_TRACK_KINDS = {"video", "audio", "subtitle"}
_TRANSITION_TYPES = {"crossfade", "fade", "wipe"}


def _fail(msg: str) -> None:
    raise HTTPException(status_code=400, detail=f"剪辑文档不合法: {msg}")


def _num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def validate_document_skeleton(doc: Any) -> dict:
    """骨架校验：不合法抛 400，合法原样返回（不做深拷贝/改写）。"""
    if not isinstance(doc, dict):
        _fail("顶层必须是对象")
    for key in ("timebase", "width", "height", "tracks", "clips"):
        if key not in doc:
            _fail(f"缺少 {key}")
    if not _num(doc["timebase"]) or doc["timebase"] <= 0:
        _fail("timebase 必须为正数")
    for key in ("width", "height"):
        if not isinstance(doc[key], int) or not (16 <= doc[key] <= 7680):
            _fail(f"{key} 必须为 16~7680 整数")
    if not isinstance(doc["tracks"], list) or not isinstance(doc["clips"], list):
        _fail("tracks/clips 必须为数组")

    track_ids = set()
    for i, tr in enumerate(doc["tracks"]):
        if not isinstance(tr, dict) or not tr.get("id") or tr.get("kind") not in _TRACK_KINDS:
            _fail(f"tracks[{i}] 形状非法")
        if tr["id"] in track_ids:
            _fail(f"轨道 id 重复: {tr['id']}")
        track_ids.add(tr["id"])
        if tr.get("flag") is not None and tr.get("flag") not in ("hidden", "locked", "muted"):
            _fail(f"tracks[{i}].flag 非法")

    clip_ids = set()
    for i, c in enumerate(doc["clips"]):
        if not isinstance(c, dict):
            _fail(f"clips[{i}] 必须为对象")
        cid = c.get("id")
        if not cid or cid in clip_ids:
            _fail(f"clips[{i}].id 缺失或重复")
        clip_ids.add(cid)
        if c.get("trackId") not in track_ids:
            _fail(f"clips[{i}].trackId 不存在")
        for key in ("start", "duration"):
            if not _num(c.get(key)) or c[key] < 0:
                _fail(f"clips[{i}].{key} 必须为非负数")
        if c.get("trimStart") is not None and (not _num(c["trimStart"]) or c["trimStart"] < 0):
            _fail(f"clips[{i}].trimStart 必须为非负数")
        if c.get("assetId") is not None and not isinstance(c["assetId"], int):
            _fail(f"clips[{i}].assetId 必须为整数")
        props = c.get("props") or {}
        if not isinstance(props, dict):
            _fail(f"clips[{i}].props 必须为对象")
        if "speed" in props and (not _num(props["speed"]) or props["speed"] <= 0):
            _fail(f"clips[{i}].props.speed 必须为正数")
        if "volume" in props and (not _num(props["volume"]) or not (0 <= props["volume"] <= 2)):
            _fail(f"clips[{i}].props.volume 必须在 0~2")
        for key in ("fadeIn", "fadeOut"):
            if key in props and (not _num(props[key]) or props[key] < 0):
                _fail(f"clips[{i}].props.{key} 必须为非负数")
        rect = props.get("rect")
        if rect is not None:
            if not isinstance(rect, dict) or any(
                not _num(rect.get(k)) or not (0 <= rect[k] <= 1) for k in ("x", "y", "w", "h")
            ):
                _fail(f"clips[{i}].props.rect 必须为 0~1 的 x/y/w/h")
        tr = props.get("transition")
        if tr is not None:
            if not isinstance(tr, dict) or tr.get("type") not in _TRANSITION_TYPES:
                _fail(f"clips[{i}].props.transition 非法")
            if not _num(tr.get("duration")) or tr["duration"] <= 0:
                _fail(f"clips[{i}].props.transition.duration 必须为正数")
        if c.get("text") is not None and not isinstance(c.get("text"), str):
            _fail(f"clips[{i}].text 必须为字符串")

    style = doc.get("subtitleStyle")
    if style is not None and not isinstance(style, dict):
        _fail("subtitleStyle 必须为对象")
    return doc


async def validate_document_assets(db: AsyncSession, doc: dict, user_id: int) -> None:
    """校验 document 内全部 assetId 均存在且属当前用户（不合法抛 404 语义 400）。"""
    asset_ids = {c.get("assetId") for c in doc.get("clips", []) if isinstance(c.get("assetId"), int)}
    if not asset_ids:
        return
    rows = (
        await db.scalars(select(Asset.id).where(Asset.id.in_(asset_ids), Asset.user_id == user_id))
    ).all()
    missing = asset_ids - set(rows)
    if missing:
        _fail(f"引用的素材不存在或无权访问: {sorted(missing)[:5]}")


def check_document_size(doc: dict) -> None:
    import json

    if len(json.dumps(doc, ensure_ascii=False).encode()) > MAX_DOCUMENT_BYTES:
        raise HTTPException(status_code=400, detail="剪辑文档过大（上限 2MB）")
