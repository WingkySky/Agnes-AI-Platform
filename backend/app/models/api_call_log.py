# =====================================================
# ApiCallLog 模型 — 上游 API 调用记账
# 每次上游调用一行（agnes_client / aibridge 客户端出口 best-effort 写入），
# 供管理端观测调用量、延迟、错误类目分布；用户/费用归因走 generations 表。
# 存量库升级：建表由 lifespan 的 Base.metadata.create_all 自动完成，无需手工 ALTER。
# =====================================================

from datetime import datetime

from sqlalchemy import Column, Integer, String, Text, DateTime

from app.core.database import Base


class ApiCallLog(Base):
    """上游 API 调用日志（一行 = 一次客户端出口调用，重试计最终结果与累计耗时）"""

    __tablename__ = "api_call_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=True, index=True)          # 归属用户（客户端层无用户上下文时为 NULL）
    provider_id = Column(Integer, nullable=True, index=True)      # 渠道 ID
    provider_name = Column(String(100), nullable=True)            # 渠道名快照（渠道删除后仍可读）
    model = Column(String(100), nullable=True, index=True)        # 模型 ID
    call_type = Column(String(30), nullable=True, index=True)     # image_create/image_poll/video_create/video_poll/chat/prompt_optimize/other
    endpoint = Column(String(255), nullable=True)                 # 请求路径
    status = Column(String(20), nullable=True, index=True)        # success / failed
    error_category = Column(String(40), nullable=True)            # 失败类目（error_taxonomy.CATEGORIES）
    error_message = Column(Text, nullable=True)                   # 失败文案（截断）
    request_id = Column(String(100), nullable=True)               # 上游请求标识（响应头/响应体）
    latency_ms = Column(Integer, nullable=True)                   # 累计耗时（含重试）
    tokens_in = Column(Integer, nullable=True)                    # 上游 usage（仅 chat 类返回）
    tokens_out = Column(Integer, nullable=True)
    estimated_credits = Column(Integer, nullable=True)            # 本次调用对应的扣费额（创建类调用可填）
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    def to_dict(self):
        """便捷转换为字典（用于 JSON 序列化）"""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "provider_id": self.provider_id,
            "provider_name": self.provider_name,
            "model": self.model,
            "call_type": self.call_type,
            "endpoint": self.endpoint,
            "status": self.status,
            "error_category": self.error_category,
            "error_message": self.error_message,
            "request_id": self.request_id,
            "latency_ms": self.latency_ms,
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "estimated_credits": self.estimated_credits,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
