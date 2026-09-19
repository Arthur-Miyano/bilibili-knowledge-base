@echo off
chcp 65001 >nul
setlocal
set "URL=http://127.0.0.1:8877"

powershell -NoProfile -Command "try { Invoke-RestMethod -Uri '%URL%/api/status' -TimeoutSec 2 | Out-Null; exit 0 } catch { exit 1 }" >nul 2>&1
if not errorlevel 1 (
    start "" "%URL%/#create"
    exit /b 0
)

cd /d "%~dp0"
python --version >nul 2>&1
if errorlevel 1 goto :python_missing

echo 正在启动 B站知识库，请保持此窗口运行。
python web_app.py
if not errorlevel 1 exit /b 0

echo.
echo [错误] B站知识库启动失败，请检查上方错误信息以及 8877 端口是否被占用。
pause
exit /b 1

:python_missing
echo [错误] 未找到 Python，请安装 Python 3.11 或更新版本并加入 PATH。
pause
exit /b 1
