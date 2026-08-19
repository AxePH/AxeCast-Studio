import os
import re
import subprocess
import threading
import time
from typing import Callable, Optional, Dict, List, Any

class LogcatManager:
    """
    High-performance ADB Logcat streaming engine.
    Parses Android logcat threadtime output in real-time, supports package PID mapping,
    and cleanly stops background processes on demand.
    """

    # Threadtime format: "08-19 20:38:20.123  1234  5678 D TagName : Log message..."
    LOG_REGEX = re.compile(
        r"^(\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d{3})\s+(\d+)\s+(\d+)\s+([VDIWEF])\s+([^:]*?)\s*:\s*(.*)$"
    )

    def __init__(self, adb_manager, serial: str):
        self.adb = adb_manager
        self.serial = serial
        self.adb_path = getattr(adb_manager, "adb_path", "adb")
        self.process: Optional[subprocess.Popen] = None
        self.stream_thread: Optional[threading.Thread] = None
        self.is_running = False
        self.on_log_callback: Optional[Callable[[Dict[str, Any]], None]] = None
        
        # Package to PID cache
        self.pkg_pid_cache: Dict[str, List[int]] = {}
        self.pid_pkg_cache: Dict[int, str] = {}
        self._last_pid_scan = 0

    def start(self, on_log_entry: Callable[[Dict[str, Any]], None], clear_buffer: bool = True):
        """Starts streaming logcat in a background thread."""
        self.stop()
        self.on_log_callback = on_log_entry
        self.is_running = True

        if clear_buffer:
            try:
                # Clear device logcat ring-buffer so we start fresh
                subprocess.run(
                    [self.adb_path, "-s", self.serial, "logcat", "-c"],
                    capture_output=True,
                    timeout=2
                )
            except Exception:
                pass

        self.stream_thread = threading.Thread(target=self._stream_worker, daemon=True)
        self.stream_thread.start()

    def stop(self):
        """Stops the active logcat streaming process."""
        self.is_running = False
        if self.process:
            try:
                self.process.terminate()
                self.process.kill()
            except Exception:
                pass
            self.process = None

    def _stream_worker(self):
        cmd = [self.adb_path, "-s", self.serial, "logcat", "-v", "threadtime"]
        try:
            startupinfo = None
            if os.name == "nt":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = 0  # SW_HIDE

            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                startupinfo=startupinfo
            )

            for line in iter(self.process.stdout.readline, ""):
                if not self.is_running:
                    break
                line = line.rstrip("\r\n")
                if not line:
                    continue

                entry = self._parse_line(line)
                if self.on_log_callback and self.is_running:
                    self.on_log_callback(entry)

        except Exception as e:
            if self.is_running and self.on_log_callback:
                self.on_log_callback({
                    "raw": f"[AxeCast Logcat Engine Stopped: {e}]",
                    "timestamp": "",
                    "pid": 0,
                    "tid": 0,
                    "level": "E",
                    "tag": "AxeCast",
                    "message": f"Log stream stopped: {e}",
                    "package": ""
                })
        finally:
            self.stop()

    def _parse_line(self, line: str) -> Dict[str, Any]:
        """Parses a logcat line into a structured dictionary."""
        match = self.LOG_REGEX.match(line)
        if match:
            timestamp, pid_s, tid_s, level, tag, msg = match.groups()
            pid = int(pid_s)
            tid = int(tid_s)
            pkg = self.pid_pkg_cache.get(pid, "")
            return {
                "raw": line,
                "timestamp": timestamp,
                "pid": pid,
                "tid": tid,
                "level": level,
                "tag": tag.strip(),
                "message": msg,
                "package": pkg
            }
        else:
            return {
                "raw": line,
                "timestamp": "",
                "pid": 0,
                "tid": 0,
                "level": "I",
                "tag": "System",
                "message": line,
                "package": ""
            }

    def refresh_package_pids(self) -> Dict[str, List[int]]:
        """Scans active Android processes to map package names to PIDs."""
        now = time.time()
        if now - self._last_pid_scan < 2.0:
            return self.pkg_pid_cache

        self._last_pid_scan = now
        try:
            cmd = [self.adb_path, "-s", self.serial, "shell", "ps", "-A", "-o", "PID,NAME"]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=3)
            if res.returncode != 0:
                # Fallback for older Android
                cmd = [self.adb_path, "-s", self.serial, "shell", "ps"]
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=3)

            pkg_map: Dict[str, List[int]] = {}
            pid_map: Dict[int, str] = {}

            for line in res.stdout.splitlines():
                parts = line.strip().split()
                if len(parts) >= 2:
                    try:
                        # Find numeric PID and package name
                        pid = None
                        pkg = parts[-1]
                        for p in parts:
                            if p.isdigit():
                                pid = int(p)
                                break
                        if pid is not None and "." in pkg and not pkg.startswith("["):
                            if pkg not in pkg_map:
                                pkg_map[pkg] = []
                            pkg_map[pkg].append(pid)
                            pid_map[pid] = pkg
                    except Exception:
                        pass

            self.pkg_pid_cache = pkg_map
            self.pid_pkg_cache = pid_map
        except Exception:
            pass

        return self.pkg_pid_cache

    def get_foreground_package(self) -> str:
        """Retrieves the package name of the app currently active on the phone screen."""
        try:
            cmd = [self.adb_path, "-s", self.serial, "shell", "dumpsys", "window"]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=3)
            for line in res.stdout.splitlines():
                if "mCurrentFocus" in line or "mFocusedApp" in line:
                    match = re.search(r"([a-zA-Z0-9_]+(\.[a-zA-Z0-9_]+)+)", line)
                    if match:
                        pkg = match.group(1)
                        if not pkg.startswith("com.android.systemui"):
                            return pkg
        except Exception:
            pass
        return ""

    def get_installed_third_party_packages(self) -> List[str]:
        """Lists installed 3rd party apps for easy filtering."""
        try:
            cmd = [self.adb_path, "-s", self.serial, "shell", "pm", "list", "packages", "-3"]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=3)
            pkgs = []
            for line in res.stdout.splitlines():
                if line.startswith("package:"):
                    pkgs.append(line.replace("package:", "").strip())
            return sorted(pkgs)
        except Exception:
            return []
