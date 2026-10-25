# =====================================================
# 聊天路由（全异步）
#
# POST   /api/chat/sessions              - 创建新会话
# GET    /api/chat/sessions              - 获取会话列表
# GET    /api/chat/sessions/{id}         - 获取会话详情（含消息）
# DELETE /api/chat/sessions/{id}         - 删除会话
# GET    /api/chat/sessions/{id}/messages - 获取会话消息列表
# POST   /api/chat/media-callback        - 媒体生成完成回调（更新消息中的 media_items）
# GET    /api/chat/media-status/{task_id} - 查询媒体生成状态
# POST   /api/chat/agent-sessions        - 创建画布 Agent 会话（type=canvas）
# PUT    /api/chat/agent-sessions/{id}   - 全量同步画布会话（context + 消息行）
# GET    /api/chat/agent-sessions/{id}   - 读取画布会话（context + 消息，恢复单请求）
# POST   /api/chat/completions           - LLM 流式透传（前端内核/管线/节点对话共用）
#
# 关键设计：
#   - LLM 编排全部住前端（pi 内核/透传通道），旧服务端编排端点已退役
#   - 消息持久化到数据库，刷新页面后可恢复历史
#   - 媒体项使用 media_items JSON 数组，支持多图/多视频
#   - 媒体生成完成后，前端通过回调接口更新消息的 media_items
# =====================================================

import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete, desc, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.database import async_session, get_async_db
from app.core.response import ok
from app.core.security import get_current_user_optional
from app.models.chat import ChatMessage, ChatSession
from app.models.user import User
from app.services.agnes_client import agnes_client
from app.services.chat_service import chat_service
from app.services.image_poller import image_poller_manager
from app.services.video_poller import poller_manager as video_poller_manager

logger = logging.getLogger("agnes_platform")
router = APIRouter()


# =====================================================
# 公共依赖
# =====================================================

def _ownership_filter(current_user: User | None):
    """会话归属过滤条件：登录用户只看自己的会话，未登录用户只看匿名会话。"""
    if current_user:
        return ChatSession.user_id == current_user.id
    return ChatSession.user_id.is_(None)


async def get_owned_session(
    session_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User | None = Depends(get_current_user_optional),
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
    title: str | None = Field(default=None, description="会话标题（可选，默认取首条消息前 30 字）")
    workspace_id: str | None = Field(default=None, max_length=64, description="画布工作区 id（可选，画布面板创建时标记上下文）")


class UpdateSessionRequest(BaseModel):
    """修改会话标题请求"""
    title: str = Field(..., min_length=1, max_length=200, description="新的会话标题")


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
    current_user: User | None = Depends(get_current_user_optional),
):
    """创建一个新的聊天会话（登录用户的会话会绑定 user_id）"""
    session = ChatSession(
        title=req.title if req and req.title else "新对话",
        user_id=current_user.id if current_user else None,
        workspace_id=req.workspace_id if req else None,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    logger.info("[Chat] 创建会话: id=%s, title=%s, user_id=%s", session.id, session.title, session.user_id)
    return ok(data=session.to_dict())


@router.get("/chat/sessions", summary="获取会话列表")
async def list_sessions(
    page: int = 1,
    page_size: int = 20,
    db: AsyncSession = Depends(get_async_db),
    current_user: User | None = Depends(get_current_user_optional),
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

    return ok(data={
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [s.to_dict() for s in sessions],
    })


@router.get("/chat/sessions/{session_id}", summary="获取会话详情（含消息）")
async def get_session(
    session: ChatSession = Depends(get_owned_session),
):
    """获取会话详情，包含所有消息（按用户隔离）"""
    return ok(data=session.to_dict(include_messages=True))


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
    return ok(data=session.to_dict())


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
    return ok(data=session.to_dict())


@router.delete("/chat/sessions/{session_id}", summary="删除会话")
async def delete_session(
    session: ChatSession = Depends(get_owned_session),
    db: AsyncSession = Depends(get_async_db),
):
    """删除会话及其所有消息（按用户隔离）"""
    await db.delete(session)
    await db.commit()
    logger.info("[Chat] 删除会话: id=%s", session.id)
    return ok(message=f"会话 {session.id} 已删除")


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

    return ok(data={"items": [m.to_dict() for m in messages]})


# =====================================================
# 画布 Agent 会话同步（前端内核驱动，全量覆盖式）
# context 列 = 内核 serializeState 原样（恢复唯一可信源）；
# 消息行只服务全局列表预览与 AI 总结标题，不做行→上下文反向重建
# =====================================================

class AgentSessionMessageIn(BaseModel):
    role: str = Field(..., description="user / assistant")
    content: str = Field(default="")
    attachments: list[dict[str, Any]] | None = Field(default=None, description="输入附件（图片 base64_image 等）")
    steps: list[dict[str, Any]] | None = Field(default=None, description="工具步骤时间线")
    media_items: list[dict[str, Any]] | None = Field(default=None, description="生成产物（type/url/task_id/status），刷新后回读展示")


class AgentSessionCreateRequest(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    workspace_id: str | None = Field(default=None, max_length=64)


class AgentSessionSyncRequest(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    workspace_id: str | None = Field(default=None, max_length=64)
    context: dict[str, Any] | None = Field(default=None, description="内核序列化状态")
    messages: list[AgentSessionMessageIn] = Field(default_factory=list)


def _require_user(current_user: User | None) -> User:
    """画布会话端点要求登录（画布路由本身 requiresAuth）。"""
    if not current_user:
        raise HTTPException(status_code=401, detail="画布会话需要登录")
    return current_user


async def _get_owned_canvas_session(session_id: int, user: User, db: AsyncSession) -> ChatSession:
    """画布/对话页共用的会话同步通道归属校验（session_type: canvas 或 chat）"""
    stmt = select(ChatSession).filter(
        ChatSession.id == session_id,
        ChatSession.user_id == user.id,
        ChatSession.session_type.in_(("canvas", "chat")),
    )
    result = await db.execute(stmt)
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="画布会话不存在")
    return session


@router.post("/chat/agent-sessions", summary="创建画布 Agent 会话")
async def create_agent_session(
    body: AgentSessionCreateRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: User | None = Depends(get_current_user_optional),
):
    user = _require_user(current_user)
    session = ChatSession(
        user_id=user.id,
        title=(body.title or "新对话")[:200],
        session_type="canvas",
        workspace_id=body.workspace_id,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    logger.info("[Chat] 创建画布会话: id=%s, workspace=%s, user=%s", session.id, body.workspace_id, user.id)
    return ok(data=session.to_dict())


@router.put("/chat/agent-sessions/{session_id}", summary="全量同步画布 Agent 会话（context + 消息行整体替换）")
async def sync_agent_session(
    session_id: int,
    body: AgentSessionSyncRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: User | None = Depends(get_current_user_optional),
):
    user = _require_user(current_user)
    session = await _get_owned_canvas_session(session_id, user, db)

    session.title = (body.title or session.title or "新对话")[:200]
    if body.workspace_id is not None:
        session.workspace_id = body.workspace_id
    # context 为 None（前端内核不在池中时的补存）不覆盖已存上下文，防止抹掉
    if body.context is not None:
        session.context = body.context

    # 消息行全量替换（幂等）：同步量小，无增量协议
    await db.execute(delete(ChatMessage).where(ChatMessage.session_id == session.id))
    for m in body.messages:
        db.add(ChatMessage(
            session_id=session.id,
            role=m.role if m.role in ("user", "assistant", "system") else "user",
            content=m.content or "",
            attachments=m.attachments or [],
            steps=m.steps or [],
            media_items=m.media_items or [],
        ))
    await db.commit()
    await db.refresh(session)
    return ok(data=session.to_dict())


@router.get("/chat/agent-sessions/{session_id}", summary="读取画布 Agent 会话（context + 消息，恢复单请求）")
async def get_agent_session(
    session_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User | None = Depends(get_current_user_optional),
):
    user = _require_user(current_user)
    session = await _get_owned_canvas_session(session_id, user, db)
    msgs = await db.execute(
        select(ChatMessage).filter(ChatMessage.session_id == session.id).order_by(ChatMessage.id)
    )
    data = session.to_dict()
    data["context"] = session.context
    data["messages"] = [m.to_dict() for m in msgs.scalars().all()]
    return ok(data=data)


# =====================================================
# 媒体回调接口 — 前端轮询到结果后调用此接口更新消息
# =====================================================

@router.post("/chat/media-callback", summary="媒体生成完成回调")
async def media_callback(
    req: MediaCallbackRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: User | None = Depends(get_current_user_optional),
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
            return ok(message="媒体状态已更新")

    raise HTTPException(status_code=404, detail="未找到对应的媒体项")


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
        return ok(data=image_task.to_dict())

    # 再尝试视频任务
    video_task = await video_poller_manager.get_status(task_id=task_id)
    if not video_task:
        video_task = await video_poller_manager.get_status(video_id=task_id)
    if video_task:
        return ok(data=video_task.to_dict())

    # 最后查数据库
    try:
        async with async_session() as db:
            from app.models.generation import Generation
            result = await db.execute(
                select(Generation).filter(Generation.task_id == task_id)
            )
            record = result.scalar_one_or_none()
            if record:
                return ok(data={
                    "task_id": task_id,
                    "status": record.status,
                    "result_url": record.result_url,
                    "type": record.type,
                })
    except Exception as e:
        logger.warning("[Chat] 数据库查询媒体状态失败: %s", e)

    # 任务不在内存中也不在数据库中，返回 unknown 状态而非 404
    # 前端收到 unknown 后会停止轮询，避免无限 404 循环
    return ok(data={
        "task_id": task_id,
        "status": "unknown",
        "message": "任务已过期或不存在，请停止轮询",
    })


class AgentCompletionsRequest(BaseModel):
    """画布 Agent LLM 透传请求（OpenAI Chat Completions 形状的子集）

    工具循环由前端驱动，本端点只代理 Agnes Chat API，不落会话库。
    model 为前端模型选择提示（对话页模型胶囊/分镜管线）：命中聊天注册表才采用，
    占位 id（agnes-chat）或未命中走默认解析链。
    """
    model: str | None = Field(default=None, description="模型提示：命中聊天注册表才采用，未命中走默认解析链")
    messages: list[dict[str, Any]] = Field(..., min_length=1, description="OpenAI 格式消息数组（含工具结果回填）")
    tools: list[dict[str, Any]] | None = Field(default=None, description="OpenAI function calling 工具定义")
    tool_choice: Any | None = Field(default=None, description="工具选择策略（auto 或具体函数）")
    temperature: float | None = Field(default=None, ge=0, le=2)


@router.post("/chat/completions", summary="LLM 透传（画布 Agent 前端内核专用，SSE 流式，不落会话库）")
async def chat_completions_passthrough(
    body: AgentCompletionsRequest,
    current_user: User | None = Depends(get_current_user_optional),
    _: None = Depends(require_agnes_api_key),
):
    """
    代理 Agnes Chat API 流式接口，原样转发上游 SSE 行（data: {...} / data: [DONE]）。
    响应为 text/event-stream，不走统一 ok() envelope（流式特例，前端 provider 直接解析）。
    """
    try:
        generator = await chat_service.open_completions_stream(
            body.model_dump(exclude_none=True),
            user_id=current_user.id if current_user else None,
        )
    except Exception as exc:
        logger.error("[Chat] completions 透传失败: %s", exc)
        raise HTTPException(status_code=502, detail=f"LLM 调用失败：{exc}")
    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
