# =====================================================
# 步骤执行器基类
# 所有流水线步骤执行器都必须继承此基类
# =====================================================

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, TYPE_CHECKING
import logging

if TYPE_CHECKING:
    # 仅用于类型注解，避免运行时循环依赖
    from app.services.style_element_service import ResolvedStyleElement

logger = logging.getLogger("agnes_platform.pipeline")


class StepExecutionContext:
    """
    步骤执行上下文

    提供步骤执行所需的全局信息，包括：
    - 用户输入参数
    - 上游步骤的输出数据
    - 风格预设、剧本模板等辅助数据
    - 用户 ID 等运行时信息
    """

    def __init__(
        self,
        inputs: Dict[str, Any],
        steps_output: Dict[str, Dict[str, Any]],
        style: Optional[Any] = None,
        script_template: Optional[Any] = None,
        user_id: Optional[int] = None,
        run_id: Optional[int] = None,
        extra: Optional[Dict[str, Any]] = None,
        style_elements: Optional[List["ResolvedStyleElement"]] = None,
    ):
        self.inputs = inputs
        self.steps_output = steps_output
        self.style = style
        self.script_template = script_template
        self.user_id = user_id
        self.run_id = run_id
        self.extra = extra or {}
        # 分层风格元素组合（路径 B，与 style 互斥，优先级高于 style）
        self.style_elements = style_elements

    def get_step_output(self, step_key: str) -> Dict[str, Any]:
        """获取指定步骤的输出数据"""
        return self.steps_output.get(step_key, {})

    def get_input(self, key: str, default: Any = None) -> Any:
        """获取用户输入参数"""
        return self.inputs.get(key, default)


class BaseStepExecutor(ABC):
    """
    步骤执行器抽象基类

    所有具体步骤执行器（LLM 生成、图片批量生成、视频批量生成等）
    都必须继承此类并实现抽象方法。

    子类必须声明：
    - step_type: 步骤类型标识（唯一）
    """

    step_type: str = ""

    def __init__(
        self,
        step_config: Dict[str, Any],
        context: StepExecutionContext,
    ):
        """
        初始化步骤执行器

        Args:
            step_config: 步骤配置（来自模板的 steps_config 中的单步配置）
            context: 执行上下文（包含输入、上游输出、风格等）
        """
        self.config = step_config
        self.context = context
        self.step_key = step_config.get("key", "unknown")
        self.step_name = step_config.get("name", "未命名步骤")
        self.max_retries = step_config.get("max_retries", 1)
        self.timeout_sec = step_config.get("timeout", 300)

    @abstractmethod
    async def validate(self) -> None:
        """
        验证输入数据是否满足步骤执行条件。

        验证失败时应抛出异常（HTTPException 或 ValueError）。
        基类调用 execute 前会先调用此方法。
        """

    @abstractmethod
    async def execute(self) -> Dict[str, Any]:
        """
        执行步骤，返回输出数据。

        输出数据将被保存到 pipeline_steps 表的 output_data 字段中，
        并传入下游步骤的上下文中。

        Returns:
            步骤输出数据字典
        """

    @abstractmethod
    async def estimate_credits(self) -> int:
        """
        预估本步骤将消耗的积分。

        用于流水线启动前的积分预估和预扣。

        Returns:
            预估积分数
        """

    async def cleanup(self) -> None:
        """
        清理资源（可选）。
        无论步骤成功还是失败，执行完成后都会调用此方法。
        """
        pass

    async def get_progress(self) -> Dict[str, Any]:
        """
        获取当前执行进度（可选）。

        用于长时间运行的步骤实时展示进度。
        默认返回空字典，表示不支持进度查询。

        Returns:
            进度信息字典，如:
            {"current": 3, "total": 10, "percent": 0.3}
        """
        return {}
