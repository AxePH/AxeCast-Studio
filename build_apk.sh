#!/usr/bin/env bash
# ============================================================
# AxeCast Stream - Fast Local Android APK Builder
# Builds AxeCast-Stream-v1.0.4.apk
# ============================================================

set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🤖 AxeCast Stream - Local Android APK Builder"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

mkdir -p release

# Sync AXECAST_SERVER_URL from .env if present
if [ -f ".env" ]; then
    ENV_URL=$(grep "^AXECAST_SERVER_URL=" .env | cut -d '=' -f2- | tr -d '"' | tr -d "'")
    if [ -n "$ENV_URL" ]; then
        echo "⚙️  Syncing AXECAST_SERVER_URL=$ENV_URL from .env to Android local.properties..."
        touch mobile/android/local.properties
        # Remove old key if exists and append new one
        grep -v "^AXECAST_SERVER_URL=" mobile/android/local.properties > mobile/android/local.properties.tmp || true
        mv mobile/android/local.properties.tmp mobile/android/local.properties
        echo "AXECAST_SERVER_URL=$ENV_URL" >> mobile/android/local.properties
    fi
fi

if [ -f "mobile/android/gradlew" ]; then
    echo "🔨 Building APK via Gradle..."
    cd mobile/android
    ./gradlew assembleRelease --quiet
    cd "$DIR"
    cp mobile/android/app/build/outputs/apk/release/app-release.apk release/AxeCast-Stream-v1.0.4.apk
    cp release/AxeCast-Stream-v1.0.4.apk axecast_stream.apk
else
    echo "📦 Packaging existing AxeCast APK as release..."
    cp axecast_stream.apk release/AxeCast-Stream-v1.0.4.apk
fi

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Build Complete! APK generated at:"
echo "   📂 release/AxeCast-Stream-v1.0.4.apk"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Auto install to connected Android device via ADB
if command -v adb >/dev/null 2>&1; then
    DEVICES=$(adb devices | grep -v "List of devices" | grep "device$" | awk '{print $1}')
    if [ -n "$DEVICES" ]; then
        for DEV_SERIAL in $DEVICES; do
            echo "📲 Installing APK to device ($DEV_SERIAL)..."
            if ! adb -s "$DEV_SERIAL" install -r release/AxeCast-Stream-v1.0.4.apk; then
                echo "⚠️ Performing clean reinstall on $DEV_SERIAL..."
                adb -s "$DEV_SERIAL" uninstall com.axecast.stream >/dev/null 2>&1 || true
                adb -s "$DEV_SERIAL" install release/AxeCast-Stream-v1.0.4.apk
            fi
            echo "🚀 Launching AxeCast Stream on $DEV_SERIAL..."
            adb -s "$DEV_SERIAL" shell am start -n com.axecast.stream/.MainActivity >/dev/null 2>&1 || true
        done
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo "🎉 App installed & launched on your phone successfully!"
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    else
        echo "ℹ️  No USB/WiFi Android device detected (skipped auto-install)."
    fi
fi

