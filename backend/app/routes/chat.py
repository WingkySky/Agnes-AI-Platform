# =====================================================
# 聊天路由（全异步 + SSE 流式响应）
#
# POST   /api/chat/sessions              - 创建新会话
# GET    /api/chat/sessions              - 获取会话列表
# GET    /api/chat/sessions/{id}         - 获取会话详情（含消息）
# DELETE /api/chat/sessions/{id}         - 删除会话
# POST   /api/chat/sessions/{id}/messages - 发送消息（SSE 流式响应）
# GET    /api/chat/sessions/{id}/messages - 获取会话消息列表
# POST   /api/chat/media-callback        - 媒体生成完成回调（更新消息中的 media_items）
# GET    /api/chat/media-status/{task_id} - 查询媒体生成状态
#
# 关键设计：
#   - 发送消息使用 SSE（Server-Sent Events）流式返回 AI 回复
#   - 工具调用（生图/生视频）结果通过 SSE 事件实时推送
#   - 消息持久化到数据库，刷新页面后可恢复历史
#   - 媒体项使用 media_items JSON 数组，支持多图/多视频
#   - 媒体生成完成后，前端通过回调接口更新消息的 media_items
# =====================================================

import logging
from datetime import datetime
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import desc, func

from app.core.database import get_async_db, async_session
from app.core.config import settings
from app.core.security import get_current_user_optional
from app.models.chat import ChatSession, ChatMessage
from app.models.user import User
from app.services.chat_service import chat_service
from app.services.agnes_client import agnes_client
from app.services.image_poller import image_poller_manager
from app.services.video_poller import poller_manager as video_poller_manager

logger = logging.getLogger("agnes_platform")
router = APIRouter()


# =====================================================
# 公共依赖
# =====================================================

def _ownership_filter(current_user: Optional[User]):
    """会话归属过滤条件：登录用户只看自己的会话，未登录用户只看匿名会话。"""
    if current_user:
        return ChatSession.user_id == current_user.id
    return ChatSession.user_id.is_(None)


async def get_owned_session(
    session_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
) -> ChatSession:
    """会话归属校验依赖：登录用户匹配 user_id，匿名匹配 user_id IS NULL，否则 404。"""
    stmt = select(ChatSession).filter(
        ChatSession.id == session_id,
        _ownership_filter(current_user),
    )
    result = await db.execute(stmt)
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    return session


async def require_agnes_api_key() -> None:
    """API Key 检查（从 agnes_client 读取当前配置，Provider 可能在前端配置页修改）"""
    if not agnes_client.api_key or agnes_client.api_key.startswith("sk-your"):
        raise HTTPException(
            status_code=401,
            detail="Agnes AI API Key 未配置，请在前端「配置管理」页面添加 Provider",
        )


# =====================================================
# 请求/响应 Schema
# =====================================================

class CreateSessionRequest(BaseModel):
    """创建会话请求"""
    title: Optional[str] = Field(default=None, description="会话标题（可选，默认取首条消息前 30 字）")


class UpdateSessionRequest(BaseModel):
    """修改会话标题请求"""
    title: str = Field(..., min_length=1, max_length=200, description="新的会话标题")


class SendMessageRequest(BaseModel):
    """发送消息请求
    - content: 消息文本（可为空字符串，此时以附件为主）
    - attachments: 可选的参考图列表（单张 ≤ 5MB，总数 ≤ 10）
    - camera_params: 可选的摄像机参数，前端 camera store 当前值
    - preset_ref: 可选，用户选择的预设 ID（仅当前轮有效）
    """
    content: str = Field(default="", description="消息内容（可为空字符串）")
    attachments: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="参考图列表，每项: {name, base64_image, size, mime_type"
    )
    camera_params: Optional[Dict[str, Any]] = Field(
        default=None,
        description="摄像机参数，含 enabled(bool) 及各摄像参数字段"
    )
    preset_ref: Optional[int] = Field(
        default=None,
        description="用户选择的预设 ID（仅当前轮有效）"
    )


class MediaCallbackRequest(BaseModel):
    """媒体生成完成回调请求"""
    message_id: int = Field(..., description="消息 ID")
    task_id: str = Field(..., description="生成任务 ID")
    media_url: str = Field(..., description="生成完成的资源 URL")
    status: str = Field(default="success", description="状态：success / failed")


# =====================================================
# 会话管理接口
# =====================================================

@router.post("/chat/sessions", summary="创建新聊天会话")
async def create_session(
    req: CreateSessionRequest = None,
    db: AsyncSession = Depends(get_async_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """创建一个新的聊天会话（登录用户的会话会绑定 user_id）"""
    session = ChatSession(
        title=req.title if req and req.title else "新对话",
        user_id=current_user.id if current_user else None,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    logger.info("[Chat] 创建会话: id=%s, title=%s, user_id=%s", session.id, session.title, session.user_id)
    return session.to_dict()


@router.get("/chat/sessions", summary="获取会话列表")
async def list_sessions(
    page: int = 1,
    page_size: int = 20,
    db: AsyncSession = Depends(get_async_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """获取会话列表（按用户隔离）：未登录用户只能看到未绑定任何用户的匿名会话"""
    # 构造过滤条件：登录用户只看自己；未登录用户看 user_id 为 NULL 的记录
    owned = _ownership_filter(current_user)
    stmt = select(ChatSession).filter(owned)
    count_stmt = select(func.count()).select_from(ChatSession).filter(owned)

    # 总数
    count_result = await db.execute(count_stmt)
    total = count_result.scalar_one() or 0

    # 分页查询
    stmt = (
        stmt
        .order_by(desc(ChatSession.updated_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(stmt)
    sessions = result.scalars().all()

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [s.to_dict() for s in sessions],
    }


@router.get("/chat/sessions/{session_id}", summary="获取会话详情（含消息）")
async def get_session(
    session: ChatSession = Depends(get_owned_session),
):
    """获取会话详情，包含所有消息（按用户隔离）"""
    return session.to_dict(include_messages=True)


@router.put("/chat/sessions/{session_id}", summary="修改会话标题")
async def update_session(
    req: UpdateSessionRequest,
    session: ChatSession = Depends(get_owned_session),
    db: AsyncSession = Depends(get_async_db),
):
    """修改会话的标题（按用户隔离）"""
    session.title = req.title[:200]
    session.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(session)
    logger.info("[Chat] 修改会话标题: id=%s, title=%s", session.id, session.title)
    return session.to_dict()


@router.post("/chat/sessions/{session_id}/summarize", summary="AI 自动总结会话主题")
async def summarize_session(
    session: ChatSession = Depends(get_owned_session),
    db: AsyncSession = Depends(get_async_db),
):
    """使用 AI 分析对话内容，自动生成一个有意义的会话标题（按用户隔离）"""
    # 获取会话的前几条消息（用于总结主题）
    result = await db.execute(
        select(ChatMessage)
        .filter(ChatMessage.session_id == session.id)
        .order_by(ChatMessage.id)
        .limit(10)
    )
    messages = result.scalars().all()

    if not messages:
        raise HTTPException(status_code=400, detail="会话没有消息，无法总结主题")

    # 调用 AI 服务生成标题
    try:
        summary_title = await chat_service.summarize_session_title(messages)
    except Exception as e:
        logger.warning("[Chat] AI 总结标题失败，使用降级方案: %s", e)
        first_user_msg = next((m for m in messages if m.role == "user"), None)
        summary_title = (first_user_msg.content[:30] + "..." if first_user_msg and first_user_msg.content and len(first_user_msg.content) > 30
                         else (first_user_msg.content if first_user_msg else "新对话"))

    # 更新会话标题
    session.title = summary_title[:200]
    session.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(session)
    logger.info("[Chat] 自动总结会话标题: id=%s, title=%s", session.id, session.title)
    return session.to_dict()


@router.delete("/chat/sessions/{session_id}", summary="删除会话")
async def delete_session(
    session: ChatSession = Depends(get_owned_session),
    db: AsyncSession = Depends(get_async_db),
):
    """删除会话及其所有消息（按用户隔离）"""
    await db.delete(session)
    await db.commit()
    logger.info("[Chat] 删除会话: id=%s", session.id)
    return {"success": True, "message": f"会话 {session.id} 已删除"}


# =====================================================
# 消息接口
# =====================================================

@router.get("/chat/sessions/{session_id}/messages", summary="获取会话消息列表")
async def get_messages(
    session: ChatSession = Depends(get_owned_session),
    db: AsyncSession = Depends(get_async_db),
):
    """获取指定会话的所有消息（按用户隔离）"""
    # 查询消息
    result = await db.execute(
        select(ChatMessage)
        .filter(ChatMessage.session_id == session.id)
        .order_by(ChatMessage.id)
    )
    messages = result.scalars().all()

    await chat_service.refresh_message_media_items(messages, db)

    return {"items": [m.to_dict() for m in messages]}


@router.post("/chat/sessions/{session_id}/messages", summary="发送消息（SSE 流式响应）")
async def send_message(
    req: SendMessageRequest,
    _api_key: None = Depends(require_agnes_api_key),
    session: ChatSession = Depends(get_owned_session),
    db: AsyncSession = Depends(get_async_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """
    发送消息并获取 AI 流式回复（SSE，按用户隔离）。

    SSE 事件格式（每行以 "data: " 开头）：
    - {"type": "user_message", "message": {...}} — 用户消息已保存
    - {"type": "text", "content": "..."} — AI 文本增量
    - {"type": "tool_call", "tool": "generate_image", "args": {...}} — 工具调用
    - {"type": "tool_result", "tool": "generate_image", "result": {...}} — 工具结果
    - {"type": "assistant_message", "message": {...}} — AI 消息已保存
    - {"type": "done"} — 结束
    """
    # 附件校验与清洗（大小/数量/格式，非法格式跳过并告警）
    validated_attachments = chat_service.validate_attachments(req.attachments)

    # 允许 content 为空但有附件（用户可以"只甩一张图说画图"）
    if not req.content.strip() and not validated_attachments:
        raise HTTPException(status_code=400, detail="消息内容不能为空")

    return StreamingResponse(
        await chat_service.stream_reply(
            db,
            session,
            content=req.content,
            attachments=validated_attachments,
            user_id=current_user.id if current_user else None,
            camera_params=req.camera_params,
            preset_ref=req.preset_ref,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# =====================================================
# 媒体回调接口 — 前端轮询到结果后调用此接口更新消息
# =====================================================

@router.post("/chat/media-callback", summary="媒体生成完成回调")
async def media_callback(
    req: MediaCallbackRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """
    前端检测到媒体生成完成后，调用此接口更新消息中的 media_items。
    这样刷新页面后也能看到已生成的媒体资源。
    """
    result = await db.execute(
        select(ChatMessage).filter(ChatMessage.id == req.message_id)
    )
    msg = result.scalar_one_or_none()
    if not msg:
        raise HTTPException(status_code=404, detail="消息不存在")

    # 鉴权：消息所属会话须属于当前登录用户（匿名用户仅可回调匿名会话的消息）
    session_result = await db.execute(
        select(ChatSession.user_id).filter(ChatSession.id == msg.session_id)
    )
    owner_id = session_result.scalar_one_or_none()
    if (current_user.id if current_user else None) != owner_id:
        raise HTTPException(status_code=403, detail="无权操作此消息")

    # 更新 media_items 中对应 task_id 的项
    if msg.media_items:
        updated = False
        for item in msg.media_items:
            if item.get("task_id") == req.task_id:
                item["url"] = req.media_url
                item["status"] = req.status
                updated = True
                break

        if updated:
            # 触发 SQLAlchemy 检测 JSON 字段变更
            msg.media_items = list(msg.media_items)
            await db.commit()
            logger.info("[Chat] 媒体回调更新: message_id=%s, task_id=%s, status=%s",
                        req.message_id, req.task_id, req.status)
            return {"success": True, "message": "媒体状态已更新"}

    return {"success": False, "message": "未找到对应的媒体项"}


# =====================================================
# 媒体生成状态查询
# =====================================================

@router.get("/chat/media-status/{task_id}", summary="查询媒体生成状态")
async def get_media_status(task_id: str):
    """
    查询图片/视频生成任务的状态。
    前端轮询此接口获取生成进度和结果 URL。
    """
    # 先尝试图片任务
    image_task = await image_poller_manager.get_status(task_id)
    if image_task:
        return image_task.to_dict()

    # 再尝试视频任务
    video_task = await video_poller_manager.get_status(task_id=task_id)
    if not video_task:
        video_task = await video_poller_manager.get_status(video_id=task_id)
    if video_task:
        return video_task.to_dict()

    # 最后查数据库
    try:
        async with async_session() as db:
            from app.models.generation import Generation
            result = await db.execute(
                select(Generation).filter(Generation.task_id == task_id)
            )
            record = result.scalar_one_or_none()
            if record:
                return {
                    "task_id": task_id,
                    "status": record.status,
                    "result_url": record.result_url,
                    "type": record.type,
                }
    except Exception as e:
        logger.warning("[Chat] 数据库查询媒体状态失败: %s", e)

    # 任务不在内存中也不在数据库中，返回 unknown 状态而非 404
    # 前端收到 unknown 后会停止轮询，避免无限 404 循环
    return {
        "task_id": task_id,
        "status": "unknown",
        "message": "任务已过期或不存在，请停止轮询",
    }
