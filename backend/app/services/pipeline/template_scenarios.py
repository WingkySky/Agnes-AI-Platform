# =====================================================
# 模板场景预设
# 定义常见创作场景的模板配置，让用户通过简单问答创建模板
#
# Task 9 改造：steps_config_template 已替换为 wizard_chain 结构
#（4 步 LLM 链：剧本生成 → 实体提取 → 分镜拆分 → 帧 prompt 提取）
# 与项目制创作 wizard.py 完全对齐，旧 PipelineRun 步骤链已废弃
# =====================================================

from typing import List, Dict, Any, Union

from app.services.project.wizard_chains import (
    WIZARD_CHAINS,
    DEFAULT_WIZARD_CHAIN,
    is_wizard_chain,
)


# =====================================================
# 场景预设列表
# 每个 scenario 包含：
#   - key/name/description/icon/color/category/i18n_key: 元数据
#   - inputs_config: 用户输入参数定义（前端表单）
#   - steps_config_template: wizard_chain 4 步 LLM 链（引用 wizard_chains 预设）
# =====================================================
TEMPLATE_SCENARIOS: List[Dict[str, Any]] = [
    {
        "key": "drama",
        "name": "Drama Generation",
        "description": "Input a story theme to auto-generate storyboard images and videos, suitable for short dramas and comics.",
        "icon": "film",
        "color": "#e74c3c",
        "category": "drama",
        "i18n_key": "drama",
        "inputs_config": [
            {"key": "topic", "label_i18n": "topic_label", "label": "Story Theme", "type": "text", "required": True, "default": "", "placeholder_i18n": "topic_ph", "placeholder": "e.g. Modern urban romance story"},
            {"key": "style", "label_i18n": "style_label", "label": "Art Style", "type": "select", "required": True, "default": "realistic",
             "options": [{"label": "Realistic", "value": "realistic"}, {"label": "Anime", "value": "anime"}, {"label": "Ink Wash", "value": "ink"}, {"label": "Cyberpunk", "value": "cyberpunk"}],
             "options_i18n_prefix": "style_opt_"},
            {"key": "episodes", "label_i18n": "episodes_label", "label": "Episodes", "type": "number", "required": False, "default": 1, "min": 1, "max": 10},
            {"key": "duration_per_episode", "label_i18n": "duration_label", "label": "Duration per Episode (sec)", "type": "number", "required": False, "default": 30, "min": 10, "max": 300},
        ],
        # wizard_chain 4 步链路（剧本 → 实体 → 分镜 → 帧 prompt）
        # prompt 中的占位符由 wizard.py 运行时用 inputs 渲染
        "steps_config_template": WIZARD_CHAINS["drama"],
        "estimated_credits": 150,
        "estimated_time_minutes": 15,
    },
    {
        "key": "ad",
        "name": "Ad Creation",
        "description": "Input product info to auto-generate ad copy, images and videos, suitable for e-commerce and brand promotion.",
        "icon": "megaphone",
        "color": "#3498db",
        "category": "ad",
        "i18n_key": "ad",
        "inputs_config": [
            {"key": "product", "label_i18n": "product_label", "label": "Product Name", "type": "text", "required": True, "default": "", "placeholder_i18n": "product_ph", "placeholder": "e.g. New smartphone"},
            {"key": "selling_points", "label_i18n": "selling_points_label", "label": "Selling Points", "type": "text", "required": True, "default": "", "placeholder_i18n": "selling_points_ph", "placeholder": "e.g. Long battery, HD camera"},
            {"key": "style", "label_i18n": "style_label", "label": "Ad Style", "type": "select", "required": True, "default": "modern",
             "options": [{"label": "Modern", "value": "modern"}, {"label": "Vintage", "value": "vintage"}, {"label": "Tech", "value": "tech"}, {"label": "Warm", "value": "warm"}],
             "options_i18n_prefix": "style_opt_"},
            {"key": "duration", "label_i18n": "duration_label", "label": "Video Duration (sec)", "type": "number", "required": False, "default": 30, "min": 10, "max": 120},
        ],
        "steps_config_template": WIZARD_CHAINS["ad"],
        "estimated_credits": 100,
        "estimated_time_minutes": 10,
    },
    {
        "key": "education",
        "name": "Educational Courseware",
        "description": "Input a teaching topic to auto-generate courseware content, images and explainer videos, suitable for online education and training.",
        "icon": "graduation-cap",
        "color": "#2ecc71",
        "category": "education",
        "i18n_key": "education",
        "inputs_config": [
            {"key": "topic", "label_i18n": "topic_label", "label": "Teaching Topic", "type": "text", "required": True, "default": "", "placeholder_i18n": "topic_ph", "placeholder": "e.g. Python programming basics"},
            {"key": "grade", "label_i18n": "grade_label", "label": "Target Grade", "type": "select", "required": False, "default": "high_school",
             "options": [{"label": "Elementary School", "value": "elementary"}, {"label": "Middle School", "value": "middle"}, {"label": "High School", "value": "high_school"}, {"label": "College", "value": "college"}, {"label": "Vocational", "value": "vocational"}],
             "options_i18n_prefix": "grade_opt_"},
            {"key": "style", "label_i18n": "style_label", "label": "Courseware Style", "type": "select", "required": False, "default": "clean",
             "options": [{"label": "Clean & Minimal", "value": "clean"}, {"label": "Lively & Colorful", "value": "lively"}, {"label": "Interactive", "value": "interactive"}],
             "options_i18n_prefix": "course_style_opt_"},
            {"key": "duration", "label_i18n": "duration_label", "label": "Video Duration (min)", "type": "number", "required": False, "default": 5, "min": 1, "max": 30},
        ],
        "steps_config_template": WIZARD_CHAINS["education"],
        "estimated_credits": 80,
        "estimated_time_minutes": 12,
    },
    {
        "key": "anime",
        "name": "Anime Creation",
        "description": "Input character design to auto-generate anime-style character images and videos.",
        "icon": "star",
        "color": "#9b59b6",
        "category": "art",
        "i18n_key": "anime",
        "inputs_config": [
            {"key": "character", "label_i18n": "character_label", "label": "Character Description", "type": "text", "required": True, "default": "", "placeholder_i18n": "character_ph", "placeholder": "e.g. Silver-haired girl, blue eyes, futuristic uniform"},
            {"key": "style", "label_i18n": "style_label", "label": "Art Style", "type": "select", "required": True, "default": "japanese",
             "options": [{"label": "Japanese Anime", "value": "japanese"}, {"label": "American Comic", "value": "american"}, {"label": "Chinese Style", "value": "chinese"}, {"label": "European Art", "value": "european"}],
             "options_i18n_prefix": "art_style_opt_"},
            {"key": "story", "label_i18n": "story_label", "label": "Story Background", "type": "text", "required": False, "default": "", "placeholder_i18n": "story_ph", "placeholder": "Optional: Character story background"},
            {"key": "num_images", "label_i18n": "num_images_label", "label": "Number of Images", "type": "number", "required": False, "default": 4, "min": 1, "max": 20},
        ],
        "steps_config_template": WIZARD_CHAINS["anime"],
        "estimated_credits": 120,
        "estimated_time_minutes": 8,
    },
]


def get_scenario_by_key(key: str) -> Dict[str, Any] | None:
    """根据 key 获取场景预设"""
    for scenario in TEMPLATE_SCENARIOS:
        if scenario["key"] == key:
            return scenario
    return None


def render_steps_config(
    scenario: Union[Dict[str, Any], str],
    inputs: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    根据用户输入渲染步骤配置（wizard_chain 格式）。

    wizard_chain 的 prompt_template 中的 {placeholder} 占位符
    在向导执行时由 wizard.py 的 _call_llm 用 inputs 渲染，
    所以这里直接返回 wizard_chain 原始配置，不做字符串替换。

    Args:
        scenario: 场景字典或场景 key
        inputs: 用户输入参数（保留接口兼容，当前不使用）
    """
    if isinstance(scenario, str):
        scenario = get_scenario_by_key(scenario)
        if not scenario:
            raise ValueError(f"场景不存在: {scenario}")

    # wizard_chain 是 list，直接返回拷贝
    steps = scenario.get("steps_config_template", [])
    if not is_wizard_chain(steps):
        # 兜底：如果不是 wizard_chain 格式，返回默认链
        return list(DEFAULT_WIZARD_CHAIN)
    return [dict(step) for step in steps]
