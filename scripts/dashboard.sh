#!/usr/bin/env bash
# Streamlit launcher for Git Bash on Windows
# Usage: bash scripts/dashboard.sh

PYTHON="C:/Users/Administrator/AppData/Roaming/uv/python/cpython-3.11-windows-x86_64-none/python.exe"
SCRIPT="$(cd "$(dirname "$0")" && pwd)/dashboard.py"

"$PYTHON" -m streamlit run "$SCRIPT"