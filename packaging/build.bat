@echo off
REM 本地一键构建桌面安装包（Windows）。
REM 前置：已安装 Python 3.11、NSIS（makensis 在 PATH 中）。
setlocal
cd /d %~dp0\..

if not exist .buildenv (
  python -m venv .buildenv
  call .buildenv\Scripts\activate.bat
  python -m pip install --upgrade pip
  pip install -r requirements-desktop.txt
) else (
  call .buildenv\Scripts\activate.bat
)

python -m PyInstaller packaging\desktop.spec --noconfirm --clean

where makensis >nul 2>nul
if errorlevel 1 (
  echo [错误] 未找到 makensis（NSIS）。请先安装 NSIS 并确保 makensis 在 PATH 中。
  echo         下载：https://nsis.sourceforge.io/Download
  exit /b 1
)

makensis packaging\installer.nsi

echo.
echo 构建完成：dist\job_hunter-setup.exe
endlocal
