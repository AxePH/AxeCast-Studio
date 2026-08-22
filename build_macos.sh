#!/usr/bin/env bash
# ============================================================
# AxeCast Studio - Fast Local macOS App Builder
# Builds native AxeCast-Studio.app in ~20 seconds
# ============================================================

set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🪓 AxeCast Studio - Local macOS .app Builder"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# 1. Check/Setup Virtual Environment
if [ -f "/opt/homebrew/bin/python3" ]; then
    SYS_PY="/opt/homebrew/bin/python3"
elif [ -f "/usr/local/bin/python3" ]; then
    SYS_PY="/usr/local/bin/python3"
else
    SYS_PY="python3"
fi

if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    $SYS_PY -m venv venv
fi

PYTHON_EXEC="venv/bin/python3"
PIP_EXEC="venv/bin/pip"

# 2. Install dependencies & PyInstaller
echo "📦 Installing build dependencies..."
$PIP_EXEC install -r requirements.txt --quiet
$PIP_EXEC install pyinstaller --quiet

# 3. Generate icon.icns if needed
if [ ! -f "assets/icon.icns" ] && [ -f "assets/icon.png" ]; then
    echo "🎨 Generating macOS app icon..."
    mkdir -p assets/AppIcon.iconset
    sips -z 16 16     assets/icon.png --out assets/AppIcon.iconset/icon_16x16.png &>/dev/null
    sips -z 32 32     assets/icon.png --out assets/AppIcon.iconset/icon_16x16@2x.png &>/dev/null
    sips -z 32 32     assets/icon.png --out assets/AppIcon.iconset/icon_32x32.png &>/dev/null
    sips -z 64 64     assets/icon.png --out assets/AppIcon.iconset/icon_32x32@2x.png &>/dev/null
    sips -z 128 128   assets/icon.png --out assets/AppIcon.iconset/icon_128x128.png &>/dev/null
    sips -z 256 256   assets/icon.png --out assets/AppIcon.iconset/icon_128x128@2x.png &>/dev/null
    sips -z 256 256   assets/icon.png --out assets/AppIcon.iconset/icon_256x256.png &>/dev/null
    sips -z 512 512   assets/icon.png --out assets/AppIcon.iconset/icon_256x256@2x.png &>/dev/null
    sips -z 512 512   assets/icon.png --out assets/AppIcon.iconset/icon_512x512.png &>/dev/null
    sips -z 1024 1024 assets/icon.png --out assets/AppIcon.iconset/icon_512x512@2x.png &>/dev/null
    iconutil -c icns assets/AppIcon.iconset -o assets/icon.icns
    rm -rf assets/AppIcon.iconset
fi

# 4. Build .app bundle
echo "🔨 Compiling AxeCast-Studio.app bundle..."
rm -rf release/AxeCast-Studio.app build

venv/bin/pyinstaller \
  --noconfirm \
  --windowed \
  --name "AxeCast-Studio" \
  --icon "assets/icon.icns" \
  --add-data "assets:assets" \
  --add-data "axecast_stream.apk:." \
  --collect-all customtkinter \
  --collect-all tkinterdnd2 \
  --collect-all websockets \
  --collect-all aiortc \
  --collect-all av \
  --collect-all certifi \
  --distpath release \
  app.py

# 5. Apply ad-hoc codesign
echo "🔏 Applying ad-hoc codesign for macOS..."
codesign --force --deep --sign - release/AxeCast-Studio.app 2>/dev/null || true

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Build Complete! App generated at:"
echo "   📂 release/AxeCast-Studio.app"
echo "   👉 Run using: open release/AxeCast-Studio.app"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
