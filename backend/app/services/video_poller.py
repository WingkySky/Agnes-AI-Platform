# =====================================================
# 视频异步任务轮询管理器（全异步 + 并发安全
# 职责：
#   1. 保存所有进行中视频任务状态（内存缓存）
#   2. 后台自动轮询 Agnes AI 直到任务完成/失败/取消
#   3. 完成后异步写入数据库（异步 SQLAlchemy，不阻塞事件循环
#   4. 定时清理过期缓存，防止内存泄漏
#
# 关键设计：
#   - 使用 asyncio.Lock 保护 _tasks 字典，并发读写安全
#   - 使用 AsyncSession 写入数据库，完全异步，不阻塞事件循环
#   - 每个视频任务是独立的 asyncio.Task，与图片生成任务**互不干扰**
#   - LRU 式清理：已完成/失败任务超过 TTL 后自动移除
# =====================================================

import asyncio
import logging
import time
from typing import Dict, Optional, List

from app.services.agnes_client import agnes_client
from app.models.generation import Generation
from app.core.database import new_async_session

logger = logging.getLogger("agnes_platform")

# ---------- 清理参数 ----------
CLEANUP_INTERVAL_SEC = 300   # 每 5 分钟扫描一次过期缓存
CLEANUP_TTL_SEC = 3600        # 已完成任务保留 1 小时后清除


# =====================================================
# 单个视频任务状态对象
# =====================================================
class VideoTask:
    """单个视频任务的状态缓存"""

    def __init__(
        self,
        task_id: Optional[str],
        video_id: Optional[str],
        prompt: str,
        params: Dict,
    ):
        self.task_id = task_id
        self.video_id = video_id
        self.prompt = prompt
        self.params = params or {}
        self.status = "processing"
        self.progress = 0
        self.video_url: Optional[str] = None
        self.error_message: Optional[str] = None
        self.created_at = time.time()
        self.last_updated = self.created_at
        self._poll_task: Optional[asyncio.Task] = None
        self._cancelled = False

    def to_dict(self) -> Dict:
        return {
            "task_id": self.task_id,
            "video_id": self.video_id,
            "status": self.status,
            "progress": self.progress,
            "video_url": self.video_url,
            "message": self.error_message,
            "elapsed_sec": int(time.time() - self.created_at),
        }


# =====================================================
# 轮询管理器（全局单例）
# =====================================================
class VideoPollerManager:
    """
    管理所有进行中的视频任务：
    - 使用 asyncio.Lock 确保并发读写安全
    - 每个任务独立的 asyncio.Task，图片生成与视频任务互不影响
    - LRU TTL 自动清理，避免内存泄漏
    """

    def __init__(self):
        self._tasks: Dict[str, VideoTask] = {}
        self._tasks_by_video_id: Dict[str, str] = {}
        self._lock = asyncio.Lock()
        self._cleanup_task: Optional[asyncio.Task] = None
        self._started = False

    # ---------- 启动后台清理协程 ----------
    async def start(self):
        """
        启动后台周期性清理协程（在应用启动时调用一次。
        """
        if self._started:
            return
        self._started = True
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info("[视频轮询器] 已启动，清理周期 %ss", CLEANUP_INTERVAL_SEC)

    # ---------- 启动一个视频任务的后台轮询 ----------
    async def start_polling(
        self,
        task_id: Optional[str],
        video_id: Optional[str],
        prompt: str,
        params: Dict,
    ) -> VideoTask:
        """
        创建 VideoTask 并启动后台协程轮询，不阻塞当前请求。
        图片生成请求（走 images 路由不会调用此方法）与视频任务互不影响。
        """
        key = task_id or video_id or f"unknown_{int(time.time() * 1000)}"
        task = VideoTask(task_id=task_id, video_id=video_id, prompt=prompt, params=params)

        async with self._lock:
            self._tasks[key] = task
            if video_id:
                self._tasks_by_video_id[video_id] = key

        # 启动后台轮询协程（独立 asyncio.Task，不阻塞创建请求）
        task._poll_task = asyncio.create_task(self._poll_loop(key, task))
        logger.info("[视频轮询器] 已启动任务: task_id=%s video_id=%s", task_id, video_id)
        return task

    # ---------- 获取任务状态 ----------
    async def get_status(
        self, task_id: Optional[str] = None, video_id: Optional[str] = None
    ) -> Optional[VideoTask]:
        """
        根据 task_id 或 video_id 查找任务状态（并发安全读取
        """
        async with self._lock:
            if task_id and task_id in self._tasks:
                return self._tasks[task_id]
            if video_id and video_id in self._tasks_by_video_id:
                return self._tasks.get(self._tasks_by_video_id[video_id])
            return None

    # ---------- 取消任务 ----------
    async def cancel(
        self, task_id: Optional[str] = None, video_id: Optional[str] = None
    ):
        """
        中止指定视频任务的后台轮询（仅停止本地轮询，不保证服务端已终止）。
        """
        task = None
        async with self._lock:
            if task_id and task_id in self._tasks:
                task = self._tasks[task_id]
            elif video_id and video_id in self._tasks_by_video_id:
                task = self._tasks.get(self._tasks_by_video_id[video_id])

        if task and not task._cancelled:
            task._cancelled = True
            task.status = "cancelled"
            if task._poll_task and not task._poll_task.done():
                task._poll_task.cancel()
            logger.info("[视频轮询器] 任务已取消: task_id=%s", task_id)

    # ---------- 轮询主循环 ----------
    async def _poll_loop(self, key: str, task: VideoTask):
        """
        后台轮询协程：每 POLL_INTERVAL 秒查询一次 Agnes AI，直到任务完成/超时/取消。
        所有 I/O 操作均为 await，不阻塞事件循环，不影响其他图片生成请求。
        """
        max_wait = self._get_timeout()
        interval = self._get_interval()
        start_time = time.time()

        try:
            while (time.time() - start_time) < max_wait:
                if task._cancelled:
                    return

                try:
                    status_data = await agnes_client.poll_video_status(
                        video_id=task.video_id, task_id=task.task_id
                    )

                    status = status_data.get("status", "unknown")
                    task.last_updated = time.time()

                    if status in ("completed", "success"):
                        task.status = "success"
                        task.progress = 100
                        task.video_url = status_data.get("video_url")
                        logger.info(
                            "[视频轮询器] 任务完成: task_id=%s url=%s",
                            task.task_id,
                            task.video_url,
                        )
                        await self._persist_result(task)
                        return

                    elif status in ("failed", "error"):
                        task.status = "failed"
                        task.error_message = status_data.get("error") or "生成失败"
                        logger.warning(
                            "[视频轮询器] 任务失败: task_id=%s error=%s",
                            task.task_id,
                            task.error_message,
                        )
                        await self._persist_result(task)
                        return

                    elif status == "cancelled":
                        task.status = "cancelled"
                        return

                    else:
                        task.status = "processing"
                        p = status_data.get("progress")
                        if isinstance(p, (int, float)):
                            task.progress = min(int(p), 99)
                        else:
                            elapsed = time.time() - start_time
                            task.progress = min(int(elapsed / 180 * 100), 85)

                except asyncio.CancelledError:
                    task.status = "cancelled"
                    return
                except Exception as e:
                    logger.warning("[视频轮询器] 单次查询异常: %s", e)
                    task.error_message = f"查询中发生错误: {str(e)}"

                await asyncio.sleep(interval)

            task.status = "failed"
            task.error_message = "轮询超时（超过配置时长）"
            logger.warning("[视频轮询器] 任务超时: task_id=%s", task.task_id)

        except Exception as e:
            task.status = "failed"
            task.error_message = f"轮询器异常: {e}"
            logger.error("[视频轮询器] 异常退出: %s", e, exc_info=True)

    # ---------- 异步写入数据库 ----------
    async def _persist_result(self, task: VideoTask):
        """
        视频任务完成/失败后，异步写入数据库。
        使用 AsyncSession，完全异步 I/O，不阻塞事件循环。
        """
        try:
            async with new_async_session() as session:
                record = Generation(
                    type="video",
                    prompt=task.prompt,
                    model=task.params.get("model", "agnes-video-v2.0"),
                    params=task.params,
                    mode=task.params.get("mode"),
                    result_url=task.video_url,
                    status=task.status,
                    task_id=task.task_id or task.video_id,
                )
                session.add(record)
                await session.commit()
            logger.info("[视频轮询器] 记录已异步写入数据库: status=%s", task.status)
        except Exception as e:
            logger.error("[视频轮询器] 数据库写入失败: %s", e)

    # ---------- 后台清理协程 ----------
    async def _cleanup_loop(self):
        """
        定期清理已完成/失败/取消且超过 TTL 的任务，防止内存泄漏。
        清理操作不阻塞事件循环。
        """
        while True:
            await asyncio.sleep(CLEANUP_INTERVAL_SEC)
            try:
                now = time.time()
                removed: List[str] = []
                async with self._lock:
                    for key, t in list(self._tasks.items()):
                        # 仅清理已完成且超过 TTL 的任务
                        if t.status in ("success", "failed", "cancelled") and (
                            now - t.last_updated > CLEANUP_TTL_SEC
                        ):
                            removed.append(key)
                            if t.video_id and t.video_id in self._tasks_by_video_id:
                                del self._tasks_by_video_id[t.video_id]
                    for key in removed:
                        del self._tasks[key]

                if removed:
                    logger.info("[视频轮询器] 已清理 %s 个过期任务缓存", len(removed))
            except Exception as e:
                logger.error("[视频轮询器] 清理协程异常: %s", e)

    # ---------- 优雅关闭 ----------
    async def shutdown(self):
        """
        服务关闭时：取消所有进行中的轮询任务，取消清理协程。
        """
        async with self._lock:
            for key, task in self._tasks.items():
                if task._poll_task and not task._poll_task.done():
                    task._poll_task.cancel()

        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()

        self._started = False
        logger.info("[视频轮询器] 已关闭所有后台任务")

    # ---------- 工具函数：获取配置（可替换为读取 settings ----------
    @staticmethod
    def _get_interval() -> int:
        try:
            from app.core.config import settings as _settings

            return int(_settings.video_poll_interval_sec or 5)
        except Exception:
            return 5

    @staticmethod
    def _get_timeout() -> int:
        try:
            from app.core.config import settings as _settings

            return int(_settings.video_poll_timeout_sec or 600)
        except Exception:
            return 600


# 全局单例
poller_manager = VideoPollerManager()
