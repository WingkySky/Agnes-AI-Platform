# =====================================================
# 历史资源迁移脚本（一次性工具）
# 职责：扫描历史 generations 记录，对未转存的非 Agnes URL 尝试下载转存到对象存储
# 用法：
#   cd backend
#   python -m app.scripts.migrate_legacy_assets           # 执行迁移
#   python -m app.scripts.migrate_legacy_assets --dry-run # 预览将处理的记录
#   python -m app.scripts.migrate_legacy_assets --limit 50 # 限制单次处理数量
# =====================================================

import argparse
import asyncio
import logging
import sys
from typing import List, Optional, Tuple

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import new_async_session
from app.models.generation import Generation
from app.services import asset_storage

# ---------- 日志配置 ----------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("migrate_legacy_assets")

# ---------- Agnes 域名关键词 ----------
# 包含这些关键词的 URL 视为 Agnes 域名，不需要转存
AGNES_DOMAIN_KEYWORDS = ("agnes-ai.space", "agnes-aigc", "storage.googleapis.com/agnes-")


# ---------- 辅助函数 ----------
def is_agnes_url(url: str) -> bool:
    """判断 URL 是否为 Agnes 域名（不需要转存）"""
    if not url:
        return False
    return any(kw in url for kw in AGNES_DOMAIN_KEYWORDS)


async def fetch_pending_records(session: AsyncSession, limit: int) -> List[Generation]:
    """查询未转存的老记录：migrate_status IS NULL AND original_url IS NULL"""
    stmt = (
        select(Generation)
        .where(Generation.migrate_status.is_(None))
        .where(Generation.original_url.is_(None))
        .where(Generation.result_url.isnot(None))
        .where(Generation.result_url != "")
        .order_by(Generation.created_at.asc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    return result.scalars().all()


async def migrate_record(record: Generation) -> Tuple[str, str, Optional[str]]:
    """
    迁移单条记录
    返回 (status, message, new_result_url_or_none)
    - status: 'success' / 'failed' / 'skipped'
    - new_result_url: 转存成功时为新的 URL，其他情况为 None
    """
    url = record.result_url
    if not url.startswith(("http://", "https://")):
        return ("skipped", f"非 HTTP URL: {url[:80]}", None)

    if is_agnes_url(url):
        return ("skipped", f"Agnes URL 不需转存: {url[:80]}", None)

    try:
        # 直接调用 _do_migrate 强制转存（一次性脚本可访问私有函数）
        new_result_url, original_url, migrate_status = await asset_storage._do_migrate(
            upstream_url=url,
            record_id=record.id,
            type=record.type,
            created_at=record.created_at,
        )
        if migrate_status == "done":
            return ("success", f"转存成功: {new_result_url[:80]}", new_result_url)
        else:
            return ("failed", f"转存失败（URL 可能已过期）: {url[:80]}", None)
    except Exception as e:
        return ("failed", f"转存异常: {e}", None)


# ---------- 主流程 ----------
async def main(args):
    logger.info("=" * 60)
    logger.info("历史资源迁移脚本启动")
    logger.info("参数: dry_run=%s limit=%s", args.dry_run, args.limit)
    logger.info("=" * 60)

    # 检查对象存储是否已配置
    if not asset_storage.is_configured():
        logger.error("对象存储未配置，无法执行迁移。请先在 .env 中配置 STORAGE_* 参数。")
        return

    async with new_async_session() as session:
        records = await fetch_pending_records(session, args.limit)
        logger.info("查询到 %s 条未转存记录", len(records))

        if args.dry_run:
            # dry-run 模式：仅预览，不执行转存
            logger.info("[dry-run 模式] 仅预览，不执行转存：")
            agnes_count = 0
            non_http_count = 0
            migrate_count = 0
            for r in records:
                if not r.result_url.startswith(("http://", "https://")):
                    non_http_count += 1
                elif is_agnes_url(r.result_url):
                    agnes_count += 1
                else:
                    migrate_count += 1
                    logger.info("  将转存: id=%s type=%s url=%s", r.id, r.type, r.result_url[:80])
            logger.info("预览统计: 待转存 %s, Agnes 跳过 %s, 非 HTTP 跳过 %s",
                        migrate_count, agnes_count, non_http_count)
            return

        # 实际执行迁移
        success_count = 0
        failed_count = 0
        skipped_count = 0

        for idx, record in enumerate(records, 1):
            logger.info("[%s/%s] 处理记录 id=%s type=%s", idx, len(records), record.id, record.type)
            status, msg, new_url = await migrate_record(record)

            if status == "success" and new_url:
                success_count += 1
                # 更新数据库：写入新的 result_url，保留原始 URL 到 original_url
                try:
                    stmt = (
                        update(Generation)
                        .where(Generation.id == record.id)
                        .values(
                            result_url=new_url,
                            original_url=record.result_url,  # 保留原 URL
                            migrate_status="done",
                        )
                    )
                    await session.execute(stmt)
                    await session.commit()
                    logger.info("  成功: %s", msg)
                except Exception as e:
                    logger.error("  数据库更新失败: id=%s error=%s", record.id, e)
                    await session.rollback()
            elif status == "failed":
                failed_count += 1
                logger.warning("  失败: %s", msg)
            else:
                skipped_count += 1
                logger.info("  跳过: %s", msg)

        logger.info("=" * 60)
        logger.info("迁移完成统计: 成功 %s, 失败 %s, 跳过 %s", success_count, failed_count, skipped_count)
        logger.info("=" * 60)


# ---------- 命令行参数解析 ----------
def parse_args():
    parser = argparse.ArgumentParser(description="历史资源迁移脚本")
    parser.add_argument("--dry-run", action="store_true", help="仅预览，不执行转存")
    parser.add_argument("--limit", type=int, default=1000, help="单次处理数量上限（默认 1000）")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(main(args))
