import os
import time
import threading
import customtkinter as ctk
from PIL import Image

class DockedScreenCard(ctk.CTkFrame):
    """A live phone screen docked on the right-side multi-screen studio panel."""
    
    def __init__(self, master, serial: str, model_name: str, stream_url: str = "", receiver=None, on_pop_out=None, on_close=None, save_dir="captures", **kwargs):
        super().__init__(master, width=320, corner_radius=10, fg_color=("#0f172a", "#090d16"), border_width=1, border_color=("#334155", "#1e293b"), **kwargs)
        
        self.serial = serial
        self.model = model_name
        self.stream_url = stream_url
        self.receiver = receiver
        self.on_pop_out = on_pop_out
        self.on_close_cb = on_close
        self.save_dir = save_dir
        self._is_alive = True
        
        self._build_ui()
        if self.receiver and self.stream_url:
            self._start_stream()

    def _build_ui(self):
        # Top Header Bar
        hdr = ctk.CTkFrame(self, height=36, fg_color=("#1e293b", "#0f172a"), corner_radius=8)
        hdr.pack(fill="x", padx=4, pady=4)
        
        title_lbl = ctk.CTkLabel(
            hdr,
            text=f"📱 {self.model}",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#38bdf8"
        )
        title_lbl.pack(side="left", padx=8)
        
        close_btn = ctk.CTkButton(
            hdr, text="✕", width=26, height=24,
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color="transparent", text_color="#ef4444",
            hover_color=("#334155", "#1e293b"),
            command=self._on_close
        )
        close_btn.pack(side="right", padx=(2, 4))
        
        if self.on_pop_out:
            pop_btn = ctk.CTkButton(
                hdr, text="↗", width=26, height=24,
                font=ctk.CTkFont(size=12, weight="bold"),
                fg_color="transparent", text_color="#cbd5e1",
                hover_color=("#334155", "#1e293b"),
                command=lambda: self.on_pop_out(self.serial, self.model, self.stream_url)
            )
            pop_btn.pack(side="right", padx=2)

        # Video Display Canvas
        self.video_container = ctk.CTkFrame(self, height=520, fg_color="black", corner_radius=6)
        self.video_container.pack(fill="both", expand=True, padx=4, pady=2)
        self.video_container.pack_propagate(False)
        
        self.video_lbl = ctk.CTkLabel(self.video_container, text="Connecting...", font=ctk.CTkFont(size=11), text_color="#64748b")
        self.video_lbl.pack(fill="both", expand=True)

        # Bottom Quick Action Toolbar
        action_bar = ctk.CTkFrame(self, height=32, fg_color="transparent")
        action_bar.pack(fill="x", padx=4, pady=(2, 4))
        
        self.snap_btn = ctk.CTkButton(
            action_bar, text="📸 Snapshot", height=24, font=ctk.CTkFont(size=10),
            fg_color=("#2563eb", "#1d4ed8"),
            command=self._on_screenshot
        )
        self.snap_btn.pack(side="left", fill="x", expand=True, padx=2)
        
        self.rec_btn = ctk.CTkButton(
            action_bar, text="🎥 Record", height=24, font=ctk.CTkFont(size=10),
            fg_color=("#dc2626", "#b91c1c"),
            command=self._on_toggle_record
        )
        self.rec_btn.pack(side="left", fill="x", expand=True, padx=2)

    def _start_stream(self):
        self.receiver.start_stream(
            self.stream_url,
            on_frame=None,
            on_error=lambda msg: self.after(0, lambda: self.video_lbl.configure(text=f"⚠ {msg}"))
        )
        self._update_loop()

    def _update_loop(self):
        if not self._is_alive:
            return
            
        if self.receiver and self.receiver.current_frame is not None:
            frame = self.receiver.current_frame
            win_w = self.video_container.winfo_width()
            win_h = self.video_container.winfo_height()
            
            if win_w > 50 and win_h > 50:
                fw, fh = frame.size
                scale = min(win_w / fw, win_h / fh)
                new_w = max(1, int(fw * scale))
                new_h = max(1, int(fh * scale))
                
                resized = frame.resize((new_w, new_h), Image.Resampling.BILINEAR)
                ctk_img = ctk.CTkImage(light_image=resized, dark_image=resized, size=(new_w, new_h))
                self.video_lbl.configure(image=ctk_img, text="")
                self.video_lbl._image = ctk_img
                
            if self.receiver.recording:
                dur = self.receiver.get_record_duration()
                self.rec_btn.configure(text=f"⏹ {dur}", fg_color=("#ea580c", "#c2410c"))
                
        self.after(50, self._update_loop)

    def _on_screenshot(self):
        if not self.receiver:
            return
        os.makedirs(self.save_dir, exist_ok=True)
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        clean_name = "".join(c for c in self.model if c.isalnum() or c in " _-").strip()
        filename = f"SNAP_{clean_name}_{timestamp}.png"
        filepath = os.path.join(self.save_dir, filename)
        
        if self.receiver.take_screenshot(filepath):
            self.snap_btn.configure(text="✅ Saved!")
            self.after(1500, lambda: self.snap_btn.configure(text="📸 Snapshot"))

    def _on_toggle_record(self):
        if not self.receiver:
            return
        if self.receiver.recording:
            saved = self.receiver.stop_recording()
            self.rec_btn.configure(text="🎥 Record", fg_color=("#dc2626", "#b91c1c"))
        else:
            os.makedirs(self.save_dir, exist_ok=True)
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            clean_name = "".join(c for c in self.model if c.isalnum() or c in " _-").strip()
            filename = f"REC_{clean_name}_{timestamp}.mp4"
            filepath = os.path.join(self.save_dir, filename)
            self.receiver.start_recording(filepath)

    def _on_close(self):
        self._is_alive = False
        if self.receiver:
            self.receiver.stop_stream()
        if self.on_close_cb:
            self.on_close_cb(self.serial)
        self.destroy()
