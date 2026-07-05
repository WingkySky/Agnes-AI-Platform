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
        # Task 18: 改造为新结构：script → storyboard → character_gen/prop_gen/scene_gen → storyboard_image → video → composite
        # 关键生成步骤添加 requires_confirmation: true，需用户确认后才继续下游
        "steps_config_template": [
            # 1. 剧本生成（LLM）- 需用户确认
            {
                "key": "step_script",
                "name": "Script Generation",
                "name_i18n": "step_script",
                "type": "llm_generate",
                "depends_on": [],
                "requires_confirmation": True,
                "config_template": {
                    "prompt_template": "根据以下主题生成{description}风格的短剧剧本：{topic}\n集数：{episodes}集\n单集时长：{duration_per_episode}秒\n\n请生成详细的剧本大纲和关键场景描述。",
                    "model": "agnes-2.0-flash",
                    "temperature": 0.8,
                },
            },
            # 2. 分镜生成（LLM）- 输出 storyboard/characters/props/scenes 清单，需用户确认
            # Task 18.4: prompt 增强，输出 JSON 含 characters/props/scenes 三个清单字段供下游读取
            {
                "key": "step_storyboard",
                "name": "Storyboard Generation",
                "name_i18n": "step_storyboard",
                "type": "llm_generate",
                "depends_on": ["step_script"],
                "requires_confirmation": True,
                "config_template": {
                    "prompt_template": "根据以下剧本生成分镜描述：\n{base_prompt}\n\n请输出 JSON 对象，包含以下字段：\n- storyboard: 分镜数组，每个元素含 image_prompt（画面描述）、characters_in_scene（本镜出现的角色名数组）、scene_name（场景名）字段\n- characters: 角色清单数组，每个元素含 name（角色名）和 description（角色简述）\n- props: 道具清单数组，每个元素含 name（道具名）和 description（道具简述）\n- scenes: 场景清单数组，每个元素含 name（场景名）和 description（场景简述）\n\n请为每个关键场景生成详细的画面描述，包括：场景、人物、动作、镜头角度。",
                    "model": "agnes-2.0-flash",
                    "temperature": 0.7,
                },
            },
            # 3. 角色生成（character_gen）- 从 step_storyboard.characters 读取，需用户确认
            {
                "key": "step_character_gen",
                "name": "Character Generation",
                "name_i18n": "step_character_gen",
                "type": "character_gen",
                "depends_on": ["step_storyboard"],
                "requires_confirmation": True,
                "config_template": {
                    "character_source": "step_storyboard.characters",
                    "estimated_count": 5,
                },
            },
            # 4. 道具生成（prop_gen）- 从 step_storyboard.props 读取，需用户确认
            {
                "key": "step_prop_gen",
                "name": "Prop Generation",
                "name_i18n": "step_prop_gen",
                "type": "prop_gen",
                "depends_on": ["step_storyboard"],
                "requires_confirmation": True,
                "config_template": {
                    "prop_source": "step_storyboard.props",
                    "estimated_count": 5,
                },
            },
            # 5. 场景生成（scene_gen）- 从 step_storyboard.scenes 读取，需用户确认
            {
                "key": "step_scene_gen",
                "name": "Scene Generation",
                "name_i18n": "step_scene_gen",
                "type": "scene_gen",
                "depends_on": ["step_storyboard"],
                "requires_confirmation": True,
                "config_template": {
                    "scene_source": "step_storyboard.scenes",
                    "estimated_count": 5,
                },
            },
            # 6. 分镜图生成（image_batch）- 从 step_storyboard.storyboard 读取，引用角色参考图，需用户确认
            # Task 18.5: reference_from_step 指向 step_character_gen，注入角色参考图保持人物一致性
            {
                "key": "step_storyboard_image",
                "name": "Generate Storyboard Images",
                "name_i18n": "step_storyboard_image",
                "type": "image_batch",
                "depends_on": ["step_character_gen", "step_prop_gen", "step_scene_gen"],
                "requires_confirmation": True,
                "config_template": {
                    "from_step": "step_storyboard",
                    "items_path": "storyboard",
                    "prompt_field": "image_prompt",
                    "reference_from_step": "step_character_gen",
                    "model": "agnes-image-1.0",
                    "size": "1024x1024",
                    "max_concurrent": 5,
                },
            },
            # 7. 视频生成（video_batch）- 从 step_storyboard_image 读取图片列表
            {
                "key": "step_video",
                "name": "Generate Video",
                "name_i18n": "step_video",
                "type": "video_batch",
                "depends_on": ["step_storyboard_image"],
                "config_template": {
                    "from_step": "step_storyboard_image",
                    "model": "agnes-video-1.0",
                    "seconds": "{duration_per_episode}",
                    "aspect_ratio": "16:9",
                },
            },
            # 8. 成片合成（ffmpeg_composite）- 从 step_video 读取视频片段
            {
                "key": "step_composite",
                "name": "Composite Output",
                "name_i18n": "step_composite",
                "type": "ffmpeg_composite",
                "depends_on": ["step_video"],
                "config_template": {
                    "from_step": "step_video",
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
            # Task 19.1: 关键生成步骤添加 requires_confirmation: true
            {
                "key": "step_copywrite",
                "name": "Copywriting Generation",
                "name_i18n": "step_copywrite",
                "type": "llm_generate",
                "depends_on": [],
                "requires_confirmation": True,
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
                "requires_confirmation": True,
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
            # 转场合成步骤：在视频生成之后插入 xfade 转场（ad 场景作为最终成片步骤）
            {
                "key": "step_transition",
                "name": "Transition Compose",
                "name_i18n": "step_transition",
                "type": "transition_compose",
                "depends_on": ["step_video"],
                "config_template": {
                    "video_clips_from": "step_video",
                    "transitions": [
                        {"type": "fade", "duration_ms": 500}
                    ],
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
            # Task 19.2: 关键生成步骤添加 requires_confirmation: true
            {
                "key": "step_outline",
                "name": "Outline Generation",
                "name_i18n": "step_outline",
                "type": "llm_generate",
                "depends_on": [],
                "requires_confirmation": True,
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
                "requires_confirmation": True,
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
                "requires_confirmation": True,
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
        # Task 18.3: 同步改造为与 drama 相同的结构，prompt 针对二次元风格
        # script → storyboard → character_gen/prop_gen/scene_gen → storyboard_image → video → composite
        "steps_config_template": [
            # 1. 角色设定生成（LLM）- 需用户确认
            {
                "key": "step_script",
                "name": "Character Setting Generation",
                "name_i18n": "step_script",
                "type": "llm_generate",
                "depends_on": [],
                "requires_confirmation": True,
                "config_template": {
                    "prompt_template": "完善以下二次元角色设定：\n角色：{character}\n画风：{style}\n剧情：{story}\n\n请完善角色的性格、背景、能力、关系等设定，并生成角色所处故事的剧本大纲。",
                    "model": "agnes-2.0-flash",
                    "temperature": 0.8,
                },
            },
            # 2. 分镜生成（LLM）- 输出 storyboard/characters/props/scenes 清单，需用户确认
            # Task 18.4: prompt 增强，输出 JSON 含 characters/props/scenes 三个清单字段供下游读取
            {
                "key": "step_storyboard",
                "name": "Storyboard Generation",
                "name_i18n": "step_storyboard",
                "type": "llm_generate",
                "depends_on": ["step_script"],
                "requires_confirmation": True,
                "config_template": {
                    "prompt_template": "根据以下二次元角色设定和故事大纲生成分镜描述：\n{base_prompt}\n\n请输出 JSON 对象，包含以下字段：\n- storyboard: 分镜数组，每个元素含 image_prompt（{style}画风的画面描述）、characters_in_scene（本镜出现的角色名数组）、scene_name（场景名）字段\n- characters: 角色清单数组，每个元素含 name（角色名）和 description（角色简述）\n- props: 道具清单数组，每个元素含 name（道具名）和 description（道具简述）\n- scenes: 场景清单数组，每个元素含 name（场景名）和 description（场景简述）\n\n请为每个关键场景生成{style}画风的详细画面描述。",
                    "model": "agnes-2.0-flash",
                    "temperature": 0.7,
                },
            },
            # 3. 角色生成（character_gen）- 从 step_storyboard.characters 读取，需用户确认
            {
                "key": "step_character_gen",
                "name": "Character Generation",
                "name_i18n": "step_character_gen",
                "type": "character_gen",
                "depends_on": ["step_storyboard"],
                "requires_confirmation": True,
                "config_template": {
                    "character_source": "step_storyboard.characters",
                    "estimated_count": 5,
                },
            },
            # 4. 道具生成（prop_gen）- 从 step_storyboard.props 读取，需用户确认
            {
                "key": "step_prop_gen",
                "name": "Prop Generation",
                "name_i18n": "step_prop_gen",
                "type": "prop_gen",
                "depends_on": ["step_storyboard"],
                "requires_confirmation": True,
                "config_template": {
                    "prop_source": "step_storyboard.props",
                    "estimated_count": 5,
                },
            },
            # 5. 场景生成（scene_gen）- 从 step_storyboard.scenes 读取，需用户确认
            {
                "key": "step_scene_gen",
                "name": "Scene Generation",
                "name_i18n": "step_scene_gen",
                "type": "scene_gen",
                "depends_on": ["step_storyboard"],
                "requires_confirmation": True,
                "config_template": {
                    "scene_source": "step_storyboard.scenes",
                    "estimated_count": 5,
                },
            },
            # 6. 分镜图生成（image_batch）- 从 step_storyboard.storyboard 读取，引用角色参考图，需用户确认
            # Task 18.5: reference_from_step 指向 step_character_gen，注入角色参考图保持人物一致性
            {
                "key": "step_storyboard_image",
                "name": "Generate Storyboard Images",
                "name_i18n": "step_storyboard_image",
                "type": "image_batch",
                "depends_on": ["step_character_gen", "step_prop_gen", "step_scene_gen"],
                "requires_confirmation": True,
                "config_template": {
                    "from_step": "step_storyboard",
                    "items_path": "storyboard",
                    "prompt_field": "image_prompt",
                    "reference_from_step": "step_character_gen",
                    "model": "agnes-image-1.0",
                    "size": "1024x1024",
                    "max_concurrent": 5,
                },
            },
            # 7. 视频生成（video_batch）- 从 step_storyboard_image 读取图片列表
            {
                "key": "step_video",
                "name": "Generate Video",
                "name_i18n": "step_video",
                "type": "video_batch",
                "depends_on": ["step_storyboard_image"],
                "config_template": {
                    "from_step": "step_storyboard_image",
                    "model": "agnes-video-1.0",
                    "seconds": 5,
                    "aspect_ratio": "16:9",
                },
            },
            # 8. 成片合成（ffmpeg_composite）- 从 step_video 读取视频片段
            {
                "key": "step_composite",
                "name": "Composite Output",
                "name_i18n": "step_composite",
                "type": "ffmpeg_composite",
                "depends_on": ["step_video"],
                "config_template": {
                    "from_step": "step_video",
                    "output_format": "mp4",
                    "quality": "high",
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
