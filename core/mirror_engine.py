import os
import sys
import subprocess
import time
import signal
from pathlib import Path
from .system_detector import SystemDetector

class MirrorEngine:
    """AxeCast core screen mirroring engine with strict single-instance per device protection."""
    
    def __init__(self, system_detector: SystemDetector = None):
        self.sys = system_detector or SystemDetector()
        self.engine_path = self.sys.get_engine_path()
        self.active_processes = {}
        self.active_recordings = {}

    def is_mirroring(self, serial: str) -> bool:
        if serial in self.active_processes:
            proc = self.active_processes[serial]
            if proc.poll() is None:
                return True
            else:
                del self.active_processes[serial]
        return False

    def start_mirror(self, serial: str, model_name: str = "", options: dict = None) -> tuple[bool, str]:
        # Enforce single mirror instance per device
        if self.is_mirroring(serial):
            return True, "Already mirroring this device"
            
        options = options or {}
        
        success, msg = self._launch_mirror_process(serial, model_name, options, no_audio=not options.get("audio", True))
        if success:
            return True, "Success"
            
        print(f"Primary mirror failed: {msg}. Retrying with safe fallback (no-audio)...")
        success2, msg2 = self._launch_mirror_process(serial, model_name, options, no_audio=True, safe_mode=True)
        if success2:
            return True, "Success (Safe Mode)"
            
        return False, msg2 or msg

    def _launch_mirror_process(self, serial: str, model_name: str, options: dict, no_audio: bool = False, safe_mode: bool = False):
        cmd = [self.engine_path, "-s", serial]
        
        title = f"AxeCast - {model_name or serial}"
        cmd.extend(["--window-title", title])
        
        if safe_mode:
            cmd.extend(["--max-size", "1080", "--video-bit-rate", "4M", "--max-fps", "30"])
        else:
            max_size = options.get("max_size", "1080")
            if max_size and max_size != "Original":
                cmd.extend(["--max-size", str(max_size)])
                
            bitrate = options.get("bitrate", "8M")
            if bitrate:
                cmd.extend(["--video-bit-rate", str(bitrate)])
                
            max_fps = options.get("max_fps", "60")
            if max_fps:
                cmd.extend(["--max-fps", str(max_fps)])
                
        if options.get("always_on_top", False):
            cmd.append("--always-on-top")
            
        if options.get("turn_screen_off", False) and not safe_mode:
            cmd.append("--turn-screen-off")
            
        if options.get("stay_awake", True):
            cmd.append("--stay-awake")
            
        if no_audio:
            cmd.append("--no-audio")
            
        kwargs = {
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "text": True
        }
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
            
        try:
            proc = subprocess.Popen(cmd, **kwargs)
            
            time.sleep(0.6)
            ret = proc.poll()
            if ret is not None:
                _, err = proc.communicate(timeout=1)
                return False, err.strip() or f"Process exited with code {ret}"
                
            self.active_processes[serial] = proc
            return True, "Running"
        except Exception as e:
            return False, str(e)

    def start_recording(self, serial: str, model_name: str, output_file: str, options: dict = None) -> bool:
        if self.is_recording(serial):
            return False
            
        options = options or {}
        Path(output_file).parent.mkdir(parents=True, exist_ok=True)
        
        cmd = [self.engine_path, "-s", serial, f"--record={output_file}"]
        
        if output_file.endswith(".mkv"):
            cmd.append("--record-format=mkv")
        else:
            cmd.append("--record-format=mp4")
        
        title = f"AxeCast [RECORDING] - {model_name or serial}"
        cmd.extend(["--window-title", title])
        
        max_size = options.get("max_size", "1080")
        if max_size and max_size != "Original":
            cmd.extend(["--max-size", str(max_size)])
            
        bitrate = options.get("bitrate", "8M")
        if bitrate:
            cmd.extend(["--video-bit-rate", str(bitrate)])
            
        if not options.get("audio", True):
            cmd.append("--no-audio")
            
        creationflags = 0
        if self.sys.os_name == "Windows":
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP
            
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creationflags
            )
            self.active_recordings[serial] = {
                "proc": proc,
                "file": output_file,
                "start_time": time.time()
            }
            return True
        except Exception as e:
            return False

    def stop_recording(self, serial: str) -> str:
        if serial in self.active_recordings:
            rec_info = self.active_recordings.pop(serial)
            proc = rec_info["proc"]
            file_path = rec_info["file"]
            
            try:
                if self.sys.os_name == "Windows":
                    proc.send_signal(signal.CTRL_BREAK_EVENT)
                else:
                    proc.send_signal(signal.SIGINT)
                    
                proc.wait(timeout=4)
            except Exception:
                try:
                    proc.terminate()
                    proc.wait(timeout=2)
                except Exception:
                    pass
                    
            return file_path
        return ""

    def is_recording(self, serial: str) -> bool:
        if serial in self.active_recordings:
            proc = self.active_recordings[serial]["proc"]
            if proc.poll() is None:
                return True
            else:
                self.active_recordings.pop(serial, None)
        return False

    def get_record_duration(self, serial: str) -> str:
        if serial in self.active_recordings:
            elapsed = int(time.time() - self.active_recordings[serial]["start_time"])
            mins = elapsed // 60
            secs = elapsed % 60
            return f"{mins:02d}:{secs:02d}"
        return "00:00"

    def stop_mirror(self, serial: str):
        """Stop mirroring a specific device."""
        if serial in self.active_processes:
            proc = self.active_processes.pop(serial)
            try:
                proc.terminate()
                proc.wait(timeout=1.0)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass

    def stop_all(self):
        """Cleanly terminate all active mirror processes and recordings."""
        # 1. Stop all recordings cleanly to finalize video files
        for serial in list(self.active_recordings.keys()):
            try:
                self.stop_recording(serial)
            except Exception:
                pass
                
        # 2. Terminate all mirroring processes
        for serial, proc in list(self.active_processes.items()):
            try:
                proc.terminate()
                proc.wait(timeout=1.0)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        self.active_processes.clear()

