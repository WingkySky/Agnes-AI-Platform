# =====================================================
# 流水线运行服务
# 提供给 API 层调用的高层服务，封装创建、查询、取消等操作
# =====================================================

import logging
import json
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any, Tuple

from fastapi import HTTPException
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pipeline import PipelineRun, PipelineStep, PipelineTemplate
from app.models.pipeline_step_output_revision import PipelineStepOutputRevision
from app.services.pipeline.engine import (
    PipelineEngine,
    create_pipeline_run,
    start_pipeline,
    resume_pipeline,
    cancel_pipeline,
)
from app.services import credits_service
from app.services.pipeline.template_service import get_template_by_id
from app.services.pipeline.sse_manager import pipeline_sse_manager

logger = logging.getLogger("agnes_platform.pipeline")


# ---------- 查询 ----------

async def get_run_by_id(db: AsyncSession, run_id: int) -> Optional[PipelineRun]:
    """根据 ID 获取流水线实例"""
    result = await db.execute(select(PipelineRun).filter(PipelineRun.id == run_id))
    return result.scalar_one_or_none()


async def get_run_steps(db: AsyncSession, run_id: int) -> List[PipelineStep]:
    """获取流水线的所有步骤"""
    result = await db.execute(
        select(PipelineStep)
        .filter(PipelineStep.run_id == run_id)
        .order_by(PipelineStep.sort_order)
    )
    return list(result.scalars().all())


async def list_runs(
    db: AsyncSession,
    user_id: Optional[int] = None,
    status: Optional[str] = None,
    template_id: Optional[int] = None,
    search: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
    include_deleted: bool = False,
) -> Tuple[List[PipelineRun], int]:
    """获取流水线实例列表（分页）"""
    query = select(PipelineRun)

    filters = []
    if not include_deleted:
        filters.append(PipelineRun.is_deleted == False)
    if user_id is not None:
        filters.append(PipelineRun.user_id == user_id)
    if status:
        filters.append(PipelineRun.status == status)
    if template_id:
        filters.append(PipelineRun.template_id == template_id)
    if search:
        search_pattern = f"%{search}%"
        filters.append(or_(
            PipelineRun.name.ilike(search_pattern),
        ))

    if filters:
        query = query.where(*filters)

    # 总数
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    query = query.order_by(PipelineRun.created_at.desc()).offset(
        (page - 1) * page_size
    ).limit(page_size)

    result = await db.execute(query)
    items = result.scalars().all()
    return list(items), total


async def get_step_by_key(db: AsyncSession, run_id: int, step_key: str) -> Optional[PipelineStep]:
    """根据 step_key 获取步骤详情"""
    result = await db.execute(
        select(PipelineStep).filter(
            PipelineStep.run_id == run_id,
            PipelineStep.step_key == step_key,
        )
    )
    return result.scalar_one_or_none()


# ---------- 创建 & 启动 ----------

async def create_and_start_run(
    db: AsyncSession,
    template_id: int,
    inputs: Dict[str, Any],
    user_id: Optional[int] = None,
    name: Optional[str] = None,
) -> PipelineRun:
    """
    创建并启动流水线。

    1. 检查用户并发限制（最多 2 个同时运行）
    2. 验证模板
    3. 预估积分并同步预扣（积分不足立即抛 402，避免创建后才失败）
    4. 创建 pipeline_run 和所有步骤记录
    5. 初始化 SSE 快照（确保前端连接时能立即看到状态）
    6. 在后台启动执行（不阻塞当前请求）
    7. 返回 run 信息

    积分预扣说明：
    - 登录用户必须在创建前同步预扣足额积分，避免"创建成功但后台执行时才积分不足"
    - 预扣使用 ref_id=pipeline_run:{run_id}，但 run_id 此时还未生成，
      所以预扣发生在创建 run 之后、后台启动之前
    - 失败的步骤会在 engine 中按步退还（_refund_step_credits）
    - 流水线整体失败时退还剩余（_refund_remaining_credits）
    """
    # 验证模板
    template = await get_template_by_id(db, template_id)
    if not template:
        raise HTTPException(status_code=404, detail="流水线模板不存在")

    # 检查并发限制（登录用户最多同时运行 2 个）
    if user_id is not None:
        await _check_concurrency_limit(db, user_id)

    # 创建实例（状态为 pending）— 先创建拿到 run_id，用于积分预扣的 ref_id
    run = await create_pipeline_run(
        db=db,
        template_id=template_id,
        inputs=inputs,
        user_id=user_id,
        name=name,
    )

    # 同步预扣积分（登录用户）— 在后台启动前执行，积分不足立即抛 402
    # 匿名用户跳过（无积分概念）
    if user_id is not None:
        await _precharge_credits_for_run(db, run, template, inputs)

    # 立即初始化 SSE 快照，确保前端跳转连接时能收到初始 pending 状态
    pipeline_sse_manager.init_snapshot(run.id, status="pending")

    # 后台启动（附带 SSE 进度回调）— engine.start() 不再重复预扣
    sse_callback = pipeline_sse_manager.make_progress_callback(run.id)
    await start_pipeline(run.id, progress_callback=sse_callback)

    logger.info(f"流水线已创建并启动: run_id={run.id}, template={template.key}, user_id={user_id}")
    return run


async def _precharge_credits_for_run(
    db: AsyncSession,
    run: PipelineRun,
    template: PipelineTemplate,
    inputs: Dict[str, Any],
) -> None:
    """
    为流水线同步预扣积分（在创建 run 之后、后台启动之前调用）。

    - 登录用户必须积分足够，否则抛 402（API 立即返回错误）
    - 使用模板的 estimated_credits 或 estimate_credits() 计算预扣金额
    - ref_id 格式: pipeline_run:{run_id}，与 engine._refund_remaining_credits 对齐
    - 积分不足时已经创建的 run 记录会被标记为 cancelled（避免遗留 pending 状态）
    """
    from app.models.user import User

    # 计算预扣金额：优先用模板预估，否则实时估算
    estimated_total = template.estimated_credits or 0
    if estimated_total <= 0:
        # 模板没填预估，实时计算（按步骤类型累加）
        estimate_result = await estimate_credits(db, template.id, inputs)
        estimated_total = estimate_result.get("estimated_total", 0)

    if estimated_total <= 0:
        # 无需扣积分（可能是免费模板或估算为 0）
        logger.info(f"[积分预扣] 跳过：预估积分为 0，run_id={run.id}")
        return

    # 获取用户对象（预扣需要 user 对象）
    result = await db.execute(select(User).filter(User.id == run.user_id))
    user = result.scalar_one_or_none()
    if not user:
        return

    ref_id = f"pipeline_run:{run.id}"
    description = f"流水线预扣: {template.name} (run_id={run.id})"

    try:
        await credits_service.consume_credits(
            db,
            user,
            estimated_total,
            description,
            ref_type="pipeline_run",
            ref_id=ref_id,
        )
        logger.info(
            f"[积分预扣] 成功 run_id={run.id} user_id={run.user_id} amount={estimated_total}"
        )
    except HTTPException as e:
        # 积分不足：把已创建的 run 标记为 cancelled，避免遗留 pending 状态
        # 用户看到的体验是"创建失败，积分不足"
        from app.models.pipeline import STATUS_CANCELLED
        run.status = STATUS_CANCELLED
        run.error_message = f"积分不足: {e.detail}" if isinstance(e.detail, str) else "积分不足"
        run.finished_at = datetime.utcnow()
        await db.commit()
        logger.warning(
            f"[积分预扣] 失败（积分不足） run_id={run.id} amount={estimated_total}: {e.detail}"
        )
        raise


# ---------- 操作 ----------

async def retry_run(
    db: AsyncSession,
    run_id: int,
    user_id: Optional[int] = None,
) -> PipelineRun:
    """
    失败后重试流水线 / 暂停后继续执行。

    - failed/cancelled：只重置失败步骤及其下游，已成功步骤跳过
    - paused：重置暂停时未完成的步骤（pending/paused 状态）及其下游

    积分处理：
    - 失败的步骤在 engine 中已通过 _refund_step_credits 退还
    - 重试时需要重新预扣这些步骤的预估积分
    - 积分不足则拒绝重试（402）
    - paused 状态无需重新预扣（积分已在首次执行时预扣）
    """
    run = await get_run_by_id(db, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="流水线不存在")

    if user_id is not None and run.user_id != user_id:
        raise HTTPException(status_code=403, detail="无权操作此流水线")

    if run.status not in ("failed", "cancelled", "paused"):
        raise HTTPException(
            status_code=400,
            detail=f"当前状态 {run.status} 不支持重试，仅 failed/cancelled/paused 状态可以重试",
        )

    steps = await get_run_steps(db, run_id)

    if run.status == "paused":
        # 暂停恢复：找出所有 paused/pending 步骤（未完成步骤）及其下游
        unfinished_steps = {s.step_key for s in steps if s.status in ("paused", "pending")}
        if not unfinished_steps:
            # 极端情况：暂停时刚好所有步骤都完成了
            run.status = "pending"
            await db.commit()
            await db.refresh(run)
            sse_callback = pipeline_sse_manager.make_progress_callback(run.id)
            await resume_pipeline(run.id, progress_callback=sse_callback)
            logger.info(f"暂停恢复（所有步骤已完成）: run_id={run_id}")
            return run

        steps_to_reset = _get_downstream_steps(steps, unfinished_steps) | unfinished_steps
        # paused 状态已预扣积分，无需重新检查
        is_paused_recovery = True
    else:
        # failed/cancelled：重置失败步骤及其下游
        failed_steps = {s.step_key for s in steps if s.status == "failed"}
        if not failed_steps:
            raise HTTPException(status_code=400, detail="没有失败的步骤需要重试")
        steps_to_reset = _get_downstream_steps(steps, failed_steps)
        is_paused_recovery = False

        # 重试前检查积分是否足够覆盖待重跑步骤的预估消耗
        if run.user_id is not None:
            await _check_credits_for_retry(db, run, steps, steps_to_reset)

    for step in steps:
        if step.step_key in steps_to_reset:
            step.status = "pending"
            step.error_message = None
            step.output_data = {}
            step.started_at = None
            step.finished_at = None
            step.retry_count = 0

    # 重置 run 状态，paused 恢复时清除 pause_requested
    run.status = "pending"
    run.error_message = None
    run.finished_at = None
    if is_paused_recovery:
        run.pause_requested = False

    await db.commit()
    await db.refresh(run)

    # 后台恢复执行（带 SSE 推送）
    sse_callback = pipeline_sse_manager.make_progress_callback(run.id)
    await resume_pipeline(run.id, progress_callback=sse_callback)

    logger.info(f"重试流水线: run_id={run_id}, 重置步骤数={len(steps_to_reset)}, paused_恢复={is_paused_recovery}")
    return run


async def retry_step(
    db: AsyncSession,
    run_id: int,
    step_key: str,
    user_id: Optional[int] = None,
    reset_output: bool = True,
) -> PipelineStep:
    """
    单独重试某一步骤（及其下游）。
    用户可以在查看步骤详情时选择单独重试。

    积分处理：同 retry_run，重试前检查积分是否足够覆盖待重跑步骤。
    """
    run = await get_run_by_id(db, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="流水线不存在")

    if user_id is not None and run.user_id != user_id:
        raise HTTPException(status_code=403, detail="无权操作此流水线")

    if run.status in ("running", "pending"):
        raise HTTPException(status_code=400, detail="流水线正在运行中，请等待完成后再重试")

    step = await get_step_by_key(db, run_id, step_key)
    if not step:
        raise HTTPException(status_code=404, detail="步骤不存在")

    # 找出该步骤及其所有下游步骤
    all_steps = await get_run_steps(db, run_id)
    steps_to_reset = _get_downstream_steps(all_steps, {step_key})

    # 重试前检查积分是否足够覆盖待重跑步骤
    if run.user_id is not None:
        await _check_credits_for_retry(db, run, all_steps, steps_to_reset)

    for s in all_steps:
        if s.step_key in steps_to_reset:
            s.status = "pending"
            s.error_message = None
            if reset_output:
                s.output_data = {}
            s.started_at = None
            s.finished_at = None
            s.retry_count = 0

    # 重置 run 状态
    run.status = "pending"
    run.error_message = None
    run.finished_at = None

    await db.commit()
    await db.refresh(step)

    # 后台恢复执行（带 SSE 推送）
    sse_callback = pipeline_sse_manager.make_progress_callback(run.id)
    await resume_pipeline(run.id, progress_callback=sse_callback)

    logger.info(f"重试单步骤: run_id={run_id}, step={step_key}")
    return step


async def _check_credits_for_retry(
    db: AsyncSession,
    run: PipelineRun,
    all_steps: List[PipelineStep],
    steps_to_reset: set,
) -> None:
    """
    重试前检查用户积分是否足够覆盖待重跑步骤的预估消耗。

    策略：
    - 累加待重跑步骤的预估积分（用 step.credits_consumed 或按类型估算）
    - 检查用户当前余额是否 >= 预估总额
    - 不足则抛 402，避免重试后中途又积分不足

    注意：这里只做"余额检查"，不实际预扣。
    实际扣费仍由 engine 在步骤执行时按步处理（_precharge 已在创建时做过全额预扣，
    失败步骤已退还，重试时这些步骤相当于"重新消费"，所以需要重新预扣）。
    为简化实现，这里用余额检查代替精确预扣，engine 会在步骤成功时确认扣费。
    """
    from app.models.user import User

    # 计算待重跑步骤的预估总积分
    estimated_needed = 0
    for step in all_steps:
        if step.step_key not in steps_to_reset:
            continue
        # 优先用该步骤上次消耗的积分作为预估
        if step.credits_consumed and step.credits_consumed > 0:
            estimated_needed += step.credits_consumed
        else:
            # 按步骤类型估算
            estimated_needed += _estimate_step_credits_by_type(step.step_type)

    if estimated_needed <= 0:
        return

    # 查询用户当前积分
    result = await db.execute(select(User.credits).filter(User.id == run.user_id))
    current_credits = result.scalar_one_or_none() or 0

    if current_credits < estimated_needed:
        raise HTTPException(
            status_code=402,
            detail=(
                f"积分不足，无法重试（当前 {current_credits}，"
                f"重试约需 {estimated_needed}）。请联系管理员充值"
            ),
        )

    logger.info(
        f"[重试积分检查] run_id={run.id} user_id={run.user_id} "
        f"current={current_credits} needed={estimated_needed}"
    )


def _estimate_step_credits_by_type(step_type: Optional[str]) -> int:
    """按步骤类型估算单步积分（与 estimate_credits 中的逻辑一致）"""
    if step_type == "llm_generate":
        return 5
    if step_type == "image_batch":
        return 80  # 8 场景 * 1 张 * 10 积分
    if step_type == "video_batch":
        return 240  # 8 场景 * 5 秒 * 6 积分
    if step_type == "tts_generate":
        return 5
    if step_type == "ffmpeg_composite":
        return 2
    return 10


async def cancel_run(
    db: AsyncSession,
    run_id: int,
    user_id: Optional[int] = None,
) -> None:
    """取消流水线"""
    run = await get_run_by_id(db, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="流水线不存在")

    if user_id is not None and run.user_id != user_id:
        raise HTTPException(status_code=403, detail="无权操作此流水线")

    if run.status not in ("running", "pending"):
        raise HTTPException(
            status_code=400,
            detail=f"当前状态 {run.status} 不支持取消",
        )

    await cancel_pipeline(run_id, user_id)


# ---------- 暂停 ----------

async def pause_run(
    db: AsyncSession,
    run_id: int,
    user_id: Optional[int] = None,
) -> PipelineRun:
    """
    请求暂停正在运行的流水线。

    设 pause_requested=True，引擎在下一轮循环时检测到标志位后会：
    - 将 run 状态设为 paused
    - 保存当前步骤进度
    - 退出执行循环
    """
    run = await get_run_by_id(db, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="流水线不存在")

    if user_id is not None and run.user_id != user_id:
        raise HTTPException(status_code=403, detail="无权操作此流水线")

    if run.status != "running":
        raise HTTPException(
            status_code=400,
            detail=f"当前状态 {run.status} 不支持暂停，仅 running 状态可以暂停",
        )

    run.pause_requested = True
    await db.commit()
    await db.refresh(run)

    logger.info(f"流水线暂停请求已发送: run_id={run_id}")
    return run


# ---------- 编辑 inputs ----------

async def update_run_inputs(
    db: AsyncSession,
    run_id: int,
    inputs: Dict[str, Any],
    user_id: Optional[int] = None,
) -> PipelineRun:
    """
    在 paused 状态下编辑流水线 inputs。

    暂停后用户可以修改输入参数（如调整角色描述、画风等），
    然后继续执行，后续步骤会使用更新后的 inputs。
    """
    run = await get_run_by_id(db, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="流水线不存在")

    if user_id is not None and run.user_id != user_id:
        raise HTTPException(status_code=403, detail="无权操作此流水线")

    if run.status not in ("paused", "pending", "failed", "cancelled"):
        raise HTTPException(
            status_code=400,
            detail=f"当前状态 {run.status} 不支持编辑 inputs，仅 paused/pending/failed/cancelled 状态可以编辑",
        )

    # 合并 inputs（保留原有未修改的字段）
    merged = dict(run.inputs or {})
    merged.update(inputs)
    run.inputs = merged
    await db.commit()
    await db.refresh(run)

    logger.info(f"流水线 inputs 已更新: run_id={run_id}")
    return run


# ---------- 导出到画布 ----------

async def export_run_to_canvas(
    db: AsyncSession,
    run_id: int,
    user_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    将流水线结果导出到画布。

    收集最终视频和所有分镜图片 URL，写入 PipelineRun.canvas_export_data。
    返回画布节点格式的数据。

    canvas_export_data 结构：
    {
        "video": "最终视频 URL",
        "scenes": ["分镜图片 URL 1", "分镜图片 URL 2", ...]
    }
    """
    run = await get_run_by_id(db, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="流水线不存在")

    if user_id is not None and run.user_id != user_id:
        raise HTTPException(status_code=403, detail="无权操作此流水线")

    if run.status != "success":
        raise HTTPException(
            status_code=400,
            detail=f"当前状态 {run.status} 不可导出，仅 success 状态可以导出到画布",
        )

    # 收集最终视频 URL
    output_summary = run.output_summary or {}
    final_video = output_summary.get("final_video_url") or output_summary.get("video_url") or ""

    # 收集分镜图片：从 image_batch 步骤的输出中提取
    steps = await get_run_steps(db, run_id)
    scene_images: List[str] = []
    for step in steps:
        if step.step_type == "image_batch" and step.status == "success":
            output = step.output_data or {}
            images = output.get("images", []) or output.get("results", [])
            for img in images:
                if isinstance(img, dict):
                    url = img.get("url") or img.get("image_url") or img.get("result_url", "")
                    if url:
                        scene_images.append(url)
                elif isinstance(img, str):
                    scene_images.append(img)

    export_data: Dict[str, Any] = {
        "video": final_video,
        "scenes": scene_images,
    }

    # 写入数据库
    run.canvas_export_data = export_data
    await db.commit()
    await db.refresh(run)

    logger.info(
        f"流水线结果已导出到画布: run_id={run_id}, "
        f"video={'有' if final_video else '无'}, "
        f"scenes={len(scene_images)}"
    )
    return export_data


# ---------- 删除 ----------

async def delete_run(
    db: AsyncSession,
    run_id: int,
    user_id: Optional[int] = None,
) -> PipelineRun:
    """
    软删除流水线运行记录。

    设置 is_deleted=True + deleted_at=now，保留数据库记录用于统计审计。
    不会级联删除关联的 pipeline_outputs 产物文件（用户可手动清理）。
    """
    run = await get_run_by_id(db, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="流水线不存在")

    if user_id is not None and run.user_id != user_id:
        raise HTTPException(status_code=403, detail="无权操作此流水线")

    if run.is_deleted:
        raise HTTPException(status_code=400, detail="流水线已删除")

    run.is_deleted = True
    run.deleted_at = datetime.utcnow()
    await db.commit()
    await db.refresh(run)

    logger.info(f"流水线已软删除: run_id={run_id}, user_id={user_id}")
    return run


# ---------- 辅助函数 ----------

# 同一用户最大并发运行的流水线数
MAX_PARALLEL_RUNS_PER_USER = 2


async def _check_concurrency_limit(db: AsyncSession, user_id: int) -> None:
    """
    检查用户的并发流水线数量限制。

    如果达到上限，抛出 429 错误。
    """
    from app.models.pipeline import STATUS_RUNNING, STATUS_PENDING

    result = await db.execute(
        select(func.count()).select_from(PipelineRun).where(
            PipelineRun.user_id == user_id,
            PipelineRun.status.in_([STATUS_RUNNING, STATUS_PENDING]),
        )
    )
    count = result.scalar_one() or 0

    if count >= MAX_PARALLEL_RUNS_PER_USER:
        raise HTTPException(
            status_code=429,
            detail=f"最多同时运行 {MAX_PARALLEL_RUNS_PER_USER} 个流水线，请等待当前任务完成后再创建新的"
        )


def _get_downstream_steps(all_steps: List[PipelineStep], start_keys: set) -> set:
    """
    找出指定步骤及其所有下游步骤（依赖这些步骤的步骤）。

    用于重试时确定需要重置哪些步骤。
    """
    result = set(start_keys)
    changed = True

    while changed:
        changed = False
        for step in all_steps:
            if step.step_key in result:
                continue
            # 如果该步骤的依赖中有任何一个在 result 中，它也需要被重置
            depends_on = step.depends_on or []
            if any(dep in result for dep in depends_on):
                result.add(step.step_key)
                changed = True

    return result


# ---------- 启动自检（基于产物状态修正僵尸流水线） ----------

def _check_step_has_output(step: PipelineStep) -> bool:
    """
    检查步骤是否已有实际产物（用于服务重启时自检状态）。

    判断规则按 step_type 区分：
    - image_batch / video_batch：output_data 中 images/videos 列表非空
    - ffmpeg_composite：final_video_path 文件实际存在
    - script_generation / llm_generate：parsed_result 或 raw_response 非空
    - 其他：output_data 非空即视为有产物

    Returns:
        True 表示产物完整，可恢复为 success；False 表示产物缺失，应标 failed
    """
    output = step.output_data or {}
    if not output:
        return False

    step_type = step.step_type or ""

    if step_type == "image_batch":
        return bool(output.get("images"))
    if step_type == "video_batch":
        return bool(output.get("videos"))
    if step_type == "ffmpeg_composite":
        # 最终视频文件必须实际存在
        final_path = output.get("final_video_path")
        if not final_path:
            return False
        import os
        return os.path.exists(final_path)
    if step_type in ("script_generation", "llm_generate"):
        return bool(output.get("parsed_result") or output.get("raw_response"))
    # 其他类型：output_data 非空即视为有产物
    return True


async def _check_url_accessible(url: str, client: Any) -> bool:
    """
    检查单个 URL 是否可访问（用于僵尸恢复时元素级产物校验）。

    判断规则：
    - HTTP(S) URL → HEAD 请求，状态码 < 400 视为可访问；HEAD 失败回退 GET
    - /pipeline/outputs/ 开头的静态路径 → 拼接本地目录检查文件存在
    - 其他本地路径 → 直接检查文件存在

    Args:
        url: 待检查的 URL 或本地路径
        client: 复用的 httpx.AsyncClient 连接池（HTTP 场景）

    Returns:
        True 表示可访问
    """
    import os

    if not url or not isinstance(url, str):
        return False

    # HTTP(S) URL → HEAD 请求检查
    if url.startswith(("http://", "https://")):
        try:
            resp = await client.head(url, follow_redirects=True)
            if resp.status_code < 400:
                return True
            # 部分 OSS 不支持 HEAD，回退 GET
            resp = await client.get(url, follow_redirects=True)
            return resp.status_code < 400
        except Exception:
            return False

    # /pipeline/outputs/ 静态路径 → 映射到本地 data/pipeline_outputs 目录
    if url.startswith("/pipeline/outputs/"):
        from app.services.pipeline.steps.ffmpeg_composite import _OUTPUT_BASE
        filename = url[len("/pipeline/outputs/"):]
        # 防目录穿越
        if "/" in filename or "\\" in filename or ".." in filename:
            return False
        local_path = os.path.join(_OUTPUT_BASE, filename)
        return os.path.exists(local_path) and os.path.isfile(local_path)

    # 其他本地路径 → 直接检查文件存在
    return os.path.exists(url) and os.path.isfile(url)


async def _check_step_items_output(step: PipelineStep) -> Tuple[bool, Dict[str, Any]]:
    """
    对步骤 output_data.items 做元素级产物可访问性检查（用于僵尸恢复）。

    遍历每个 item 的 image_url / video_url / audio_url：
    - 已是 failed 状态的 item 直接保留
    - 有产物 URL 的 item：任一 URL 不可访问 → 标 status=failed, error="产物 URL 不可访问"
    - 所有 URL 均可访问 → 标 status=success
    - 无 URL 字段的 item 保持原状态

    最后重新计算 summary（total/success_count/failed_count）。

    Returns:
        (overall_success, updated_output_data)
        - overall_success: True 表示至少有一个元素成功；False 表示全部失败
        - updated_output_data: 更新后的 output_data（含修正后的 items 和 summary）
    """
    import asyncio
    import httpx

    output = step.output_data or {}
    items = output.get("items")
    if not isinstance(items, list) or not items:
        # 无 items 或空列表 → 让调用方走原逻辑
        return False, output

    # 并发检查所有 item 的产物 URL（复用 httpx 连接池）
    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
        async def check_item(item: Dict[str, Any]) -> Dict[str, Any]:
            """检查单个 item 的产物 URL 可访问性"""
            if not isinstance(item, dict):
                return item

            # 已是 failed 状态的 item 直接保留（不重复检查）
            if item.get("status") == "failed":
                return item

            # 检查所有产物 URL 字段，任一不可访问即视为失败
            url_fields = ("image_url", "video_url", "audio_url")
            has_url = False
            for field in url_fields:
                url = item.get(field)
                if url:
                    has_url = True
                    if not await _check_url_accessible(url, client):
                        item["status"] = "failed"
                        item["error"] = "产物 URL 不可访问"
                        break

            # 有可访问产物 URL 的 item → 标记为 success（确保 status 字段存在）
            if has_url and item.get("status") != "failed":
                item["status"] = "success"
                item["error"] = None

            return item

        # 并发执行所有元素检查
        checked_items = await asyncio.gather(*[check_item(it) for it in items])

    # 重新计算 summary
    success_count = sum(
        1 for it in checked_items
        if isinstance(it, dict) and it.get("status") == "success"
    )
    failed_count = len(checked_items) - success_count

    new_output = dict(output)
    new_output["items"] = list(checked_items)
    new_output["summary"] = {
        "total": len(checked_items),
        "success_count": success_count,
        "failed_count": failed_count,
    }

    return success_count > 0, new_output


async def recover_zombie_runs(db: AsyncSession) -> Dict[str, int]:
    """
    服务启动时自检僵尸流水线：根据实际产物修正状态。

    扫描所有 status in (running, pending) 的 run（paused 是用户主动暂停，不处理），
    对每个 run 下 status in (pending, running) 的 step 做 _check_step_has_output 自检：
    - 产物完整 → step 标 success（避免重启后重复生成已完成的产物）
    - 产物缺失 → step 标 failed（让用户可以正常点重试，不会卡在等待中）

    最后根据所有步骤的最终状态汇总 run 状态：
    - 全部 success/skipped → run 标 success
    - 有任意 failed → run 标 failed

    Returns:
        {"runs_checked": N, "recovered_to_success": N, "marked_failed": N}
    """
    from datetime import datetime, timezone

    # 扫描所有 running/pending 状态的 run（paused 不动，保留用户主动暂停语义）
    zombie_runs = (
        await db.execute(
            select(PipelineRun).where(PipelineRun.status.in_(["running", "pending"]))
        )
    ).scalars().all()

    if not zombie_runs:
        logger.info("✓ 无僵尸流水线记录")
        return {"runs_checked": 0, "recovered_to_success": 0, "marked_failed": 0}

    now = datetime.now(timezone.utc)
    recovered = 0
    failed = 0

    for run in zombie_runs:
        # 查询该 run 下所有未完成的步骤
        unfinished_steps = (
            await db.execute(
                select(PipelineStep).where(
                    PipelineStep.run_id == run.id,
                    PipelineStep.status.in_(["pending", "running"]),
                )
            )
        ).scalars().all()

        # 按产物自检逐个修正状态
        for step in unfinished_steps:
            output = step.output_data or {}
            # 优先做元素级检查（针对 output_data.items 数组的步骤，如 scene_gen/character_gen/prop_gen）
            if isinstance(output.get("items"), list) and output["items"]:
                overall_success, new_output = await _check_step_items_output(step)
                step.output_data = new_output
                if overall_success:
                    # 至少一个元素成功 → 步骤标 success（部分元素失败仍算成功）
                    step.status = "success"
                    step.finished_at = step.finished_at or now
                    step.error_message = None
                else:
                    # 所有元素产物均不可访问 → 标 failed
                    step.status = "failed"
                    step.finished_at = now
                    step.error_message = "服务重启，任务已中断（所有元素产物均不可访问）"
                continue

            # 无 items 字段 → 沿用原有整体产物判定逻辑
            if _check_step_has_output(step):
                # 产物完整 → 恢复为 success（避免重启后重复生成）
                step.status = "success"
                step.finished_at = step.finished_at or now
                step.error_message = None
            else:
                # 产物缺失 → 标 failed（让用户可以重试，不会卡在 running）
                step.status = "failed"
                step.finished_at = now
                step.error_message = "服务重启，任务已中断（产物未生成）"

        # 根据"所有步骤"最终状态汇总 run 状态
        all_steps = (
            await db.execute(
                select(PipelineStep).where(PipelineStep.run_id == run.id)
            )
        ).scalars().all()
        any_failed = any(s.status == "failed" for s in all_steps)
        all_done = all(s.status in ("success", "skipped") for s in all_steps)

        if all_done and not any_failed:
            run.status = "success"
            run.finished_at = run.finished_at or now
            run.error_message = None
            recovered += 1
            logger.info(f"  ↳ run #{run.id} 自检恢复为 success（所有步骤产物完整）")
        else:
            run.status = "failed"
            run.finished_at = now
            run.error_message = "服务重启，任务已中断（部分步骤产物未生成，请重试）"
            failed += 1
            missing = [s.step_key for s in unfinished_steps if s.status == "failed"]
            logger.info(f"  ↳ run #{run.id} 自检标记为 failed（缺失产物步骤: {missing}）")

    await db.commit()
    logger.warning(
        f"⚠️ 已自检 {len(zombie_runs)} 条僵尸流水线：{recovered} 条恢复 success，{failed} 条标记 failed"
    )
    return {
        "runs_checked": len(zombie_runs),
        "recovered_to_success": recovered,
        "marked_failed": failed,
    }


# ---------- 积分预估 ----------

async def estimate_credits(
    db: AsyncSession,
    template_id: int,
    inputs: Dict[str, Any],
) -> Dict[str, Any]:
    """
    预估流水线积分消耗。

    注意：这只是粗略预估，实际消耗可能因重试、模型选择等因素变化。
    """
    template = await get_template_by_id(db, template_id)
    if not template:
        raise HTTPException(status_code=404, detail="流水线模板不存在")

    breakdown = []
    total = 0

    # 简单估算：按步骤类型和数量估算
    for step_cfg in template.steps_config:
        step_type = step_cfg.get("type")
        step_name = step_cfg.get("name", step_cfg.get("key", ""))
        step_key = step_cfg.get("key", "")

        estimated = 0

        if step_type == "llm_generate":
            estimated = 5  # LLM 生成大约 5 积分
        elif step_type == "image_batch":
            # 估算图片数量（粗略）
            scenes_count = inputs.get("scenes_count", 8)
            images_per_scene = step_cfg.get("config", {}).get("images_per_character", 3)
            count = scenes_count * images_per_scene
            estimated = count * 10  # 每张图约 10 积分
        elif step_type == "video_batch":
            scenes_count = inputs.get("scenes_count", 8)
            estimated = scenes_count * 30  # 每段视频约 30 积分
        elif step_type == "ffmpeg_composite":
            estimated = 2  # 合成步骤消耗少
        elif step_type == "tts_generate":
            estimated = 5
        else:
            estimated = 10  # 未知类型的默认估算

        breakdown.append({
            "step_key": step_key,
            "step_name": step_name,
            "step_type": step_type,
            "estimated_credits": estimated,
        })
        total += estimated

    return {
        "estimated_total": total,
        "breakdown": breakdown,
        "note": "预估积分仅供参考，实际消耗以执行为准",
    }


# ---------- 字幕编辑 ----------

async def save_subtitles(
    db: AsyncSession,
    run_id: int,
    user_id: int,
    subtitles: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    保存用户编辑后的字幕，重新生成 SRT 文件并更新 ffmpeg_composite 步骤输出。

    处理流程：
    1. 校验 run 归属当前用户
    2. 定位 ffmpeg_composite 步骤（取最后一个成功的）
    3. 校验字幕格式（end > start、text 非空），按 start 升序重新编号 index
    4. 拼接 SRT 内容，覆盖写入原 SRT 文件（文件名 subtitles_{run_id}.srt）
    5. 更新 step.output_data.subtitles 字段并持久化
    6. 返回新的 srt_url 和 subtitles 列表

    Args:
        db: 异步会话
        run_id: 流水线运行 ID
        user_id: 当前用户 ID（鉴权用）
        subtitles: 字幕条目列表 [{start, end, text, scene_index?}, ...]

    Returns:
        {"srt_url": str, "subtitles": List[Dict]}
    """
    import os
    from app.services.pipeline.steps.ffmpeg_composite import _OUTPUT_BASE

    # 1. 校验 run 归属
    run = await get_run_by_id(db, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="流水线不存在")
    if run.user_id != user_id:
        raise HTTPException(status_code=403, detail="无权修改此流水线的字幕")

    # 2. 定位最后一个成功的 ffmpeg_composite 步骤
    steps = await get_run_steps(db, run_id)
    composite_steps = [
        s for s in steps
        if s.step_type == "ffmpeg_composite" and s.status == "success"
    ]
    if not composite_steps:
        raise HTTPException(
            status_code=400,
            detail="未找到已完成的合成步骤，无法编辑字幕"
        )
    composite_step = sorted(
        composite_steps, key=lambda s: s.sort_order, reverse=True
    )[0]

    old_output = dict(composite_step.output_data or {})

    # 3. 校验字幕 + 重新编号 index（按 start 升序）
    if not subtitles:
        raise HTTPException(status_code=400, detail="字幕列表不能为空")

    sorted_subs = sorted(subtitles, key=lambda s: float(s.get("start", 0)))
    cleaned: List[Dict[str, Any]] = []
    for i, sub in enumerate(sorted_subs):
        start = float(sub.get("start", 0))
        end = float(sub.get("end", 0))
        text = str(sub.get("text", "")).strip()
        if end <= start:
            raise HTTPException(
                status_code=400,
                detail=f"第 {i + 1} 条字幕结束时间必须大于开始时间"
            )
        if not text:
            raise HTTPException(
                status_code=400,
                detail=f"第 {i + 1} 条字幕文本不能为空"
            )
        cleaned.append({
            "index": i,
            "scene_index": sub.get("scene_index", i),
            "start": round(start, 3),
            "end": round(end, 3),
            "text": text,
        })

    # 4. 拼接 SRT 内容并写入文件（覆盖原文件）
    # 复用 ffmpeg_composite 步骤执行器的输出目录常量，保证写入位置与路由访问位置一致
    srt_content = _format_srt_content(cleaned)
    os.makedirs(_OUTPUT_BASE, exist_ok=True)
    srt_filename = f"subtitles_{run_id}.srt"
    srt_path = os.path.join(_OUTPUT_BASE, srt_filename)

    try:
        with open(srt_path, "w", encoding="utf-8") as f:
            f.write(srt_content)
    except OSError as e:
        logger.error(f"[字幕编辑] 写入 SRT 文件失败: {srt_path}, error={e}")
        raise HTTPException(status_code=500, detail="字幕文件保存失败")

    srt_url = f"/api/pipeline/outputs/{srt_filename}"
    logger.info(
        f"[字幕编辑] run_id={run_id} 字幕已保存: {srt_path}, 共 {len(cleaned)} 条"
    )

    # 同步生成 VTT 文件（浏览器 <track> 标签需要 VTT 格式，非 SRT）
    vtt_url = old_output.get("vtt_url", "")
    try:
        vtt_filename = f"subtitles_{run_id}.vtt"
        vtt_path = os.path.join(_OUTPUT_BASE, vtt_filename)
        vtt_lines = ["WEBVTT", ""]
        for entry in cleaned:
            start_str = _seconds_to_vtt_time(float(entry["start"]))
            end_str = _seconds_to_vtt_time(float(entry["end"]))
            vtt_lines.append(f"{start_str} --> {end_str}")
            vtt_lines.append(str(entry["text"]))
            vtt_lines.append("")  # 空行分隔
        with open(vtt_path, "w", encoding="utf-8") as f:
            f.write("\n".join(vtt_lines))
        vtt_url = f"/api/pipeline/outputs/{vtt_filename}"
        logger.info(
            f"[字幕编辑] run_id={run_id} VTT 已生成: {vtt_path}"
        )
    except Exception as e:
        # VTT 生成失败不阻断主流程（SRT 已保存成功）
        logger.warning(f"[字幕编辑] run_id={run_id} VTT 生成失败: {e}")

    # 5. 更新 step.output_data（保留其他字段，只覆盖 subtitles / srt_url / vtt_url / has_srt / has_vtt）
    new_output = dict(old_output)
    new_output["subtitles"] = cleaned
    new_output["srt_url"] = srt_url
    new_output["vtt_url"] = vtt_url
    new_output["has_srt"] = True
    new_output["has_vtt"] = bool(vtt_url)
    composite_step.output_data = new_output

    await db.commit()

    return {
        "srt_url": srt_url,
        "vtt_url": vtt_url,
        "subtitles": cleaned,
    }


# ---------- 字幕重新烧录 ----------

async def recompose_video(
    db: AsyncSession,
    run_id: int,
    user_id: int,
    subtitles: Optional[List[Dict[str, Any]]] = None,
    subtitle_style: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    用新字幕/样式重新烧录视频

    流程：
    1. 校验 run 归属当前用户
    2. 定位 video_batch 步骤（取视频 URL 列表）
    3. 定位 ffmpeg_composite 步骤（取原 config + 已保存字幕）
    4. 如 subtitles 为 None，用 step.output_data.subtitles
    5. 如 subtitle_style 为 None，用 output_data.subtitle_style 或默认
    6. 调 recompose_pipeline_video 重新合成
    7. 更新 step.output_data（final_video_url/subtitles/srt_url/vtt_url）
    8. 返回新产物 URL（带 ?v=timestamp 防缓存）

    Args:
        db: 异步会话
        run_id: 流水线运行 ID
        user_id: 当前用户 ID（鉴权用）
        subtitles: 字幕条目列表（None 时用已保存的）
        subtitle_style: 字幕样式配置（None 时用 step output_data 中保存的或默认）

    Returns:
        {
            "final_video_url": str,
            "srt_url": str,
            "vtt_url": str,
            "subtitles": List[Dict],
            "duration_seconds": float,
            "segments_count": int,
        }
    """
    import time
    from app.services.pipeline.steps.ffmpeg_composite import (
        recompose_pipeline_video,
        _OUTPUT_BASE,
    )

    # 1. 校验 run 归属
    run = await get_run_by_id(db, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="流水线不存在")
    if run.user_id != user_id:
        raise HTTPException(status_code=403, detail="无权修改此流水线")

    # 2. 获取所有步骤
    steps = await get_run_steps(db, run_id)

    # 3. 定位 video_batch 步骤（取视频 URL 列表）
    video_steps = [s for s in steps if s.step_type == "video_batch" and s.status == "success"]
    if not video_steps:
        raise HTTPException(
            status_code=400,
            detail="未找到已完成的视频生成步骤，无法重新烧录"
        )
    video_step = sorted(video_steps, key=lambda s: s.sort_order, reverse=True)[0]
    video_output = video_step.output_data or {}
    videos = video_output.get("videos", [])
    if not videos:
        raise HTTPException(status_code=400, detail="视频步骤无产出")
    video_urls = [v.get("video_url") or v.get("url", "") for v in videos]

    # 4. 定位 ffmpeg_composite 步骤（取原 config + 字幕）
    composite_steps = [
        s for s in steps
        if s.step_type == "ffmpeg_composite" and s.status == "success"
    ]
    if not composite_steps:
        raise HTTPException(
            status_code=400,
            detail="未找到已完成的合成步骤，无法重新烧录"
        )
    composite_step = sorted(composite_steps, key=lambda s: s.sort_order, reverse=True)[0]
    composite_output = dict(composite_step.output_data or {})

    # 5. 字幕：优先用传入的，否则用已保存的
    if subtitles is None:
        subtitles = composite_output.get("subtitles", [])
    if not subtitles:
        raise HTTPException(status_code=400, detail="字幕列表为空，无法重新烧录")

    # 6. 字幕样式：优先用传入的，否则用 output_data 中持久化的（PipelineStep 无 config 列，
    #    上次 recompose 写入的 subtitle_style 保存在 output_data 中）
    if subtitle_style is None:
        subtitle_style = composite_output.get("subtitle_style")

    # step_config_dict：原 step config 内容（用于 recompose_pipeline_video 构造 executor）
    # PipelineStep 模型只有 input_data/output_data，没有 config 列；input_data 初始化为 {}
    step_config = composite_step.input_data or {}
    if isinstance(step_config, dict):
        step_config_dict = step_config.get("config", step_config)
    else:
        step_config_dict = {}

    # 7. 定位 tts_generate 步骤（如有，取音频 URL）
    audio_urls: List[str] = []
    tts_steps = [s for s in steps if s.step_type == "tts_generate" and s.status == "success"]
    if tts_steps:
        tts_step = sorted(tts_steps, key=lambda s: s.sort_order, reverse=True)[0]
        tts_output = tts_step.output_data or {}
        audios = tts_output.get("audios", [])
        audio_urls = [a.get("audio_url", "") for a in audios]

    # 8. 调 recompose_pipeline_video 执行重新合成
    try:
        result = await recompose_pipeline_video(
            run_id=run_id,
            user_id=user_id,
            video_urls=video_urls,
            audio_urls=audio_urls,
            subtitles=subtitles,
            subtitle_style=subtitle_style,
            step_config=step_config_dict,
            audio_base_dir=_OUTPUT_BASE,
        )
    except Exception as e:
        logger.error(f"[recompose] run={run_id} 失败: {e}")
        raise HTTPException(status_code=500, detail=f"重新烧录失败: {e}")

    # 9. 更新 step.output_data（PipelineStep 无 config 列，subtitle_style 也写入 output_data 持久化）
    new_output = {
        **composite_output,
        "final_video_url": result["final_video_url"],
        "final_video_path": result["final_video_path"],
        "srt_url": result["srt_url"],
        "vtt_url": result["vtt_url"],
        "subtitles": result["subtitles"],
        "duration_seconds": result["duration_seconds"],
        "segments_count": result["segments_count"],
        "recomposed_at": time.time(),
    }
    # 样式持久化：PipelineStep 没有 config 列，写入 output_data 以便下次 recompose 读取
    if subtitle_style is not None:
        new_output["subtitle_style"] = subtitle_style
    composite_step.output_data = new_output

    await db.commit()

    # 10. 返回带防缓存时间戳的 URL
    ts = int(time.time())
    return {
        "final_video_url": f"{result['final_video_url']}?v={ts}",
        "srt_url": f"{result['srt_url']}?v={ts}",
        "vtt_url": f"{result['vtt_url']}?v={ts}",
        "subtitles": result["subtitles"],
        "duration_seconds": result["duration_seconds"],
        "segments_count": result["segments_count"],
    }


def _format_srt_content(entries: List[Dict[str, Any]]) -> str:
    """
    将字幕条目列表格式化为标准 SRT 文件内容。

    SRT 格式：
        1
        00:00:00,000 --> 00:00:05,200
        字幕文本

        2
        ...
    """
    lines: List[str] = []
    for i, entry in enumerate(entries, start=1):
        lines.append(str(i))
        start_str = _seconds_to_srt_time(float(entry["start"]))
        end_str = _seconds_to_srt_time(float(entry["end"]))
        lines.append(f"{start_str} --> {end_str}")
        lines.append(str(entry["text"]))
        lines.append("")  # 空行分隔
    return "\n".join(lines)


def _seconds_to_srt_time(seconds: float) -> str:
    """将秒数转换为 SRT 时间格式 HH:MM:SS,mmm"""
    if seconds < 0:
        seconds = 0
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    ms = int(round((seconds - int(seconds)) * 1000))
    # 处理 ms 进位到 1000 的情况（浮点精度问题）
    if ms >= 1000:
        ms = 999
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def _seconds_to_vtt_time(seconds: float) -> str:
    """将秒数转换为 VTT 时间格式 HH:MM:SS.mmm（与 SRT 唯一差异：用 . 而非 ,）"""
    if seconds < 0:
        seconds = 0
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    ms = int(round((seconds - int(seconds)) * 1000))
    # 处理 ms 进位到 1000 的情况（浮点精度问题）
    if ms >= 1000:
        ms = 999
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{ms:03d}"


# =====================================================
# Task 11-17：步骤确认 / 元素级重试 / 产物编辑 /
# 下游失效 / 编辑锁 / 版本历史 / 自动确认 / 步骤级重试增强
# =====================================================

# 编辑锁超时时间（5 分钟）
EDIT_LOCK_TIMEOUT_SECONDS = 5 * 60
# 每个 run 最多保留的版本历史数量
MAX_REVISIONS_PER_RUN = 20


# ---------- 下游失效标记（Task 14 工具函数，DAG 传递闭包） ----------

async def mark_downstream_stale(
    db: AsyncSession,
    run_id: int,
    edited_step_key: str,
    reason: str = "上游产物被编辑",
) -> List[str]:
    """
    标记指定步骤的所有下游步骤为 stale（产物已失效）。

    通过 DAG 传递闭包找出 edited_step_key 的所有直接和间接下游步骤
    （即任何 depends_on 链中包含 edited_step_key 的步骤），
    将它们的 stale=True / stale_reason=reason。

    Args:
        db: 异步会话
        run_id: 流水线运行 ID
        edited_step_key: 被编辑的步骤 key
        reason: 失效原因（写入 stale_reason）

    Returns:
        被标记为 stale 的下游步骤 key 列表（用于 SSE 推送）
    """
    steps = await get_run_steps(db, run_id)
    # 收集 edited_step_key 的所有传递性下游
    downstream_keys = _collect_transitive_downstream(steps, edited_step_key)

    marked: List[str] = []
    for step in steps:
        if step.step_key in downstream_keys:
            step.stale = True
            step.stale_reason = reason
            marked.append(step.step_key)

    if marked:
        await db.commit()
        logger.info(
            f"[下游失效] run_id={run_id} edited_step={edited_step_key} "
            f"标记下游 stale: {marked}"
        )
    return marked


def _collect_transitive_downstream(
    all_steps: List[PipelineStep], root_key: str
) -> set:
    """
    收集 root_key 的所有传递性下游步骤 key（直接 + 间接依赖链）。

    与 engine._collect_transitive_dependents 等价，但在 service 层独立实现，
    避免 service 层依赖 engine 内部辅助函数。
    """
    result: set = set()
    queue = [root_key]
    while queue:
        current = queue.pop(0)
        for s in all_steps:
            if s.step_key in result or s.step_key == root_key:
                continue
            if current in (s.depends_on or []):
                result.add(s.step_key)
                queue.append(s.step_key)
    return result


# ---------- 版本历史辅助函数（Task 13/15 共用） ----------

async def _save_step_output_revision(
    db: AsyncSession,
    run_id: int,
    step_key: str,
    output_data: Dict[str, Any],
    edited_by: Optional[int],
    change_summary: str,
) -> Optional[PipelineStepOutputRevision]:
    """
    保存步骤产物的版本快照到 PipelineStepOutputRevision 表。

    每个 run 最多保留 MAX_REVISIONS_PER_RUN 个版本，超过则删除最旧的。
    """
    # 查询当前 run+step 的修订数量与最大 revision 号
    count_result = await db.execute(
        select(func.count()).select_from(PipelineStepOutputRevision).where(
            PipelineStepOutputRevision.run_id == run_id,
            PipelineStepOutputRevision.step_key == step_key,
        )
    )
    rev_count = count_result.scalar_one() or 0

    # 超过上限则删除最旧的
    if rev_count >= MAX_REVISIONS_PER_RUN:
        oldest_result = await db.execute(
            select(PipelineStepOutputRevision)
            .where(
                PipelineStepOutputRevision.run_id == run_id,
                PipelineStepOutputRevision.step_key == step_key,
            )
            .order_by(PipelineStepOutputRevision.revision.asc())
            .limit(rev_count - MAX_REVISIONS_PER_RUN + 1)
        )
        for old_rev in oldest_result.scalars().all():
            await db.delete(old_rev)

    # 计算新 revision 号
    max_rev_result = await db.execute(
        select(func.max(PipelineStepOutputRevision.revision)).where(
            PipelineStepOutputRevision.run_id == run_id,
            PipelineStepOutputRevision.step_key == step_key,
        )
    )
    max_rev = max_rev_result.scalar_one_or_none() or 0
    new_rev = max_rev + 1

    revision = PipelineStepOutputRevision(
        run_id=run_id,
        step_key=step_key,
        revision=new_rev,
        output_data=output_data,
        edited_by=edited_by,
        edited_at=datetime.utcnow(),
        change_summary=change_summary,
    )
    db.add(revision)
    await db.flush()
    return revision


# ---------- Task 11: 确认 / 驳回 ----------

async def confirm_step(
    db: AsyncSession,
    run_id: int,
    step_key: str,
    action: str,
    comment: Optional[str] = None,
    edited_output: Optional[Dict[str, Any]] = None,
    user_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    确认或驳回处于 pending 确认状态的步骤。

    - 验证 run 状态为 paused 且 pause_reason=awaiting_confirmation
    - 验证 step confirmation_status=pending
    - 若 edited_output 非空，先覆盖 step.output_data，并调 mark_downstream_stale 标记下游
    - action=confirm：置 confirmed，清 run.pause_requested 和 pause_reason，调 engine.resume()
    - action=reject：置 rejected + step.status=failed，调 engine._skip_blocked_steps()，
      run 转 failed
    - 推送 confirmation_updated SSE 事件

    Returns:
        包含 run_id / step_key / action / confirmation_status 的字典
    """
    from app.services.pipeline.engine import PipelineEngine

    run = await get_run_by_id(db, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="流水线不存在")

    if user_id is not None and run.user_id != user_id:
        raise HTTPException(status_code=403, detail="无权操作此流水线")

    if action not in ("confirm", "reject"):
        raise HTTPException(status_code=400, detail="action 必须为 confirm 或 reject")

    if run.status != "paused" or run.pause_reason != "awaiting_confirmation":
        raise HTTPException(
            status_code=400,
            detail=f"当前 run 状态 {run.status}（pause_reason={run.pause_reason}），"
            f"不在等待确认状态",
        )

    step = await get_step_by_key(db, run_id, step_key)
    if not step:
        raise HTTPException(status_code=404, detail="步骤不存在")

    if step.confirmation_status != "pending":
        raise HTTPException(
            status_code=400,
            detail=f"步骤 confirmation_status={step.confirmation_status}，"
            f"非 pending 不可操作",
        )

    # 若提供了 edited_output，覆盖当前 output_data 并标记下游 stale
    downstream_marked: List[str] = []
    if edited_output and isinstance(edited_output, dict):
        # 保存修订前快照（便于回滚）
        await _save_step_output_revision(
            db=db,
            run_id=run_id,
            step_key=step_key,
            output_data=step.output_data or {},
            edited_by=user_id,
            change_summary="确认时编辑产物前快照",
        )
        step.output_data = edited_output
        downstream_marked = await mark_downstream_stale(
            db=db,
            run_id=run_id,
            edited_step_key=step_key,
            reason=f"上游步骤 {step_key} 在确认时被编辑",
        )

    if action == "confirm":
        # 置 confirmed，清暂停标志
        step.confirmation_status = "confirmed"
        step.confirmation_comment = comment
        run.pause_requested = False
        run.pause_reason = None
        await db.commit()

        # 推送 confirmation_updated 事件
        await pipeline_sse_manager.emit(
            run_id, "confirmation_updated", step_key, {
                "run_id": run_id,
                "step_key": step_key,
                "action": "confirm",
                "confirmation_status": "confirmed",
                "comment": comment,
                "downstream_marked_stale": downstream_marked,
            }
        )

        # 后台恢复执行
        sse_callback = pipeline_sse_manager.make_progress_callback(run.id)
        await resume_pipeline(run.id, progress_callback=sse_callback)

        logger.info(
            f"[确认] run_id={run_id} step={step_key} confirmed, "
            f"downstream_stale={downstream_marked}"
        )
    else:
        # reject：置 rejected + failed
        step.confirmation_status = "rejected"
        step.confirmation_comment = comment
        step.status = "failed"
        step.error_message = f"用户驳回: {comment or ''}"
        step.finished_at = datetime.utcnow()
        await db.commit()

        # 调 engine._skip_blocked_steps 跳过下游
        # 直接通过独立 session 触发一次引擎的 skip 流程较复杂，
        # 简化处理：手动将下游 pending 步骤标记为 skipped
        all_steps = await get_run_steps(db, run_id)
        skipped = _skip_downstream_pending(all_steps, step_key)
        for s in skipped:
            s.status = "skipped"
            s.error_message = f"上游步骤 {step_key} 被驳回"
            s.finished_at = datetime.utcnow()
        await db.commit()

        # run 转 failed
        run.status = "failed"
        run.error_message = f"步骤 {step_key} 被用户驳回"
        run.finished_at = datetime.utcnow()
        await db.commit()

        # 推送 confirmation_updated 事件
        await pipeline_sse_manager.emit(
            run_id, "confirmation_updated", step_key, {
                "run_id": run_id,
                "step_key": step_key,
                "action": "reject",
                "confirmation_status": "rejected",
                "comment": comment,
            }
        )

        logger.info(
            f"[驳回] run_id={run_id} step={step_key} rejected, "
            f"skipped_downstream={[s.step_key for s in skipped]}"
        )

    return {
        "run_id": run_id,
        "step_key": step_key,
        "action": action,
        "confirmation_status": step.confirmation_status,
        "downstream_marked_stale": downstream_marked,
    }


def _skip_downstream_pending(
    all_steps: List[PipelineStep], root_key: str
) -> List[PipelineStep]:
    """将 root_key 的所有传递性下游中状态为 pending 的步骤标记为 skipped（内存操作）。"""
    downstream = _collect_transitive_downstream(all_steps, root_key)
    return [
        s for s in all_steps
        if s.step_key in downstream and s.status == "pending"
    ]


# ---------- Task 12: 元素级重试 ----------

async def retry_step_item(
    db: AsyncSession,
    run_id: int,
    step_key: str,
    item_id: str,
    prompt_override: Optional[str] = None,
    seed: Optional[int] = None,
    user_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    重试步骤中的单个元素（如单张图片/视频）。

    - 验证步骤非 stale（stale 返回 409）
    - 从 output_data.items 找到 item_id 对应元素
    - 构建 SingleItemContext，调 executor.execute_single()
    - 更新 items[i] 和 summary
    - 推送 item_updated SSE 事件
    - 步骤已 confirmed 时响应 requires_reconfirmation=true

    Returns:
        包含 item / requires_reconfirmation 的字典
    """
    from app.services.pipeline.steps import create_step_executor
    from app.services.pipeline.steps.base import (
        StepExecutionContext,
        SingleItemContext,
    )

    run = await get_run_by_id(db, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="流水线不存在")

    if user_id is not None and run.user_id != user_id:
        raise HTTPException(status_code=403, detail="无权操作此流水线")

    step = await get_step_by_key(db, run_id, step_key)
    if not step:
        raise HTTPException(status_code=404, detail="步骤不存在")

    if step.stale:
        raise HTTPException(
            status_code=409,
            detail="步骤产物已失效（stale），请先重试整个步骤或应用下游失效",
        )

    output_data = step.output_data or {}
    items: List[Dict[str, Any]] = output_data.get("items", []) or []
    if not items:
        raise HTTPException(
            status_code=400,
            detail="步骤 output_data 中无 items 列表，无法执行元素级重试",
        )

    # 找到对应 item（按 item_id / id / index 匹配）
    target_idx = -1
    for i, it in enumerate(items):
        if not isinstance(it, dict):
            continue
        if str(it.get("item_id") or it.get("id") or it.get("index")) == str(item_id):
            target_idx = i
            break
    if target_idx < 0:
        raise HTTPException(
            status_code=404,
            detail=f"未在步骤 items 中找到 item_id={item_id}",
        )

    target_item = items[target_idx]

    # 加载模板配置用于构建执行器
    template = await get_template_by_id(db, run.template_id)
    if not template:
        raise HTTPException(status_code=500, detail="模板不存在")
    step_config = None
    for cfg in template.steps_config:
        if cfg.get("key") == step_key:
            step_config = cfg
            break
    if not step_config:
        raise HTTPException(status_code=500, detail="步骤配置不存在于模板")

    # 加载所有步骤输出，构建上下文
    all_steps = await get_run_steps(db, run_id)
    steps_output = {s.step_key: (s.output_data or {}) for s in all_steps}

    # 加载风格预设（与 engine 一致）
    style = None
    style_id = (run.inputs or {}).get("style_id")
    if style_id:
        from app.services import style_service
        style = await style_service.get_style_by_id(db, int(style_id))

    # 加载分层风格元素
    style_elements = None
    style_elements_input = (run.inputs or {}).get("style_elements") or []
    if style_elements_input:
        try:
            from app.services.style_element_service import resolve_elements
            style_elements = await resolve_elements(db, style_elements_input)
        except Exception as e:
            logger.warning(f"[元素级重试] 加载 style_elements 失败: {e}")

    # 加载剧本模板
    script_template = None
    if template.script_template_id:
        from app.services import script_template_service
        script_template = await script_template_service.get_script_template_by_id(
            db, template.script_template_id
        )

    context = StepExecutionContext(
        inputs=run.inputs or {},
        steps_output=steps_output,
        style=style,
        script_template=script_template,
        user_id=run.user_id,
        run_id=run_id,
        style_elements=style_elements,
    )

    executor = create_step_executor(step_config, context)

    single_ctx = SingleItemContext(
        step=step,
        item=target_item,
        inputs=run.inputs or {},
        steps_output=steps_output,
        prompt_override=prompt_override,
        seed=seed,
        config=step_config.get("config", {}),
    )

    try:
        result = await executor.execute_single(single_ctx)
    except NotImplementedError as e:
        raise HTTPException(
            status_code=400,
            detail=f"步骤类型 {step.step_type} 不支持元素级重试: {e}",
        )

    # 更新 items[i] 和 summary
    items[target_idx] = result.item
    output_data["items"] = items
    # 重新统计 success/failed
    success_count = sum(1 for it in items if isinstance(it, dict) and it.get("status") == "success")
    failed_count = sum(1 for it in items if isinstance(it, dict) and it.get("status") == "failed")
    output_data["success_count"] = success_count
    output_data["failed_count"] = failed_count
    # 同步更新嵌套 summary 字段（character_gen/prop_gen/scene_gen 等输出含 summary）
    summary = output_data.get("summary")
    if isinstance(summary, dict):
        summary["success_count"] = success_count
        summary["failed_count"] = failed_count
        summary["total"] = len(items)
    # 兼容字段同步更新（images / videos）
    if "images" in output_data:
        output_data["images"] = [it for it in items if isinstance(it, dict)]
    if "videos" in output_data:
        output_data["videos"] = [it for it in items if isinstance(it, dict)]

    # JSON 字段原地修改不会被 SQLAlchemy 自动检测，需用 flag_modified 标记
    from sqlalchemy.orm.attributes import flag_modified
    step.output_data = output_data
    flag_modified(step, "output_data")
    await db.commit()

    # 推送 item_updated SSE 事件
    await pipeline_sse_manager.emit(
        run_id, "item_updated", step_key, {
            "run_id": run_id,
            "step_key": step_key,
            "item_id": item_id,
            "item": result.item,
            "status": result.status,
            "success_count": success_count,
            "failed_count": failed_count,
        }
    )

    # 步骤已 confirmed 时响应 requires_reconfirmation=true
    requires_reconfirmation = (step.confirmation_status == "confirmed")
    if requires_reconfirmation:
        # 把状态重置为 pending，提示前端需要重新确认
        step.confirmation_status = "pending"
        await db.commit()

    logger.info(
        f"[元素级重试] run_id={run_id} step={step_key} item_id={item_id} "
        f"status={result.status} requires_reconfirmation={requires_reconfirmation}"
    )

    return {
        "run_id": run_id,
        "step_key": step_key,
        "item_id": item_id,
        "item": result.item,
        "status": result.status,
        "requires_reconfirmation": requires_reconfirmation,
    }


# ---------- Task 13: 产物编辑 ----------

async def edit_step_output(
    db: AsyncSession,
    run_id: int,
    step_key: str,
    items: Optional[List[Dict[str, Any]]] = None,
    remove_item_ids: Optional[List[str]] = None,
    add_items: Optional[List[Dict[str, Any]]] = None,
    user_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    编辑步骤产物（替换/删除/新增 items）。

    - 编辑前保存版本到 PipelineStepOutputRevision
    - 应用变更到 output_data.items
    - 调 mark_downstream_stale 标记下游
    - 推送 stale_marked SSE 事件（每个下游步骤一次）
    - 引擎 running 状态返回 409

    Returns:
        包含 step_key / 更新后的 items / 被标记 stale 的下游步骤的字典
    """
    run = await get_run_by_id(db, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="流水线不存在")

    if user_id is not None and run.user_id != user_id:
        raise HTTPException(status_code=403, detail="无权操作此流水线")

    if run.status == "running":
        raise HTTPException(
            status_code=409,
            detail="流水线正在运行中，不可编辑产物",
        )

    step = await get_step_by_key(db, run_id, step_key)
    if not step:
        raise HTTPException(status_code=404, detail="步骤不存在")

    output_data = dict(step.output_data or {})
    current_items: List[Dict[str, Any]] = list(output_data.get("items", []) or [])

    # 保存修订前快照
    await _save_step_output_revision(
        db=db,
        run_id=run_id,
        step_key=step_key,
        output_data=step.output_data or {},
        edited_by=user_id,
        change_summary="编辑产物前快照",
    )

    # 1. 整体替换 items
    if items is not None:
        current_items = list(items)
    else:
        # 2. 删除指定 item_id
        if remove_item_ids:
            remove_set = {str(i) for i in remove_item_ids}
            current_items = [
                it for it in current_items
                if not isinstance(it, dict)
                or str(it.get("item_id") or it.get("id") or it.get("index")) not in remove_set
            ]
        # 3. 追加新 items
        if add_items:
            for new_item in add_items:
                if isinstance(new_item, dict):
                    current_items.append(new_item)

    output_data["items"] = current_items
    # 重新统计
    success_count = sum(1 for it in current_items if isinstance(it, dict) and it.get("status") == "success")
    failed_count = sum(1 for it in current_items if isinstance(it, dict) and it.get("status") == "failed")
    output_data["success_count"] = success_count
    output_data["failed_count"] = failed_count
    # 同步更新嵌套 summary 字段（character_gen/prop_gen/scene_gen 等输出含 summary）
    summary = output_data.get("summary")
    if isinstance(summary, dict):
        summary["success_count"] = success_count
        summary["failed_count"] = failed_count
        summary["total"] = len(current_items)
    # 兼容字段同步更新
    if "images" in output_data:
        output_data["images"] = current_items
    if "videos" in output_data:
        output_data["videos"] = current_items

    # JSON 字段原地修改不会被 SQLAlchemy 自动检测，需用 flag_modified 标记
    from sqlalchemy.orm.attributes import flag_modified
    step.output_data = output_data
    flag_modified(step, "output_data")
    await db.commit()

    # 标记下游 stale
    downstream_marked = await mark_downstream_stale(
        db=db,
        run_id=run_id,
        edited_step_key=step_key,
        reason=f"步骤 {step_key} 产物被编辑",
    )

    # 推送 stale_marked 事件（每个下游一次）
    for ds_key in downstream_marked:
        await pipeline_sse_manager.emit(
            run_id, "stale_marked", ds_key, {
                "run_id": run_id,
                "step_key": ds_key,
                "reason": f"上游步骤 {step_key} 产物被编辑",
            }
        )

    logger.info(
        f"[产物编辑] run_id={run_id} step={step_key} "
        f"items_count={len(current_items)} downstream_stale={downstream_marked}"
    )

    return {
        "run_id": run_id,
        "step_key": step_key,
        "items": current_items,
        "success_count": success_count,
        "failed_count": failed_count,
        "downstream_marked_stale": downstream_marked,
    }


async def upload_step_item(
    db: AsyncSession,
    run_id: int,
    step_key: str,
    item_id: str,
    file_content: bytes,
    content_type: str,
    filename: str,
    user_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    上传图片替换步骤中某个 item 的图片。

    - 校验格式（jpg/png/webp）和大小（≤10MB）
    - 自动压缩（超过阈值时）
    - 保存修订前快照
    - 更新 item.image_url
    - 标记下游 stale
    - 推送 stale_marked SSE 事件

    Returns:
        包含 item_id / 新 image_url 的字典
    """
    import os

    run = await get_run_by_id(db, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="流水线不存在")

    if user_id is not None and run.user_id != user_id:
        raise HTTPException(status_code=403, detail="无权操作此流水线")

    if run.status == "running":
        raise HTTPException(
            status_code=409,
            detail="流水线正在运行中，不可上传产物",
        )

    # 格式校验
    allowed_types = {"image/jpeg", "image/png", "image/webp"}
    if content_type not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的图片格式：{content_type}，仅支持 jpg/png/webp",
        )

    # 大小校验（10MB）
    max_size = 10 * 1024 * 1024
    if len(file_content) > max_size:
        raise HTTPException(
            status_code=400,
            detail="图片文件过大，最大 10MB",
        )

    step = await get_step_by_key(db, run_id, step_key)
    if not step:
        raise HTTPException(status_code=404, detail="步骤不存在")

    output_data = step.output_data or {}
    items: List[Dict[str, Any]] = list(output_data.get("items", []) or [])
    target_idx = -1
    for i, it in enumerate(items):
        if not isinstance(it, dict):
            continue
        if str(it.get("item_id") or it.get("id") or it.get("index")) == str(item_id):
            target_idx = i
            break
    if target_idx < 0:
        raise HTTPException(
            status_code=404,
            detail=f"未在步骤 items 中找到 item_id={item_id}",
        )

    # 保存修订前快照
    await _save_step_output_revision(
        db=db,
        run_id=run_id,
        step_key=step_key,
        output_data=step.output_data or {},
        edited_by=user_id,
        change_summary=f"上传图片替换 item {item_id} 前快照",
    )

    # 写入文件到 uploads/pipeline_items/ 目录
    uploads_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
        "uploads", "pipeline_items",
    )
    os.makedirs(uploads_dir, exist_ok=True)
    ext_map = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
    ext = ext_map.get(content_type, ".jpg")
    saved_filename = f"run{run_id}_{step_key}_{item_id}_{int(datetime.utcnow().timestamp())}{ext}"
    saved_path = os.path.join(uploads_dir, saved_filename)

    # 简单压缩：若文件 > 2MB，用 Pillow 缩放至 80% 质量
    try:
        from PIL import Image
        import io
        img = Image.open(io.BytesIO(file_content))
        # 转为 RGB 避免 PNG alpha 通道问题
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        if len(file_content) > 2 * 1024 * 1024:
            img.save(saved_path, quality=80, optimize=True)
        else:
            img.save(saved_path, quality=95, optimize=True)
    except Exception as e:
        # Pillow 失败时直接写入原始字节
        logger.warning(f"[产物上传] Pillow 压缩失败，写入原始字节: {e}")
        with open(saved_path, "wb") as f:
            f.write(file_content)

    image_url = f"/uploads/pipeline_items/{saved_filename}"

    # 更新 item
    items[target_idx]["image_url"] = image_url
    items[target_idx]["uploaded"] = True
    items[target_idx]["uploaded_at"] = datetime.utcnow().isoformat()
    output_data["items"] = items
    if "images" in output_data:
        output_data["images"] = items
    if "videos" in output_data:
        output_data["videos"] = items
    step.output_data = output_data
    await db.commit()

    # 标记下游 stale
    downstream_marked = await mark_downstream_stale(
        db=db,
        run_id=run_id,
        edited_step_key=step_key,
        reason=f"步骤 {step_key} 的 item {item_id} 被上传图片替换",
    )
    for ds_key in downstream_marked:
        await pipeline_sse_manager.emit(
            run_id, "stale_marked", ds_key, {
                "run_id": run_id,
                "step_key": ds_key,
                "reason": f"上游步骤 {step_key} 上传了新图片",
            }
        )

    logger.info(
        f"[产物上传] run_id={run_id} step={step_key} item_id={item_id} "
        f"image_url={image_url} downstream_stale={downstream_marked}"
    )

    return {
        "run_id": run_id,
        "step_key": step_key,
        "item_id": item_id,
        "image_url": image_url,
        "downstream_marked_stale": downstream_marked,
    }


# ---------- Task 14: 下游失效应用 / 忽略 ----------

async def apply_stale(
    db: AsyncSession,
    run_id: int,
    user_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    应用下游失效：按 DAG 逆序重置 stale 步骤及其下游（status=pending,
    output_data=null, stale=False），清 pause_requested，调 engine.resume()。

    Returns:
        包含被重置的步骤 key 列表的字典
    """
    run = await get_run_by_id(db, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="流水线不存在")

    if user_id is not None and run.user_id != user_id:
        raise HTTPException(status_code=403, detail="无权操作此流水线")

    if run.status == "running":
        raise HTTPException(
            status_code=409,
            detail="流水线正在运行中，不可应用下游失效",
        )

    steps = await get_run_steps(db, run_id)
    stale_keys = {s.step_key for s in steps if s.stale}
    if not stale_keys:
        return {"run_id": run_id, "reset_steps": [], "message": "无 stale 步骤"}

    # 按 DAG 逆序找出所有 stale 步骤的下游（也包含 stale 步骤本身）
    all_to_reset = set(stale_keys)
    for k in list(stale_keys):
        all_to_reset |= _collect_transitive_downstream(steps, k)

    # 按 sort_order 逆序重置
    reset_steps: List[str] = []
    for step in sorted(steps, key=lambda s: s.sort_order, reverse=True):
        if step.step_key in all_to_reset:
            step.status = "pending"
            step.output_data = {}
            step.stale = False
            step.stale_reason = None
            step.error_message = None
            step.started_at = None
            step.finished_at = None
            step.retry_count = 0
            reset_steps.append(step.step_key)

    # 清暂停标志
    run.pause_requested = False
    run.pause_reason = None
    run.status = "pending"
    run.error_message = None
    run.finished_at = None
    await db.commit()

    # 后台恢复执行
    sse_callback = pipeline_sse_manager.make_progress_callback(run.id)
    await resume_pipeline(run.id, progress_callback=sse_callback)

    logger.info(
        f"[应用下游失效] run_id={run_id} reset_steps={reset_steps}"
    )

    return {
        "run_id": run_id,
        "reset_steps": reset_steps,
    }


async def ignore_stale(
    db: AsyncSession,
    run_id: int,
    user_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    忽略下游失效：清除所有步骤的 stale 和 stale_reason。

    Returns:
        包含被清除 stale 的步骤 key 列表的字典
    """
    run = await get_run_by_id(db, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="流水线不存在")

    if user_id is not None and run.user_id != user_id:
        raise HTTPException(status_code=403, detail="无权操作此流水线")

    if run.status == "running":
        raise HTTPException(
            status_code=409,
            detail="流水线正在运行中，不可忽略下游失效",
        )

    steps = await get_run_steps(db, run_id)
    cleared: List[str] = []
    for step in steps:
        if step.stale:
            step.stale = False
            step.stale_reason = None
            cleared.append(step.step_key)
    await db.commit()

    logger.info(
        f"[忽略下游失效] run_id={run_id} cleared_steps={cleared}"
    )

    return {
        "run_id": run_id,
        "cleared_steps": cleared,
    }


# ---------- Task 15: 编辑锁 ----------

async def acquire_edit_lock(
    db: AsyncSession,
    run_id: int,
    user_id: int,
) -> Dict[str, Any]:
    """
    获取 run 级编辑锁。5 分钟超时（惰性检查）。

    - 若锁已被其他用户持有且未过期 → 返回 409
    - 若锁已过期或为当前用户持有 → 重新获取
    """
    run = await get_run_by_id(db, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="流水线不存在")

    if run.user_id != user_id:
        raise HTTPException(status_code=403, detail="无权操作此流水线")

    now = datetime.utcnow()
    # 检查锁是否被其他用户持有且未过期
    if (
        run.edit_lock_user_id
        and run.edit_lock_user_id != user_id
        and run.edit_lock_expires_at
        and run.edit_lock_expires_at > now
    ):
        raise HTTPException(
            status_code=409,
            detail=f"流水线正被用户 {run.edit_lock_user_id} 编辑，请等待其完成",
        )

    # 获取锁
    run.edit_lock_user_id = user_id
    run.edit_lock_expires_at = now + timedelta(seconds=EDIT_LOCK_TIMEOUT_SECONDS)
    await db.commit()

    logger.info(
        f"[编辑锁] run_id={run_id} user_id={user_id} 获取锁，"
        f"过期时间={run.edit_lock_expires_at}"
    )

    return {
        "run_id": run_id,
        "locked_by": user_id,
        "expires_at": run.edit_lock_expires_at.isoformat(),
    }


async def release_edit_lock(
    db: AsyncSession,
    run_id: int,
    user_id: int,
) -> Dict[str, Any]:
    """
    释放 run 级编辑锁。

    - 仅锁持有者本人或管理员可释放
    - 锁不存在时返回 404
    """
    run = await get_run_by_id(db, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="流水线不存在")

    if run.user_id != user_id:
        raise HTTPException(status_code=403, detail="无权操作此流水线")

    if not run.edit_lock_user_id:
        return {
            "run_id": run_id,
            "message": "无编辑锁",
        }

    # 仅持有者本人可释放（管理员通过 user_id 校验已放宽）
    if run.edit_lock_user_id != user_id:
        # 检查是否过期（过期后任何人可释放）
        if run.edit_lock_expires_at and run.edit_lock_expires_at > datetime.utcnow():
            raise HTTPException(
                status_code=403,
                detail=f"无法释放其他用户持有的编辑锁: user={run.edit_lock_user_id}",
            )

    run.edit_lock_user_id = None
    run.edit_lock_expires_at = None
    await db.commit()

    logger.info(f"[编辑锁] run_id={run_id} user_id={user_id} 释放锁")

    return {
        "run_id": run_id,
        "released_by": user_id,
    }


# ---------- Task 15: 版本历史 ----------

async def list_step_revisions(
    db: AsyncSession,
    run_id: int,
    step_key: str,
    user_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """查询步骤产物的版本历史。"""
    run = await get_run_by_id(db, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="流水线不存在")

    if user_id is not None and run.user_id != user_id:
        raise HTTPException(status_code=403, detail="无权查看此流水线")

    step = await get_step_by_key(db, run_id, step_key)
    if not step:
        raise HTTPException(status_code=404, detail="步骤不存在")

    result = await db.execute(
        select(PipelineStepOutputRevision)
        .where(
            PipelineStepOutputRevision.run_id == run_id,
            PipelineStepOutputRevision.step_key == step_key,
        )
        .order_by(PipelineStepOutputRevision.revision.desc())
    )
    revisions = result.scalars().all()

    return [
        {
            "id": rev.id,
            "run_id": rev.run_id,
            "step_key": rev.step_key,
            "revision": rev.revision,
            "edited_by": rev.edited_by,
            "edited_at": rev.edited_at.isoformat() if rev.edited_at else None,
            "change_summary": rev.change_summary,
            "output_data_size": len(json.dumps(rev.output_data or {})) if rev.output_data else 0,
        }
        for rev in revisions
    ]


async def rollback_step_revision(
    db: AsyncSession,
    run_id: int,
    step_key: str,
    revision: int,
    user_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    回滚步骤产物到指定版本。

    - 用指定版本覆盖当前 output_data
    - 标记下游 stale
    - 保存回滚前版本（便于反向回滚）
    """
    run = await get_run_by_id(db, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="流水线不存在")

    if user_id is not None and run.user_id != user_id:
        raise HTTPException(status_code=403, detail="无权操作此流水线")

    if run.status == "running":
        raise HTTPException(
            status_code=409,
            detail="流水线正在运行中，不可回滚",
        )

    step = await get_step_by_key(db, run_id, step_key)
    if not step:
        raise HTTPException(status_code=404, detail="步骤不存在")

    # 查询目标版本
    result = await db.execute(
        select(PipelineStepOutputRevision).where(
            PipelineStepOutputRevision.run_id == run_id,
            PipelineStepOutputRevision.step_key == step_key,
            PipelineStepOutputRevision.revision == revision,
        )
    )
    target_rev = result.scalar_one_or_none()
    if not target_rev:
        raise HTTPException(
            status_code=404,
            detail=f"未找到 revision={revision} 的版本",
        )

    # 保存回滚前版本
    await _save_step_output_revision(
        db=db,
        run_id=run_id,
        step_key=step_key,
        output_data=step.output_data or {},
        edited_by=user_id,
        change_summary=f"回滚到 revision={revision} 前快照",
    )

    # 覆盖当前 output_data
    step.output_data = target_rev.output_data
    await db.commit()

    # 标记下游 stale
    downstream_marked = await mark_downstream_stale(
        db=db,
        run_id=run_id,
        edited_step_key=step_key,
        reason=f"步骤 {step_key} 回滚到 revision={revision}",
    )

    logger.info(
        f"[回滚] run_id={run_id} step={step_key} revision={revision} "
        f"downstream_stale={downstream_marked}"
    )

    return {
        "run_id": run_id,
        "step_key": step_key,
        "rolled_back_to": revision,
        "downstream_marked_stale": downstream_marked,
    }


# ---------- Task 16: 自动确认切换 ----------

async def set_auto_confirm(
    db: AsyncSession,
    run_id: int,
    enabled: bool,
    user_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    切换 run.auto_confirm 标志。

    开启后，后续需要确认的步骤会自动置 confirmed 跳过暂停。
    """
    run = await get_run_by_id(db, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="流水线不存在")

    if user_id is not None and run.user_id != user_id:
        raise HTTPException(status_code=403, detail="无权操作此流水线")

    run.auto_confirm = bool(enabled)
    await db.commit()

    logger.info(
        f"[自动确认] run_id={run_id} user_id={user_id} auto_confirm={enabled}"
    )

    return {
        "run_id": run_id,
        "auto_confirm": run.auto_confirm,
    }


# ---------- Task 17: 步骤级重试保留已成功元素 ----------

async def retry_step_preserve_success(
    db: AsyncSession,
    run_id: int,
    step_key: str,
    user_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    步骤级重试，保留 output_data.items 中 status=success 的元素。

    - 把 success 元素写入 output_data.preserved_items（执行器执行时跳过对应 item_id）
    - 重置步骤状态为 pending，触发 engine.resume()
    - 只对重跑的失败元素计费

    Returns:
        包含 preserved_count 的字典
    """
    run = await get_run_by_id(db, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="流水线不存在")

    if user_id is not None and run.user_id != user_id:
        raise HTTPException(status_code=403, detail="无权操作此流水线")

    if run.status == "running":
        raise HTTPException(
            status_code=400,
            detail="流水线正在运行中，请等待完成后再重试",
        )

    step = await get_step_by_key(db, run_id, step_key)
    if not step:
        raise HTTPException(status_code=404, detail="步骤不存在")

    if step.status not in ("failed", "skipped", "success"):
        raise HTTPException(
            status_code=400,
            detail=f"只能重试失败/被跳过/已完成的步骤，当前状态: {step.status}",
        )

    # 收集需要保留的 success 元素
    output_data = step.output_data or {}
    items: List[Dict[str, Any]] = output_data.get("items", []) or []
    preserved_items = [
        it for it in items
        if isinstance(it, dict) and it.get("status") == "success"
    ]

    # 写入 preserved_items 字段，执行器执行时检查并跳过
    if preserved_items:
        output_data["preserved_items"] = preserved_items
        # 从 items 中移除已保留的 success 元素，只保留待重跑的失败元素
        output_data["items"] = [
            it for it in items
            if not (isinstance(it, dict) and it.get("status") == "success")
        ]
    else:
        output_data["preserved_items"] = []
    # JSON 字段原地修改不会被 SQLAlchemy 自动检测，需用 flag_modified 标记
    from sqlalchemy.orm.attributes import flag_modified
    step.output_data = output_data
    flag_modified(step, "output_data")

    # 重置步骤状态
    step.status = "pending"
    step.error_message = None
    step.retry_count = 0
    step.started_at = None
    step.finished_at = None

    # 重置 run 状态
    run.status = "pending"
    run.error_message = None
    run.finished_at = None
    await db.commit()

    # 后台恢复执行
    sse_callback = pipeline_sse_manager.make_progress_callback(run.id)
    await resume_pipeline(run.id, progress_callback=sse_callback)

    logger.info(
        f"[步骤级重试-保留成功] run_id={run_id} step={step_key} "
        f"preserved_count={len(preserved_items)}"
    )

    return {
        "run_id": run_id,
        "step_key": step_key,
        "preserved_count": len(preserved_items),
    }
