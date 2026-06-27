# =====================================================
# 数据库初始化脚本
# 功能：
#   1. 根据模型定义创建所有数据表（幂等，不修改已有表结构）
#      覆盖表：users / credit_rules / generations / chat_sessions /
#              chat_messages / api_providers / model_definitions / credit_transactions
#   2. 创建默认超级管理员（用户名/密码/邮箱可通过环境变量修改）
#   3. 写入默认积分规则（若 rules 表中缺少则补全，已有规则不覆盖）
#
# 使用方式（在 backend 目录下）：
#   python init_db.py
#
# 环境变量（可选）：
#   ADMIN_USERNAME  超级管理员用户名（默认 admin）
#   ADMIN_PASSWORD  超级管理员密码（默认 admin123）
#   ADMIN_EMAIL     超级管理员邮箱（默认 admin@example.com）
#   ADMIN_CREDITS   超级管理员初始积分（默认 9999）
#
# 安全保证（不会覆盖已有数据）：
#   - create_all 只创建缺失的表，不修改/删除已有表结构和数据
#   - 若超级管理员用户已存在，脚本不会重复创建，只打印提示
#   - 若某条积分规则已存在，保留原值不会被覆盖（防止误改管理员配置）
#   - 早期未绑定 user_id 的数据会自动归属于此管理员，新用户注册后将拥有独立数据空间
#   - 本脚本使用异步 Session，兼容 SQLite / PostgreSQL
# =====================================================

import asyncio
import logging
import os
import sys

# 允许直接以脚本形式运行（不依赖 PYTHONPATH 手动配置）
script_dir = os.path.dirname(os.path.abspath(__file__))
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

# ---------- 核心组件 ----------
from app.core.database import Base, async_engine, async_session
from app.core.security import hash_password

# ---------- 模型 ----------
# 逐个导入所有模型，确保 Base.metadata.create_all 能创建全部表
# （create_all 只注册被导入过的模型对应的表）
# 逐个导入而非一次性导入：某个非核心模型导入失败时不会中断整个脚本，
# 核心表（users / credit_rules）仍能正常创建，失败项会打印明确警告
from app.models.user import User, ROLE_ADMIN
from app.models.credit_rule import CreditRule, DEFAULT_CREDIT_RULES

# 非核心模型逐个导入，失败时记录警告但不中断
_import_errors = []

def _safe_import(module_path: str, names: list[str]):
    """安全导入模型模块，失败时记录到 _import_errors 但不抛异常"""
    try:
        mod = __import__(module_path, fromlist=names)
        return {name: getattr(mod, name) for name in names}
    except Exception as e:
        _import_errors.append(f"{module_path}: {e}")
        return {}

_safe_import("app.models.generation", ["Generation"])
_safe_import("app.models.chat", ["ChatSession", "ChatMessage"])
_safe_import("app.models.api_provider", ["ApiProvider"])
_safe_import("app.models.model_definition", ["ModelDefinition"])
_safe_import("app.models.credit_transaction", ["CreditTransaction"])
_safe_import("app.models.user_preference", ["UserPreference"])
_safe_import("app.models.role", ["Role"])
_safe_import("app.models.sensitive_word", ["SensitiveWord"])
_safe_import("app.models.watermark", ["WatermarkConfig"])
_safe_import("app.models.plaza_like", ["PlazaLike"])
_safe_import("app.models.system_config", ["SystemConfig"])
_safe_import("app.models.pipeline", [
    "PipelineTemplate",
    "PipelineRun",
    "PipelineStep",
    "StylePreset",
    "ScriptTemplate",
])
_safe_import("app.models.style_element", ["StyleElement"])
_safe_import("app.models.asset", ["Asset"])

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
)
logger = logging.getLogger("init_db")

# 若有模型导入失败，打印明确警告（不中断流程，核心表仍会创建）
if _import_errors:
    logger.warning("以下模型导入失败（对应表不会被创建，请检查依赖）：")
    for err in _import_errors:
        logger.warning("  - %s", err)


# =====================================================
# 1. 创建所有表
# =====================================================
async def create_tables():
    """根据 Base.metadata 创建所有数据表（幂等，表已存在则跳过）"""
    # 打印已注册的表名，方便用户确认覆盖范围
    registered_tables = sorted(Base.metadata.tables.keys())
    logger.info("已注册模型表（共 %d 张）：%s", len(registered_tables), ", ".join(registered_tables))
    if _import_errors:
        missing = [err.split(":")[0].split(".")[-1] for err in _import_errors]
        logger.warning("因导入失败未注册的表：%s", ", ".join(missing))

    logger.info("开始创建数据表...")
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("数据表创建完成 ✓")

    # 老库兼容：create_all 不会修改已有表结构，应用启动时由 main.py 的
    # _auto_migrate_missing_columns() 统一兜底新增 provider_type 等新字段


# =====================================================
# 2. 创建默认超级管理员并绑定早期数据
# =====================================================
async def create_default_admin(db: AsyncSession):
    """若 users 表中无超级管理员，则创建一个默认超级管理员并绑定早期数据"""
    username = os.environ.get("ADMIN_USERNAME", "admin").strip()
    password = os.environ.get("ADMIN_PASSWORD", "admin123").strip()
    email = os.environ.get("ADMIN_EMAIL", "admin@example.com").strip() or None
    credits = int(os.environ.get("ADMIN_CREDITS", "9999"))

    # 判断用户是否已存在
    result = await db.execute(select(User).filter(User.username == username))
    existing = result.scalar_one_or_none()
    if existing:
        logger.info("超级管理员已存在（用户名: %s），跳过创建", username)
        return existing

    # 密码哈希
    hashed = hash_password(password)

    admin = User(
        username=username,
        email=email,
        password_hash=hashed,
        credits=credits,
        role=ROLE_ADMIN,
        is_admin=True,
        is_active=True,
    )

    db.add(admin)
    await db.flush()  # 生成 admin.id
    admin_id = admin.id
    logger.info(
        "超级管理员创建成功：id=%s username=%s email=%s credits=%s",
        admin_id, username, email, credits,
    )

    # ---------- 绑定早期数据（未绑定 user_id 的历史归属该管理员） ----------
    try:
        from app.models.generation import Generation  # noqa: F811
        update_count_stmt = text(
            "UPDATE generations SET user_id = :aid WHERE user_id IS NULL"
        )
        r = await db.execute(update_count_stmt, {"aid": admin_id})
        updated_gen = r.rowcount if hasattr(r, "rowcount") else 0
        if updated_gen:
            logger.info("已绑定 %s 条早期生成记录（generations）到管理员", updated_gen)
    except Exception as e:
        logger.warning("跳过 generations 早期数据绑定：%s", e)

    try:
        from app.models.chat import ChatSession, ChatMessage  # noqa: F811
        r1 = await db.execute(
            text("UPDATE chat_sessions SET user_id = :aid WHERE user_id IS NULL"),
            {"aid": admin_id},
        )
        r2 = await db.execute(
            text("UPDATE chat_messages SET user_id = :aid WHERE user_id IS NULL"),
            {"aid": admin_id},
        )
        n1 = r1.rowcount if hasattr(r1, "rowcount") else 0
        n2 = r2.rowcount if hasattr(r2, "rowcount") else 0
        if n1 or n2:
            logger.info("已绑定 %s 条会话 / %s 条消息到管理员", n1, n2)
    except Exception as e:
        logger.warning("跳过 chat 早期数据绑定：%s", e)

    await db.commit()
    return admin


# =====================================================
# 3. 写入默认积分规则
# =====================================================
async def seed_default_credit_rules(db: AsyncSession):
    """若 credit_rules 表中缺少某条规则，则补插默认值（不覆盖已有配置）"""
    added = 0
    for rule in DEFAULT_CREDIT_RULES:
        result = await db.execute(
            select(CreditRule).filter(CreditRule.rule_key == rule["rule_key"])
        )
        existing = result.scalar_one_or_none()
        if existing:
            continue

        new_rule = CreditRule(
            rule_key=rule["rule_key"],
            name=rule["name"],
            value=rule["value"],
            description=rule.get("description", ""),
        )
        db.add(new_rule)
        added += 1
        logger.info("新增积分规则：%s = %s", rule["rule_key"], rule["value"])

    if added:
        await db.commit()
        logger.info("积分规则写入完成 ✓ 共新增 %s 条", added)
    else:
        logger.info("积分规则已完整，无需新增")


# =====================================================
# 4. 初始化系统配置（SMTP等）
# =====================================================
async def seed_system_configs(db: AsyncSession):
    """初始化默认系统配置（缺失的补上，不覆盖已有）"""
    try:
        from app.models.system_config import DEFAULT_SYSTEM_CONFIGS, SystemConfig

        result = await db.execute(select(SystemConfig.config_key))
        existing_keys = {row[0] for row in result.all()}

        added = 0
        for key, info in DEFAULT_SYSTEM_CONFIGS.items():
            if key not in existing_keys:
                db.add(SystemConfig(
                    config_key=key,
                    config_value=info["value"],
                    category=info["category"],
                    description=info["description"],
                ))
                added += 1
                logger.info("新增系统配置：%s = %s", key, info["value"])

        if added:
            await db.commit()
            logger.info("系统配置初始化完成 ✓ 共新增 %s 条", added)
        else:
            logger.info("系统配置已完整，无需新增")
    except Exception as e:
        logger.warning("跳过系统配置初始化：%s", e)


# =====================================================
# 主入口
# =====================================================
async def main():
    logger.info("==== 开始初始化数据库 ====")
    await create_tables()

    async with async_session() as session:
        await create_default_admin(session)
        await seed_default_credit_rules(session)
        await seed_system_configs(session)

    logger.info("==== 初始化完成 ====")
    print("")
    print("超级管理员账号：admin / admin123")
    print("（可通过环境变量 ADMIN_USERNAME / ADMIN_PASSWORD / ADMIN_EMAIL / ADMIN_CREDITS 修改）")
    print("首次登录后请在「用户管理」中修改默认密码和邮箱")
    print("新用户注册后将拥有独立的数据空间（历史记录、素材、画板、生成队列相互隔离）")
    print("")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("已取消")
