# =====================================================
# Generation 模型 — 生成历史记录
# 所有图片/视频生成记录统一存储在此表中，通过 type 字段区分
# =====================================================

from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, JSON

from app.core.database import Base


class Generation(Base):
    """
    生成历史记录

    字段说明:
    - id: 主键
    - type: 类型（'image' 或 'video'）
    - prompt: 用户输入的提示词
    - model: 使用的模型名（如 agnes-image-2.1-flash / agnes-video-v2.0）
    - params: JSON 格式的生成参数（尺寸、帧数、帧率、分辨率等）
    - image_input: base64 图片（可选，图生图/图生视频时使用）
    - result_url: 生成结果的 URL（图片/视频）
    - status: 状态（success / failed / pending / cancelled）
    - task_id: Agnes AI 异步任务 ID（主要用于视频生成）
    - created_at: 创建时间
    """

    __tablename__ = "generations"

    id = Column(Integer, primary_key=True, index=True)
    type = Column(String(20), index=True, nullable=False)     # 'image' | 'video'
    prompt = Column(Text, nullable=False)                       # 提示词
    model = Column(String(100), nullable=True)                  # 使用的模型名
    params = Column(JSON, nullable=True)                        # JSON 参数
    image_input = Column(Text, nullable=True)                   # base64 输入图片（可选）
    result_url = Column(Text, nullable=True)                    # 生成结果 URL
    status = Column(String(20), default="success")              # 任务状态
    task_id = Column(String(200), nullable=True, index=True)    # Agnes AI 任务/视频 ID
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    def to_dict(self):
        """便捷转换为字典（用于 JSON 序列化）"""
        return {
            "id": self.id,
            "type": self.type,
            "prompt": self.prompt,
            "model": self.model,
            "params": self.params,
            "result_url": self.result_url,
            "status": self.status,
            "task_id": self.task_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
