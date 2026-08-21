"""
AxeCast Remote Viewer
Dual-pane window showing:
  - Left: Live screen mirror with touch relay and navigation buttons
  - Right: Real-time log stream with search/filter
  - Top bar: Device telemetry badges (name, battery, FPS, latency)
"""

import os
import time
import threading
import customtkinter as ctk
from PIL import Image
from typing import Optional

from core.remote_session_manager import RemoteSessionManager, LogEntry


class RemoteViewer(ctk.CTkToplevel):
    """Dual-pane Remote Studio Viewer for screen mirroring and live log streaming."""
    
    def __init__(self, master, server_url: str, room_code: str, save_dir: str = "captures"):
        super().__init__(master)
        self.title(f"🌐 AxeCast Remote — Room {room_code}")
        self.geometry("1100x720")
        self.minsize(800, 500)
        
        self.server_url = server_url
        self.room_code = room_code
        self.save_dir = save_dir
        self._is_alive = True
        self._current_frame: Optional[Image.Image] = None
        self._frame_lock = threading.Lock()
        self._log_entries: list = []
        self._log_filter_level: str = "ALL"
        self._log_search: str = ""
        self._auto_scroll = True
        
        # Session manager
        self.session = RemoteSessionManager()
        
        self._build_ui()
        self._connect_session()
        
        self.protocol("WM_DELETE_WINDOW", self._on_close)
    
    def _build_ui(self):
        # ── Top Telemetry Bar ──
        self._build_top_bar()
        
        # ── Main Split ──
        self.main_pane = ctk.CTkFrame(self, fg_color="transparent")
        self.main_pane.pack(fill="both", expand=True, padx=8, pady=(4, 8))
        
        # Left pane: Screen viewer (~60%)
        self._build_screen_pane()
        
        # Right pane: Log viewer (~40%)
        self._build_log_pane()
    
    def _build_top_bar(self):
        bar = ctk.CTkFrame(self, height=44, fg_color=("#0f172a", "#090d16"), corner_radius=0)
        bar.pack(fill="x")
        
        # Left: Connection status
        self.conn_badge = ctk.CTkLabel(
            bar,
            text="⏳ Connecting...",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#f59e0b"
        )
        self.conn_badge.pack(side="left", padx=16, pady=8)
        
        # Right: Telemetry badges
        badges_frame = ctk.CTkFrame(bar, fg_color=("#1e293b", "#0f172a"), corner_radius=6)
        badges_frame.pack(side="right", padx=12, pady=6)
        
        self.device_badge = ctk.CTkLabel(
            badges_frame,
            text="📱 —",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#38bdf8"
        )
        self.device_badge.pack(side="left", padx=(8, 4))
        
        ctk.CTkLabel(badges_frame, text="|", font=ctk.CTkFont(size=10), text_color="#475569").pack(side="left")
        
        self.battery_badge = ctk.CTkLabel(
            badges_frame,
            text="🔋 —%",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#10b981"
        )
        self.battery_badge.pack(side="left", padx=4)
        
        ctk.CTkLabel(badges_frame, text="|", font=ctk.CTkFont(size=10), text_color="#475569").pack(side="left")
        
        self.fps_badge = ctk.CTkLabel(
            badges_frame,
            text="⚡ 0 FPS",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#a855f7"
        )
        self.fps_badge.pack(side="left", padx=4)
        
        ctk.CTkLabel(badges_frame, text="|", font=ctk.CTkFont(size=10), text_color="#475569").pack(side="left")
        
        self.latency_badge = ctk.CTkLabel(
            badges_frame,
            text="📡 — ms",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#f59e0b"
        )
        self.latency_badge.pack(side="left", padx=(4, 8))
    
    # ── Left Pane: Screen Viewer ──
    def _build_screen_pane(self):
        self.screen_frame = ctk.CTkFrame(self.main_pane, fg_color=("#1e293b", "#0f172a"), corner_radius=10)
        self.screen_frame.pack(side="left", fill="both", expand=True, padx=(0, 4))
        
        # Screen canvas
        self.canvas_frame = ctk.CTkFrame(self.screen_frame, fg_color="black", corner_radius=6)
        self.canvas_frame.pack(fill="both", expand=True, padx=6, pady=(6, 4))
        
        self.video_label = ctk.CTkLabel(self.canvas_frame, text="⏳ Waiting for remote screen...",
                                         font=ctk.CTkFont(size=14), text_color="#475569", fg_color="black")
        self.video_label.pack(fill="both", expand=True)
        
        # Bind mouse events for touch relay
        self.video_label.bind("<Button-1>", self._on_mouse_click)
        self.video_label.bind("<B1-Motion>", self._on_mouse_drag)
        self.video_label.bind("<ButtonRelease-1>", self._on_mouse_release)
        
        # Bottom toolbar: Navigation buttons + Screenshot/Record
        nav_bar = ctk.CTkFrame(self.screen_frame, height=40, fg_color="transparent")
        nav_bar.pack(fill="x", padx=6, pady=(0, 6))
        
        # Navigation buttons (left)
        nav_left = ctk.CTkFrame(nav_bar, fg_color="transparent")
        nav_left.pack(side="left")
        
        nav_buttons = [
            ("🔙", "back", "Back"),
            ("🏠", "home", "Home"),
            ("📑", "recents", "Recent Apps"),
            ("🔒", "power", "Power"),
            ("🔄", "rotate", "Rotate"),
        ]
        
        for emoji, action, tooltip in nav_buttons:
            btn = ctk.CTkButton(
                nav_left,
                text=emoji,
                width=36,
                height=30,
                font=ctk.CTkFont(size=14),
                fg_color=("#334155", "#1e293b"),
                hover_color=("#475569", "#334155"),
                command=lambda a=action: self.session.send_button(a)
            )
            btn.pack(side="left", padx=2)
        
        # Action buttons (right)
        action_right = ctk.CTkFrame(nav_bar, fg_color="transparent")
        action_right.pack(side="right")
        
        self.snap_btn = ctk.CTkButton(
            action_right,
            text="📸 Screenshot",
            width=100,
            height=30,
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color=("#2563eb", "#1d4ed8"),
            command=self._on_screenshot
        )
        self.snap_btn.pack(side="left", padx=2)
    
    # ── Right Pane: Log Viewer ──
    def _build_log_pane(self):
        self.log_frame = ctk.CTkFrame(self.main_pane, width=380, fg_color=("#1e293b", "#0f172a"), corner_radius=10)
        self.log_frame.pack(side="right", fill="both", padx=(4, 0))
        self.log_frame.pack_propagate(False)
        
        # Log header
        log_header = ctk.CTkFrame(self.log_frame, height=36, fg_color="transparent")
        log_header.pack(fill="x", padx=8, pady=(8, 4))
        
        ctk.CTkLabel(
            log_header,
            text="📜 Live Logs",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#38bdf8"
        ).pack(side="left")
        
        self.log_count_label = ctk.CTkLabel(
            log_header,
            text="0",
            font=ctk.CTkFont(size=11),
            text_color="#94a3b8"
        )
        self.log_count_label.pack(side="right")
        
        # Search bar
        search_frame = ctk.CTkFrame(self.log_frame, fg_color="transparent")
        search_frame.pack(fill="x", padx=8, pady=(0, 4))
        
        self.log_search_entry = ctk.CTkEntry(
            search_frame,
            placeholder_text="🔍 Search logs...",
            height=30,
            font=ctk.CTkFont(size=11)
        )
        self.log_search_entry.pack(side="left", fill="x", expand=True, padx=(0, 4))
        self.log_search_entry.bind("<KeyRelease>", self._on_log_search)
        
        clear_btn = ctk.CTkButton(
            search_frame,
            text="🗑",
            width=32,
            height=30,
            font=ctk.CTkFont(size=12),
            fg_color=("#475569", "#334155"),
            command=self._clear_logs
        )
        clear_btn.pack(side="right")
        
        # Log level filter badges
        filter_frame = ctk.CTkFrame(self.log_frame, fg_color="transparent")
        filter_frame.pack(fill="x", padx=8, pady=(0, 4))
        
        self._filter_btns = {}
        levels = [
            ("ALL", "#94a3b8"),
            ("E", "#ef4444"),
            ("W", "#f59e0b"),
            ("I", "#10b981"),
            ("D", "#38bdf8"),
        ]
        
        for level, color in levels:
            btn = ctk.CTkButton(
                filter_frame,
                text=level,
                width=40,
                height=24,
                font=ctk.CTkFont(size=10, weight="bold"),
                fg_color=color if level == "ALL" else ("#334155", "#1e293b"),
                text_color="white",
                hover_color=color,
                command=lambda l=level, c=color: self._set_log_filter(l, c)
            )
            btn.pack(side="left", padx=2)
            self._filter_btns[level] = (btn, color)
        
        # Log text area
        self.log_textbox = ctk.CTkTextbox(
            self.log_frame,
            font=ctk.CTkFont(family="Menlo, Consolas, monospace", size=11),
            fg_color=("#0f172a", "#050a14"),
            text_color="#e2e8f0",
            corner_radius=6,
            wrap="word"
        )
        self.log_textbox.pack(fill="both", expand=True, padx=8, pady=(0, 4))
        self.log_textbox.configure(state="disabled")
        
        # Configure color tags
        self.log_textbox.tag_config("V", foreground="#94a3b8")
        self.log_textbox.tag_config("D", foreground="#38bdf8")
        self.log_textbox.tag_config("I", foreground="#10b981")
        self.log_textbox.tag_config("W", foreground="#f59e0b")
        self.log_textbox.tag_config("E", foreground="#ef4444")
        self.log_textbox.tag_config("F", foreground="#dc2626")
        
        # Bottom: Export + Auto-scroll toggle
        log_bottom = ctk.CTkFrame(self.log_frame, height=32, fg_color="transparent")
        log_bottom.pack(fill="x", padx=8, pady=(0, 6))
        
        self.autoscroll_var = ctk.BooleanVar(value=True)
        self.autoscroll_cb = ctk.CTkCheckBox(
            log_bottom,
            text="Auto-scroll",
            variable=self.autoscroll_var,
            font=ctk.CTkFont(size=11),
            height=24,
            checkbox_width=18,
            checkbox_height=18
        )
        self.autoscroll_cb.pack(side="left")
        
        export_btn = ctk.CTkButton(
            log_bottom,
            text="💾 Export Logs",
            width=90,
            height=26,
            font=ctk.CTkFont(size=11),
            fg_color=("#475569", "#334155"),
            command=self._export_logs
        )
        export_btn.pack(side="right")
    
    # ── Session Connection ──
    def _connect_session(self):
        self.session.connect(
            server_url=self.server_url,
            room_code=self.room_code,
            on_frame=self._on_frame,
            on_log=self._on_log,
            on_status=self._on_status,
            on_device_info=self._on_device_info
        )
        self._update_display_loop()
        self._update_stats_loop()
    
    def _on_frame(self, img: Image.Image):
        with self._frame_lock:
            self._current_frame = img
    
    def _on_log(self, entry: LogEntry):
        self._log_entries.append(entry)
        self.after(0, lambda: self._append_log_ui(entry))
    
    def _on_status(self, status: str, message: str):
        def _update():
            if status == "connected":
                self.conn_badge.configure(text=f"🟢 {message}", text_color="#22c55e")
            elif status == "connecting":
                self.conn_badge.configure(text=f"⏳ {message}", text_color="#f59e0b")
            elif status == "error":
                self.conn_badge.configure(text=f"❌ {message}", text_color="#ef4444")
            elif status == "closed" or status == "disconnected":
                self.conn_badge.configure(text=f"⚫ {message}", text_color="#94a3b8")
        self.after(0, _update)
    
    def _on_device_info(self, info: dict):
        def _update():
            name = info.get("model", info.get("name", "Unknown"))
            ver = info.get("version", "v1.0.2")
            battery = info.get("battery", "—")
            self.device_badge.configure(text=f"📱 {name} ({ver})")
            self.battery_badge.configure(text=f"🔋 {battery}%")
            self.title(f"🌐 AxeCast Remote — {name} {ver} ({self.room_code})")
        self.after(0, _update)
    
    # ── Display Loop ──
    def _update_display_loop(self):
        if not self._is_alive:
            return
        
        with self._frame_lock:
            frame = self._current_frame
        
        if frame is not None:
            win_w = self.canvas_frame.winfo_width()
            win_h = self.canvas_frame.winfo_height()
            
            if win_w > 50 and win_h > 50:
                fw, fh = frame.size
                scale = min(win_w / fw, win_h / fh)
                new_w = max(1, int(fw * scale))
                new_h = max(1, int(fh * scale))
                
                resized = frame.resize((new_w, new_h), Image.Resampling.BILINEAR)
                ctk_img = ctk.CTkImage(light_image=resized, dark_image=resized, size=(new_w, new_h))
                self.video_label.configure(image=ctk_img, text="")
                self.video_label._image = ctk_img
        
        self.after(33, self._update_display_loop)  # ~30 FPS UI refresh
    
    def _update_stats_loop(self):
        if not self._is_alive:
            return
        
        fps = self.session.fps
        latency = self.session.latency_ms
        
        self.fps_badge.configure(text=f"⚡ {fps:.0f} FPS")
        self.latency_badge.configure(text=f"📡 {latency:.0f} ms")
        self.log_count_label.configure(text=f"{len(self._log_entries)} lines")
        
        self.after(1000, self._update_stats_loop)
    
    # ── Touch Relay ──
    def _on_mouse_click(self, event):
        self._send_touch(event, "down")
    
    def _on_mouse_drag(self, event):
        self._send_touch(event, "move")
    
    def _on_mouse_release(self, event):
        self._send_touch(event, "up")
    
    def _send_touch(self, event, action: str):
        if not self.session.connected or self._current_frame is None:
            return
        
        label_w = self.video_label.winfo_width()
        label_h = self.video_label.winfo_height()
        
        if label_w < 10 or label_h < 10:
            return
        
        self.session.send_touch(
            x=event.x,
            y=event.y,
            action=action,
            source_width=label_w,
            source_height=label_h
        )
    
    # ── Log UI ──
    def _append_log_ui(self, entry: LogEntry):
        # Apply filter
        if self._log_filter_level != "ALL" and entry.level != self._log_filter_level:
            return
        
        if self._log_search and self._log_search.lower() not in entry.display_text.lower():
            return
        
        self.log_textbox.configure(state="normal")
        tag = entry.level if entry.level in ("V", "D", "I", "W", "E", "F") else "I"
        self.log_textbox.insert("end", entry.display_text + "\n", tag)
        
        # Limit to last 2000 lines to keep memory low
        line_count = int(self.log_textbox.index("end-1c").split(".")[0])
        if line_count > 2000:
            self.log_textbox.delete("1.0", "500.0")
        
        if self.autoscroll_var.get():
            self.log_textbox.see("end")
        
        self.log_textbox.configure(state="disabled")
    
    def _set_log_filter(self, level: str, color: str):
        self._log_filter_level = level
        
        # Update button styles
        for lv, (btn, c) in self._filter_btns.items():
            if lv == level:
                btn.configure(fg_color=c)
            else:
                btn.configure(fg_color=("#334155", "#1e293b"))
        
        # Re-render filtered logs
        self._rerender_logs()
    
    def _on_log_search(self, event=None):
        self._log_search = self.log_search_entry.get().strip()
        self._rerender_logs()
    
    def _rerender_logs(self):
        self.log_textbox.configure(state="normal")
        self.log_textbox.delete("1.0", "end")
        
        for entry in self._log_entries[-2000:]:
            if self._log_filter_level != "ALL" and entry.level != self._log_filter_level:
                continue
            if self._log_search and self._log_search.lower() not in entry.display_text.lower():
                continue
            tag = entry.level if entry.level in ("V", "D", "I", "W", "E", "F") else "I"
            self.log_textbox.insert("end", entry.display_text + "\n", tag)
        
        if self.autoscroll_var.get():
            self.log_textbox.see("end")
        
        self.log_textbox.configure(state="disabled")
    
    def _clear_logs(self):
        self._log_entries.clear()
        self.log_textbox.configure(state="normal")
        self.log_textbox.delete("1.0", "end")
        self.log_textbox.configure(state="disabled")
        self.log_count_label.configure(text="0 lines")
    
    def _export_logs(self):
        os.makedirs(self.save_dir, exist_ok=True)
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        filename = f"remote_logs_{self.room_code}_{timestamp}.txt"
        filepath = os.path.join(self.save_dir, filename)
        
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                for entry in self._log_entries:
                    f.write(entry.display_text + "\n")
            self.log_count_label.configure(text=f"💾 Saved: {filename}")
        except Exception as e:
            self.log_count_label.configure(text=f"❌ Export failed: {e}")
    
    # ── Screenshot ──
    def _on_screenshot(self):
        with self._frame_lock:
            frame = self._current_frame
        
        if frame is None:
            return
        
        os.makedirs(self.save_dir, exist_ok=True)
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        filename = f"REMOTE_{self.room_code}_{timestamp}.png"
        filepath = os.path.join(self.save_dir, filename)
        
        frame.save(filepath, "PNG")
        self.conn_badge.configure(text=f"📸 Saved: {filename}", text_color="#22c55e")
        self.after(3000, lambda: self.conn_badge.configure(
            text="🟢 Connected" if self.session.connected else "⚫ Disconnected",
            text_color="#22c55e" if self.session.connected else "#94a3b8"
        ))
    
    # ── Cleanup ──
    def _on_close(self):
        self._is_alive = False
        self.session.disconnect()
        self.destroy()
