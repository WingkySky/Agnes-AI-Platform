# =====================================================
# Pipeline 模板审核服务
# - prescreen_template_revision: 公开模板修订草稿的 AI 预筛
#   复用 submit-public 流程的敏感词检测逻辑（app.services.moderation_service.check_sensitive_text）
# =====================================================

import logging
from typing import Tuple, List

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pipeline_template_revision import PipelineTemplateRevision

logger = logging.getLogger("agnes_platform.pipeline")


async def prescreen_template_revision(
    db: AsyncSession, revision: PipelineTemplateRevision
) -> Tuple[bool, List[str]]:
    """
    对 revision 进行 AI 预筛（敏感词检测）。

    与 submit-public 流程一致：
      - 检查 name / description / tags / submit_reason 中是否包含敏感词
      - 命中 → revision.is_rejected=True，记录 reject_reason，返回 (True, hit_words)
      - 未命中 → revision 保持 pending 状态，由 admin_review 队列接管，返回 (False, [])

    通过后 revision 自然可被 admin_review 列表查询到（is_approved=False 且 is_rejected=False）。
    """
    from app.services.moderation_service import check_sensitive_text

    check_text = " ".join([
        revision.name or "",
        revision.description or "",
        " ".join(revision.tags or []),
        revision.submit_reason or "",
    ])
    hit, hit_words = await check_sensitive_text(db, check_text)
    if hit:
        revision.is_approved = False
        revision.is_rejected = True
        revision.reject_reason = f"AI 预筛命中敏感词：{', '.join(hit_words[:5])}"
        logger.info(
            "[模板修订预筛] revision id=%s 命中敏感词: %s",
            revision.id, hit_words[:5],
        )
    else:
        # 未命中 → 保持 pending，等待 admin 审核
        revision.is_approved = False
        revision.is_rejected = False
        revision.reject_reason = None
        logger.info("[模板修订预筛] revision id=%s 通过 AI 预筛，进入 admin 审核队列", revision.id)

    return hit, hit_words
