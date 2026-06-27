# =====================================================
# 批量图片生成步骤执行器
# 用于一次性生成多张图片（如角色设定图、场景图、分镜图等）
# 支持并发生成，自动整合结果
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
class ImageBatchExecutor(BaseStepExecutor):
    """
    批量图片生成步骤执行器

    可以:
    - 从上游步骤输出中提取图片生成列表（如剧本分镜）
    - 为每个场景/角色生成图片
    - 应用风格预设
    - 并发生成，提高效率
    """

    step_type = "image_batch"

    async def validate(self) -> None:
        """验证输入"""
        config = self.config.get("config", {})

        # 检查图片来源配置
        source = config.get("source", "parsed_result")
        if source not in ("parsed_result", "input_list", "custom"):
            raise ValueError(f"不支持的图片来源: {source}")

        if source == "parsed_result":
            # 需要指定从哪个步骤的 parsed_result 中提取
            if not config.get("from_step"):
                raise ValueError("source=parsed_result 时必须指定 from_step")
            if not config.get("items_path"):
                raise ValueError("source=parsed_result 时必须指定 items_path")

    async def execute(self) -> Dict[str, Any]:
        """执行批量图片生成"""
        config = self.config.get("config", {})

        # 1. 构建图片生成任务列表
        image_tasks = self._build_image_tasks()

        if not image_tasks:
            logger.warning(f"[图片批量] 没有生成任务: step_key={self.step_key}")
            return {"images": [], "total": 0, "failed": 0}

        logger.info(f"[图片批量] 开始生成 {len(image_tasks)} 张图片: step_key={self.step_key}")

        # 2. 并发生成图片（控制并发度）
        max_concurrent = config.get("max_concurrent", 5)
        results = await self._generate_images_concurrent(
            image_tasks, max_concurrent
        )
        self._results_cache = results

        # 3. 统计结果
        success_images = [r for r in results if r.get("success")]
        failed_images = [r for r in results if not r.get("success")]

        logger.info(
            f"[图片批量] 完成: 成功 {len(success_images)}/{len(results)}, "
            f"失败 {len(failed_images)}"
        )

        # 4. 保存生成记录到 generations 表
        if success_images and self.context.run_id:
            try:
                async with new_async_session() as db:
                    gen_ids = await integration.save_batch_generations(
                        db=db,
                        run_id=self.context.run_id,
                        step_key=self.step_key,
                        items=success_images,
                        gen_type="image",
                        user_id=self.context.user_id,
                    )
                    logger.info(f"[图片批量] 已保存 {len(gen_ids)} 条生成记录: step_key={self.step_key}")
            except Exception as e:
                logger.warning(f"[图片批量] 保存生成记录失败: {e}")

        return {
            "images": success_images,
            "failed_images": failed_images,
            "total": len(results),
            "success_count": len(success_images),
            "failed_count": len(failed_images),
        }

    async def estimate_credits(self) -> int:
        """预估积分消耗"""
        config = self.config.get("config", {})
        estimated_count = config.get("estimated_count", 10)
        return estimated_count * 10  # 每张图约 10 积分

    async def get_progress(self) -> Dict[str, Any]:
        """
        获取当前执行进度。

        返回: {"current": int, "total": int, "percent": float}
        """
        image_tasks = getattr(self, "_image_tasks_cache", None)
        results = getattr(self, "_results_cache", None)

        if image_tasks is None:
            return {}

        total = len(image_tasks)
        if total == 0:
            return {}

        completed = 0
        if results is not None:
            completed = len([r for r in results if r and r.get("success") is not None])

        return {
            "current": completed,
            "total": total,
            "percent": round(completed / total, 3),
        }

    # ---------- 内部方法 ----------

    def _build_image_tasks(self) -> List[Dict[str, Any]]:
        """构建图片生成任务列表"""
        config = self.config.get("config", {})
        source = config.get("source", "parsed_result")

        if source == "parsed_result":
            tasks = self._build_tasks_from_parsed_result(config)
        elif source == "input_list":
            tasks = self._build_tasks_from_input(config)
        elif source == "custom":
            tasks = config.get("tasks", [])
        else:
            tasks = []

        # 角色参考图传递：从上游 character_images 步骤构建 {角色名: image_url} 映射，
        # 为每个 scene 注入 reference_images，保持人物一致性
        reference_from_step = config.get("reference_from_step")
        if reference_from_step and tasks:
            character_image_map = self._build_character_image_map(reference_from_step)
            if character_image_map:
                for task in tasks:
                    scene_data = task.get("scene_data") or {}
                    characters_in_scene = scene_data.get("characters_in_scene") or []
                    if characters_in_scene:
                        # 根据场景出现的角色名，找到对应角色图 URL
                        refs = [
                            character_image_map[name]
                            for name in characters_in_scene
                            if name in character_image_map
                        ]
                        if refs:
                            task["reference_images"] = refs

        # 风格参考图（新增，从 step config 读取风格图 URL）
        # 与角色参考图（reference_images）分离，风格图取视觉氛围，角色图取主体
        style_reference_image = config.get("style_reference_image")
        if style_reference_image:
            for task in tasks:
                task["style_reference_image"] = style_reference_image

        # 缓存任务列表供进度查询
        self._image_tasks_cache = tasks
        return tasks

    def _build_tasks_from_parsed_result(self, config: Dict[str, Any]) -> List[Dict[str, Any]]:
        """从上游步骤的解析结果中提取图片任务"""
        from_step_key = config.get("from_step", "")
        items_path = config.get("items_path", "")

        # 获取上游步骤输出
        step_output = self.context.steps_output.get(from_step_key, {})
        parsed_result = step_output.get("parsed_result")

        # 防御性检查：上游 LLM 步骤的 parsed_result 为 None 时抛出明确错误
        # 避免静默返回空列表导致步骤被标记为 success（实际没有任何产出）
        if parsed_result is None:
            raw_response = step_output.get("raw_response", "")
            raise ValueError(
                f"上游步骤 '{from_step_key}' 的 parsed_result 为空，"
                f"无法提取图片任务（raw_response 长度={len(raw_response)}）。"
                f"可能是 LLM 输出 JSON 解析失败。"
            )

        # 按路径提取
        items = self._get_by_path(parsed_result, items_path, default=[])
        if not isinstance(items, list):
            items = [items]

        # 构建任务
        tasks = []
        for idx, item in enumerate(items):
            task = self._build_single_task(item, idx, config)
            if task:
                tasks.append(task)

        return tasks

    def _build_tasks_from_input(self, config: Dict[str, Any]) -> List[Dict[str, Any]]:
        """从 inputs 中提取图片任务"""
        input_key = config.get("input_key", "image_prompts")
        prompts = self.context.get_input(input_key, [])

        tasks = []
        for idx, prompt in enumerate(prompts):
            if isinstance(prompt, str):
                tasks.append({
                    "index": idx,
                    "prompt": prompt,
                    "size": config.get("size", "1024x1024"),
                })
            elif isinstance(prompt, dict):
                tasks.append({
                    "index": idx,
                    "prompt": prompt.get("prompt", ""),
                    "size": prompt.get("size", config.get("size", "1024x1024")),
                })

        return tasks

    def _build_character_image_map(self, from_step_key: str) -> Dict[str, str]:
        """
        从上游 character_images 步骤构建 {角色名: image_url} 映射。

        用于 scene_images 步骤的参考图传递：每个 scene 根据 characters_in_scene
        字段找到对应角色图，作为图生图的参考图，保持人物一致性。

        Args:
            from_step_key: 上游角色图步骤的 step_key（如 "character_images"）

        Returns:
            {角色名: image_url} 字典；
            如上游步骤无输出、无角色名、或角色图 URL 为空，返回空字典
        """
        step_output = self.context.steps_output.get(from_step_key, {})
        images = step_output.get("images", [])

        mapping: Dict[str, str] = {}
        for img_data in images:
            # character_images 步骤的 scene_data 是角色对象（含 name 字段）
            scene_data = img_data.get("scene_data") or {}
            name = scene_data.get("name", "")
            image_url = img_data.get("image_url", "")
            if name and image_url:
                mapping[name] = image_url

        return mapping

    def _build_single_task(
        self, item: Dict[str, Any], index: int, config: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """从单个 item 构建图片生成任务"""
        prompt_field = config.get("prompt_field", "image_prompt")
        size_field = config.get("size_field", "")
        default_size = config.get("size", "1024x1024")

        prompt = item.get(prompt_field, "")
        if not prompt:
            return None

        size = item.get(size_field, default_size) if size_field else default_size

        return {
            "index": index,
            "prompt": prompt,
            "size": size,
            "scene_data": item,  # 保留原始场景数据
        }

    async def _generate_images_concurrent(
        self, tasks: List[Dict[str, Any]], max_concurrent: int
    ) -> List[Dict[str, Any]]:
        """并发生成图片（使用信号量控制并发度）"""
        semaphore = asyncio.Semaphore(max_concurrent)
        results: List[Dict[str, Any]] = [{}] * len(tasks)

        async def generate_one(task: Dict[str, Any], idx: int) -> None:
            async with semaphore:
                results[idx] = await self._generate_single_image(task)

        await asyncio.gather(
            *(generate_one(task, i) for i, task in enumerate(tasks))
        )

        return results

    async def _generate_single_image(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """生成单张图片"""
        prompt = task.get("prompt", "")
        size = task.get("size", "1024x1024")
        index = task.get("index", 0)
        # 角色参考图 URL 列表（来自上游 character_images 步骤，用于保持人物一致性）
        reference_images = task.get("reference_images", []) or []
        # 风格参考图（来自 step config，取视觉氛围）
        style_reference_image = task.get("style_reference_image")

        # 应用风格预设（返回 positive + negative 元组）
        # 注意：Agnes Image API 不支持 negative_prompt 参数，负面提示词拼接到 prompt 末尾
        if self.context.style:
            prompt, _negative = style_service.build_prompt_with_style(
                prompt, self.context.style
            )
            # 拼接负面提示词后缀（avoid: xxx, yyy）
            negative_suffix = style_service.build_negative_prompt_suffix(self.context.style)
            if negative_suffix:
                prompt = f"{prompt}, {negative_suffix}"

        # 路径 B：StyleElement 分层组合（优先级高于 A，engine 已保证互斥）
        if self.context.style_elements:
            from app.services.style_element_service import (
                build_prompt_with_elements,
                build_negative_prompt_suffix_from_elements,
            )
            prompt, _neg = build_prompt_with_elements(prompt, self.context.style_elements)
            neg_suffix = build_negative_prompt_suffix_from_elements(self.context.style_elements)
            if neg_suffix:
                prompt = f"{prompt}, {neg_suffix}"

        # 获取图片模型：优先用 step config 中的 model，否则从 model_registry 取第一个可用模型
        # 复用项目原有的 model_registry 机制，避免硬编码模型名导致 503 错误
        config = self.config.get("config", {})
        model = config.get("model", "")
        if not model:
            try:
                from app.services.model_registry import get_models_by_type
                image_models = await get_models_by_type("image")
                model = image_models[0].id if image_models else ""
            except Exception as e:
                logger.warning(f"[图片批量] 获取可用图片模型失败: {e}")
                model = ""

        # 参考图：风格参考图（取视觉氛围）+ 角色参考图（取主体）合并
        all_refs = []
        if style_reference_image:
            all_refs.append(style_reference_image)
        all_refs.extend(reference_images)

        try:
            # 如有参考图（风格图 + 角色图），走图生图模式；否则文生图
            if all_refs:
                result = await agnes_client.create_image(
                    prompt=prompt,
                    model=model,
                    size=size,
                    response_format="url",
                    image_urls=all_refs,
                )
            else:
                result = await agnes_client.create_image(
                    prompt=prompt,
                    model=model,
                    size=size,
                    response_format="url",
                )

            # 解析结果：优先 URL；若仅有 base64，则包装为 data URI 以便前端 <img> 直接显示
            image_url = ""
            if isinstance(result, dict):
                data = result.get("data", [])
                if data and isinstance(data, list):
                    raw_url = data[0].get("url", "")
                    raw_b64 = data[0].get("b64_json", "")
                    if raw_url:
                        image_url = raw_url
                    elif raw_b64:
                        image_url = f"data:image/png;base64,{raw_b64}"

            return {
                "success": True,
                "index": index,
                "prompt": prompt,
                "size": size,
                "image_url": image_url,
                "scene_data": task.get("scene_data"),
                "model": model,
                "reference_images": reference_images,  # 记录使用的角色参考图（便于调试）
            }
        except Exception as e:
            logger.error(f"[图片批量] 单张图片生成失败 #{index}: {e}", exc_info=True)
            return {
                "success": False,
                "index": index,
                "prompt": prompt,
                "size": size,
                "error": str(e),
                "scene_data": task.get("scene_data"),
            }

    def _get_by_path(self, data: Dict[str, Any], path: str, default: Any = None) -> Any:
        """按点路径获取字典中的值，如 'scenes.characters'"""
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
