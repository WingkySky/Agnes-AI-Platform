@echo off
chcp 65001 >nul
:: =====================================================
:: Agnes AI Platform 后端启动脚本 (Windows)
:: =====================================================

:: 获取脚本所在目录
set SCRIPT_DIR=%~dp0
cd /d "%SCRIPT_DIR%"

echo.
echo ================================================
echo   Agnes AI Platform - 后端启动 (Windows)
echo ================================================
echo.

:: 查找空闲端口
set PORT=8000
netstat -ano | findstr ":8000 " >nul
if %errorlevel%==0 (
    echo  端口 8000 已被占用，尝试其他端口...
    set PORT=8001
)

:: 检查 .env 是否存在
if not exist ".env" (
    echo  [提示] .env 文件不存在，正在检查 .env.example...
    if exist ".env.example" (
        copy .env.example .env >nul
        echo  [成功] 已创建 .env 文件，请编辑并填入 AGNES_API_KEY
        echo.
    )
) else (
    echo  [成功] .env 文件已存在
    echo.
)

:: 检查 Python 虚拟环境
if exist ".venv\Scripts\python.exe" (
    set VENV_PY=.venv\Scripts\python.exe
    echo  [提示] 检测到虚拟环境，正在激活...
) else (
    set VENV_PY=python
    echo  [提示] 未检测到虚拟环境，将使用系统 Python
    echo         如需创建虚拟环境，运行: python -m venv .venv
)

:: 初始化数据库（幂等：表/管理员已存在则跳过）
echo.
echo  初始化数据库（创建表 + 默认超级管理员）...
%VENV_PY% init_db.py

echo.
echo ================================================
echo  启动后端服务 (端口 %PORT%)...
echo  API 文档: http://localhost:%PORT%/docs
echo  健康检查: http://localhost:%PORT%/health
echo ================================================
echo.
echo  按 Ctrl+C 停止服务
echo.

:: 启动 uvicorn（自动检测依赖是否安装）
%VENV_PY% -m uvicorn app.main:app --host 0.0.0.0 --port %PORT% --reload
