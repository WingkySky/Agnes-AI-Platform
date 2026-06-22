#!/usr/bin/env python3
# =====================================================
# Agnes AI Platform 一键启动脚本（跨平台）
# - 自动检测操作系统类型
# - macOS / Linux: 调用同目录 start.sh
# - Windows: 调用同目录 start.bat
# - 无 shell 时（如纯 Python 环境）直接启动后端
# =====================================================

import sys
import os
import subprocess

# 获取脚本所在目录（resolve symlinks）
SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))

# 获取操作系统
IS_WINDOWS = sys.platform.startswith("win") or os.name == "nt"
IS_MACOS = sys.platform == "darwin"


def find_free_port(start=8000):
    """查找空闲端口"""
    import socket
    for port in range(start, start + 100):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.bind(("127.0.0.1", port))
            s.close()
            return port
        except OSError:
            continue
    return start  # 回退


def check_python():
    """检查 Python 版本"""
    ver = sys.version_info
    if ver.major < 3 or (ver.major == 3 and ver.minor < 10):
        print(f"错误: Python {ver.major}.{ver.minor} 不满足要求（需要 3.10+）")
        return False
    return True


def run_command(cmd, env=None, cwd=None):
    """阻塞执行命令（用于启动服务）"""
    try:
        proc = subprocess.Popen(
            cmd,
            env=env,
            cwd=cwd,
            shell=IS_WINDOWS,
        )
        proc.wait()
    except KeyboardInterrupt:
        print("\n已停止")
        proc.terminate()
    except Exception as e:
        print(f"执行失败: {e}")


def start_backend(venv_python: str | None = None):
    """启动后端服务"""
    backend_dir = os.path.join(SCRIPT_DIR, "backend")

    # 优先使用虚拟环境中的 Python
    venv_py = venv_python
    if not venv_py:
        if IS_WINDOWS:
            venv_py = os.path.join(backend_dir, ".venv", "Scripts", "python.exe")
        else:
            venv_py = os.path.join(backend_dir, ".venv", "bin", "python3")

    if not os.path.exists(venv_py):
        venv_py = "python"  # 回退系统 Python

    print(f"\n{'='*50}")
    print("  Agnes AI Platform - 后端启动")
    print(f"{'='*50}")

    # 检查 .env
    env_file = os.path.join(backend_dir, ".env")
    env_example = os.path.join(backend_dir, ".env.example")
    if not os.path.exists(env_file) and os.path.exists(env_example):
        import shutil
        shutil.copy(env_example, env_file)
        print(f"提示: 已自动创建 .env 文件，请编辑并填入 AGNES_API_KEY")
        print()

    # 检查依赖
    print("检查依赖...")
    req_file = os.path.join(backend_dir, "requirements.txt")
    try:
        subprocess.run(
            [venv_py, "-m", "pip", "show", "fastapi"],
            capture_output=True,
            cwd=backend_dir,
        ).check_returncode()
    except subprocess.CalledProcessError:
        print("安装后端依赖...")
        subprocess.run(
            [venv_py, "-m", "pip", "install", "-r", req_file],
            cwd=backend_dir,
        )

    port = find_free_port(8000)
    print(f"后端启动中 (端口 {port})...")
    print(f"  API 文档: http://localhost:{port}/docs")
    print(f"  健康检查: http://localhost:{port}/health")
    print(f"{'='*50}\n")

    cmd = [venv_py, "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", str(port), "--reload"]
    run_command(cmd, cwd=backend_dir)


def start_frontend():
    """启动前端服务"""
    frontend_dir = os.path.join(SCRIPT_DIR, "frontend")

    # 检查 node_modules
    if not os.path.exists(os.path.join(frontend_dir, "node_modules")):
        print("安装前端依赖...")
        npm = "npm.cmd" if IS_WINDOWS else "npm"
        subprocess.run([npm, "install"], cwd=frontend_dir)

    print(f"\n{'='*50}")
    print("  Agnes AI Platform - 前端启动")
    print(f"{'='*50}")

    port = find_free_port(5173)
    print(f"前端启动中 (端口 {port})...")
    print(f"  访问地址: http://localhost:{port}")
    print(f"{'='*50}\n")

    npm = "npm.cmd" if IS_WINDOWS else "npm"
    cmd = [npm, "run", "dev", "--", "--port", str(port)]
    run_command(cmd, cwd=frontend_dir)


def main():
    if not check_python():
        sys.exit(1)

    # 优先尝试 shell 脚本（更好的彩色输出和进度条）
    if IS_WINDOWS:
        sh = os.path.join(SCRIPT_DIR, "start.bat")
        if os.path.exists(sh):
            print("调用 start.bat 启动...")
            subprocess.run(["cmd", "/c", sh], cwd=SCRIPT_DIR)
            return
    else:
        sh = os.path.join(SCRIPT_DIR, "start.sh")
        if os.path.exists(sh):
            print("调用 start.sh 启动...")
            subprocess.run(["bash", sh], cwd=SCRIPT_DIR)
            return

    # 兜底：直接用 Python 启动（无 shell 环境时）
    print("未找到启动脚本，直接启动...")
    start_backend()
    start_frontend()


if __name__ == "__main__":
    main()
