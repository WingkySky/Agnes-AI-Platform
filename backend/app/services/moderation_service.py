# =====================================================
# 内容审核服务
# - 敏感词检测（Prompt 文本审核）
# - AI 图像/视频内容审核（调用多模态模型判断画面是否违规）
# - 自动预审：命中后自动标记为待审核或直接拒绝
# =====================================================

import base64
import logging
import os
import tempfile
from typing import List, Tuple, Optional, Dict, Any
import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models.sensitive_word import SensitiveWord, DEFAULT_SENSITIVE_WORDS

logger = logging.getLogger("agnes_platform")


# ---------- 初始化默认敏感词 ----------
async def ensure_default_sensitive_words(db: AsyncSession) -> None:
    """确保默认敏感词存在，启动时调用"""
    for word in DEFAULT_SENSITIVE_WORDS:
        result = await db.execute(select(SensitiveWord).filter(SensitiveWord.word == word))
        if not result.scalar_one_or_none():
            db.add(SensitiveWord(
                word=word,
                category="other",
                description="系统默认敏感词",
                is_active=1,
            ))
    await db.commit()


# ---------- 敏感词检测 ----------
async def check_sensitive_text(
    db: AsyncSession,
    text: str,
) -> Tuple[bool, List[str]]:
    """
    检查文本中是否包含敏感词。
    返回：(是否命中, 命中的敏感词列表)
    """
    if not text:
        return False, []

    # 读取所有启用的敏感词
    result = await db.execute(
        select(SensitiveWord).filter(SensitiveWord.is_active == 1)
    )
    words = result.scalars().all()
    if not words:
        return False, []

    text_lower = text.lower()
    hit_words = []
    for w in words:
        if w.word.lower() in text_lower:
            hit_words.append(w.word)

    return (len(hit_words) > 0), hit_words


# ---------- 为 Generation 记录应用审核结果 ----------
def apply_moderation_result(record, hit_words: List[str], reason: Optional[str] = None):
    """
    将敏感词检测结果应用到 Generation 记录。
    命中后设置 moderation_status = 'pending'，并记录命中的关键词。
    """
    if hit_words:
        record.moderation_status = "pending"
        record.moderation_flags = hit_words
        record.moderation_reason = reason or f"命中敏感词: {', '.join(hit_words[:5])}"
    else:
        record.moderation_status = "approved"
        record.moderation_flags = None
        record.moderation_reason = None


# =====================================================
# AI 内容审核（基于多模态聊天模型）
# =====================================================

# 审核违规类别定义
_MODERATION_CATEGORIES = {
    "sexual": "色情露骨内容",
    "violence": "血腥暴力内容",
    "illegal": "违法违规内容",
    "hate": "仇恨歧视内容",
    "politics": "政治敏感内容",
    "drugs": "毒品相关内容",
    "weapons": "武器爆炸物",
    "self_harm": "自残自杀内容",
    "other": "其他违规内容",
}

# 审核系统提示词
_MODERATION_SYSTEM_PROMPT = """你是一个内容安全审核员。请仔细检查提供的图片内容，判断其是否违反社区规范。

违规类别：
1. sexual - 色情露骨内容（裸体、性行为、色情暗示等）
2. violence - 血腥暴力内容（严重暴力、血腥、虐待等）
3. illegal - 违法违规内容
4. hate - 仇恨歧视内容（种族、性别、宗教歧视等）
5. politics - 政治敏感内容
6. drugs - 毒品相关内容
7. weapons - 武器爆炸物
8. self_harm - 自残自杀内容
9. other - 其他违规内容

请严格按照以下 JSON 格式输出，不要输出任何其他文字：
{
  "is_violation": true/false,
  "categories": ["类别1", "类别2"],
  "confidence": 0.95,
  "reason": "简要说明违规原因"
}

注意：
- 正常的艺术、医疗、教育类图片不视为违规
- 轻度暴力（如动作电影海报）不视为违规
- 泳装、正常人体艺术不视为色情
- 如果不确定是否违规，is_violation 设为 false
- confidence 范围 0-1，表示判断的置信度"""


async def _download_image_as_base64(image_url: str) -> Optional[str]:
    """
    下载图片并转为 base64 data URI。
    失败返回 None。
    """
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            resp = await client.get(image_url, headers={"User-Agent": "Agnes-Moderation"})
            if resp.status_code != 200:
                logger.warning("[AI审核] 下载图片失败: status=%d, url=%s", resp.status_code, image_url)
                return None
            ct = resp.headers.get("content-type", "")
            if ct and ("text/html" in ct or "application/xhtml" in ct):
                logger.warning("[AI审核] 图片返回 HTML: url=%s", image_url)
                return None
            # 推断 MIME 类型
            if not ct or ct.startswith("application/octet-stream"):
                lower_url = image_url.lower()
                if lower_url.endswith(".png"):
                    ct = "image/png"
                elif lower_url.endswith((".jpg", ".jpeg")):
                    ct = "image/jpeg"
                elif lower_url.endswith(".webp"):
                    ct = "image/webp"
                elif lower_url.endswith(".gif"):
                    ct = "image/gif"
                else:
                    ct = "image/png"
            b64 = base64.b64encode(resp.content).decode("ascii")
            return f"data:{ct};base64,{b64}"
    except Exception as e:
        logger.warning("[AI审核] 下载图片异常: %s", e)
        return None


async def _extract_video_first_frame(video_url: str) -> Optional[str]:
    """
    提取视频首帧图片并转为 base64 data URI。
    使用 ffmpeg 提取，失败返回 None。
    """
    import asyncio
    tmp_video = os.path.join(tempfile.gettempdir(), f"mod_vid_{os.urandom(8).hex()}.mp4")
    tmp_frame = os.path.join(tempfile.gettempdir(), f"mod_frame_{os.urandom(8).hex()}.jpg")
    try:
        # 下载视频前 5MB
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            async with client.stream("GET", video_url, headers={
                "User-Agent": "Agnes-Moderation",
                "Range": "bytes=0-5242879",  # 5MB
            }) as resp:
                if resp.status_code not in (200, 206):
                    logger.warning("[AI审核] 下载视频失败: status=%d", resp.status_code)
                    return None
                with open(tmp_video, "wb") as f:
                    async for chunk in resp.aiter_bytes():
                        f.write(chunk)
                        if f.tell() >= 5 * 1024 * 1024:
                            break
        if not os.path.exists(tmp_video) or os.path.getsize(tmp_video) < 1024:
            return None

        # 使用 ffmpeg 提取首帧
        cmd = [
            "ffmpeg", "-y",
            "-i", tmp_video,
            "-vframes", "1",
            "-q:v", "4",
            "-vf", "scale=480:-2",
            tmp_frame,
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=15.0)
        if proc.returncode != 0:
            logger.warning("[AI审核] ffmpeg 提取帧失败: %s", stderr.decode(errors="ignore")[:200])
            return None

        if not os.path.exists(tmp_frame) or os.path.getsize(tmp_frame) < 100:
            return None

        with open(tmp_frame, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("ascii")
        return f"data:image/jpeg;base64,{b64}"
    except Exception as e:
        logger.warning("[AI审核] 提取视频首帧异常: %s", e)
        return None
    finally:
        # 清理临时文件
        for p in (tmp_video, tmp_frame):
            try:
                if os.path.exists(p):
                    os.remove(p)
            except Exception:
                pass


def _parse_moderation_result(content: str) -> Dict[str, Any]:
    """
    解析 AI 返回的审核结果 JSON。
    返回：{is_violation: bool, categories: [...], reason: str, confidence: float}
    """
    import json
    text = (content or "").strip()
    # 尝试直接解析
    try:
        data = json.loads(text)
    except Exception:
        # 尝试从文本中提取 JSON 部分
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                data = json.loads(text[start:end + 1])
            except Exception:
                data = {}
        else:
            data = {}

    is_violation = bool(data.get("is_violation", False))
    categories = data.get("categories", []) or []
    reason = data.get("reason", "") or ""
    confidence = float(data.get("confidence", 0.0) or 0.0)

    # 类别映射为中文标签
    category_labels = []
    for cat in categories:
        label = _MODERATION_CATEGORIES.get(cat)
        if label:
            category_labels.append(label)
        elif cat in _MODERATION_CATEGORIES.values():
            category_labels.append(cat)  # 已经是中文

    return {
        "is_violation": is_violation,
        "categories": category_labels,
        "reason": reason,
        "confidence": confidence,
    }


async def moderate_image_with_ai(
    image_url: str,
    prompt: Optional[str] = None,
) -> Dict[str, Any]:
    """
    使用 AI 多模态模型审核图片内容。

    返回：
    {
        "success": bool,          # 审核是否成功（失败时降级为通过）
        "is_violation": bool,     # 是否违规
        "categories": [...],      # 违规类别列表（中文）
        "reason": str,            # 违规原因
        "confidence": float,      # 置信度
    }
    """
    from app.services.agnes_client import agnes_client
    from app.services.model_registry import get_models_by_type

    # 下载图片为 base64
    image_b64 = await _download_image_as_base64(image_url)
    if not image_b64:
        # 下载失败，降级为通过（不误伤）
        logger.warning("[AI审核] 图片下载失败，降级为通过: url=%s", image_url[:80])
        return {"success": False, "is_violation": False, "categories": [], "reason": "", "confidence": 0.0}

    # 获取聊天模型
    try:
        chat_models = await get_models_by_type("chat")
        model = chat_models[0].id if chat_models else ""
    except Exception:
        model = ""
    if not model:
        logger.warning("[AI审核] 无可用聊天模型，降级为通过")
        return {"success": False, "is_violation": False, "categories": [], "reason": "", "confidence": 0.0}

    # 构造用户提示词（附带上原始 prompt 作为参考）
    user_text = "请审核以下图片内容是否违规。"
    if prompt:
        user_text += f"\n\n图片的生成提示词（供参考）：{prompt[:500]}"

    # 构造多模态消息（OpenAI 兼容格式）
    messages = [
        {"role": "system", "content": _MODERATION_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": user_text},
                {
                    "type": "image_url",
                    "image_url": {"url": image_b64},
                },
            ],
        },
    ]

    body = {
        "model": model,
        "messages": messages,
        "temperature": 0.1,
        "max_tokens": 500,
    }

    try:
        chat_url = f"{agnes_client.base_url}/chat/completions"
        result = await agnes_client._post(chat_url, body)
        choice = result.get("choices", [{}])[0]
        message = choice.get("message", {})
        content = message.get("content", "") or ""

        parsed = _parse_moderation_result(content)
        parsed["success"] = True
        return parsed
    except Exception as e:
        logger.warning("[AI审核] 调用 AI 审核失败: %s", e)
        return {"success": False, "is_violation": False, "categories": [], "reason": "", "confidence": 0.0}


async def moderate_video_with_ai(
    video_url: str,
    prompt: Optional[str] = None,
) -> Dict[str, Any]:
    """
    使用 AI 审核视频内容（提取首帧进行审核）。

    返回格式同 moderate_image_with_ai。
    """
    # 提取视频首帧
    frame_b64 = await _extract_video_first_frame(video_url)
    if not frame_b64:
        logger.warning("[AI审核] 视频首帧提取失败，降级为通过: url=%s", video_url[:80])
        return {"success": False, "is_violation": False, "categories": [], "reason": "", "confidence": 0.0}

    from app.services.agnes_client import agnes_client
    from app.services.model_registry import get_models_by_type

    # 获取聊天模型
    try:
        chat_models = await get_models_by_type("chat")
        model = chat_models[0].id if chat_models else ""
    except Exception:
        model = ""
    if not model:
        logger.warning("[AI审核] 无可用聊天模型，降级为通过")
        return {"success": False, "is_violation": False, "categories": [], "reason": "", "confidence": 0.0}

    user_text = "请审核以下视频的首帧图片内容是否违规。注意：这只是首帧，可能无法代表完整视频内容，请谨慎判断。"
    if prompt:
        user_text += f"\n\n视频的生成提示词（供参考）：{prompt[:500]}"

    messages = [
        {"role": "system", "content": _MODERATION_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": user_text},
                {
                    "type": "image_url",
                    "image_url": {"url": frame_b64},
                },
            ],
        },
    ]

    body = {
        "model": model,
        "messages": messages,
        "temperature": 0.1,
        "max_tokens": 500,
    }

    try:
        chat_url = f"{agnes_client.base_url}/chat/completions"
        result = await agnes_client._post(chat_url, body)
        choice = result.get("choices", [{}])[0]
        message = choice.get("message", {})
        content = message.get("content", "") or ""

        parsed = _parse_moderation_result(content)
        parsed["success"] = True
        return parsed
    except Exception as e:
        logger.warning("[AI审核] 调用 AI 视频审核失败: %s", e)
        return {"success": False, "is_violation": False, "categories": [], "reason": "", "confidence": 0.0}


async def moderate_generation_with_ai(
    gen_type: str,
    result_url: Optional[str],
    prompt: Optional[str] = None,
) -> Dict[str, Any]:
    """
    统一入口：根据生成类型（image/video）调用对应的 AI 审核。

    返回：同 moderate_image_with_ai
    """
    if not result_url:
        return {"success": False, "is_violation": False, "categories": [], "reason": "", "confidence": 0.0}
    if gen_type == "video":
        return await moderate_video_with_ai(result_url, prompt)
    else:
        return await moderate_image_with_ai(result_url, prompt)
