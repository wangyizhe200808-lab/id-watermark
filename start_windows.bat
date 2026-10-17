@echo off
setlocal
cd /d "%~dp0"
if exist .venv\Scripts\python.exe (
  .venv\Scripts\python.exe app.py
) else (
  echo Please run install_windows.bat first.
  pause
  exit /b 1
)
if errorlevel 1 pause
