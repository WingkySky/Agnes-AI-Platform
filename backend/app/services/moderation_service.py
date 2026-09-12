# =====================================================
# 内容审核服务
# - 敏感词检测（Prompt 文本审核）
# - AI 图像/视频内容审核（调用多模态模型判断画面是否违规）
# - 自动预审：命中后自动标记为待审核或直接拒绝
# =====================================================

import asyncio
import base64
import json
import logging
import os
import tempfile
import time
from datetime import datetime
from typing import List, Tuple, Optional, Dict, Any
import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.database import async_session
from app.models.generation import Generation
from app.models.sensitive_word import SensitiveWord, DEFAULT_SENSITIVE_WORDS

logger = logging.getLogger("agnes_platform")


# ---------- 敏感词进程内缓存 ----------
# 缓存结构：(words_list, updated_at)，TTL 60 秒
# 敏感词表更新不频繁，但每次审核都全表加载开销大，因此做进程内缓存
_sensitive_words_cache: tuple[List[str], float] | None = None
_SENSITIVE_WORDS_CACHE_TTL = 60.0  # 秒


def invalidate_sensitive_words_cache() -> None:
    """清除敏感词缓存（在敏感词增删改后调用）"""
    global _sensitive_words_cache
    _sensitive_words_cache = None


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
    # 初始化后清除缓存（防止之前残留的缓存影响后续审核）
    invalidate_sensitive_words_cache()


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

    # 先查进程内缓存（60 秒 TTL）
    global _sensitive_words_cache
    words_lower: List[str] = []
    if _sensitive_words_cache is not None:
        cached_words, updated_at = _sensitive_words_cache
        if time.time() - updated_at < _SENSITIVE_WORDS_CACHE_TTL:
            words_lower = cached_words
        else:
            _sensitive_words_cache = None

    # 缓存未命中：读取所有启用的敏感词
    if not words_lower:
        result = await db.execute(
            select(SensitiveWord).filter(SensitiveWord.is_active == 1)
        )
        rows = result.scalars().all()
        if not rows:
            # 仍然缓存空结果，避免连续空查打 DB
            _sensitive_words_cache = ([], time.time())
            return False, []
        words_lower = [w.word.lower() for w in rows]
        _sensitive_words_cache = (words_lower, time.time())

    if not words_lower:
        return False, []

    text_lower = text.lower()
    hit_words = [w for w in words_lower if w in text_lower]

    return (len(hit_words) > 0), hit_words


# ---------- 为 Generation 记录应用审核结果 ----------


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


async def _moderate_frame_with_ai(frame_b64: str, user_text: str, scene: str = "") -> Dict[str, Any]:
    """
    用多模态聊天模型审核单帧图片内容
    （模型解析、messages 构造、chat_text 调用、结果解析与异常降级）。

    scene 用于日志区分审核对象（如"视频"首帧审核）。

    返回格式同 moderate_image_with_ai。
    """
    from app.services.agnes_client import agnes_client

    # 审核为系统级任务：管理员配置 model.moderation_chat > 系统默认对话模型
    try:
        from app.services.model_registry import resolve_system_chat_model_id, SYSTEM_CHAT_MODEL_KEYS
        model = await resolve_system_chat_model_id(None, SYSTEM_CHAT_MODEL_KEYS["moderation"])
    except Exception:
        model = ""
    if not model:
        logger.warning("[AI审核] 无可用聊天模型，降级为通过")
        return {"success": False, "is_violation": False, "categories": [], "reason": "", "confidence": 0.0}

    # 构造多模态消息（OpenAI 兼容格式）
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

    try:
        content = await agnes_client.chat_text(
            model, messages, temperature=0.1, max_tokens=500,
        )

        parsed = _parse_moderation_result(content)
        parsed["success"] = True
        return parsed
    except Exception as e:
        logger.warning(f"[AI审核] 调用 AI {scene}审核失败: %s", e)
        return {"success": False, "is_violation": False, "categories": [], "reason": "", "confidence": 0.0}


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
    # 下载图片为 base64
    image_b64 = await _download_image_as_base64(image_url)
    if not image_b64:
        # 下载失败，降级为通过（不误伤）
        logger.warning("[AI审核] 图片下载失败，降级为通过: url=%s", image_url[:80])
        return {"success": False, "is_violation": False, "categories": [], "reason": "", "confidence": 0.0}

    # 构造用户提示词（附带上原始 prompt 作为参考）
    user_text = "请审核以下图片内容是否违规。"
    if prompt:
        user_text += f"\n\n图片的生成提示词（供参考）：{prompt[:500]}"

    return await _moderate_frame_with_ai(image_b64, user_text)


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

    user_text = "请审核以下视频的首帧图片内容是否违规。注意：这只是首帧，可能无法代表完整视频内容，请谨慎判断。"
    if prompt:
        user_text += f"\n\n视频的生成提示词（供参考）：{prompt[:500]}"

    return await _moderate_frame_with_ai(frame_b64, user_text, scene="视频")


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


# =====================================================
# 资产分享审核（与 generations 复用同一套多模态预审）
# 资产表无 ai_moderation_status 列，结果直接落在 moderation_status：
#   - 违规 → rejected
#   - 不违规 → pending（等待人工复审）
#   - 失败 → pending（人工兜底）
# =====================================================

async def run_async_asset_moderation(
    asset_id: int,
    gen_type: str,
    result_url: Optional[str],
    prompt: Optional[str] = None,
) -> None:
    """
    后台异步任务：调用 AI 多模态模型审核资产内容（图片/视频）。
    结果写回 assets 表的 moderation_status 与 moderation_reason。
    该函数由 asyncio.create_task 触发，不阻塞分享接口响应。
    """
    from app.core.database import async_session
    from app.models.asset import Asset

    try:
        result = await moderate_generation_with_ai(gen_type, result_url, prompt)

        async with async_session() as db:
            stmt = select(Asset).filter(Asset.id == asset_id)
            res = await db.execute(stmt)
            asset = res.scalar_one_or_none()
            if not asset:
                return

            if not result.get("success"):
                # 审核调用失败，保持 pending，等人工审核
                asset.moderation_status = "pending"
                asset.moderation_reason = "系统预审失败，等待人工审核"
                await db.commit()
                logger.info("[AI审核] 资产 %d 审核失败，保持待审核", asset_id)
                return

            if result.get("is_violation"):
                categories = result.get("categories", []) or []
                reason = result.get("reason", "") or ""
                confidence = result.get("confidence", 0)
                asset.moderation_status = "rejected"
                reason_text = f"AI 预审不通过：{reason}"
                if categories:
                    reason_text += f"（{', '.join(categories[:3])}）"
                reason_text += f"，置信度 {int(confidence * 100)}%"
                asset.moderation_reason = reason_text
                await db.commit()
                logger.info("[AI审核] 资产 %d 判定违规: %s", asset_id, reason_text)
            else:
                # AI 判定没问题 → 保持 pending，等人工复审
                asset.moderation_status = "pending"
                asset.moderation_reason = "AI 预审通过，等待人工复审"
                await db.commit()
                logger.info("[AI审核] 资产 %d AI 预审通过，等待人工复审", asset_id)

    except Exception as e:
        logger.exception("[AI审核] 资产后台任务异常 id=%d: %s", asset_id, e)


# =====================================================
# 生成记录（generations）后台审核
# 分享置公开时的统一入口：置 pending + 敏感词筛查 + 异步 AI 审核
# =====================================================


async def mark_pending_with_keyword_check(record: Generation, db: AsyncSession) -> None:
    """
    分享置公开时：记录进入待审核状态，并做敏感词快速筛查（结果写入 flags/reason）。
    """
    # 默认待审核
    record.moderation_status = "pending"
    record.moderation_flags = None
    record.moderation_reason = "审核中：等待系统预审"
    # AI 预审状态：进入 pending，等异步任务跑完更新
    record.ai_moderation_status = "pending"

    # 敏感词快速筛查（作为 flags 记录下来，供管理员参考）
    try:
        hit, hit_words = await check_sensitive_text(db, record.prompt or "")
        if hit:
            record.moderation_flags = hit_words
            record.moderation_reason = f"审核中：提示词命中敏感词（{', '.join(hit_words[:3])}），等待图像审核"
    except Exception as mod_err:
        logger.warning("[广场] 分享时敏感词检测失败: %s", mod_err)


def queue_ai_moderation(record: Generation) -> None:
    """
    异步触发 AI 图像/视频内容审核后台任务（不阻塞调用方响应）。
    """
    try:
        asyncio.create_task(run_async_generation_moderation(
            record.id, record.type, record.result_url, record.prompt,
        ))
    except Exception as task_err:
        logger.warning("[广场] 启动 AI 异步审核失败 id=%d: %s", record.id, task_err)


async def run_async_generation_moderation(
    record_id: int,
    gen_type: str,
    result_url: Optional[str],
    prompt: Optional[str],
) -> None:
    """
    后台异步任务：调用 AI 多模态模型审核图片/视频内容。
    审核完成后更新记录的 moderation_status 与 ai_moderation_status：
    - 违规 → moderation_status=rejected, ai_moderation_status=violated
    - 不违规 → moderation_status=pending, ai_moderation_status=passed（等人工复审）
    - 审核失败 → moderation_status=pending, ai_moderation_status=failed（人工兜底）
    """
    try:
        result = await moderate_generation_with_ai(gen_type, result_url, prompt)

        async with async_session() as db:
            stmt = select(Generation).filter(Generation.id == record_id)
            res = await db.execute(stmt)
            record = res.scalar_one_or_none()
            if not record:
                return

            if not result.get("success"):
                # 审核失败，保持 pending，等人工审核
                record.moderation_reason = "系统预审失败，等待人工审核"
                record.ai_moderation_status = "failed"
                await db.commit()
                logger.info("[AI审核] 记录 %d 审核失败，保持待审核", record_id)
                return

            if result.get("is_violation"):
                # AI 判定违规 → 直接设为 rejected
                categories = result.get("categories", []) or []
                reason = result.get("reason", "") or ""
                confidence = result.get("confidence", 0)
                record.moderation_status = "rejected"
                record.ai_moderation_status = "violated"
                # 把 AI 审核结果追加到 flags 里
                existing_flags = record.moderation_flags or []
                if isinstance(existing_flags, list):
                    new_flags = list(existing_flags)
                else:
                    new_flags = []
                for cat in categories:
                    if cat not in new_flags:
                        new_flags.append(cat)
                record.moderation_flags = new_flags
                reason_text = f"AI 预审不通过：{reason}"
                if categories:
                    reason_text += f"（{', '.join(categories[:3])}）"
                reason_text += f"，置信度 {int(confidence * 100)}%"
                record.moderation_reason = reason_text
                record.moderated_at = datetime.utcnow()
                await db.commit()
                logger.info("[AI审核] 记录 %d 判定违规: %s", record_id, reason_text)
            else:
                # AI 判定没问题 → 保持 pending，等人工复审
                record.ai_moderation_status = "passed"
                reason = "AI 预审通过，等待人工复审"
                flags = record.moderation_flags or []
                if not flags:
                    record.moderation_reason = reason
                else:
                    record.moderation_reason = f"{reason}（提示词含敏感词，需人工确认）"
                await db.commit()
                logger.info("[AI审核] 记录 %d AI 预审通过，等待人工复审", record_id)

    except Exception as e:
        # 异常时也标记为 failed，方便管理员识别
        try:
            async with async_session() as db:
                stmt = select(Generation).filter(Generation.id == record_id)
                res = await db.execute(stmt)
                record = res.scalar_one_or_none()
                if record:
                    record.ai_moderation_status = "failed"
                    record.moderation_reason = "AI 审核任务异常，等待人工审核"
                    await db.commit()
        except Exception:
            pass
        logger.exception("[AI审核] 后台任务异常 id=%d: %s", record_id, e)
