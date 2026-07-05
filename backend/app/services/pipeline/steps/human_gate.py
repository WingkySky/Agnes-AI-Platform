# =====================================================
# 人工确认（Human Gate）步骤执行器
# 用于流水线中需要人工决策/确认的关卡步骤
# =====================================================

import logging
from typing import Any, Dict

from app.services.pipeline.steps import register_step_executor
from app.services.pipeline.steps.base import BaseStepExecutor

logger = logging.getLogger("agnes_platform.pipeline")


@register_step_executor
class HumanGateExecutor(BaseStepExecutor):
    """
    人工确认步骤执行器

    用于流水线中需要用户进行人工确认/决策的关卡步骤。
    实际确认逻辑由引擎层（engine.py）处理：检测到 step_type=human_gate 时
    直接置 status=success（无产物）并触发确认流程，不会调用 execute()。
    本执行器仅用于满足 BaseStepExecutor 接口契约与配置校验。
    """

    step_type = "human_gate"

    async def validate(self) -> None:
        """验证 human_gate 配置"""
        config = self.config.get("config", {})

        # options 可选：若提供必须是 list 且每项包含 value/label
        options = config.get("options")
        if options is None:
            return

        if not isinstance(options, list):
            raise ValueError("human_gate 的 options 必须为列表")

        for idx, opt in enumerate(options):
            if not isinstance(opt, dict):
                raise ValueError(f"human_gate 的 options[{idx}] 必须为字典")
            if "value" not in opt or "label" not in opt:
                raise ValueError(
                    f"human_gate 的 options[{idx}] 必须包含 value 和 label 字段"
                )

    async def execute(self) -> Dict[str, Any]:
        """
        执行 human_gate 步骤

        注意：实际确认逻辑由引擎层处理，此方法仅满足接口契约，
        引擎层不会调用此方法。返回占位的空成功结果，包含 options 供前端展示可选项。
        """
        config = self.config.get("config", {})
        options = config.get("options", [])

        # 占位结果：decision/comment 由后续确认流程回填
        return {
            "decision": None,
            "comment": None,
            "options": options,
        }

    async def estimate_credits(self) -> int:
        """预估积分消耗（人工确认步骤不消耗积分）"""
        return 0
