# =====================================================
# 提示词优化器服务（prompt_optimize_service）
#
# 五种模式结构化返回正负提示词 + 变化说明 + 假设声明 + 最多两个备选版本。
# LLM 调用复用 services/llm.call_llm（系统默认对话模型），JSON 解析失败自动重试一次。
# =====================================================

import logging
import re
from typing import Any, Optional

from app.services.llm import call_llm, parse_json_loose

logger = logging.getLogger("agnes_platform")

# 模式枚举（与前端 PromptOptimizeDialog 一致）
PROMPT_OPTIMIZE_MODES = ("expand", "refine", "style", "model-adapt", "reference")
PROMPT_OPTIMIZE_TARGETS = ("image", "video")

_MODE_INSTRUCTIONS = {
    "expand": "扩展想法：在保留用户核心意图的前提下，补充画面主体、环境、构图、光影等细节，让提示词可直接用于生成。",
    "refine": "精修已有提示词：修正语病与冲突描述，重排为模型易读的结构，不新增用户未要求的内容。",
    "style": "强化视觉风格：为提示词注入明确的风格化描述（媒介质感、镜头语言、色调氛围），保持主体不变。",
    "model-adapt": "适配当前模型：按目标模型的提示词方言改写（规则见下方），去除该模型不支持或不推荐的语法。",
    "reference": "结合参考素材：围绕参考素材重写提示词，明确「保留什么、改变什么」，与参考内容形成互补而非重复。",
}

# model-adapt 方言规则：按模型 ID 关键词匹配（首个命中生效），无命中用通用规则
_MODEL_ADAPT_RULES: list[tuple[tuple[str, ...], str]] = [
    (
        ("gpt-image", "dall-e", "dalle", "openai-image", "grok-image", "grok-imagine"),
        "该模型族不支持独立的 negativePrompt，重要限制必须写进正向描述；不要使用 SD 权重语法或 -- 参数。",
    ),
    (
        ("seedream", "jimeng", "doubao", "ark"),
        "该模型族不要套用 SD 的权重语法、质量词串或无意义的英文标签；不要把多个镜头或互相冲突的动作混在一条提示词里。",
    ),
    (
        ("flux",),
        "该模型族偏好自然语言长描述，不要输出逗号标签清单或堆叠 negative prompt；不要添加未经要求的 LoRA、采样器或权重标记。",
    ),
    (
        ("gemini", "imagen", "nano-banana", "nanobanana"),
        "该模型族不要使用 SD 权重、反向提示词标签或未经确认的供应商参数。",
    ),
    (
        ("qwen", "wanx"),
        "该模型族偏好中文或英文自然语句描述，避免堆叠无实义质量词。",
    ),
]
_MODEL_ADAPT_GENERIC = "未识别目标模型方言时保持通用写法：自然语言完整描述，正负提示词分工明确，不使用特定厂商的私有语法。"

_VIDEO_RULE = "目标是视频生成：补充镜头运动、时长内的动作连续性与节奏描述，不要堆叠静态摄影参数；不要新增用户未要求的转场、角色或剧情。"
_IMAGE_RULE = "目标是图片生成：描述应聚焦单帧画面的主体、环境、构图与光影。"

# 输出语言硬规则（钉死，防模型中英摇摆）：中文输入 → 全字段简体中文；其余 → 跟随输入语言
_CJK_PATTERN = re.compile(r"[\u4e00-\u9fff]")


def _language_rule(prompt: str) -> str:
    if _CJK_PATTERN.search(prompt or ""):
        return (
            "输出语言（强制）：用户提示词是中文，positive / negative / changes / assumptions "
            "以及 variants 的 label 一律使用简体中文，禁止输出英文提示词，禁止中英混杂。"
        )
    return "输出语言（强制）：与用户提示词保持一致（非中文输入 → 所有字段使用相同语言）。"


def _model_adapt_rule(model_id: str) -> str:
    lower = (model_id or "").lower()
    for keywords, rule in _MODEL_ADAPT_RULES:
        if any(kw in lower for kw in keywords):
            return rule
    return _MODEL_ADAPT_GENERIC


def _build_prompt(prompt: str, mode: str, target: str, model_id: str, reference_names: list[str]) -> str:
    target_rule = _VIDEO_RULE if target == "video" else _IMAGE_RULE
    parts = [
        "你是 AI 生图/生视频的提示词优化器。请按以下要求优化用户提示词，并只输出一个 JSON 对象。",
        f"优化模式：{_MODE_INSTRUCTIONS[mode]}",
        target_rule,
        _language_rule(prompt),
    ]
    if mode == "model-adapt":
        parts.append(f"目标模型方言规则：{_model_adapt_rule(model_id)}")
    if mode == "reference" and reference_names:
        parts.append(f"参考素材（提示词中的「参考图N」依次对应）：{'、'.join(reference_names)}")
    parts += [
        "输出 JSON 字段：",
        '- "positive"：可直接用于生成的正向提示词（字符串，与用户提示词同语言）',
        '- "negative"：需要规避的内容（字符串，没有则为空字符串）',
        '- "changes"：相较输入做出的关键变化（字符串数组，可为空）',
        '- "assumptions"：对模糊需求做出的假设（字符串数组，没有则为空）',
        '- "variants"：最多两个可选版本（数组，每项 {"label": "短标签", "prompt": "完整提示词"}，可为空）',
        "只输出 JSON，不要输出解释或 markdown 代码块。",
        f"用户提示词：\n{prompt}",
    ]
    return "\n".join(parts)


def _normalize_result(data: Any) -> Optional[dict]:
    """校验并规整 LLM 返回结构；不合法返回 None"""
    if not isinstance(data, dict):
        return None
    positive = data.get("positive")
    if not isinstance(positive, str) or not positive.strip():
        return None
    negative = data.get("negative") if isinstance(data.get("negative"), str) else ""
    changes = [c for c in data.get("changes", []) if isinstance(c, str)] if isinstance(data.get("changes"), list) else []
    assumptions = [a for a in data.get("assumptions", []) if isinstance(a, str)] if isinstance(data.get("assumptions"), list) else []
    variants = []
    if isinstance(data.get("variants"), list):
        for item in data.get("variants", []):
            if isinstance(item, dict) and isinstance(item.get("prompt"), str) and item["prompt"].strip():
                variants.append({"label": str(item.get("label") or ""), "prompt": item["prompt"]})
    # 变体最多两个（超出截断）
    return {
        "positive": positive.strip(),
        "negative": negative.strip(),
        "changes": changes,
        "assumptions": assumptions,
        "variants": variants[:2],
    }


async def optimize_prompt(
    prompt: str,
    mode: str,
    target: str,
    model_id: str = "",
    reference_names: Optional[list[str]] = None,
) -> dict:
    """
    优化提示词并返回结构化结果（positive/negative/changes/assumptions/variants）。
    LLM 异常与两次解析失败统一抛 RuntimeError（路由层映射 502）。
    """
    llm_prompt = _build_prompt(prompt, mode, target, model_id, reference_names or [])
    last_error: Optional[Exception] = None
    for _ in range(2):
        try:
            text = await call_llm(llm_prompt)
            result = _normalize_result(parse_json_loose(text))
        except RuntimeError as e:
            last_error = e
            continue
        if result is not None:
            return result
        last_error = RuntimeError("优化结果解析失败，请重试")
    raise last_error or RuntimeError("提示词优化失败，请重试")
