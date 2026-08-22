#!/usr/bin/env python3
"""
AxeCast Signaling & Relay Server
Ultra-lightweight async WebSocket server for 6-digit room-based 1-to-Many screen + log broadcasting.
Can run standalone (python server/signaling_server.py) or embedded inside AxeCast Studio.
"""

import os
import sys
import json
import time
import random
import asyncio
import logging
import argparse
from typing import Dict, Set, Optional, Callable

# Configure logging to file
try:
    fh_server = logging.FileHandler("/tmp/axecast_signaling.log")
    fh_server.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    logging.basicConfig(level=logging.INFO, handlers=[logging.StreamHandler(), fh_server])
except Exception:
    logging.basicConfig(level=logging.INFO)

logger = logging.getLogger("axecast-relay")

try:
    import websockets
    from websockets.asyncio.server import serve as ws_serve
except ImportError:
    print("❌ Missing dependency: pip install websockets")
    sys.exit(1)


# ──────────────────────────────────────────────
# Room & Session Data Structures
# ──────────────────────────────────────────────

class RoomSession:
    """Represents a single room created by a mobile publisher."""
    
    def __init__(self, room_code: str, publisher_ws):
        self.room_code = room_code
        self.publisher_ws = publisher_ws
        self.subscribers: Set = set()
        self.created_at = time.time()
        self.publisher_info: dict = {}
        self.max_age_seconds = 1800  # 30 minutes auto-expire
        self.pin: str = f"{random.randint(1000, 9999)}"
        self.last_offer: Optional[str] = None
    
    @property
    def is_expired(self) -> bool:
        return (time.time() - self.created_at) > self.max_age_seconds
    
    @property
    def subscriber_count(self) -> int:
        return len(self.subscribers)


class RelayServer:
    """AxeCast WebSocket Signaling & Frame/Log Relay Server."""
    
    def __init__(self, host: str = "0.0.0.0", port: int = 9820, on_room_created: Optional[Callable[[str, str], None]] = None):
        self.host = host
        self.port = port
        self.on_room_created = on_room_created
        self.rooms: Dict[str, RoomSession] = {}
        self._cleanup_task: Optional[asyncio.Task] = None
    
    def generate_room_code(self) -> str:
        """Generate unique 6-digit room code (format: XXX-XXX)."""
        for _ in range(100):
            code = f"{random.randint(100, 999)}-{random.randint(100, 999)}"
            if code not in self.rooms:
                return code
        return f"{random.randint(100, 999)}-{random.randint(100, 999)}"
    
    async def handle_connection(self, websocket):
        """Main WebSocket connection handler - routes based on message type."""
        role = None
        room_code = None
        
        try:
            async for raw_msg in websocket:
                if isinstance(raw_msg, bytes):
                    # Direct binary video frame relay (ultra-fast, zero JSON parsing overhead)
                    if role == "publisher" and room_code:
                        await self._relay_to_subscribers(room_code, raw_msg)
                    continue

                try:
                    logger.info(f"[{role}] Room {room_code} | Msg: {str(raw_msg)[:150]}")
                    msg = json.loads(raw_msg)
                except json.JSONDecodeError:
                    continue
                
                msg_type = msg.get("type", "")
                
                # ── Publisher Messages ──
                if msg_type == "create_room":
                    role = "publisher"
                    room_code = await self._handle_create_room(websocket, msg)
                
                elif msg_type in ("frame", "log", "logs_batch", "packages_list", "active_app"):
                    if role == "publisher" and room_code:
                        await self._relay_to_subscribers(room_code, raw_msg)
                
                elif msg_type == "device_info":
                    if role == "publisher" and room_code and room_code in self.rooms:
                        self.rooms[room_code].publisher_info = msg.get("info", {})
                        await self._relay_to_subscribers(room_code, raw_msg)
                
                # ── Subscriber Messages ──
                elif msg_type == "join_room":
                    role = "subscriber"
                    room_code = await self._handle_join_room(websocket, msg)
                
                elif msg_type in ("touch", "key", "button", "request_offer", "shell_exec"):
                    if role == "subscriber" and room_code:
                        await self._relay_to_publisher(room_code, raw_msg)
                
                elif msg_type in ("shell_output", "shell_done"):
                    if role == "publisher" and room_code:
                        await self._relay_to_subscribers(room_code, raw_msg)

                # ── WebRTC Signaling Messages (Offer / Answer / ICE Candidates) ──
                elif msg_type in ("webrtc_offer", "webrtc_answer", "webrtc_ice"):
                    if role == "publisher" and room_code:
                        if msg_type == "webrtc_offer" and room_code in self.rooms:
                            self.rooms[room_code].last_offer = raw_msg
                        await self._relay_to_subscribers(room_code, raw_msg)
                    elif role == "subscriber" and room_code:
                        await self._relay_to_publisher(room_code, raw_msg)

                # ── Common Messages ──
                elif msg_type == "ping":
                    await websocket.send(json.dumps({"type": "pong", "ts": time.time()}))
                    
        except websockets.exceptions.ConnectionClosed:
            pass
        except Exception as e:
            logger.warning(f"Connection error: {e}")
        finally:
            await self._handle_disconnect(websocket, role, room_code)
    
    @staticmethod
    def normalize_code(code: str) -> str:
        """Strip hyphens, spaces and lowercase for fuzzy matching."""
        if not code:
            return ""
        return str(code).replace("-", "").replace(" ", "").strip().upper()

    async def _handle_create_room(self, websocket, msg) -> str:
        """Publisher requests a new room."""
        requested_code = msg.get("room_code", "").strip()
        if requested_code:
            norm = self.normalize_code(requested_code)
            room_code = f"{norm[:3]}-{norm[3:]}" if len(norm) == 6 else requested_code
        else:
            room_code = self.generate_room_code()
            
        pin = msg.get("pin")
        if pin is None:
            pin = f"{random.randint(1000, 9999)}"
        else:
            pin = str(pin).strip()
            
        room = RoomSession(room_code, websocket)
        room.pin = pin
        room.publisher_info = msg.get("device_info", {})
        self.rooms[room_code] = room
        
        logger.info(f"📱 Room created: {room_code} (PIN: {room.pin if room.pin else 'OFF / Open'})")
        
        if self.on_room_created:
            try:
                self.on_room_created(room_code, room.pin)
            except Exception as e:
                logger.warning(f"Error in on_room_created callback: {e}")

        await websocket.send(json.dumps({
            "type": "room_created",
            "room_code": room_code,
            "pin": room.pin
        }))
        return room_code
    
    def _find_room(self, code: str):
        """Find room by exact key or normalized 6 digits."""
        if not code:
            return None
        if code in self.rooms:
            return code, self.rooms[code]
        norm = self.normalize_code(code)
        for r_code, session in self.rooms.items():
            if self.normalize_code(r_code) == norm:
                return r_code, session
        return None

    async def _handle_join_room(self, websocket, msg) -> Optional[str]:
        """Subscriber joins an existing room by code."""
        raw_code = msg.get("room_code", "").strip()
        room_match = self._find_room(raw_code)
        
        if not room_match:
            await websocket.send(json.dumps({
                "type": "error",
                "message": f"Room '{raw_code}' not found or expired."
            }))
            return None
        
        room_code, room = room_match
        
        if room.is_expired:
            del self.rooms[room_code]
            await websocket.send(json.dumps({
                "type": "error",
                "message": "Room has expired. Ask the tester to create a new session."
            }))
            return None
        
        # Check PIN authentication if room has PIN configured
        req_pin = str(msg.get("pin", "")).strip()
        if room.pin:
            if not req_pin:
                await websocket.send(json.dumps({
                    "type": "pin_required",
                    "room_code": room_code,
                    "message": "This room is protected by a 4-digit PIN."
                }))
                return None
            elif req_pin != str(room.pin).strip():
                await websocket.send(json.dumps({
                    "type": "error",
                    "error_code": "INVALID_PIN",
                    "message": "Incorrect PIN. Please check the 4-digit PIN on the phone screen."
                }))
                return None
        
        room.subscribers.add(websocket)
        logger.info(f"💻 Subscriber joined room {room_code} (total: {room.subscriber_count})")
        
        await websocket.send(json.dumps({
            "type": "joined",
            "room_code": room_code,
            "device_info": room.publisher_info
        }))
        
        # If publisher already posted a WebRTC offer, forward it to this subscriber immediately
        if room.last_offer:
            try:
                await websocket.send(room.last_offer)
            except Exception:
                pass
        
        # Notify publisher that a new viewer joined
        try:
            await room.publisher_ws.send(json.dumps({
                "type": "viewer_joined",
                "count": room.subscriber_count
            }))
        except Exception:
            pass
        
        return room_code
    
    async def _relay_to_subscribers(self, room_code: str, raw_msg: str):
        """Fan-out: relay publisher message to all subscribers."""
        room = self.rooms.get(room_code)
        if not room or not room.subscribers:
            return
        
        dead = set()
        for sub_ws in room.subscribers:
            try:
                await sub_ws.send(raw_msg)
            except Exception:
                dead.add(sub_ws)
        
        room.subscribers -= dead
    
    async def _relay_to_publisher(self, room_code: str, raw_msg: str):
        """Relay subscriber input events back to publisher."""
        room = self.rooms.get(room_code)
        if not room:
            return
        try:
            await room.publisher_ws.send(raw_msg)
        except Exception:
            pass
    
    async def _handle_disconnect(self, websocket, role: Optional[str], room_code: Optional[str]):
        """Clean up when a connection closes."""
        if not room_code or room_code not in self.rooms:
            return
        
        room = self.rooms[room_code]
        
        if role == "publisher":
            # Publisher disconnected - notify all subscribers and close room
            for sub_ws in room.subscribers:
                try:
                    await sub_ws.send(json.dumps({
                        "type": "room_closed",
                        "message": "The remote device has disconnected."
                    }))
                except Exception:
                    pass
            del self.rooms[room_code]
            logger.info(f"📴 Room {room_code} closed (publisher disconnected)")
        
        elif role == "subscriber":
            room.subscribers.discard(websocket)
            logger.info(f"💻 Subscriber left room {room_code} (remaining: {room.subscriber_count})")
            try:
                await room.publisher_ws.send(json.dumps({
                    "type": "viewer_left",
                    "count": room.subscriber_count
                }))
            except Exception:
                pass
    
    async def _cleanup_expired_rooms(self):
        """Periodically clean up expired rooms."""
        while True:
            await asyncio.sleep(60)
            expired = [code for code, room in self.rooms.items() if room.is_expired]
            for code in expired:
                room = self.rooms.pop(code, None)
                if room:
                    for sub_ws in room.subscribers:
                        try:
                            await sub_ws.send(json.dumps({
                                "type": "room_closed",
                                "message": "Session expired."
                            }))
                        except Exception:
                            pass
                    logger.info(f"🗑 Expired room {code} cleaned up")
    
    async def start(self):
        """Start the relay server."""
        self._cleanup_task = asyncio.create_task(self._cleanup_expired_rooms())
        
        logger.info(f"🚀 AxeCast Relay Server running on ws://{self.host}:{self.port}")
        logger.info(f"   Rooms expire after 30 minutes of inactivity.")
        
        async with ws_serve(self.handle_connection, self.host, self.port, max_size=2**22):
            await asyncio.Future()  # Run forever


def run_server(host: str = "0.0.0.0", port: int = 9820):
    """Entry point to run the relay server."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S"
    )
    server = RelayServer(host=host, port=port)
    asyncio.run(server.start())


if __name__ == "__main__":
    env_port = int(os.environ.get("PORT", 9820))
    parser = argparse.ArgumentParser(description="AxeCast Signaling & Relay Server")
    parser.add_argument("--host", default="0.0.0.0", help="Bind address (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=env_port, help=f"Port (default: {env_port})")
    args = parser.parse_args()
    run_server(host=args.host, port=args.port)
