# 📋 Changelog

All notable changes to **AxeCast Studio** will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.0.2] - 2026-08-21

### 🌟 Added
* **🌐 In-House Remote Session & 6-Digit Room Code (`AxeCast Remote Room`)**:
  * **Zero 3rd-Party Dependencies:** 100% standalone remote connection without Tailscale, VPNs, or paid cloud services.
  * **1-to-Many Broadcasting:** 1 Mobile device can broadcast its screen and live logs simultaneously to multiple PCs/Macs without battery or network penalties.
  * **In-House WebSocket Signaling & Relay Server (`server/signaling_server.py`):** Supports ephemeral 6-digit room codes (`XXX-XXX`) with 30-minute auto-expiry and in-memory zero-data retention.
  * **Dual-Pane Remote Studio Viewer (`ui/remote_viewer.py`):**
    * Left Pane (~60%): Real-time screen mirror with touch relay, screenshot capture, and navigation controls (Back, Home, Recents, Power, Rotate).
    * Right Pane (~40%): Live Logcat stream with search filter, color-coded level badges (`ALL`, `E`, `W`, `I`, `D`), auto-scroll lock, and `.txt` export.
    * Top Bar: Live telemetry badges showing device model, battery %, real-time FPS, and round-trip latency (ms).
  * **Embedded Local Host Relay (`ui/remote_room_dialog.py`):** 1-Click start/stop embedded relay server directly on developer's machine with local IP detection.
* **🍏 iOS ReplayKit Companion App Integration**:
  * Architecture support and CI/CD workflow integration for **`AxeCast-Stream.ipa`** (iOS 15.0 - iOS 18+).
* **🎯 Target Highest Platform Upgrades**:
  * Android: Target SDK 35 (Android 15), Min SDK 24.
  * iOS: Target iOS 18 (Xcode 16 SDK), Min iOS 15.0.
  * Desktop: Python 3.11/3.12, macOS 15 Sequoia (ARM64 M1/M2/M3/M4 & Intel), Windows 11 (24H2), Ubuntu 24.04 LTS.

### 🔄 Changed
* **Dynamic Multi-Platform CI/CD Pipeline (`.github/workflows/build_release.yml`):**
  * Automated builds for 5 ecosystem artifacts: Windows ZIP, macOS ZIP/TAR, Linux TAR, Android APK, and iOS IPA.
  * Dynamic release tag matching with automated release notes generation.
* **Dependency Updates:** Added `websockets>=12.0` with full PyInstaller bundle collection across all platforms.
* **Version Alignment:** Synchronized `CURRENT_VERSION` to `1.0.2` across the entire ecosystem.

---

## [1.0.1] - 2026-08-20

### 🌟 Added
* **🗄️ AxeSQL Studio 🪓**:
  * Embedded SQLite database explorer and multi-tab query editor for Android applications.
  * Automatic table schema visualizer, execution plan, and live data editing grid.
* **📁 Device File Explorer**:
  * Seamless drag-and-drop file transfer between PC/Mac and mobile device storage.
  * Inline file renaming (`F2`), context menus, and Android `MediaStore` automatic scan broadcasts.
  * Cross-platform system clipboard helper (`core/system_clipboard.py`) with native macOS AppleScript support.
* **🎨 macOS Native ICNS Icon Generator**:
  * Automated high-resolution iconset generation during macOS build process.

### 🐛 Fixed
* **macOS Environment Recovery:** Resolved `adb: command not found` on macOS GUI app bundles by injecting Homebrew and SDK paths into subprocess environments.
* **Filename Whitespace Handling:** Refactored regex parsing in `DeviceFileManager` to preserve consecutive spaces (e.g., Thai/Unicode filenames).
* **Tcl 9.0 Compatibility:** Fixed variable trace handler callbacks in SQL editor widgets.
* **Git Hygiene:** Added comprehensive `.gitignore` rules for temporary databases, logs, and OS caches.

---

## [1.0.0] - 2026-08-19

### 🚀 Initial Release
* **⚡ 60 FPS Hardware-Accelerated Mirroring:** Ultra-low latency (~30ms) screen casting with GPU decoding.
* **👥 Multi-Device Studio:** Simultaneous multi-device management, docked screen cards, and independent floating windows.
* **⚡ Global Controls:** `Mirror All` and `Capture All` multi-device shortcuts.
* **🔍 Emulator Auto-Discovery:** Native detection for LDPlayer, BlueStacks, NoxPlayer, MEmu, and Windows Subsystem for Android (WSA).
* **📊 Live Performance Telemetry:** Rolling real-time CPU, GPU, RAM, and Disk resource badges and canvas charts.
* **📜 Android Logcat Studio:** Real-time log capture with package filters, PID inspection, and distraction-free clean copying.
* **📲 Wireless Streaming Companion:** Initial local Wi-Fi MJPEG streaming mode via `axecast_stream.apk`.
* **📦 Cross-Platform Distribution:** Pre-compiled standalone releases for Windows (x64), macOS (ARM64/Intel), and Linux (x64).
