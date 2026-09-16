# =====================================================
# 默认超管环境变量配置读取（与 ensure 逻辑隔离，便于测试打桩）
# =====================================================

import os


def admin_username() -> str:
    return os.environ.get("ADMIN_USERNAME", "admin").strip()


def admin_password() -> str:
    return os.environ.get("ADMIN_PASSWORD", "admin123").strip()


def admin_email() -> str | None:
    return os.environ.get("ADMIN_EMAIL", "admin@example.com").strip() or None


def admin_credits() -> int:
    return int(os.environ.get("ADMIN_CREDITS", "9999"))
