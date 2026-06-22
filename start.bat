@echo off
chcp 65001 >nul
:: =====================================================
:: Agnes AI Platform 一键启动脚本 (Windows)
:: =====================================================

:: 获取脚本所在目录
set SCRIPT_DIR=%~dp0
:: 去掉末尾反斜杠（避免路径问题）
set SCRIPT_DIR=%SCRIPT_DIR:~0,-1%

echo.
echo ================================================
echo   Agnes AI Platform - 启动中
echo ================================================
echo.

:: ── 检查 Python ──────────────────────────────────
where python >nul 2>&1
if %errorlevel% neq 0 (
    where py >nul 2>&1
    if %errorlevel% neq 0 (
        echo [错误] 未找到 Python，请先安装 Python 3.10+
        pause
        exit /b 1
    )
    set PY_CMD=py
) else (
    set PY_CMD=python
)

:: 检查 Python 版本
for /f "delims=" %%v in ('%PY_CMD% -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"') do set PY_VER=%%v
echo   Python %PY_VER%

:: ── 检查 Node.js ─────────────────────────────────
where npm >nul 2>&1
if %errorlevel% equ 0 (
    echo   npm ✓
) else (
    echo   [警告] 未检测到 Node.js，前端无法启动
)

:: ── 启动后端 ─────────────────────────────────────

echo.
echo 启动后端...
cd /d "%SCRIPT_DIR%\backend"

:: 检查 .env
if not exist ".env" (
    if exist ".env.example" (
        copy .env.example .env >nul
        echo  [提示] 已创建 .env，请编辑填入 AGNES_API_KEY
    )
)

:: 优先使用虚拟环境
if exist ".venv\Scripts\python.exe" (
    set PY=%SCRIPT_DIR%\backend\.venv\Scripts\python.exe
    echo  [提示] 使用虚拟环境
) else (
    set PY=%PY_CMD%
)

:: 查找空闲端口
set PORT=8000
netstat -ano | findstr "LISTENING" | findstr ":%PORT% " >nul
if %errorlevel% equ 0 (
    set PORT=8001
)

:: 检查依赖
%PY% -c "import fastapi" 2>nul
if %errorlevel% neq 0 (
    echo  安装后端依赖...
    %PY% -m pip install -r requirements.txt -q
)

:: 初始化数据库（幂等：表/管理员已存在则跳过）
echo.
echo  初始化数据库（创建表 + 默认超级管理员）...
%PY% init_db.py

echo.
echo  后端启动中 (端口 %PORT%)...
echo  API 文档: http://localhost:%PORT%/docs
echo  健康检查: http://localhost:%PORT%/health
echo.

:: 启动后端（后台）
start "Agnes Backend" /min "%PY%" -m uvicorn app.main:app --host 0.0.0.0 --port %PORT% --reload

:: 等待后端启动
timeout /t 3 /nobreak >nul

:: ── 启动前端 ─────────────────────────────────────

where npm >nul 2>&1
if %errorlevel% equ 0 (
    echo.
    echo 启动前端...
    cd /d "%SCRIPT_DIR%\frontend"

    if not exist "node_modules" (
        echo  安装前端依赖（首次较慢）...
        call npm install
    )

    :: 查找空闲端口
    set FE_PORT=5173
    :find_fe_port
    netstat -ano | findstr "LISTENING" | findstr ":%FE_PORT% " >nul
    if %errorlevel% equ 0 (
        set /a FE_PORT+=1
        goto find_fe_port
    )

    echo.
    echo  前端启动中 (端口 %FE_PORT%)...
    echo  访问地址: http://localhost:%FE_PORT%
    echo.

    start "Agnes Frontend" /min cmd /c "npm run dev -- --port %FE_PORT%"
) else (
    echo.
    echo  [跳过] 未检测到 npm，前端未启动
    echo  请手动运行: cd frontend ^&^& npm install ^&^& npm run dev
)

:: ── 完成提示 ─────────────────────────────────────

echo.
echo ================================================
echo   所有服务已启动（后台运行中）
echo ================================================
echo.
echo   前端: http://localhost:%FE_PORT%
echo   后端: http://localhost:%PORT%
echo   API:  http://localhost:%PORT%/docs
echo.
echo   关闭此窗口即可停止所有服务
echo ================================================
echo.
pause
