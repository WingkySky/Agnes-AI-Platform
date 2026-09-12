#!/bin/bash
# =====================================================
# Agnes AI Platform 后端启动脚本
# =====================================================

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "========================================"
echo "  Agnes AI Platform - Backend Start"
echo "========================================"

# 检查 .env 文件
if [ ! -f ".env" ]; then
    echo "[Warning] .env file not found!"
    echo "  Please copy from .env.example and set AGNES_API_KEY"
    echo ""
    if [ -f ".env.example" ]; then
        cp .env.example .env
        echo "[Info] Created .env, please edit and set your API Key"
    fi
    echo ""
fi

# 检查虚拟环境
if [ -d ".venv" ]; then
    echo "Using virtual environment: .venv"
    PY="./.venv/bin/python"
else
    echo "[Warning] .venv not found, using system Python"
    echo "  Create with: python3 -m venv .venv"
    PY="python3"
    command -v python >/dev/null 2>&1 && PY="python"
fi

# 检查依赖
echo ""
echo "Checking dependencies..."
$PY -c "import fastapi" 2>/dev/null || {
    echo "  Installing dependencies..."
    $PY -m pip install -r requirements.txt -q
}

# 检查 8000 端口是否被占用
PORT=8000
if lsof -ti:$PORT >/dev/null 2>&1; then
    echo "[Warning] Port $PORT is in use, cleaning up..."
    kill $(lsof -ti:$PORT) 2>/dev/null
    sleep 1
    if lsof -ti:$PORT >/dev/null 2>&1; then
        kill -9 $(lsof -ti:$PORT) 2>/dev/null
        sleep 1
    fi
    echo "  Port freed"
    echo ""
else
    echo "  Port $PORT is free"
fi

echo ""
echo "Starting backend server on port $PORT..."
echo "  API Docs: http://localhost:$PORT/docs"
echo "  Health:   http://localhost:$PORT/health"
echo ""
echo "Press Ctrl+C to stop"
echo "========================================"
echo ""

# 启动 uvicorn
exec $PY -m uvicorn app.main:app --host 0.0.0.0 --port $PORT --reload
