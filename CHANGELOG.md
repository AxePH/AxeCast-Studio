# 📋 Changelog

All notable changes to **AxeCast Studio** are documented in this file.

---

## [1.0.4] - 2026-08-23

### 🌟 Added
* 🌐 **Dual-Engine Streaming (WebRTC P2P + WebSocket Cloud Relay Fallback):** Guaranteed 100% video stream connectivity on 4G/5G mobile networks across strict carrier CGNAT.
* 🛡️ **TURN Relay Server Integration:** Built-in open TURN relay penetration (`openrelay.metered.ca`) for seamless NAT traversal.
* 💻 **Interactive Remote Terminal:** Real-time remote Android ADB shell execution with command history, colorized stdout/stderr, and quick debug shortcuts.
* 🔌 **1-Click Remote ADB Bridge:** Direct port tunnel for live building, running, and debugging in Android Studio & VS Code over WebRTC.
* 📱 **Active App Detection:** Real-time foreground application tracking and smart logcat filtering without ADB root requirements.

### 🐛 Fixed
* 🔧 Fixed WebRTC video capture dimensions alignment to even integers (preventing hardware encoder dropouts).
* 📜 Fixed logcat stream drop condition (`hasBufferedData`) and elevated process reading priority.
* 💻 Fixed `AdbTcpBridge` socket imports and multi-device installation logic in `build_apk.sh`.

---

## [1.0.3] - 2026-08-22

### 🌟 Added
* ⚡ Real-time dynamic video resolution scaling (360p, 480p, 720p, 1080p) in Android Stream app.
* 🔒 4-digit PIN authentication toggle for Remote Room protection.

---

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
