#!/usr/bin/env bash
# ============================================================
# AxeCast Studio Launcher & Pre-Flight Environment Checker
# Platform: macOS & Linux
# ============================================================

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🪓 AxeCast Studio - System Environment Check"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# 1. Check Python 3
if [ -f "/opt/homebrew/bin/python3" ]; then
    PYTHON_CMD="/opt/homebrew/bin/python3"
elif [ -f "/usr/local/bin/python3" ]; then
    PYTHON_CMD="/usr/local/bin/python3"
elif command -v python3 &>/dev/null; then
    PYTHON_CMD="python3"
elif command -v python &>/dev/null; then
    PYTHON_CMD="python"
else
    echo "❌ Error: Python 3 is not installed."
    if [[ "$(uname -s)" == "Darwin" ]]; then
        echo "   👉 Please install Python via: brew install python python-tk"
    else
        echo "   👉 Please install Python via: sudo apt install python3 python3-venv python3-pip"
    fi
    exit 1
fi
echo "✅ Python runtime: $($PYTHON_CMD --version)"

# 2. Check Platform Tools (scrcpy & adb)
OS_TYPE="$(uname -s)"
HAS_ADB=false
HAS_SCRCPY=false

if command -v adb &>/dev/null || [ -f "/opt/homebrew/bin/adb" ] || [ -f "/usr/local/bin/adb" ] || [ -f "$HOME/Library/Android/sdk/platform-tools/adb" ]; then
    HAS_ADB=true
fi

if command -v scrcpy &>/dev/null || [ -f "/opt/homebrew/bin/scrcpy" ] || [ -f "/usr/local/bin/scrcpy" ]; then
    HAS_SCRCPY=true
fi

if [ "$HAS_ADB" = true ]; then
    echo "✅ Android Debug Bridge (ADB): Ready"
else
    echo "⚠️  ADB not found in PATH"
fi

if [ "$HAS_SCRCPY" = true ]; then
    echo "✅ Scrcpy Mirror Engine: Ready"
else
    echo "⚠️  Scrcpy engine not detected!"
    if [[ "$OS_TYPE" == "Darwin" ]]; then
        echo "   💡 To enable high-speed USB/Wi-Fi screen mirroring, run:"
        echo "      brew install scrcpy android-platform-tools"
    else
        echo "   💡 To enable high-speed USB/Wi-Fi screen mirroring, run:"
        echo "      sudo apt install scrcpy adb"
    fi
    echo ""
fi

# 3. Setup Virtual Environment (venv)
if [ ! -d "venv" ]; then
    echo "📦 Initializing Python Virtual Environment (venv)..."
    $PYTHON_CMD -m venv venv
fi

if [ -f "venv/bin/python3" ]; then
    PYTHON_EXEC="venv/bin/python3"
    PIP_EXEC="venv/bin/pip"
elif [ -f "venv/bin/python" ]; then
    PYTHON_EXEC="venv/bin/python"
    PIP_EXEC="venv/bin/pip"
else
    PYTHON_EXEC="$PYTHON_CMD"
    PIP_EXEC="$PYTHON_CMD -m pip"
fi

# 4. Check & Install Python Dependencies
echo "📦 Verifying Python dependencies..."
$PIP_EXEC install -r requirements.txt --quiet

echo "🚀 Launching AxeCast Studio..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
$PYTHON_EXEC app.py
