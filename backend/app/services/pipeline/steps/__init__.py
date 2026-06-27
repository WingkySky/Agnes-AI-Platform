# =====================================================
# 步骤执行器注册表 & 工厂
# 通过注册表模式管理所有步骤执行器，支持动态注册
# =====================================================

from typing import Dict, Type, Optional
import logging

from app.services.pipeline.steps.base import BaseStepExecutor, StepExecutionContext

logger = logging.getLogger("agnes_platform.pipeline")

# 全局注册表：step_type -> Executor 类
_registry: Dict[str, Type[BaseStepExecutor]] = {}


def register_step_executor(executor_cls: Type[BaseStepExecutor]) -> Type[BaseStepExecutor]:
    """
    注册步骤执行器（装饰器模式）

    用法:
        @register_step_executor
        class LlmGenerateExecutor(BaseStepExecutor):
            step_type = "llm_generate"
            ...
    """
    step_type = executor_cls.step_type
    if not step_type:
        raise ValueError(f"步骤执行器 {executor_cls.__name__} 未声明 step_type")

    if step_type in _registry:
        logger.warning(f"步骤类型 '{step_type}' 已存在，将被 {executor_cls.__name__} 覆盖")

    _registry[step_type] = executor_cls
    logger.debug(f"已注册步骤执行器: {step_type} -> {executor_cls.__name__}")
    return executor_cls


def get_step_executor_class(step_type: str) -> Optional[Type[BaseStepExecutor]]:
    """根据步骤类型获取执行器类"""
    return _registry.get(step_type)


def create_step_executor(
    step_config: dict,
    context: StepExecutionContext,
) -> BaseStepExecutor:
    """
    工厂方法：根据步骤配置创建对应的执行器实例

    Args:
        step_config: 步骤配置字典（必须包含 type 字段）
        context: 执行上下文

    Returns:
        步骤执行器实例

    Raises:
        ValueError: 步骤类型未注册
    """
    step_type = step_config.get("type")
    if not step_type:
        raise ValueError(f"步骤配置缺少 type 字段: {step_config.get('key', 'unknown')}")

    executor_cls = get_step_executor_class(step_type)
    if not executor_cls:
        raise ValueError(
            f"未找到步骤类型 '{step_type}' 的执行器。"
            f"已注册类型: {', '.join(_registry.keys())}"
        )

    return executor_cls(step_config, context)


def list_registered_steps() -> Dict[str, str]:
    """列出所有已注册的步骤类型（用于调试和前端展示）"""
    return {key: cls.__name__ for key, cls in _registry.items()}


# ---------- 导入所有步骤执行器，触发注册 ----------
# 在这里导入所有步骤执行器模块，它们会通过装饰器自动注册
# 注意：必须在工厂函数之后导入，避免循环导入

def _import_all_executors():
    """延迟导入所有步骤执行器，触发注册"""
    # 各个步骤执行器会在模块加载时通过装饰器注册自己
    try:
        from app.services.pipeline.steps import llm_generate  # noqa: F401
    except ImportError as e:
        logger.debug(f"步骤执行器未加载（可能尚未实现）: llm_generate - {e}")

    try:
        from app.services.pipeline.steps import image_batch  # noqa: F401
    except ImportError as e:
        logger.debug(f"步骤执行器未加载（可能尚未实现）: image_batch - {e}")

    try:
        from app.services.pipeline.steps import video_batch  # noqa: F401
    except ImportError as e:
        logger.debug(f"步骤执行器未加载（可能尚未实现）: video_batch - {e}")

    try:
        from app.services.pipeline.steps import ffmpeg_composite  # noqa: F401
    except ImportError as e:
        logger.debug(f"步骤执行器未加载（可能尚未实现）: ffmpeg_composite - {e}")

    try:
        from app.services.pipeline.steps import tts_generate  # noqa: F401
    except ImportError as e:
        logger.debug(f"步骤执行器未加载（可能尚未实现）: tts_generate - {e}")


# 调用一次以触发注册（但在模块未实现时不会报错）
_import_all_executors()
