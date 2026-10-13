@echo off
setlocal
cd /d "%~dp0"

python --version >nul 2>nul
if %errorlevel%==0 (
    set "PYTHON_CMD=python"
) else (
    py -3 --version >nul 2>nul
    if errorlevel 1 (
        echo Python wurde nicht gefunden.
        echo Bitte Python installieren und danach erneut starten.
        pause
        exit /b 1
    )
    set "PYTHON_CMD=py -3"
)

%PYTHON_CMD% -c "import streamlit, pandas, plotly" >nul 2>nul
if errorlevel 1 (
    echo Benötigte Python-Pakete fehlen. Installation wird gestartet ...
    %PYTHON_CMD% -m pip install -r requirements.txt
    if errorlevel 1 (
        echo Installation fehlgeschlagen.
        pause
        exit /b 1
    )
)

powershell.exe -NoProfile -Command "try { if ((Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8507/_stcore/health' -TimeoutSec 2).StatusCode -eq 200) { Start-Process 'http://127.0.0.1:8507'; exit 0 } } catch {}; exit 1"
if %errorlevel%==0 exit /b 0

%PYTHON_CMD% -m streamlit run "%~dp0streamlit_app.py" --server.address=127.0.0.1 --server.port=8507 --server.headless=false --browser.gatherUsageStats=false
