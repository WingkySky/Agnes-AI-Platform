# =====================================================
# 图片异步任务轮询管理器（全异步 + 并发安全）
# 职责：
#   1. 保存所有进行中图片任务状态（内存缓存）
#   2. 后台异步调用 Agnes AI 生成图片（不阻塞请求返回）
#   3. 完成后异步写入数据库（AsyncSession，不阻塞事件循环）
#   4. 定时清理过期缓存，防止内存泄漏
#
# 关键设计：
#   - 与视频任务完全独立，互不干扰
#   - 使用 asyncio.Lock 保护 _tasks 字典，并发读写安全
#   - 图片生成使用 Agnes AI 的同步接口，包装为独立 asyncio.Task
#   - LRU 式清理：已完成/失败任务超过 TTL 后自动移除
#   - 若在创建时传入 user_id + credits_consumed，会写入 generations 表
# =====================================================

import asyncio
import logging
import time
import uuid
from typing import Dict, Optional, List

from app.services.agnes_client import agnes_client
from app.models.generation import Generation
from app.core.database import new_async_session
from app.services.credits_service import confirm_credits, refund_credits

logger = logging.getLogger("agnes_platform")

CLEANUP_INTERVAL_SEC = 300
CLEANUP_TTL_SEC = 3600


class ImageTask:
    """单个图片任务的状态缓存"""

    def __init__(
        self,
        task_id: str,
        prompt: str,
        params: Dict,
        user_id: Optional[int] = None,
        credits_consumed: int = 0,
    ):
        self.task_id = task_id
        self.prompt = prompt
        self.params = params or {}
        self.user_id = user_id
        self.credits_consumed = credits_consumed
        self.status = "queued"
        self.progress = 0
        self.result_url: Optional[str] = None
        self.image_b64: Optional[str] = None
        self.error_message: Optional[str] = None
        self.created_at = time.time()
        self.last_updated = self.created_at
        self._gen_task: Optional[asyncio.Task] = None
        self._cancelled = False

    def to_dict(self) -> Dict:
        return {
            "task_id": self.task_id,
            "status": self.status,
            "progress": self.progress,
            "result_url": self.result_url,
            "url": self.result_url,
            "image_b64": self.image_b64,
            "message": self.error_message,
            "credits_consumed": self.credits_consumed,
            "elapsed_sec": int(time.time() - self.created_at),
        }


class ImagePollerManager:
    """
    管理所有进行中的图片任务：
    - 与视频任务完全独立，互不干扰
    - 使用 asyncio.Lock 确保并发读写安全
    - LRU TTL 自动清理，避免内存泄漏
    """

    def __init__(self):
        self._tasks: Dict[str, ImageTask] = {}
        self._lock = asyncio.Lock()
        self._cleanup_task: Optional[asyncio.Task] = None
        self._started = False

    async def start(self):
        if self._started:
            return
        self._started = True
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info("[图片任务器] 已启动，清理周期 %ss", CLEANUP_INTERVAL_SEC)

    async def create_task(
        self,
        prompt: str,
        params: Dict,
        user_id: Optional[int] = None,
        credits_consumed: int = 0,
        task_id: Optional[str] = None,
    ) -> ImageTask:
        # 支持外部传入 task_id（便于路由层先扣分再创建任务时保持 ref_id 一致）
        if not task_id:
            task_id = f"img_{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}"
        task = ImageTask(
            task_id=task_id,
            prompt=prompt,
            params=params,
            user_id=user_id,
            credits_consumed=credits_consumed,
        )
        task.status = "pending"

        async with self._lock:
            self._tasks[task_id] = task

        task._gen_task = asyncio.create_task(self._gen_loop(task_id, task))
        logger.info(
            "[图片任务器] 已创建任务: task_id=%s user=%s cost=%s prompt=%s",
            task_id, user_id, credits_consumed, prompt[:50],
        )
        return task

    async def get_status(self, task_id: str) -> Optional[ImageTask]:
        async with self._lock:
            return self._tasks.get(task_id)

    async def cancel(self, task_id: str):
        task = None
        async with self._lock:
            task = self._tasks.get(task_id)
        if task and not task._cancelled:
            task._cancelled = True
            task.status = "cancelled"
            if task._gen_task and not task._gen_task.done():
                task._gen_task.cancel()
            logger.info("[图片任务器] 任务已取消: task_id=%s", task_id)

    async def _gen_loop(self, task_id: str, task: ImageTask):
        try:
            task.status = "processing"
            task.progress = 10
            task.last_updated = time.time()

            result = await agnes_client.create_image(
                prompt=task.prompt,
                model=task.params.get("model", ""),
                size=task.params.get("size", "1024x1024"),
                response_format=task.params.get("response_format", "url"),
                base64_image=task.params.get("base64_image"),
                image_url=task.params.get("image_url"),
                base64_images=task.params.get("base64_images"),
                image_urls=task.params.get("image_urls"),
                mask=task.params.get("mask"),
            )

            output_url = None
            output_b64 = None
            if isinstance(result, dict):
                data = result.get("data")
                if isinstance(data, list) and len(data) > 0:
                    output_url = data[0].get("url")
                    output_b64 = data[0].get("b64_json")
                if not output_url and isinstance(result.get("url"), str):
                    output_url = result["url"]
                if not output_url and result.get("image"):
                    output_url = result["image"]

            task.progress = 80
            task.last_updated = time.time()

            if not output_url and not output_b64:
                task.status = "failed"
                task.error_message = "Agnes AI 返回异常，未找到图片数据"
                logger.warning("[图片任务器] 无结果数据: task_id=%s", task_id)
                # 生成失败：退还预扣的积分
                await self._refund_if_needed(task)
                return

            task.status = "success"
            task.progress = 100
            task.result_url = output_url
            task.image_b64 = output_b64
            task.last_updated = time.time()

            logger.info(
                "[图片任务器] 任务完成: task_id=%s url=%s",
                task_id, output_url[:100] if output_url else "(base64)",
            )

            await self._persist_result(task)
            # 生成成功：确认预扣的积分
            await self._confirm_if_needed(task)

        except asyncio.CancelledError:
            task.status = "cancelled"
            logger.info("[图片任务器] 任务被取消: task_id=%s", task_id)
            # 任务取消：退还预扣的积分
            await self._refund_if_needed(task)
        except Exception as e:
            task.status = "failed"
            task.error_message = str(e) or "生成失败，请稍后重试"
            task.last_updated = time.time()
            logger.error(
                "[图片任务器] 任务失败: task_id=%s error=%s",
                task_id, str(e), exc_info=True,
            )
            # 生成失败：退还预扣的积分
            await self._refund_if_needed(task)

    async def _confirm_if_needed(self, task: ImageTask):
        """生成成功后，把对应的预扣流水状态改为 confirmed（积分不变）"""
        if not task.user_id or not task.credits_consumed:
            return
        try:
            async with new_async_session() as session:
                await confirm_credits(session, task.user_id, task.task_id)
        except Exception as e:
            logger.warning("[图片任务器] 确认积分失败: task_id=%s error=%s", task.task_id, e)

    async def _refund_if_needed(self, task: ImageTask):
        """生成失败/取消后，退还预扣的积分"""
        if not task.user_id or not task.credits_consumed:
            return
        try:
            async with new_async_session() as session:
                await refund_credits(
                    session, task.user_id, task.task_id,
                    reason=f"图片生成失败：{task.error_message or '未知错误'}",
                )
        except Exception as e:
            logger.error("[图片任务器] 退还积分失败: task_id=%s error=%s", task.task_id, e)

    async def _persist_result(self, task: ImageTask):
        if task.status != "success":
            return
        try:
            async with new_async_session() as session:
                record = Generation(
                    type="image",
                    user_id=task.user_id,
                    prompt=task.prompt,
                    model=task.params.get("model", ""),
                    params={
                        k: v for k, v in task.params.items()
                        if k not in ("base64_image", "image_url", "base64_images", "image_urls", "mask")
                    },
                    mode=task.params.get("mode"),
                    result_url=task.result_url or "(base64)",
                    status=task.status,
                    credits_consumed=task.credits_consumed,
                    task_id=task.task_id,
                )
                session.add(record)
                await session.commit()
            logger.info("[图片任务器] 记录已异步写入数据库: task_id=%s", task.task_id)
        except Exception as e:
            logger.error("[图片任务器] 数据库写入失败: %s", e)

    async def _cleanup_loop(self):
        while True:
            await asyncio.sleep(CLEANUP_INTERVAL_SEC)
            try:
                now = time.time()
                removed: List[str] = []
                async with self._lock:
                    for key, t in list(self._tasks.items()):
                        if t.status in ("success", "failed", "cancelled") and (
                            now - t.last_updated > CLEANUP_TTL_SEC
                        ):
                            removed.append(key)
                    for key in removed:
                        del self._tasks[key]
                if removed:
                    logger.info("[图片任务器] 已清理 %s 个过期任务缓存", len(removed))
            except Exception as e:
                logger.error("[图片任务器] 清理协程异常: %s", e)

    async def shutdown(self):
        async with self._lock:
            for key, task in self._tasks.items():
                if task._gen_task and not task._gen_task.done():
                    task._gen_task.cancel()
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
        self._started = False
        logger.info("[图片任务器] 已关闭所有后台任务")


image_poller_manager = ImagePollerManager()
