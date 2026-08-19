import time
import threading
from typing import List, Dict, Any, Callable, Optional

class StudioLogger:
    """
    Centralized, thread-safe logger for AxeCast Studio application events,
    diagnostics, ADB status, and system operations.
    """
    _instance = None
    _lock = threading.RLock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(StudioLogger, cls).__new__(cls)
                cls._instance._init_logger()
            return cls._instance

    def _init_logger(self):
        self.logs: List[Dict[str, Any]] = []
        self.subscribers: List[Callable[[Dict[str, Any]], None]] = []
        self._max_logs = 5000
        
        # Log initial app startup
        self.info("SYSTEM", "AxeCast Studio 🪓 core engine initialized.")

    def log(self, level: str, tag: str, message: str):
        now_str = time.strftime("%Y-%m-%d %H:%M:%S")
        entry = {
            "timestamp": now_str,
            "level": level.upper(),
            "tag": tag.upper(),
            "message": message
        }
        with self._lock:
            self.logs.append(entry)
            if len(self.logs) > self._max_logs:
                self.logs = self.logs[-4000:]
                
            for sub in list(self.subscribers):
                try:
                    sub(entry)
                except Exception:
                    pass

    def info(self, tag: str, message: str):
        self.log("INFO", tag, message)

    def warn(self, tag: str, message: str):
        self.log("WARN", tag, message)

    def error(self, tag: str, message: str):
        self.log("ERROR", tag, message)

    def success(self, tag: str, message: str):
        self.log("SUCCESS", tag, message)

    def subscribe(self, callback: Callable[[Dict[str, Any]], None]):
        with self._lock:
            if callback not in self.subscribers:
                self.subscribers.append(callback)

    def unsubscribe(self, callback: Callable[[Dict[str, Any]], None]):
        with self._lock:
            if callback in self.subscribers:
                self.subscribers.remove(callback)

    def get_all_logs(self) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self.logs)

    def clear(self):
        with self._lock:
            self.logs.clear()

logger = StudioLogger()
