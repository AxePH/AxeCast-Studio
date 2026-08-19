#!/usr/bin/env bash
# AxeCast Studio Launcher for macOS & Linux

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"

# Check Python 3
if command -v python3 &>/dev/null; then
    PYTHON_CMD="python3"
elif command -v python &>/dev/null; then
    PYTHON_CMD="python"
else
    echo "❌ Python 3 is required but not found. Please install Python 3."
    exit 1
fi

echo "🪓 Starting AxeCast Studio on $(uname -s)..."
$PYTHON_CMD -m pip install -r requirements.txt --quiet
$PYTHON_CMD app.py
