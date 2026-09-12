# =====================================================
# 统一预设广场种子数据 — 官方风格卡 + 官方特效卡
# 使用方式（在 backend 目录下）：
#   python3 seed_plaza_presets.py
#
# 幂等性：按 (type, name) 判断，已存在则跳过
# 来源：
#   1. 生图/生视频页原硬编码风格（迁入后前端删除硬编码）
#   2. style_presets 内置风格（读取现表数据转换为 prompt_config，画布侧原表保留）
#   3. 全新特效模板（特效广场风格）
# =====================================================

import asyncio
import logging
import os
import sys

script_dir = os.path.dirname(os.path.abspath(__file__))
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session
from app.models.prompt_preset import PromptPreset
from app.models.pipeline import StylePreset

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [%(levelname)s] %(message)s")
logger = logging.getLogger("seed_plaza_presets")

# 官方卡统一字段
OFFICIAL = {"is_official": True, "is_public": True, "is_approved": True, "user_id": None}

# =====================================================
# 官方风格（原生图/生视频页硬编码迁移，suffix 与原实现逐字一致）
# =====================================================
OFFICIAL_STYLES = [
    # 原生图页 imageTemplates
    {"name": "超现实主义", "category": "风格插画", "suffix": "超现实主义风格，梦幻，高细节", "description": "梦幻超现实画面，细节丰富"},
    {"name": "电影感", "category": "摄影写真", "suffix": "电影感，戏剧性光照，宽银幕", "description": "电影级质感与戏剧性打光"},
    {"name": "日式动漫", "category": "动漫游戏", "suffix": "日式动漫风格，鲜艳色彩，细腻线条", "description": "日系动漫画风，色彩明快"},
    {"name": "2D 动画", "category": "动漫游戏", "suffix": "2D 动画风格，平涂色块，清晰描线，赛璐璐质感", "description": "平面二维动画画风，赛璐璐上色"},
    {"name": "3D 动画", "category": "动漫游戏", "suffix": "3D 动画风格，三维卡通渲染，柔和材质光照", "description": "三维卡通渲染动画质感"},
    {"name": "古典油画", "category": "风格插画", "suffix": "古典油画风格，厚重笔触，文艺复兴质感", "description": "古典油画质感，厚重笔触"},
    {"name": "写实摄影", "category": "摄影写真", "suffix": "专业摄影，8K 超高清，自然光照", "description": "专业摄影级写实画质"},
    {"name": "赛博朋克", "category": "风格插画", "suffix": "赛博朋克，霓虹光，未来都市感", "description": "霓虹闪烁的赛博都市"},
    {"name": "中国水墨", "category": "国风水墨", "suffix": "中国水墨风格，留白艺术，意境悠远", "description": "水墨留白，东方意境"},
    # 原生视频页 videoTemplates
    {"name": "电影镜头感", "category": "摄影写真", "suffix": "电影镜头感，缓慢平移，平滑 dolly-in，戏剧性光影", "description": "电影级运镜与光影"},
    {"name": "慢动作", "category": "摄影写真", "suffix": "慢动作，细腻细节，优雅节奏", "description": "升格慢动作，细节优雅"},
    {"name": "手持跟拍", "category": "摄影写真", "suffix": "手持跟拍，真实感，纪实", "description": "手持纪实跟拍质感"},
    {"name": "霓虹夜景", "category": "风格插画", "suffix": "霓虹夜景，水面反光，都市感", "description": "霓虹夜色，都市氛围"},
    {"name": "航拍大远景", "category": "摄影写真", "suffix": "航拍大远景，缓慢扫镜，史诗感", "description": "航拍史诗大场面"},
    {"name": "丝滑过渡", "category": "摄影写真", "suffix": "丝滑电影感过渡，电影级调色", "description": "丝滑转场与电影调色"},
]

# =====================================================
# 官方运镜（分镜/运镜词表：name 即分镜拆分的取值词，camera_params 与生成请求同形）
# =====================================================
OFFICIAL_CAMERAS = [
    {"name": "固定机位", "camera_movement": "固定机位"},
    {"name": "缓推", "camera_movement": "缓推"},
    {"name": "缓拉", "camera_movement": "缓拉"},
    {"name": "左摇", "camera_movement": "左摇"},
    {"name": "右摇", "camera_movement": "右摇"},
    {"name": "跟拍", "camera_movement": "跟拍"},
    {"name": "手持跟随", "camera_movement": "手持跟随"},
    {"name": "升降镜头", "camera_movement": "升降镜头"},
    {"name": "环绕运镜", "camera_movement": "环绕运镜"},
    {"name": "俯拍", "camera_movement": "俯拍视角"},
    {"name": "仰拍", "camera_movement": "仰拍视角"},
]

# =====================================================
# 官方特效（视频特效模板，suffix 为视频 prompt 片段）
# =====================================================
OFFICIAL_EFFECTS = [
    {"name": "穿云而入", "category": "运镜", "suffix": "镜头高速穿越云层俯冲而下，穿云而入，气势磅礴", "description": "高速穿云俯冲，气势磅礴"},
    {"name": "俯冲地球", "category": "运镜", "suffix": "镜头从太空急速俯冲向地球表面，穿越大气层，气势恢宏", "description": "从太空俯冲到地面"},
    {"name": "环绕运镜", "category": "运镜", "suffix": "镜头围绕主体 360 度环绕拍摄，弧形运镜", "description": "360 度环绕主体"},
    {"name": "希区柯克变焦", "category": "运镜", "suffix": "滑动变焦，背景拉伸变形，主体大小不变，眩晕感", "description": "推拉变焦的空间眩晕感"},
    {"name": "子弹时间", "category": "氛围", "suffix": "子弹时间，时间凝固，镜头绕主体高速旋转", "description": "时间凝固的环绕瞬间"},
    {"name": "慢动作推近", "category": "氛围", "suffix": "升格慢动作，镜头缓缓推近主体，细节纤毫毕现", "description": "慢动作推进特写"},
    {"name": "无人机俯瞰", "category": "运镜", "suffix": "无人机高空俯瞰视角，缓缓下降接近主体", "description": "高空俯瞰缓缓下降"},
    {"name": "第一人称冲刺", "category": "氛围", "suffix": "第一人称视角高速冲刺，速度感强烈，画面拉伸", "description": "第一人称高速冲刺"},
    {"name": "逆光剪影", "category": "氛围", "suffix": "逆光拍摄，主体呈现剪影效果，光晕弥漫", "description": "逆光剪影，光晕氛围"},
    {"name": "微距世界", "category": "氛围", "suffix": "微距镜头，极浅景深，微观世界细节纤毫毕现", "description": "微距浅景深特写"},
    {"name": "时间流逝", "category": "转场", "suffix": "延时摄影效果，云影飞逝，光影流转，时间快速流逝", "description": "延时摄影时间流逝"},
    {"name": "时空转场", "category": "转场", "suffix": "丝滑时空转场，画面无缝衔接切换场景，电影级过渡", "description": "无缝时空场景切换"},
]


# =====================================================
# 官方技能（Agent 技能：name=技能名，description=何时使用，prompt_text=正文）
# 系统提示只列 名称+description，正文由 agent_load_skill 按需加载
# =====================================================
OFFICIAL_SKILLS = [
    {
        "name": "分镜节奏与情绪曲线",
        "tag": "节奏",
        "category": "方法论",
        "description": "规划或调整分镜数量、镜头时长与排列顺序时使用",
        "prompt_text": (
            "短剧分镜节奏方法论：\n"
            "1. 开场 3 秒必须有钩子（冲突/悬念/反差），第一个分镜就是信息量最大的一帧\n"
            "2. 每 3-5 个分镜安排一次小高潮或转折，避免平铺\n"
            "3. 镜头时长对比制造节奏：动作/惊讶镜头短（2-3 秒），情绪/关系镜头长（5-8 秒）\n"
            "4. 情绪曲线：铺垫→上升→高潮→回落，低谷放在转场处，不要连续两个高潮相邻\n"
            "5. 生成提示词时把节奏写进运镜与时长：快切用固定机位短时长，情绪用缓推长时长\n"
            "6. 结尾留钩子（下一集期待感），最后一个分镜不收死画面"
        ),
    },
    {
        "name": "短剧台词打磨",
        "tag": "台词",
        "category": "方法论",
        "description": "撰写、修改剧本台词或为分镜补配音文案时使用",
        "prompt_text": (
            "短剧台词打磨原则：\n"
            "1. 口语化短句，单句 ≤15 字（适配 TTS 停顿与字幕一行）\n"
            "2. 潜台词优于直说：人物想要的不说破，用动作和错位回答\n"
            "3. 每句台词都要推进信息或关系，删掉纯寒暄\n"
            "4. 台词不写入画面提示词（画面是单帧剧照，台词属于配音/字幕阶段）\n"
            "5. 冲突对话用短促交锋试探，不用长独白；独白只留给情绪爆点\n"
            "6. 代词少用，人名直呼（TTS 与观众都更清楚谁在说）"
        ),
    },
    {
        "name": "角色一致性技巧",
        "tag": "一致性",
        "category": "方法论",
        "description": "建实体卡、生成设定图或发现跨镜头画风/长相漂移时使用",
        "prompt_text": (
            "角色一致性技巧：\n"
            "1. 每个角色建立固定的外观锚点（发色/瞳色/年龄感/标志性服装），锚点词逐字复用不改写\n"
            "2. 先生成三视图设定图，再以设定图为参考图出分镜图——参考图比文字更稳\n"
            "3. 分镜提示词里角色只写动作与表情，外貌交给设定上下文，避免每次重新描述外貌\n"
            "4. 同一角色跨镜头的外貌描述出现两个版本时，立即统一成一套锚点词\n"
            "5. 换装/受伤等状态变化只改锚点差异项，其余锚点保持原词"
        ),
    },
]


async def _exists(db: AsyncSession, preset_type: str, name: str) -> bool:
    result = await db.execute(
        select(PromptPreset).filter(
            PromptPreset.type == preset_type,
            PromptPreset.name == name,
        )
    )
    return result.scalar_one_or_none() is not None


async def _add(db: AsyncSession, preset_type: str, name: str, category: str,
               description: str, prompt_config: dict, cover_image: str | None,
               camera_params: dict | None = None, prompt_text: str = "") -> int:
    if await _exists(db, preset_type, name):
        return 0
    db.add(PromptPreset(
        name=name,
        type=preset_type,
        category=category or "通用",
        description=description,
        prompt_text=prompt_text,
        prompt_config=prompt_config,
        cover_image=cover_image,
        camera_params=camera_params,
        **OFFICIAL,
    ))
    return 1


async def seed_official_presets(db: AsyncSession) -> None:
    added = 0

    # 1. 硬编码迁移的官方风格
    for s in OFFICIAL_STYLES:
        added += await _add(db, "style", s["name"], s["category"], s["description"],
                            {"suffix": s["suffix"]}, None)

    # 1.5 官方技能（Agent 技能：正文走 prompt_text）
    for s in OFFICIAL_SKILLS:
        added += await _add(db, "skill", s["name"], s["category"], s["description"],
                            {"tag": s["tag"]}, None, prompt_text=s["prompt_text"])

    # 2. style_presets 内置风格 → 官方风格卡（画布侧原表保留不动）
    result = await db.execute(select(StylePreset).filter(StylePreset.is_builtin == True))  # noqa: E712
    for sp in result.scalars().all():
        parts = [p for p in [sp.visual_prefix, sp.lighting, sp.color_palette, sp.quality_suffix] if p]
        if not parts:
            continue
        prompt_config = {"suffix": "，".join(parts)}
        if sp.negative_prompt:
            prompt_config["negative_prompt"] = sp.negative_prompt
        added += await _add(db, "style", sp.name, sp.category or "风格插画", sp.description,
                            prompt_config, sp.preview_image)

    # 3. 官方特效
    for e in OFFICIAL_EFFECTS:
        added += await _add(db, "effect", e["name"], e["category"], e["description"],
                            {"suffix": e["suffix"]}, None)

    # 4. 官方运镜词表
    for cam in OFFICIAL_CAMERAS:
        added += await _add(db, "camera", cam["name"], "运镜", f"运镜方式：{cam['camera_movement']}",
                            {}, None, camera_params={"enabled": True, "camera_movement": cam["camera_movement"]})

    await db.commit()
    logger.info("官方预设写入完成：新增 %d 条（已存在的跳过）", added)


async def main():
    print("==== 开始写入统一预设广场种子数据 ====")
    async with async_session() as session:
        await seed_official_presets(session)
    print("==== 种子数据写入完成 ====")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("已取消")
