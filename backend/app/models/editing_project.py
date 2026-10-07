# =====================================================
# 剪辑工程（独立实体）模型
#
# - editing_projects: 剪辑器 domain 主表，document JSON 存时间线（tracks/clips/subtitleStyle）
#   （融合子批次 3：剪辑器彻底独立实体，不挂靠旧 project；work_id 可空挂靠作品，一对多）
# - 冲突保护: revision 乐观锁，PUT document 带 base_revision 不符返回 409（仿画布工作区）
# - 渲染: render_document 提交时快照（编辑不干扰渲染），render_client_op_id 幂等去重，
#   render_progress 进度透出，成片 final_url 并自动入资产库
# =====================================================

from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, JSON, String, Text

from app.core.database import Base

# 渲染状态机
RENDER_IDLE = "idle"
RENDER_RENDERING = "rendering"
RENDER_SUCCEEDED = "succeeded"
RENDER_FAILED = "failed"


class EditingProject(Base):
    """剪辑工程：独立剪辑实体，时间线文档 + 乐观锁 + 渲染状态"""

    __tablename__ = "editing_projects"

    id = Column(Integer, primary_key=True, index=True)
    uid = Column(String(36), unique=True, nullable=False, index=True)   # 对外 id（/editor/:uid）
    user_id = Column(Integer, nullable=False, index=True)
    work_id = Column(Integer, nullable=True, index=True)                # 挂靠作品，NULL=自由工程
    title = Column(String(200), nullable=False)
    # 时间线文档：{ timebase, width, height, tracks[], clips[], subtitleStyle }（语义权威在前端命令表）
    document = Column(JSON, nullable=False, default=dict)
    revision = Column(Integer, nullable=False, default=1)               # 乐观锁版本号，每次保存自增
    final_url = Column(String(1024), nullable=True)                     # 最近一次渲染成片
    #   存量库升级（dev 库已执行）：
    #   ALTER TABLE editing_projects ADD COLUMN cover_url VARCHAR(1024);
    cover_url = Column(String(1024), nullable=True)                     # 工程封面（帧截图或上传图，/uploads/ 相对路径）
    render_status = Column(String(20), nullable=False, default=RENDER_IDLE)
    render_error = Column(Text, nullable=True)
    render_progress = Column(String(20), nullable=True)                 # 归一化 "3/8" 或 "composing"
    render_document = Column(JSON, nullable=True)                       # 渲染提交时快照（编辑不干扰渲染）
    render_client_op_id = Column(String(64), nullable=True)             # 幂等去重
    source_workspace_id = Column(String(64), nullable=True)             # 来源画布（送进剪辑器，成片回写用）
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
