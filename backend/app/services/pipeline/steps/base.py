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
    from app.models.pipeline import PipelineStep

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


class SingleItemContext:
    """
    单元素执行上下文

    用于元素级重生成（retry single item）场景，仅承载单个元素的相关数据：
    - step: 当前步骤的 PipelineStep 记录实例
    - item: 单个元素的当前数据（含 id, name, setting_text/description, image_url, seed 等）
    - inputs: run 级输入
    - steps_output: 上游步骤输出
    - prompt_override: 用户修改后的 prompt（用于重生）
    - seed: 用户指定的种子
    - config: 步骤配置
    """

    def __init__(
        self,
        step: "PipelineStep",
        item: Dict[str, Any],
        inputs: Dict[str, Any],
        steps_output: Dict[str, Dict[str, Any]],
        prompt_override: Optional[str] = None,
        seed: Optional[int] = None,
        config: Optional[Dict[str, Any]] = None,
    ):
        self.step = step
        self.item = item
        self.inputs = inputs
        self.steps_output = steps_output
        # 用户修改后的 prompt（用于重生），未修改时为 None
        self.prompt_override = prompt_override
        # 用户指定的种子，未指定时为 None
        self.seed = seed
        # 步骤配置（来自模板的 steps_config 中的单步配置）
        self.config = config or {}


class ItemResult:
    """
    单元素执行结果

    用于元素级重生成返回值，承载单个元素执行后的状态与产物：
    - status: 执行状态，"success" / "failed"
    - item: 更新后的元素数据（含新的 image_url, seed, error 等）
    - error: 失败原因（成功时为 None）
    - credits_consumed: 本次消耗积分
    """

    def __init__(
        self,
        status: str,
        item: Dict[str, Any],
        error: Optional[str] = None,
        credits_consumed: int = 0,
    ):
        self.status = status
        self.item = item
        self.error = error
        self.credits_consumed = credits_consumed


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

    # ---------- Task 17: 步骤级重试保留已成功元素 ----------
    def get_preserved_items(self) -> List[Dict[str, Any]]:
        """
        获取本次执行需要保留的已成功元素列表。

        由 engine._execute_step 在步骤级重试时通过 context.extra["preserved_items"]
        注入（来自 retry_step_preserve_success 服务函数写入 step.output_data.preserved_items）。
        执行器在构建任务时应跳过这些元素对应的 item_id / index，
        只对剩余的失败元素重新执行，避免重复计费。

        Returns:
            保留元素列表（每个元素是 dict，含 item_id / id / index 等标识字段）
        """
        preserved = self.context.extra.get("preserved_items") if self.context and self.context.extra else None
        if not preserved or not isinstance(preserved, list):
            return []
        return [p for p in preserved if isinstance(p, dict)]

    def get_preserved_item_ids(self) -> set:
        """
        获取保留元素的标识集合（item_id / id / index 字符串形式）。

        用于执行器在 _build_*_tasks() 中快速过滤掉需要跳过的任务。
        """
        ids: set = set()
        for item in self.get_preserved_items():
            for key in ("item_id", "id", "index"):
                val = item.get(key)
                if val is not None:
                    ids.add(str(val))
        return ids

    async def execute_single(self, ctx: SingleItemContext) -> ItemResult:
        """
        执行单个元素的重生成（可选）。

        用于元素级重试场景：用户针对某个失败/不满意的元素单独重生。
        默认抛 NotImplementedError，需要支持元素级重试的执行器覆盖此方法。

        Args:
            ctx: 单元素执行上下文

        Returns:
            ItemResult: 单元素执行结果
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} does not support execute_single"
        )

    @staticmethod
    def get_failed_items(output_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        从步骤输出数据中提取失败元素列表。

        用于在元素级重试时快速筛选出 status == "failed" 的元素。

        Args:
            output_data: 步骤输出数据字典，应包含 "items" 列表

        Returns:
            失败元素列表；若 output_data 为空或无 items 字段则返回空列表
        """
        if not output_data or "items" not in output_data:
            return []
        return [
            item for item in output_data["items"]
            if item.get("status") == "failed"
        ]
