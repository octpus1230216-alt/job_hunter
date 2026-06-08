@echo off
REM ============================================
REM  职位猎手 - 每日精选自动运行脚本
REM  配合 Windows 任务计划程序使用
REM ============================================

cd /d "C:\ProgramData\WorkBuddy\chromium-env\6od91a\WorkBuddy\2026-06-08-10-32-07\job-hunter"

REM 激活虚拟环境
call "C:\ProgramData\WorkBuddy\chromium-env\6od91a\.workbuddy\binaries\python\envs\default\Scripts\activate.bat"

REM 运行每日精选
python daily_digest.py > daily_run.log 2>&1

echo.
echo 完成时间: %date% %time%
