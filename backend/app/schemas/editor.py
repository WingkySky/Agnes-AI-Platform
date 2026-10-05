# =====================================================
# 剪辑工程请求/响应模型
# =====================================================

from typing import Any, Optional

from pydantic import BaseModel, Field


class EditorProjectCreate(BaseModel):
    """新建剪辑工程（document 可选：从画布送进剪辑器时携带草稿时间线）"""
    title: str = Field(..., min_length=1, max_length=200)
    work_id: Optional[int] = None
    source_workspace_id: Optional[str] = None
    document: Optional[dict[str, Any]] = None
    asset_ids: Optional[list[int]] = None   # 圈选素材：未入库的懒入库后按序排入主轨


class EditorProjectUpdate(BaseModel):
    """编辑剪辑工程元数据（仅更新提交项）"""
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    work_id: Optional[int] = None


class EditorDocumentSave(BaseModel):
    """保存时间线文档（乐观锁）"""
    document: dict[str, Any]
    base_revision: int = Field(..., ge=1)


class EditorProjectBrief(BaseModel):
    id: int
    uid: str
    user_id: int
    work_id: Optional[int] = None
    title: str
    revision: int
    final_url: Optional[str] = None
    render_status: str
    render_error: Optional[str] = None
    render_progress: Optional[str] = None
    source_workspace_id: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class EditorProjectDetail(EditorProjectBrief):
    document: dict[str, Any]


class EditorProjectListResponse(BaseModel):
    total: int
    items: list[EditorProjectBrief]


class SubtitlePreviewRequest(BaseModel):
    """whisper 转写预览：指定音频轨，返回字幕片段草稿（入轨走 rebuildSubtitleClips 命令）"""
    track_id: str
