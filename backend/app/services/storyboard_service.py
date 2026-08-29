# =====================================================
# 分镜脚本生成服务（无限画布 script 节点）
# - 拼装结构化 prompt，调用 LLM 生成 JSON 分镜数组
# - 解析失败自动重试一次，仍失败抛 RuntimeError（路由转 502）
# =====================================================

import json
import logging
import re
from typing import Optional

from app.schemas.storyboard import (
    StoryboardAssetGroup,
    StoryboardRequest,
    StoryboardResult,
    StoryboardShot,
)
from app.services.agnes_client import agnes_client
from app.services.model_registry import get_models_by_type

logger = logging.getLogger(__name__)

_MAX_ATTEMPTS = 2

_PROMPT_TEMPLATE = """你是专业短剧分镜师。请根据剧情概述和角色/场景设定，完成两件事：
1. 提取全剧资产清单；2. 生成结构化分镜脚本。

## 要求
- 镜头数量：{shot_min} 到 {shot_max} 个
- 资产清单：从剧情中提取角色与场景。角色 description 写外貌/服饰/气质等可直接用于生成角色设定图的内容；场景 description 写环境/时间/氛围。若下方已给定角色/场景设定，必须沿用其 name 与描述，不得改写
- 每个镜头包含：no（序号，从1开始）、shot_size（景别：远景/全景/中景/近景/特写）、camera（机位/运镜，如"中景缓推"）、location（场景名，必须取自场景清单）、characters（出场角色名数组，必须取自角色清单）、description（画面描述）、dialogue（台词，没有则为空字符串）
- description 必须是可直接用于 AI 生图的具体画面描述，包含场景、人物动作、表情、光线；人物以角色名指代，与 characters 字段一致
- 台词短句化，符合短剧节奏
- 严格输出 JSON 对象，不要输出任何其他内容
{style_line}
## 剧情概述
{story}

## 已有角色设定
{characters}

## 已有场景设定
{scenes}

## 输出格式
{{"assets": {{"characters": [{{"name": "...", "description": "..."}}], "scenes": [{{"name": "...", "description": "..."}}]}}, "shots": [{{"no": 1, "shot_size": "中景", "camera": "缓推", "location": "...", "characters": ["..."], "description": "...", "dialogue": "..."}}]}}"""


def _build_prompt(req: StoryboardRequest) -> str:
    characters = "\n".join(
        f"- {c.name or '未命名角色'}：{c.description}" + (f"（参考图：{c.ref_image_url}）" if c.ref_image_url else "")
        for c in req.characters
    ) or "无（请根据剧情自行设定角色）"
    scenes = "\n".join(
        f"- {c.name or '未命名场景'}：{c.description}"
        for c in req.scenes
    ) or "无（请根据剧情自行设定场景）"
    style_line = f"## 画面风格\n{req.style}\n" if req.style else ""
    return _PROMPT_TEMPLATE.format(
        shot_min=req.shot_count_min,
        shot_max=req.shot_count_max,
        style_line=style_line,
        story=req.story,
        characters=characters,
        scenes=scenes,
    )


def _extract_json(content: str) -> str:
    """剥离 markdown 代码栅栏，容忍前后杂文"""
    text = content.strip()
    fence_match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
    return fence_match.group(1).strip() if fence_match else text


def _parse_result(content: str) -> StoryboardResult:
    """解析 LLM 输出为分镜 + 资产结果（兼容旧的纯分镜数组格式，降级为 assets 为空）"""
    data = json.loads(_extract_json(content))
    if isinstance(data, list):
        shots = [StoryboardShot(**item) for item in data if isinstance(item, dict)]
        for i, shot in enumerate(shots, start=1):
            if shot.no < 1:
                shot.no = i
        return StoryboardResult(shots=shots)
    if not isinstance(data, dict):
        raise ValueError("分镜数据不是 JSON 对象")
    shots_raw = data.get("shots")
    if not isinstance(shots_raw, list):
        raise ValueError("分镜数据缺少 shots 数组")
    shots = [StoryboardShot(**item) for item in shots_raw if isinstance(item, dict)]
    for i, shot in enumerate(shots, start=1):
        if shot.no < 1:
            shot.no = i
    assets_raw = data.get("assets")
    assets = StoryboardAssetGroup(**assets_raw) if isinstance(assets_raw, dict) else StoryboardAssetGroup()
    return StoryboardResult(shots=shots, assets=assets)


async def generate_storyboard(req: StoryboardRequest) -> StoryboardResult:
    """生成分镜脚本 + 全剧资产清单：调用 LLM，解析失败重试一次"""
    chat_models = await get_models_by_type("chat")
    if not chat_models:
        raise ValueError("未配置聊天模型")
    body = {
        "model": chat_models[0].id,
        "messages": [{"role": "user", "content": _build_prompt(req)}],
        "temperature": 0.7,
    }
    last_error: Optional[Exception] = None
    for attempt in range(_MAX_ATTEMPTS):
        result = await agnes_client._post(f"{agnes_client.base_url}/chat/completions", body)
        choices = result.get("choices", [])
        content = (choices[0].get("message", {}).get("content", "") if choices else "") or ""
        try:
            return _parse_result(content)
        except Exception as e:
            last_error = e
            logger.warning("[storyboard] 第 %s 次解析失败: %s", attempt + 1, e)
    raise RuntimeError(f"分镜脚本解析失败: {last_error}")
