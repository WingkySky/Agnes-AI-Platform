# =====================================================
# 创意流水线种子数据
# 功能：
#   1. 内置风格预设（风格库）
#   2. 内置剧本模板（剧本模板库）
#   3. 第一个流水线模板 - 标准漫剧生成
#
# 使用方式（在 backend 目录下）：
#   python seed_pipeline_data.py
#
# 幂等性保证：
#   - 风格预设按 key 判断，已存在则不覆盖
#   - 剧本模板按 key 判断，已存在则不覆盖
#   - 流水线模板按 key 判断，已存在则不覆盖
# =====================================================

import asyncio
import logging
import os
import sys

# 允许直接以脚本形式运行
script_dir = os.path.dirname(os.path.abspath(__file__))
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session
from app.models.pipeline import StylePreset, ScriptTemplate, PipelineTemplate

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
)
logger = logging.getLogger("seed_pipeline")


# =====================================================
# 内置风格预设
# 字段需与 StylePreset 模型匹配：
#   - visual_prefix: 视觉风格前缀
#   - lighting: 光影风格
#   - color_palette: 配色方案
#   - quality_suffix: 品质增强词
#   - negative_prompt: 负面提示词
#   - camera_language: 镜头语言偏好
#   - mood_keywords: 氛围关键词
# =====================================================

BUILTIN_STYLES = [
    {
        "key": "comic_manga_jp",
        "name": "日系漫画风",
        "category": "art_style",
        "description": "经典日本黑白漫画风格，细腻的线条，丰富的网点纸效果",
        "visual_prefix": "manga style, japanese comic book art, clean lineart, detailed inking",
        "lighting": "dramatic lighting, high contrast black and white",
        "color_palette": "black and white, screentone, halftone dots, grayscale",
        "quality_suffix": "masterpiece, best quality, highly detailed",
        "negative_prompt": "color, photorealistic, 3d render, anime, western comic",
        "camera_language": "dynamic angles, dramatic composition, cinematic panels",
        "mood_keywords": "dramatic, intense, classic manga feel",
        "preview_image": "",
        "tags": ["漫画", "日系", "黑白", "经典"],
        "is_builtin": True,
    },
    {
        "key": "comic_color_manhua",
        "name": "国彩漫画风",
        "category": "art_style",
        "description": "全彩国漫风格，色彩鲜艳，人物美型",
        "visual_prefix": "chinese manhua style, full color comic, beautiful characters",
        "lighting": "soft lighting, ambient fill, subtle shadows",
        "color_palette": "vibrant colors, cel shading, soft gradients, rich saturation",
        "quality_suffix": "masterpiece, best quality, highly detailed",
        "negative_prompt": "black and white, sketch, low quality, western comic style",
        "camera_language": "cinematic composition, dynamic angles",
        "mood_keywords": "vibrant, energetic, modern chinese aesthetic",
        "preview_image": "",
        "tags": ["漫画", "国漫", "全彩", "美型"],
        "is_builtin": True,
    },
    {
        "key": "comic_webtoon",
        "name": "条漫/Webtoon风",
        "category": "art_style",
        "description": "竖屏条漫风格，适合手机阅读，画面干净简洁",
        "visual_prefix": "webtoon style, vertical comic format, korean comic art",
        "lighting": "bright, clean lighting, flat shading",
        "color_palette": "soft colors, clean aesthetic, pastels, bright tones",
        "quality_suffix": "high quality, clean lineart, webtoon style",
        "negative_prompt": "complex background, dark, gritty, traditional comic",
        "camera_language": "simple composition, vertical layout, clean panels",
        "mood_keywords": "cute, fresh, modern, mobile-friendly",
        "preview_image": "",
        "tags": ["条漫", "Webtoon", "竖屏", "可爱"],
        "is_builtin": True,
    },
    {
        "key": "anime_cinematic",
        "name": "动漫电影风",
        "category": "art_style",
        "description": "高质量动画电影风格，光影精美，画面细腻",
        "visual_prefix": "anime movie style, studio quality animation, detailed anime art",
        "lighting": "cinematic lighting, dramatic lens flare, volumetric lighting",
        "color_palette": "vibrant colors, cinematic color grading, rich contrast",
        "quality_suffix": "masterpiece, best quality, studio anime, cinematic detail",
        "negative_prompt": "photorealistic, 3d render, live action, western cartoon",
        "camera_language": "wide angle shots, cinematic framing, dramatic perspectives",
        "mood_keywords": "emotional, dreamy, atmospheric, cinematic, epic",
        "preview_image": "",
        "tags": ["动漫", "电影", "精美", "光影"],
        "is_builtin": True,
    },
    {
        "key": "pixel_art_retro",
        "name": "像素风",
        "category": "art_style",
        "description": "复古像素艺术风格，8-bit/16-bit游戏质感",
        "visual_prefix": "pixel art, 16-bit style, retro game graphics, 8-bit aesthetic",
        "lighting": "flat lighting, limited light sources, nostalgic glow",
        "color_palette": "limited color palette, bold colors, NES/SNES palette, vibrant retro",
        "quality_suffix": "pixel art, game sprite, retro gaming aesthetic",
        "negative_prompt": "smooth, photorealistic, high detail, 3d render, modern graphics",
        "camera_language": "tile-based composition, side view, isometric view",
        "mood_keywords": "nostalgic, retro, gaming, classic 8-bit/16-bit era",
        "preview_image": "",
        "tags": ["像素", "复古", "游戏", "8-bit"],
        "is_builtin": True,
    },
    {
        "key": "product_ad_clean",
        "name": "产品广告风",
        "category": "commercial",
        "description": "干净专业的产品广告风格，突出产品主体",
        "visual_prefix": "product photography style, clean commercial look, professional advertising",
        "lighting": "studio lighting, soft shadows, rim lighting, professional product lighting",
        "color_palette": "bright, crisp, professional color grading, clean whites",
        "quality_suffix": "professional photography, commercial quality, high resolution",
        "negative_prompt": "cluttered, messy, dark, amateur, low budget",
        "camera_language": "product showcase angles, hero shot composition",
        "mood_keywords": "professional, clean, trustworthy, modern, premium",
        "preview_image": "",
        "tags": ["产品", "广告", "商业", "干净"],
        "is_builtin": True,
    },
    # 以下为设计文档附录B中规划的风格，按需启用
    {
        "key": "anime_warm",
        "name": "温暖二次元",
        "category": "art_style",
        "description": "日系动漫风，暖色调，温馨治愈",
        "visual_prefix": "anime style, warm anime art, soft anime aesthetic",
        "lighting": "warm sunlight, soft ambient light, golden hour glow",
        "color_palette": "warm colors, orange and yellow tones, soft pastels",
        "quality_suffix": "anime style, warm lighting, soft shading",
        "negative_prompt": "dark, gritty, realistic, western cartoon",
        "camera_language": "gentle compositions, warm framing",
        "mood_keywords": "warm, cozy, healing, heartwarming, slice of life",
        "preview_image": "",
        "tags": ["二次元", "温暖", "治愈", "日系"],
        "is_builtin": True,
    },
    {
        "key": "cyberpunk_neon",
        "name": "赛博朋克·霓虹夜",
        "category": "art_style",
        "description": "赛博朋克，霓虹灯光，未来都市",
        "visual_prefix": "cyberpunk style, neonpunk, futuristic cyber aesthetic",
        "lighting": "neon lighting, dramatic rim lights, volumetric neon glow",
        "color_palette": "neon colors, cyan, magenta, purple, electric blue, dark backgrounds",
        "quality_suffix": "cyberpunk art, neon city, futuristic masterpiece",
        "negative_prompt": "natural lighting, daytime, warm colors, medieval",
        "camera_language": "wide cityscape, neon reflections, dramatic angles",
        "mood_keywords": "futuristic, edgy, high-tech, dystopian, electric",
        "preview_image": "",
        "tags": ["赛博朋克", "霓虹", "未来", "科技"],
        "is_builtin": True,
    },
    {
        "key": "chinese_ink",
        "name": "国风水墨",
        "category": "art_style",
        "description": "中国风水墨画，古典意境",
        "visual_prefix": "chinese ink painting style, shuimohua, traditional chinese art",
        "lighting": "soft natural light, misty atmosphere, ethereal glow",
        "color_palette": "ink wash, black and white, subtle grey tones, traditional chinese colors",
        "quality_suffix": "chinese ink painting, traditional chinese art style",
        "negative_prompt": "western style, bright colors, photorealistic, modern graphics",
        "camera_language": "traditional composition, poetic framing, negative space",
        "mood_keywords": "serene, classical, poetic, traditional, meditative",
        "preview_image": "",
        "tags": ["水墨", "国风", "古典", "意境"],
        "is_builtin": True,
    },
    {
        "key": "realistic_cine",
        "name": "写实电影感",
        "category": "art_style",
        "description": "照片级写实，电影构图",
        "visual_prefix": "photorealistic, cinematic photography, movie still quality",
        "lighting": "cinematic lighting, film noir style, dramatic natural lighting",
        "color_palette": "natural colors, film grain, cinema color grading, rich blacks",
        "quality_suffix": "photorealistic, 8k, ultra detailed, cinematic photography",
        "negative_prompt": "anime, cartoon, illustration, painting, artificial",
        "camera_language": "cinematic framing, anamorphic lens, film composition",
        "mood_keywords": "dramatic, cinematic, immersive, cinematic storytelling",
        "preview_image": "",
        "tags": ["写实", "电影", "摄影", "真实"],
        "is_builtin": True,
    },
    {
        "key": "watercolor_soft",
        "name": "柔和水彩",
        "category": "art_style",
        "description": "水彩画风格，柔和色调",
        "visual_prefix": "watercolor painting style, soft artistic watercolor art",
        "lighting": "soft diffused light, gentle illumination, paper texture glow",
        "color_palette": "watercolor palette, soft pastels, bleeding colors, muted tones",
        "quality_suffix": "beautiful watercolor painting, artistic soft style",
        "negative_prompt": "harsh lines, digital art, photorealistic, dark themes",
        "camera_language": "artistic composition, focus on texture and flow",
        "mood_keywords": "soft, gentle, artistic, dreamy, whimsical",
        "preview_image": "",
        "tags": ["水彩", "柔和", "艺术", "梦幻"],
        "is_builtin": True,
    },
    {
        "key": "3d_pixar_style",
        "name": "3D 皮克斯风",
        "category": "art_style",
        "description": "3D卡通渲染，皮克斯质感",
        "visual_prefix": "3D render, Pixar style, 3D animation aesthetic, CGI cartoon",
        "lighting": "Pixar lighting, soft shadows, volumetric ambient occlusion",
        "color_palette": "vibrant 3D colors, Pixar color palette, rich saturated tones",
        "quality_suffix": "Pixar 3D render, professional CGI, 3D animation quality",
        "negative_prompt": "2D, anime, realistic, dark, horror",
        "camera_language": "cinematic 3D composition, dynamic camera movement style",
        "mood_keywords": "playful, heartwarming, colorful, family-friendly, magical",
        "preview_image": "",
        "tags": ["3D", "皮克斯", "卡通", "可爱"],
        "is_builtin": True,
    },
]


# =====================================================
# 内置剧本模板
# 字段需与 ScriptTemplate 模型匹配：
#   - structure: 叙事结构（three_act 五幕式 / five_act 三幕式 / kishotenketsu 起承转合）
#   - output_schema: 期望的 JSON 输出结构（JSON Schema）
#   - scenes_min / scenes_max: 分镜数量范围
#   - default_scene_duration: 默认单镜时长（秒）
# =====================================================

BUILTIN_SCRIPT_TEMPLATES = [
    {
        "key": "short_story_comic",
        "name": "短篇故事漫剧",
        "category": "comic",
        "structure": "kishotenketsu",
        "description": "适合8-12个分镜的短篇故事漫剧，有起承转合的完整叙事结构",
        "prompt_template": """
请根据以下主题创作一个短篇漫画剧本：

主题：{{ theme }}
分镜数量：{{ scenes_count }}
风格：{{ style_name }}（{{ style_category }}）

要求：
1. 故事要有完整的起承转合结构
2. 每个分镜包含：场景描述、人物动作、对话、镜头角度
3. 人物形象要保持一致，有鲜明的性格特点
4. 画面要有视觉冲击力，适合漫画表现
5. 最后一镜要有回味或反转

请以JSON格式输出，结构如下：
{
  "title": "故事标题",
  "summary": "一句话梗概",
  "characters": [
    {
      "name": "角色名",
      "description": "外貌描述",
      "personality": "性格特点",
      "image_prompt": "用于生成角色设定图的英文提示词"
    }
  ],
  "scenes": [
    {
      "scene_num": 1,
      "description": "场景描述",
      "dialogue": "角色对话（可选）",
      "camera_angle": "镜头角度（如：正面、侧面、俯视、特写等）",
      "characters_in_scene": ["本场景出现的角色名1", "角色名2"],
      "image_prompt": "用于生成分镜图的英文提示词（详细描述画面内容、构图、光影）",
      "video_prompt": "用于生成动态视频的英文提示词（描述动作和镜头运动）",
      "duration": 5,
      "transition": "转场方式（如：淡入淡出、切镜、推进等）"
    }
  ]
}

注意：
- characters_in_scene 必须与 characters 数组中的 name 完全一致
- image_prompt 和 video_prompt 必须用英文
- 提示词要详细，包含：主体、环境、动作、构图、光影、风格
- 严格输出JSON，不要有多余的文字说明
        """.strip(),
        "output_schema": {
            "type": "object",
            "required": ["title", "summary", "characters", "scenes"],
            "properties": {
                "title": {"type": "string"},
                "summary": {"type": "string"},
                "characters": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["name", "description", "image_prompt"],
                        "properties": {
                            "name": {"type": "string"},
                            "description": {"type": "string"},
                            "personality": {"type": "string"},
                            "image_prompt": {"type": "string"}
                        }
                    }
                },
                "scenes": {
                    "type": "array",
                    "minItems": 4,
                    "maxItems": 20,
                    "items": {
                        "type": "object",
                        "required": ["scene_num", "description", "image_prompt"],
                        "properties": {
                            "scene_num": {"type": "integer"},
                            "description": {"type": "string"},
                            "dialogue": {"type": "string"},
                            "camera_angle": {"type": "string"},
                            "characters_in_scene": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "本场景出现的角色名列表（必须与 characters.name 一致）"
                            },
                            "image_prompt": {"type": "string"},
                            "video_prompt": {"type": "string"},
                            "duration": {"type": "number"},
                            "transition": {"type": "string"}
                        }
                    }
                }
            }
        },
        "scenes_min": 4,
        "scenes_max": 12,
        "default_scene_duration": 5,
        "variables_schema": {
            "theme": {"type": "string", "label": "故事主题", "required": True},
            "scenes_count": {"type": "integer", "label": "分镜数量", "default": 8, "min": 4, "max": 20},
        },
        "output_format": "json",
        "tags": ["漫剧", "短篇", "故事"],
        "is_builtin": True,
    },
    {
        "key": "product_ad_story",
        "name": "产品广告剧情",
        "category": "commercial",
        "structure": "three_act",
        "description": "产品推广类短视频剧本，有剧情有转折，自然植入产品",
        "prompt_template": """
请为以下产品创作一个有剧情的短视频广告剧本：

产品/主题：{{ theme }}
分镜数量：{{ scenes_count }}
风格：{{ style_name }}

要求：
1. 要有吸引人的开头（前3秒抓住注意力）
2. 有一个小冲突或痛点，然后产品解决问题
3. 产品植入要自然，不生硬
4. 结尾要有行动号召（Call to Action）
5. 整体节奏明快，适合短视频平台

请以JSON格式输出，结构如下：
{
  "title": "广告标题",
  "hook": "前3秒钩子文案",
  "product": "产品名称",
  "scenes": [
    {
      "scene_num": 1,
      "description": "场景描述",
      "voiceover": "旁白/配音文案",
      "text_overlay": "屏幕文字",
      "image_prompt": "英文画面提示词",
      "video_prompt": "英文动态提示词",
      "duration": 3,
      "transition": "转场方式"
    }
  ],
  "cta": "行动号召文案"
}

注意：
- image_prompt 和 video_prompt 用英文
- 画面提示词要详细，包含产品展示
- 严格输出JSON格式
        """.strip(),
        "output_schema": {
            "type": "object",
            "required": ["title", "hook", "product", "scenes", "cta"],
            "properties": {
                "title": {"type": "string"},
                "hook": {"type": "string"},
                "product": {"type": "string"},
                "cta": {"type": "string"},
                "scenes": {
                    "type": "array",
                    "minItems": 3,
                    "maxItems": 15,
                    "items": {
                        "type": "object",
                        "required": ["scene_num", "description", "image_prompt"],
                        "properties": {
                            "scene_num": {"type": "integer"},
                            "description": {"type": "string"},
                            "voiceover": {"type": "string"},
                            "text_overlay": {"type": "string"},
                            "image_prompt": {"type": "string"},
                            "video_prompt": {"type": "string"},
                            "duration": {"type": "number"},
                            "transition": {"type": "string"}
                        }
                    }
                }
            }
        },
        "scenes_min": 3,
        "scenes_max": 10,
        "default_scene_duration": 3,
        "variables_schema": {
            "theme": {"type": "string", "label": "产品/主题", "required": True},
            "scenes_count": {"type": "integer", "label": "分镜数量", "default": 6, "min": 3, "max": 15},
        },
        "output_format": "json",
        "tags": ["广告", "产品", "短视频"],
        "is_builtin": True,
    },
    {
        "key": "emotional_short",
        "name": "情感短剧",
        "category": "drama",
        "structure": "three_act",
        "description": "有情感共鸣的短剧剧本，适合治愈/励志/感人题材",
        "prompt_template": """
请创作一个情感类短剧剧本：

主题：{{ theme }}
分镜数量：{{ scenes_count }}
风格：{{ style_name }}

要求：
1. 要有情感铺垫和情绪递进
2. 人物有内心变化和成长
3. 画面要有氛围感，配合情绪
4. 结尾有升华或治愈感
5. 对话精炼，留白也很重要

请以JSON格式输出，结构如下：
{
  "title": "短剧标题",
  "theme": "核心主题",
  "mood": "整体情绪基调",
  "characters": [
    {
      "name": "角色名",
      "description": "外貌",
      "backstory": "背景故事",
      "image_prompt": "角色图英文提示词"
    }
  ],
  "scenes": [
    {
      "scene_num": 1,
      "description": "场景描述",
      "emotion": "本镜情绪",
      "dialogue": "对话",
      "inner_thought": "内心独白（可选）",
      "image_prompt": "画面英文提示词",
      "video_prompt": "动态英文提示词",
      "duration": 5,
      "bgm_mood": "背景音乐情绪",
      "transition": "转场"
    }
  ]
}

注意：
- 提示词用英文
- 画面描述要配合情绪（光影、色调、构图）
- 严格输出JSON
        """.strip(),
        "output_schema": {
            "type": "object",
            "required": ["title", "theme", "mood", "characters", "scenes"],
            "properties": {
                "title": {"type": "string"},
                "theme": {"type": "string"},
                "mood": {"type": "string"},
                "characters": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["name", "description", "image_prompt"],
                        "properties": {
                            "name": {"type": "string"},
                            "description": {"type": "string"},
                            "backstory": {"type": "string"},
                            "image_prompt": {"type": "string"}
                        }
                    }
                },
                "scenes": {
                    "type": "array",
                    "minItems": 4,
                    "maxItems": 15,
                    "items": {
                        "type": "object",
                        "required": ["scene_num", "description", "emotion", "image_prompt"],
                        "properties": {
                            "scene_num": {"type": "integer"},
                            "description": {"type": "string"},
                            "emotion": {"type": "string"},
                            "dialogue": {"type": "string"},
                            "inner_thought": {"type": "string"},
                            "image_prompt": {"type": "string"},
                            "video_prompt": {"type": "string"},
                            "duration": {"type": "number"},
                            "bgm_mood": {"type": "string"},
                            "transition": {"type": "string"}
                        }
                    }
                }
            }
        },
        "scenes_min": 4,
        "scenes_max": 15,
        "default_scene_duration": 5,
        "variables_schema": {
            "theme": {"type": "string", "label": "主题/情感", "required": True},
            "scenes_count": {"type": "integer", "label": "分镜数量", "default": 8, "min": 4, "max": 15},
        },
        "output_format": "json",
        "tags": ["情感", "治愈", "短剧"],
        "is_builtin": True,
    },
]


# =====================================================
# 内置流水线模板
# =====================================================

BUILTIN_PIPELINE_TEMPLATES = [
    {
        "key": "standard_comic_drama",
        "name": "标准漫剧生成",
        "description": "一键生成完整漫剧：剧本创作 → 角色设定 → 分镜图片 → 分镜视频",
        "category": "comic",
        "thumbnail_url": "https://placehold.co/600x400/6366F1/FFFFFF?text=漫剧生成",
        "script_template_key": "short_story_comic",
        "inputs_config": [
            {
                "key": "theme",
                "label": "故事主题",
                "type": "text",
                "required": True,
                "placeholder": "例如：一只小猫的冒险之旅",
            },
            {
                "key": "scenes_count",
                "label": "分镜数量",
                "type": "number",
                "required": False,
                "default": 8,
                "min": 4,
                "max": 12,
            },
            {
                "key": "style_id",
                "label": "风格预设",
                "type": "style_select",
                "required": False,
            },
            {
                "key": "generate_video",
                "label": "生成视频",
                "type": "boolean",
                "required": False,
                "default": True,
                "description": "关闭则只生成图片分镜，速度更快",
            },
            {
                "key": "enable_tts",
                "label": "启用配音",
                "type": "boolean",
                "required": False,
                "default": True,
                "description": "关闭则跳过语音合成，最终视频为静音（适合纯音乐/字幕漫剧）",
            },
        ],
        "steps_config": [
            {
                "key": "script_generation",
                "name": "剧本生成",
                "type": "llm_generate",
                "depends_on": [],
                "config": {
                    "use_script_template": True,
                    "json_output": True,
                    "model": "agnes-2.0-flash",
                    "temperature": 0.8,
                },
                "max_retries": 2,
                "timeout": 120,
            },
            {
                "key": "character_images",
                "name": "角色设定图",
                "type": "image_batch",
                "depends_on": ["script_generation"],
                "config": {
                    "source": "parsed_result",
                    "from_step": "script_generation",
                    "items_path": "characters",
                    "prompt_field": "image_prompt",
                    "size": "1024x1024",
                    "max_concurrent": 4,
                },
                "max_retries": 1,
                "timeout": 300,
            },
            {
                "key": "scene_images",
                "name": "分镜图片",
                "type": "image_batch",
                "depends_on": ["script_generation", "character_images"],
                "config": {
                    "source": "parsed_result",
                    "from_step": "script_generation",
                    "items_path": "scenes",
                    "prompt_field": "image_prompt",
                    "size": "1024x768",
                    "max_concurrent": 5,
                    "reference_from_step": "character_images",
                },
                "max_retries": 1,
                "timeout": 600,
            },
            {
                "key": "scene_videos",
                "name": "分镜视频",
                "type": "video_batch",
                "depends_on": ["scene_images"],
                "condition": "inputs.generate_video === true",
                "config": {
                    "source": "image_step",
                    "from_step": "scene_images",
                    "seconds": 5,
                    "aspect_ratio": "16:9",
                    "max_concurrent": 3,
                    "poll_interval": 10,
                    "max_poll_time": 600,
                },
                "max_retries": 1,
                "timeout": 900,
            },
            {
                "key": "scene_tts",
                "name": "分镜配音",
                "type": "tts_generate",
                "depends_on": ["script_generation"],
                "condition": "inputs.generate_video === true && inputs.enable_tts !== false",
                "config": {
                    "from_step": "script_generation",
                    "text_field": "dialogue",
                    "default_voice": "zh-CN-XiaoxiaoNeural",
                    "rate": "+0%",
                    "max_concurrent": 3,
                },
                "max_retries": 1,
                "timeout": 300,
            },
            {
                "key": "final_composite",
                "name": "最终合成",
                "type": "ffmpeg_composite",
                "depends_on": ["scene_videos", "scene_tts"],
                "condition": "inputs.generate_video === true",
                "config": {
                    "from_step": "scene_videos",
                    "audio_from_step": "scene_tts",
                    "script_from_step": "script_generation",
                    "with_subtitle": True,
                    "with_bgm": False,
                    "bgm_volume": 0.3,
                },
                "optional_depends_on": ["scene_tts"],
                "max_retries": 1,
                "timeout": 600,
            },
        ],
        "output_mapping": {
            "script": "script_generation.parsed_result",
            "characters": "character_images.images",
            "scene_images": "scene_images.images",
            "scene_videos": "scene_videos.videos",
            "audios": "scene_tts.audios",
            "final_video": "final_composite.final_video_url",
        },
        "estimated_credits": 200,
        "estimated_time_minutes": 15,
        "tags": ["漫剧", "标准", "一键生成"],
        "is_builtin": True,
    },
    {
        "key": "product_ad_video",
        "name": "产品广告视频",
        "description": "快速生成有剧情的产品广告短视频",
        "category": "commercial",
        "thumbnail_url": "https://placehold.co/600x400/F59E0B/FFFFFF?text=广告视频",
        "script_template_key": "product_ad_story",
        "inputs_config": [
            {
                "key": "theme",
                "label": "产品/主题",
                "type": "text",
                "required": True,
                "placeholder": "例如：一款神奇的保温杯",
            },
            {
                "key": "scenes_count",
                "label": "分镜数量",
                "type": "number",
                "required": False,
                "default": 6,
                "min": 3,
                "max": 10,
            },
            {
                "key": "style_id",
                "label": "风格预设",
                "type": "style_select",
                "required": False,
            },
        ],
        "steps_config": [
            {
                "key": "ad_script",
                "name": "广告剧本",
                "type": "llm_generate",
                "depends_on": [],
                "config": {
                    "use_script_template": True,
                    "json_output": True,
                    "model": "agnes-2.0-flash",
                    "temperature": 0.7,
                },
                "max_retries": 2,
                "timeout": 120,
            },
            {
                "key": "ad_scene_images",
                "name": "广告分镜图",
                "type": "image_batch",
                "depends_on": ["ad_script"],
                "config": {
                    "source": "parsed_result",
                    "from_step": "ad_script",
                    "items_path": "scenes",
                    "prompt_field": "image_prompt",
                    "size": "1024x768",
                    "max_concurrent": 5,
                },
                "max_retries": 1,
                "timeout": 600,
            },
            {
                "key": "ad_videos",
                "name": "广告视频",
                "type": "video_batch",
                "depends_on": ["ad_scene_images"],
                "config": {
                    "source": "image_step",
                    "from_step": "ad_scene_images",
                    "seconds": 4,
                    "aspect_ratio": "16:9",
                    "max_concurrent": 3,
                    "poll_interval": 10,
                    "max_poll_time": 600,
                },
                "max_retries": 1,
                "timeout": 900,
            },
            {
                "key": "ad_tts",
                "name": "广告配音",
                "type": "tts_generate",
                "depends_on": ["ad_script"],
                "config": {
                    "from_step": "ad_script",
                    "text_field": "dialogue",
                    "default_voice": "zh-CN-XiaoxiaoNeural",
                    "rate": "+0%",
                    "max_concurrent": 3,
                },
                "max_retries": 1,
                "timeout": 300,
            },
            {
                "key": "ad_final_composite",
                "name": "最终合成",
                "type": "ffmpeg_composite",
                "depends_on": ["ad_videos", "ad_tts"],
                "config": {
                    "from_step": "ad_videos",
                    "audio_from_step": "ad_tts",
                    "script_from_step": "ad_script",
                    "with_subtitle": True,
                    "with_bgm": False,
                    "bgm_volume": 0.3,
                },
                "max_retries": 1,
                "timeout": 600,
            },
        ],
        "output_mapping": {
            "script": "ad_script.parsed_result",
            "scene_images": "ad_scene_images.images",
            "videos": "ad_videos.videos",
            "audios": "ad_tts.audios",
            "final_video": "ad_final_composite.final_video_url",
        },
        "estimated_credits": 150,
        "estimated_time_minutes": 12,
        "tags": ["广告", "产品", "短视频"],
        "is_builtin": True,
    },
    {
        "key": "science_short_video",
        "name": "科普短片",
        "description": "生成科普知识短片：剧本 → 场景图 → 场景视频 → 旁白配音 → 最终合成（含字幕）",
        "category": "education",
        "thumbnail_url": "https://placehold.co/600x400/10B981/FFFFFF?text=科普短片",
        "script_template_key": "short_story_comic",
        "inputs_config": [
            {
                "key": "theme",
                "label": "科普主题",
                "type": "text",
                "required": True,
                "placeholder": "例如：黑洞是如何形成的",
            },
            {
                "key": "scenes_count",
                "label": "分镜数量",
                "type": "number",
                "required": False,
                "default": 6,
                "min": 4,
                "max": 10,
            },
            {
                "key": "style_id",
                "label": "风格预设",
                "type": "style_select",
                "required": False,
            },
        ],
        "steps_config": [
            {
                "key": "sci_script",
                "name": "科普剧本",
                "type": "llm_generate",
                "depends_on": [],
                "config": {
                    "use_script_template": True,
                    "json_output": True,
                    "model": "agnes-2.0-flash",
                    "temperature": 0.7,
                },
                "max_retries": 2,
                "timeout": 120,
            },
            {
                "key": "sci_scene_images",
                "name": "场景图片",
                "type": "image_batch",
                "depends_on": ["sci_script"],
                "config": {
                    "source": "parsed_result",
                    "from_step": "sci_script",
                    "items_path": "scenes",
                    "prompt_field": "image_prompt",
                    "size": "1024x768",
                    "max_concurrent": 5,
                },
                "max_retries": 1,
                "timeout": 600,
            },
            {
                "key": "sci_videos",
                "name": "场景视频",
                "type": "video_batch",
                "depends_on": ["sci_scene_images"],
                "config": {
                    "source": "image_step",
                    "from_step": "sci_scene_images",
                    "seconds": 6,
                    "aspect_ratio": "16:9",
                    "max_concurrent": 3,
                    "poll_interval": 10,
                    "max_poll_time": 600,
                },
                "max_retries": 1,
                "timeout": 900,
            },
            {
                "key": "sci_narration",
                "name": "旁白配音",
                "type": "tts_generate",
                "depends_on": ["sci_script"],
                # 科普短片用 description 字段做旁白（而非对白）
                "config": {
                    "from_step": "sci_script",
                    "text_field": "description",
                    "default_voice": "zh-CN-YunyangNeural",
                    "rate": "-10%",
                    "max_concurrent": 3,
                },
                "max_retries": 1,
                "timeout": 300,
            },
            {
                "key": "sci_final",
                "name": "最终合成",
                "type": "ffmpeg_composite",
                "depends_on": ["sci_videos", "sci_narration"],
                "config": {
                    "from_step": "sci_videos",
                    "audio_from_step": "sci_narration",
                    "script_from_step": "sci_script",
                    "with_subtitle": True,
                    "with_bgm": False,
                    "bgm_volume": 0.3,
                },
                "max_retries": 1,
                "timeout": 600,
            },
        ],
        "output_mapping": {
            "script": "sci_script.parsed_result",
            "scene_images": "sci_scene_images.images",
            "videos": "sci_videos.videos",
            "audios": "sci_narration.audios",
            "final_video": "sci_final.final_video_url",
        },
        "estimated_credits": 180,
        "estimated_time_minutes": 14,
        "tags": ["科普", "教育", "旁白", "短视频"],
        "is_builtin": True,
    },
]


# =====================================================
# 种子数据写入
# =====================================================

async def seed_style_presets(db: AsyncSession) -> int:
    """写入内置风格预设（幂等）"""
    added = 0
    for style_data in BUILTIN_STYLES:
        key = style_data["key"]
        result = await db.execute(select(StylePreset).filter(StylePreset.key == key))
        existing = result.scalar_one_or_none()
        if existing:
            logger.info("风格预设已存在: %s，跳过", key)
            continue

        # 内置数据默认公开
        data = {**style_data, "is_public": True}
        style = StylePreset(**data)
        db.add(style)
        added += 1
        logger.info("新增风格预设: %s (%s)", key, style_data["name"])

    if added:
        await db.commit()
        logger.info("风格预设写入完成 ✓ 共新增 %d 个", added)
    else:
        logger.info("风格预设已完整，无需新增")
    return added


async def seed_script_templates(db: AsyncSession) -> int:
    """
    写入内置剧本模板（内置模板支持 upsert）

    - 内置模板：已存在时更新 prompt_template/output_schema 等核心字段，
      保证开发期间模板变更能同步到数据库
    - 用户自定义模板：已存在则跳过，不覆盖
    """
    added = 0
    updated = 0
    for tpl_data in BUILTIN_SCRIPT_TEMPLATES:
        key = tpl_data["key"]
        result = await db.execute(select(ScriptTemplate).filter(ScriptTemplate.key == key))
        existing = result.scalar_one_or_none()
        if existing:
            # 内置模板：更新核心字段（与 seed_pipeline_templates 逻辑一致）
            if existing.is_builtin:
                existing.name = tpl_data["name"]
                existing.description = tpl_data.get("description", "")
                existing.prompt_template = tpl_data["prompt_template"]
                existing.output_schema = tpl_data["output_schema"]
                existing.scenes_min = tpl_data.get("scenes_min", existing.scenes_min)
                existing.scenes_max = tpl_data.get("scenes_max", existing.scenes_max)
                existing.default_scene_duration = tpl_data.get(
                    "default_scene_duration", existing.default_scene_duration
                )
                updated += 1
                logger.info("更新剧本模板: %s", key)
            else:
                logger.info("剧本模板已存在（用户自定义）: %s，跳过", key)
            continue

        # 内置数据默认公开
        data = {**tpl_data, "is_public": True}
        tpl = ScriptTemplate(**data)
        db.add(tpl)
        added += 1
        logger.info("新增剧本模板: %s (%s)", key, tpl_data["name"])

    if added or updated:
        await db.commit()
        logger.info("剧本模板写入完成 ✓ 新增 %d 个，更新 %d 个", added, updated)
    else:
        logger.info("剧本模板已完整，无需新增")
    return added


async def seed_pipeline_templates(db: AsyncSession) -> int:
    """
    写入内置流水线模板（内置模板支持 upsert，用户自定义模板跳过）

    - 内置模板（is_builtin=True）：已存在时更新 steps_config/output_mapping 等核心字段，
      保证开发期间模板变更能同步到数据库
    - 用户自定义模板：已存在则跳过，不覆盖
    """
    added = 0
    updated = 0
    for tpl_data in BUILTIN_PIPELINE_TEMPLATES:
        key = tpl_data["key"]
        result = await db.execute(select(PipelineTemplate).filter(PipelineTemplate.key == key))
        existing = result.scalar_one_or_none()

        # 查找关联的剧本模板ID
        script_template_key = tpl_data.get("script_template_key")
        script_template_id = None
        if script_template_key:
            tpl_result = await db.execute(
                select(ScriptTemplate).filter(ScriptTemplate.key == script_template_key)
            )
            script_tpl = tpl_result.scalar_one_or_none()
            if script_tpl:
                script_template_id = script_tpl.id

        if existing:
            # 内置模板：更新核心字段（steps_config 等可能在开发期间变化）
            if getattr(existing, "is_builtin", False):
                existing.name = tpl_data.get("name", existing.name)
                existing.description = tpl_data.get("description", existing.description)
                existing.steps_config = tpl_data.get("steps_config", existing.steps_config)
                existing.output_mapping = tpl_data.get("output_mapping", existing.output_mapping)
                existing.inputs_config = tpl_data.get("inputs_config", existing.inputs_config)
                existing.estimated_credits = tpl_data.get("estimated_credits", existing.estimated_credits)
                existing.estimated_time_minutes = tpl_data.get("estimated_time_minutes", existing.estimated_time_minutes)
                existing.tags = tpl_data.get("tags", existing.tags)
                existing.category = tpl_data.get("category", existing.category)
                if script_template_id:
                    existing.script_template_id = script_template_id
                updated += 1
                logger.info("更新内置流水线模板: %s (%s)", key, tpl_data["name"])
            else:
                logger.info("流水线模板已存在（用户自定义）: %s，跳过", key)
            continue

        # 新增：去掉 key 字段，准备数据；内置数据默认公开
        tpl_dict = {k: v for k, v in tpl_data.items() if k != "script_template_key"}
        tpl_dict["is_public"] = True
        if script_template_id:
            tpl_dict["script_template_id"] = script_template_id

        tpl = PipelineTemplate(**tpl_dict)
        db.add(tpl)
        added += 1
        logger.info("新增流水线模板: %s (%s)", key, tpl_data["name"])

    if added or updated:
        await db.commit()
        logger.info("流水线模板写入完成 ✓ 新增 %d 个，更新 %d 个", added, updated)
    else:
        logger.info("流水线模板已完整，无需新增")
    return added


# =====================================================
# 主入口
# =====================================================

async def main():
    logger.info("==== 开始写入流水线种子数据 ====")

    async with async_session() as session:
        n1 = await seed_style_presets(session)
        n2 = await seed_script_templates(session)
        n3 = await seed_pipeline_templates(session)

        total = n1 + n2 + n3
        logger.info("==== 种子数据写入完成 ====")
        if total > 0:
            print(f"")
            print(f"成功新增 {total} 项数据：")
            print(f"  - 风格预设：{n1} 个")
            print(f"  - 剧本模板：{n2} 个")
            print(f"  - 流水线模板：{n3} 个")
        else:
            print("")
            print("所有数据已存在，无需新增")
        print("")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("已取消")
