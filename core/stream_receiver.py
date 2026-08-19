import os
import time
import threading
import requests
import numpy as np
import cv2
from PIL import Image
from pathlib import Path

class StreamReceiver:
    """Robust MJPEG Stream receiver with instant rendering."""
    
    def __init__(self):
        self.is_streaming = False
        self.current_frame = None
        self.stream_thread = None
        self.recording = False
        self.video_writer = None
        self.record_start_time = 0
        self.record_file = ""
        self._lock = threading.Lock()

    def start_stream(self, stream_url: str, on_frame=None, on_error=None):
        if not stream_url.startswith("http"):
            stream_url = "http://" + stream_url
            
        if not stream_url.endswith("/stream") and not stream_url.endswith("/video"):
            stream_url = stream_url.rstrip("/") + "/stream"
            
        self.is_streaming = True
        
        def receive_loop():
            try:
                # Connection timeout: 5s, Read timeout: None (Infinite streaming)
                session = requests.Session()
                response = session.get(stream_url, stream=True, timeout=(5, None))
                
                if response.status_code != 200:
                    if on_error:
                        on_error(f"HTTP Error {response.status_code}")
                    self.is_streaming = False
                    return
                    
                buf = b""
                for chunk in response.iter_content(chunk_size=8192):
                    if not self.is_streaming:
                        break
                        
                    if not chunk:
                        continue
                        
                    buf += chunk
                    
                    while True:
                        start = buf.find(b"\xff\xd8")
                        end = buf.find(b"\xff\xd9")
                        
                        if start == -1 or end == -1 or end <= start:
                            if len(buf) > 400000:
                                buf = buf[-100000:]
                            break
                            
                        jpg_data = buf[start:end + 2]
                        buf = buf[end + 2:]
                        
                        try:
                            frame = cv2.imdecode(
                                np.frombuffer(jpg_data, dtype=np.uint8),
                                cv2.IMREAD_COLOR
                            )
                            
                            if frame is not None:
                                with self._lock:
                                    self.current_frame = frame
                                    if self.recording and self.video_writer is not None:
                                        self.video_writer.write(frame)
                                
                                if on_frame:
                                    on_frame(frame)
                        except Exception:
                            pass
                                
            except Exception as e:
                if on_error and self.is_streaming:
                    on_error(f"Stream error: {str(e)}")
            finally:
                self.is_streaming = False
                
        self.stream_thread = threading.Thread(target=receive_loop, daemon=True)
        self.stream_thread.start()

    def stop_stream(self):
        self.is_streaming = False
        if self.recording:
            self.stop_recording()

    def take_screenshot(self, save_path: str) -> bool:
        with self._lock:
            if self.current_frame is not None:
                Path(save_path).parent.mkdir(parents=True, exist_ok=True)
                rgb_frame = cv2.cvtColor(self.current_frame, cv2.COLOR_BGR2RGB)
                img = Image.fromarray(rgb_frame)
                img.save(save_path, "PNG")
                return True
        return False

    def start_recording(self, save_path: str, fps: int = 20) -> bool:
        with self._lock:
            if self.current_frame is None:
                return False
                
            Path(save_path).parent.mkdir(parents=True, exist_ok=True)
            h, w = self.current_frame.shape[:2]
            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            self.video_writer = cv2.VideoWriter(save_path, fourcc, fps, (w, h))
            self.recording = True
            self.record_start_time = time.time()
            self.record_file = save_path
            return True

    def stop_recording(self) -> str:
        with self._lock:
            self.recording = False
            if self.video_writer is not None:
                self.video_writer.release()
                self.video_writer = None
            saved = self.record_file
            self.record_file = ""
            return saved

    def get_record_duration(self) -> str:
        if self.recording:
            elapsed = int(time.time() - self.record_start_time)
            mins = elapsed // 60
            secs = elapsed % 60
            return f"{mins:02d}:{secs:02d}"
        return "00:00"
