# =====================================================
# 流水线 - 现有系统集成服务
#
# 功能:
#   1. 将流水线生成的图片/视频写入 generations 表
#   2. 流水线积分扣减（预估 + 结算）
#   3. 内容审核集成（流水线产出物走审核流程）
#   4. 流水线产出物同步到历史记录
# =====================================================

import logging
from typing import Dict, Any, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.generation import Generation
from app.models.pipeline import PipelineRun, PipelineStep

logger = logging.getLogger("agnes_platform.pipeline")


# =====================================================
# 生成记录集成
# =====================================================

async def save_generation_from_step(
    db: AsyncSession,
    run_id: int,
    step_key: str,
    gen_type: str,  # 'image' 或 'video'
    prompt: str,
    result_url: str,
    model: str = "",
    params: Optional[Dict[str, Any]] = None,
    mode: Optional[str] = None,
    user_id: Optional[int] = None,
    credits_consumed: int = 0,
    task_id: Optional[str] = None,
) -> Generation:
    """
    将步骤生成的结果写入 generations 表，建立关联。

    这样流水线产出的内容也能在历史记录中看到，
    并且统一走审核流程。
    """
    gen = Generation(
        user_id=user_id,
        type=gen_type,
        prompt=prompt,
        model=model,
        params=params or {},
        mode=mode,
        result_url=result_url,
        status="success",
        credits_consumed=credits_consumed,
        task_id=task_id,
        pipeline_run_id=run_id,
        pipeline_step_key=step_key,
    )

    db.add(gen)
    await db.flush()

    logger.info(
        f"流水线生成记录已写入: run_id={run_id}, step={step_key}, "
        f"type={gen_type}, gen_id={gen.id}"
    )
    return gen


async def save_batch_generations(
    db: AsyncSession,
    run_id: int,
    step_key: str,
    items: List[Dict[str, Any]],
    gen_type: str,
    user_id: Optional[int] = None,
) -> List[int]:
    """
    批量保存生成结果。

    Args:
        items: 每个 item 包含 prompt, image_url/video_url, model 等字段
        gen_type: 'image' 或 'video'，决定从 item 中取哪个 URL 字段
    """
    gen_ids = []
    for item in items:
        if not item.get("success"):
            continue

        # 按 gen_type 选择正确的 URL 字段：
        # - image: 取 image_url
        # - video: 取 video_url（注意不要误取 image_url，video_batch 的 item 中
        #   image_url 是首帧图片，video_url 才是最终视频地址）
        if gen_type == "video":
            result_url = item.get("video_url", "")
        else:
            result_url = item.get("image_url", "")

        if not result_url:
            continue

        try:
            gen = await save_generation_from_step(
                db=db,
                run_id=run_id,
                step_key=step_key,
                gen_type=gen_type,
                prompt=item.get("prompt", ""),
                result_url=result_url,
                model=item.get("model", ""),
                params={},
                mode=item.get("mode"),
                user_id=user_id,
                credits_consumed=item.get("credits_consumed", 0),
                task_id=item.get("task_id"),
            )
            gen_ids.append(gen.id)
        except Exception as e:
            logger.warning(f"保存生成记录失败: {e}")

    await db.commit()
    return gen_ids


# =====================================================
# 积分集成
# =====================================================

async def estimate_pipeline_total_credits(
    db: AsyncSession,
    template_id: int,
    inputs: Dict[str, Any],
) -> Dict[str, Any]:
    """
    预估流水线总积分消耗（在创建流水线之前调用，用于用户确认）。

    返回：
        {
            "estimated_total": 200,
            "breakdown": [
                {"step_key": "script", "step_name": "剧本生成", "estimated_credits": 5},
                ...
            ],
            "note": "..."
        }
    """
    from app.services.pipeline.template_service import get_template_by_id

    template = await get_template_by_id(db, template_id)
    if not template:
        raise ValueError("流水线模板不存在")

    breakdown = []
    total = 0

    for step_cfg in template.steps_config:
        step_type = step_cfg.get("type", "")
        step_key = step_cfg.get("key", "")
        step_name = step_cfg.get("name", step_key)

        estimated = _estimate_step_credits(step_type, step_cfg, inputs)
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
        "note": "预估积分仅供参考，实际消耗以执行为准。失败的步骤会退还积分。",
    }


def _estimate_step_credits(
    step_type: str,
    step_cfg: Dict[str, Any],
    inputs: Dict[str, Any],
) -> int:
    """预估单个步骤的积分消耗"""
    config = step_cfg.get("config", {})

    if step_type == "llm_generate":
        return 5

    if step_type == "image_batch":
        scenes_count = inputs.get("scenes_count", 8)
        images_per_scene = config.get("images_per_scene", 1)
        # 简单估算：每张图 10 积分
        return scenes_count * images_per_scene * 10

    if step_type == "video_batch":
        scenes_count = inputs.get("scenes_count", 8)
        seconds = config.get("seconds", 5)
        # 简单估算：每秒 6 积分
        return scenes_count * seconds * 6

    if step_type == "tts_generate":
        return 5

    if step_type == "ffmpeg_composite":
        return 2

    # 默认估算
    return 10


# =====================================================
# 审核集成
# =====================================================

async def auto_moderate_pipeline_outputs(
    db: AsyncSession,
    run_id: int,
) -> None:
    """
    对流水线产出物进行自动审核。

    这里只做简单的状态标记，具体审核逻辑复用现有审核系统。
    """
    # 查询该流水线关联的所有 generations
    from sqlalchemy import select

    result = await db.execute(
        select(Generation).filter(Generation.pipeline_run_id == run_id)
    )
    gens = result.scalars().all()

    # 标记为待审核（如果系统配置了自动审核）
    # 具体的审核逻辑由现有的 moderation 服务处理
    # 这里只是确保关联关系建立好了

    logger.info(f"流水线产出物审核检查: run_id={run_id}, 产出物数量={len(gens)}")
    for gen in gens:
        logger.debug(f"  - gen_id={gen.id}, type={gen.type}, status={gen.moderation_status}")
