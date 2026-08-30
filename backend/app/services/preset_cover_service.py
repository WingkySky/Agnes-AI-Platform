# =====================================================
# 预设封面生成服务
# 用 Agnes Image API 为预设生成代表性封面图（官方卡维护）。
# 生成模式复用 generate_style_previews.py 的做法：
# create_image → 提取 URL → 下载 → 存 uploads/preset-covers/
# =====================================================

import asyncio
import os
import time

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.prompt_preset import PromptPreset
from app.services.agnes_client import agnes_client

# 与 routes/uploads.py 的封面上传目录保持一致
COVER_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "uploads", "preset-covers")
# 动态封面视频目录
COVER_VIDEO_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "uploads", "preset-videos")
COVER_MODEL = "agnes-image-2.1-flash"
COVER_SIZE = "512x512"
# 动态封面：2.5-flash（快/省），3:4 匹配卡片画幅，4 秒最短档
COVER_VIDEO_MODEL = "agnes-video-2.5-flash"
COVER_VIDEO_SECONDS = 4
COVER_VIDEO_ASPECT = "3:4"
COVER_VIDEO_TIMEOUT = 300
COVER_VIDEO_POLL_INTERVAL = 5

# effect/camera 类型生成动态封面，其余生成静态图
VIDEO_COVER_TYPES = ("effect", "camera")

# 各类型封面的代表性主体（与风格/效果正交，突出画风或效果本身）
_COVER_SUBJECTS = {
    "style": "一位年轻女性的半身肖像，室内自然光，背景简洁",
    "effect": "一名跑者在城市街道上奔跑的动感瞬间，电影感构图",
    "camera": "一辆红色跑车驶过城市街角，动态构图",
    "prompt": "清晨森林中的小木屋，薄雾缭绕",
    "script": "书桌上的剧本手稿与咖啡，暖光",
    "pipeline": "深色背景上的抽象工作流节点连线图",
}


def build_cover_prompt(preset: PromptPreset) -> str:
    """构造封面生成 prompt：代表性主体 + 预设提示词片段"""
    subject = _COVER_SUBJECTS.get(preset.type, _COVER_SUBJECTS["style"])
    cfg = preset.prompt_config or {}
    fragment = cfg.get("suffix") or preset.prompt_text or ""
    parts = [subject]
    if fragment:
        parts.append(str(fragment).strip("，, "))
    return "，".join(parts)


def _extract_image_url(result) -> str:
    """从 Agnes Image API 响应中提取图片 URL（兼容多种返回结构）"""
    if not isinstance(result, dict):
        return ""
    data_field = result.get("data")
    if isinstance(data_field, list) and data_field:
        first = data_field[0]
        if isinstance(first, dict):
            return first.get("url") or first.get("image_url") or ""
    if isinstance(data_field, dict):
        return data_field.get("url") or data_field.get("image_url") or ""
    return result.get("url") or result.get("image_url") or ""


async def generate_cover_image(preset: PromptPreset) -> str:
    """
    为单个预设生成封面：生图 → 下载 → 落盘 uploads/preset-covers/。
    成功返回可访问 URL；失败抛 RuntimeError（路由转 502）。
    """
    prompt = build_cover_prompt(preset)
    result = await agnes_client.create_image(
        prompt=prompt,
        model=COVER_MODEL,
        size=COVER_SIZE,
        response_format="url",
    )
    image_url = _extract_image_url(result)
    if not image_url:
        raise RuntimeError(f"封面生成失败：上游未返回图片 URL：{str(result)[:200]}")

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.get(image_url)
        if resp.status_code != 200:
            raise RuntimeError(f"封面图片下载失败：status={resp.status_code}")
        content = resp.content

    os.makedirs(COVER_DIR, exist_ok=True)
    filename = f"cover_{preset.id}_{int(time.time())}.png"
    with open(os.path.join(COVER_DIR, filename), "wb") as f:
        f.write(content)
    return f"/uploads/preset-covers/{filename}"


# 动态封面的运动主体（与特效/运镜提示词正交，突出效果本身）
_VIDEO_SUBJECTS = {
    "effect": "一名跑者在城市街道上奔跑的动感瞬间，电影感构图",
    "camera": "一辆红色跑车驶过城市街角，动态构图",
}


def build_cover_video_prompt(preset: PromptPreset) -> str:
    """构造动态封面 prompt：运动主体 + 特效/运镜提示词片段"""
    subject = _VIDEO_SUBJECTS.get(preset.type, _VIDEO_SUBJECTS["effect"])
    cfg = preset.prompt_config or {}
    fragment = cfg.get("suffix") or ""
    parts = [subject]
    if fragment:
        parts.append(str(fragment).strip("，, "))
    return "，".join(parts)


def _extract_task_ids(result) -> tuple[str, str]:
    """从视频任务创建响应中提取 (video_id, task_id)，兼容多层结构"""
    if not isinstance(result, dict):
        return "", ""
    data_field = result.get("data")
    first = data_field[0] if isinstance(data_field, list) and data_field else (
        data_field if isinstance(data_field, dict) else {}
    )
    video_id = result.get("video_id") or (first.get("video_id") if isinstance(first, dict) else None) or ""
    task_id = result.get("task_id") or (first.get("task_id") if isinstance(first, dict) else None) or ""
    return str(video_id), str(task_id)


async def generate_cover_video(preset: PromptPreset) -> str:
    """
    为特效/运镜预设生成动态封面：创建视频任务 → 轮询至完成 → 下载 →
    落盘 uploads/preset-videos/。成功返回 URL；失败/超时抛 RuntimeError。
    """
    prompt = build_cover_video_prompt(preset)
    result = await agnes_client.create_video_task(
        prompt=prompt,
        model=COVER_VIDEO_MODEL,
        seconds=COVER_VIDEO_SECONDS,
        aspect_ratio=COVER_VIDEO_ASPECT,
        mode="text2video",
    )
    video_id, task_id = _extract_task_ids(result)
    if not video_id and not task_id:
        raise RuntimeError(f"动态封面创建失败：上游未返回任务 ID：{str(result)[:200]}")

    deadline = time.monotonic() + COVER_VIDEO_TIMEOUT
    video_url = ""
    while time.monotonic() < deadline:
        await asyncio.sleep(COVER_VIDEO_POLL_INTERVAL)
        status_data = await agnes_client.poll_video_status(
            video_id=video_id or None,
            task_id=task_id or None,
            model_name=COVER_VIDEO_MODEL,
        )
        status = status_data.get("status")
        if status == "success":
            video_url = status_data.get("video_url") or ""
            break
        if status == "failed":
            raise RuntimeError(f"动态封面生成失败：{str(status_data)[:200]}")
    if not video_url:
        raise RuntimeError(f"动态封面生成超时（{COVER_VIDEO_TIMEOUT}s）")

    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.get(video_url)
        if resp.status_code != 200:
            raise RuntimeError(f"动态封面下载失败：status={resp.status_code}")
        content = resp.content

    os.makedirs(COVER_VIDEO_DIR, exist_ok=True)
    filename = f"cover_{preset.id}_{int(time.time())}.mp4"
    with open(os.path.join(COVER_VIDEO_DIR, filename), "wb") as f:
        f.write(content)
    return f"/uploads/preset-videos/{filename}"


async def generate_missing_official_covers(db: AsyncSession) -> int:
    """为官方预设批量补齐封面（批量脚本用）：effect/camera 生成动态封面，其余生成静态图。返回成功数"""
    from sqlalchemy import select, not_

    result = await db.execute(
        select(PromptPreset).filter(PromptPreset.is_official == True)  # noqa: E712
    )
    presets = result.scalars().all()
    ok = 0
    for preset in presets:
        try:
            if preset.type in VIDEO_COVER_TYPES:
                if preset.cover_video:
                    continue
                url = await generate_cover_video(preset)
                preset.cover_video = url
                label = "动态封面"
            else:
                if preset.cover_image:
                    continue
                url = await generate_cover_image(preset)
                preset.cover_image = url
                label = "封面"
            await db.commit()
            ok += 1
            print(f"  ✓ [{label}] {preset.name} -> {url}")
        except Exception as e:
            print(f"  ✗ {preset.name}: {e}")
    return ok
