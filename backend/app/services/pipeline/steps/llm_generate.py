# =====================================================
# LLM 文本生成步骤执行器
# 用于剧本生成、文案创作、对白生成等需要调用大模型的步骤
# =====================================================

import json
import logging
import re
from typing import Dict, Any, List, Optional

try:
    from json_repair import repair_json
    _HAS_JSON_REPAIR = True
except ImportError:
    _HAS_JSON_REPAIR = False

from app.services.pipeline.steps import register_step_executor
from app.services.pipeline.steps.base import BaseStepExecutor
from app.services.agnes_client import agnes_client
from app.services import script_template_service

logger = logging.getLogger("agnes_platform.pipeline")


@register_step_executor
class LlmGenerateExecutor(BaseStepExecutor):
    """
    LLM 文本生成步骤执行器

    调用大语言模型生成文本内容（剧本、文案、对白等），
    支持 JSON 输出解析和多层容错。
    """

    step_type = "llm_generate"

    async def validate(self) -> None:
        """验证输入"""
        # 检查是否有剧本模板或自定义 prompt
        config = self.config.get("config", {})
        use_script_template = config.get("use_script_template", False)

        if use_script_template:
            # 使用关联的剧本模板
            if not self.context.script_template:
                raise ValueError("配置了使用剧本模板但未加载剧本模板")
        else:
            # 直接使用 prompt_template（兼容旧字段名 prompt）
            prompt_template = config.get("prompt_template") or config.get("prompt") or ""
            if not prompt_template:
                raise ValueError("缺少 prompt_template 配置")
            # 统一字段名，避免 _build_prompts 重复处理
            if not config.get("prompt_template"):
                config["prompt_template"] = prompt_template

    async def execute(self) -> Dict[str, Any]:
        """执行 LLM 生成"""
        config = self.config.get("config", {})

        # 构建提示词
        system_prompt, user_prompt = self._build_prompts()

        # 调用 LLM
        logger.info(f"[LLM步骤] 开始生成: step_key={self.step_key}")

        try:
            response_text = await self._call_llm(system_prompt, user_prompt)
        except Exception as e:
            logger.error(f"[LLM步骤] 调用失败: {e}", exc_info=True)
            raise RuntimeError(f"LLM 调用失败: {e}") from e

        # 解析 JSON（如果配置了 json_output）
        parsed_result = None
        if config.get("json_output", True):
            try:
                parsed_result = self._parse_json_output(response_text)
            except Exception as e:
                logger.warning(f"[LLM步骤] JSON 解析失败，将保存原始文本: {e}")

        result = {
            "raw_response": response_text,
            "parsed_result": parsed_result,
            "model": config.get("model", "agnes-2.0-flash"),
        }

        logger.info(f"[LLM步骤] 完成: step_key={self.step_key}, parsed={parsed_result is not None}")
        return result

    async def estimate_credits(self) -> int:
        """预估积分消耗（LLM 消耗较少）"""
        return 5

    # ---------- 内部方法 ----------

    def _build_prompts(self) -> tuple[str, str]:
        """构建系统提示词和用户提示词"""
        config = self.config.get("config", {})

        # 系统提示词
        system_prompt = config.get(
            "system_prompt",
            "你是一位专业的创意内容创作者，擅长创作高质量的剧本、文案和故事。",
        )

        # 用户提示词（从剧本模板或配置中获取）
        if config.get("use_script_template", False) and self.context.script_template:
            # 使用剧本模板
            template_text = self.context.script_template.prompt_template
            variables = self._get_template_variables()
            user_prompt = script_template_service.render_prompt_template(
                template_text, variables
            )
        else:
            # 直接使用配置中的模板（兼容旧字段名 prompt）
            prompt_template = config.get("prompt_template") or config.get("prompt") or ""
            variables = self._get_template_variables()
            user_prompt = script_template_service.render_prompt_template(
                prompt_template, variables
            )

        return system_prompt, user_prompt

    def _get_template_variables(self) -> Dict[str, Any]:
        """获取模板变量"""
        variables = {
            "inputs": self.context.inputs,
            "theme": self.context.get_input("theme", ""),
            "scenes_count": self.context.get_input("scenes_count", 8),
            "style_name": "",
            "style_category": "",
        }

        # 风格信息
        if self.context.style:
            variables["style_name"] = self.context.style.name or ""
            variables["style_category"] = self.context.style.category or ""
            variables["style_description"] = self.context.style.description or ""

        # 上游步骤输出
        variables["steps"] = self.context.steps_output

        return variables

    async def _call_llm(self, system_prompt: str, user_prompt: str) -> str:
        """调用 LLM API"""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        try:
            response = await agnes_client.chat_completion(
                messages=messages,
                model="agnes-2.0-flash",
                temperature=0.8,
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
            # 如果 agnes_client 没有 chat_completion 方法，用简单的方式
            return await self._fallback_chat(messages)

    async def _fallback_chat(self, messages: List[Dict[str, str]]) -> str:
        """兜底的聊天调用（直接用 httpx）"""
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
                    "model": "agnes-2.0-flash",
                    "messages": messages,
                    "temperature": 0.8,
                    "stream": False,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("choices", [{}])[0].get("message", {}).get("content", "")

    def _parse_json_output(self, text: str) -> Dict[str, Any]:
        """
        从 LLM 输出中解析 JSON（多层容错）。

        容错策略:
        1. 直接 JSON.parse
        2. 去除 markdown 代码块（```json ... ```）
        3. 找到第一个 { 和最后一个 }，截取中间部分
        4. 去除尾部逗号（trailing comma）
        5. 使用 json_repair 库修复不规范的 JSON（字段值未加引号等 LLM 常见问题）
        """
        # 1. 直接解析
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # 2. 去除 markdown 代码块
        cleaned = text
        code_block_pattern = r"```(?:json)?\s*\n?([\s\S]*?)\n?```"
        matches = re.findall(code_block_pattern, text)
        if matches:
            cleaned = matches[-1].strip()
            try:
                return json.loads(cleaned)
            except json.JSONDecodeError:
                pass

        # 3. 找第一个 { 和最后一个 }
        first_brace = text.find("{")
        last_brace = text.rfind("}")
        if first_brace >= 0 and last_brace > first_brace:
            json_str = text[first_brace: last_brace + 1]
            try:
                return json.loads(json_str)
            except json.JSONDecodeError:
                # 4. 去除尾部逗号
                try:
                    fixed = re.sub(r",\s*([}\]])", r"\1", json_str)
                    return json.loads(fixed)
                except json.JSONDecodeError:
                    pass

        # 5. 终极容错：使用 json_repair 修复 LLM 常见的 JSON 格式问题
        #    如字段值未加引号、单引号、尾部多余逗号等
        if _HAS_JSON_REPAIR:
            try:
                repaired = repair_json(text, return_objects=True)
                if isinstance(repaired, (dict, list)):
                    logger.info(f"[LLM步骤] json_repair 修复成功")
                    return repaired
            except Exception as e:
                logger.debug(f"[LLM步骤] json_repair 也无法修复: {e}")

        raise ValueError("无法从 LLM 输出中解析 JSON")
