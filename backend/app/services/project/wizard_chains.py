# =====================================================
# 向导链预设 — 4 种场景的 4 步 LLM 链配置
#
# 每个向导链包含 4 个步骤:
#   1. script_generation:    剧本生成
#   2. entity_extraction:    实体提取（角色/场景/道具）
#   3. storyboard_split:     分镜拆分（注入实体清单，E2 模式）
#   4. frame_prompt_extract: 帧级绘画 prompt 提取
#
# 使用方式:
#   - 创建项目时根据模板的 category 字段查找对应 wizard_chain
#   - 存储到 template.steps_config JSON 字段（兼容现有表结构）
#   - run_wizard() 按顺序执行各步骤
# =====================================================

from typing import Dict, List, Any


# =====================================================
# 通用 4 步链路模板
# =====================================================

def _build_wizard_chain(
    *,
    script_prompt: str,
    entity_prompt: str,
    storyboard_prompt: str,
    frame_prompt: str,
    model: str = "",  # 空=运行时走解析链（项目所有者偏好 > 系统默认）
) -> List[Dict[str, Any]]:
    """构建 4 步 wizard_chain"""
    return [
        {
            "key": "script_generation",
            "name": "剧本生成",
            "type": "llm_generate",
            "config": {
                "prompt_template": script_prompt,
                "model": model,
                "temperature": 0.8,
            },
            "output_target": "project_scripts",
        },
        {
            "key": "entity_extraction",
            "name": "实体提取",
            "type": "llm_generate",
            "config": {
                "prompt_template": entity_prompt,
                "model": model,
                "temperature": 0.5,
            },
            "output_target": "project_characters+project_scenes+project_props",
            "depends_on": ["script_generation"],
        },
        {
            "key": "storyboard_split",
            "name": "分镜拆分",
            "type": "llm_generate",
            "config": {
                "prompt_template": storyboard_prompt,
                "model": model,
                "temperature": 0.6,
            },
            "output_target": "project_shots",
            "depends_on": ["entity_extraction"],
        },
        {
            "key": "frame_prompt_extract",
            "name": "帧 prompt 提取",
            "type": "llm_generate",
            "config": {
                "prompt_template": frame_prompt,
                "model": model,
                "temperature": 0.5,
            },
            "output_target": "project_shots.image_prompt",
            "depends_on": ["storyboard_split"],
        },
    ]


# =====================================================
# 预设向导链
# =====================================================

WIZARD_CHAINS: Dict[str, List[Dict[str, Any]]] = {
    # =================================================
    # 短剧（drama）
    # =================================================
    "drama": _build_wizard_chain(
        script_prompt=(
            "请根据以下主题生成一部短剧剧本：\n"
            "主题：{topic}\n"
            "风格：{style}\n"
            "集数：{episodes} 集\n"
            "单集时长：约 {duration_per_episode} 秒\n\n"
            "要求：\n"
            "1. 包含完整的故事弧线（起因/发展/高潮/结局）\n"
            "2. 每个场景有明确的地点、时间、人物、动作描述\n"
            "3. 包含主要角色的对话和旁白\n"
            "4. 输出纯文本剧本，不要附加说明\n"
        ),
        entity_prompt=(
            "请从以下剧本中提取所有角色、场景、道具清单，返回 JSON 格式：\n"
            "{\n"
            '  "characters": [{"name": "角色名", "description": "简介", '
            '"appearance_desc": "外观描述（用于生图）", "role_type": "main|supporting|minor"}],\n'
            '  "scenes": [{"name": "场景名", "description": "简介", '
            '"location": "地点", "time_of_day": "白天/夜晚/黄昏", "atmosphere": "氛围"}],\n'
            '  "props": [{"name": "道具名", "description": "简介", '
            '"visual_desc": "视觉描述（用于生图）"}]\n'
            "}\n\n"
            "剧本：\n{script}\n\n"
            "请确保 JSON 格式正确，不要附加其他说明。"
        ),
        storyboard_prompt=(
            "请基于以下剧本和已确认的实体清单，将剧本拆分为分镜列表，返回 JSON 格式：\n"
            "{\n"
            '  "shots": [\n'
            '    {"title": "分镜标题", "shot_type": "景别(特写/中景/全景)", '
            '"camera_movement": "运镜(推/拉/摇/移)", "angle": "视角(俯视/平视/仰视)", '
            '"dialogue": "台词/旁白", "visual_desc": "画面描述", '
            '"atmosphere": "氛围", "duration_ms": 3000, '
            '"scene_name": "场景名（从场景清单选择）", '
            '"characters_in_scene": ["角色名数组"], '
            '"props_in_scene": ["道具名数组"]}\n'
            "  ]\n"
            "}\n\n"
            "剧本：\n{script}\n\n"
            "可选角色清单：{characters}\n"
            "可选场景清单：{scenes}\n"
            "可选道具清单：{props}\n\n"
            "请确保 scene_name/characters_in_scene/props_in_scene 中的名称与清单完全匹配。"
        ),
        frame_prompt=(
            "请为以下每个分镜生成详细的英文绘画 prompt，用于 AI 图片生成。\n"
            "要求：\n"
            "1. 包含主体、场景、光照、构图、风格等细节\n"
            "2. 不要使用 SD 语法权重括号 (keyword:weight)\n"
            "3. 返回 JSON 格式：{\"shots\": [{\"id\": 分镜ID, \"image_prompt\": \"英文prompt\"}]}\n\n"
            "分镜列表：\n{shots}\n"
        ),
    ),

    # =================================================
    # 广告（ad）
    # =================================================
    "ad": _build_wizard_chain(
        script_prompt=(
            "请根据以下信息生成一份广告剧本：\n"
            "产品：{product}\n"
            "卖点：{selling_points}\n"
            "风格：{style}\n"
            "视频时长：约 {duration} 秒\n\n"
            "要求：\n"
            "1. 包含吸引眼球的开场（前 3 秒）\n"
            "2. 突出产品卖点和使用场景\n"
            "3. 包含明确的行动号召（CTA）\n"
            "4. 输出纯文本剧本\n"
        ),
        entity_prompt=(
            "请从以下广告剧本中提取所有角色、场景、道具清单，返回 JSON 格式：\n"
            "{\n"
            '  "characters": [{"name": "角色名", "description": "简介", '
            '"appearance_desc": "外观描述", "role_type": "main|supporting"}],\n'
            '  "scenes": [{"name": "场景名", "description": "简介", '
            '"location": "地点", "time_of_day": "时间段", "atmosphere": "氛围"}],\n'
            '  "props": [{"name": "产品/道具名", "description": "简介", '
            '"visual_desc": "视觉描述"}]\n'
            "}\n\n"
            "剧本：\n{script}\n"
        ),
        storyboard_prompt=(
            "请基于以下广告剧本和实体清单拆分分镜，返回 JSON 格式：\n"
            "{\n"
            '  "shots": [{"title": "标题", "shot_type": "景别", '
            '"camera_movement": "运镜", "angle": "视角", "dialogue": "台词", '
            '"visual_desc": "画面描述", "duration_ms": 2000, '
            '"scene_name": "场景名", "characters_in_scene": [], "props_in_scene": []}]\n'
            "}\n\n"
            "剧本：\n{script}\n\n"
            "可选角色：{characters}\n可选场景：{scenes}\n可选道具：{props}\n"
        ),
        frame_prompt=(
            "为以下广告分镜生成英文绘画 prompt，强调产品视觉冲击力：\n"
            "返回 JSON：{{\"shots\": [{{\"id\": ID, \"image_prompt\": \"prompt\"}}]}}\n\n"
            "分镜：\n{shots}\n"
        ),
    ),

    # =================================================
    # 教育（education）
    # =================================================
    "education": _build_wizard_chain(
        script_prompt=(
            "请根据以下信息生成一份教学课件剧本：\n"
            "教学主题：{topic}\n"
            "目标年级：{grade}\n"
            "课件风格：{style}\n"
            "视频时长：约 {duration} 分钟\n\n"
            "要求：\n"
            "1. 包含知识点拆解和例题讲解\n"
            "2. 语言通俗易懂，适合目标年级\n"
            "3. 包含互动提问环节\n"
            "4. 输出纯文本剧本\n"
        ),
        entity_prompt=(
            "请从以下教学剧本中提取角色、场景、道具（教具）清单，返回 JSON 格式：\n"
            "{\n"
            '  "characters": [{"name": "角色名", "description": "简介", '
            '"appearance_desc": "外观", "role_type": "main|supporting"}],\n'
            '  "scenes": [{"name": "场景名", "description": "简介", '
            '"location": "地点", "time_of_day": "", "atmosphere": "氛围"}],\n'
            '  "props": [{"name": "教具名", "description": "简介", '
            '"visual_desc": "视觉描述"}]\n'
            "}\n\n"
            "剧本：\n{script}\n"
        ),
        storyboard_prompt=(
            "请基于以下教学剧本和实体清单拆分分镜，返回 JSON 格式：\n"
            "每个分镜对应一个知识点或例题片段。\n\n"
            "剧本：\n{script}\n\n"
            "可选角色：{characters}\n可选场景：{scenes}\n可选道具：{props}\n"
        ),
        frame_prompt=(
            "为以下教学分镜生成英文绘画 prompt，强调教学内容的可视化：\n"
            "返回 JSON：{{\"shots\": [{{\"id\": ID, \"image_prompt\": \"prompt\"}}]}}\n\n"
            "分镜：\n{shots}\n"
        ),
    ),

    # =================================================
    # 动漫（anime）
    # =================================================
    "anime": _build_wizard_chain(
        script_prompt=(
            "请根据以下信息生成一份动漫剧本：\n"
            "主角设定：{character}\n"
            "画风：{style}\n"
            "故事背景：{story}\n"
            "图片数量：{num_images} 张\n\n"
            "要求：\n"
            "1. 围绕主角展开故事\n"
            "2. 每个场景有丰富的视觉描述\n"
            "3. 包含角色的情感和动作描写\n"
            "4. 输出纯文本剧本\n"
        ),
        entity_prompt=(
            "请从以下动漫剧本中提取角色、场景、道具清单，返回 JSON 格式：\n"
            "特别注意提取主角的详细外观描述（发色/瞳色/服装等）\n\n"
            "剧本：\n{script}\n"
        ),
        storyboard_prompt=(
            "请基于以下动漫剧本和实体清单拆分分镜，返回 JSON 格式：\n"
            "每个分镜要有强烈的画面感和情感表达\n\n"
            "剧本：\n{script}\n\n"
            "可选角色：{characters}\n可选场景：{scenes}\n可选道具：{props}\n"
        ),
        frame_prompt=(
            "为以下动漫分镜生成英文绘画 prompt，强调动漫风格的视觉表现力：\n"
            "返回 JSON：{{\"shots\": [{{\"id\": ID, \"image_prompt\": \"prompt\"}}]}}\n\n"
            "分镜：\n{shots}\n"
        ),
    ),
}


# =====================================================
# 默认向导链（无匹配 category 时使用）
# =====================================================

DEFAULT_WIZARD_CHAIN = WIZARD_CHAINS["drama"]


def get_wizard_chain(category: str) -> List[Dict[str, Any]]:
    """
    根据模板 category 获取对应的 wizard_chain

    Args:
        category: 模板分类（drama/ad/education/anime 等）
    Returns:
        wizard_chain 配置（4 步 LLM 链）
    """
    return WIZARD_CHAINS.get(category, DEFAULT_WIZARD_CHAIN)


def is_wizard_chain(steps_config: Any) -> bool:
    """
    判断 steps_config 是否已经是 wizard_chain 格式

    wizard_chain 格式特征:
    - 是 list
    - 第一个元素的 key 是 script_generation/entity_extraction/storyboard_split/frame_prompt_extract 之一
    """
    if not isinstance(steps_config, list) or not steps_config:
        return False
    first = steps_config[0]
    if not isinstance(first, dict):
        return False
    return first.get("key") in {
        "script_generation",
        "entity_extraction",
        "storyboard_split",
        "frame_prompt_extract",
    }
