# =====================================================
# 项目创建向导 — 按模板 wizard_chain 顺序执行 LLM 链
#
# 4 步链路（D2）:
#   1. script_generation:    剧本生成
#   2. entity_extraction:    从剧本提取角色/场景/道具清单
#   3. storyboard_split:     基于已确认实体清单拆分分镜（E2）
#   4. frame_prompt_extract: 为每个分镜提取帧级绘画 prompt（可选）
#
# 关键特性:
#   - parse_json_loose: 宽松 JSON 解析（容错代码块包裹/字段缺失/尾部逗号）
#   - 单步失败重试 2 次
#   - 每步立即落库
#   - SSE 推送进度
#   - 支持从失败步骤 resume
# =====================================================

import json
import re
import logging
from typing import Dict, Any, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import (
    Project,
    ProjectScript,
    ProjectCharacter,
    ProjectScene,
    ProjectProp,
    ProjectShot,
    ProjectShotCharacter,
    ProjectShotProp,
    PROJECT_STATUS_IN_PROGRESS,
)
from app.services.agnes_client import agnes_client
from app.services.project.sse_manager import project_sse_manager

logger = logging.getLogger("agnes_platform.project.wizard")


# =====================================================
# 工具函数
# =====================================================

def parse_json_loose(text: str) -> Any:
    """
    宽松 JSON 解析:
    - 去除 markdown 代码块包裹
    - 提取首个 { ... } 或 [ ... ] 块
    - 容忍尾部逗号
    """
    if not text:
        return {}
    # 去除 markdown 代码块
    text = re.sub(r"```(?:json)?\s*", "", text)
    text = text.replace("```", "")
    text = text.strip()
    # 尝试直接解析
    try:
        return json.loads(text)
    except Exception:
        pass
    # 提取首个 JSON 对象/数组
    for start_char, end_char in [("{", "}"), ("[", "]")]:
        start = text.find(start_char)
        end = text.rfind(end_char)
        if start != -1 and end != -1 and end > start:
            fragment = text[start:end + 1]
            # 去除尾部逗号
            fragment = re.sub(r",\s*([}\]])", r"\1", fragment)
            try:
                return json.loads(fragment)
            except Exception:
                continue
    return {}


async def _call_llm(prompt: str, model: str = "", temperature: float = 0.7) -> str:
    """调用 LLM 返回文本（通过 AgnesAIClient._post 走 chat/completions）"""
    body = {
        "model": model or "agnes-2.0-flash",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
    }
    result = await agnes_client._post(
        f"{agnes_client.base_url}/chat/completions", body
    )
    choices = result.get("choices", [])
    if not choices:
        raise RuntimeError("LLM 返回为空")
    return choices[0].get("message", {}).get("content", "") or ""


# =====================================================
# 步骤执行器
# =====================================================

async def _step_script_generation(
    db: AsyncSession, project: Project, step_config: dict, inputs: dict
) -> dict:
    """步骤 1: 剧本生成"""
    prompt = step_config["prompt_template"].format(**inputs)
    content = await _call_llm(
        prompt, step_config.get("model"), step_config.get("temperature", 0.8)
    )

    script = ProjectScript(
        project_id=project.id,
        episode_no=1,
        title=inputs.get("topic", "默认剧集"),
        content=content,
        model=step_config.get("model"),
        prompt_template=step_config["prompt_template"],
        status="approved",
    )
    db.add(script)
    await db.commit()
    await db.refresh(script)
    return {"script_id": script.id, "content": content}


async def _step_entity_extraction(
    db: AsyncSession, project: Project, step_config: dict, context: dict
) -> dict:
    """步骤 2: 从剧本提取角色/场景/道具清单"""
    script_content = context.get("script_generation", {}).get("content", "")
    prompt = step_config["prompt_template"].format(script=script_content)
    result_text = await _call_llm(
        prompt, step_config.get("model"), step_config.get("temperature", 0.5)
    )
    parsed = parse_json_loose(result_text)

    stats = {"characters": 0, "scenes": 0, "props": 0}

    # 批量写入角色
    for item in parsed.get("characters", []):
        char = ProjectCharacter(
            project_id=project.id,
            name=item.get("name", "未命名"),
            description=item.get("description", ""),
            appearance_desc=item.get(
                "appearance_desc", item.get("description", "")
            ),
            role_type=item.get("role_type", "supporting"),
        )
        db.add(char)
        stats["characters"] += 1

    # 批量写入场景
    for item in parsed.get("scenes", []):
        scene = ProjectScene(
            project_id=project.id,
            name=item.get("name", "未命名场景"),
            description=item.get("description", ""),
            location=item.get("location", ""),
            time_of_day=item.get("time_of_day", ""),
            atmosphere=item.get("atmosphere", ""),
        )
        db.add(scene)
        stats["scenes"] += 1

    # 批量写入道具
    for item in parsed.get("props", []):
        prop = ProjectProp(
            project_id=project.id,
            name=item.get("name", "未命名道具"),
            description=item.get("description", ""),
            visual_desc=item.get("visual_desc", item.get("description", "")),
        )
        db.add(prop)
        stats["props"] += 1

    await db.commit()
    return stats


async def _step_storyboard_split(
    db: AsyncSession, project: Project, step_config: dict, context: dict
) -> dict:
    """步骤 3: 基于已确认实体清单拆分分镜（E2 - 注入 charList/sceneList/propList）"""
    script_content = context.get("script_generation", {}).get("content", "")

    # 注入实体清单
    chars = (
        await db.execute(
            select(ProjectCharacter).where(ProjectCharacter.project_id == project.id)
        )
    ).scalars().all()
    scenes = (
        await db.execute(
            select(ProjectScene).where(ProjectScene.project_id == project.id)
        )
    ).scalars().all()
    props = (
        await db.execute(
            select(ProjectProp).where(ProjectProp.project_id == project.id)
        )
    ).scalars().all()

    char_info = json.dumps(
        [{"id": c.id, "name": c.name, "desc": c.description} for c in chars],
        ensure_ascii=False,
    )
    scene_info = json.dumps(
        [{"id": s.id, "name": s.name, "desc": s.description} for s in scenes],
        ensure_ascii=False,
    )
    prop_info = json.dumps(
        [{"id": p.id, "name": p.name, "desc": p.description} for p in props],
        ensure_ascii=False,
    )

    prompt = step_config["prompt_template"].format(
        script=script_content,
        characters=char_info,
        scenes=scene_info,
        props=prop_info,
    )
    result_text = await _call_llm(
        prompt, step_config.get("model"), step_config.get("temperature", 0.6)
    )
    parsed = parse_json_loose(result_text)

    # 构建实体名 → id 映射（用于按名匹配绑定）
    char_map = {c.name: c.id for c in chars}
    scene_map = {s.name: s.id for s in scenes}
    prop_map = {p.name: p.id for p in props}

    count = 0
    for idx, shot_data in enumerate(
        parsed.get("shots", parsed.get("storyboard", [])), start=1
    ):
        shot = ProjectShot(
            project_id=project.id,
            sequence_no=idx,
            sort_order=idx - 1,
            title=shot_data.get("title", f"分镜 {idx}"),
            shot_type=shot_data.get("shot_type", ""),
            camera_movement=shot_data.get("camera_movement", ""),
            angle=shot_data.get("angle", ""),
            dialogue=shot_data.get("dialogue", ""),
            visual_desc=shot_data.get(
                "visual_desc", shot_data.get("image_prompt", "")
            ),
            atmosphere=shot_data.get("atmosphere", ""),
            image_prompt=shot_data.get(
                "image_prompt", shot_data.get("visual_desc", "")
            ),
            duration_ms=shot_data.get("duration_ms", 3000),
            scene_id=scene_map.get(shot_data.get("scene_name", "")),
            status="draft",
        )
        db.add(shot)
        await db.flush()  # 获取 shot.id

        # 绑定角色
        for char_name in shot_data.get("characters_in_scene", []):
            cid = char_map.get(char_name)
            if cid:
                db.add(
                    ProjectShotCharacter(shot_id=shot.id, character_id=cid)
                )

        # 绑定道具
        for prop_name in shot_data.get("props_in_scene", []):
            pid = prop_map.get(prop_name)
            if pid:
                db.add(ProjectShotProp(shot_id=shot.id, prop_id=pid))

        count += 1

    await db.commit()
    return {"shots": count}


async def _step_frame_prompt_extract(
    db: AsyncSession, project: Project, step_config: dict, context: dict
) -> dict:
    """步骤 4: 为每个分镜提取帧级绘画 prompt（可选，用于优化生图质量）"""
    shots = (
        await db.execute(
            select(ProjectShot)
            .where(ProjectShot.project_id == project.id)
            .order_by(ProjectShot.sequence_no)
        )
    ).scalars().all()

    if not shots:
        return {"updated": 0}

    # 构建分镜概览
    shots_summary = json.dumps(
        [
            {
                "id": s.id,
                "title": s.title,
                "visual_desc": s.visual_desc,
                "dialogue": s.dialogue,
            }
            for s in shots
        ],
        ensure_ascii=False,
    )

    prompt = step_config["prompt_template"].format(shots=shots_summary)
    result_text = await _call_llm(
        prompt, step_config.get("model"), step_config.get("temperature", 0.5)
    )
    parsed = parse_json_loose(result_text)

    updated = 0
    prompts_map = {
        item["id"]: item.get("image_prompt", "")
        for item in parsed.get("shots", [])
        if "id" in item
    }
    for shot in shots:
        new_prompt = prompts_map.get(shot.id)
        if new_prompt and new_prompt != shot.image_prompt:
            shot.image_prompt = new_prompt
            updated += 1

    await db.commit()
    return {"updated": updated}


# 步骤执行器映射
STEP_EXECUTORS = {
    "script_generation": _step_script_generation,
    "entity_extraction": _step_entity_extraction,
    "storyboard_split": _step_storyboard_split,
    "frame_prompt_extract": _step_frame_prompt_extract,
}


# =====================================================
# 向导主流程
# =====================================================

async def run_wizard(
    db: AsyncSession,
    project: Project,
    wizard_chain: List[dict],
    inputs: dict,
    resume_from: str = "",
) -> Project:
    """
    执行项目创建向导 LLM 链

    参数:
    - project: 项目对象（status=creating）
    - wizard_chain: 向导链配置（来自模板的 steps_config）
    - inputs: 用户输入参数
    - resume_from: 从指定 step key 恢复（空字符串表示从头开始）
    """
    context = {"inputs": inputs}
    started = not resume_from

    for step in wizard_chain:
        step_key = step["key"]
        if not started:
            if step_key == resume_from:
                started = True
            else:
                continue

        await project_sse_manager.push(
            project.id,
            "wizard_step_started",
            {"step": step_key, "name": step.get("name", step_key)},
        )

        executor = STEP_EXECUTORS.get(step_key)
        if not executor:
            # 未知步骤类型，跳过
            continue

        # 重试 2 次
        last_err: Optional[Exception] = None
        for attempt in range(2):
            try:
                result = await executor(
                    db, project, step.get("config", step), context
                )
                context[step_key] = result
                await project_sse_manager.push(
                    project.id,
                    "wizard_step_completed",
                    {"step": step_key, "stats": result},
                )
                last_err = None
                break
            except Exception as e:
                last_err = e
                logger.warning(
                    f"向导步骤 {step_key} 第 {attempt + 1} 次失败: {e}"
                )

        if last_err:
            await project_sse_manager.push(
                project.id,
                "wizard_step_failed",
                {"step": step_key, "error": str(last_err)},
            )
            # 部分成功保留，不中断向导
            logger.error(f"向导步骤 {step_key} 最终失败: {last_err}")

    # 向导完成，状态 → in_progress
    project.status = PROJECT_STATUS_IN_PROGRESS
    await db.commit()
    await db.refresh(project)

    await project_sse_manager.push(
        project.id,
        "wizard_completed",
        {"project_id": project.id, "status": "in_progress"},
    )
    return project
