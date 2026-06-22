#!/bin/bash
# =====================================================
# Agnes AI Platform 一键启动脚本 (macOS / Linux)
# =====================================================

# 获取脚本所在目录（支持符号链接）
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo ""
echo "============================================"
echo "   Agnes AI Platform - 启动中"
echo "============================================"

# ── 检查依赖 ──────────────────────────────────────

command -v python3 >/dev/null 2>&1 || {
    echo "错误: 需要 Python 3，请先安装"
    exit 1
}

PYTHON_CMD="python3"
# 如果有 python 命令（非 python3）也用上
command -v python >/dev/null 2>&1 && PYTHON_CMD="python"

PY_VER=$($PYTHON_CMD -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
if [ "$(echo "$PY_VER < 3.10" | bc)" = "1" ]; then
    echo "错误: Python $PY_VER 不满足要求（需要 3.10+）"
    exit 1
fi
echo "  Python $PY_VER ✓"

command -v node >/dev/null 2>&1 || {
    echo "警告: 未检测到 Node.js，前端将无法启动"
}
command -v npm >/dev/null 2>&1 && echo "  npm ✓"

# ── 启动后端 ──────────────────────────────────────

echo ""
echo "启动后端..."
BACKEND_DIR="$SCRIPT_DIR/backend"
cd "$BACKEND_DIR"

# 检查 .env
if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        cp .env.example .env
        echo "  [提示] 已从 .env.example 创建 .env，请编辑填入 AGNES_API_KEY"
    fi
fi

# 优先使用虚拟环境
if [ -d ".venv" ]; then
    source .venv/bin/activate
    PY="$SCRIPT_DIR/backend/.venv/bin/python"
else
    PY="$PYTHON_CMD"
fi

# 检查后端依赖
$PY -c "import fastapi" 2>/dev/null || {
    echo "  安装后端依赖..."
    $PY -m pip install -r requirements.txt -q
}

# 初始化数据库（幂等：表/管理员已存在则跳过）
echo ""
echo "  初始化数据库（创建表 + 默认超级管理员）..."
$PY init_db.py

# 查找空闲端口
PORT=8000
while nc -z 127.0.0.1 $PORT >/dev/null 2>&1; do
    PORT=$((PORT + 1))
done

echo ""
echo "  后端启动中 (端口 $PORT)..."
echo "  API 文档: http://localhost:$PORT/docs"
echo "  健康检查: http://localhost:$PORT/health"
echo ""

# 后台启动后端
$PY -m uvicorn app.main:app --host 0.0.0.0 --port $PORT --reload &
BACKEND_PID=$!

# 等待后端启动
sleep 3

# ── 启动前端 ──────────────────────────────────────

if command -v npm >/dev/null 2>&1; then
    echo ""
    echo "启动前端..."
    FRONTEND_DIR="$SCRIPT_DIR/frontend"
    cd "$FRONTEND_DIR"

    # 检查 node_modules
    if [ ! -d "node_modules" ]; then
        echo "  安装前端依赖（首次较慢）..."
        npm install
    fi

    # 查找空闲端口
    FE_PORT=5173
    while nc -z 127.0.0.1 $FE_PORT >/dev/null 2>&1; do
        FE_PORT=$((FE_PORT + 1))
    done

    echo ""
    echo "  前端启动中 (端口 $FE_PORT)..."
    echo "  访问地址: http://localhost:$FE_PORT"
    echo ""

    npm run dev -- --port $FE_PORT &
    FE_PID=$!
else
    echo ""
    echo "  [跳过] 未检测到 npm，前端未启动"
    echo "  请手动运行: cd frontend && npm install && npm run dev"
fi

# ── 清理函数 ──────────────────────────────────────

cleanup() {
    echo ""
    echo "正在停止服务..."
    [ -n "$BACKEND_PID" ] && kill $BACKEND_PID 2>/dev/null
    [ -n "$FE_PID" ] && kill $FE_PID 2>/dev/null
    echo "已停止"
    exit 0
}
trap cleanup SIGINT SIGTERM

echo ""
echo "============================================"
echo "   所有服务已启动"
echo "============================================"
echo ""
if command -v npm >/dev/null 2>&1; then
    echo "  前端: http://localhost:$FE_PORT"
fi
echo "  后端: http://localhost:$PORT"
echo "  API:  http://localhost:$PORT/docs"
echo ""
echo "  按 Ctrl+C 停止所有服务"
echo "============================================"

# 等待子进程
wait
