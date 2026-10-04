# =====================================================
# 画布工作区云端落库模型
#
# - canvas_workspaces: 每工作区一行，data JSON 存 panels/connections/groups/viewport/styleConfig
#   （id 用前端生成的 uid 直作主键，本地迁移时引用零重映射）
# - canvas_snapshots: 工作区版本快照（auto=保存节流自动 / manual=手动命名 / pre_danger=危险操作前）
#   manual 与 pre_danger 不占 auto 的滚动额度
# - 冲突保护: workspaces.revision 乐观锁，PUT base_revision 不符返回 409（流程见设计文档 §6）
# =====================================================

from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, JSON, String

from app.core.database import Base

# auto 快照滚动保留上限
MAX_AUTO_SNAPSHOTS = 20
# 自动快照最小间隔（秒）：内容有变化且距上次快照超过该间隔才拍
SNAPSHOT_MIN_INTERVAL_SEC = 300


class CanvasWorkspace(Base):
    """画布工作区（每用户多工作区，云端落库主表）"""

    __tablename__ = "canvas_workspaces"

    id = Column(String(64), primary_key=True)                        # 前端 uid() 直作主键
    user_id = Column(Integer, nullable=False, index=True)
    # 存量库升级：ALTER TABLE canvas_workspaces ADD COLUMN work_id INTEGER;
    work_id = Column(Integer, nullable=True, index=True)             # 所属作品（轻容器），NULL=自由画布
    name = Column(String(255), nullable=False)
    # panels / connections / groups / viewport / styleConfig（结构与前端 CanvasWorkspace 对应字段一致）
    data = Column(JSON, nullable=False, default=dict)
    revision = Column(Integer, nullable=False, default=1)            # 乐观锁版本号，每次保存自增
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class CanvasSnapshot(Base):
    """画布工作区版本快照（还原=拉快照 data 走正常保存链路，无独立还原端点）"""

    __tablename__ = "canvas_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    workspace_id = Column(String(64), ForeignKey("canvas_workspaces.id", ondelete="CASCADE"),
                          nullable=False, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    kind = Column(String(20), nullable=False, default="auto")        # auto | manual | pre_danger
    name = Column(String(255), nullable=True)                        # 仅 manual 用
    revision = Column(Integer, nullable=False, default=1)            # 快照时的工作区版本号
    content_hash = Column(String(64), nullable=False, default="")    # data 的 sha256（节流比较）
    data = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    __table_args__ = (
        Index("ix_canvas_snapshots_ws_created", "workspace_id", "created_at"),
    )
