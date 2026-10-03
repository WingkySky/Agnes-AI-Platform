# =====================================================
# 默认超管环境变量配置读取（与 ensure 逻辑隔离，便于测试打桩）
#
# 种子语义：仅当 ADMIN_USERNAME 与 ADMIN_PASSWORD 同时显式设置时才
# 种子默认超管（自动化部署场景）；未设置时不种任何账号，由首启
# 向导引导用户免登录创建管理员（见 routes/setup.py /bootstrap）。
# =====================================================

import os


def seed_credentials() -> tuple[str, str] | None:
    """ADMIN_USERNAME + ADMIN_PASSWORD 同时显式设置时返回 (用户名, 密码)，否则 None"""
    username = os.environ.get("ADMIN_USERNAME", "").strip()
    password = os.environ.get("ADMIN_PASSWORD", "").strip()
    if not username or not password:
        return None
    return username, password


def admin_email() -> str | None:
    return os.environ.get("ADMIN_EMAIL", "admin@example.com").strip() or None


def admin_credits() -> int:
    return int(os.environ.get("ADMIN_CREDITS", "9999"))
