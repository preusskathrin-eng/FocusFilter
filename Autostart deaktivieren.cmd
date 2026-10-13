@echo off
setlocal
set "LINK_PATH=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\FocusFilter.lnk"

if exist "%LINK_PATH%" (
    del "%LINK_PATH%"
    echo Autostart wurde deaktiviert.
) else (
    echo Es war kein FocusFilter-Autostart eingerichtet.
)
pause
