# =====================================================
# 创意工坊模板校验 & 示例文件
#
# 提供:
#   - get_sample_template(): 返回标准漫剧示例 JSON（供前端下载）
#   - validate_template():   无副作用校验模板结构（不落库、不启动运行）
#
# 所有 step.type 校验以 backend/app/services/pipeline/steps/__init__.py
# 的注册表为准，避免再次出现 image_gen/video_gen/composite 等历史误名。
# =====================================================

from datetime import datetime
from typing import Any, Dict, List, Tuple

from app.services.pipeline.steps import list_registered_steps

# 导出文件格式版本（与 routes/pipeline.py 的 TEMPLATE_EXPORT_VERSION 保持一致）
TEMPLATE_EXPORT_VERSION = "1.0"


def _registered_step_types() -> set:
    """获取后端已注册的所有 step_type（权威清单来源）"""
    return set(list_registered_steps().keys())


def get_sample_template() -> Dict[str, Any]:
    """
    返回一份最小可用的示例模板 JSON。

    结构与 /api/pipeline/export/templates 的导出格式完全一致，
    用户可直接保存为 .json 然后通过 /api/pipeline/templates/import 导入。
    """
    return {
        "version": TEMPLATE_EXPORT_VERSION,
        "exported_at": datetime.utcnow().isoformat() + "Z",
        "templates": [
            {
                "key": "example_standard_drama",
                "name": "示例 · 标准漫剧",
                "description": "剧本 → 分镜 → 视频 → 合成（最小可用示例，可直接导入）",
                "category": "drama",
                "tags": ["示例", "漫剧"],
                "inputs_config": [
                    {
                        "key": "theme",
                        "label": "主题",
                        "type": "text",
                        "required": True,
                        "default": "",
                    }
                ],
                "steps_config": [
                    {
                        "key": "step_0",
                        "name": "剧本生成",
                        "type": "llm_generate",
                        "depends_on": [],
                        "config": {
                            "prompt_template": "根据主题 {{theme}} 生成 8 个分镜剧本，输出 JSON 数组，每个元素含 prompt 字段",
                            "model": "agnes-2.0-flash",
                            "temperature": 0.8,
                            "max_tokens": 2048,
                            "output_format": "json",
                        },
                    },
                    {
                        "key": "step_1",
                        "name": "分镜绘制",
                        "type": "image_batch",
                        "depends_on": ["step_0"],
                        "config": {
                            "from_step": "step_0",
                            "prompt_field": "prompt",
                            "model": "agnes-image-1.0",
                            "size": "1024x1024",
                            "batch_size": 8,
                        },
                    },
                    {
                        "key": "step_2",
                        "name": "视频生成",
                        "type": "video_batch",
                        "depends_on": ["step_1"],
                        "config": {
                            "from_step": "step_1",
                            "model": "agnes-video-1.0",
                            "seconds": 5,
                            "aspect_ratio": "16:9",
                        },
                    },
                    {
                        "key": "step_3",
                        "name": "成片合成",
                        "type": "ffmpeg_composite",
                        "depends_on": ["step_2"],
                        "config": {
                            "from_step": "step_2",
                            "with_subtitle": False,
                            "audio_from_step": None,
                            "subtitle_from_step": None,
                        },
                    },
                ],
                "output_mapping": None,
                "is_public": False,
            }
        ],
        "script_templates": [],
        "style_presets": [],
    }


def validate_template(template_data: Dict[str, Any]) -> Tuple[bool, List[Dict[str, Any]]]:
    """
    无副作用校验模板结构（不落库、不启动运行、不实例化执行器）。

    检查项:
      - steps_config 每个 step.type 必须命中后端注册表
      - step.key 必须非空且在同模板内唯一
      - depends_on 引用的 key 必须存在于同模板内
      - from_step / audio_from_step / subtitle_from_step 同样校验存在性

    Args:
        template_data: 完整模板 dict（可含 key/name/steps_config 等字段）

    Returns:
        (is_valid, errors)
        errors 形如 [{step_key, field, reason}]
    """
    errors: List[Dict[str, Any]] = []
    registered_types = _registered_step_types()

    steps = template_data.get("steps_config") or []
    if not isinstance(steps, list) or not steps:
        return False, [
            {
                "step_key": None,
                "field": "steps_config",
                "reason": "steps_config 不能为空",
            }
        ]

    # 第一遍：收集 key 集合，校验 type / key 唯一性
    seen_keys: set = set()
    duplicate_keys: set = set()
    for step in steps:
        if not isinstance(step, dict):
            errors.append(
                {"step_key": None, "field": "step", "reason": "step 必须是对象"}
            )
            continue

        key = step.get("key")
        if not key:
            errors.append(
                {"step_key": None, "field": "key", "reason": "步骤缺少 key"}
            )
            continue

        if key in seen_keys:
            duplicate_keys.add(key)
        seen_keys.add(key)

        step_type = step.get("type")
        if not step_type:
            errors.append(
                {
                    "step_key": key,
                    "field": "type",
                    "reason": f"步骤 {key} 缺少 type 字段，请参考 docs/workshop-template-format.md",
                }
            )
        elif step_type not in registered_types:
            errors.append(
                {
                    "step_key": key,
                    "field": "type",
                    "reason": (
                        f"未知步骤类型 '{step_type}'，已注册类型: "
                        f"{', '.join(sorted(registered_types))}。"
                        f"请参考 docs/workshop-template-format.md"
                    ),
                }
            )

    # 重复 key 错误（去重后只报一次）
    for k in duplicate_keys:
        errors.append(
            {
                "step_key": k,
                "field": "key",
                "reason": f"步骤 key 重复: {k}",
            }
        )

    # 第二遍：校验 depends_on 和 from_step 引用（依赖 key 存在性）
    for step in steps:
        if not isinstance(step, dict):
            continue
        key = step.get("key") or "<unknown>"
        config = step.get("config") or {}

        # depends_on
        depends_on = step.get("depends_on") or []
        if isinstance(depends_on, list):
            for dep in depends_on:
                if dep not in seen_keys:
                    errors.append(
                        {
                            "step_key": key,
                            "field": "depends_on",
                            "reason": f"depends_on 引用了不存在的步骤 key: {dep}",
                        }
                    )

        # from_step（数据来源引用，常用于 image_batch/video_batch/tts_generate/ffmpeg_composite）
        from_step = config.get("from_step")
        if from_step and from_step not in seen_keys:
            errors.append(
                {
                    "step_key": key,
                    "field": "from_step",
                    "reason": f"from_step 引用了不存在的步骤 key: {from_step}",
                }
            )

        # audio_from_step（ffmpeg_composite 可选）
        audio_from = config.get("audio_from_step")
        if audio_from and audio_from not in seen_keys:
            errors.append(
                {
                    "step_key": key,
                    "field": "audio_from_step",
                    "reason": f"audio_from_step 引用了不存在的步骤 key: {audio_from}",
                }
            )

        # subtitle_from_step（ffmpeg_composite 可选）
        subtitle_from = config.get("subtitle_from_step")
        if subtitle_from and subtitle_from not in seen_keys:
            errors.append(
                {
                    "step_key": key,
                    "field": "subtitle_from_step",
                    "reason": f"subtitle_from_step 引用了不存在的步骤 key: {subtitle_from}",
                }
            )

    return (len(errors) == 0), errors


def infer_output_mapping(steps_config: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    当 output_mapping 为 null/空时，按步骤顺序推断最终产物。

    规则:
      - 取最后一个 ffmpeg_composite 步骤的输出作为最终产物
      - 无 ffmpeg_composite 时取最后一个 video_batch
      - 都没有则返回 None（纯文本/图片流程，无最终视频）

    Args:
        steps_config: 有序的 steps 列表

    Returns:
        推断出的 output_mapping dict，或 None
    """
    if not steps_config:
        return None

    # 倒序找最后一个 ffmpeg_composite
    for step in reversed(steps_config):
        if (step.get("type") or "").lower() == "ffmpeg_composite":
            return {
                "final_video": f"steps.{step.get('key')}.output.final_video",
                "source_step": step.get("key"),
                "source_type": "ffmpeg_composite",
            }

    # 倒序找最后一个 video_batch
    for step in reversed(steps_config):
        if (step.get("type") or "").lower() == "video_batch":
            return {
                "final_video": f"steps.{step.get('key')}.output.videos",
                "source_step": step.get("key"),
                "source_type": "video_batch",
            }

    return None
