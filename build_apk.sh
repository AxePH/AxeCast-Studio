#!/usr/bin/env bash
# ============================================================
# AxeCast Stream - Fast Local Android APK Builder
# Builds AxeCast-Stream-v1.0.2.apk
# ============================================================

set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🤖 AxeCast Stream - Local Android APK Builder"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

mkdir -p release

if [ -f "mobile/android/gradlew" ]; then
    echo "🔨 Building APK via Gradle..."
    cd mobile/android
    ./gradlew assembleRelease --quiet
    cd "$DIR"
    cp mobile/android/app/build/outputs/apk/release/app-release.apk release/AxeCast-Stream-v1.0.2.apk
    cp release/AxeCast-Stream-v1.0.2.apk axecast_stream.apk
else
    echo "📦 Packaging existing AxeCast APK as release..."
    cp axecast_stream.apk release/AxeCast-Stream-v1.0.2.apk
fi

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Build Complete! APK generated at:"
echo "   📂 release/AxeCast-Stream-v1.0.2.apk"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
