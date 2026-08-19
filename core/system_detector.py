import os
import sys
import subprocess
import shutil
from pathlib import Path

class SystemDetector:
    """Cross-platform helper to detect system OS, binary paths, and environment with strict UTF-8 decoding."""
    
    def __init__(self):
        self.os_name = self._detect_os()
        self.bin_dir = Path(__file__).resolve().parent.parent / "bin"
        
    def _detect_os(self) -> str:
        if sys.platform.startswith("win"):
            return "Windows"
        elif sys.platform.startswith("darwin"):
            return "Darwin"
        else:
            return "Linux"
            
    def get_adb_path(self) -> str:
        if self.os_name == "Windows":
            local_bin = self.bin_dir / "adb.exe"
            if local_bin.exists():
                return str(local_bin)
                
            local_appdata = os.environ.get("LOCALAPPDATA", "")
            if local_appdata:
                sdk_adb = Path(local_appdata) / "Android" / "Sdk" / "platform-tools" / "adb.exe"
                if sdk_adb.exists():
                    return str(sdk_adb)
            which_adb = shutil.which("adb.exe")
            if which_adb:
                return which_adb
            return "adb.exe"
        else:
            which_adb = shutil.which("adb")
            if which_adb:
                return which_adb
            mac_paths = [
                "/opt/homebrew/bin/adb",
                "/usr/local/bin/adb",
                os.path.expanduser("~/Library/Android/sdk/platform-tools/adb")
            ]
            for p in mac_paths:
                if os.path.exists(p):
                    return p
            return "adb"

    def get_engine_path(self) -> str:
        if self.os_name == "Windows":
            for name in ["scrcpy.exe", "engine.exe"]:
                local_bin = self.bin_dir / name
                if local_bin.exists():
                    return str(local_bin)
            which_bin = shutil.which("scrcpy.exe") or shutil.which("engine.exe")
            if which_bin:
                return which_bin
            return str(self.bin_dir / "scrcpy.exe")
        else:
            for name in ["scrcpy", "engine"]:
                which_bin = shutil.which(name)
                if which_bin:
                    return which_bin
            mac_paths = [
                "/opt/homebrew/bin/scrcpy",
                "/usr/local/bin/scrcpy"
            ]
            for p in mac_paths:
                if os.path.exists(p):
                    return p
            return "scrcpy"

    def run_command_hidden(self, cmd: list, timeout: int = 15) -> tuple[int, str, str]:
        """Runs command hidden with strict UTF-8 decoding to avoid ??? character corruption."""
        kwargs = {
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "timeout": timeout
        }
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
            
        try:
            res = subprocess.run(cmd, **kwargs)
            stdout = res.stdout.decode("utf-8", errors="replace")
            stderr = res.stderr.decode("utf-8", errors="replace")
            return res.returncode, stdout, stderr
        except subprocess.TimeoutExpired:
            return -1, "", "Command timed out"
        except Exception as e:
            return -1, "", str(e)
