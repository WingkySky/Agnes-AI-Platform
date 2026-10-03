@echo off
rem =====================================================
rem Agnes AI Platform Windows 便携版启动脚本
rem 双击运行；首次运行如遇 SmartScreen 提示：
rem 点「更多信息」->「仍要运行」
rem =====================================================
setlocal
cd /d "%~dp0"
set "PY=%~dp0runtime\python\python.exe"
set "PYTHONPATH=%~dp0site-packages"

rem 端口探测：8000 被占（如开发服务在跑）则自动顺延
set PORT=8000
:findport
netstat -ano -p tcp | findstr LISTENING | findstr /C:":%PORT% " >nul 2>&1
if not errorlevel 1 (
    set /a PORT+=1
    goto findport
)
if not "%PORT%"=="8000" echo 端口 8000 已被占用（可能是开发服务），自动改用端口 %PORT%

if not exist "backend\.env" (
    copy "backend\.env.example" "backend\.env" >nul
    echo 已初始化配置文件 backend\.env
)

echo 正在确保安全密钥...
"%PY%" backend\ensure_secrets.py

rem 服务就绪后自动打开浏览器
start "" cmd /c "timeout /t 3 /nobreak >nul & start "" http://localhost:%PORT%"

cd backend
echo.
echo 服务启动中：http://localhost:%PORT%  （关闭本窗口或 Ctrl+C 停止）
echo.
"%PY%" -m uvicorn app.main:app --host 0.0.0.0 --port %PORT%
