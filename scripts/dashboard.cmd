@echo off
REM Streamlit launcher for Windows. Uses python on PATH.
REM Usage: scripts\dashboard.cmd

python -m streamlit run "%~dp0dashboard.py"
pause
