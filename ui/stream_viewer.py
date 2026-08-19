import os
import time
import threading
import customtkinter as ctk
from PIL import Image
import cv2

class StreamViewer(ctk.CTkToplevel):
    """Live HD viewer window for No-Dev stream with screenshot and record buttons."""
    
    def __init__(self, master, stream_receiver, stream_url, device_name="Mobile", save_dir="captures"):
        super().__init__(master)
        self.title(f"AxeCast HD - {device_name}")
        self.geometry("460x860")
        self.minsize(360, 600)
        
        self.receiver = stream_receiver
        self.stream_url = stream_url
        self.device_name = device_name
        self.save_dir = save_dir
        self._is_alive = True
        self._last_rendered_frame = None
        
        self._build_ui()
        self._connect_stream()
        
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self):
        toolbar = ctk.CTkFrame(self, height=42, fg_color=("#0f172a", "#090d16"))
        toolbar.pack(fill="x", side="top")
        
        self.status_lbl = ctk.CTkLabel(toolbar, text="⏳ Connecting...", font=ctk.CTkFont(size=12), text_color="#38bdf8")
        self.status_lbl.pack(side="left", padx=12, pady=6)
        
        self.snap_btn = ctk.CTkButton(
            toolbar,
            text="📸 Screenshot",
            width=100,
            height=28,
            font=ctk.CTkFont(size=12),
            fg_color=("#2563eb", "#1d4ed8"),
            command=self._on_screenshot
        )
        self.snap_btn.pack(side="right", padx=4, pady=6)
        
        self.rec_btn = ctk.CTkButton(
            toolbar,
            text="🎥 Record",
            width=90,
            height=28,
            font=ctk.CTkFont(size=12),
            fg_color=("#dc2626", "#b91c1c"),
            command=self._on_toggle_record
        )
        self.rec_btn.pack(side="right", padx=4, pady=6)
        
        self.canvas_frame = ctk.CTkFrame(self, fg_color="black")
        self.canvas_frame.pack(fill="both", expand=True)
        
        self.video_label = ctk.CTkLabel(self.canvas_frame, text="", fg_color="black")
        self.video_label.pack(fill="both", expand=True)
        
        info_bar = ctk.CTkFrame(self, height=24, fg_color=("#e2e8f0", "#0f172a"))
        info_bar.pack(fill="x", side="bottom")
        
        self.info_lbl = ctk.CTkLabel(info_bar, text="Full HD Native Resolution", font=ctk.CTkFont(size=11), text_color=("#64748b", "#94a3b8"))
        self.info_lbl.pack(side="left", padx=10)

    def _connect_stream(self):
        self.receiver.start_stream(
            self.stream_url,
            on_frame=self._on_new_frame,
            on_error=self._on_stream_error
        )
        self._update_display()

    def _on_new_frame(self, frame):
        pass

    def _on_stream_error(self, msg):
        self.after(0, lambda: self.status_lbl.configure(text=f"❌ {msg}", text_color="#ef4444"))

    def _update_display(self):
        if not self._is_alive:
            return
            
        if self.receiver.current_frame is not None:
            frame = self.receiver.current_frame
            
            # Only process and resize if frame changed or window resized
            win_w = self.canvas_frame.winfo_width()
            win_h = self.canvas_frame.winfo_height()
            
            if win_w > 50 and win_h > 50:
                fh, fw = frame.shape[:2]
                scale = min(win_w / fw, win_h / fh)
                new_w = max(1, int(fw * scale))
                new_h = max(1, int(fh * scale))
                
                # High quality OpenCV resize for sharp text & graphics
                if scale < 1.0:
                    resized = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_AREA)
                else:
                    resized = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_LANCZOS4)
                    
                rgb_resized = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
                pil_img = Image.fromarray(rgb_resized)
                
                ctk_img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=(new_w, new_h))
                self.video_label.configure(image=ctk_img)
                self.video_label._image = ctk_img
                
                self.status_lbl.configure(text=f"🟢 Live Stream Connected ({fw}x{fh})", text_color="#22c55e")
                
            if self.receiver.recording:
                dur = self.receiver.get_record_duration()
                self.rec_btn.configure(text=f"⏹ {dur}", fg_color=("#ea580c", "#c2410c"))
                
        self.after(50, self._update_display)

    def _on_screenshot(self):
        os.makedirs(self.save_dir, exist_ok=True)
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        clean_name = "".join(c for c in self.device_name if c.isalnum() or c in " _-").strip()
        filename = f"SNAP_{clean_name}_{timestamp}.png"
        filepath = os.path.join(self.save_dir, filename)
        
        if self.receiver.take_screenshot(filepath):
            self.info_lbl.configure(text=f"📸 Saved Full HD: {filename}")
        else:
            self.info_lbl.configure(text="⚠ No frame available yet")

    def _on_toggle_record(self):
        if self.receiver.recording:
            saved = self.receiver.stop_recording()
            self.rec_btn.configure(text="🎥 Record", fg_color=("#dc2626", "#b91c1c"))
            if saved:
                self.info_lbl.configure(text=f"🎬 Saved: {os.path.basename(saved)}")
        else:
            os.makedirs(self.save_dir, exist_ok=True)
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            clean_name = "".join(c for c in self.device_name if c.isalnum() or c in " _-").strip()
            filename = f"REC_{clean_name}_{timestamp}.mp4"
            filepath = os.path.join(self.save_dir, filename)
            
            if self.receiver.start_recording(filepath):
                self.info_lbl.configure(text="🔴 Recording...")
            else:
                self.info_lbl.configure(text="⚠ No frame yet, wait for stream to connect")

    def _on_close(self):
        self._is_alive = False
        self.receiver.stop_stream()
        self.destroy()
