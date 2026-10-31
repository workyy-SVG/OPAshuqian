@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Python environment is missing. Follow README.md to install dependencies first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m scripts.init_db
if errorlevel 1 exit /b 1
".venv\Scripts\python.exe" -m streamlit run app.py --server.address=127.0.0.1
pause
