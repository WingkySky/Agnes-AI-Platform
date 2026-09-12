# =====================================================
# 项目制 LLM 公共工具 — 从 wizard.py 抽出（原实现原样保留）
#
# 消费方：subtitle_service / canvas_media_service（画布 TTS/字幕/合成节点的
# LLM 子调用）。项目制编排已迁前端管线，wizard 本体已删除。
# =====================================================

import json
import re
from typing import Any

from app.services.agnes_client import agnes_client


def parse_json_loose(text: str) -> Any:
    """
    宽松 JSON 解析:
    - 去除 markdown 代码块包裹
    - 提取首个 { ... } 或 [ ... ] 块
    - 容忍尾部逗号
    """
    if not text:
        return {}
    # 去除 markdown 代码块
    text = re.sub(r"```(?:json)?\s*", "", text)
    text = text.replace("```", "")
    text = text.strip()
    # 尝试直接解析
    try:
        return json.loads(text)
    except Exception:
        pass
    # 提取首个 JSON 对象/数组
    for start_char, end_char in [("{", "}"), ("[", "]")]:
        start = text.find(start_char)
        end = text.rfind(end_char)
        if start != -1 and end != -1 and end > start:
            fragment = text[start:end + 1]
            # 去除尾部逗号
            fragment = re.sub(r",\s*([}\]])", r"\1", fragment)
            try:
                return json.loads(fragment)
            except Exception:
                continue
    return {}


async def call_llm(
    prompt: str,
    model: str = "",
    temperature: float = 0.7,
    fallback_model: str = "",
) -> str:
    """
    调用 LLM 返回文本（通过 AgnesAIClient._post 走 chat/completions）。
    模型优先级：显式 model > fallback_model（项目所有者偏好）> 系统默认（管理员配置）。
    """
    body_model = ""
    if model:
        from app.services.model_registry import get_models_by_type
        if model in {m.id for m in await get_models_by_type("chat")}:
            body_model = model
    if not body_model:
        body_model = fallback_model
    if not body_model:
        from app.services.model_registry import resolve_system_chat_model_id, SYSTEM_CHAT_MODEL_KEYS
        body_model = await resolve_system_chat_model_id(None, SYSTEM_CHAT_MODEL_KEYS["chat_default"])
    if not body_model:
        raise RuntimeError("未配置可用的对话模型，请先在配置页同步或添加对话模型")
    body = {
        "model": body_model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
    }
    result = await agnes_client._post(
        f"{agnes_client.base_url}/chat/completions", body
    )
    choices = result.get("choices", [])
    if not choices:
        raise RuntimeError("LLM 返回为空")
    return choices[0].get("message", {}).get("content", "") or ""
