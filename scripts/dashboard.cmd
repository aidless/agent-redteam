@echo off
REM Streamlit launcher for Windows
REM Usage: scripts\dashboard.cmd

set PYTHON=C:\Users\Administrator\AppData\Roaming\uv\python\cpython-3.11-windows-x86_64-none\python.exe
set SCRIPT=%~dp0dashboard.py

"%PYTHON%" -m streamlit run "%SCRIPT%"
pause