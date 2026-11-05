#!/usr/bin/env bash
# Streamlit launcher. Uses python3 on PATH.
# Usage: bash scripts/dashboard.sh

SCRIPT="$(cd "$(dirname "$0")" && pwd)/dashboard.py"
python3 -m streamlit run "$SCRIPT"
