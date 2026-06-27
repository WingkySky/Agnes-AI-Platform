# =====================================================
# 批量视频生成步骤执行器
# 用于一次性生成多个视频（如分镜视频、场景视频等）
# 支持从图片生成视频，也支持文生视频
# =====================================================

import asyncio
import logging
from typing import Dict, Any, List, Optional

from app.core.database import new_async_session
from app.services.pipeline.steps import register_step_executor
from app.services.pipeline.steps.base import BaseStepExecutor
from app.services.agnes_client import agnes_client
from app.services import style_service
from app.services.pipeline import integration

logger = logging.getLogger("agnes_platform.pipeline")


@register_step_executor
class VideoBatchExecutor(BaseStepExecutor):
    """
    批量视频生成步骤执行器

    可以:
    - 从上游图片生成步骤输出中获取图片，批量生成视频
    - 从剧本分镜中提取提示词，文生视频
    - 控制并发度，避免触发限流
    - 自动轮询直到所有视频生成完成
    """

    step_type = "video_batch"

    async def validate(self) -> None:
        """验证输入"""
        config = self.config.get("config", {})
        source = config.get("source", "image_step")

        if source == "image_step":
            if not config.get("from_step"):
                raise ValueError("source=image_step 时必须指定 from_step")
        elif source == "parsed_result":
            if not config.get("from_step"):
                raise ValueError("source=parsed_result 时必须指定 from_step")
        elif source == "input_list":
            pass
        else:
            raise ValueError(f"不支持的视频来源: {source}")

    async def execute(self) -> Dict[str, Any]:
        """执行批量视频生成"""
        config = self.config.get("config", {})

        # 1. 构建视频生成任务列表
        video_tasks = self._build_video_tasks()

        if not video_tasks:
            logger.warning(f"[视频批量] 没有生成任务: step_key={self.step_key}")
            return {"videos": [], "total": 0, "failed": 0}

        logger.info(f"[视频批量] 开始生成 {len(video_tasks)} 个视频: step_key={self.step_key}")

        # 2. 第一阶段：批量创建视频任务
        self._progress_phase = "creating"
        self._created_count = 0
        max_concurrent = config.get("max_concurrent", 3)
        task_results = await self._create_videos_concurrent(
            video_tasks, max_concurrent
        )
        self._created_count = len([t for t in task_results if t.get("task_id") or t.get("video_id")])

        # 3. 第二阶段：轮询等待所有任务完成
        created_tasks = [t for t in task_results if t.get("task_id") or t.get("video_id")]
        failed_create = [t for t in task_results if not (t.get("task_id") or t.get("video_id"))]

        if created_tasks:
            logger.info(f"[视频批量] 已创建 {len(created_tasks)} 个任务，开始轮询...")
            self._progress_phase = "polling"
            self._completed_count = 0
            completed = await self._poll_all_videos(created_tasks, config)
        else:
            completed = []

        # 4. 合并结果
        all_results = completed + [
            {
                **t,
                "success": False,
                "error": t.get("error", "创建任务失败"),
            }
            for t in failed_create
        ]

        # 按 index 排序
        all_results.sort(key=lambda x: x.get("index", 0))

        success_videos = [r for r in all_results if r.get("success")]
        failed_videos = [r for r in all_results if not r.get("success")]

        logger.info(
            f"[视频批量] 完成: 成功 {len(success_videos)}/{len(all_results)}, "
            f"失败 {len(failed_videos)}"
        )

        # 5. 保存生成记录到 generations 表
        if success_videos and self.context.run_id:
            try:
                async with new_async_session() as db:
                    gen_ids = await integration.save_batch_generations(
                        db=db,
                        run_id=self.context.run_id,
                        step_key=self.step_key,
                        items=success_videos,
                        gen_type="video",
                        user_id=self.context.user_id,
                    )
                    logger.info(f"[视频批量] 已保存 {len(gen_ids)} 条生成记录: step_key={self.step_key}")
            except Exception as e:
                logger.warning(f"[视频批量] 保存生成记录失败: {e}")

        return {
            "videos": success_videos,
            "failed_videos": failed_videos,
            "total": len(all_results),
            "success_count": len(success_videos),
            "failed_count": len(failed_videos),
        }

    async def estimate_credits(self) -> int:
        """预估积分消耗"""
        config = self.config.get("config", {})
        estimated_count = config.get("estimated_count", 8)
        return estimated_count * 30  # 每个视频约 30 积分

    async def get_progress(self) -> Dict[str, Any]:
        """
        获取当前执行进度。

        视频生成有两阶段：创建任务 + 轮询完成。
        返回: {"current": int, "total": int, "percent": float, "phase": str}
        """
        total = getattr(self, "_total_videos", 0)
        if total == 0:
            return {}

        phase = getattr(self, "_progress_phase", "creating")
        created = getattr(self, "_created_count", 0)
        completed = getattr(self, "_completed_count", 0)

        if phase == "creating":
            # 第一阶段：创建任务（约占 30% 进度）
            percent = round(created / total * 0.3, 3) if total > 0 else 0
            return {
                "current": created,
                "total": total,
                "percent": percent,
                "phase": "creating",
                "phase_text": "创建视频任务中",
            }
        elif phase == "polling":
            # 第二阶段：轮询完成（约占 70% 进度）
            percent = round(0.3 + completed / total * 0.7, 3) if total > 0 else 0
            return {
                "current": completed,
                "total": total,
                "percent": percent,
                "phase": "polling",
                "phase_text": "视频生成中",
            }
        else:
            return {}

    # ---------- 内部方法 ----------

    def _build_video_tasks(self) -> List[Dict[str, Any]]:
        """构建视频生成任务列表"""
        config = self.config.get("config", {})
        source = config.get("source", "image_step")

        if source == "image_step":
            tasks = self._build_tasks_from_image_step(config)
        elif source == "parsed_result":
            tasks = self._build_tasks_from_parsed_result(config)
        elif source == "input_list":
            tasks = self._build_tasks_from_input(config)
        else:
            tasks = []

        # 缓存任务总数供进度查询
        self._total_videos = len(tasks)
        return tasks

    def _build_tasks_from_image_step(self, config: Dict[str, Any]) -> List[Dict[str, Any]]:
        """从上游图片步骤输出中构建视频任务"""
        from_step_key = config.get("from_step", "")

        step_output = self.context.steps_output.get(from_step_key, {})
        images = step_output.get("images", [])

        tasks = []
        for idx, img_data in enumerate(images):
            image_url = img_data.get("image_url", "")
            if not image_url:
                continue

            # 从图片数据中提取提示词
            prompt = ""
            scene_data = img_data.get("scene_data")
            if scene_data:
                prompt = scene_data.get("video_prompt") or scene_data.get("description") or ""

            if not prompt:
                prompt = img_data.get("prompt", "")

            tasks.append({
                "index": idx,
                "image_url": image_url,
                "prompt": prompt,
                # Agnes Video API 使用 "image2video" 模式
                "mode": "image2video",
                "seconds": config.get("seconds", 5),
                "aspect_ratio": config.get("aspect_ratio", "16:9"),
                "scene_data": img_data.get("scene_data"),
                "image_data": img_data,
            })

        return tasks

    def _build_tasks_from_parsed_result(self, config: Dict[str, Any]) -> List[Dict[str, Any]]:
        """从解析结果中构建视频任务"""
        from_step_key = config.get("from_step", "")
        items_path = config.get("items_path", "scenes")

        step_output = self.context.steps_output.get(from_step_key, {})
        parsed_result = step_output.get("parsed_result")

        # 防御性检查：上游 LLM 步骤的 parsed_result 为 None 时抛出明确错误
        # 避免静默返回空列表导致步骤被标记为 success（实际没有任何产出）
        if parsed_result is None:
            raw_response = step_output.get("raw_response", "")
            raise ValueError(
                f"上游步骤 '{from_step_key}' 的 parsed_result 为空，"
                f"无法提取视频任务（raw_response 长度={len(raw_response)}）。"
                f"可能是 LLM 输出 JSON 解析失败。"
            )

        items = self._get_by_path(parsed_result, items_path, default=[])
        if not isinstance(items, list):
            items = [items]

        tasks = []
        for idx, item in enumerate(items):
            prompt = item.get("video_prompt") or item.get("description") or item.get("prompt", "")
            image_url = item.get("image_url", "")

            if not prompt and not image_url:
                continue

            task = {
                "index": idx,
                "prompt": prompt,
                "seconds": config.get("seconds", 5),
                "aspect_ratio": config.get("aspect_ratio", "16:9"),
                "scene_data": item,
            }

            if image_url:
                task["image_url"] = image_url
                # Agnes Video API 使用 "image2video" 模式
                task["mode"] = "image2video"
            else:
                task["mode"] = "text2video"

            tasks.append(task)

        return tasks

    def _build_tasks_from_input(self, config: Dict[str, Any]) -> List[Dict[str, Any]]:
        """从 inputs 中构建视频任务"""
        input_key = config.get("input_key", "video_prompts")
        prompts = self.context.get_input(input_key, [])

        tasks = []
        for idx, item in enumerate(prompts):
            if isinstance(item, str):
                tasks.append({
                    "index": idx,
                    "prompt": item,
                    "mode": "text2video",
                    "seconds": config.get("seconds", 5),
                    "aspect_ratio": config.get("aspect_ratio", "16:9"),
                })
            elif isinstance(item, dict):
                tasks.append({
                    "index": idx,
                    "prompt": item.get("prompt", ""),
                    "image_url": item.get("image_url", ""),
                    "mode": item.get("mode", "text2video"),
                    "seconds": item.get("seconds", config.get("seconds", 5)),
                    "aspect_ratio": item.get("aspect_ratio", config.get("aspect_ratio", "16:9")),
                })

        return tasks

    async def _create_videos_concurrent(
        self, tasks: List[Dict[str, Any]], max_concurrent: int
    ) -> List[Dict[str, Any]]:
        """并发创建视频任务"""
        semaphore = asyncio.Semaphore(max_concurrent)
        results: List[Dict[str, Any]] = [{}] * len(tasks)

        async def create_one(task: Dict[str, Any], idx: int) -> None:
            async with semaphore:
                results[idx] = await self._create_single_video(task)

        await asyncio.gather(
            *(create_one(task, i) for i, task in enumerate(tasks))
        )

        return results

    async def _create_single_video(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """创建单个视频任务

        遇到 Agnes AI 内容审核拒绝（HTTP 400 "Unable to generate this content"）时，
        会调用 LLM 改写 prompt 去除敏感词后重试一次，并在返回结果中记录改写信息
        供前端反馈给用户（让用户知道哪条 prompt 被改写、原文与改写后文本对比）。
        """
        index = task.get("index", 0)
        prompt = task.get("prompt", "")
        mode = task.get("mode", "text2video")
        image_url = task.get("image_url", "")

        # Agnes Video API 使用 "image2video" 模式（不是 "ti2vid"）
        # 客户端会自动根据是否有单图/多图来决定实际 API mode
        if mode == "ti2vid":
            mode = "image2video"

        seconds = task.get("seconds", 5)
        aspect_ratio = task.get("aspect_ratio", "16:9")

        # 应用风格预设（返回 positive + negative 元组）
        # 注意：原代码只在 text2video 时应用风格，本次改造 image2video 也应用，
        # 因为 prompt 仍会传给视频 API，风格关键词有助于保持视频画面与图片风格一致
        negative_prompt = ""
        if self.context.style:
            prompt, negative_prompt = style_service.build_prompt_with_style(
                prompt, self.context.style
            )

        # 路径 B：StyleElement 分层组合（优先级高于 A，engine 已保证互斥）
        # 视频专用：不加权（视频模型对 (kw:weight) 语法理解弱，易触发 HTTP 400），
        # negative 只保留画质类（避免风格类负面与 positive 矛盾导致 API 拒绝）
        if self.context.style_elements:
            from app.services.style_element_service import build_video_prompt_with_elements
            prompt, negative_prompt = build_video_prompt_with_elements(
                prompt, self.context.style_elements
            )

        # 保留原始 prompt（合并风格后）用于改写反馈
        original_prompt_full = prompt

        # 获取视频模型：优先用 step config 中的 model，否则从 model_registry 取第一个可用模型
        # 复用项目原有的 model_registry 机制（与 chat_service.py 一致），避免不传 model 导致 API 拒绝
        config = self.config.get("config", {})
        model = config.get("model", "")
        if not model:
            try:
                from app.services.model_registry import get_models_by_type
                video_models = await get_models_by_type("video")
                model = video_models[0].id if video_models else ""
            except Exception as e:
                logger.warning(f"[视频批量] 获取可用视频模型失败: {e}")
                model = ""

        # 从 config 读取可选的 width/height/num_frames/frame_rate
        # 这些参数符合 Agnes Video API 规范（参考 agnes_client.create_video_task 和 chat_service.py）
        width = config.get("width")
        height = config.get("height")
        num_frames = config.get("num_frames")
        frame_rate = config.get("frame_rate", 24)

        try:
            # 按模型 ID 路由到对应 Provider 的 client
            from app.services.provider_registry import provider_registry
            _video_client = await provider_registry.get_client_for_model(model)
            result = await _video_client.create_video_task(
                prompt=prompt,
                model=model,
                mode=mode,
                image=image_url if mode == "image2video" else None,
                seconds=seconds,
                aspect_ratio=aspect_ratio,
                width=width,
                height=height,
                num_frames=num_frames,
                frame_rate=frame_rate,
                negative_prompt=negative_prompt or None,  # Agnes Video API 原生支持负面提示词
            )

            task_id = result.get("task_id") or result.get("id") or ""
            video_id = result.get("video_id") or ""

            return {
                **task,
                "success": True,
                "task_id": task_id,
                "video_id": video_id,
                "status": "processing",
                "model": model,
            }
        except Exception as e:
            error_msg = str(e)
            # 检测 Agnes AI 内容审核拒绝错误，调用 LLM 改写 prompt 后重试一次
            # 错误特征：HTTP 400 + "Unable to generate this content"
            if "Unable to generate this content" in error_msg:
                logger.warning(
                    f"[视频批量] #{index} 被内容审核拒绝，尝试 LLM 改写 prompt 后重试: "
                    f"original={original_prompt_full[:120]}..."
                )
                rewritten_prompt = await self._rewrite_prompt_with_llm(original_prompt_full)

                if rewritten_prompt and rewritten_prompt.strip() and rewritten_prompt != original_prompt_full:
                    logger.info(
                        f"[视频批量] #{index} LLM 改写完成，重试创建: "
                        f"rewritten={rewritten_prompt[:120]}..."
                    )
                    try:
                        result = await _video_client.create_video_task(
                            prompt=rewritten_prompt,
                            model=model,
                            mode=mode,
                            image=image_url if mode == "image2video" else None,
                            seconds=seconds,
                            aspect_ratio=aspect_ratio,
                            width=width,
                            height=height,
                            num_frames=num_frames,
                            frame_rate=frame_rate,
                            negative_prompt=negative_prompt or None,
                        )

                        task_id = result.get("task_id") or result.get("id") or ""
                        video_id = result.get("video_id") or ""

                        logger.info(f"[视频批量] #{index} 改写后重试成功")
                        return {
                            **task,
                            "success": True,
                            "task_id": task_id,
                            "video_id": video_id,
                            "status": "processing",
                            "model": model,
                            # 改写反馈字段，前端据此展示改写提示
                            "was_rewritten": True,
                            "original_prompt": original_prompt_full,
                            "rewritten_prompt": rewritten_prompt,
                        }
                    except Exception as e2:
                        logger.error(
                            f"[视频批量] #{index} 改写后重试仍失败: {e2}", exc_info=True
                        )
                        return {
                            **task,
                            "success": False,
                            "error": f"内容审核拒绝（改写后仍失败）: {e2}",
                            "was_rewritten": True,
                            "original_prompt": original_prompt_full,
                            "rewritten_prompt": rewritten_prompt,
                        }
                else:
                    logger.warning(f"[视频批量] #{index} LLM 改写返回空或无变化，放弃重试")

            logger.error(f"[视频批量] 创建任务失败 #{index}: {e}", exc_info=True)
            return {
                **task,
                "success": False,
                "error": str(e),
            }

    async def _rewrite_prompt_with_llm(self, original_prompt: str) -> Optional[str]:
        """调用 Agnes AI Chat API 改写被审核拒绝的视频 prompt

        复用项目已有的 chat_service 与 agnes_client 调用模式（参考 chat_service.summarize_session_title）。
        改写策略：保留镜头语言和风格关键词，仅替换叙事中的暴力/恐怖/攻击类词汇为温和表达。
        """
        from app.services.chat_service import chat_service

        system_prompt = """你是一个视频生成提示词改写助手。原始 prompt 被内容审核系统拒绝，请改写它。

要求：
1. 保留原镜头语言（如 Camera pans up、Static shot、Close up 等）不变
2. 保留所有风格关键词（如 manga style、soft lighting、warm color palette 等）不变
3. 仅替换叙事中的暴力、恐怖、攻击、伤害类词汇为温和表达，例如：
   - demon / monster / evil creature → mysterious figure / dark figure
   - claw → hand / fingers
   - strikes / attacks / slashes → moves / gestures / reaches
   - hits the ground / slams into → lands on / descends to
   - screams in pain / bleeding → 移除或改为中性表达（如 reacts）
   - blood / gore / wound → 移除
4. 保持英文输出
5. 只输出改写后的 prompt，不要任何解释、前后缀、引号"""

        body = {
            "model": await chat_service._get_default_chat_model(),
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": original_prompt},
            ],
            "temperature": 0.3,
            "max_tokens": 800,
        }

        try:
            result = await agnes_client._post(chat_service.chat_url, body)
            choice = result.get("choices", [{}])[0]
            content = choice.get("message", {}).get("content", "").strip()
            # 去除可能的前后引号
            content = content.strip('"').strip("'").strip("`").strip()
            return content if content else None
        except Exception as e:
            logger.warning(f"[视频批量] LLM 改写 prompt 失败: {e}")
            return None

    async def _poll_all_videos(
        self, tasks: List[Dict[str, Any]], config: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """轮询所有视频任务直到完成"""
        poll_interval = config.get("poll_interval", 10)  # 轮询间隔（秒）
        max_poll_time = config.get("max_poll_time", 600)  # 最大轮询时间（秒）

        pending_tasks = list(tasks)
        completed_results: List[Dict[str, Any]] = []
        total_elapsed = 0
        total_count = len(tasks)

        while pending_tasks and total_elapsed < max_poll_time:
            await asyncio.sleep(poll_interval)
            total_elapsed += poll_interval

            still_pending = []
            for task in pending_tasks:
                try:
                    status_result = await self._poll_single_video(task)
                    if status_result.get("status") in ("succeeded", "completed", "success"):
                        completed_results.append(status_result)
                    elif status_result.get("status") in ("failed", "error"):
                        completed_results.append({
                            **status_result,
                            "success": False,
                            "error": status_result.get("error", "生成失败"),
                        })
                    else:
                        still_pending.append(task)
                except Exception as e:
                    logger.warning(f"[视频批量] 轮询异常: {e}")
                    still_pending.append(task)

            pending_tasks = still_pending
            # 更新进度计数器
            self._completed_count = len(completed_results)
            if total_count > 0:
                logger.debug(
                    f"[视频批量] 轮询进度: {self._completed_count}/{total_count} "
                    f"({round(self._completed_count/total_count*100, 1)}%)"
                )

        # 超时的任务标记为失败
        for task in pending_tasks:
            completed_results.append({
                **task,
                "success": False,
                "error": "生成超时",
                "status": "timeout",
            })

        return completed_results

    async def _poll_single_video(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """轮询单个视频任务状态"""
        task_id = task.get("task_id") or task.get("video_id")
        video_id = task.get("video_id") or task.get("task_id")

        try:
            # 按模型 ID 路由到对应 Provider 的 client
            from app.services.provider_registry import provider_registry
            _model_id = task.get("model", "")
            _poll_client = await provider_registry.get_client_for_model(_model_id)
            result = await _poll_client.poll_video_status(
                task_id=task_id,
                video_id=video_id,
            )

            status = result.get("status", "processing")
            video_url = result.get("video_url") or result.get("output", {}).get("video_url", "")

            return {
                **task,
                "status": status,
                "video_url": video_url,
                "success": status in ("succeeded", "completed", "success"),
                "progress": result.get("progress", 0),
                "raw_result": result,
            }
        except Exception as e:
            logger.error(f"[视频批量] 轮询失败: {e}", exc_info=True)
            return {
                **task,
                "status": "error",
                "success": False,
                "error": str(e),
            }

    def _get_by_path(self, data: Dict[str, Any], path: str, default: Any = None) -> Any:
        """按点路径获取字典中的值"""
        keys = path.split(".")
        current = data
        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            elif isinstance(current, list) and key.isdigit():
                idx = int(key)
                if 0 <= idx < len(current):
                    current = current[idx]
                else:
                    return default
            else:
                return default
        return current
