' JARVIS AI Assistant - silent launcher (no console window)
Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
WshShell.Run "dist\JARVIS.exe", 0, False
Set WshShell = Nothing
