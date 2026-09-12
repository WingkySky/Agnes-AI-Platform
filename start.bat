@echo off
chcp 65001 >nul
:: =====================================================
:: Agnes AI Platform 一键启动脚本 (Windows)
:: =====================================================

:: 获取脚本所在目录
set SCRIPT_DIR=%~dp0
:: 去掉末尾反斜杠
set SCRIPT_DIR=%SCRIPT_DIR:~0,-1%

echo.
echo ================================================
echo   Agnes AI Platform - Starting
echo ================================================
echo.

:: ── 检查 Python ──────────────────────────────────
where python >nul 2>&1
if %errorlevel% neq 0 (
    where py >nul 2>&1
    if %errorlevel% neq 0 (
        echo [Error] Python not found, please install Python 3.10+
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
    echo   npm OK
) else (
    echo   [Warning] Node.js not found, frontend will not start
)

:: ── 启动后端 ─────────────────────────────────────

echo.
echo Starting backend...
cd /d "%SCRIPT_DIR%\backend"

:: 检查 .env
if not exist ".env" (
    if exist ".env.example" (
        copy .env.example .env >nul
        echo  [Note] Created .env, please set AGNES_API_KEY
    )
)

:: 优先使用虚拟环境
if exist ".venv\Scripts\python.exe" (
    set PY=%SCRIPT_DIR%\backend\.venv\Scripts\python.exe
    echo  Using virtual environment
) else (
    set PY=%PY_CMD%
)

:: 查找空闲端口
set PORT=8000
netstat -ano | findstr "LISTENING" | findstr ":%PORT% " >nul
if %errorlevel% equ 0 (
    echo  [Warning] Port %PORT% in use, trying next available port...
    set /a PORT+=1
)

:: 检查依赖
%PY% -c "import fastapi" 2>nul
if %errorlevel% neq 0 (
    echo  Installing backend dependencies...
    %PY% -m pip install -r requirements.txt -q
)

:: 初始化数据库
echo.
echo  Initializing database...
%PY% init_db.py

echo.
echo  Backend starting on port %PORT%...
echo  API Docs: http://localhost:%PORT%/docs
echo  Health:   http://localhost:%PORT%/health
echo.

:: 启动后端（后台）
start "Agnes Backend" /min cmd /c "%PY% -m uvicorn app.main:app --host 0.0.0.0 --port %PORT% --reload"

:: 等待后端启动
timeout /t 5 /nobreak >nul

:: ── 启动前端 ─────────────────────────────────────

where npm >nul 2>&1
if %errorlevel% equ 0 (
    echo.
    echo Starting frontend...
    cd /d "%SCRIPT_DIR%\frontend"

    if not exist "node_modules" (
        echo  Installing frontend dependencies (first time, this may take a while)...
        call npm install
    )

    :: 查找空闲端口
    set FE_PORT=5174
    :find_fe_port
    netstat -ano | findstr "LISTENING" | findstr ":%FE_PORT% " >nul
    if %errorlevel% equ 0 (
        echo  [Warning] Port %FE_PORT% in use, trying next available port...
        set /a FE_PORT+=1
        goto find_fe_port
    )

    echo.
    echo  Frontend starting on port %FE_PORT%...
    echo  Access: http://localhost:%FE_PORT%
    echo.

    start "Agnes Frontend" /min cmd /c "npm run dev -- --port %FE_PORT%"

    :: 等待前端启动
    timeout /t 3 /nobreak >nul
) else (
    echo.
    echo  [Skipped] npm not found, frontend not started
    echo  Run manually: cd frontend && npm install && npm run dev
)

:: ── 完成提示 ─────────────────────────────────────

echo.
echo ================================================
echo   All services started (running in background)
echo ================================================
echo.
if defined FE_PORT (
    echo   Frontend: http://localhost:%FE_PORT%
)
echo   Backend:  http://localhost:%PORT%
echo   API Docs: http://localhost:%PORT%/docs
echo.
echo   Close this window to stop all services
echo ================================================
echo.
pause
