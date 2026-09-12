#!/bin/bash
# =====================================================
# Agnes AI Platform 一键启动脚本 (macOS / Linux)
# =====================================================

# 获取脚本所在目录（支持符号链接）
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo ""
echo "============================================"
echo "   Agnes AI Platform - Starting"
echo "============================================"

# ── 检查依赖 ──────────────────────────────────────

command -v python3 >/dev/null 2>&1 || {
    echo "Error: Python 3 required, please install"
    exit 1
}

PYTHON_CMD="python3"
command -v python >/dev/null 2>&1 && PYTHON_CMD="python"

PY_VER=$($PYTHON_CMD -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
if [ "$(echo "$PY_VER < 3.10" | bc)" = "1" ]; then
    echo "Error: Python $PY_VER not supported (need 3.10+)"
    exit 1
fi
echo "  Python $PY_VER OK"

command -v node >/dev/null 2>&1 || {
    echo "Warning: Node.js not found, frontend will not start"
}
command -v npm >/dev/null 2>&1 && echo "  npm OK"

# ── 启动后端 ──────────────────────────────────────

echo ""
echo "Starting backend..."
BACKEND_DIR="$SCRIPT_DIR/backend"
cd "$BACKEND_DIR"

# 检查 .env
if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        cp .env.example .env
        echo "  [Note] Created .env from .env.example, please set AGNES_API_KEY"
    fi
fi

# 优先使用虚拟环境
if [ -d ".venv" ]; then
    PY=".venv/bin/python"
    echo "  Using virtual environment: .venv"
else
    PY="$PYTHON_CMD"
fi

# 检查后端依赖
$PY -c "import fastapi" 2>/dev/null || {
    echo "  Installing backend dependencies..."
    $PY -m pip install -r requirements.txt -q
}

# 初始化数据库（幂等）
echo ""
echo "  Initializing database..."
$PY init_db.py

# 查找空闲端口
PORT=8000
if nc -z 127.0.0.1 $PORT >/dev/null 2>&1; then
    echo "  [Warning] Port $PORT is in use, trying next available port..."
    while nc -z 127.0.0.1 $PORT >/dev/null 2>&1; do
        PORT=$((PORT + 1))
    done
fi

echo ""
echo "  Backend starting on port $PORT..."
echo "  API Docs: http://localhost:$PORT/docs"
echo "  Health:   http://localhost:$PORT/health"
echo ""

# 后台启动后端
$PY -m uvicorn app.main:app --host 0.0.0.0 --port $PORT --reload --reload-delay 3 &
BACKEND_PID=$!

# 等待后端启动并验证
echo "  Waiting for backend to start..."
for i in $(seq 1 10); do
    if curl -s "http://localhost:$PORT/health" >/dev/null 2>&1; then
        echo "  Backend started successfully"
        break
    fi
    sleep 1
done

# ── 启动前端 ──────────────────────────────────────

if command -v npm >/dev/null 2>&1; then
    echo ""
    echo "Starting frontend..."
    FRONTEND_DIR="$SCRIPT_DIR/frontend"
    cd "$FRONTEND_DIR"

    # 检查 node_modules
    if [ ! -d "node_modules" ]; then
        echo "  Installing frontend dependencies (first time, this may take a while)..."
        npm install
    fi

    # 查找空闲端口
    FE_PORT=5174
    if nc -z 127.0.0.1 $FE_PORT >/dev/null 2>&1; then
        echo "  [Warning] Port $FE_PORT is in use, trying next available port..."
        while nc -z 127.0.0.1 $FE_PORT >/dev/null 2>&1; do
            FE_PORT=$((FE_PORT + 1))
        done
    fi

    echo ""
    echo "  Frontend starting on port $FE_PORT..."
    echo "  Access: http://localhost:$FE_PORT"
    echo ""

    npm run dev -- --port $FE_PORT > /tmp/agnes-frontend.log 2>&1 &
    FE_PID=$!

    # 等待前端启动
    sleep 3
    if curl -s "http://localhost:$FE_PORT" | grep -q "<title>" 2>/dev/null; then
        echo "  Frontend started successfully"
    else
        echo "  Frontend may still be starting..."
    fi
else
    echo ""
    echo "  [Skipped] npm not found, frontend not started"
    echo "  Run manually: cd frontend && npm install && npm run dev"
fi

# ── 清理函数 ──────────────────────────────────────

cleanup() {
    echo ""
    echo "Stopping services..."
    [ -n "$BACKEND_PID" ] && kill $BACKEND_PID 2>/dev/null
    [ -n "$FE_PID" ] && kill $FE_PID 2>/dev/null
    echo "Stopped"
    exit 0
}
trap cleanup SIGINT SIGTERM

echo ""
echo "============================================"
echo "   All services started"
echo "============================================"
echo ""
if command -v npm >/dev/null 2>&1; then
    echo "  Frontend: http://localhost:$FE_PORT"
fi
echo "  Backend:  http://localhost:$PORT"
echo "  API Docs: http://localhost:$PORT/docs"
echo ""
echo "  Press Ctrl+C to stop all services"
echo "============================================"

# 等待子进程
wait
