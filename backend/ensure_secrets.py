# =====================================================
# .env 密钥保障脚本（由 start.sh / start.bat 在启动 uvicorn 前调用）
# JWT_SECRET / ENCRYPTION_KEY 缺失、为空或为已知占位串时，自动生成随机值写回 .env
# 仅用标准库，不 import app：config.py 的密钥校验发生在应用导入期，必须在此之前完成写回
# 直接裸跑 uvicorn 的场景不经过本脚本，需自行配置密钥（config.py 会明确报错提示）
# =====================================================

import secrets
from pathlib import Path

# 与 app/core/config.py 的 insecure 黑名单对齐，另含 .env.example 的历史占位串
INSECURE_VALUES = {
    "change-me-please-this-is-not-secure",
    "change-me",
    "secret",
    "jwt-secret",
    "agnes-platform-default-encryption-key",
    "please-change-this-to-a-random-string-at-least-32-chars-long",
    "please-change-this-to-a-random-string-at-least-32-bytes-long",
}

KEYS = {
    "ENCRYPTION_KEY": lambda: secrets.token_urlsafe(32),
    "JWT_SECRET": lambda: secrets.token_urlsafe(48),
}


def _needs_generate(value: str) -> bool:
    value = value.strip().strip('"').strip("'")
    return not value or value in INSECURE_VALUES


def ensure_secrets(env_path: Path) -> None:
    if not env_path.exists():
        print(f"[ensure_secrets] {env_path} 不存在，跳过")
        return

    lines = env_path.read_text(encoding="utf-8").splitlines()
    generated = []
    for i, line in enumerate(lines):
        for key, gen in KEYS.items():
            if not line.startswith(f"{key}="):
                continue
            value = line.split("=", 1)[1]
            if _needs_generate(value):
                lines[i] = f"{key}={gen()}"
                generated.append(key)
            break

    if generated:
        env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"[ensure_secrets] 已自动生成随机密钥写入 .env：{', '.join(generated)}")
    else:
        print("[ensure_secrets] 密钥已配置，无需生成")


if __name__ == "__main__":
    ensure_secrets(Path(__file__).resolve().parent / ".env")
