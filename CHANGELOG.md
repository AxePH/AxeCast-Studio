# 📋 Changelog

All notable changes to **AxeCast Studio** are documented in this file.

---

## [1.0.2] - 2026-08-21

### 🌟 Added
* 🌐 **In-House Remote Room:** 6-digit room code for 1-to-Many live screen & Logcat streaming (no VPN required).
* 🖥️ **Dual-Pane Remote Viewer:** Real-time screen mirror + searchable, color-coded Logcat stream.
* 🍏 **iOS ReplayKit Support:** CI/CD & build pipeline integration for `AxeCast-Stream.ipa`.
* 🎯 **Target Highest SDKs:** Android 15 (API 35), iOS 18 (Xcode 16), macOS 15, Windows 11 (24H2).

### 🔄 Changed
* 📦 **Unified Multi-Platform Release:** Automated builds for Windows ZIP, macOS ZIP, Linux TAR, Android APK, and iOS IPA.
* ⚡ **Performance:** Added `websockets` dependency with full PyInstaller bundles across all OS.

---

## [1.0.1] - 2026-08-20

### 🌟 Added
* 🗄️ **AxeSQL Studio 🪓:** Integrated SQLite database viewer and multi-tab query editor.
* 📁 **Device File Explorer:** Drag-and-drop file manager, inline renaming (`F2`), and MediaStore broadcast.
* 🎨 **macOS Retina Icon:** Auto-generated native `.icns` iconset during build.

### 🐛 Fixed
* 🍎 Fixed macOS GUI `adb` environment path resolution.
* 🔤 Fixed filename parsing for consecutive whitespace characters (Thai/Unicode names).
* 🧹 Cleaned up `.gitignore` rules for build artifacts.

---

## [1.0.0] - 2026-08-19

### 🚀 Initial Release
* ⚡ **60 FPS Mirroring:** Low-latency hardware-accelerated screen casting with multi-device controls.
* 🔍 **Emulator Auto-Discovery:** Instant detection for LDPlayer, BlueStacks, Nox, MEmu, and WSA.
* 📊 **Live Telemetry:** Real-time CPU, GPU, RAM, and Disk rolling canvas charts.
* 📜 **Logcat Studio:** Clean-copy Android log streaming with package and PID filters.
* 📦 **Cross-Platform:** Pre-compiled binaries for Windows, macOS, Linux, and Android APK.
