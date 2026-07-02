# =====================================================
# 历史视频后期处理服务
#
# 核心功能:
#   对 Generation 表中已存在的视频做二次后期处理（调色 / 剪辑），
#   无需重跑整个流水线。
#
# 设计思路:
#   复用 ColorGradeExecutor / VideoEditExecutor 执行器，构造一个
#   "虚拟步骤上下文"，把单个历史视频包装成上游步骤产出，
#   交给执行器处理。处理结果作为新的 Generation 记录入库，
#   并关联到原视频（params.source_generation_id）。
#
# 支持的操作:
#   - color_grade: 调色（4 预设 + 自定义滤镜链 + 可选音频淡入淡出）
#   - video_edit:  剪辑（trim/cut 多段拼接 + 30ms 音频淡入淡出）
# =====================================================

import logging
import os
import uuid
from typing import Dict, Any, Optional, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.generation import Generation
from app.services.pipeline.steps.base import StepExecutionContext
from app.services.pipeline.steps.color_grade import ColorGradeExecutor
from app.services.pipeline.steps.video_edit import VideoEditExecutor

logger = logging.getLogger("agnes_platform.pipeline")


async def post_process_video(
    db: AsyncSession,
    generation_id: int,
    operation: str,
    config: Dict[str, Any],
    user_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    对单个历史视频执行后期处理

    Args:
        db: 数据库会话
        generation_id: 源视频的 Generation ID
        operation: 操作类型 ('color_grade' | 'video_edit')
        config: 操作配置
            - color_grade: {preset, with_audio_fade}
            - video_edit:  {operations: [{type, start, end}, ...]}
        user_id: 操作者用户 ID

    Returns:
        {
            "success": True,
            "source_generation_id": 123,
            "new_generation_id": 124,
            "result_url": "/api/pipeline/outputs/graded_xxx.mp4",
            "operation": "color_grade",
            "credits_consumed": 1
        }

    Raises:
        ValueError: 参数错误或源视频不存在
        RuntimeError: 处理失败
    """
    # 1. 加载源视频记录
    result = await db.execute(
        select(Generation).filter(Generation.id == generation_id)
    )
    source_gen = result.scalar_one_or_none()
    if not source_gen:
        raise ValueError(f"源视频记录不存在: generation_id={generation_id}")

    if source_gen.type != "video":
        raise ValueError(f"仅支持视频后期处理，当前类型: {source_gen.type}")

    source_url = source_gen.result_url
    if not source_url:
        raise ValueError("源视频没有 result_url")

    logger.info(
        f"[后期处理] 开始: gen_id={generation_id}, operation={operation}, "
        f"source_url={source_url}"
    )

    # 2. 构造虚拟步骤配置和上下文
    #    把单个历史视频包装成"上游步骤产出"，让执行器按正常流程处理
    virtual_step_key = "_source_video"
    step_config = _build_step_config(operation, config, virtual_step_key)

    # 虚拟上下文：上游步骤产出只含一个视频
    virtual_context = StepExecutionContext(
        inputs={},
        steps_output={
            virtual_step_key: {
                "videos": [
                    {
                        "index": 0,
                        "video_url": source_url,
                        "success": True,
                    }
                ]
            }
        },
        user_id=user_id or source_gen.user_id,
        run_id=None,  # 后期处理不属于任何 PipelineRun
        extra={
            "post_process": True,
            "source_generation_id": generation_id,
        },
    )

    # 3. 选择并执行对应的执行器
    if operation == "color_grade":
        executor = ColorGradeExecutor(step_config, virtual_context)
    elif operation == "video_edit":
        executor = VideoEditExecutor(step_config, virtual_context)
    else:
        raise ValueError(f"不支持的操作类型: {operation}（可选: color_grade / video_edit）")

    # 4. 校验并执行
    await executor.validate()
    output = await executor.execute()

    # 5. 提取结果
    videos: List[Dict[str, Any]] = output.get("videos", [])
    success_count = output.get("success_count", 0)
    if success_count == 0 or not videos:
        errors = [v.get("error", "未知错误") for v in videos if not v.get("success")]
        raise RuntimeError(f"后期处理失败: {errors}")

    # 取第一个成功的结果（历史视频后期处理只处理单个视频）
    result_video = next((v for v in videos if v.get("success")), None)
    if not result_video:
        raise RuntimeError("后期处理无成功结果")

    result_url = result_video.get("video_url", "")
    credits_consumed = await executor.estimate_credits()

    # 6. 创建新的 Generation 记录，关联到源视频
    new_gen = Generation(
        user_id=user_id or source_gen.user_id,
        type="video",
        prompt=source_gen.prompt or "",
        model=f"post_process:{operation}",
        params={
            "operation": operation,
            "config": config,
            "source_generation_id": generation_id,
            "source_url": source_url,
        },
        result_url=result_url,
        status="success",
        credits_consumed=credits_consumed,
        # 后期处理产物默认不公开，需用户手动分享
        is_public=False,
        moderation_status="approved",  # 后期处理不改变内容审核状态，继承源视频的合规性
    )
    db.add(new_gen)
    await db.commit()
    await db.refresh(new_gen)

    logger.info(
        f"[后期处理] 完成: gen_id={generation_id} → new_gen_id={new_gen.id}, "
        f"operation={operation}, url={result_url}"
    )

    return {
        "success": True,
        "source_generation_id": generation_id,
        "new_generation_id": new_gen.id,
        "result_url": result_url,
        "operation": operation,
        "credits_consumed": credits_consumed,
    }


def _build_step_config(
    operation: str,
    config: Dict[str, Any],
    virtual_step_key: str,
) -> Dict[str, Any]:
    """
    构造虚拟步骤配置

    把后期处理请求包装成执行器能识别的 steps_config 单步配置格式：
    {
        "key": "post_process",
        "name": "后期处理-调色/剪辑",
        "type": "color_grade" | "video_edit",
        "config": {
            "from_step": "_source_video",
            ...用户传入的配置
        }
    }
    """
    return {
        "key": "post_process",
        "name": f"后期处理-{operation}",
        "type": operation,
        "config": {
            "from_step": virtual_step_key,
            **config,
        },
    }
