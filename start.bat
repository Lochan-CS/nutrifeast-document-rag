@echo off
cd /d "%~dp0"
echo Starting NutriFeast Document RAG...
where py >nul 2>nul
if %errorlevel%==0 (py -3.11 -m venv .venv 2>nul) else (python -m venv .venv 2>nul)
if not exist .venv\Scripts\python.exe (echo Python installation not found. Install Python 3.11. & pause & exit /b 1)
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 (echo Dependency installation failed. & pause & exit /b 1)
start "" http://127.0.0.1:8765
.venv\Scripts\python.exe -m uvicorn app:app --host 127.0.0.1 --port 8765
pause
