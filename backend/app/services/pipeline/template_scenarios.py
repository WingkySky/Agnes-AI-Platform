# =====================================================
# 模板场景预设
# 定义常见创作场景的模板配置，让用户通过简单问答创建模板
# =====================================================

from typing import List, Dict, Any, Union
from datetime import datetime


# 场景预设列表
TEMPLATE_SCENARIOS = [
    {
        "key": "drama",
        "name": "Drama Generation",
        "description": "Input a story theme to auto-generate storyboard images and videos, suitable for short dramas and comics.",
        "icon": "film",
        "color": "#e74c3c",
        "category": "drama",
        # i18n 翻译键前缀（前端用于查找对应语言的翻译）
        "i18n_key": "drama",
        # 用户输入参数定义（label/placeholder/options 均为英文 fallback，前端用 i18n_key 查找翻译）
        "inputs_config": [
            {"key": "topic", "label_i18n": "topic_label", "label": "Story Theme", "type": "text", "required": True, "default": "", "placeholder_i18n": "topic_ph", "placeholder": "e.g. Modern urban romance story"},
            {"key": "style", "label_i18n": "style_label", "label": "Art Style", "type": "select", "required": True, "default": "realistic",
             "options": [{"label": "Realistic", "value": "realistic"}, {"label": "Anime", "value": "anime"}, {"label": "Ink Wash", "value": "ink"}, {"label": "Cyberpunk", "value": "cyberpunk"}],
             "options_i18n_prefix": "style_opt_"},
            {"key": "episodes", "label_i18n": "episodes_label", "label": "Episodes", "type": "number", "required": False, "default": 1, "min": 1, "max": 10},
            {"key": "duration_per_episode", "label_i18n": "duration_label", "label": "Duration per Episode (sec)", "type": "number", "required": False, "default": 30, "min": 10, "max": 300},
        ],
        # 步骤配置模板（name 为英文 fallback，name_i18n 用于前端翻译）
        "steps_config_template": [
            {
                "key": "step_script",
                "name": "Script Generation",
                "name_i18n": "step_script",
                "type": "llm_generate",
                "depends_on": [],
                "config_template": {
                    "prompt_template": "根据以下主题生成{description}风格的短剧剧本：{topic}\n集数：{episodes}集\n单集时长：{duration_per_episode}秒\n\n请生成详细的剧本大纲和关键场景描述。",
                    "model": "agnes-2.0-flash",
                    "temperature": 0.8,
                },
            },
            {
                "key": "step_storyboard",
                "name": "Storyboard Generation",
                "name_i18n": "step_storyboard",
                "type": "llm_generate",
                "depends_on": ["step_script"],
                "config_template": {
                    "prompt_template": "根据以下剧本生成分镜描述：\n{base_prompt}\n\n请为每个关键场景生成详细的画面描述，包括：场景、人物、动作、镜头角度。",
                    "model": "agnes-2.0-flash",
                    "temperature": 0.7,
                },
            },
            {
                "key": "step_image",
                "name": "Generate Storyboard Images",
                "name_i18n": "step_image",
                "type": "image_gen",
                "depends_on": ["step_storyboard"],
                "config_template": {
                    "prompt_from_step": "step_storyboard",
                    "model": "agnes-2.0-flash",
                    "size": "1024x1024",
                    "style": "{style}",
                },
            },
            {
                "key": "step_video",
                "name": "Generate Video",
                "name_i18n": "step_video",
                "type": "video_gen",
                "depends_on": ["step_image"],
                "config_template": {
                    "prompt_from_step": "step_storyboard",
                    "model": "agnes-video-1.0",
                    "seconds": "{duration_per_episode}",
                    "aspect_ratio": "16:9",
                },
            },
            {
                "key": "step_composite",
                "name": "Composite Output",
                "name_i18n": "step_composite",
                "type": "composite",
                "depends_on": ["step_video"],
                "config_template": {
                    "output_format": "mp4",
                    "quality": "high",
                },
            },
        ],
        # 预估积分（会自动重新计算）
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
        "steps_config_template": [
            {
                "key": "step_copywrite",
                "name": "Copywriting Generation",
                "name_i18n": "step_copywrite",
                "type": "llm_generate",
                "depends_on": [],
                "config_template": {
                    "prompt_template": "为以下产品创作广告文案：\n产品：{product}\n卖点：{selling_points}\n风格：{style}\n\n请生成吸引人的广告标题和正文，突出产品优势。",
                    "model": "agnes-2.0-flash",
                    "temperature": 0.8,
                },
            },
            {
                "key": "step_image",
                "name": "Generate Product Images",
                "name_i18n": "step_image",
                "type": "image_gen",
                "depends_on": ["step_copywrite"],
                "config_template": {
                    "prompt_template": "为以下产品生成高质量的广告配图：\n产品：{product}\n卖点：{selling_points}\n风格：{style}\n\n图片要求：高清、吸引人、突出产品特点。",
                    "model": "agnes-2.0-flash",
                    "size": "1024x1024",
                    "style": "{style}",
                },
            },
            {
                "key": "step_video",
                "name": "Generate Ad Video",
                "name_i18n": "step_video",
                "type": "video_gen",
                "depends_on": ["step_image"],
                "config_template": {
                    "prompt_template": "{base_prompt}",
                    "model": "agnes-video-1.0",
                    "seconds": "{duration}",
                    "aspect_ratio": "16:9",
                },
            },
        ],
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
        "steps_config_template": [
            {
                "key": "step_outline",
                "name": "Outline Generation",
                "name_i18n": "step_outline",
                "type": "llm_generate",
                "depends_on": [],
                "config_template": {
                    "prompt_template": "为以下教学主题生成课件大纲：\n主题：{topic}\n目标年级：{grade}\n风格：{style}\n时长：{duration}分钟\n\n请生成详细的教学大纲，包括：知识点、教学目标、教学重点。",
                    "model": "agnes-2.0-flash",
                    "temperature": 0.5,
                },
            },
            {
                "key": "step_content",
                "name": "Content Generation",
                "name_i18n": "step_content",
                "type": "llm_generate",
                "depends_on": ["step_outline"],
                "config_template": {
                    "prompt_template": "根据以下大纲生成详细的课件内容：\n{base_prompt}\n\n请生成适合{grade}学生的教学内容，语言{description}，包含例子和练习。",
                    "model": "agnes-2.0-flash",
                    "temperature": 0.6,
                },
            },
            {
                "key": "step_images",
                "name": "Generate Illustrations",
                "name_i18n": "step_images",
                "type": "image_gen",
                "depends_on": ["step_content"],
                "config_template": {
                    "prompt_template": "为以下教学内容生成配图：\n{base_prompt}\n\n请生成清晰、易懂的教学配图，帮助学生理解。",
                    "model": "agnes-2.0-flash",
                    "size": "1024x1024",
                    "style": "clean",
                },
            },
            {
                "key": "step_video",
                "name": "Generate Explainer Video",
                "name_i18n": "step_video",
                "type": "video_gen",
                "depends_on": ["step_content", "step_images"],
                "config_template": {
                    "prompt_template": "根据以下课件内容生成讲解视频脚本：\n{base_prompt}",
                    "model": "agnes-video-1.0",
                    "seconds": "{duration} * 60",
                    "aspect_ratio": "16:9",
                },
            },
        ],
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
        "steps_config_template": [
            {
                "key": "step_character_setting",
                "name": "Character Setting Refinement",
                "name_i18n": "step_character_setting",
                "type": "llm_generate",
                "depends_on": [],
                "config_template": {
                    "prompt_template": "完善以下二次元角色设定：\n角色：{character}\n画风：{style}\n剧情：{story}\n\n请完善角色的性格、背景、能力、关系等设定，使其更立体。",
                    "model": "agnes-2.0-flash",
                    "temperature": 0.8,
                },
            },
            {
                "key": "step_character_images",
                "name": "Generate Character Art",
                "name_i18n": "step_character_images",
                "type": "image_gen",
                "depends_on": ["step_character_setting"],
                "config_template": {
                    "prompt_template": "{base_prompt}\n\n请生成{style}画风的角色立绘，高清，细节丰富。",
                    "model": "agnes-2.0-flash",
                    "size": "1024x1536",
                    "style": "{style}",
                    "num_images": "{num_images}",
                },
            },
            {
                "key": "step_story_images",
                "name": "Generate Scene Images",
                "name_i18n": "step_story_images",
                "type": "image_gen",
                "depends_on": ["step_character_setting"],
                "config_template": {
                    "prompt_template": "{base_prompt}\n\n请生成{style}画风的剧情场景图，展现角色在故事中的关键时刻。",
                    "model": "agnes-2.0-flash",
                    "size": "1024x576",
                    "style": "{style}",
                },
            },
        ],
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


def render_steps_config(scenario: Union[Dict[str, Any], str], inputs: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    根据用户输入渲染步骤配置。

    将 scenario["steps_config_template"] 中的 {placeholder} 替换为用户输入，
    生成最终的 steps_config。

    Args:
        scenario: 可以是场景字典，也可以是场景 key（字符串）
        inputs: 用户输入的参数
    """
    import re

    # 如果传入的是字符串 key，先获取场景字典
    if isinstance(scenario, str):
        scenario = get_scenario_by_key(scenario)
        if not scenario:
            raise ValueError(f"场景不存在: {scenario}")

    def render_template(template_str: str, inputs: Dict[str, Any]) -> str:
        """渲染模板字符串，替换 {key} 为用户输入值"""
        def replace_match(match):
            key = match.group(1)
            value = inputs.get(key)
            if value is None:
                return match.group(0)  # 保持原样
            return str(value)
        return re.sub(r"\{(\w+)\}", replace_match, template_str)

    steps_config = []
    for step_template in scenario["steps_config_template"]:
        step = dict(step_template)
        config_template = step.pop("config_template", {})
        config = {}
        for k, v in config_template.items():
            if isinstance(v, str):
                config[k] = render_template(v, inputs)
            elif isinstance(v, (int, float, bool)):
                # 处理数字类型的模板（如 "{duration} * 60"）
                if isinstance(v, str) and "{" in str(v):
                    # 尝试计算表达式
                    try:
                        # 简单表达式计算（只支持乘法）
                        expr = render_template(str(v), inputs)
                        if "*" in expr:
                            parts = expr.split("*")
                            result = float(parts[0].strip())
                            for part in parts[1:]:
                                result *= float(part.strip())
                            config[k] = int(result)
                        else:
                            config[k] = int(expr)
                    except Exception:
                        config[k] = v
                else:
                    config[k] = v
        step["config"] = config
        steps_config.append(step)
    return steps_config
