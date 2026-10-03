#!/bin/bash
# =====================================================
# Agnes AI Platform macOS 便携版启动脚本
# 首次运行若被 Gatekeeper 拦截，先在终端执行（目录换成实际解压路径）：
#   xattr -cr ~/Downloads/agnes-platform
# 之后双击本文件，或在终端运行：./start-macos.command
# =====================================================
cd "$(dirname "$0")"
export PYTHONPATH="$PWD/site-packages"
PY="$PWD/runtime/python/bin/python3"

# 端口探测：8000 被占（如开发服务在跑）则自动顺延，避免静默打到别的服务
PORT=8000
while nc -z 127.0.0.1 "$PORT" >/dev/null 2>&1; do
    PORT=$((PORT + 1))
done
if [ "$PORT" != "8000" ]; then
    echo "端口 8000 已被占用（可能是开发服务），自动改用端口 $PORT"
fi

if [ ! -f backend/.env ]; then
    cp backend/.env.example backend/.env
    echo "已初始化配置文件 backend/.env"
fi

echo "正在确保安全密钥..."
"$PY" backend/ensure_secrets.py

# 服务就绪后自动打开浏览器
( sleep 3; open "http://localhost:$PORT" ) &

cd backend
echo ""
echo "服务启动中：http://localhost:$PORT  （关闭本终端窗口或 Ctrl+C 停止）"
echo ""
exec "$PY" -m uvicorn app.main:app --host 0.0.0.0 --port "$PORT"
