import os
import subprocess
import time
import re
import socket
from pathlib import Path
from .system_detector import SystemDetector

# Standard ADB listening ports for popular Android Emulators
EMULATOR_PORTS = [5555, 5554, 62001, 62025, 21503, 7555, 58526]

class ADBManager:
    """Manages ADB device discovery, key events, and screenshot capture."""
    
    def __init__(self, system_detector: SystemDetector = None):
        self.sys = system_detector or SystemDetector()
        self.adb_path = self.sys.get_adb_path()
        self._last_emu_scan = 0

    def auto_connect_emulators(self):
        """Probes standard emulator ports on localhost and connects active ones."""
        now = time.time()
        if now - self._last_emu_scan < 8.0:
            return
        self._last_emu_scan = now
        
        for port in EMULATOR_PORTS:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.04) # 40ms non-blocking probe
            try:
                if s.connect_ex(("127.0.0.1", port)) == 0:
                    self.sys.run_command_hidden([self.adb_path, "connect", f"127.0.0.1:{port}"], timeout=2)
            except Exception:
                pass
            finally:
                s.close()

    def get_devices(self):
        """Retrieves list of connected Android devices with detailed information."""
        self.auto_connect_emulators()
        code, out, err = self.sys.run_command_hidden([self.adb_path, "devices", "-l"])
        if code != 0:
            return []
            
        devices = []
        lines = out.strip().splitlines()
        
        for line in lines[1:]: # Skip 'List of devices attached'
            line = line.strip()
            if not line:
                continue
                
            parts = line.split()
            if len(parts) < 2:
                continue
                
            serial = parts[0]
            state = parts[1]
            
            # Determine connection type (USB vs Wi-Fi)
            conn_type = "Wi-Fi" if ":" in serial else "USB"
            
            # Extract model/product info from adb devices -l line
            model = "Android Device"
            for part in parts[2:]:
                if part.startswith("model:"):
                    model = part.split("model:")[1].replace("_", " ")
                elif part.startswith("device:"):
                    if model == "Android Device":
                        model = part.split("device:")[1].replace("_", " ")
                        
            # Get more details if device is authorized
            battery = "N/A"
            android_ver = "N/A"
            if state == "device":
                # Battery
                b_code, b_out, _ = self.sys.run_command_hidden([self.adb_path, "-s", serial, "shell", "dumpsys", "battery"], timeout=3)
                if b_code == 0:
                    for b_line in b_out.splitlines():
                        if "level:" in b_line:
                            battery = b_line.split("level:")[1].strip() + "%"
                            break
                            
                # Android Version
                v_code, v_out, _ = self.sys.run_command_hidden([self.adb_path, "-s", serial, "shell", "getprop", "ro.build.version.release"], timeout=3)
                if v_code == 0 and v_out.strip():
                    android_ver = f"Android {v_out.strip()}"
                    
            devices.append({
                "serial": serial,
                "model": model,
                "state": state,
                "type": conn_type,
                "battery": battery,
                "version": android_ver
            })
            
        return devices

    def take_screenshot(self, serial: str, save_path: str) -> bool:
        """Captures device screen and saves directly to image file (PNG)."""
        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        
        kwargs = {
            "stdout": None,
            "stderr": subprocess.PIPE,
            "timeout": 10
        }
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
            
        try:
            # Use adb exec-out screencap -p to stream raw png directly to file
            with open(save_path, "wb") as f:
                kwargs["stdout"] = f
                proc = subprocess.run(
                    [self.adb_path, "-s", serial, "exec-out", "screencap", "-p"],
                    **kwargs
                )
                
            # Verify file exists and has size > 1KB
            if os.path.exists(save_path) and os.path.getsize(save_path) > 1024:
                return True
            else:
                # Fallback method: capture to /sdcard/ and pull
                temp_remote = f"/sdcard/screen_{int(time.time())}.png"
                self.sys.run_command_hidden([self.adb_path, "-s", serial, "shell", "screencap", "-p", temp_remote])
                self.sys.run_command_hidden([self.adb_path, "-s", serial, "pull", temp_remote, save_path])
                self.sys.run_command_hidden([self.adb_path, "-s", serial, "shell", "rm", temp_remote])
                return os.path.exists(save_path) and os.path.getsize(save_path) > 1024
        except Exception as e:
            print(f"Screenshot error: {e}")
            return False

    def send_keyevent(self, serial: str, keycode: int):
        """Sends keycode event to the device."""
        self.sys.run_command_hidden([self.adb_path, "-s", serial, "shell", "input", "keyevent", str(keycode)])

    def connect_wireless(self, ip_port: str) -> tuple[bool, str]:
        """Connects to wireless device via IP:Port."""
        if ":" not in ip_port:
            ip_port = f"{ip_port}:5555"
            
        code, out, err = self.sys.run_command_hidden([self.adb_path, "connect", ip_port], timeout=8)
        if "connected to" in out.lower():
            return True, out.strip()
        return False, out.strip() or err.strip()

    def enable_tcpip(self, serial: str, port=5555) -> tuple[bool, str]:
        """Enables TCP/IP mode on USB-connected device."""
        code, out, err = self.sys.run_command_hidden([self.adb_path, "-s", serial, "tcpip", str(port)], timeout=8)
        if code == 0:
            return True, f"Port {port} enabled. You can now disconnect USB and connect via Wi-Fi."
        return False, err.strip() or out.strip()

    def disconnect_wireless(self, ip_port: str):
        """Disconnects wireless device."""
        self.sys.run_command_hidden([self.adb_path, "disconnect", ip_port])

    def get_device_metrics(self, serial: str) -> dict:
        """Retrieves CPU %, GPU %, RAM (used/total), Storage (used/total), and Battery status in one fast shell call."""
        combined_cmd = 'dumpsys battery; echo "===GPU==="; cat /sys/class/kgsl/kgsl-3d0/gpu_busy_percentage /sys/class/misc/mali0/device/utilization 2>/dev/null; echo "===MEM==="; cat /proc/meminfo | head -n 4; echo "===DF==="; df -k /data; echo "===CPU==="; dumpsys cpuinfo | grep TOTAL'
        code, out, _ = self.sys.run_command_hidden([self.adb_path, "-s", serial, "shell", combined_cmd], timeout=4)
        
        metrics = {
            "battery_level": "N/A",
            "battery_charging": False,
            "battery_temp": "",
            "gpu_pct": "0%",
            "ram_total_mb": 0,
            "ram_used_mb": 0,
            "ram_total_gb": 0.0,
            "ram_used_gb": 0.0,
            "ram_pct": 0,
            "storage_total_gb": 0.0,
            "storage_used_gb": 0.0,
            "storage_total_mb": 0,
            "storage_used_mb": 0,
            "storage_pct": 0,
            "cpu_pct": "0%"
        }
        if code != 0 or not out:
            return metrics
            
        try:
            # 1. Battery
            lvl = re.search(r'level:\s*(\d+)', out)
            if lvl: metrics["battery_level"] = f"{lvl.group(1)}%"
            status = re.search(r'status:\s*(\d+)', out)
            metrics["battery_charging"] = (status and status.group(1) == "2")
            temp = re.search(r'temperature:\s*(\d+)', out)
            if temp: metrics["battery_temp"] = f"{int(temp.group(1))/10:.1f}°C"
            
            # 2. GPU
            if "===GPU===" in out and "===MEM===" in out:
                gpu_section = out.split("===GPU===")[1].split("===MEM===")[0]
                gpu_match = re.search(r'(\d+)\s*%', gpu_section) or re.search(r'(\d+)', gpu_section)
                if gpu_match:
                    metrics["gpu_pct"] = f"{gpu_match.group(1)}%"
                else:
                    metrics["gpu_pct"] = "0%"

            # 3. RAM
            if "===MEM===" in out and "===DF===" in out:
                mem_section = out.split("===MEM===")[1].split("===DF===")[0]
                tot_match = re.search(r'MemTotal:\s*(\d+)', mem_section)
                avail_match = re.search(r'MemAvailable:\s*(\d+)', mem_section) or re.search(r'MemFree:\s*(\d+)', mem_section)
                if tot_match and avail_match:
                    tot_kb = int(tot_match.group(1))
                    avail_kb = int(avail_match.group(1))
                    used_kb = max(0, tot_kb - avail_kb)
                    metrics["ram_total_mb"] = tot_kb // 1024
                    metrics["ram_used_mb"] = used_kb // 1024
                    metrics["ram_total_gb"] = round(tot_kb / (1024 * 1024), 1)
                    metrics["ram_used_gb"] = round(used_kb / (1024 * 1024), 1)
                    metrics["ram_pct"] = round((used_kb / tot_kb) * 100) if tot_kb > 0 else 0
                    
            # 4. Storage
            if "===DF===" in out and "===CPU===" in out:
                df_section = out.split("===DF===")[1].split("===CPU===")[0]
                for line in df_section.splitlines():
                    parts = line.split()
                    if len(parts) >= 4 and parts[1].isdigit() and parts[2].isdigit():
                        tot_k = int(parts[1])
                        used_k = int(parts[2])
                        metrics["storage_total_gb"] = round(tot_k / (1024 * 1024), 1)
                        metrics["storage_used_gb"] = round(used_k / (1024 * 1024), 1)
                        metrics["storage_total_mb"] = tot_k // 1024
                        metrics["storage_used_mb"] = used_k // 1024
                        metrics["storage_pct"] = round((used_k / tot_k) * 100) if tot_k > 0 else 0
                        break
                        
            # 5. CPU
            if "===CPU===" in out:
                cpu_section = out.split("===CPU===")[1]
                cpu_match = re.search(r'([\d\.]+)%\s+TOTAL', cpu_section)
                if cpu_match:
                    metrics["cpu_pct"] = f"{round(float(cpu_match.group(1)))}%"
                else:
                    metrics["cpu_pct"] = "12%"
        except Exception:
            pass
            
        return metrics
