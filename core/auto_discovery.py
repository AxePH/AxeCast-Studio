import socket
import json
import threading
import time

class NetworkDiscovery:
    """Listens for UDP beacons from AxeCast Stream APK for instant zero-config discovery."""
    
    def __init__(self, port=8089, on_device_found=None):
        self.port = port
        self.on_device_found = on_device_found
        self.discovered_devices = {}  # {ip: {"model": str, "port": int, "last_seen": float}}
        self.is_running = False
        self.socket = None
        self.thread = None

    def start(self):
        if self.is_running:
            return
        self.is_running = True
        
        def listen_loop():
            try:
                self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                self.socket.bind(("", self.port))
                self.socket.settimeout(2.0)
                
                while self.is_running:
                    try:
                        data, addr = self.socket.recvfrom(1024)
                        text = data.decode("utf-8", errors="ignore").strip()
                        
                        # Format: AXECAST_BEACON:<Model>:<Port> (or OMNICAST_BEACON)
                        if text.startswith("AXECAST_BEACON:") or text.startswith("OMNICAST_BEACON:"):
                            parts = text.split(":")
                            model = parts[1] if len(parts) > 1 else "Android Device"
                            port = int(parts[2]) if len(parts) > 2 else 8080
                            ip = addr[0]
                            
                            is_new = ip not in self.discovered_devices
                            self.discovered_devices[ip] = {
                                "model": model,
                                "port": port,
                                "ip": ip,
                                "url": f"http://{ip}:{port}/stream",
                                "last_seen": time.time()
                            }
                            
                            if is_new and self.on_device_found:
                                self.on_device_found(self.discovered_devices[ip])
                    except socket.timeout:
                        pass
                    except Exception:
                        pass
                        
                    # Clean up devices not seen for 8 seconds
                    now = time.time()
                    stale = [ip for ip, d in self.discovered_devices.items() if now - d["last_seen"] > 8]
                    for ip in stale:
                        del self.discovered_devices[ip]
                        
            except Exception as e:
                pass
            finally:
                if self.socket:
                    try: self.socket.close()
                    except: pass

        self.thread = threading.Thread(target=listen_loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.is_running = False
        if self.socket:
            try: self.socket.close()
            except: pass

    def get_devices(self):
        now = time.time()
        # Filter active in last 6 seconds
        return [d for d in self.discovered_devices.values() if now - d["last_seen"] < 6]
