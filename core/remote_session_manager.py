"""
AxeCast Remote Session Manager
Desktop-side WebSocket client that connects to a relay server,
receives live video frames and log streams, and sends touch/input events.
"""

import io
import json
import time
import base64
import asyncio
import logging
import threading
from typing import Callable, Optional, Dict, Any

try:
    import websockets
except ImportError:
    websockets = None

from PIL import Image

logger = logging.getLogger("axecast-remote")


class LogEntry:
    """Parsed log message from the remote device."""
    
    LEVEL_COLORS = {
        "V": "#94a3b8",  # Verbose - gray
        "D": "#38bdf8",  # Debug   - blue
        "I": "#10b981",  # Info    - green
        "W": "#f59e0b",  # Warn    - amber
        "E": "#ef4444",  # Error   - red
        "F": "#dc2626",  # Fatal   - dark red
    }
    
    def __init__(self, raw: str, level: str = "I", tag: str = "", message: str = "", timestamp: str = ""):
        self.raw = raw
        self.level = level.upper()[:1] if level else "I"
        self.tag = tag
        self.message = message
        self.timestamp = timestamp or time.strftime("%H:%M:%S")
    
    @classmethod
    def from_dict(cls, data: dict) -> "LogEntry":
        return cls(
            raw=data.get("raw", ""),
            level=data.get("level", "I"),
            tag=data.get("tag", ""),
            message=data.get("message", ""),
            timestamp=data.get("timestamp", "")
        )
    
    @property
    def color(self) -> str:
        return self.LEVEL_COLORS.get(self.level, "#94a3b8")
    
    @property
    def display_text(self) -> str:
        return f"[{self.timestamp}] {self.level}/{self.tag}: {self.message}"


class RemoteSessionManager:
    """
    Manages a remote session connection to the AxeCast Relay Server.
    
    Usage:
        session = RemoteSessionManager()
        session.connect("ws://relay:9820", "882-109",
            on_frame=my_frame_callback,
            on_log=my_log_callback,
            on_status=my_status_callback)
        # Later:
        session.send_touch(x=100, y=200, action="tap")
        session.disconnect()
    """
    
    def __init__(self):
        self.ws = None
        self.connected = False
        self.room_code: str = ""
        self.server_url: str = ""
        self.device_info: dict = {}
        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._stop_event = threading.Event()
        
        # Callbacks
        self._on_frame: Optional[Callable[[Image.Image], None]] = None
        self._on_log: Optional[Callable[[LogEntry], None]] = None
        self._on_status: Optional[Callable[[str, str], None]] = None  # (status, message)
        self._on_device_info: Optional[Callable[[dict], None]] = None
        
        # Stats
        self.fps: float = 0.0
        self.latency_ms: float = 0.0
        self.frames_received: int = 0
        self._last_fps_time: float = 0
        self._fps_frame_count: int = 0
    
    def connect(self, server_url: str, room_code: str,
                on_frame: Optional[Callable] = None,
                on_log: Optional[Callable] = None,
                on_status: Optional[Callable] = None,
                on_device_info: Optional[Callable] = None):
        """
        Connect to a remote session room (non-blocking, runs in background thread).
        """
        if not websockets:
            if on_status:
                on_status("error", "Missing 'websockets' package. Run: pip install websockets")
            return
        
        # Sanitize server URL
        url = server_url.strip()
        if url.startswith("https://"):
            url = "wss://" + url[8:]
        elif url.startswith("http://"):
            url = "ws://" + url[7:]
        elif not url.startswith("ws://") and not url.startswith("wss://"):
            url = "wss://" + url
            
        self.server_url = url
        self.room_code = room_code.replace("-", "").replace(" ", "").strip().upper()
        self._on_frame = on_frame
        self._on_log = on_log
        self._on_status = on_status
        self._on_device_info = on_device_info
        self._stop_event.clear()
        
        self._thread = threading.Thread(target=self._run_async_loop, daemon=True)
        self._thread.start()
    
    def disconnect(self):
        """Disconnect from the remote session."""
        self._stop_event.set()
        self.connected = False
        
        if self._loop and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(self._loop.stop)
        
        if self._on_status:
            self._on_status("disconnected", "Remote session ended.")
    
    def send_touch(self, x: int, y: int, action: str = "tap",
                   source_width: int = 0, source_height: int = 0):
        """Send touch event to the remote device."""
        self._send_msg({
            "type": "touch",
            "x": x, "y": y,
            "action": action,
            "sw": source_width,
            "sh": source_height
        })
    
    def send_key(self, text: str):
        """Send text input to the remote device."""
        self._send_msg({
            "type": "key",
            "text": text
        })
    
    def send_button(self, button: str):
        """Send hardware button press (home, back, recents, power, rotate)."""
        self._send_msg({
            "type": "button",
            "button": button
        })
    
    def _send_msg(self, data: dict):
        """Thread-safe message send."""
        if not self.connected or not self._loop:
            return
        raw = json.dumps(data)
        try:
            asyncio.run_coroutine_threadsafe(self._async_send(raw), self._loop)
        except Exception:
            pass
    
    async def _async_send(self, raw: str):
        if self.ws:
            try:
                await self.ws.send(raw)
            except Exception:
                pass
    
    def _run_async_loop(self):
        """Run the async event loop in a background thread."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._connect_and_receive())
        except Exception as e:
            logger.warning(f"Remote session loop error: {e}")
        finally:
            self._loop.close()
            self.connected = False
    
    async def _connect_and_receive(self):
        """Connect to relay server and process incoming messages."""
        if self._on_status:
            self._on_status("connecting", f"Connecting to {self.server_url}...")
        
        try:
            async with websockets.connect(
                self.server_url,
                max_size=2**22,  # 4MB max frame
                close_timeout=5
            ) as ws:
                self.ws = ws
                
                # Join the room
                await ws.send(json.dumps({
                    "type": "join_room",
                    "room_code": self.room_code
                }))
                
                self._last_fps_time = time.time()
                self._fps_frame_count = 0
                
                async for raw_msg in ws:
                    if self._stop_event.is_set():
                        break
                    
                    try:
                        msg = json.loads(raw_msg)
                    except json.JSONDecodeError:
                        continue
                    
                    msg_type = msg.get("type", "")
                    
                    if msg_type == "joined":
                        self.connected = True
                        self.device_info = msg.get("device_info", {})
                        if self._on_status:
                            self._on_status("connected", f"Connected to room {self.room_code}")
                        if self._on_device_info and self.device_info:
                            self._on_device_info(self.device_info)
                    
                    elif msg_type == "error":
                        if self._on_status:
                            self._on_status("error", msg.get("message", "Unknown error"))
                        break
                    
                    elif msg_type == "frame":
                        self._handle_frame(msg)
                    
                    elif msg_type == "log":
                        self._handle_log(msg)
                    
                    elif msg_type == "device_info":
                        self.device_info = msg.get("info", {})
                        if self._on_device_info:
                            self._on_device_info(self.device_info)
                    
                    elif msg_type == "room_closed":
                        if self._on_status:
                            self._on_status("closed", msg.get("message", "Room closed."))
                        break
                    
                    elif msg_type == "pong":
                        sent_ts = msg.get("ts", 0)
                        if sent_ts:
                            self.latency_ms = (time.time() - sent_ts) * 1000
        
        except websockets.exceptions.ConnectionClosed:
            if self._on_status:
                self._on_status("disconnected", "Connection closed.")
        except ConnectionRefusedError:
            if self._on_status:
                self._on_status("error", f"Cannot reach relay server at {self.server_url}")
        except Exception as e:
            if self._on_status:
                self._on_status("error", f"Connection error: {str(e)}")
        finally:
            self.ws = None
            self.connected = False
    
    def _handle_frame(self, msg: dict):
        """Decode base64 JPEG frame and invoke callback."""
        frame_data = msg.get("data")
        if not frame_data:
            return
        
        try:
            jpg_bytes = base64.b64decode(frame_data)
            img = Image.open(io.BytesIO(jpg_bytes)).convert("RGB")
            
            # FPS calculation
            self.frames_received += 1
            self._fps_frame_count += 1
            now = time.time()
            elapsed = now - self._last_fps_time
            if elapsed >= 1.0:
                self.fps = self._fps_frame_count / elapsed
                self._fps_frame_count = 0
                self._last_fps_time = now
            
            if self._on_frame:
                self._on_frame(img)
        except Exception as e:
            logger.debug(f"Frame decode error: {e}")
    
    def _handle_log(self, msg: dict):
        """Parse log message and invoke callback."""
        entry = LogEntry.from_dict(msg)
        if self._on_log:
            self._on_log(entry)


class EmbeddedRelayServer:
    """
    Runs the AxeCast Relay Server in a background thread inside AxeCast Studio.
    This allows the desktop app to act as its own relay (no external server needed).
    """
    
    def __init__(self, port: int = 9820):
        self.port = port
        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._server = None
        self.running = False
    
    def start(self) -> str:
        """Start the embedded relay server. Returns the server URL."""
        if self.running:
            return f"ws://localhost:{self.port}"
        
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self.running = True
        return f"ws://localhost:{self.port}"
    
    def stop(self):
        """Stop the embedded relay server."""
        self.running = False
        if self._loop and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(self._loop.stop)
    
    def _run(self):
        from server.signaling_server import RelayServer
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        
        server = RelayServer(host="0.0.0.0", port=self.port)
        try:
            self._loop.run_until_complete(server.start())
        except Exception:
            pass
        finally:
            self._loop.close()
            self.running = False
    
    @property
    def local_url(self) -> str:
        return f"ws://localhost:{self.port}"


_SHARED_EMBEDDED_SERVER: Optional[EmbeddedRelayServer] = None

def get_or_start_embedded_server(port: int = 9820) -> EmbeddedRelayServer:
    """Returns or auto-starts the global embedded relay server instance."""
    global _SHARED_EMBEDDED_SERVER
    if _SHARED_EMBEDDED_SERVER is None or not _SHARED_EMBEDDED_SERVER.running:
        _SHARED_EMBEDDED_SERVER = EmbeddedRelayServer(port=port)
        _SHARED_EMBEDDED_SERVER.start()
    return _SHARED_EMBEDDED_SERVER

