# 🪓 AxeCast Studio
### Universal Mobile Screen Mirroring & Multi-Device Control Suite
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-Apache_2.0-green.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-orange.svg)]()
[![Build](https://img.shields.io/github/actions/workflow/status/AxePH/AxeCast-Studio/build_release.yml?label=Build)](https://github.com/AxePH/AxeCast-Studio/actions)
[![Release](https://img.shields.io/github/v/release/AxePH/AxeCast-Studio?label=Latest%20Release)](https://github.com/AxePH/AxeCast-Studio/releases/latest)

**AxeCast Studio 🪓** is a high-performance, cross-platform mobile screen mirroring, multi-device management, and developer diagnostic studio. It features real-time **60 FPS screen casting**, native **AxeSQL Studio 🪓** database exploration, **Android Logcat Studio** with clean-copy filtering, and a drag-and-drop **Device File Explorer** for Windows, macOS, and Linux.

---

## 📥 Download (Pre-Built Binaries — No Python Required)

> **Download the latest release for your OS from the [Releases Page](https://github.com/AxePH/AxeCast-Studio/releases/latest).**

| Platform | Download | How to Use |
| :--- | :--- | :--- |
| 🪟 **Windows** (x64) | [`AxeCast-Studio-Windows-x64.zip`](https://github.com/AxePH/AxeCast-Studio/releases/latest) | Extract ZIP → double-click `AxeCast-Studio.exe` |
| 🍎 **macOS** (ARM64 / Intel) | [`AxeCast-Studio-macOS-arm64.zip`](https://github.com/AxePH/AxeCast-Studio/releases/latest) | Extract → move to `Applications` → open `AxeCast-Studio.app` |
| 🐧 **Linux** (x64) | [`AxeCast-Studio-Linux-x64.tar.gz`](https://github.com/AxePH/AxeCast-Studio/releases/latest) | Extract → run `./run.sh` |
| 📲 **Android APK** | [`axecast_stream.apk`](https://github.com/AxePH/AxeCast-Studio/releases/latest) | Install on phone for wireless streaming |

### 🍎 macOS First-Time Launch & Security Notice (Gatekeeper):

Because AxeCast Studio is an open-source binary distributed outside the Mac App Store, macOS Gatekeeper may show a security prompt on first launch (*"Apple could not verify..."* or *"Not Opened"*):

#### 🔹 Method 1: Unlock via Terminal (Recommended — One-Time)
Open Terminal and run:
```bash
# If installed in Applications:
xattr -cr /Applications/AxeCast-Studio.app

# If running directly from Downloads:
xattr -cr ~/Downloads/AxeCast-Studio.app
```

#### 🔹 Method 2: Allow in System Settings
1. Click **Done** on the security warning dialog.
2. Go to **Apple Menu ()** → **System Settings** → **Privacy & Security**.
3. Scroll to the bottom and click **"Open Anyway"** next to the *AxeCast-Studio* prompt.

#### 🔹 Method 3: Right-Click Open
Right-click (or Control + Click) `AxeCast-Studio.app` in Finder → select **Open** → click **Open** on the confirmation prompt.

---

## 🚀 Quick Start (Run from Source Code)

If you prefer running from source code instead of the pre-built binary:

| Operating System | Recommended 1-Click Launch Method |
| :--- | :--- |
| **🪟 Windows** | Double-click **`run.bat`** (or the **`AxeCast Studio`** Desktop icon) |
| **🍎 macOS** | Double-click **`AxeCast Studio.command`** or run `./run.sh` |
| **🐧 Linux** | Execute `./run.sh` in Terminal |

---

## 🌟 Key Features

### 1. 📱 Multi-Device Screen Mirroring & Control
* **Ultra-Low Latency (~30ms)** smooth 60 FPS streaming powered by Hardware GPU Acceleration.
* Full keyboard and mouse passthrough for remote interaction, navigation, and typing.
* Global controls: **Mirror All** (cast all connected devices) and **Capture All** (simultaneous multi-device screenshots).

### 2. 🗄️ AxeSQL Studio 🪓 (Integrated Database Suite)
* Inspect, query, and edit Android SQLite databases directly on device in real time.
* Multi-Tab SQL Editor with syntax highlighting, live data grid, and automated schema visualizer.

### 3. 📁 Device File Explorer (Drag & Drop)
* Seamlessly transfer files between PC and Android devices via Drag & Drop.
* Inline file renaming (F2), cut/copy/paste clipboard support, and direct download to computer.

### 4. 📜 Android Logcat Studio & Studio Diagnostics
* Capture real-time logs filtered by package name, tag, or active foreground app.
* Toggle timestamp formatting on/off for clean, distraction-free log copying.
* Live dynamic metric badges counting total entries, errors (🔴), and warnings (🟡).

### 5. 📲 Companion APK Wireless Mode (No Developer Options)
* Stream high-framerate video and audio wirelessly using the companion **`axecast_stream.apk`** without enabling USB debugging.

### 6. 🌐 In-House Remote Session & Multi-Client Broadcasting
* **1-to-Many Remote Collaboration:** 1 Mobile Phone can broadcast its screen and real-time logs simultaneously to multiple PCs/Macs using a secure **6-digit Room Code**.
* **Zero 3rd-Party Dependencies:** Works 100% standalone without Tailscale, VPNs, or external services. Includes an embedded local relay server or connects to any custom relay.
* **Dual-Pane Remote Studio Viewer:** Integrated live screen mirror + searchable, color-coded Logcat stream in a single unified window.

---

## 📦 Setup & Prerequisites (Source Code)

### 🪟 Windows
```bash
# Simply run the batch launcher; dependencies will install automatically:
run.bat
```

### 🍎 macOS
```bash
# Install core platform tools via Homebrew (if not already installed):
brew install scrcpy android-platform-tools

# Run AxeCast Studio:
chmod +x run.sh
./run.sh
```

### 🐧 Linux (Ubuntu / Debian / Arch / Fedora)
```bash
# Install platform tools:
sudo apt install scrcpy adb

# Run AxeCast Studio:
chmod +x run.sh
./run.sh
```

---

## 📁 Project Architecture

```text
axecast_studio/
├── app.py                      # Main Application Entry Point
├── run.bat                     # 1-Click Launcher for Windows
├── run.sh                      # Shell Launcher for macOS / Linux
├── AxeCast Studio.command      # Clickable Launcher for macOS Finder
├── requirements.txt            # Python Package Dependencies
├── .github/workflows/          # GitHub Actions CI/CD (Auto-Build & Release)
│   └── build_release.yml       # Nuitka build for Windows, macOS, Linux
├── assets/                     # High-Resolution Application Icons (ICO, PNG)
├── bin/                        # Portable ADB and Scrcpy Runtime Binaries
├── core/                       # Engine & Core Logic Modules
│   ├── adb_manager.py          # Android Debug Bridge Controller
│   ├── mirror_engine.py        # Scrcpy Mirroring & Video Recording Engine
│   ├── studio_logger.py        # Centralized Studio Event & Diagnostic Logger
│   ├── auto_discovery.py       # Local Wi-Fi Beacon & Device Auto-Discovery
│   └── system_detector.py      # Cross-Platform OS & Binary Path Resolver
├── ui/                         # User Interface Components (CustomTkinter)
│   ├── main_window.py          # Main Application Dashboard
│   ├── device_card.py          # Per-Device Control & Status Cards
│   ├── sqlite_studio_dialog.py # AxeSQL Studio Database Manager
│   ├── logcat_dialog.py        # Android Logcat Studio & Live Filter
│   ├── file_explorer_view.py   # Device File Explorer & Transfer View
│   └── modern_context_menu.py  # 2-Block Styled Context Menu
└── axecast_stream.apk          # Companion Android Streaming App (20.5 KB)
```

---

## 🤖 CI/CD: Automated Cross-Platform Builds (GitHub Actions)

This project includes a fully configured GitHub Actions workflow at [`.github/workflows/build_release.yml`](.github/workflows/build_release.yml) that:

1. **Triggers** automatically when you push a version tag (e.g. `git tag v1.0.0 && git push --tags`)
2. **Builds** native compiled binaries using **Nuitka** (Python → C++ → Machine Code) on:
   - 🪟 `windows-latest` → `AxeCast-Studio.exe`
   - 🍎 `macos-latest` → `AxeCast-Studio.app`
   - 🐧 `ubuntu-latest` → `AxeCast-Studio` (ELF binary)
3. **Publishes** all 3 platform builds to a GitHub Release page with download table
4. **Protects** your source code — the compiled binaries contain zero Python source files

### How to trigger a release:
```bash
git add .
git commit -m "feat: release v1.0.0"
git tag v1.0.0
git push origin main --tags
```

GitHub will automatically build all 3 platforms and create a release page with download links within ~10-15 minutes.

---

## 📄 License
This project is open-source and licensed under the [Apache License 2.0](LICENSE). You are free to use, modify, and distribute it for both commercial and personal projects.
