@echo off
setlocal
cd /d "%~dp0"

python -m unittest discover -s tests -v
if errorlevel 1 (
    echo.
    echo Mindestens ein Test ist fehlgeschlagen.
    pause
    exit /b 1
)

echo.
echo Alle Tests waren erfolgreich.
pause
