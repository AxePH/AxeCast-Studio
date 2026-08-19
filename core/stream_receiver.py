import os
import io
import time
import threading
import requests
from PIL import Image
from pathlib import Path

class StreamReceiver:
    """Robust MJPEG Stream receiver with pure Pillow/Image decoding (fast, cross-platform, zero OpenCV recursion issues)."""
    
    def __init__(self):
        self.is_streaming = False
        self.current_frame = None  # PIL.Image instance
        self.stream_thread = None
        self.recording = False
        self.record_frames = []
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
                            # Pure Pillow JPEG decoding (RGB mode)
                            img = Image.open(io.BytesIO(jpg_data)).convert("RGB")
                            
                            with self._lock:
                                self.current_frame = img
                                if self.recording:
                                    self.record_frames.append(img.copy())
                            
                            if on_frame:
                                on_frame(img)
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
                self.current_frame.save(save_path, "PNG")
                return True
        return False

    def start_recording(self, save_path: str, fps: int = 20) -> bool:
        with self._lock:
            if self.current_frame is None:
                return False
                
            Path(save_path).parent.mkdir(parents=True, exist_ok=True)
            self.record_frames = []
            self.recording = True
            self.record_start_time = time.time()
            self.record_file = save_path
            return True

    def stop_recording(self) -> str:
        with self._lock:
            self.recording = False
            saved = self.record_file
            frames = list(self.record_frames)
            self.record_frames.clear()
            self.record_file = ""
            
        if frames and saved:
            def _save_video():
                try:
                    # Save as animated GIF or sequence if needed
                    if saved.endswith(".gif"):
                        frames[0].save(saved, save_all=True, append_images=frames[1:], duration=50, loop=0)
                    else:
                        # If mp4, try imageio/ffmpeg if present or fallback to first frame snapshot
                        try:
                            import cv2
                            import numpy as np
                            w, h = frames[0].size
                            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
                            vw = cv2.VideoWriter(saved, fourcc, 20, (w, h))
                            for f in frames:
                                arr = np.array(f)
                                bgr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
                                vw.write(bgr)
                            vw.release()
                        except Exception:
                            # Fallback to GIF or save as images
                            gif_path = saved.rsplit(".", 1)[0] + ".gif"
                            frames[0].save(gif_path, save_all=True, append_images=frames[1:], duration=50, loop=0)
                except Exception:
                    pass
            threading.Thread(target=_save_video, daemon=True).start()
            
        return saved

    def get_record_duration(self) -> str:
        if self.recording:
            elapsed = int(time.time() - self.record_start_time)
            mins = elapsed // 60
            secs = elapsed % 60
            return f"{mins:02d}:{secs:02d}"
        return "00:00"
