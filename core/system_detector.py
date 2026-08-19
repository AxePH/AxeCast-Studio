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
        self._setup_system_path()

    def _setup_system_path(self):
        """Ensures ADB and Scrcpy directories are injected into system PATH and ADB env var."""
        current_path = os.environ.get("PATH", "")
        extra_paths = []
        if self.os_name == "Darwin":
            extra_paths = [
                "/opt/homebrew/bin",
                "/usr/local/bin",
                os.path.expanduser("~/Library/Android/sdk/platform-tools"),
                "/opt/homebrew/sbin"
            ]
        elif self.os_name == "Windows":
            local_appdata = os.environ.get("LOCALAPPDATA", "")
            if local_appdata:
                extra_paths.append(str(Path(local_appdata) / "Android" / "Sdk" / "platform-tools"))
            extra_paths.append(str(self.bin_dir))

        for p in extra_paths:
            if os.path.exists(p) and p not in current_path:
                current_path = f"{p}:{current_path}" if self.os_name != "Windows" else f"{p};{current_path}"

        os.environ["PATH"] = current_path
        
        # Set ADB environment variable directly so scrcpy always finds it
        adb_p = self.get_adb_path()
        if adb_p and os.path.exists(adb_p):
            os.environ["ADB"] = adb_p

    def get_environment(self) -> dict:
        """Returns clean environment dictionary with ADB and correct PATH injected."""
        env = os.environ.copy()
        adb_p = self.get_adb_path()
        if adb_p and os.path.exists(adb_p):
            env["ADB"] = adb_p
            adb_dir = os.path.dirname(adb_p)
            if adb_dir and adb_dir not in env.get("PATH", ""):
                sep = ";" if self.os_name == "Windows" else ":"
                env["PATH"] = f"{adb_dir}{sep}{env.get('PATH', '')}"
        return env
        
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
            "timeout": timeout,
            "env": self.get_environment()
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

    def check_prerequisites(self) -> dict:
        """Checks if ADB and Scrcpy runtime tools are present on the system."""
        adb_path = self.get_adb_path()
        engine_path = self.get_engine_path()
        
        adb_found = False
        if os.path.isabs(adb_path) and os.path.exists(adb_path):
            adb_found = True
        elif shutil.which(adb_path):
            adb_found = True
            
        engine_found = False
        if os.path.isabs(engine_path) and os.path.exists(engine_path):
            engine_found = True
        elif shutil.which(engine_path):
            engine_found = True
            
        return {
            "os": self.os_name,
            "adb_found": adb_found,
            "adb_path": adb_path if adb_found else None,
            "engine_found": engine_found,
            "engine_path": engine_path if engine_found else None,
            "all_ok": adb_found and engine_found
        }
