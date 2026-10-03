#!/bin/sh
# =====================================================
# Agnes AI Platform 容器入口
# - 把用户产物目录（uploads/logs/data）软链进数据卷 /app/data
# - JWT_SECRET / ENCRYPTION_KEY 持久化到数据卷 secrets.env
#   （优先环境变量注入；否则首次启动生成、升级镜像不失效）
# =====================================================
set -e

DATA_DIR="/app/data"
BACKEND_DIR="/app/backend"

mkdir -p "$DATA_DIR/uploads" "$DATA_DIR/logs" "$DATA_DIR/appdata"

# 用户产物目录软链进数据卷；目标已是真实目录（异常场景）则跳过并告警，不覆盖数据
link_dir() {
    src="$1"
    dst="$2"
    if [ -L "$src" ]; then
        return
    fi
    if [ -d "$src" ]; then
        echo "[entrypoint] 警告: $src 已是真实目录，跳过软链，该目录数据不会落入数据卷"
        return
    fi
    ln -s "$dst" "$src"
}
link_dir "$BACKEND_DIR/uploads" "$DATA_DIR/uploads"
link_dir "$BACKEND_DIR/logs" "$DATA_DIR/logs"
link_dir "$BACKEND_DIR/data" "$DATA_DIR/appdata"

# 密钥保障：env 注入 > 数据卷 secrets.env > 现场生成（config.py 校验发生在应用导入期，必须先于此完成）
if [ -z "$JWT_SECRET" ] || [ -z "$ENCRYPTION_KEY" ]; then
    SECRETS_FILE="$DATA_DIR/secrets.env"
    if [ -f "$SECRETS_FILE" ]; then
        . "$SECRETS_FILE"
    fi
    if [ -z "$JWT_SECRET" ] || [ -z "$ENCRYPTION_KEY" ]; then
        JWT_SECRET="${JWT_SECRET:-$(python -c 'import secrets; print(secrets.token_urlsafe(48))')}"
        ENCRYPTION_KEY="${ENCRYPTION_KEY:-$(python -c 'import secrets; print(secrets.token_urlsafe(32))')}"
        umask 177
        printf 'JWT_SECRET=%s\nENCRYPTION_KEY=%s\n' "$JWT_SECRET" "$ENCRYPTION_KEY" > "$SECRETS_FILE"
        umask 022
        echo "[entrypoint] 已生成随机密钥写入 $SECRETS_FILE"
    fi
    export JWT_SECRET ENCRYPTION_KEY
fi

cd "$BACKEND_DIR"
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
