@echo off
setlocal
cd /d "%~dp0"
py -3 -m venv .venv
if errorlevel 1 goto failed
.venv\Scripts\python.exe -m pip install --upgrade pip
if errorlevel 1 goto failed
.venv\Scripts\python.exe -m pip install .
if errorlevel 1 goto failed
echo Installation complete. Run start_windows.bat.
pause
exit /b 0
:failed
echo Installation failed. Check Python and the error above.
pause
exit /b 1
