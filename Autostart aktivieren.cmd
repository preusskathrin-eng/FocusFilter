@echo off
setlocal
set "APP_VBS=%~dp0FocusFilter starten.vbs"
set "APP_DIR=%~dp0"
set "LINK_PATH=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\FocusFilter.lnk"

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$shell = New-Object -ComObject WScript.Shell; $shortcut = $shell.CreateShortcut($env:LINK_PATH); $shortcut.TargetPath = $env:APP_VBS; $shortcut.WorkingDirectory = $env:APP_DIR; $shortcut.Description = 'FocusFilter'; $shortcut.Save()"

if errorlevel 1 (
    echo Autostart konnte nicht eingerichtet werden.
) else (
    echo Autostart ist eingerichtet.
)
pause
