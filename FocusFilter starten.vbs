Option Explicit

Dim shell, fileSystem, appFolder, command
Set shell = CreateObject("WScript.Shell")
Set fileSystem = CreateObject("Scripting.FileSystemObject")

appFolder = fileSystem.GetParentFolderName(WScript.ScriptFullName)
command = "cmd.exe /c """ & appFolder & "\FocusFilter starten.cmd"""
shell.Run command, 0, False
