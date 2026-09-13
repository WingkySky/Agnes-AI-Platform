#!/bin/bash
# =====================================================
# Agnes Platform 一键停止脚本 (macOS / Linux)
# 清理本项目所有相关进程（含多次启动残留的重复进程）：
#   - 后端 uvicorn (app.main:app，任意端口，含 --reload 子进程)
#   - 前端 vite / npm run dev（按工作目录限定在本项目内）
# 用法: ./stop.sh            停止全部
#       ./stop.sh --dry-run  只列出将停止的进程，不实际停止
# =====================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DRY_RUN=0
[[ "$1" == "--dry-run" || "$1" == "-n" ]] && DRY_RUN=1

collect_pids() {
    # 后端 uvicorn 主进程（任意端口）
    pgrep -f "uvicorn.*app\.main:app"
    # 其余候选（uvicorn --reload 子进程 / vite / npm run dev），
    # 再按工作目录过滤出本项目的，避免误杀其他项目同名进程
    for pid in $(pgrep -f "spawn_main|vite|npm run dev" 2>/dev/null); do
        cwd=$(lsof -a -p "$pid" -d cwd -Fn 2>/dev/null | grep '^n' | sed 's/^n//')
        [[ "$cwd" == "$SCRIPT_DIR" || "$cwd" == "$SCRIPT_DIR"/* ]] && echo "$pid"
    done
}

PIDS=$(collect_pids | sort -un)
if [ -z "$PIDS" ]; then
    echo "未发现 Agnes Platform 相关进程"
    exit 0
fi

echo "发现以下进程："
ps -o pid,command -p "$(echo "$PIDS" | paste -sd, -)" | cut -c1-160

if [ "$DRY_RUN" = 1 ]; then
    echo "(dry-run 模式，未实际停止)"
    exit 0
fi

kill $PIDS 2>/dev/null

# 等待最多 10 秒优雅退出，仍未退出的强制结束
for i in $(seq 1 10); do
    PIDS=$(collect_pids | sort -un)
    [ -z "$PIDS" ] && break
    sleep 1
done
if [ -n "$PIDS" ]; then
    echo "强制结束: $(echo "$PIDS" | tr '\n' ' ')"
    kill -9 $PIDS 2>/dev/null
fi

echo "Agnes Platform 进程已全部停止"
