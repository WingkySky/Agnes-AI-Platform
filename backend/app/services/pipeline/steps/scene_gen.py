# =====================================================
# 场景生成步骤执行器（场景生成）
# 两阶段执行：
#   1. LLM 阶段：根据上游场景清单为每个场景生成详细视觉描述（环境/光线/氛围）
#   2. 图片阶段：根据视觉描述为每个场景生成参考图
# 按元素独立记录 status，单个场景失败不阻塞其他场景
# =====================================================

import asyncio
import logging
import random
from typing import Dict, Any, List

from app.core.database import new_async_session
from app.services.pipeline.steps import register_step_executor
from app.services.pipeline.steps.base import (
    BaseStepExecutor,
    SingleItemContext,
    ItemResult,
)
from app.services.agnes_client import agnes_client
from app.services import script_template_service
from app.services import style_service
from app.services.pipeline import integration

logger = logging.getLogger("agnes_platform.pipeline")


# 默认场景视觉描述生成 prompt 模板（用户可在 llm_config.prompt_template 中覆盖）
_DEFAULT_SCENE_PROMPT_TEMPLATE = """请为以下场景生成详细的视觉描述，用于 AI 图片生成参考。

场景名称：{{ name }}
简述：{{ description }}

请输出一段详细的场景视觉描述（200字以内），包含以下方面：
1. 环境特征（地形、建筑、植被等空间要素）
2. 光线方向与色温（清晨/正午/黄昏/夜晚，暖色/冷色）
3. 氛围情绪（宁静/紧张/神秘/温馨等）
4. 时间天气（季节、时段、晴/阴/雨/雪）
5. 空间纵深（前景/中景/背景层次）
6. 关键道具元素（标志性物件、装饰细节）

直接输出描述文本，不要加标题或分段标记。"""


@register_step_executor
class SceneGenExecutor(BaseStepExecutor):
    """
    场景生成步骤执行器（场景生成）

    两阶段执行：
    - 阶段一 LLM：从上游读取场景清单，为每个场景生成详细视觉描述
    - 阶段二 image_batch：用视觉描述作为 prompt 为每个场景生成参考图

    输出结构：
    {
        "items": [
            {"id": "scene_001", "name": "森林入口", "description": "...",
             "image_url": "...", "status": "success", "seed": 12345, "error": null}
        ],
        "summary": {"total": 1, "success_count": 1, "failed_count": 0}
    }
    """

    step_type = "scene_gen"

    async def validate(self) -> None:
        """验证输入"""
        config = self.config.get("config", {})
        scene_source = config.get("scene_source", "")
        if not scene_source:
            raise ValueError("缺少 scene_source 配置")

    async def execute(self) -> Dict[str, Any]:
        """执行两阶段场景生成"""
        config = self.config.get("config", {})

        # 1. 从上游读取场景清单
        scenes = self._get_scenes(config.get("scene_source", ""))
        if not scenes:
            logger.warning(f"[场景生成] 上游无场景清单: step_key={self.step_key}")
            return {
                "items": [],
                "summary": {"total": 0, "success_count": 0, "failed_count": 0},
            }

        logger.info(f"[场景生成] 开始生成 {len(scenes)} 个场景: step_key={self.step_key}")

        # 2. 阶段一：并发调用 LLM 生成每个场景的视觉描述
        llm_results = await self._generate_settings_concurrent(scenes, config)

        # 3. 阶段二：并发调用图片 API 生成每个场景的参考图
        items = await self._generate_images_concurrent(llm_results, config)

        # 4. 统计结果
        success_count = sum(1 for it in items if it.get("status") == "success")
        failed_count = len(items) - success_count

        logger.info(
            f"[场景生成] 完成: 成功 {success_count}/{len(items)}, 失败 {failed_count}"
        )

        # 5. 保存生成记录到 generations 表（复用 image_batch 的保存逻辑）
        success_items = [
            {
                "success": True,
                "image_url": it.get("image_url", ""),
                "prompt": it.get("description", ""),
                "model": config.get("image_config", {}).get("model", ""),
            }
            for it in items
            if it.get("status") == "success" and it.get("image_url")
        ]
        if success_items and self.context.run_id:
            try:
                async with new_async_session() as db:
                    await integration.save_batch_generations(
                        db=db,
                        run_id=self.context.run_id,
                        step_key=self.step_key,
                        items=success_items,
                        gen_type="image",
                        user_id=self.context.user_id,
                    )
                    logger.info(f"[场景生成] 已保存 {len(success_items)} 条生成记录: step_key={self.step_key}")
            except Exception as e:
                logger.warning(f"[场景生成] 保存生成记录失败: {e}")

        return {
            "items": items,
            "summary": {
                "total": len(items),
                "success_count": success_count,
                "failed_count": failed_count,
            },
        }

    async def estimate_credits(self) -> int:
        """预估积分消耗（LLM 少量 + 图片按场景数）"""
        config = self.config.get("config", {})
        estimated_count = config.get("estimated_count", 5)
        # LLM 5 积分 + 每张图 10 积分
        return 5 + estimated_count * 10

    async def execute_single(self, ctx: SingleItemContext) -> ItemResult:
        """
        单场景重生成（重跑 LLM + image 两阶段）

        Args:
            ctx: 单元素执行上下文，item 含 id/name/description 等字段

        Returns:
            ItemResult: 单元素执行结果
        """
        item = ctx.item or {}
        # ctx.config 可能是完整 step_config（含 type/key/config）或直接是内层 config
        raw_config = ctx.config or {}
        config = (
            raw_config.get("config")
            if isinstance(raw_config, dict) and "config" in raw_config
            else raw_config
        )

        scene_id = item.get("id", "")
        name = item.get("name", "")
        description = item.get("description", "")

        logger.info(f"[场景生成-单元素] 重生场景: id={scene_id}, name={name}")

        # 用 ctx.prompt_override 替换 LLM prompt（若提供），否则走 LLM 生成
        prompt_override = ctx.prompt_override
        # 用 ctx.seed 替换图片生成种子（若提供），否则生成新的随机 seed
        # 注意：Agnes Image API 当前不支持 seed 参数，seed 仅作记录用于跟踪
        seed = ctx.seed if ctx.seed is not None else random.randint(0, 2**31 - 1)

        # 阶段一：LLM 生成视觉描述
        setting_text = ""
        if prompt_override:
            # 用户提供了 prompt 覆盖，直接作为视觉描述
            setting_text = prompt_override
        else:
            try:
                setting_text = await self._generate_setting_text(
                    name=name,
                    description=description,
                    config=config,
                )
            except Exception as e:
                logger.error(
                    f"[场景生成-单元素] LLM 生成失败: id={scene_id}, name={name}, err={e}",
                    exc_info=True,
                )
                return ItemResult(
                    status="failed",
                    item={
                        **item,
                        "description": "",
                        "image_url": "",
                        "seed": seed,
                        "error": f"LLM 生成失败: {e}",
                    },
                    error=f"LLM 生成失败: {e}",
                )

        # 阶段二：图片生成
        try:
            image_url = await self._generate_scene_image(
                setting_text=setting_text,
                name=name,
                config=config,
                seed=seed,
            )
            return ItemResult(
                status="success",
                item={
                    **item,
                    "description": setting_text,
                    "image_url": image_url,
                    "seed": seed,
                    "error": None,
                },
            )
        except Exception as e:
            logger.error(
                f"[场景生成-单元素] 图片生成失败: id={scene_id}, name={name}, err={e}",
                exc_info=True,
            )
            return ItemResult(
                status="failed",
                item={
                    **item,
                    "description": setting_text,
                    "image_url": "",
                    "seed": seed,
                    "error": f"图片生成失败: {e}",
                },
                error=f"图片生成失败: {e}",
            )

    # ---------- 内部方法 ----------

    def _get_scenes(self, source_path: str) -> List[Dict[str, Any]]:
        """
        从上游步骤输出中读取场景清单。

        支持点路径访问，如 "steps_output.step_storyboard.scenes"
        或 "step_storyboard.scenes"（默认从 steps_output 开始）。
        若上游没有 scenes 字段或为空，返回空列表（不报错）。
        """
        if not source_path:
            return []

        # 兼容 "steps_output.xxx" 和 "xxx" 两种写法
        path = source_path
        if path.startswith("steps_output."):
            path = path[len("steps_output."):]

        current: Any = self.context.steps_output
        for key in path.split("."):
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return []

        if not isinstance(current, list):
            return []

        # 过滤无效项，归一化为 {id, name, description}
        # 兼容字段：name/scene_name, description/brief/summary
        scenes: List[Dict[str, Any]] = []
        for idx, item in enumerate(current):
            if not isinstance(item, dict):
                continue
            name = item.get("name") or item.get("scene_name") or ""
            description = (
                item.get("description")
                or item.get("brief")
                or item.get("summary")
                or ""
            )
            if not name:
                # 没有名字的场景跳过
                continue
            scenes.append({
                "id": item.get("id") or f"scene_{idx + 1:03d}",
                "name": name,
                "description": description,
            })
        return scenes

    async def _generate_settings_concurrent(
        self,
        scenes: List[Dict[str, Any]],
        config: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """阶段一：并发调用 LLM 生成每个场景的视觉描述"""
        llm_config = config.get("llm_config", {})
        max_concurrent = llm_config.get("max_concurrent", 3)
        semaphore = asyncio.Semaphore(max_concurrent)
        results: List[Dict[str, Any]] = [{}] * len(scenes)

        async def gen_one(idx: int, scene: Dict[str, Any]) -> None:
            async with semaphore:
                scene_id = scene.get("id", f"scene_{idx + 1:03d}")
                name = scene.get("name", "")
                description = scene.get("description", "")
                try:
                    setting_text = await self._generate_setting_text(
                        name=name,
                        description=description,
                        config=config,
                    )
                    results[idx] = {
                        "id": scene_id,
                        "name": name,
                        "description": description,
                        "setting_text": setting_text,
                        "llm_success": True,
                        "llm_error": None,
                    }
                except Exception as e:
                    logger.error(
                        f"[场景生成] LLM 阶段失败: id={scene_id}, name={name}, err={e}",
                        exc_info=True,
                    )
                    results[idx] = {
                        "id": scene_id,
                        "name": name,
                        "description": description,
                        "setting_text": "",
                        "llm_success": False,
                        "llm_error": str(e),
                    }

        await asyncio.gather(
            *(gen_one(i, s) for i, s in enumerate(scenes))
        )
        return results

    async def _generate_images_concurrent(
        self,
        llm_results: List[Dict[str, Any]],
        config: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """阶段二：并发调用图片 API 生成每个场景的参考图"""
        image_config = config.get("image_config", {})
        max_concurrent = image_config.get("max_concurrent", 3)
        semaphore = asyncio.Semaphore(max_concurrent)
        results: List[Dict[str, Any]] = [{}] * len(llm_results)

        async def gen_one(idx: int, llm_res: Dict[str, Any]) -> None:
            async with semaphore:
                scene_id = llm_res.get("id", f"scene_{idx + 1:03d}")
                name = llm_res.get("name", "")

                # LLM 失败的场景直接标记失败，不进入图片阶段
                if not llm_res.get("llm_success"):
                    results[idx] = {
                        "id": scene_id,
                        "name": name,
                        "description": "",
                        "image_url": "",
                        "status": "failed",
                        "seed": None,
                        "error": f"LLM 生成失败: {llm_res.get('llm_error', '未知错误')}",
                    }
                    return

                setting_text = llm_res.get("setting_text", "")
                # 生成随机 seed 用于跟踪（Image API 当前不支持 seed 参数，仅作记录）
                seed = random.randint(0, 2**31 - 1)
                try:
                    image_url = await self._generate_scene_image(
                        setting_text=setting_text,
                        name=name,
                        config=config,
                        seed=seed,
                    )
                    results[idx] = {
                        "id": scene_id,
                        "name": name,
                        "description": setting_text,
                        "image_url": image_url,
                        "status": "success",
                        "seed": seed,
                        "error": None,
                    }
                except Exception as e:
                    logger.error(
                        f"[场景生成] 图片阶段失败: id={scene_id}, name={name}, err={e}",
                        exc_info=True,
                    )
                    results[idx] = {
                        "id": scene_id,
                        "name": name,
                        "description": setting_text,
                        "image_url": "",
                        "status": "failed",
                        "seed": seed,
                        "error": f"图片生成失败: {e}",
                    }

        await asyncio.gather(
            *(gen_one(i, r) for i, r in enumerate(llm_results))
        )
        return results

    async def _generate_setting_text(
        self,
        name: str,
        description: str,
        config: Dict[str, Any],
    ) -> str:
        """调用 LLM 为单个场景生成详细视觉描述"""
        llm_config = config.get("llm_config", {})
        system_prompt = llm_config.get(
            "system_prompt",
            "你是一位专业的场景设计师，擅长创作富有氛围感的场景视觉描述。",
        )
        prompt_template = (
            llm_config.get("prompt_template") or _DEFAULT_SCENE_PROMPT_TEMPLATE
        )

        # 渲染 prompt 模板（复用 script_template_service 的 Jinja2 渲染）
        variables = {
            "name": name,
            "description": description,
            "inputs": self.context.inputs,
            "steps": self.context.steps_output,
        }
        user_prompt = script_template_service.render_prompt_template(
            prompt_template, variables
        )

        # 调用 LLM
        return await self._call_llm(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model=llm_config.get("model", "agnes-2.0-flash"),
            temperature=llm_config.get("temperature", 0.8),
        )

    async def _generate_scene_image(
        self,
        setting_text: str,
        name: str,
        config: Dict[str, Any],
        seed: int,
    ) -> str:
        """调用图片生成 API 为单个场景生成参考图（文生图模式）"""
        image_config = config.get("image_config", {})
        size = image_config.get("size", "1024x576")

        # 构建图片 prompt：场景名 + 视觉描述
        prompt = f"场景参考图 - {name}: {setting_text}"

        # 应用风格预设（与 image_batch.py 一致：返回 positive + negative 元组）
        # 注意：Agnes Image API 不支持 negative_prompt 参数，负面提示词拼接到 prompt 末尾
        if self.context.style:
            prompt, _negative = style_service.build_prompt_with_style(
                prompt, self.context.style
            )
            negative_suffix = style_service.build_negative_prompt_suffix(self.context.style)
            if negative_suffix:
                prompt = f"{prompt}, {negative_suffix}"

        # 路径 B：StyleElement 分层组合（优先级高于 style，engine 已保证互斥）
        if self.context.style_elements:
            from app.services.style_element_service import (
                build_prompt_with_elements,
                build_negative_prompt_suffix_from_elements,
            )
            prompt, _neg = build_prompt_with_elements(prompt, self.context.style_elements)
            neg_suffix = build_negative_prompt_suffix_from_elements(self.context.style_elements)
            if neg_suffix:
                prompt = f"{prompt}, {neg_suffix}"

        # 获取图片模型：优先用 image_config.model，否则从 model_registry 取第一个可用模型
        # 复用项目原有的 model_registry 机制，避免硬编码模型名导致 503 错误
        model = image_config.get("model", "")
        if not model:
            try:
                from app.services.model_registry import get_models_by_type
                image_models = await get_models_by_type("image")
                model = image_models[0].id if image_models else ""
            except Exception as e:
                logger.warning(f"[场景生成] 获取可用图片模型失败: {e}")
                model = ""

        # 通过 provider_registry 路由到对应 Provider 的 client（与 image_batch.py 一致）
        from app.services.provider_registry import provider_registry
        _img_client = await provider_registry.get_client_for_model(model)

        # 调用图片生成（场景参考图为文生图，不传参考图）
        # 注意：Agnes Image API 参数表无 seed 字段，传了可能导致 422，seed 仅作记录用于跟踪
        result = await _img_client.create_image(
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

        if not image_url:
            raise RuntimeError("图片生成 API 未返回有效 URL 或 base64")

        return image_url

    async def _call_llm(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str = "agnes-2.0-flash",
        temperature: float = 0.8,
    ) -> str:
        """调用 LLM API（与 llm_generate.py 一致的调用方式）"""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        try:
            response = await agnes_client.chat_completion(
                messages=messages,
                model=model,
                temperature=temperature,
                stream=False,
            )
            # 从响应中提取文本
            if isinstance(response, dict):
                choices = response.get("choices", [])
                if choices:
                    return choices[0].get("message", {}).get("content", "")
            elif hasattr(response, "choices"):
                if response.choices:
                    return response.choices[0].message.content
            return str(response)
        except AttributeError:
            # agnes_client 没有 chat_completion 方法，走兜底（与 llm_generate.py 一致）
            return await self._fallback_chat(messages, model, temperature)

    async def _fallback_chat(
        self,
        messages: List[Dict[str, str]],
        model: str,
        temperature: float,
    ) -> str:
        """兜底的聊天调用（直接用 httpx，与 llm_generate.py 一致）"""
        import httpx

        from app.core.config import settings

        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{settings.agnes_api_base_url.rstrip('/')}/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.agnes_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": messages,
                    "temperature": temperature,
                    "stream": False,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("choices", [{}])[0].get("message", {}).get("content", "")
