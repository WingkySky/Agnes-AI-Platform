# =====================================================
# 流水线 SSE 进度推送管理器
#
# 功能:
#   1. 管理每个流水线的 SSE 订阅者
#   2. 执行引擎通过回调推送进度事件
#   3. 自动清理超时/断开的连接
#   4. 新订阅者能获取当前状态（回放）
#
# 使用方式:
#   - 执行引擎: pipeline_sse_manager.emit(run_id, event, data)
#   - API 路由: pipeline_sse_manager.subscribe(run_id) -> 生成器
# =====================================================

import asyncio
import json
import logging
import time
from typing import Dict, Any, Optional, Set, Callable

logger = logging.getLogger("agnes_platform.pipeline")


class PipelineSSEManager:
    """
    流水线 SSE 进度推送管理器

    管理所有流水线的 SSE 订阅，使用 asyncio.Queue 实现多订阅者模式。
    """

    def __init__(self):
        # run_id -> set of queues
        self._subscribers: Dict[int, Set[asyncio.Queue]] = {}
        # run_id -> 最近的状态快照（用于新订阅者回放）
        self._state_snapshots: Dict[int, Dict[str, Any]] = {}
        # 锁
        self._lock = asyncio.Lock()

    # ---------- 订阅 ----------

    async def subscribe(self, run_id: int) -> asyncio.Queue:
        """
        订阅一个流水线的进度事件。
        返回一个 asyncio.Queue，里面是 SSE 事件字符串。
        """
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)

        async with self._lock:
            if run_id not in self._subscribers:
                self._subscribers[run_id] = set()
            self._subscribers[run_id].add(queue)

        # 如果有状态快照，先把当前状态推给新订阅者
        snapshot = self._state_snapshots.get(run_id)
        if not snapshot:
            # 内存中没有快照，尝试从数据库构建（流水线刚启动或服务重启场景）
            snapshot = await self._build_snapshot_from_db(run_id)
            if snapshot:
                self._state_snapshots[run_id] = snapshot

        if snapshot:
            # 使用与其他事件一致的包装格式
            event_data = {
                "run_id": run_id,
                "event_type": "state_snapshot",
                "step_key": "",
                "timestamp": time.time(),
                "data": snapshot,
            }
            event_str = self._format_sse_event("state_snapshot", event_data)
            await queue.put(event_str)

        logger.debug(f"SSE 订阅: run_id={run_id}, 当前订阅数={len(self._subscribers[run_id])}")
        return queue

    async def _build_snapshot_from_db(self, run_id: int) -> Optional[Dict[str, Any]]:
        """从数据库构建当前状态快照（用于内存中没有快照时的初始回放）"""
        db = None
        try:
            from app.core.database import new_async_session
            from app.models.pipeline import PipelineRun, PipelineStep
            from sqlalchemy import select

            db = new_async_session()
            run_result = await db.execute(
                select(PipelineRun).filter(PipelineRun.id == run_id)
            )
            run = run_result.scalar_one_or_none()
            if not run:
                return None

            steps_result = await db.execute(
                select(PipelineStep)
                .filter(PipelineStep.run_id == run_id)
                .order_by(PipelineStep.sort_order)
            )
            steps = steps_result.scalars().all()

            steps_dict = {}
            current_step = None
            for step in steps:
                steps_dict[step.step_key] = {
                    "status": step.status,
                    "name": step.name,
                    "error": step.error_message,
                }
                if step.status == "running":
                    current_step = step.step_key

            return {
                "run_id": run_id,
                "status": run.status,
                "current_step": current_step or run.current_step_key,
                "steps": steps_dict,
                "error": run.error_message,
                "updated_at": time.time(),
            }
        except Exception as e:
            logger.warning(f"从 DB 构建 SSE 快照失败 run_id={run_id}: {e}")
            return None
        finally:
            if db:
                await db.close()

    def init_snapshot(self, run_id: int, status: str = "pending") -> None:
        """初始化一个流水线的快照（创建 run 时立即调用，确保订阅者能收到初始状态）"""
        self._state_snapshots[run_id] = {
            "run_id": run_id,
            "status": status,
            "current_step": None,
            "steps": {},
            "updated_at": time.time(),
        }

    async def unsubscribe(self, run_id: int, queue: asyncio.Queue) -> None:
        """取消订阅"""
        async with self._lock:
            if run_id in self._subscribers:
                self._subscribers[run_id].discard(queue)
                if not self._subscribers[run_id]:
                    del self._subscribers[run_id]
                    # 保留快照一段时间，用于重连

        logger.debug(f"SSE 取消订阅: run_id={run_id}")

    # ---------- 推送 ----------

    async def emit(self, run_id: int, event_type: str, step_key: str, data: Dict[str, Any]) -> None:
        """
        发送进度事件给所有订阅者。

        Args:
            run_id: 流水线 ID
            event_type: 事件类型（step_started / step_progress / step_completed / step_failed / pipeline_completed）
            step_key: 步骤 key
            data: 事件数据
        """
        event_data = {
            "run_id": run_id,
            "event_type": event_type,
            "step_key": step_key,
            "timestamp": time.time(),
            "data": data,
        }

        event_str = self._format_sse_event(event_type, event_data)

        # 更新状态快照
        self._update_snapshot(run_id, event_type, step_key, data)

        # 推送给所有订阅者
        async with self._lock:
            queues = self._subscribers.get(run_id, set())
            dead_queues = []

            for queue in queues:
                try:
                    queue.put_nowait(event_str)
                except asyncio.QueueFull:
                    # 队列满了，可能是死连接，标记清理
                    dead_queues.append(queue)

            # 清理死连接
            for dead_q in dead_queues:
                queues.discard(dead_q)

            if queues and not self._subscribers.get(run_id):
                del self._subscribers[run_id]

        if dead_queues:
            logger.debug(f"SSE 清理死连接: run_id={run_id}, 清理 {len(dead_queues)} 个")

    def emit_sync(self, run_id: int, event_type: str, step_key: str, data: Dict[str, Any]) -> None:
        """同步版本的 emit（用于非 async 上下文，通过 create_task 调度）"""
        asyncio.create_task(self.emit(run_id, event_type, step_key, data))

    # ---------- 状态快照 ----------

    def _update_snapshot(self, run_id: int, event_type: str, step_key: str, data: Dict[str, Any]) -> None:
        """更新状态快照（新订阅者连接时回放）"""
        snapshot = self._state_snapshots.setdefault(run_id, {
            "run_id": run_id,
            "status": "running",
            "current_step": None,
            "steps": {},
            "updated_at": time.time(),
        })

        snapshot["updated_at"] = time.time()

        if event_type == "pipeline_started":
            snapshot["status"] = "running"
            snapshot["started_at"] = time.time()
            # 如果事件中带了步骤列表，初始化到快照中
            if data.get("steps"):
                for step_info in data["steps"]:
                    key = step_info.get("key")
                    if key and key not in snapshot["steps"]:
                        snapshot["steps"][key] = {
                            "status": step_info.get("status", "pending"),
                            "name": step_info.get("name"),
                        }
        elif event_type == "step_started":
            snapshot["current_step"] = step_key
            snapshot["steps"][step_key] = {
                "status": "running",
                "name": data.get("name"),
                "started_at": time.time(),
            }
        elif event_type == "step_progress":
            if step_key in snapshot["steps"]:
                snapshot["steps"][step_key]["progress"] = data.get("progress")
        elif event_type == "step_completed":
            if step_key in snapshot["steps"]:
                snapshot["steps"][step_key]["status"] = "success"
                snapshot["steps"][step_key]["completed_at"] = time.time()
                snapshot["steps"][step_key]["output_summary"] = data.get("output_summary")
        elif event_type == "step_failed":
            if step_key in snapshot["steps"]:
                snapshot["steps"][step_key]["status"] = "failed"
                snapshot["steps"][step_key]["error"] = data.get("error")
                snapshot["steps"][step_key]["failed_at"] = time.time()
        elif event_type == "pipeline_completed":
            snapshot["status"] = data.get("status", "success")
            snapshot["output_summary"] = data.get("output_summary")
            snapshot["finished_at"] = time.time()

    def get_snapshot(self, run_id: int) -> Optional[Dict[str, Any]]:
        """获取当前状态快照"""
        return self._state_snapshots.get(run_id)

    # ---------- 清理 ----------

    def cleanup_run(self, run_id: int) -> None:
        """清理一个流水线的所有订阅者和快照（流水线结束后延迟调用）"""
        # 不立即清理，保留一段时间用于重连
        # 可以在流水线完成一段时间后由后台任务清理
        pass

    # ---------- 工具方法 ----------

    def _format_sse_event(self, event_type: str, data: Dict[str, Any]) -> str:
        """格式化 SSE 事件"""
        data_str = json.dumps(data, ensure_ascii=False)
        return f"event: {event_type}\ndata: {data_str}\n\n"

    def make_progress_callback(self, run_id: int) -> Callable:
        """
        创建一个进度回调函数，传给流水线引擎使用。

        用法:
            callback = pipeline_sse_manager.make_progress_callback(run_id)
            engine = PipelineEngine(run_id, progress_callback=callback)
        """
        def _callback(event_type: str, step_key: str, data: Dict[str, Any]) -> None:
            self.emit_sync(run_id, event_type, step_key, data)

        return _callback


# 全局单例
pipeline_sse_manager = PipelineSSEManager()
