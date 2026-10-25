# =====================================================
# 日志接口 Schema（前端错误上报）
# =====================================================


from pydantic import BaseModel, Field, field_validator

MESSAGE_MAX = 2048
STACK_MAX = 8192
URL_MAX = 2048
BATCH_MAX = 50


class FrontendLogEvent(BaseModel):
    """前端错误上报单条事件（超长字段截断而非拒绝，保证上报不丢）"""
    message: str = Field(..., min_length=1, description="错误消息")
    stack: str | None = Field(default=None, description="错误堆栈")
    level: str = Field(default="error", description="级别：error / warning")
    url: str | None = Field(default=None, description="发生页面 URL")
    timestamp: str | None = Field(default=None, description="客户端时间（ISO 字符串）")

    @field_validator("message")
    @classmethod
    def _cut_message(cls, v: str) -> str:
        return v[:MESSAGE_MAX]

    @field_validator("stack")
    @classmethod
    def _cut_stack(cls, v: str | None) -> str | None:
        return v[:STACK_MAX] if v else v

    @field_validator("url")
    @classmethod
    def _cut_url(cls, v: str | None) -> str | None:
        return v[:URL_MAX] if v else v

    @field_validator("level")
    @classmethod
    def _norm_level(cls, v: str) -> str:
        return v if v in ("error", "warning") else "error"


class FrontendLogReport(BaseModel):
    """前端错误上报请求体"""
    events: list[FrontendLogEvent] = Field(..., min_length=1, description="事件列表")
