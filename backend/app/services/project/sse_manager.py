# =====================================================
# 项目级 SSE 推送管理器
#
# 功能:
#   1. 管理每个项目的 SSE 订阅者（多订阅者模式）
#   2. 向导进度、生成进度、实体变更等事件推送
#   3. 新订阅者可获取最近状态快照（重连场景）
#   4. 自动清理死连接
#
# 事件类型（event_type）:
#   - wizard_step_started:       向导步骤开始
#   - wizard_step_completed:     向导步骤完成
#   - wizard_step_failed:        向导步骤失败
#   - wizard_progress:           向导进度增量（如 LLM 流式 token）
#   - entity_updated:            实体（角色/场景/道具/分镜）更新
#   - generation_started:        生成任务开始（图片/视频）
#   - generation_progress:       生成进度
#   - generation_completed:      生成完成
#   - generation_failed:         生成失败
#   - active_version_changed:    当前激活版本变更
#   - project_status_changed:    项目状态变更
#   - merge_progress:            合成进度
#   - merge_completed:           合成完成
#   - state_snapshot:            状态快照（新订阅者首次回放）
#
# 使用方式:
#   - 服务层: await project_sse_manager.push(project_id, event_type, data)
#   - API 路由: queue = await project_sse_manager.subscribe(project_id) -> 生成器
# =====================================================

import asyncio
import json
import logging
import time
from typing import Dict, Any, Optional, Set

logger = logging.getLogger("agnes_platform.project")


class ProjectSSEManager:
    """
    项目级 SSE 推送管理器

    使用 asyncio.Queue 实现多订阅者模式，每个 project_id 独立维护订阅集合与状态快照。
    """

    def __init__(self):
        # project_id -> set of queues
        self._subscribers: Dict[int, Set[asyncio.Queue]] = {}
        # project_id -> 最近的状态快照（用于新订阅者回放）
        self._state_snapshots: Dict[int, Dict[str, Any]] = {}
        # 锁
        self._lock = asyncio.Lock()

    # ---------- 订阅 ----------

    async def subscribe(self, project_id: int) -> asyncio.Queue:
        """
        订阅一个项目的事件流。

        Returns:
            asyncio.Queue: 队列中是已格式化的 SSE 事件字符串
        """
        queue: asyncio.Queue = asyncio.Queue(maxsize=200)

        async with self._lock:
            if project_id not in self._subscribers:
                self._subscribers[project_id] = set()
            self._subscribers[project_id].add(queue)

        # 推送当前状态快照给新订阅者
        snapshot = self._state_snapshots.get(project_id)
        if snapshot:
            event_data = {
                "project_id": project_id,
                "event_type": "state_snapshot",
                "timestamp": time.time(),
                "data": snapshot,
            }
            event_str = self._format_sse_event("state_snapshot", event_data)
            await queue.put(event_str)

        logger.debug(
            f"Project SSE 订阅: project_id={project_id}, "
            f"当前订阅数={len(self._subscribers.get(project_id, set()))}"
        )
        return queue

    async def unsubscribe(self, project_id: int, queue: asyncio.Queue) -> None:
        """取消订阅"""
        async with self._lock:
            if project_id in self._subscribers:
                self._subscribers[project_id].discard(queue)
                if not self._subscribers[project_id]:
                    del self._subscribers[project_id]
                    # 保留快照一段时间，用于重连

        logger.debug(f"Project SSE 取消订阅: project_id={project_id}")

    # ---------- 推送 ----------

    async def push(
        self,
        project_id: int,
        event_type: str,
        data: Dict[str, Any],
        *,
        update_snapshot: bool = True,
    ) -> None:
        """
        向项目所有订阅者推送事件。

        Args:
            project_id: 项目 ID
            event_type: 事件类型（见模块文档）
            data: 事件数据
            update_snapshot: 是否同步更新状态快照（默认 True）
        """
        event_data = {
            "project_id": project_id,
            "event_type": event_type,
            "timestamp": time.time(),
            "data": data,
        }
        event_str = self._format_sse_event(event_type, event_data)

        if update_snapshot:
            self._update_snapshot(project_id, event_type, data)

        dead_queues: list = []
        async with self._lock:
            queues = self._subscribers.get(project_id, set())
            for queue in queues:
                try:
                    queue.put_nowait(event_str)
                except asyncio.QueueFull:
                    dead_queues.append(queue)

            for dead_q in dead_queues:
                queues.discard(dead_q)

            if queues and not self._subscribers.get(project_id):
                del self._subscribers[project_id]

        if dead_queues:
            logger.debug(
                f"Project SSE 清理死连接: project_id={project_id}, 清理 {len(dead_queues)} 个"
            )

    def push_sync(
        self,
        project_id: int,
        event_type: str,
        data: Dict[str, Any],
        *,
        update_snapshot: bool = True,
    ) -> None:
        """同步版本的 push（用于非 async 上下文，通过 create_task 调度）"""
        asyncio.create_task(
            self.push(project_id, event_type, data, update_snapshot=update_snapshot)
        )

    # ---------- 状态快照 ----------

    def init_snapshot(self, project_id: int, status: str = "draft") -> None:
        """初始化项目状态快照（项目创建时立即调用）"""
        self._state_snapshots[project_id] = {
            "project_id": project_id,
            "status": status,
            "wizard_step": None,
            "active_generations": {},
            "updated_at": time.time(),
        }

    def _update_snapshot(
        self, project_id: int, event_type: str, data: Dict[str, Any]
    ) -> None:
        """更新状态快照（新订阅者连接时回放）"""
        snapshot = self._state_snapshots.setdefault(
            project_id,
            {
                "project_id": project_id,
                "status": "in_progress",
                "wizard_step": None,
                "active_generations": {},
                "updated_at": time.time(),
            },
        )
        snapshot["updated_at"] = time.time()

        if event_type == "project_status_changed":
            snapshot["status"] = data.get("status", snapshot.get("status"))
        elif event_type.startswith("wizard_"):
            snapshot["wizard_step"] = data.get("step")
            if event_type == "wizard_step_failed":
                snapshot["wizard_error"] = data.get("error")
            elif event_type == "wizard_step_completed":
                snapshot.pop("wizard_error", None)
        elif event_type == "generation_started":
            gen_id = data.get("generation_id") or data.get("version_id")
            target = data.get("target")  # e.g. "character:12" / "shot:34:frame_image"
            if gen_id and target:
                snapshot["active_generations"][str(gen_id)] = {
                    "target": target,
                    "status": "running",
                    "started_at": time.time(),
                }
        elif event_type == "generation_progress":
            gen_id = data.get("generation_id") or data.get("version_id")
            if gen_id and str(gen_id) in snapshot["active_generations"]:
                snapshot["active_generations"][str(gen_id)]["progress"] = data.get(
                    "progress"
                )
        elif event_type in ("generation_completed", "generation_failed"):
            gen_id = data.get("generation_id") or data.get("version_id")
            if gen_id:
                snapshot["active_generations"].pop(str(gen_id), None)
        elif event_type == "active_version_changed":
            target = data.get("target")
            version_id = data.get("version_id")
            if target:
                snapshot.setdefault("active_versions", {})[target] = version_id

    def get_snapshot(self, project_id: int) -> Optional[Dict[str, Any]]:
        """获取当前状态快照"""
        return self._state_snapshots.get(project_id)

    # ---------- 清理 ----------

    def cleanup_project(self, project_id: int) -> None:
        """
        清理一个项目的所有订阅者和快照。
        项目归档/删除后由后台任务延迟调用。
        """
        # 当前实现：不立即清理，保留用于重连
        pass

    # ---------- 工具方法 ----------

    def _format_sse_event(self, event_type: str, data: Dict[str, Any]) -> str:
        """格式化 SSE 事件字符串"""
        data_str = json.dumps(data, ensure_ascii=False, default=str)
        return f"event: {event_type}\ndata: {data_str}\n\n"


# 全局单例
project_sse_manager = ProjectSSEManager()
