# =====================================================
# 风格元素种子数据 — 内置分层风格元素
# 使用方式（在 backend 目录下）：
#   python3 seed_style_elements.py
#
# 幂等性：内置元素按 key 判断，已存在则更新核心字段
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
from app.models.style_element import StyleElement

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [%(levelname)s] %(message)s")
logger = logging.getLogger("seed_style_elements")


# =====================================================
# 内置风格元素数据（6 层 × 每层若干元素）
# 字段需与 StyleElement 模型匹配：
#   - key: 元素唯一标识（如 "visual_style.manga_jp"）
#   - name: 显示名称
#   - description: 描述
#   - layer: 所属层（visual_style / lighting / color / camera / mood / quality）
#   - category: 细分类
#   - content: 该层提示词内容
#   - negative_content: 该层负面提示词
#   - weight_default: 默认权重 0.0–1.0
#   - tags: 标签（JSON 数组）
#   - sort_order: 排序权重
# =====================================================
BUILTIN_STYLE_ELEMENTS = [
    # ===== 画风层 visual_style =====
    {
        "key": "visual_style.manga_jp",
        "name": "日系漫画",
        "description": "日式黑白漫画风，clean lineart",
        "layer": "visual_style",
        "category": "anime",
        "content": "manga style, japanese comic book art, clean lineart, screentone",
        "negative_content": "color, photorealistic, 3d render, western comic",
        "weight_default": 1.0,
        "tags": ["anime", "comic", "black and white"],
        "sort_order": 10,
    },
    {
        "key": "visual_style.color_manhua",
        "name": "彩色国漫",
        "description": "中式彩色漫画风",
        "layer": "visual_style",
        "category": "comic",
        "content": "chinese manhua style, color comic illustration, soft shading",
        "negative_content": "photorealistic, 3d render, sketch only",
        "weight_default": 1.0,
        "tags": ["comic", "color", "chinese"],
        "sort_order": 20,
    },
    {
        "key": "visual_style.watercolor",
        "name": "水彩",
        "description": "柔和水彩画风",
        "layer": "visual_style",
        "category": "art",
        "content": "watercolor painting style, soft edges, color bleeding, paper texture",
        "negative_content": "sharp lines, digital art, 3d render",
        "weight_default": 1.0,
        "tags": ["art", "painting", "soft"],
        "sort_order": 30,
    },
    {
        "key": "visual_style.pixel_art",
        "name": "像素艺术",
        "description": "复古像素风",
        "layer": "visual_style",
        "category": "retro",
        "content": "pixel art, 16-bit retro game style, limited palette",
        "negative_content": "smooth gradients, photorealistic, high resolution",
        "weight_default": 1.0,
        "tags": ["retro", "game", "pixel"],
        "sort_order": 40,
    },
    {
        "key": "visual_style.pixar_3d",
        "name": "3D皮克斯",
        "description": "Pixar 风格 3D 渲染",
        "layer": "visual_style",
        "category": "3d",
        "content": "3d render, pixar style, smooth shading, stylized character",
        "negative_content": "2d, sketch, photorealistic, horror",
        "weight_default": 1.0,
        "tags": ["3d", "pixar", "animation"],
        "sort_order": 50,
    },
    {
        "key": "visual_style.cyberpunk",
        "name": "赛博朋克",
        "description": "霓虹赛博朋克风",
        "layer": "visual_style",
        "category": "scifi",
        "content": "cyberpunk style, neon lights, futuristic city, high tech low life",
        "negative_content": "medieval, fantasy, pastel colors",
        "weight_default": 1.0,
        "tags": ["scifi", "neon", "futuristic"],
        "sort_order": 60,
    },
    {
        "key": "visual_style.realistic_cine",
        "name": "写实电影",
        "description": "电影级写实风",
        "layer": "visual_style",
        "category": "realistic",
        "content": "cinematic realistic, photorealistic, film grain, depth of field",
        "negative_content": "anime, cartoon, 3d render, low quality",
        "weight_default": 1.0,
        "tags": ["realistic", "cinematic", "film"],
        "sort_order": 70,
    },
    {
        "key": "visual_style.chinese_ink",
        "name": "国风水墨",
        "description": "中国传统水墨画风",
        "layer": "visual_style",
        "category": "traditional",
        "content": "chinese ink painting, traditional brush stroke, xieyi style, monochrome",
        "negative_content": "color photo, 3d render, digital art",
        "weight_default": 1.0,
        "tags": ["traditional", "chinese", "ink"],
        "sort_order": 80,
    },

    # ===== 光影层 lighting =====
    {
        "key": "lighting.dramatic",
        "name": "戏剧光影",
        "description": "高对比度戏剧光",
        "layer": "lighting",
        "category": "dramatic",
        "content": "dramatic lighting, high contrast, strong shadows, chiaroscuro",
        "negative_content": "flat lighting, overexposed",
        "weight_default": 0.9,
        "tags": ["dramatic", "contrast"],
        "sort_order": 10,
    },
    {
        "key": "lighting.soft",
        "name": "柔和光",
        "description": "柔光均匀",
        "layer": "lighting",
        "category": "soft",
        "content": "soft lighting, diffused light, gentle shadows, even illumination",
        "negative_content": "harsh shadows, high contrast",
        "weight_default": 0.9,
        "tags": ["soft", "gentle"],
        "sort_order": 20,
    },
    {
        "key": "lighting.neon",
        "name": "霓虹光",
        "description": "霓虹灯光氛围",
        "layer": "lighting",
        "category": "neon",
        "content": "neon lighting, glowing lights, vibrant colors, night atmosphere",
        "negative_content": "natural daylight, muted colors",
        "weight_default": 0.9,
        "tags": ["neon", "night", "vibrant"],
        "sort_order": 30,
    },
    {
        "key": "lighting.natural",
        "name": "自然光",
        "description": "自然日光",
        "layer": "lighting",
        "category": "natural",
        "content": "natural lighting, sunlight, warm daylight, realistic illumination",
        "negative_content": "artificial neon, studio lighting",
        "weight_default": 0.9,
        "tags": ["natural", "daylight"],
        "sort_order": 40,
    },
    {
        "key": "lighting.backlight",
        "name": "逆光剪影",
        "description": "逆光剪影效果",
        "layer": "lighting",
        "category": "backlight",
        "content": "backlight, silhouette, rim light, glowing edges",
        "negative_content": "front lighting, flat",
        "weight_default": 0.9,
        "tags": ["backlight", "silhouette"],
        "sort_order": 50,
    },

    # ===== 配色层 color =====
    {
        "key": "color.monochrome",
        "name": "黑白单色",
        "description": "黑白单色配色",
        "layer": "color",
        "category": "monochrome",
        "content": "black and white, monochrome, grayscale",
        "negative_content": "colorful, vivid colors",
        "weight_default": 1.0,
        "tags": ["bw", "monochrome"],
        "sort_order": 10,
    },
    {
        "key": "color.warm",
        "name": "暖色调",
        "description": "温暖橙红色调",
        "layer": "color",
        "category": "warm",
        "content": "warm color palette, orange tones, cozy atmosphere",
        "negative_content": "cold blue tones",
        "weight_default": 0.9,
        "tags": ["warm", "orange"],
        "sort_order": 20,
    },
    {
        "key": "color.cold",
        "name": "冷色调",
        "description": "冷蓝绿色调",
        "layer": "color",
        "category": "cold",
        "content": "cold color palette, blue tones, cool atmosphere",
        "negative_content": "warm orange tones",
        "weight_default": 0.9,
        "tags": ["cold", "blue"],
        "sort_order": 30,
    },
    {
        "key": "color.high_contrast",
        "name": "高对比",
        "description": "高饱和高对比",
        "layer": "color",
        "category": "contrast",
        "content": "high contrast colors, vivid saturation, bold palette",
        "negative_content": "muted, desaturated, pastel",
        "weight_default": 0.9,
        "tags": ["contrast", "vivid"],
        "sort_order": 40,
    },
    {
        "key": "color.pastel",
        "name": "低饱和",
        "description": "柔和低饱和粉彩",
        "layer": "color",
        "category": "pastel",
        "content": "pastel colors, soft palette, low saturation, dreamy",
        "negative_content": "high saturation, bold contrast",
        "weight_default": 0.9,
        "tags": ["pastel", "soft", "dreamy"],
        "sort_order": 50,
    },

    # ===== 镜头层 camera =====
    {
        "key": "camera.closeup",
        "name": "特写",
        "description": "面部/物体特写",
        "layer": "camera",
        "category": "closeup",
        "content": "close-up shot, detailed face, shallow depth of field",
        "negative_content": "wide shot, distant",
        "weight_default": 0.9,
        "tags": ["closeup", "detail"],
        "sort_order": 10,
    },
    {
        "key": "camera.wide",
        "name": "广角",
        "description": "广角全景",
        "layer": "camera",
        "category": "wide",
        "content": "wide angle shot, expansive view, establishing shot",
        "negative_content": "close-up, cramped",
        "weight_default": 0.9,
        "tags": ["wide", "panorama"],
        "sort_order": 20,
    },
    {
        "key": "camera.topdown",
        "name": "俯视",
        "description": "俯视鸟瞰角度",
        "layer": "camera",
        "category": "angle",
        "content": "top-down view, bird's eye angle, overhead shot",
        "negative_content": "eye level, low angle",
        "weight_default": 0.9,
        "tags": ["topdown", "overhead"],
        "sort_order": 30,
    },
    {
        "key": "camera.low_angle",
        "name": "低角度",
        "description": "仰视英雄角度",
        "layer": "camera",
        "category": "angle",
        "content": "low angle shot, looking up, heroic perspective",
        "negative_content": "top-down, eye level",
        "weight_default": 0.9,
        "tags": ["lowangle", "heroic"],
        "sort_order": 40,
    },
    {
        "key": "camera.pov",
        "name": "第一人称",
        "description": "第一人称视角",
        "layer": "camera",
        "category": "pov",
        "content": "first person view, POV shot, immersive perspective",
        "negative_content": "third person, distant",
        "weight_default": 0.9,
        "tags": ["pov", "immersive"],
        "sort_order": 50,
    },

    # ===== 氛围层 mood =====
    {
        "key": "mood.warm_cozy",
        "name": "温馨",
        "description": "温馨治愈氛围",
        "layer": "mood",
        "category": "warm",
        "content": "warm cozy atmosphere, heartwarming, gentle mood",
        "negative_content": "dark, horror, tense",
        "weight_default": 0.9,
        "tags": ["warm", "cozy", "healing"],
        "sort_order": 10,
    },
    {
        "key": "mood.mysterious",
        "name": "神秘",
        "description": "神秘悬疑氛围",
        "layer": "mood",
        "category": "mystery",
        "content": "mysterious atmosphere, enigmatic mood, suspenseful",
        "negative_content": "cheerful, bright",
        "weight_default": 0.9,
        "tags": ["mystery", "suspense"],
        "sort_order": 20,
    },
    {
        "key": "mood.tense",
        "name": "紧张",
        "description": "紧张刺激氛围",
        "layer": "mood",
        "category": "tense",
        "content": "tense atmosphere, thrilling mood, high stakes",
        "negative_content": "relaxed, peaceful",
        "weight_default": 0.9,
        "tags": ["tense", "thrilling"],
        "sort_order": 30,
    },
    {
        "key": "mood.epic",
        "name": "史诗感",
        "description": "宏大史诗氛围",
        "layer": "mood",
        "category": "epic",
        "content": "epic atmosphere, grand scale, majestic mood",
        "negative_content": "small scale, mundane",
        "weight_default": 0.9,
        "tags": ["epic", "grand"],
        "sort_order": 40,
    },
    {
        "key": "mood.peaceful",
        "name": "宁静",
        "description": "宁静祥和氛围",
        "layer": "mood",
        "category": "peaceful",
        "content": "peaceful atmosphere, serene mood, tranquil",
        "negative_content": "chaotic, tense",
        "weight_default": 0.9,
        "tags": ["peaceful", "serene"],
        "sort_order": 50,
    },

    # ===== 品质层 quality =====
    {
        "key": "quality.masterpiece",
        "name": "杰作画质",
        "description": "最高品质",
        "layer": "quality",
        "category": "quality",
        "content": "masterpiece, best quality, highly detailed",
        "negative_content": "low quality, worst quality, blurry",
        "weight_default": 1.0,
        "tags": ["quality", "masterpiece"],
        "sort_order": 10,
    },
    {
        "key": "quality.ultra_detail",
        "name": "超精细",
        "description": "极致细节",
        "layer": "quality",
        "category": "detail",
        "content": "ultra detailed, intricate details, fine texture",
        "negative_content": "simple, low detail",
        "weight_default": 1.0,
        "tags": ["detail", "intricate"],
        "sort_order": 20,
    },
    {
        "key": "quality.8k",
        "name": "8K",
        "description": "8K 超高分辨率",
        "layer": "quality",
        "category": "resolution",
        "content": "8k resolution, ultra high definition, sharp focus",
        "negative_content": "low resolution, blurry",
        "weight_default": 1.0,
        "tags": ["8k", "uhd"],
        "sort_order": 30,
    },
    {
        "key": "quality.cinematic",
        "name": "电影级",
        "description": "电影级画质",
        "layer": "quality",
        "category": "cinematic",
        "content": "cinematic quality, film grain, professional color grading",
        "negative_content": "amateur, low budget",
        "weight_default": 1.0,
        "tags": ["cinematic", "film"],
        "sort_order": 40,
    },
]


# =====================================================
# 写入内置风格元素（内置支持 upsert）
# 已存在的元素按 key 更新核心字段，不存在的元素新增
# =====================================================
async def seed_style_elements(db: AsyncSession) -> int:
    """写入内置风格元素，返回新增数量"""
    added = 0
    updated = 0
    for elem_data in BUILTIN_STYLE_ELEMENTS:
        key = elem_data["key"]
        result = await db.execute(select(StyleElement).filter(StyleElement.key == key))
        existing = result.scalar_one_or_none()
        if existing:
            # 内置元素：更新核心字段
            existing.name = elem_data["name"]
            existing.description = elem_data.get("description", "")
            existing.layer = elem_data["layer"]
            existing.category = elem_data.get("category")
            existing.content = elem_data["content"]
            existing.negative_content = elem_data.get("negative_content", "")
            existing.weight_default = elem_data.get("weight_default", 1.0)
            existing.tags = elem_data.get("tags", [])
            existing.sort_order = elem_data.get("sort_order", 0)
            existing.is_builtin = True
            existing.is_public = True
            updated += 1
            logger.info("更新风格元素: %s", key)
            continue

        # 新增
        element = StyleElement(
            **elem_data,
            is_builtin=True,
            is_public=True,
        )
        db.add(element)
        added += 1
        logger.info("新增风格元素: %s (%s)", key, elem_data["name"])

    if added or updated:
        await db.commit()
        logger.info("风格元素写入完成 ✓ 新增 %d 个，更新 %d 个", added, updated)
    else:
        logger.info("风格元素已完整，无需新增")
    return added


async def main():
    print("==== 开始写入风格元素种子数据 ====")
    async with async_session() as session:
        await seed_style_elements(session)
    print("==== 种子数据写入完成 ====")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("已取消")
