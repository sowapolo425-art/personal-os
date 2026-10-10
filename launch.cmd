@echo off
chcp 65001 >nul
cd /d "%~dp0"
where py >nul 2>&1
if errorlevel 1 (
  python scripts\launch.py %*
) else (
  py -3 scripts\launch.py %*
)
if errorlevel 1 (
  echo Install Python 3.11 or newer, then try again. See README for details.
  pause
)
