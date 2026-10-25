# =====================================================
# StorageObject 模型 — 用户存储台账（存储配额体系）
#
# 只增不删：资产删除不删物理文件，台账行与盘上文件一一对应；
# storage_key 唯一索引保证重复落盘路径幂等跳过。
# =====================================================

from datetime import datetime

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Integer, String

from app.core.database import Base


class StorageObject(Base):
    """用户级本地存储文件台账（用量 = SUM(bytes) per user）"""

    __tablename__ = "storage_objects"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    # uploads 相对路径（如 canvas/assets/xxx.png），幂等键；S3 件不落台账
    storage_key = Column(String(500), nullable=False, unique=True, index=True)
    bytes = Column(BigInteger, nullable=False, default=0)
    kind = Column(String(20), nullable=False, default="file")       # image / video / audio / file
    source = Column(String(30), nullable=False, default="upload")   # upload / generation / render
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
