# =====================================================
# CanvasWorkspace Schemas — 画布工作区云端落库 请求/响应结构
# =====================================================

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class WorkspaceCreate(BaseModel):
    """创建画布工作区（迁移场景可透传前端 uid 作 id，重复创建幂等返回已有）"""
    id: Optional[str] = Field(None, max_length=64, description="工作区 id（不传则后端生成）")
    name: str = Field(..., max_length=255, description="工作区名称")
    data: Dict[str, Any] = Field(default_factory=dict, description="panels/connections/groups/viewport/styleConfig")


class WorkspaceSave(BaseModel):
    """保存画布工作区（乐观锁：base_revision 不符返回 409）"""
    data: Dict[str, Any] = Field(..., description="完整工作区数据")
    base_revision: int = Field(..., ge=0, description="客户端持有的版本号")
    name: Optional[str] = Field(None, max_length=255, description="可选同步改名")


class WorkspaceBrief(BaseModel):
    """工作区列表项（不含 data）"""
    id: str
    name: str
    revision: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class WorkspaceDetail(WorkspaceBrief):
    """工作区全量（含 data 与 revision）"""
    data: Dict[str, Any] = Field(default_factory=dict)


class WorkspaceSaveResponse(BaseModel):
    """保存响应：服务端最新版本号"""
    revision: int


class ConflictResponse(BaseModel):
    """409 冲突响应体"""
    current_revision: int


class SnapshotCreate(BaseModel):
    """创建快照（auto 由保存链路内嵌生成，此端点仅接受 manual/pre_danger）"""
    kind: str = Field("manual", description="manual=手动命名 / pre_danger=危险操作前")
    name: Optional[str] = Field(None, max_length=255, description="手动版本名")


class SnapshotBrief(BaseModel):
    """快照列表项（不含 data）"""
    id: int
    kind: str
    name: Optional[str] = None
    revision: int
    created_at: datetime

    class Config:
        from_attributes = True


class SnapshotDetail(SnapshotBrief):
    """快照全量"""
    data: Dict[str, Any] = Field(default_factory=dict)


class SnapshotListResponse(BaseModel):
    """快照列表响应"""
    items: List[SnapshotBrief]
