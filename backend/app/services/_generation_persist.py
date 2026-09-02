# =====================================================
# 生成结果落库公共逻辑（image_poller / video_poller 共享）
#
# 两份 _persist_result 及积分确认/退还、过期任务清理逻辑
# 几乎逐字相同，统一抽到此模块；两轮询器仅保留各自的
# 差异点（图片 b64 包装与 params 过滤、视频 poll 循环）。
# =====================================================

import asyncio
import logging
import time
from datetime import datetime
from typing import Dict, List, Optional

from sqlalchemy import select

from app.services.provider_registry import provider_registry
from app.services import asset_storage
from app.models.generation import Generation
from app.models.model_definition import ModelDefinition
from app.core.database import new_async_session
from app.services.credits_service import confirm_credits, refund_credits
from app.services import asset_archive

logger = logging.getLogger("agnes_platform")

# ---------- 清理参数 ----------
CLEANUP_INTERVAL_SEC = 300   # 每 5 分钟扫描一次过期缓存
CLEANUP_TTL_SEC = 3600       # 已完成任务保留 1 小时后清除


def as_container_id(value) -> Optional[str]:
    """容器 ID 统一存字符串（项目 ID 是数字，剧本面板 ID 是字符串）"""
    return None if value is None or value == "" else str(value)


async def confirm_generation_credits(task, ref_id, log_prefix: str) -> None:
    """生成成功后，把对应的预扣流水状态改为 confirmed（积分不变）"""
    if not task.user_id or not task.credits_consumed:
        return
    if not ref_id:
        return
    try:
        async with new_async_session() as session:
            await confirm_credits(session, task.user_id, ref_id)
    except Exception as e:
        logger.warning("%s 确认积分失败: ref_id=%s error=%s", log_prefix, ref_id, e)


async def refund_generation_credits(
    task, ref_id, kind_label: str, log_prefix: str
) -> None:
    """生成失败/取消/超时后，退还预扣的积分"""
    if not task.user_id or not task.credits_consumed:
        return
    if not ref_id:
        return
    try:
        async with new_async_session() as session:
            await refund_credits(
                session, task.user_id, ref_id,
                reason=f"{kind_label}生成失败：{task.error_message or '未知错误'}",
            )
    except Exception as e:
        logger.error("%s 退还积分失败: ref_id=%s error=%s", log_prefix, ref_id, e)


async def persist_generation(
    task,
    *,
    kind: str,                       # "image" / "video"（Generation.type）
    result_url: str,                 # 初始结果 URL（图片侧含 b64 data URI 兜底，视频侧为 video_url）
    record_params: Dict,             # Generation.params（图片侧过滤多模态大字段后传入）
    record_task_id: Optional[str],   # Generation.task_id（视频侧 task.task_id or video_id）
    log_prefix: str,                 # 日志前缀 "[图片任务器]" / "[视频轮询器]"
) -> None:
    """
    任务成功后把结果异步写入 generations 表（调用方需先保证 task.status == "success"）。

    流程：敏感词预审（仅公开作品）→ 写记录 → 资源转存（HTTP URL）→ 创作归档。
    """
    try:
        async with new_async_session() as session:
            # 从 params 提取广场分享标记
            is_public = task.params.get("is_public", False)

            # ===== 自动预审：敏感词检测（针对公开作品）=====
            moderation_status = "approved"
            moderation_flags = None
            moderation_reason = None
            if is_public and task.prompt:
                try:
                    from app.services.moderation_service import check_sensitive_text
                    hit, hit_words = await check_sensitive_text(session, task.prompt)
                    if hit:
                        moderation_status = "pending"
                        moderation_flags = hit_words
                        moderation_reason = f"命中敏感词: {', '.join(hit_words[:5])}"
                except Exception as mod_err:
                    logger.warning("%s 自动预审失败: %s", log_prefix, mod_err)

            record = Generation(
                type=kind,
                user_id=task.user_id,
                prompt=task.prompt,
                model=task.params.get("model", ""),
                params=record_params,
                mode=task.params.get("mode"),
                result_url=result_url,  # 先用原始 URL，转存成功后再更新
                status=task.status,
                credits_consumed=task.credits_consumed,
                task_id=record_task_id,
                is_public=is_public,
                public_shared_at=datetime.utcnow() if is_public else None,
                moderation_status=moderation_status,
                moderation_flags=moderation_flags,
                moderation_reason=moderation_reason,
                preset_id=task.preset_id,
                # 创作归属：画布/项目生成打标，历史页据此默认过滤
                source=(task.context or {}).get("source") or "independent",
                container_type=(task.context or {}).get("container_type"),
                container_id=as_container_id((task.context or {}).get("container_id")),
            )
            session.add(record)
            await session.commit()  # 先提交拿到 record.id

            # ===== 资源转存：把上游 URL 转存到对象存储（仅对 HTTP/HTTPS URL，跳过 data URI） =====
            if result_url and result_url.startswith(("http://", "https://")):
                try:
                    model_id = task.params.get("model", "")

                    # 查询模型的 asset_storage_mode（默认 auto）
                    asset_storage_mode = "auto"
                    try:
                        stmt = select(ModelDefinition.asset_storage_mode).where(
                            ModelDefinition.model_id == model_id
                        )
                        mode_result = await session.execute(stmt)
                        mode_row = mode_result.first()
                        if mode_row:
                            asset_storage_mode = mode_row[0]
                    except Exception as mode_err:
                        logger.warning(
                            "%s 查询 asset_storage_mode 失败，用默认 auto: task_id=%s error=%s",
                            log_prefix, task.task_id, mode_err,
                        )

                    # 查询 provider_type（用于 auto 模式判断是否需要转存）
                    provider_type = ""
                    try:
                        provider_type = await provider_registry.get_provider_type(model_id)
                    except Exception as pt_err:
                        logger.warning(
                            "%s 查询 provider_type 失败: task_id=%s error=%s",
                            log_prefix, task.task_id, pt_err,
                        )

                    logger.info(
                        "%s 资源转存开始: task_id=%s model_id=%s mode=%s provider_type=%s",
                        log_prefix, task.task_id, model_id, asset_storage_mode, provider_type,
                    )
                    # 执行转存（失败不抛异常，返回 pending 状态）
                    new_result_url, original_url, migrate_status = await asset_storage.migrate_if_needed(
                        upstream_url=result_url,
                        record_id=record.id,
                        type=kind,
                        created_at=record.created_at,
                        model_id=model_id,
                        asset_storage_mode=asset_storage_mode,
                        provider_type=provider_type,
                    )
                    # 用转存结果更新记录
                    record.result_url = new_result_url
                    record.original_url = original_url
                    record.migrate_status = migrate_status
                    await session.commit()
                    logger.info(
                        "%s 资源转存完成: task_id=%s migrate_status=%s",
                        log_prefix, task.task_id, migrate_status,
                    )
                except Exception as migrate_err:
                    # 转存失败不影响主流程：记录已写入，result_url 保持原始 URL，migrate_status 保持 NULL
                    logger.error(
                        "%s 资源转存异常: task_id=%s error=%s",
                        log_prefix, task.task_id, migrate_err, exc_info=True,
                    )

            # ===== 创作归档：画布/项目生成自动归档进资产库（旁路，失败仅记日志）=====
            # archive_to_asset 内部自带 container 守卫：无 container 上下文直接跳过
            try:
                await asset_archive.archive_to_asset(session, record, task.context or {})
            except Exception as archive_err:
                logger.error(
                    "%s 创作归档失败（不影响主流程）: task_id=%s error=%s",
                    log_prefix, task.task_id, archive_err, exc_info=True,
                )
        logger.info(
            "%s 记录已异步写入数据库: task_id=%s moderation=%s",
            log_prefix, task.task_id, moderation_status,
        )
    except Exception as e:
        logger.error("%s 数据库写入失败: %s", log_prefix, e)


async def cleanup_expired_tasks(
    tasks: dict, lock: asyncio.Lock, log_prefix: str, on_remove=None
) -> None:
    """
    定期清理已完成/失败/取消且超过 TTL 的任务缓存，防止内存泄漏。

    Args:
        tasks: 任务字典（key -> task）
        lock: 保护 tasks 的 asyncio.Lock
        on_remove: 可选回调 (key, task)，用于同步清理附加索引（如视频的 video_id 反查表）
    """
    while True:
        await asyncio.sleep(CLEANUP_INTERVAL_SEC)
        try:
            now = time.time()
            removed: List[str] = []
            async with lock:
                for key, t in list(tasks.items()):
                    if t.status in ("success", "failed", "cancelled") and (
                        now - t.last_updated > CLEANUP_TTL_SEC
                    ):
                        removed.append(key)
                        if on_remove:
                            on_remove(key, t)
                for key in removed:
                    del tasks[key]
            if removed:
                logger.info("%s 已清理 %s 个过期任务缓存", log_prefix, len(removed))
        except Exception as e:
            logger.error("%s 清理协程异常: %s", log_prefix, e)
