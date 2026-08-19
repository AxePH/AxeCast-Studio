import os
import socket
import threading
import http.server
import socketserver
from pathlib import Path
import qrcode
from PIL import Image

def get_local_ip():
    """Gets the computer local IP address on Wi-Fi/LAN."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AxeCast Light - Mobile Screen Share</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f172a; color: #f8fafc; display: flex; flex-direction: column; align-items: center; justify-content: center; min-height: 100vh; padding: 20px; text-align: center; }
        .card { background: #1e293b; border-radius: 16px; padding: 24px; max-width: 420px; width: 100%; box-shadow: 0 10px 25px -5px rgba(0,0,0,0.5); border: 1px solid #334155; }
        h1 { font-size: 22px; margin-bottom: 8px; color: #38bdf8; }
        p { font-size: 14px; color: #94a3b8; margin-bottom: 20px; line-height: 1.5; }
        .btn { background: #0284c7; color: white; border: none; padding: 14px 24px; font-size: 16px; font-weight: 600; border-radius: 10px; cursor: pointer; width: 100%; transition: all 0.2s; }
        .btn:hover { background: #0369a1; }
        .status { margin-top: 16px; font-size: 13px; color: #22c55e; }
        video { width: 100%; border-radius: 12px; margin-top: 16px; display: none; background: #000; }
    </style>
</head>
<body>
    <div class="card">
        <h1>📱 AxeCast Share</h1>
        <p>No-Developer Mode Screen Sharing<br>Click the button below to start streaming your screen to your PC</p>
        <button id="startBtn" class="btn" onclick="startSharing()">🚀 Start Screen Share</button>
        <div id="status" class="status"></div>
        <video id="preview" autoplay playsinline muted></video>
    </div>

    <script>
        async function startSharing() {
            try {
                const stream = await navigator.mediaDevices.getDisplayMedia({
                    video: { cursor: "always" },
                    audio: true
                });
                const video = document.getElementById('preview');
                video.srcObject = stream;
                video.style.display = 'block';
                document.getElementById('status').innerText = '🟢 Streaming screen to computer...';
                document.getElementById('startBtn').style.display = 'none';
            } catch (err) {
                alert('Unable to share screen: ' + err.message);
            }
        }
    </script>
</body>
</html>
"""

class NoDevStreamServer:
    """Lightweight HTTP server to receive/serve browser-based screen cast with QR code."""
    
    def __init__(self, port=8088):
        self.port = port
        self.ip = get_local_ip()
        self.server = None
        self.thread = None
        self.is_running = False

    def get_url(self):
        return f"http://{self.ip}:{self.port}"

    def generate_qr_code(self, save_path: str):
        """Generates QR code for mobile connection."""
        url = self.get_url()
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=8,
            border=2,
        )
        qr.add_data(url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="#0f172a", back_color="white")
        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        img.save(save_path)
        return save_path

    def start(self):
        if self.is_running:
            return
            
        class Handler(http.server.SimpleHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(HTML_TEMPLATE.encode("utf-8"))
                
            def log_message(self, format, *args):
                pass # Suppress console noise

        def serve():
            try:
                socketserver.TCPServer.allow_reuse_address = True
                with socketserver.TCPServer(("", self.port), Handler) as httpd:
                    self.server = httpd
                    self.is_running = True
                    httpd.serve_forever()
            except Exception as e:
                print(f"NoDev server error: {e}")

        self.thread = threading.Thread(target=serve, daemon=True)
        self.thread.start()
        self.is_running = True

    def stop(self):
        if self.server:
            try:
                self.server.shutdown()
                self.server.server_close()
            except Exception:
                pass
        self.is_running = False
