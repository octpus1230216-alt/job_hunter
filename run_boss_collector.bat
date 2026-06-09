@echo off
chcp 65001 >nul
echo ============================================================
echo   Boss直聘 职位采集器（二终端版）
echo   同时启动: Chrome + 数据接收 + 指令桥接（端口 9999）
echo ============================================================
echo.
echo 💡 然后在另一个终端运行: streamlit run app.py
echo.

set PYTHON=C:\ProgramData\WorkBuddy\chromium-env\6od91a\.workbuddy\binaries\python\envs\default\Scripts\python.exe
set SCRIPT_DIR=%~dp0

echo 🚀 启动中...
echo.

"%PYTHON%" "%SCRIPT_DIR%boss_collector_cdp.py"

pause
