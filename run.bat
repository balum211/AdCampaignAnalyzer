@echo off
REM One-click local run on Windows: creates a virtual env, installs deps, starts the app.
cd /d "%~dp0"
if not exist .venv (
    python -m venv .venv
)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip >nul
pip install -r requirements.txt
streamlit run app.py
