# =====================================================
# 道具生成步骤执行器（道具参考图生成）
# 两阶段执行：
#   1. LLM 阶段：根据上游道具清单为每个道具生成详细视觉描述（外观/材质/功能/使用场景）
#   2. 图片阶段：根据视觉描述为每个道具生成参考图
# 按元素独立记录 status，单个道具失败不阻塞其他道具
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


# 默认道具视觉描述生成 prompt 模板（用户可在 llm_config.prompt_template 中覆盖）
_DEFAULT_PROP_PROMPT_TEMPLATE = """请为以下道具生成详细的视觉描述，用于后续生成道具参考图。

道具名称：{{ name }}
简述：{{ description }}

请输出一段详细的道具视觉描述（150-300字），包含以下方面：
1. 外观特征（形状、轮廓、标志性造型等）
2. 材质（金属、木材、布料、宝石等）
3. 颜色（主色调、配色、光泽等）
4. 尺寸比例（相对大小、长宽高等）
5. 功能细节（机关、纹路、发光部位、可活动部件等）
6. 使用场景（手持、摆放、佩戴、悬挂等）

直接输出描述文本，不要加标题或分段标记。"""


@register_step_executor
class PropGenExecutor(BaseStepExecutor):
    """
    道具生成步骤执行器（道具参考图生成）

    两阶段执行：
    - 阶段一 LLM：从上游读取道具清单，为每个道具生成详细视觉描述
    - 阶段二 image_batch：用视觉描述作为 prompt 为每个道具生成参考图

    输出结构：
    {
        "items": [
            {"id": "prop_001", "name": "圣剑", "description": "...",
             "image_url": "...", "status": "success", "seed": 12345, "error": null}
        ],
        "summary": {"total": 1, "success_count": 1, "failed_count": 0}
    }
    """

    step_type = "prop_gen"

    async def validate(self) -> None:
        """验证输入"""
        config = self.config.get("config", {})
        prop_source = config.get("prop_source", "")
        if not prop_source:
            raise ValueError("缺少 prop_source 配置")

    async def execute(self) -> Dict[str, Any]:
        """执行两阶段道具生成"""
        config = self.config.get("config", {})

        # 1. 从上游读取道具清单
        props = self._get_props(config.get("prop_source", ""))
        if not props:
            logger.warning(f"[道具生成] 上游无道具清单: step_key={self.step_key}")
            return {
                "items": [],
                "summary": {"total": 0, "success_count": 0, "failed_count": 0},
            }

        logger.info(f"[道具生成] 开始生成 {len(props)} 个道具: step_key={self.step_key}")

        # 2. 阶段一：并发调用 LLM 生成每个道具的视觉描述
        llm_results = await self._generate_descriptions_concurrent(props, config)

        # 3. 阶段二：并发调用图片 API 生成每个道具的参考图
        items = await self._generate_images_concurrent(llm_results, config)

        # 4. 统计结果
        success_count = sum(1 for it in items if it.get("status") == "success")
        failed_count = len(items) - success_count

        logger.info(
            f"[道具生成] 完成: 成功 {success_count}/{len(items)}, 失败 {failed_count}"
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
                    logger.info(f"[道具生成] 已保存 {len(success_items)} 条生成记录: step_key={self.step_key}")
            except Exception as e:
                logger.warning(f"[道具生成] 保存生成记录失败: {e}")

        return {
            "items": items,
            "summary": {
                "total": len(items),
                "success_count": success_count,
                "failed_count": failed_count,
            },
        }

    async def estimate_credits(self) -> int:
        """预估积分消耗（LLM 少量 + 图片按道具数）"""
        config = self.config.get("config", {})
        estimated_count = config.get("estimated_count", 5)
        # LLM 5 积分 + 每张图 10 积分
        return 5 + estimated_count * 10

    async def execute_single(self, ctx: SingleItemContext) -> ItemResult:
        """
        单道具重生成（重跑 LLM + image 两阶段）

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

        prop_id = item.get("id", "")
        name = item.get("name", "")
        description = item.get("description", "")

        logger.info(f"[道具生成-单元素] 重生道具: id={prop_id}, name={name}")

        # 用 ctx.prompt_override 替换 LLM prompt（若提供），否则走 LLM 生成
        prompt_override = ctx.prompt_override
        # 用 ctx.seed 替换图片生成种子（若提供），否则生成新的随机 seed
        # 注意：Agnes Image API 当前不支持 seed 参数，seed 仅作记录用于跟踪
        seed = ctx.seed if ctx.seed is not None else random.randint(0, 2**31 - 1)

        # 阶段一：LLM 生成视觉描述
        visual_desc = ""
        if prompt_override:
            # 用户提供了 prompt 覆盖，直接作为视觉描述
            visual_desc = prompt_override
        else:
            try:
                visual_desc = await self._generate_description_text(
                    name=name,
                    description=description,
                    config=config,
                )
            except Exception as e:
                logger.error(
                    f"[道具生成-单元素] LLM 生成失败: id={prop_id}, name={name}, err={e}",
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
            image_url = await self._generate_prop_image(
                description=visual_desc,
                name=name,
                config=config,
                seed=seed,
            )
            return ItemResult(
                status="success",
                item={
                    **item,
                    "description": visual_desc,
                    "image_url": image_url,
                    "seed": seed,
                    "error": None,
                },
            )
        except Exception as e:
            logger.error(
                f"[道具生成-单元素] 图片生成失败: id={prop_id}, name={name}, err={e}",
                exc_info=True,
            )
            return ItemResult(
                status="failed",
                item={
                    **item,
                    "description": visual_desc,
                    "image_url": "",
                    "seed": seed,
                    "error": f"图片生成失败: {e}",
                },
                error=f"图片生成失败: {e}",
            )

    # ---------- 内部方法 ----------

    def _get_props(self, source_path: str) -> List[Dict[str, Any]]:
        """
        从上游步骤输出中读取道具清单。

        支持点路径访问，如 "steps_output.step_storyboard.props"
        或 "step_storyboard.props"（默认从 steps_output 开始）。
        若上游没有 props 字段或为空，返回空列表（不报错）。
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
        # 兼容上游字段：name/prop_name, description/brief/summary
        props: List[Dict[str, Any]] = []
        for idx, item in enumerate(current):
            if not isinstance(item, dict):
                continue
            name = item.get("name") or item.get("prop_name") or ""
            description = (
                item.get("description")
                or item.get("brief")
                or item.get("summary")
                or ""
            )
            if not name:
                # 没有名字的道具跳过
                continue
            props.append({
                "id": item.get("id") or f"prop_{idx + 1:03d}",
                "name": name,
                "description": description,
            })
        return props

    async def _generate_descriptions_concurrent(
        self,
        props: List[Dict[str, Any]],
        config: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """阶段一：并发调用 LLM 生成每个道具的视觉描述"""
        llm_config = config.get("llm_config", {})
        max_concurrent = llm_config.get("max_concurrent", 3)
        semaphore = asyncio.Semaphore(max_concurrent)
        results: List[Dict[str, Any]] = [{}] * len(props)

        async def gen_one(idx: int, prop: Dict[str, Any]) -> None:
            async with semaphore:
                prop_id = prop.get("id", f"prop_{idx + 1:03d}")
                name = prop.get("name", "")
                description = prop.get("description", "")
                try:
                    visual_desc = await self._generate_description_text(
                        name=name,
                        description=description,
                        config=config,
                    )
                    results[idx] = {
                        "id": prop_id,
                        "name": name,
                        "description": visual_desc,
                        "origin_description": description,
                        "llm_success": True,
                        "llm_error": None,
                    }
                except Exception as e:
                    logger.error(
                        f"[道具生成] LLM 阶段失败: id={prop_id}, name={name}, err={e}",
                        exc_info=True,
                    )
                    results[idx] = {
                        "id": prop_id,
                        "name": name,
                        "description": "",
                        "origin_description": description,
                        "llm_success": False,
                        "llm_error": str(e),
                    }

        await asyncio.gather(
            *(gen_one(i, p) for i, p in enumerate(props))
        )
        return results

    async def _generate_images_concurrent(
        self,
        llm_results: List[Dict[str, Any]],
        config: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """阶段二：并发调用图片 API 生成每个道具的参考图"""
        image_config = config.get("image_config", {})
        max_concurrent = image_config.get("max_concurrent", 3)
        semaphore = asyncio.Semaphore(max_concurrent)
        results: List[Dict[str, Any]] = [{}] * len(llm_results)

        async def gen_one(idx: int, llm_res: Dict[str, Any]) -> None:
            async with semaphore:
                prop_id = llm_res.get("id", f"prop_{idx + 1:03d}")
                name = llm_res.get("name", "")

                # LLM 失败的道具直接标记失败，不进入图片阶段
                if not llm_res.get("llm_success"):
                    results[idx] = {
                        "id": prop_id,
                        "name": name,
                        "description": "",
                        "image_url": "",
                        "status": "failed",
                        "seed": None,
                        "error": f"LLM 生成失败: {llm_res.get('llm_error', '未知错误')}",
                    }
                    return

                visual_desc = llm_res.get("description", "")
                # 生成随机 seed 用于跟踪（Image API 当前不支持 seed 参数，仅作记录）
                seed = random.randint(0, 2**31 - 1)
                try:
                    image_url = await self._generate_prop_image(
                        description=visual_desc,
                        name=name,
                        config=config,
                        seed=seed,
                    )
                    results[idx] = {
                        "id": prop_id,
                        "name": name,
                        "description": visual_desc,
                        "image_url": image_url,
                        "status": "success",
                        "seed": seed,
                        "error": None,
                    }
                except Exception as e:
                    logger.error(
                        f"[道具生成] 图片阶段失败: id={prop_id}, name={name}, err={e}",
                        exc_info=True,
                    )
                    results[idx] = {
                        "id": prop_id,
                        "name": name,
                        "description": visual_desc,
                        "image_url": "",
                        "status": "failed",
                        "seed": seed,
                        "error": f"图片生成失败: {e}",
                    }

        await asyncio.gather(
            *(gen_one(i, r) for i, r in enumerate(llm_results))
        )
        return results

    async def _generate_description_text(
        self,
        name: str,
        description: str,
        config: Dict[str, Any],
    ) -> str:
        """调用 LLM 为单个道具生成详细视觉描述"""
        llm_config = config.get("llm_config", {})
        system_prompt = llm_config.get(
            "system_prompt",
            "你是一位专业的道具设计师，擅长创作生动、独特的道具视觉描述。",
        )
        prompt_template = (
            llm_config.get("prompt_template") or _DEFAULT_PROP_PROMPT_TEMPLATE
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

    async def _generate_prop_image(
        self,
        description: str,
        name: str,
        config: Dict[str, Any],
        seed: int,
    ) -> str:
        """调用图片生成 API 为单个道具生成参考图（文生图模式）"""
        image_config = config.get("image_config", {})
        size = image_config.get("size", "768x1024")

        # 构建图片 prompt：道具名 + 视觉描述
        prompt = f"道具参考图 - {name}: {description}"

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
                logger.warning(f"[道具生成] 获取可用图片模型失败: {e}")
                model = ""

        # 通过 provider_registry 路由到对应 Provider 的 client（与 image_batch.py 一致）
        from app.services.provider_registry import provider_registry
        _img_client = await provider_registry.get_client_for_model(model)

        # 调用图片生成（道具参考图为文生图，不传参考图）
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
