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

if not exist "backend\.env" (
    copy "backend\.env.example" "backend\.env" >nul
    echo 已初始化配置文件 backend\.env
)

echo 正在确保安全密钥...
"%PY%" backend\ensure_secrets.py

rem 服务就绪后自动打开浏览器
start "" cmd /c "timeout /t 3 /nobreak >nul & start "" http://localhost:8000"

cd backend
echo.
echo 服务启动中：http://localhost:8000  （关闭本窗口或 Ctrl+C 停止）
echo.
"%PY%" -m uvicorn app.main:app --host 0.0.0.0 --port 8000
