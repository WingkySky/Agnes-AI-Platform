# =====================================================
# AgentRelay Schemas — 反向控制桥 请求/响应结构
# =====================================================

from typing import Any, Dict

from pydantic import BaseModel, Field


class RelayCallCreate(BaseModel):
    """桥中继调用：把页外工具调用下发到打开着的目标页面执行"""

    host: str = Field(..., description="目标宿主种类：canvas / editor")
    target_id: str = Field(..., min_length=1, max_length=64, description="目标 id（画布工作区 id / 剪辑工程 uid）")
    tool: str = Field(..., min_length=1, max_length=64, description="要执行的工具名（须在桥白名单内）")
    args: Dict[str, Any] = Field(default_factory=dict, description="工具参数")
