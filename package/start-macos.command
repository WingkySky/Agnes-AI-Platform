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

if [ ! -f backend/.env ]; then
    cp backend/.env.example backend/.env
    echo "已初始化配置文件 backend/.env"
fi

echo "正在确保安全密钥..."
"$PY" backend/ensure_secrets.py

# 服务就绪后自动打开浏览器
( sleep 3; open http://localhost:8000 ) &

cd backend
echo ""
echo "服务启动中：http://localhost:8000  （关闭本终端窗口或 Ctrl+C 停止）"
echo ""
exec "$PY" -m uvicorn app.main:app --host 0.0.0.0 --port 8000
