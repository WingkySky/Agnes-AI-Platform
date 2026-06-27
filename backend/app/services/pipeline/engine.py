# =====================================================
# 流水线执行引擎
#
# 核心功能:
#   1. DAG 依赖解析 + 拓扑排序
#   2. 状态机管理（pipeline 级别 + step 级别）
#   3. 步骤调度执行（支持串行 + 可并行步骤并发）
#   4. 失败重试
#   5. 断点续跑（从数据库恢复状态后继续）
#   6. 积分扣减
#   7. SSE 进度推送（通过回调机制）
# =====================================================

import asyncio
import logging
from datetime import datetime
from typing import Callable, Dict, Any, List, Optional, Set
from collections import deque

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update as sa_update
from fastapi import HTTPException

from app.core.database import new_async_session
from app.models.pipeline import (
    PipelineTemplate,
    PipelineRun,
    PipelineStep,
    StylePreset,
    ScriptTemplate,
)
from app.services.pipeline.steps import create_step_executor, StepExecutionContext
from app.services.pipeline.template_service import get_template_by_id
from app.services import credits_service
from app.services import style_service
from app.services import script_template_service

logger = logging.getLogger("agnes_platform.pipeline")

# 状态常量
STATUS_PENDING = "pending"
STATUS_RUNNING = "running"
STATUS_SUCCESS = "success"
STATUS_FAILED = "failed"
STATUS_CANCELLED = "cancelled"
STATUS_SKIPPED = "skipped"
STATUS_WAITING_REVIEW = "waiting_review"


# ---------- 进度回调类型 ----------
ProgressCallback = Callable[[str, str, Dict[str, Any]], None]
# event_type: step_started / step_progress / step_completed / step_failed / pipeline_completed


# =====================================================
# 流水线实例创建 & 初始化
# =====================================================

async def create_pipeline_run(
    db: AsyncSession,
    template_id: int,
    inputs: Dict[str, Any],
    user_id: Optional[int] = None,
    name: Optional[str] = None,
) -> PipelineRun:
    """
    创建流水线实例（但不启动执行）。

    会做:
    - 验证模板存在
    - 验证输入参数
    - 创建 pipeline_run 记录
    - 根据模板创建所有 pipeline_step 记录（状态为 pending）
    """
    template = await get_template_by_id(db, template_id)
    if not template:
        raise HTTPException(status_code=404, detail="流水线模板不存在")

    # 验证输入（简单校验必填项，详细校验在步骤执行时做）
    for input_def in template.inputs_config:
        if input_def.get("required") and input_def.get("key") not in inputs:
            raise HTTPException(
                status_code=400,
                detail=f"缺少必填参数: {input_def.get('key')} ({input_def.get('label')})",
            )

    # 创建流水线实例
    run = PipelineRun(
        template_id=template_id,
        user_id=user_id,
        name=name or template.name,
        inputs=inputs,
        status=STATUS_PENDING,
    )
    db.add(run)
    await db.flush()  # 获取 run.id

    # 根据模板创建步骤记录
    steps_config = template.steps_config
    for idx, step_cfg in enumerate(steps_config):
        step = PipelineStep(
            run_id=run.id,
            step_key=step_cfg.get("key", f"step_{idx}"),
            name=step_cfg.get("name", f"步骤 {idx + 1}"),
            step_type=step_cfg.get("type", "unknown"),
            status=STATUS_PENDING,
            input_data={},
            output_data={},
            max_retries=step_cfg.get("max_retries", 1),
            timeout_sec=step_cfg.get("timeout", 300),
            depends_on=step_cfg.get("depends_on", []),
            sort_order=idx,
        )
        db.add(step)

    await db.commit()
    await db.refresh(run)

    logger.info(f"创建流水线实例: run_id={run.id}, template={template.key}, user_id={user_id}")
    return run


# =====================================================
# 流水线引擎（核心执行逻辑）
# =====================================================

class PipelineEngine:
    """
    流水线执行引擎

    负责调度和执行一个流水线实例的所有步骤。
    每个引擎实例对应一个 pipeline_run。
    """

    def __init__(
        self,
        run_id: int,
        progress_callback: Optional[ProgressCallback] = None,
    ):
        self.run_id = run_id
        self.progress_callback = progress_callback
        self._cancelled = False
        self._db: Optional[AsyncSession] = None
        self._run: Optional[PipelineRun] = None
        self._template: Optional[PipelineTemplate] = None
        self._style: Optional[StylePreset] = None
        # 分层风格元素组合（路径 B，与 style 互斥，优先级高于 style）
        self._style_elements = None
        self._script_template: Optional[ScriptTemplate] = None
        self._steps: Dict[str, PipelineStep] = {}  # step_key -> step

    # ---------- 公共入口 ----------

    async def start(self) -> None:
        """启动流水线（从 pending 状态开始执行）"""
        async with new_async_session() as db:
            self._db = db
            try:
                await self._load_run_data()

                # 积分预扣已在 run_service.create_and_start_run 中同步完成
                # （积分不足会立即抛 402，不会进入后台执行）
                # 这里不再重复预扣，避免双重扣费

                await self._set_run_status(STATUS_RUNNING)

                # 立即推送"流水线开始"事件，让前端知道已经启动
                self._emit_progress("pipeline_started", "", {
                    "run_id": self.run_id,
                    "status": STATUS_RUNNING,
                    "steps_count": len(self._steps),
                    "steps": [
                        {"key": k, "name": v.name, "status": v.status}
                        for k, v in self._steps.items()
                    ],
                })

                await self._execute_loop()
            except HTTPException as e:
                # HTTPException（如积分不足）也需要标记流水线失败，避免状态卡在 running
                error_msg = e.detail if isinstance(e.detail, str) else str(e.detail)
                logger.warning(f"流水线启动失败(HTTP {e.status_code}): run_id={self.run_id}, error={error_msg}")
                await self._fail_pipeline(error_msg)
                raise  # 继续抛出，让 API 层返回正确的 HTTP 错误码
            except Exception as e:
                logger.error(f"流水线执行异常: run_id={self.run_id}, error={e}", exc_info=True)
                await self._fail_pipeline(str(e))

    async def resume(self) -> None:
        """从断点恢复执行（失败后重试 / 人工审核后继续）"""
        async with new_async_session() as db:
            self._db = db
            try:
                await self._load_run_data()
                await self._set_run_status(STATUS_RUNNING)

                # 断点续跑前重置可执行的 SKIPPED 步骤
                # 场景：上游步骤之前失败导致下游被 skip，上游重试成功后，
                # 下游的 SKIPPED 状态应该被重置为 PENDING，让 _execute_loop 重新执行
                await self._reset_skipped_steps_with_satisfied_deps()

                # 推送恢复事件
                self._emit_progress("pipeline_started", "", {
                    "run_id": self.run_id,
                    "status": STATUS_RUNNING,
                    "resumed": True,
                    "steps_count": len(self._steps),
                })

                await self._execute_loop()
            except Exception as e:
                logger.error(f"流水线恢复执行异常: run_id={self.run_id}, error={e}", exc_info=True)
                await self._fail_pipeline(str(e))

    async def _reset_skipped_steps_with_satisfied_deps(self) -> None:
        """
        重置所有"上游依赖已全部成功"的 SKIPPED 步骤为 PENDING。

        场景：步骤 A 失败 → 步骤 B 被 _skip_blocked_steps 标记为 SKIPPED
              用户重试 A → A 成功变为 SUCCESS
              此时 B 仍然是 SKIPPED，但它的上游已经满足了，应该重置为 PENDING 让 _execute_loop 重新执行。
        """
        reset_count = 0
        for step_key, step in self._steps.items():
            if step.status != STATUS_SKIPPED:
                continue

            # 检查所有上游依赖是否都已成功
            depends_on = step.depends_on or []
            if not depends_on:
                continue

            all_deps_success = True
            for dep_key in depends_on:
                dep_step = self._steps.get(dep_key)
                if not dep_step or dep_step.status != STATUS_SUCCESS:
                    all_deps_success = False
                    break

            if all_deps_success:
                logger.info(
                    f"[流水线] 重置 SKIPPED 步骤为 PENDING（上游已全部成功）: "
                    f"{step_key}, 原因: {step.error_message}"
                )
                step.status = STATUS_PENDING
                step.error_message = None
                step.started_at = None
                step.finished_at = None
                reset_count += 1

        if reset_count > 0:
            await self._safe_commit()
            logger.info(f"[流水线] 共重置 {reset_count} 个 SKIPPED 步骤为 PENDING")

    async def cancel(self) -> None:
        """取消流水线"""
        self._cancelled = True
        # 取消操作使用独立 session 执行数据库更新，避免依赖运行中的 session
        async with new_async_session() as db:
            # 加载 run
            result = await db.execute(
                select(PipelineRun).filter(PipelineRun.id == self.run_id)
            )
            run = result.scalar_one_or_none()
            if not run:
                return
            # 修复：使用已定义的 STATUS_WAITING_REVIEW 常量（原 STATUS_WAITING_APPROVAL 未定义）
            if run.status in (STATUS_PENDING, STATUS_RUNNING, STATUS_WAITING_REVIEW):
                run.status = STATUS_CANCELLED
                run.finished_at = datetime.utcnow()
                await db.commit()
                # 退还 pipeline 级预扣积分
                # 修复：原代码使用了不存在的 run.precharged_credits 字段和错误的 refund_credits 调用签名（多传了 amount 参数）
                # 现直接调用 refund_credits 退还 ref_id=pipeline_run:{run_id} 的 pending 预扣流水
                if run.user_id:
                    try:
                        from app.services.credits_service import refund_credits
                        await refund_credits(
                            db,
                            run.user_id,
                            f"pipeline_run:{self.run_id}",
                            reason="流水线取消退款",
                        )
                    except Exception as e:
                        logger.warning(f"流水线取消退款失败: {e}")

    # ---------- 数据加载 ----------

    async def _load_run_data(self) -> None:
        """加载流水线运行时数据（run / template / steps / style / script_template）"""
        assert self._db is not None

        # 加载 run
        result = await self._db.execute(
            select(PipelineRun).filter(PipelineRun.id == self.run_id)
        )
        self._run = result.scalar_one_or_none()
        if not self._run:
            raise ValueError(f"流水线实例不存在: {self.run_id}")

        # 立即访问需要的属性，避免后续 rollback 后懒加载触发 greenlet 错误
        run_user_id = self._run.user_id
        run_inputs = self._run.inputs
        run_template_id = self._run.template_id

        # 加载 template
        self._template = await get_template_by_id(self._db, self._run.template_id)
        if not self._template:
            raise ValueError(f"流水线模板不存在: {self._run.template_id}")

        # 加载所有步骤
        steps_result = await self._db.execute(
            select(PipelineStep)
            .filter(PipelineStep.run_id == self.run_id)
            .order_by(PipelineStep.sort_order)
        )
        steps_list = steps_result.scalars().all()
        self._steps = {step.step_key: step for step in steps_list}

        # 立即访问每个步骤需要的属性，避免后续懒加载问题
        for step in self._steps.values():
            _ = step.step_key
            _ = step.name
            _ = step.status
            _ = step.step_type
            _ = step.depends_on
            _ = step.output_data
            _ = step.error_message
            _ = step.retry_count
            _ = step.max_retries

        # 加载风格预设（如果输入了 style_id）
        style_id = run_inputs.get("style_id")
        if style_id:
            self._style = await style_service.get_style_by_id(self._db, int(style_id))

        # 加载分层风格元素组合（如果输入了 style_elements）—— 路径 B
        # 与 style_id 互斥，优先级高于 style_id
        style_elements_input = run_inputs.get("style_elements") or []
        if style_elements_input:
            from app.services.style_element_service import resolve_elements
            self._style_elements = await resolve_elements(self._db, style_elements_input)
            # 路径 B 优先，清空路径 A
            self._style = None
        else:
            self._style_elements = None

        # 加载剧本模板（如果模板关联了）
        if self._template.script_template_id:
            self._script_template = await script_template_service.get_script_template_by_id(
                self._db, self._template.script_template_id
            )

        logger.info(
            f"加载流水线数据: run_id={self.run_id}, "
            f"steps={len(self._steps)}, "
            f"status={self._run.status}"
        )

    # ---------- 主执行循环 ----------

    async def _execute_loop(self) -> None:
        """
        主执行循环：DAG 调度（串行执行，避免 AsyncSession 并发事务冲突）

        算法:
        1. 先标记所有依赖已失败的步骤为 SKIPPED
        2. 找出所有依赖已满足且状态为 pending 的步骤
        3. 串行执行这些步骤（一个完成后再执行下一个，保证 session 安全）
        4. 重复 1-3 直到没有可执行步骤或所有步骤完成

        注：步骤内部的 HTTP 请求（图片/视频生成）本身是异步非阻塞的，
            串行不会影响吞吐量；且步骤间有依赖关系，真正可并行的步骤很少。
        """
        while not self._cancelled:
            # 检查暂停标志：如果在运行中用户请求暂停，保存状态并优雅退出
            await self._check_pause_request()

            # 先标记所有"依赖链已断裂"的步骤为 SKIPPED（上游失败了，下游无需执行）
            await self._skip_blocked_steps()

            ready_steps = self._get_ready_steps()

            if not ready_steps:
                # 没有可执行步骤了，检查是否全部完成
                all_done = all(
                    step.status in (STATUS_SUCCESS, STATUS_SKIPPED, STATUS_FAILED)
                    for step in self._steps.values()
                )
                if all_done:
                    # 检查是否有失败的
                    any_failed = any(
                        step.status == STATUS_FAILED
                        for step in self._steps.values()
                    )
                    if any_failed:
                        await self._fail_pipeline("有步骤执行失败")
                    else:
                        await self._complete_pipeline()
                break

            # 串行执行就绪步骤（一个接一个，避免 AsyncSession 并发 commit 冲突）
            for step_key in ready_steps:
                if self._cancelled:
                    break
                try:
                    await self._execute_step(step_key)
                except Exception as e:
                    logger.error(f"步骤执行异常（未捕获）: {step_key}, error={e}", exc_info=True)
                    # _execute_step 内部应该已经处理失败并标记状态，这里作为兜底
                    try:
                        await self._fail_step(step_key, str(e))
                    except Exception:
                        pass

            # 检查是否被取消
            if self._cancelled:
                await self._set_run_status(STATUS_CANCELLED)
                break

    # ---------- 暂停检查 ----------

    async def _check_pause_request(self) -> None:
        """
        检查数据库中 pause_requested 标志。
        如果为 True，将 run 状态置为 paused，退出执行循环。
        步骤保持当前状态，后续 resume 可继续执行。
        """
        if not self._db:
            return
        try:
            result = await self._db.execute(
                select(PipelineRun.pause_requested).filter(PipelineRun.id == self.run_id)
            )
            pause_requested = result.scalar_one_or_none()
            if pause_requested:
                logger.info(f"[流水线] 收到暂停请求: run_id={self.run_id}")
                # 清除标志位，将状态设为 paused
                await self._db.execute(
                    sa_update(PipelineRun)
                    .where(PipelineRun.id == self.run_id)
                    .values(
                        status="paused",
                        pause_requested=False,
                    )
                )
                self._run.status = "paused"
                await self._safe_commit()
                self._cancelled = True
                self._emit_progress("pipeline_paused", "", {
                    "run_id": self.run_id,
                    "status": "paused",
                    "message": "流水线已暂停，可编辑参数后继续",
                })
        except Exception as e:
            logger.warning(f"[流水线] 暂停检查异常: {e}")

    def _get_ready_steps(self) -> List[str]:
        """获取所有依赖已满足、状态为 pending、条件为真的步骤 key 列表

        可选依赖（optional_depends_on）的上游即使 failed/skipped 也不阻止下游就绪。
        """
        ready = []
        for step_key, step in self._steps.items():
            if step.status != STATUS_PENDING:
                continue

            step_config = self._get_step_config(step_key) or {}
            optional_deps = set(step_config.get("optional_depends_on", []) or [])

            # 检查所有非可选依赖是否都成功完成
            depends_on = step.depends_on or []
            all_deps_satisfied = True
            for dep_key in depends_on:
                dep_step = self._steps.get(dep_key)
                if not dep_step:
                    continue
                if dep_key in optional_deps:
                    # 可选依赖：可以处于任何终态（success/failed/skipped），不阻塞
                    continue
                if dep_step.status != STATUS_SUCCESS:
                    all_deps_satisfied = False
                    break

            if not all_deps_satisfied:
                continue

            # 检查条件是否满足
            if step_config:
                condition = step_config.get("condition")
                if condition and not self._evaluate_condition(condition):
                    # 条件不满足，跳过此步骤
                    logger.info(f"[流水线] 步骤条件不满足，跳过: {step_key}, condition={condition}")
                    continue

            ready.append(step_key)

        return ready

    async def _skip_blocked_steps(self) -> None:
        """
        将所有因上游失败/跳过而无法执行的 pending 步骤标记为 SKIPPED。
        需要循环处理，因为依赖链可能有多级（A失败→B跳过→C也跳过）。

        可选依赖（optional_depends_on）：上游 skipped/failed 时不阻塞下游。
        """
        changed = True
        while changed:
            changed = False
            for step_key, step in self._steps.items():
                if step.status != STATUS_PENDING:
                    continue

                step_config = self._get_step_config(step_key) or {}
                optional_deps = set(step_config.get("optional_depends_on", []) or [])

                depends_on = step.depends_on or []
                for dep_key in depends_on:
                    dep_step = self._steps.get(dep_key)
                    if dep_step and dep_step.status in (STATUS_FAILED, STATUS_SKIPPED):
                        # 可选依赖：上游失败/跳过不阻塞
                        if dep_key in optional_deps:
                            logger.info(
                                f"[流水线] 可选依赖 {dep_key} 状态为 {dep_step.status}，"
                                f"不阻塞步骤: {step_key}"
                            )
                            continue
                        # 非可选依赖：上游失败则跳过
                        logger.info(f"[流水线] 上游步骤 {dep_key} 状态为 {dep_step.status}，跳过步骤: {step_key}")
                        step.status = STATUS_SKIPPED
                        step.error_message = f"上游步骤 {dep_key} 未成功完成"
                        step.finished_at = datetime.utcnow()
                        changed = True
                        self._emit_progress("step_skipped", step_key, {
                            "name": step.name,
                            "reason": f"上游步骤 {dep_step.name} 未成功",
                        })
                        break
        # 统一提交跳过状态
        if self._db:
            await self._safe_commit()

    def _evaluate_condition(self, condition: str) -> bool:
        """
        评估条件表达式。

        支持的格式：
        - inputs.xxx === true/false
        - inputs.xxx === "value"
        - inputs.xxx > num
        - inputs.xxx < num

        示例：
        - "inputs.generate_video === true"  # 检查用户是否选择生成视频
        - "inputs.quality === 'high'"  # 检查质量设置
        """
        if not condition:
            return True

        condition = condition.strip()

        # 解析 === 比较
        if "===" in condition:
            parts = condition.split("===")
            if len(parts) == 2:
                left = parts[0].strip()
                right = parts[1].strip()

                # 获取左值
                value = self._get_nested_value(left)

                # 解析右值类型
                if right == "true":
                    expected = True
                elif right == "false":
                    expected = False
                elif right.startswith("'") and right.endswith("'"):
                    expected = right[1:-1]
                elif right.startswith('"') and right.endswith('"'):
                    expected = right[1:-1]
                elif right.isdigit():
                    expected = int(right)
                else:
                    try:
                        expected = float(right)
                    except ValueError:
                        expected = right

                return value == expected

        # 解析 > 比较
        if " > " in condition:
            parts = condition.split(" > ")
            if len(parts) == 2:
                left = parts[0].strip()
                right = parts[1].strip()
                value = self._get_nested_value(left)
                try:
                    threshold = float(right) if "." in right else int(right)
                    return value > threshold
                except (ValueError, TypeError):
                    return False

        # 解析 < 比较
        if " < " in condition:
            parts = condition.split(" < ")
            if len(parts) == 2:
                left = parts[0].strip()
                right = parts[1].strip()
                value = self._get_nested_value(left)
                try:
                    threshold = float(right) if "." in right else int(right)
                    return value < threshold
                except (ValueError, TypeError):
                    return False

        # 不支持的表达式
        logger.warning(f"[流水线] 不支持的条件表达式: {condition}")
        return False

    def _get_nested_value(self, path: str):
        """
        从 inputs 中获取嵌套值。

        支持的路径格式：
        - inputs.xxx
        - steps.xxx.output.yyy
        """
        parts = path.split(".")
        if not parts:
            return None

        # 移除第一层（inputs 或 steps）
        if parts[0] == "inputs":
            data = self._run.inputs if self._run else {}
            parts = parts[1:]
        elif parts[0] == "steps":
            # steps.xxx.output.yyy 格式
            data = {}
            parts = parts[1:]
        else:
            data = self._run.inputs if self._run else {}

        # 遍历剩余路径
        current = data
        for part in parts:
            if isinstance(current, dict):
                current = current.get(part)
            else:
                return None

        return current

    # ---------- 单步骤执行 ----------

    async def _execute_step(self, step_key: str) -> None:
        """执行单个步骤"""
        step = self._steps.get(step_key)
        if not step:
            return

        step_config = self._get_step_config(step_key)
        if not step_config:
            await self._fail_step(step_key, f"找不到步骤配置: {step_key}")
            return

        # 更新状态为 running
        await self._set_step_status(step_key, STATUS_RUNNING)
        self._emit_progress("step_started", step_key, {
            "name": step.name,
            "step_type": step.step_type,
        })

        # 构建执行上下文
        context = StepExecutionContext(
            inputs=self._run.inputs if self._run else {},
            steps_output={
                k: v.output_data for k, v in self._steps.items()
            },
            style=self._style,
            script_template=self._script_template,
            user_id=self._run.user_id if self._run else None,
            run_id=self.run_id,
            extra={
                "step_config": step_config,
            },
            style_elements=self._style_elements,
        )

        executor = None
        step_credits = 0
        actual_credits = 0
        progress_task = None
        try:
            # 创建执行器
            executor = create_step_executor(step_config, context)

            # 验证输入
            await executor.validate()

            # 预估本步骤积分
            step_credits = await executor.estimate_credits()

            # 启动步骤进度轮询（后台任务，每 2s 推送 step_progress 事件到前端）
            progress_task = asyncio.create_task(
                self._poll_step_progress(step_key, executor)
            )

            # 执行
            output_data = await executor.execute()

            # 校验执行结果：如果预期有任务但全部失败，标记步骤失败
            total = output_data.get("total", 0)
            success_count = output_data.get("success_count", len(output_data.get("images", [])) + len(output_data.get("videos", [])))
            failed_count = output_data.get("failed_count", 0)

            if total > 0 and success_count == 0:
                # 有任务但全部失败了，步骤应该标记为失败
                failed_items = (
                    output_data.get("failed_audios")
                    or output_data.get("failed_images")
                    or output_data.get("failed_videos")
                    or []
                )
                # 按 error_type 分类统计
                error_types: dict = {}
                for item in failed_items:
                    et = item.get("error_type", "unknown")
                    error_types[et] = error_types.get(et, 0) + 1

                first_error = failed_items[0].get("error", "未知错误") if failed_items else ""
                if error_types:
                    type_summary = ", ".join(f"{k}: {v}" for k, v in error_types.items())
                    error_msg = (
                        f"全部 {total} 个任务失败（错误类型分布: {type_summary}）。"
                        f"首个错误: {first_error}"
                    )
                else:
                    error_msg = f"全部 {total} 个任务失败。首个错误: {first_error}" if first_error else f"全部 {total} 个任务失败"
                raise RuntimeError(error_msg)

            # 按实际成功数量计算积分（图片每张10，视频每个30）
            if "images" in output_data:
                actual_credits = len(output_data.get("images", [])) * 10
            elif "videos" in output_data:
                actual_credits = len(output_data.get("videos", [])) * 30
            else:
                actual_credits = step_credits if success_count > 0 or total == 0 else 0

            # 成功：保存输出，更新状态（同一事务提交步骤状态 + 累计积分）
            await self._complete_step(step_key, output_data, actual_credits)

            # 确认积分（独立 session，不影响 pipeline 状态）
            if actual_credits > 0:
                await self._confirm_step_credits(step_key, actual_credits)

            self._emit_progress("step_completed", step_key, {
                "name": step.name,
                "output_summary": self._summarize_output(output_data),
                "credits_consumed": actual_credits,
                # 推送完整 output_data，让前端 StepResultGallery 能立即渲染产物
                # 包含 images/videos/parsed_result 等字段
                "output": output_data,
            })

        except Exception as e:
            error_msg = str(e)
            logger.error(f"步骤执行失败: {step_key}, error={error_msg}", exc_info=True)

            # 退还本步骤预扣的积分（独立 session）
            await self._refund_step_credits(step_key, step.credits_consumed or step_credits or 0)

            # 重试逻辑
            if step.retry_count < step.max_retries:
                # 先确保事务干净
                try:
                    if self._db:
                        await self._db.rollback()
                except Exception:
                    pass
                step.retry_count += 1
                step.error_message = error_msg
                step.status = STATUS_PENDING  # 重置为 pending 等待下一轮执行
                await self._safe_commit()
                logger.info(f"步骤将重试: {step_key}, 第 {step.retry_count}/{step.max_retries} 次")
            else:
                await self._fail_step(step_key, error_msg)
                self._emit_progress("step_failed", step_key, {
                    "name": step.name,
                    "error": error_msg,
                    "retryable": False,
                })
        finally:
            # 停止进度轮询
            if progress_task and not progress_task.done():
                progress_task.cancel()
                try:
                    await progress_task
                except asyncio.CancelledError:
                    pass
            if executor:
                try:
                    await executor.cleanup()
                except Exception:
                    pass

    def _get_step_config(self, step_key: str) -> Optional[Dict[str, Any]]:
        """从模板配置中获取指定步骤的配置"""
        if not self._template:
            return None
        for step_cfg in self._template.steps_config:
            if step_cfg.get("key") == step_key:
                return step_cfg
        return None

    def _summarize_output(self, output_data: Dict[str, Any]) -> Dict[str, Any]:
        """生成输出摘要（用于进度推送，避免传大量数据）"""
        summary = {}
        if "images" in output_data:
            summary["image_count"] = len(output_data["images"])
        if "videos" in output_data:
            summary["video_count"] = len(output_data["videos"])
        if "parsed_result" in output_data:
            summary["has_parsed_result"] = True
        return summary

    # ---------- 事务安全辅助方法 ----------

    async def _safe_commit(self) -> bool:
        """
        安全提交数据库事务。
        - 成功返回 True
        - 失败时尝试 rollback，返回 False
        """
        if not self._db:
            return False
        try:
            await self._db.commit()
            return True
        except Exception as e:
            logger.warning(f"数据库 commit 失败，尝试 rollback: {e}")
            try:
                await self._db.rollback()
            except Exception as rb_err:
                logger.warning(f"rollback 也失败（事务可能已关闭）: {rb_err}")
            return False

    async def _safe_refresh(self, obj) -> None:
        """安全刷新对象，忽略事务关闭错误"""
        if not self._db or not obj:
            return
        try:
            await self._db.refresh(obj)
        except Exception as e:
            logger.debug(f"refresh 对象失败（可忽略）: {e}")

    # ---------- 积分管理（使用独立 session，避免事务冲突）----------

    async def _precharge_credits(self) -> None:
        """预扣流水线总积分（使用独立 session）"""
        if not self._run or not self._template:
            return
        # 匿名用户不需要预扣
        if not self._run.user_id:
            return

        # 计算总预估积分
        total_credits = self._template.estimated_credits or 200
        if total_credits <= 0:
            return

        # 使用独立的 session 处理积分操作，避免和 pipeline 状态操作共享事务
        async with new_async_session() as db:
            try:
                # 获取用户对象
                from app.models.user import User
                result = await db.execute(
                    select(User).filter(User.id == self._run.user_id)
                )
                user = result.scalar_one_or_none()
                if not user:
                    return

                # ref_id 格式: pipeline_run:{run_id}
                ref_id = f"pipeline_run:{self.run_id}"
                description = f"流水线预扣: {self._template.name} (run_id={self.run_id})"

                # 预扣积分（credits_service 内部会自己 commit）
                await credits_service.consume_credits(
                    db,
                    user,
                    total_credits,
                    description,
                    ref_type="pipeline_run",
                    ref_id=ref_id,
                )
                logger.info(f"[积分预扣] run_id={self.run_id} user_id={self._run.user_id} amount={total_credits}")
            except HTTPException:
                # 积分不足，抛出让上层处理
                raise
            except Exception as e:
                logger.warning(f"[积分预扣] 失败 run_id={self.run_id}: {e}")
                # 积分预扣失败不阻止流水线执行

    async def _refund_remaining_credits(self, reason: str) -> None:
        """退还流水线剩余未消耗的积分（使用独立 session）"""
        if not self._run or not self._template:
            return
        if not self._run.user_id:
            return

        # 计算已消耗的积分
        total_consumed = self._run.total_credits or 0
        # 预估总积分
        estimated_total = self._template.estimated_credits or 200
        # 剩余可退还的积分
        remaining = max(0, estimated_total - total_consumed)

        if remaining <= 0:
            return

        # 使用独立的 session 处理积分操作
        async with new_async_session() as db:
            try:
                ref_id = f"pipeline_run:{self.run_id}"
                await credits_service.refund_credits(
                    db,
                    self._run.user_id,
                    ref_id,
                    reason=reason,
                )
                logger.info(f"[积分退还] run_id={self.run_id} user_id={self._run.user_id} amount={remaining} reason={reason}")
            except Exception as e:
                logger.warning(f"[积分退还] 失败 run_id={self.run_id}: {e}")

    async def _confirm_step_credits(self, step_key: str, amount: int) -> None:
        """确认步骤积分消耗（预扣流水改为 confirmed，使用独立 session）"""
        if not self._run or amount <= 0:
            return
        # 使用独立的 session 处理积分操作
        async with new_async_session() as db:
            try:
                # ref_id 格式: pipeline_run:{run_id}:step:{step_key}
                ref_id = f"pipeline_run:{self.run_id}:step:{step_key}"
                await credits_service.confirm_credits(db, self._run.user_id, ref_id)
                logger.info(f"[积分确认] step={step_key} amount={amount}")
            except Exception as e:
                logger.warning(f"[积分确认] 失败 step={step_key}: {e}")

    async def _refund_step_credits(self, step_key: str, amount: int) -> None:
        """退还步骤积分（使用独立 session）"""
        if not self._run or amount <= 0:
            return
        # 使用独立的 session 处理积分操作
        async with new_async_session() as db:
            try:
                ref_id = f"pipeline_run:{self.run_id}:step:{step_key}"
                reason = f"流水线步骤失败退款: {step_key}"
                await credits_service.refund_credits(db, self._run.user_id, ref_id, reason)
                logger.info(f"[积分退还] step={step_key} amount={amount}")
            except Exception as e:
                logger.warning(f"[积分退还] 失败 step={step_key}: {e}")

    # ---------- 状态更新 ----------

    async def _set_run_status(self, status: str) -> None:
        """更新流水线状态"""
        if not self._run or not self._db:
            return

        self._run.status = status
        if status in (STATUS_RUNNING,) and not self._run.started_at:
            self._run.started_at = datetime.utcnow()
        if status in (STATUS_SUCCESS, STATUS_FAILED, STATUS_CANCELLED):
            self._run.finished_at = datetime.utcnow()
        await self._safe_commit()
        await self._safe_refresh(self._run)

    async def _set_step_status(self, step_key: str, status: str) -> None:
        """更新步骤状态"""
        step = self._steps.get(step_key)
        if not step or not self._db:
            return

        step.status = status
        if status == STATUS_RUNNING and not step.started_at:
            step.started_at = datetime.utcnow()
        if status in (STATUS_SUCCESS, STATUS_FAILED, STATUS_SKIPPED):
            step.finished_at = datetime.utcnow()
        await self._safe_commit()

    async def _complete_step(self, step_key: str, output_data: Dict[str, Any], step_credits: int = 0) -> None:
        """
        标记步骤成功（原子操作：步骤状态 + 流水线累计积分在同一事务中提交）
        """
        step = self._steps.get(step_key)
        if not step or not self._db:
            return

        # 更新步骤状态
        step.output_data = output_data
        step.status = STATUS_SUCCESS
        step.finished_at = datetime.utcnow()
        step.credits_consumed = step_credits

        # 更新流水线累计积分和当前步骤指针
        if self._run:
            self._run.total_credits = (self._run.total_credits or 0) + step_credits
            self._run.current_step_key = step_key

        await self._safe_commit()

    async def _fail_step(self, step_key: str, error_msg: str) -> None:
        """标记步骤失败"""
        step = self._steps.get(step_key)
        if not step or not self._db:
            return

        step.status = STATUS_FAILED
        step.error_message = error_msg
        step.finished_at = datetime.utcnow()
        await self._safe_commit()

    async def _complete_pipeline(self) -> None:
        """标记流水线完成"""
        if not self._run:
            return

        # 构建输出摘要
        output_summary = self._build_output_summary()
        self._run.output_summary = output_summary

        await self._set_run_status(STATUS_SUCCESS)
        self._emit_progress("pipeline_completed", "", {
            "status": STATUS_SUCCESS,
            "output_summary": output_summary,
        })
        logger.info(f"流水线执行完成: run_id={self.run_id}")

    async def _fail_pipeline(self, error_msg: str) -> None:
        """标记流水线失败"""
        if not self._run:
            return
        self._run.error_message = error_msg
        await self._set_run_status(STATUS_FAILED)
        # 退还剩余未消耗的积分
        await self._refund_remaining_credits(reason=f"流水线失败退款: {error_msg[:50]}")
        self._emit_progress("pipeline_completed", "", {
            "status": STATUS_FAILED,
            "error": error_msg,
        })
        logger.error(f"流水线执行失败: run_id={self.run_id}, error={error_msg}")

    def _build_output_summary(self) -> Dict[str, Any]:
        """构建流水线输出摘要"""
        summary: Dict[str, Any] = {
            "total_steps": len(self._steps),
            "completed_steps": sum(
                1 for s in self._steps.values() if s.status == STATUS_SUCCESS
            ),
        }

        # 收集主要输出
        for step_key, step in self._steps.items():
            if step.status != STATUS_SUCCESS:
                continue
            out = step.output_data or {}
            if "images" in out:
                summary[f"{step_key}_images"] = len(out["images"])
            if "videos" in out:
                summary[f"{step_key}_videos"] = len(out["videos"])
            if "final_video_url" in out:
                summary["final_video_url"] = out["final_video_url"]

        return summary

    # ---------- 进度推送 ----------

    def _emit_progress(self, event_type: str, step_key: str, data: Dict[str, Any]) -> None:
        """发送进度回调"""
        if self.progress_callback:
            try:
                self.progress_callback(event_type, step_key, data)
            except Exception as e:
                logger.warning(f"进度回调异常: {e}")

    async def _poll_step_progress(self, step_key: str, executor) -> None:
        """
        后台循环轮询执行器进度，通过 SSE 推送给前端。

        每 2 秒调用 executor.get_progress()，有数据则 emit step_progress 事件。
        由 _execute_step 创建并在 finally 中取消。
        """
        try:
            while True:
                await asyncio.sleep(2)
                try:
                    progress_info = await executor.get_progress()
                    if progress_info:
                        step = self._steps.get(step_key)
                        if step and step.status == STATUS_RUNNING:
                            self._emit_progress("step_progress", step_key, {
                                "name": step.name,
                                "progress": progress_info,
                            })
                except Exception as e:
                    logger.debug(f"步骤进度轮询异常: {e}")
        except asyncio.CancelledError:
            pass

    async def _emit_step_progress(self, step_key: str) -> None:
        """
        推送步骤执行中的进度事件（step_progress）。

        从执行器的 get_progress() 获取进度信息，通过 SSE 推送给前端。
        """
        try:
            step = self._steps.get(step_key)
            if not step or step.status != STATUS_RUNNING:
                return

            step_config = self._get_step_config(step_key)
            if not step_config:
                return

            # 创建执行器以获取进度
            from app.services.pipeline.steps import create_step_executor
            context = self._build_context()
            executor = create_step_executor(step_config, context)
            progress_info = await executor.get_progress()

            if progress_info:
                self._emit_progress("step_progress", step_key, {
                    "name": step.name,
                    "progress": progress_info,
                })
        except Exception as e:
            logger.debug(f"获取步骤进度失败: {step_key}, error={e}")

    def _build_context(self) -> "StepExecutionContext":
        """构建步骤执行上下文（供进度查询等场景复用）"""
        from app.services.pipeline.steps.base import StepExecutionContext
        return StepExecutionContext(
            inputs=self._run.inputs if self._run else {},
            steps_output={
                k: v.output_data for k, v in self._steps.items()
            },
            style=self._style,
            script_template=self._script_template,
            user_id=self._run.user_id if self._run else None,
            run_id=self.run_id,
            style_elements=self._style_elements,
        )


# =====================================================
# 便捷函数（外部调用入口）
# =====================================================

async def start_pipeline(
    run_id: int,
    progress_callback: Optional[ProgressCallback] = None,
) -> None:
    """
    后台启动一个流水线（异步任务，不阻塞当前请求）。

    使用 asyncio.create_task 在后台运行。
    """
    engine = PipelineEngine(run_id, progress_callback)
    asyncio.create_task(engine.start())
    logger.info(f"已在后台启动流水线: run_id={run_id}")


async def resume_pipeline(
    run_id: int,
    progress_callback: Optional[ProgressCallback] = None,
) -> None:
    """从断点恢复执行流水线"""
    engine = PipelineEngine(run_id, progress_callback)
    asyncio.create_task(engine.resume())
    logger.info(f"已在后台恢复流水线: run_id={run_id}")


def _collect_transitive_dependents(all_steps: List[PipelineStep], root_key: str) -> set:
    """收集 root_key 的所有传递性下游步骤 key（直接 + 间接依赖链）。"""
    key_to_deps: Dict[str, List[str]] = {}
    for s in all_steps:
        key_to_deps[s.step_key] = s.depends_on or []

    result: set = set()
    queue = [root_key]
    while queue:
        current = queue.pop(0)
        for s in all_steps:
            if s.step_key in result or s.step_key == root_key:
                continue
            if current in (s.depends_on or []):
                result.add(s.step_key)
                queue.append(s.step_key)
    return result


async def cancel_pipeline(run_id: int, user_id: Optional[int] = None) -> None:
    """取消流水线执行"""
    db = new_async_session()
    try:
        result = await db.execute(
            select(PipelineRun).filter(PipelineRun.id == run_id)
        )
        run = result.scalar_one_or_none()
        if not run:
            raise HTTPException(status_code=404, detail="流水线不存在")

        if user_id is not None and run.user_id != user_id:
            # 检查是否是管理员（这里简单处理，实际应结合权限系统）
            pass

        if run.status in (STATUS_RUNNING, STATUS_PENDING):
            run.status = STATUS_CANCELLED
            run.finished_at = datetime.utcnow()
            await db.commit()
            logger.info(f"流水线已取消: run_id={run_id}")
    finally:
        await db.close()


async def retry_pipeline_step(
    run_id: int,
    step_key: str,
    user_id: Optional[int] = None,
    progress_callback: Optional[ProgressCallback] = None,
) -> None:
    """
    重试流水线中失败/被跳过/已成功的单个步骤。

    - failed/skipped：重置该步骤为 PENDING，级联重置其 SKIPPED 下游
    - success：重置该步骤为 PENDING，级联重置**所有**下游步骤（含 success/failed/skipped）
      因为重新执行成功步骤会改变其输出，下游结果随之失效。

    重试后自动启动 resume 继续执行。
    """
    db = new_async_session()
    try:
        # 检查流水线存在且属于该用户
        result = await db.execute(
            select(PipelineRun).filter(PipelineRun.id == run_id)
        )
        run = result.scalar_one_or_none()
        if not run:
            raise HTTPException(status_code=404, detail="流水线不存在")

        if user_id is not None and run.user_id != user_id:
            raise HTTPException(status_code=403, detail="无权操作此流水线")

        # 检查步骤存在且状态为 failed / skipped / success
        step_result = await db.execute(
            select(PipelineStep)
            .filter(PipelineStep.run_id == run_id)
            .filter(PipelineStep.step_key == step_key)
        )
        step = step_result.scalar_one_or_none()
        if not step:
            raise HTTPException(status_code=404, detail=f"步骤不存在: {step_key}")

        if step.status not in (STATUS_FAILED, STATUS_SKIPPED, STATUS_SUCCESS):
            raise HTTPException(
                status_code=400,
                detail=f"只能重试失败/被跳过/已完成的步骤，当前状态: {step.status}"
            )

        is_retry_success = (step.status == STATUS_SUCCESS)

        # 重置目标步骤为 pending
        step.status = STATUS_PENDING
        step.error_message = None
        step.output_data = {} if is_retry_success else step.output_data
        step.retry_count = 0  # 重置重试计数

        # 级联重置下游步骤
        all_steps_result = await db.execute(
            select(PipelineStep)
            .filter(PipelineStep.run_id == run_id)
        )
        all_steps = all_steps_result.scalars().all()
        reset_downstream = []

        if is_retry_success:
            # 重试 success 步骤 → 级联重置**所有**直接和间接依赖它的下游步骤
            # 下游可能有 success / failed / skipped 等状态，全部重置
            all_deps = _collect_transitive_dependents(all_steps, step_key)
            for s in all_steps:
                if s.step_key in all_deps and s.step_key != step_key:
                    s.status = STATUS_PENDING
                    s.error_message = None
                    s.output_data = {}
                    s.started_at = None
                    s.finished_at = None
                    s.retry_count = 0
                    reset_downstream.append(s.step_key)
        else:
            # 重试 failed/skipped 步骤 → 仅级联重置下游 SKIPPED 步骤
            for s in all_steps:
                if s.step_key == step_key or s.status != STATUS_SKIPPED:
                    continue
                depends_on = s.depends_on or []
                if step_key in depends_on:
                    s.status = STATUS_PENDING
                    s.error_message = None
                    s.started_at = None
                    s.finished_at = None
                    reset_downstream.append(s.step_key)

        await db.commit()

        if reset_downstream:
            logger.info(
                f"[流水线] 重试步骤 {step_key}"
                f"{'（成功步骤重跑，级联重置所有下游）' if is_retry_success else ''}"
                f"，重置下游步骤: {reset_downstream}"
            )

        # 启动流水线执行（resume 会自动重置其他可执行的 SKIPPED 步骤）
        engine = PipelineEngine(run_id, progress_callback)
        asyncio.create_task(engine.resume())
        logger.info(f"已在后台重试步骤: run_id={run_id}, step_key={step_key}")
    finally:
        await db.close()
