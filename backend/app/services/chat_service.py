# =====================================================
# Chat Service — 聊天服务层
#
# 职责（AI 编排已全部迁前端内核，本层只保留三类能力）：
#   1. LLM 流式透传（open_completions_stream：前端内核/分镜管线/画布节点对话共用通道）
#   2. 会话标题总结（summarize_session_title，宿主自动命名用）
#   3. 消息媒体项状态刷新（refresh_message_media_items，宿主恢复历史用）
# =====================================================

import json
import logging
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models.chat import ChatMessage
from app.services.agnes_client import agnes_client
from app.services.image_poller import image_poller_manager
from app.services.video_poller import poller_manager as video_poller_manager

logger = logging.getLogger("agnes_platform")


class ChatService:
    """
    聊天服务：LLM 流式透传 + 会话标题总结 + 消息媒体项刷新
    """

    @property
    def chat_url(self) -> str:
        """动态获取聊天 API 地址（从 agnes_client 读取最新的 base_url）"""
        return f"{agnes_client.base_url}/chat/completions"

    async def _get_default_chat_model(self, user_id: int | None = None) -> str:
        """
        解析对话模型：用户偏好 default_chat_model_id > 系统默认（管理员配置 model.chat_default）> 注册表第一个 chat 模型。
        user_id 为空时跳过用户偏好层。
        """
        from app.core.database import new_async_session
        from app.services.model_registry import resolve_user_chat_model_id
        async with new_async_session() as db:
            model = await resolve_user_chat_model_id(db, user_id or 0)
        if not model:
            raise RuntimeError("未配置可用的对话模型，请先在配置页同步或添加对话模型")
        return model

    async def _resolve_stream_model(self, model_hint: Any, user_id: int | None = None) -> str:
        """透传流式模型解析：显式 model 命中聊天注册表才用（分镜管线/对话选择），占位 id 走默认链"""
        if isinstance(model_hint, str) and model_hint.strip():
            from app.services.model_registry import get_models_by_type
            chat_models = await get_models_by_type("chat")
            if any(m.id == model_hint for m in chat_models):
                return model_hint
        return await self._get_default_chat_model(user_id)

    @staticmethod
    def _sanitize_passthrough_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """透传消息清洗：剔除畸形 tool_call 与孤儿 tool 结果。
        上游推理模型偶发吐出 id/name 全空的 tool_call（arguments 为 {}），内核以"Tool not found"
        回填后，畸形 assistant 消息随历史重放会被上游 400（Invalid JSON data）拒绝并卡死后续回合。"""
        out: list[dict[str, Any]] = []
        for msg in messages:
            if not isinstance(msg, dict):
                continue
            role = msg.get("role")
            if role == "assistant" and isinstance(msg.get("tool_calls"), list):
                raw_calls = msg["tool_calls"]
                valid = [
                    tc for tc in raw_calls
                    if isinstance(tc, dict)
                    and isinstance(tc.get("function"), dict)
                    and str((tc.get("function") or {}).get("name") or "").strip()
                    and str(tc.get("id") or "").strip()
                ]
                if len(valid) != len(raw_calls):
                    content = msg.get("content")
                    has_text = isinstance(content, str) and bool(content.strip())
                    if not valid and not has_text:
                        continue  # 整条只有空调用且无正文：丢弃
                    msg = {**msg, "tool_calls": valid} if valid else {k: v for k, v in msg.items() if k != "tool_calls"}
            if role == "tool" and not str(msg.get("tool_call_id") or "").strip():
                continue  # 空 tool_call_id 的结果无处挂靠，重放必被上游拒绝
            out.append(msg)
        return out

    async def open_completions_stream(self, payload: dict[str, Any], user_id: int | None = None):
        """
        LLM 透传流式连接（画布 Agent 前端内核专用）：不落会话库，工具循环由前端驱动，
        后端只负责代理 Agnes Chat API（API key 不出后端）。
        payload 为 OpenAI Chat Completions 请求形状的子集：messages 必填，
        tools / tool_choice / temperature 可选；模型始终由后端默认解析链决定——
        前端内核只知道占位 id（如 agnes-chat），若透传会 upstream model_not_found。
        建连失败抛异常由路由转 502；返回原始 SSE 行生成器（data: {...} / data: [DONE]），
        调用方需完整消费以释放连接。
        """
        body: dict[str, Any] = {
            "model": await self._resolve_stream_model(payload.get("model"), user_id),
            "messages": self._sanitize_passthrough_messages(payload.get("messages") or []),
            "stream": True,
        }
        if payload.get("tools"):
            body["tools"] = payload["tools"]
        if payload.get("tool_choice") is not None:
            body["tool_choice"] = payload["tool_choice"]
        if payload.get("temperature") is not None:
            body["temperature"] = payload["temperature"]

        headers = {
            "Authorization": f"Bearer {agnes_client.api_key}",
            "Content-Type": "application/json",
        }
        # 请求体日志（与 _post 同风格，截断长字段）：透传链路排障用——此前流式端点无日志导致 Agent 行为无法取证
        safe_body = {
            k: (f"<str len={len(v)}> {v[:120]}..." if isinstance(v, str) and len(v) > 200 else v)
            for k, v in body.items()
        }
        logger.info("[Chat] completions 流式透传 body=%s", safe_body)
        request = agnes_client.client.build_request(
            "POST",
            self.chat_url,
            json=body,
            headers=headers,
            timeout=httpx.Timeout(120.0, connect=30.0),
        )
        response = await agnes_client.client.send(request, stream=True)
        if response.status_code != 200:
            error_text = await response.aread()
            await response.aclose()
            raise RuntimeError(f"上游 API 错误 (HTTP {response.status_code}): {error_text.decode()[:200]}")

        async def sse_lines():
            try:
                done_seen = False
                async for line in response.aiter_lines():
                    line = line.strip()
                    if not line.startswith("data: "):
                        continue
                    # SSE 事件以空行分隔；aiter_lines 已去换行，必须补 \n\n 否则整条流连成一行，客户端解析器切不出事件
                    yield f"{line}\n\n"
                    if line[6:] == "[DONE]":
                        done_seen = True
                        return
                if not done_seen:
                    # 上游提前断流：补 [DONE] 让前端流式解析正常收尾
                    yield "data: [DONE]\n\n"
            except Exception as e:
                logger.error("[Chat] completions 流式透传中断: %s", e)
                err = json.dumps({"error": {"message": f"上游连接中断: {e}", "type": "upstream_error"}}, ensure_ascii=False)
                yield f"data: {err}\n\n"
                yield "data: [DONE]\n\n"
            finally:
                await response.aclose()

        return sse_lines()

    # =====================================================
    # 【会话标题总结】—— 根据对话内容自动生成有意义的标题
    # =====================================================
    async def summarize_session_title(self, messages) -> str:
        """
        根据对话内容，使用 AI 生成一个简洁、有意义的会话标题。

        Args:
            messages: 消息对象列表（ChatMessage ORM 对象）

        Returns:
            生成的标题字符串（不超过 30 字）
        """
        # 提取对话内容（只用前 5 条，控制上下文长度）
        chat_history = []
        for msg in messages[:5]:
            if msg.role in ("user", "assistant"):
                content = msg.content or ""
                if content.strip():
                    # 截断过长的单条消息
                    if len(content) > 500:
                        content = content[:500] + "..."
                    chat_history.append({
                        "role": msg.role,
                        "content": content,
                    })

        if not chat_history:
            return "新对话"

        # 构造总结标题的请求
        system_prompt = """你是一个对话总结助手。请根据提供的对话内容，生成一个简洁、有意义的中文标题。

要求：
1. 标题必须使用中文
2. 不超过 20 个字符
3. 准确概括对话的核心主题或用户意图
4. 不要加引号、冒号等前缀
5. 只输出标题本身，不要输出任何其他文字、解释或说明"""

        user_prompt = "请根据以下对话生成一个简洁的中文标题（不超过 20 字）：\n\n"
        for item in chat_history:
            role_label = "用户" if item["role"] == "user" else "助手"
            user_prompt += f"{role_label}: {item['content']}\n"
        user_prompt += "\n标题："

        # 标题总结为系统级任务：管理员配置 model.title_summary_chat > 系统默认
        from app.services.model_registry import (
            SYSTEM_CHAT_MODEL_KEYS,
            resolve_system_chat_model_id,
        )
        title_model = await resolve_system_chat_model_id(None, SYSTEM_CHAT_MODEL_KEYS["title_summary"])
        body = {
            "model": title_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.5,
            "max_tokens": 50,
        }

        try:
            result = await agnes_client._post(self.chat_url, body)
            choice = result.get("choices", [{}])[0]
            message = choice.get("message", {})
            title = message.get("content", "") or ""
            title = title.strip().strip('"').strip("'").strip("`")
            # 去除可能的前缀说明
            if "：" in title and len(title) > 40:
                title = title.split("：")[-1].strip()
            if ":" in title and len(title) > 40:
                title = title.split(":")[-1].strip()
            # 限制长度
            if len(title) > 30:
                title = title[:30]
            return title or "新对话"
        except Exception as e:
            logger.warning("[Chat] 总结标题失败: %s", e)
            # 降级：取第一条用户消息的前 30 字
            first_user = next((m for m in chat_history if m["role"] == "user"), None)
            if first_user and first_user.get("content"):
                return first_user["content"][:30]
            return "新对话"

    # =====================================================
    # 【消息媒体项刷新】—— 宿主恢复历史时同步媒体任务最新状态
    # =====================================================

    async def refresh_message_media_items(self, messages: list[ChatMessage], db: AsyncSession) -> None:
        """
        将消息里的 pending/processing 媒体项刷新为最新状态。

        发送下一轮聊天前也必须做这件事，否则用户虽然已经在前端看到图片完成，
        但后端构建上下文时仍可能只看到 pending，导致无法把上一张图作为 image2image 参考图。
        """
        for msg in messages:
            if not msg.media_items:
                continue

            updated = False
            refreshed_items = []
            for original_item in msg.media_items:
                item = dict(original_item)
                if item.get("status") not in ("pending", "processing") or not item.get("task_id"):
                    refreshed_items.append(item)
                    continue

                task_id = item["task_id"]
                result_url = None
                new_status = None

                img_task = await image_poller_manager.get_status(task_id)
                if img_task:
                    d = img_task.to_dict()
                    if d.get("status") in ("success", "completed", "done"):
                        result_url = d.get("result_url") or d.get("url")
                        new_status = "success"
                    elif d.get("status") in ("failed", "error"):
                        new_status = "failed"

                if not result_url and not new_status:
                    vid_task = await video_poller_manager.get_status(task_id=task_id)
                    if not vid_task:
                        vid_task = await video_poller_manager.get_status(video_id=task_id)
                    if vid_task:
                        d = vid_task.to_dict()
                        if d.get("status") in ("success", "completed", "done"):
                            result_url = d.get("video_url") or d.get("url")
                            new_status = "success"
                        elif d.get("status") in ("failed", "error"):
                            new_status = "failed"

                if not result_url and not new_status:
                    try:
                        from app.models.generation import Generation
                        gen_record = await db.scalars(
                            select(Generation).filter(Generation.task_id == task_id)
                        ).first()
                        if gen_record:
                            if gen_record.status == "success":
                                result_url = gen_record.result_url
                                new_status = "success"
                            elif gen_record.status == "failed":
                                new_status = "failed"
                    except Exception:
                        pass

                if result_url or new_status:
                    if result_url:
                        item["url"] = result_url
                    if new_status:
                        item["status"] = new_status
                    updated = True
                refreshed_items.append(item)

            if updated:
                msg.media_items = refreshed_items

        await db.commit()


# 全局单例
chat_service = ChatService()
