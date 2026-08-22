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
import os
import ssl
import socket
from typing import Callable, Optional, Dict, Any, Tuple

# Force file logging for debugging
fh = logging.FileHandler("/tmp/axecast_remote.log")
fh.setLevel(logging.DEBUG)
logger = logging.getLogger("axecast-remote")
logger.setLevel(logging.DEBUG)
logger.addHandler(fh)

def _get_ssl_context(url: str) -> Optional[ssl.SSLContext]:
    """Get or create an SSL context that handles macOS cert issues gracefully."""
    if not url or not url.startswith("wss://"):
        return None
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        pass
    try:
        return ssl.create_default_context()
    except Exception:
        return ssl._create_unverified_context()


try:
    import websockets
except ImportError:
    websockets = None

try:
    from aiortc import RTCPeerConnection, RTCSessionDescription, RTCIceServer, RTCConfiguration, RTCIceCandidate
    import av
    HAS_AIORTC = True
except ImportError:
    HAS_AIORTC = False

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
    
    def __init__(self, raw: str, level: str = "I", tag: str = "", message: str = "", timestamp: str = "", pid: int = 0, package: str = ""):
        self.raw = raw
        self.level = level.upper()[:1] if level else "I"
        self.tag = tag
        self.message = message
        self.timestamp = timestamp or time.strftime("%H:%M:%S")
        self.pid = pid
        self.package = package
    
    @classmethod
    def from_dict(cls, data: dict) -> "LogEntry":
        return cls(
            raw=data.get("raw", ""),
            level=data.get("level", "I"),
            tag=data.get("tag", ""),
            message=data.get("message", ""),
            timestamp=data.get("timestamp", ""),
            pid=data.get("pid", 0),
            package=data.get("package", "")
        )
    
    @property
    def color(self) -> str:
        return self.LEVEL_COLORS.get(self.level, "#94a3b8")
    
    @property
    def display_text(self) -> str:
        pkg_part = f"[{self.package}] " if self.package else ""
        return f"[{self.timestamp}] {self.level} {pkg_part}{self.tag}: {self.message}"


def normalize_relay_url(server_url: str) -> str:
    """Sanitizes and auto-corrects relay server URLs (including stripping invalid ports from cloud domains)."""
    import re
    url = str(server_url).strip()
    if url.startswith("https://"):
        url = "wss://" + url[8:]
    elif url.startswith("http://"):
        url = "ws://" + url[7:]
    elif not url.startswith("ws://") and not url.startswith("wss://"):
        url = "wss://" + url
    
    # Auto-strip port 9820/8080 if pointing to cloud domains (Render, Fly, Heroku, etc.)
    cloud_domains = ("onrender.com", "fly.dev", "railway.app", "herokuapp.com", "pages.dev", "appspot.com")
    if any(cd in url.lower() for cd in cloud_domains):
        url = re.sub(r":(?:9820|8080)", "", url)
        
    return url


class AdbTcpBridge:
    """
    Local TCP server that forwards incoming ADB client connections (e.g. adb connect 127.0.0.1:5555)
    over WebRTC DataChannel / WebSocket to remote Android device's ADB daemon.
    """
    def __init__(self, session: "RemoteSessionManager"):
        self.session = session
        self.server_socket: Optional[socket.socket] = None
        self.port: int = 5555
        self.running = False
        self._thread: Optional[threading.Thread] = None
        self._clients: Dict[str, socket.socket] = {}
        self._client_lock = threading.Lock()

    def start(self, port: int = 5555) -> Tuple[bool, int, str]:
        if self.running and self.server_socket:
            return True, self.port, f"Already running on 127.0.0.1:{self.port}"
        
        target_port = port
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("127.0.0.1", target_port))
        except OSError:
            try:
                target_port = 5556
                s.bind(("127.0.0.1", target_port))
            except OSError:
                s.bind(("127.0.0.1", 0))
                target_port = s.getsockname()[1]
        
        s.listen(5)
        self.server_socket = s
        self.port = target_port
        self.running = True

        self._thread = threading.Thread(target=self._accept_loop, daemon=True)
        self._thread.start()
        logger.info(f"🔌 ADB TCP Bridge listening on 127.0.0.1:{self.port}")
        return True, self.port, f"Bridge started on 127.0.0.1:{self.port}"

    def stop(self):
        self.running = False
        if self.server_socket:
            try:
                self.server_socket.close()
            except Exception:
                pass
            self.server_socket = None

        with self._client_lock:
            for cid, sock in list(self._clients.items()):
                try:
                    sock.close()
                except Exception:
                    pass
                self.session._send_msg({"type": "adb_close", "cid": cid})
            self._clients.clear()

    def _accept_loop(self):
        while self.running and self.server_socket:
            try:
                client_sock, addr = self.server_socket.accept()
                cid = f"cid_{int(time.time() * 1000)}_{len(self._clients)}"
                with self._client_lock:
                    self._clients[cid] = client_sock
                
                # Notify remote to open socket
                self.session._send_msg({"type": "adb_open", "cid": cid})
                threading.Thread(target=self._client_reader, args=(cid, client_sock), daemon=True).start()
            except Exception:
                break

    def _client_reader(self, cid: str, sock: socket.socket):
        while self.running:
            try:
                data = sock.recv(32768)
                if not data:
                    break
                b64 = base64.b64encode(data).decode("ascii")
                self.session._send_msg({
                    "type": "adb_data",
                    "cid": cid,
                    "data": b64
                })
            except Exception:
                break
        
        with self._client_lock:
            self._clients.pop(cid, None)
        try:
            sock.close()
        except Exception:
            pass
        self.session._send_msg({"type": "adb_close", "cid": cid})

    def handle_remote_data(self, cid: str, b64_data: str):
        try:
            raw = base64.b64decode(b64_data)
            with self._client_lock:
                sock = self._clients.get(cid)
            if sock:
                sock.sendall(raw)
        except Exception as e:
            logger.debug(f"Error handling remote ADB data: {e}")

    def handle_remote_close(self, cid: str):
        with self._client_lock:
            sock = self._clients.pop(cid, None)
        if sock:
            try:
                sock.close()
            except Exception:
                pass


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
        self.adb_bridge = AdbTcpBridge(self)
        
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
        self.pin: str = ""
        self._fps_frame_count: int = 0

        # WebRTC & Real-time Speedometer
        self.pc = None
        self.is_p2p: bool = False
        self.speed_mbps = 0.0
        self.speed_kbps = 0.0
        self._last_fps_time = 0.0
        self._fps_frame_count = 0
        self._total_bytes_received = 0
        self._window_bytes = 0
        self._last_speed_time: float = time.time()
        
        # Lock for thread-safety
        self._frame_lock = threading.Lock()
        self._latest_frame: Optional[Image.Image] = None

    def _record_bytes(self, num_bytes: int):
        """Accumulate bytes for real-time throughput calculation."""
        self._total_bytes_received += num_bytes
        self._window_bytes += num_bytes
        now = time.time()
        elapsed = now - self._last_speed_time
        if elapsed >= 0.5:
            bps = (self._window_bytes * 8) / elapsed
            self.speed_mbps = bps / 1_000_000
            self.speed_kbps = (self._window_bytes / 1024) / elapsed
            self._window_bytes = 0
            self._last_speed_time = now
    
    def connect(self, server_url: str, room_code: str, pin: str = "",
                on_frame: Optional[Callable] = None,
                on_log: Optional[Callable] = None,
                on_status: Optional[Callable] = None,
                on_device_info: Optional[Callable] = None,
                on_packages: Optional[Callable] = None,
                on_active_app: Optional[Callable] = None,
                on_shell_output: Optional[Callable] = None,
                on_shell_done: Optional[Callable] = None):
        """
        Connect to a remote session room (non-blocking, runs in background thread).
        """
        if not websockets:
            if on_status:
                on_status("error", "Missing 'websockets' package. Run: pip install websockets")
            return
        
        # Sanitize server URL
        self.server_url = normalize_relay_url(server_url)
        self.pin = str(pin).strip()
        digits = "".join(c for c in str(room_code) if c.isdigit())
        if len(digits) == 6:
            self.room_code = f"{digits[:3]}-{digits[3:]}"
        else:
            self.room_code = str(room_code).strip()
            
        self._on_frame = on_frame
        self._on_log = on_log
        self._on_status = on_status
        self._on_device_info = on_device_info
        self._on_packages = on_packages
        self._on_active_app = on_active_app
        self._on_shell_output = on_shell_output
        self._on_shell_done = on_shell_done
        self._stop_event.clear()
        
        self._thread = threading.Thread(target=self._run_async_loop, daemon=True)
        self._thread.start()
    
    def disconnect(self):
        """Disconnect from the remote session."""
        self._stop_event.set()
        self.connected = False
        self._data_channel = None
        
        if self._loop and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(self._loop.stop)
        
        if self._on_status:
            self._on_status("disconnected", "Remote session ended.")
    
        self.adb_bridge = AdbTcpBridge(self)
        
    def start_adb_bridge(self, port: int = 5555) -> Tuple[bool, int, str]:
        """Start local TCP bridge for adb connect localhost:<port>."""
        return self.adb_bridge.start(port)
        
    def stop_adb_bridge(self):
        """Stop local TCP bridge."""
        self.adb_bridge.stop()

    def is_adb_bridge_running(self) -> bool:
        return self.adb_bridge.running and self.adb_bridge.server_socket is not None
        
    def get_adb_bridge_port(self) -> int:
        return self.adb_bridge.port

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
        
    def send_shell_command(self, command: str, cmd_id: Optional[str] = None) -> str:
        """Send shell command to remote device for execution."""
        if not cmd_id:
            cmd_id = f"cmd_{int(time.time() * 1000)}"
        self._send_msg({
            "type": "shell_exec",
            "id": cmd_id,
            "command": command
        })
        return cmd_id
    
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
        if self._data_channel and getattr(self._data_channel, "readyState", "") == "open":
            try:
                self._data_channel.send(raw)
                return
            except Exception:
                pass
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
        except (asyncio.CancelledError, RuntimeError):
            pass
        except Exception as e:
            logger.debug(f"Remote session loop ended: {e}")
        finally:
            try:
                pending = asyncio.all_tasks(self._loop)
                for task in pending:
                    task.cancel()
                if pending:
                    self._loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                self._loop.close()
            except Exception:
                pass
            self.connected = False
    
    async def _handle_connected_websocket(self, ws):
        self.ws = ws
        
        # Join the room
        await ws.send(json.dumps({
            "type": "join_room",
            "room_code": self.room_code,
            "pin": self.pin
        }))
        
        self._last_fps_time = time.time()
        self._fps_frame_count = 0
        
        logger.info(f"Connected to relay: {self.server_url}, joined room: {self.room_code}")
        
        async for raw_msg in ws:
            if self._stop_event.is_set():
                break
            
            if isinstance(raw_msg, bytes):
                # Direct binary JPEG frame (Zero JSON / Base64 parsing overhead)
                self._handle_binary_frame(raw_msg)
                continue

            try:
                logger.debug(f"Received WS msg: {raw_msg[:100]}")
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
                # Request WebRTC offer from mobile device
                try:
                    await ws.send(json.dumps({
                        "type": "request_offer",
                        "room_code": self.room_code
                    }))
                except Exception:
                    pass
            
            elif msg_type == "error":
                if self._on_status:
                    self._on_status("error", msg.get("message", "Unknown error"))
                break
            
            elif msg_type == "frame":
                self._handle_frame(msg)
            
            elif msg_type == "log":
                self._handle_log(msg)

            elif msg_type == "logs_batch":
                for log_item in msg.get("logs", []):
                    self._handle_log(log_item)
            
            elif msg_type == "device_info":
                self.device_info = msg.get("info", {})
                if self._on_device_info:
                    self._on_device_info(self.device_info)
            
            elif msg_type == "packages_list":
                pkgs = msg.get("packages", [])
                if self._on_packages and pkgs:
                    self._on_packages(pkgs)
                    
            elif msg_type == "active_app":
                pkg = msg.get("package", "")
                if self._on_active_app and pkg:
                    self._on_active_app(pkg)
            
            elif msg_type == "shell_output":
                cmd_id = msg.get("id", "")
                text = msg.get("text", "")
                is_err = msg.get("is_err", False)
                if self._on_shell_output:
                    self._on_shell_output(cmd_id, text, is_err)
                    
            elif msg_type == "shell_done":
                cmd_id = msg.get("id", "")
                exit_code = msg.get("exit_code", 0)
                if self._on_shell_done:
                    self._on_shell_done(cmd_id, exit_code)
                    
            elif msg_type == "adb_data":
                cid = msg.get("cid", "")
                data_b64 = msg.get("data", "")
                if cid and data_b64:
                    self.adb_bridge.handle_remote_data(cid, data_b64)
                    
            elif msg_type == "adb_close":
                cid = msg.get("cid", "")
                if cid:
                    self.adb_bridge.handle_remote_close(cid)
            
            elif msg_type == "webrtc_offer":
                logger.debug("Received WebRTC offer in websocket loop!")
                if HAS_AIORTC:
                    async def safe_handle():
                        try:
                            logger.debug("Calling _handle_webrtc_offer...")
                            await self._handle_webrtc_offer(msg, ws)
                        except Exception as e:
                            logger.error(f"❌ Error in _handle_webrtc_offer: {e}", exc_info=True)
                    asyncio.create_task(safe_handle())
                else:
                    logger.error("❌ Received WebRTC offer but aiortc is not installed!")

            elif msg_type == "webrtc_ice":
                if HAS_AIORTC and self.pc:
                    asyncio.create_task(self._handle_webrtc_ice(msg))

            elif msg_type == "room_closed":
                if self._on_status:
                    self._on_status("closed", msg.get("message", "Room closed."))
                break
            
            elif msg_type == "pong":
                sent_ts = msg.get("ts", 0)
                if sent_ts:
                    self.latency_ms = (time.time() - sent_ts) * 1000
    
    async def _connect_and_receive(self):
        """Connect to relay server and process incoming messages."""
        if self._on_status:
            self._on_status("connecting", f"Connecting to {self.server_url}...")
        
        ssl_ctx = _get_ssl_context(self.server_url)
        try:
            try:
                async with websockets.connect(
                    self.server_url,
                    ssl=ssl_ctx,
                    open_timeout=8,
                    max_size=2**22,  # 4MB max frame
                    close_timeout=5
                ) as ws:
                    await self._handle_connected_websocket(ws)
            except Exception as e:
                if "CERTIFICATE_VERIFY_FAILED" in str(e) and self.server_url.startswith("wss://"):
                    logger.warning("SSL verification failed, retrying with unverified context...")
                    async with websockets.connect(
                        self.server_url,
                        ssl=ssl._create_unverified_context(),
                        open_timeout=8,
                        max_size=2**22,
                        close_timeout=5
                    ) as ws:
                        await self._handle_connected_websocket(ws)
                else:
                    raise e
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
            if self.pc:
                try:
                    asyncio.create_task(self.pc.close())
                except Exception:
                    pass
            self.ws = None
            self.connected = False
            self.connected = False
    
    def _handle_frame(self, msg: dict):
        """Decode base64 JPEG frame and invoke callback."""
        frame_data = msg.get("data")
        if not frame_data:
            return
        
        try:
            jpg_bytes = base64.b64decode(frame_data)
            self._record_bytes(len(jpg_bytes))
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

    def _handle_binary_frame(self, raw_bytes: bytes):
        """Directly decode binary JPEG frame without Base64 overhead."""
        try:
            self._record_bytes(len(raw_bytes))
            img = Image.open(io.BytesIO(raw_bytes)).convert("RGB")
            
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
            logger.debug(f"Binary frame decode error: {e}")
    
    def _handle_log(self, msg: dict):
        """Parse log message and invoke callback."""
        self._record_bytes(len(msg.get("message", "")) + 50)
        entry = LogEntry.from_dict(msg)
        if self._on_log:
            self._on_log(entry)

    async def _handle_webrtc_offer(self, msg: dict, ws):
        logger.debug("_handle_webrtc_offer triggered!")
        if not HAS_AIORTC:
            logger.debug("HAS_AIORTC is false, returning")
            return
        if self.is_p2p:
            logger.debug("P2P already established, ignoring duplicate offer")
            return
        try:
            sdp = msg.get("sdp", "")
            if not sdp:
                logger.debug("SDP is empty, returning")
                return
            
            logger.debug(f"SDP length: {len(sdp)}")

            config = RTCConfiguration(iceServers=[
                RTCIceServer(urls=["stun:stun.l.google.com:19302"]),
                RTCIceServer(urls=["stun:stun1.l.google.com:19302"]),
                RTCIceServer(urls=["stun:stun2.l.google.com:19302"]),
                RTCIceServer(urls=["turn:openrelay.metered.ca:80", "turn:openrelay.metered.ca:443"], username="openrelay", credential="openrelay"),
                RTCIceServer(urls=["turn:openrelay.metered.ca:443?transport=tcp"], username="openrelay", credential="openrelay")
            ])
            self.pc = RTCPeerConnection(configuration=config)

            @self.pc.on("track")
            def on_track(track):
                logger.debug(f"Received track: {track.kind}")
                if track.kind == "video":
                    asyncio.create_task(self._consume_video_track(track))

            @self.pc.on("datachannel")
            def on_datachannel(channel):
                logger.debug("Datachannel created")
                self._data_channel = channel
                @channel.on("message")
                def on_msg(message):
                    self._record_bytes(len(message) if isinstance(message, (str, bytes)) else 64)
                    try:
                        data = json.loads(message)
                        m_type = data.get("type", "")
                        if m_type == "log":
                            self._handle_log(data)
                        elif m_type == "device_info":
                            self.device_info = data.get("info", {})
                            if self._on_device_info:
                                self._on_device_info(self.device_info)
                        elif m_type == "packages_list":
                            pkgs = data.get("packages", [])
                            if self._on_packages and pkgs:
                                self._on_packages(pkgs)
                        elif m_type == "active_app":
                            pkg = data.get("package", "")
                            if self._on_active_app and pkg:
                                self._on_active_app(pkg)
                        elif m_type == "shell_output":
                            cmd_id = data.get("id", "")
                            text = data.get("text", "")
                            is_err = data.get("is_err", False)
                            if self._on_shell_output:
                                self._on_shell_output(cmd_id, text, is_err)
                        elif m_type == "shell_done":
                            cmd_id = data.get("id", "")
                            exit_code = data.get("exit_code", 0)
                            if self._on_shell_done:
                                self._on_shell_done(cmd_id, exit_code)
                        elif m_type == "adb_data":
                            cid = data.get("cid", "")
                            data_b64 = data.get("data", "")
                            if cid and data_b64:
                                self.adb_bridge.handle_remote_data(cid, data_b64)
                        elif m_type == "adb_close":
                            cid = data.get("cid", "")
                            if cid:
                                self.adb_bridge.handle_remote_close(cid)
                    except Exception:
                        pass

            @self.pc.on("connectionstatechange")
            async def on_connectionstatechange():
                logger.debug(f"Connection state is {self.pc.connectionState}")

            @self.pc.on("iceconnectionstatechange")
            async def on_iceconnectionstatechange():
                logger.debug(f"ICE connection state is {self.pc.iceConnectionState}")

            @self.pc.on("icecandidate")
            async def on_ice(candidate):
                if candidate:
                    logger.debug("Found local ICE candidate, sending...")
                    await ws.send(json.dumps({
                        "type": "webrtc_ice",
                        "room_code": self.room_code,
                        "candidate": {
                            "candidate": candidate.candidate,
                            "sdpMid": candidate.sdpMid,
                            "sdpMLineIndex": candidate.sdpMLineIndex
                        }
                    }))

            logger.debug("Setting remote description...")
            offer = RTCSessionDescription(sdp=sdp, type="offer")
            await self.pc.setRemoteDescription(offer)
            
            logger.debug("Creating answer...")
            answer = await self.pc.createAnswer()
            
            logger.debug("Setting local description...")
            await self.pc.setLocalDescription(answer)

            logger.debug("Sending webrtc_answer...")
            await ws.send(json.dumps({
                "type": "webrtc_answer",
                "room_code": self.room_code,
                "sdp": self.pc.localDescription.sdp
            }))
            self.is_p2p = True
            logger.debug("P2P established!")
            if self._on_status:
                self._on_status("connected", f"⚡ WebRTC Direct P2P Connected (Room {self.room_code})")
        except Exception as e:
            logger.error(f"WebRTC offer error: {e}", exc_info=True)

    async def _handle_webrtc_ice(self, msg: dict):
        if not self.pc or not HAS_AIORTC:
            return
        try:
            cand_data = msg.get("candidate")
            if cand_data and isinstance(cand_data, dict):
                cand_str = cand_data.get("candidate", "")
                sdp_mid = cand_data.get("sdpMid")
                sdp_mline_index = cand_data.get("sdpMLineIndex")
                if cand_str:
                    from aiortc.sdp import candidate_from_sdp
                    c = candidate_from_sdp(cand_str)
                    c.sdpMid = sdp_mid
                    c.sdpMLineIndex = sdp_mline_index
                    await self.pc.addIceCandidate(c)
        except Exception:
            pass

    async def _consume_video_track(self, track):
        logger.debug(f"Starting to consume video track: {track.id}")
        while not self._stop_event.is_set():
            try:
                frame = await track.recv()
                # Offload YUV -> RGB conversion to avoid blocking the asyncio event loop
                img = await asyncio.to_thread(frame.to_image)
                
                self._record_bytes(frame.planes[0].buffer_size if frame.planes else 25000)
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
                logger.error(f"Error consuming video track: {e}", exc_info=True)
                break
        logger.debug("Video track consumption ended")


class EmbeddedRelayServer:
    """
    Runs the AxeCast Relay Server in a background thread inside AxeCast Studio.
    This allows the desktop app to act as its own relay (no external server needed).
    """
    
    def __init__(self, port: int = 9820, on_room_created: Optional[Callable[[str, str], None]] = None):
        self.port = port
        self.on_room_created = on_room_created
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
        
        server = RelayServer(host="0.0.0.0", port=self.port, on_room_created=self.on_room_created)
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


async def _async_check_room(server_url: str, room_code: str, pin: str = "", timeout: float = 6.0) -> tuple:
    """Connect to relay server and test if room exists, pin is needed, or open."""
    if not websockets:
        return False, "Missing 'websockets' package."

    url = normalize_relay_url(server_url)

    digits = "".join(c for c in str(room_code) if c.isdigit())
    code = f"{digits[:3]}-{digits[3:]}" if len(digits) == 6 else str(room_code).strip()

    ssl_ctx = _get_ssl_context(url)

    async def _do_check(ctx):
        async with websockets.connect(url, ssl=ctx, open_timeout=timeout, close_timeout=2) as ws:
            join_msg = {
                "type": "join_room",
                "room_code": code,
                "pin": pin
            }
            await ws.send(json.dumps(join_msg))
            resp_raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
            resp = json.loads(resp_raw)
            msg_type = resp.get("type")
            if msg_type == "joined":
                return True, "CONNECTED"
            elif msg_type == "pin_required":
                return True, "PIN_REQUIRED"
            elif msg_type == "error":
                err_code = resp.get("error_code", "")
                if err_code == "INVALID_PIN":
                    return False, "INVALID_PIN"
                return False, resp.get("message", f"Room '{code}' not found or expired.")
            return True, "OK"

    try:
        try:
            return await _do_check(ssl_ctx)
        except Exception as e:
            if "CERTIFICATE_VERIFY_FAILED" in str(e) and url.startswith("wss://"):
                return await _do_check(ssl._create_unverified_context())
            raise e
    except asyncio.TimeoutError:
        return False, "Connection timed out."
    except ConnectionRefusedError:
        return False, f"Could not connect to {url}"
    except Exception as e:
        return False, str(e)


def check_room_availability(server_url: str, room_code: str, pin: str = "", timeout: float = 6.0) -> tuple:
    """Thread-safe synchronous check for room availability. Returns (success, status_code_or_message)."""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(_async_check_room(server_url, room_code, pin, timeout))
        loop.close()
        return result
    except Exception as e:
        return False, str(e)

