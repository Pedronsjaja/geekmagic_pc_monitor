@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" src\pc_monitor.py
) else (
    python src\pc_monitor.py
)
pause
