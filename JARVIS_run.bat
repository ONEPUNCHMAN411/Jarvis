@echo off
REM JARVIS launcher - calls wscript explicitly so .vbs association does not matter
cd /d "%~dp0"
wscript.exe //B JARVIS.vbs
