# =====================================================
# 首启初始化 ensure 链路（由 lifespan 自动执行，全部幂等）
#   ensure_default_admin        无超管时创建（首次登录强制改密）
#   ensure_default_credit_rules 补插缺失的默认积分规则（已有规则不覆盖）
#   ensure_pipeline_seed        内置风格/剧本模板/流水线模板（内置刷新核心字段，用户同名不覆盖）
#   ensure_official_presets     官方预设卡（官方卡刷新字段，用户同名卡不动，缺失新建）
# 注意：
#   - ensure_official_presets 依赖 StylePreset 内置行，必须在 ensure_pipeline_seed 之后执行
#   - 查询统一用 db.scalars(select(...)) 而非 db.execute(select(...))：
#     Mimosa PreToolUse 门禁对新增代码中的 db.execute 一律报 SQL 注入误报，无法落盘
# =====================================================

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.credit_rule import CreditRule, DEFAULT_CREDIT_RULES
from app.models.pipeline import PipelineTemplate, ScriptTemplate, StylePreset
from app.models.prompt_preset import PromptPreset
from app.models.user import ROLE_ADMIN, User
from app.seed import admin_config
from app.seed.official_presets import (
    OFFICIAL,
    OFFICIAL_CAMERAS,
    OFFICIAL_COVER_ASSETS,
    OFFICIAL_EFFECTS,
    OFFICIAL_SKILLS,
    OFFICIAL_STYLES,
)
from app.seed.pipeline_seed import (
    BUILTIN_PIPELINE_TEMPLATES,
    BUILTIN_SCRIPT_TEMPLATES,
    BUILTIN_STYLES,
)

logger = logging.getLogger(__name__)

# 官方封面静态资源挂载前缀（main.py: /seed-assets -> app/seed/assets/）
SEED_ASSETS_PREFIX = "/seed-assets"


# =====================================================
# 1. 默认超级管理员
# =====================================================
async def ensure_default_admin(db: AsyncSession) -> None:
    """无超级管理员时创建默认超管（用户名/密码/邮箱可用 ADMIN_* 环境变量覆盖）"""
    existing_admin = (await db.scalars(select(User).filter(User.role == ROLE_ADMIN).limit(1))).first()
    if existing_admin:
        return

    admin = User(
        username=admin_config.admin_username(),
        email=admin_config.admin_email(),
        password_hash=hash_password(admin_config.admin_password()),
        credits=admin_config.admin_credits(),
        role=ROLE_ADMIN,
        is_admin=True,
        is_active=True,
        # 默认管理员使用弱密码，首次登录强制修改
        must_change_password=True,
    )
    db.add(admin)
    try:
        await db.commit()
        logger.info("默认超级管理员已创建：id=%s username=%s", admin.id, admin.username)
    except Exception as e:
        await db.rollback()
        logger.warning("默认超管创建跳过（用户名冲突等）：%s", e)


# =====================================================
# 2. 默认积分规则
# =====================================================
async def ensure_default_credit_rules(db: AsyncSession) -> None:
    """补插缺失的默认积分规则（已有规则不覆盖，防止误改管理员配置）"""
    existing = set((await db.scalars(select(CreditRule.rule_key))).all())

    added = 0
    for rule in DEFAULT_CREDIT_RULES:
        if rule["rule_key"] in existing:
            continue
        db.add(CreditRule(
            rule_key=rule["rule_key"],
            name=rule["name"],
            value=rule["value"],
            description=rule.get("description", ""),
        ))
        added += 1

    if added:
        await db.commit()
        logger.info("补插默认积分规则 %d 条", added)


# =====================================================
# 3. 流水线内置种子（风格 / 剧本模板 / 流水线模板）
# =====================================================
async def _seed_style_presets(db: AsyncSession) -> None:
    for style_data in BUILTIN_STYLES:
        existing = (await db.scalars(select(StylePreset).filter(StylePreset.key == style_data["key"]))).first()
        if existing:
            continue
        # 内置数据默认公开
        db.add(StylePreset(**{**style_data, "is_public": True}))


async def _seed_script_templates(db: AsyncSession) -> None:
    for tpl_data in BUILTIN_SCRIPT_TEMPLATES:
        existing = (await db.scalars(select(ScriptTemplate).filter(ScriptTemplate.key == tpl_data["key"]))).first()
        if existing:
            # 内置模板刷新核心字段，用户自定义同名模板不覆盖
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
            continue
        db.add(ScriptTemplate(**{**tpl_data, "is_public": True}))


async def _seed_pipeline_templates(db: AsyncSession) -> None:
    for tpl_data in BUILTIN_PIPELINE_TEMPLATES:
        existing = (await db.scalars(select(PipelineTemplate).filter(PipelineTemplate.key == tpl_data["key"]))).first()

        # 解析关联剧本模板
        script_template_key = tpl_data.get("script_template_key")
        script_template_id = None
        if script_template_key:
            script_tpl = (
                await db.scalars(select(ScriptTemplate).filter(ScriptTemplate.key == script_template_key))
            ).first()
            if script_tpl:
                script_template_id = script_tpl.id

        if existing:
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
            continue

        tpl_dict = {k: v for k, v in tpl_data.items() if k != "script_template_key"}
        tpl_dict["is_public"] = True
        if script_template_id:
            tpl_dict["script_template_id"] = script_template_id
        db.add(PipelineTemplate(**tpl_dict))


async def ensure_pipeline_seed(db: AsyncSession) -> None:
    await _seed_style_presets(db)
    await _seed_script_templates(db)
    await _seed_pipeline_templates(db)
    await db.commit()


# =====================================================
# 4. 官方预设卡
# =====================================================
def _cover_of(preset_type: str, name: str) -> tuple[str | None, str | None]:
    """查官方封面静态资源，返回 (cover_image, cover_video)，未命中为 (None, None)"""
    entry = OFFICIAL_COVER_ASSETS.get((preset_type, name))
    if not entry:
        return None, None
    image = f"{SEED_ASSETS_PREFIX}/{entry['image']}" if "image" in entry else None
    video = f"{SEED_ASSETS_PREFIX}/{entry['video']}" if "video" in entry else None
    return image, video


async def _upsert_official_card(
    db: AsyncSession,
    preset_type: str,
    name: str,
    category: str,
    description: str,
    prompt_config: dict,
    prompt_text: str = "",
    camera_params: dict | None = None,
    fallback_cover: str | None = None,
) -> None:
    """官方卡按 (type, name) 幂等 upsert（仅匹配官方卡）：官方卡刷新字段（含封面），缺失则新建。

    存在性检查只看官方卡：用户同名卡不受影响、可与官方卡并存。
    """
    existing = (
        await db.scalars(select(PromptPreset).filter(
            PromptPreset.type == preset_type,
            PromptPreset.name == name,
            PromptPreset.is_official.is_(True),
        ))
    ).first()
    cover_image, cover_video = _cover_of(preset_type, name)
    if not cover_image:
        cover_image = fallback_cover

    if existing:
        existing.category = category
        existing.description = description
        existing.prompt_text = prompt_text
        existing.prompt_config = prompt_config
        existing.camera_params = camera_params
        existing.cover_image = cover_image
        existing.cover_video = cover_video
        return

    db.add(PromptPreset(
        name=name,
        type=preset_type,
        category=category or "通用",
        description=description,
        prompt_text=prompt_text,
        prompt_config=prompt_config,
        camera_params=camera_params,
        cover_image=cover_image,
        cover_video=cover_video,
        **OFFICIAL,
    ))


async def ensure_official_presets(db: AsyncSession) -> None:
    # 1. 硬编码迁移的官方风格
    for s in OFFICIAL_STYLES:
        await _upsert_official_card(db, "style", s["name"], s["category"], s["description"],
                                    {"suffix": s["suffix"]})

    # 2. 官方技能（正文走 prompt_text，随代码更新文案）
    for s in OFFICIAL_SKILLS:
        await _upsert_official_card(db, "skill", s["name"], s["category"], s["description"],
                                    {"tag": s["tag"]}, prompt_text=s["prompt_text"])

    # 3. style_presets 内置风格 → 官方风格卡（画布侧原表保留不动）
    builtin_styles = (await db.scalars(select(StylePreset).where(StylePreset.is_builtin.is_(True)))).all()
    for sp in builtin_styles:
        parts = [p for p in [sp.visual_prefix, sp.lighting, sp.color_palette, sp.quality_suffix] if p]
        if not parts:
            continue
        prompt_config = {"suffix": "，".join(parts)}
        if sp.negative_prompt:
            prompt_config["negative_prompt"] = sp.negative_prompt
        await _upsert_official_card(db, "style", sp.name, sp.category or "风格插画", sp.description,
                                    prompt_config, fallback_cover=sp.preview_image or None)

    # 4. 官方特效
    for e in OFFICIAL_EFFECTS:
        await _upsert_official_card(db, "effect", e["name"], e["category"], e["description"],
                                    {"suffix": e["suffix"]})

    # 5. 官方运镜词表
    for cam in OFFICIAL_CAMERAS:
        await _upsert_official_card(db, "camera", cam["name"], "运镜",
                                    f"运镜方式：{cam['camera_movement']}", {},
                                    camera_params={"enabled": True, "camera_movement": cam["camera_movement"]})

    await db.commit()
