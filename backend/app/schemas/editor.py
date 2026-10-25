# =====================================================
# 剪辑工程请求/响应模型
# =====================================================

from typing import Any

from pydantic import BaseModel, Field


class EditorProjectCreate(BaseModel):
    """新建剪辑工程（document 可选：从画布送进剪辑器时携带草稿时间线）"""
    title: str = Field(..., min_length=1, max_length=200)
    work_id: int | None = None
    source_workspace_id: str | None = None
    document: dict[str, Any] | None = None
    asset_ids: list[int] | None = None   # 圈选素材：未入库的懒入库后按序排入主轨


class EditorProjectUpdate(BaseModel):
    """编辑剪辑工程元数据（仅更新提交项）"""
    title: str | None = Field(None, min_length=1, max_length=200)
    work_id: int | None = None
    cover_url: str | None = Field(None, max_length=1024, description="封面图 URL（帧截图/上传图）")


class EditorDocumentSave(BaseModel):
    """保存时间线文档（乐观锁）；snapshot_reason 仅 agent 工具层携带，触发写前快照"""
    document: dict[str, Any]
    base_revision: int = Field(..., ge=1)
    snapshot_reason: str | None = Field(None, max_length=255)


class EditorProjectBrief(BaseModel):
    id: int
    uid: str
    user_id: int
    work_id: int | None = None
    title: str
    revision: int
    final_url: str | None = None
    cover_url: str | None = None
    render_status: str
    render_error: str | None = None
    render_progress: str | None = None
    source_workspace_id: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class EditorProjectDetail(EditorProjectBrief):
    document: dict[str, Any]


class EditorProjectListResponse(BaseModel):
    total: int
    items: list[EditorProjectBrief]


class SubtitlePreviewRequest(BaseModel):
    """whisper 转写预览：指定音频轨，返回字幕片段草稿（入轨走 rebuildSubtitleClips 命令）"""
    track_id: str


class RoughCutAnalyzeRequest(BaseModel):
    """AI 粗剪分析：silence=剔除静音（输出有声段），scenes=场景切分（输出镜头段）"""
    mode: str  # 'silence' | 'scenes'
    params: dict[str, Any] = {}
