# =====================================================
# Generation 模型 — 生成历史记录
# 所有图片/视频生成记录统一存储在此表中，通过 type 字段区分
# =====================================================

from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, JSON, Boolean

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
    - is_public: 是否公开到广场（默认 False）
    - public_shared_at: 首次设为公开的时间（用于广场「最新」排序）
    - likes_count: 点赞数（反范式缓存，用于高性能排序）
    - views_count: 浏览次数（打开详情即 +1）
    """

    __tablename__ = "generations"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=True, index=True)         # 归属用户 ID（匿名任务为 NULL，登录用户为 user.id）
    type = Column(String(20), index=True, nullable=False)     # 'image' | 'video'
    prompt = Column(Text, nullable=False)                          # 提示词
    model = Column(String(100), nullable=True)                    # 使用的模型名
    params = Column(JSON, nullable=True)                           # JSON 参数
    mode = Column(String(30), nullable=True)                     # 生成模式：text2image / image2image / text2video / image2video / keyframes
    image_input = Column(Text, nullable=True)                    # base64 输入图片（可选）
    result_url = Column(Text, nullable=True)                    # 生成结果 URL
    status = Column(String(20), default="success")                  # 任务状态
    credits_consumed = Column(Integer, default=0, nullable=False)    # 本次任务消耗的积分数
    task_id = Column(String(200), nullable=True, index=True)    # Agnes AI 异步任务 ID（主要用于视频生成）
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    # ===== 广场相关字段 =====
    is_public = Column(Boolean, default=False, nullable=False, index=True)       # 是否公开到广场
    public_shared_at = Column(DateTime, nullable=True)                           # 首次设为公开的时间
    likes_count = Column(Integer, default=0, nullable=False)                     # 点赞数（反范式缓存）
    views_count = Column(Integer, default=0, nullable=False)                     # 浏览次数

    # ===== 内容审核字段 =====
    # 审核状态：approved（审核通过，正常展示）/ pending（待审核，系统自动标记）/ rejected（已屏蔽，不展示）
    moderation_status = Column(String(20), default="approved", nullable=False, index=True)
    moderation_reason = Column(String(255), nullable=True)                       # 屏蔽/待审核原因
    moderated_by = Column(Integer, nullable=True)                                # 审核人用户 ID（管理员操作时记录）
    moderated_at = Column(DateTime, nullable=True)                               # 最后审核时间
    # 自动预审命中的敏感关键词（JSON 数组，便于管理员快速查看）
    moderation_flags = Column(JSON, nullable=True)

    def to_dict(self):
        """便捷转换为字典（用于 JSON 序列化）"""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "type": self.type,
            "prompt": self.prompt,
            "model": self.model,
            "params": self.params,
            "result_url": self.result_url,
            "status": self.status,
            "credits_consumed": self.credits_consumed,
            "task_id": self.task_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "is_public": self.is_public,
            "public_shared_at": self.public_shared_at.isoformat() if self.public_shared_at else None,
            "likes_count": self.likes_count,
            "views_count": self.views_count,
            "moderation_status": self.moderation_status,
            "moderation_reason": self.moderation_reason,
            "moderation_flags": self.moderation_flags,
        }
