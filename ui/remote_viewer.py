"""
AxeCast Remote Viewer
Dual-pane window showing:
  - Left: Live screen mirror with touch relay and navigation buttons
  - Right: Real-time log stream with search/filter
  - Top bar: Device telemetry badges (name, battery, FPS, latency)
"""

import os
import re
import time
import subprocess
import threading
import tkinter as tk
import customtkinter as ctk
from PIL import Image
from typing import Optional

from core.remote_session_manager import RemoteSessionManager, LogEntry


class RemoteViewer(ctk.CTkToplevel):
    """Dual-pane Remote Studio Viewer for screen mirroring and live log streaming."""
    
    def __init__(self, master, server_url: str, room_code: str, pin: str = "", save_dir: str = "captures"):
        super().__init__(master)
        self.title(f"🌐 AxeCast Remote — Room {room_code}")
        self.geometry("1180x750")
        self.minsize(850, 520)
        
        self.server_url = server_url
        self.room_code = room_code
        self.pin = str(pin).strip()
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
        self.deiconify()
        self.lift()
        self.focus_force()
        try:
            self.attributes("-topmost", True)
            self.after(200, lambda: self.attributes("-topmost", False) if self.winfo_exists() else None)
        except Exception:
            pass
    
    def _build_ui(self):
        # ── Top Telemetry Bar ──
        self._build_top_bar()
        
        # ── Main Split ──
        self.main_pane = ctk.CTkFrame(self, fg_color="transparent")
        self.main_pane.pack(fill="both", expand=True, padx=8, pady=(4, 8))
        
        # Right pane: Log viewer (initial width 480)
        self._build_log_pane()
        
        # Center draggable splitter
        self._build_splitter()
        
        # Left pane: Screen viewer (expands to fill remaining space)
        self._build_screen_pane()
    
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
        
        self.mode_badge = ctk.CTkLabel(
            badges_frame,
            text="🟢 P2P Direct",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#22c55e"
        )
        self.mode_badge.pack(side="left", padx=4)

        ctk.CTkLabel(badges_frame, text="|", font=ctk.CTkFont(size=10), text_color="#475569").pack(side="left")

        self.speed_badge = ctk.CTkLabel(
            badges_frame,
            text="🚀 0.00 Mbps",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#38bdf8"
        )
        self.speed_badge.pack(side="left", padx=4)

        ctk.CTkLabel(badges_frame, text="|", font=ctk.CTkFont(size=10), text_color="#475569").pack(side="left")
        
        self.fps_badge = ctk.CTkLabel(
            badges_frame,
            text="⚡ 0 FPS",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#a855f7"
        )
        self.fps_badge.pack(side="left", padx=4)
        
        ctk.CTkLabel(badges_frame, text="|", font=ctk.CTkFont(size=10), text_color="#475569").pack(side="left")

        # 1-Click ADB Connect button for Android Studio
        self.adb_btn = ctk.CTkButton(
            badges_frame,
            text="🔌 Connect ADB",
            width=110,
            height=26,
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color=("#334155", "#1e293b"),
            hover_color=("#0284c7", "#0369a1"),
            command=self._toggle_adb_bridge
        )
        self.adb_btn.pack(side="left", padx=(4, 4))
        
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
        
        # Bottom toolbar: Navigation buttons + Screenshot/Record + Note
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
                command=lambda a=action: self._on_nav_button(a)
            )
            btn.pack(side="left", padx=2)
            
        ctk.CTkLabel(
            nav_left,
            text="💡 Screen: Non-Touch",
            font=ctk.CTkFont(size=11),
            text_color="#64748b"
        ).pack(side="left", padx=8)
        
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
    
    def _on_nav_button(self, action: str):
        """Send navigation action over WebSocket, with ADB keyevent backup if available."""
        self.session.send_button(action)
        
        if hasattr(self.master, "adb") and self.master.adb:
            key_map = {
                "back": "KEYCODE_BACK",
                "home": "KEYCODE_HOME",
                "recents": "KEYCODE_APP_SWITCH",
                "power": "KEYCODE_POWER"
            }
            code = key_map.get(action)
            if code:
                for dev in getattr(self.master, "devices", []):
                    serial = dev.get("serial")
                    if serial and not dev.get("is_apk"):
                        self.master.adb.send_keyevent(serial, code)
                        break

    # ── Draggable Resizable Splitter ──
    def _build_splitter(self):
        self.splitter = ctk.CTkFrame(
            self.main_pane,
            width=8,
            fg_color=("#334155", "#1e293b"),
            corner_radius=4,
            cursor="sb_h_double_arrow"
        )
        self.splitter.pack(side="right", fill="y", padx=4)
        
        # Visual center grip bar
        grip = ctk.CTkFrame(self.splitter, width=2, height=36, fg_color=("#64748b", "#475569"), corner_radius=1)
        grip.place(relx=0.5, rely=0.5, anchor="center")
        
        self.splitter.bind("<B1-Motion>", self._on_splitter_drag)
        grip.bind("<B1-Motion>", self._on_splitter_drag)

    def _on_splitter_drag(self, event):
        try:
            pane_w = self.main_pane.winfo_width()
            pane_rootx = self.main_pane.winfo_rootx()
            mouse_x = event.x_root
            
            # Calculate right pane width (distance from right border to mouse)
            new_log_w = (pane_rootx + pane_w) - mouse_x
            new_log_w = max(240, min(new_log_w, pane_w - 280))
            
            self.log_frame.configure(width=new_log_w)
        except Exception:
            pass

    # ── Right Pane: Dual Mode (Live Logs & Remote Terminal) ──
    def _build_log_pane(self):
        self.log_frame = ctk.CTkFrame(self.main_pane, width=500, fg_color=("#1e293b", "#0f172a"), corner_radius=10)
        self.log_frame.pack(side="right", fill="both", padx=(0, 0))
        self.log_frame.pack_propagate(False)
        
        # Dual-tab switcher
        tab_bar = ctk.CTkFrame(self.log_frame, height=38, fg_color="transparent")
        tab_bar.pack(fill="x", padx=8, pady=(8, 4))
        
        self.right_tab_seg = ctk.CTkSegmentedButton(
            tab_bar,
            values=["📜 Live Logs", "💻 Remote Terminal"],
            height=30,
            font=ctk.CTkFont(size=12, weight="bold"),
            selected_color=("#0284c7", "#0369a1"),
            selected_hover_color=("#0369a1", "#0284c7"),
            command=self._on_right_tab_changed
        )
        self.right_tab_seg.set("📜 Live Logs")
        self.right_tab_seg.pack(side="left", fill="x", expand=True)

        # Subframes for tabs
        self.log_subframe = ctk.CTkFrame(self.log_frame, fg_color="transparent")
        self.term_subframe = ctk.CTkFrame(self.log_frame, fg_color="transparent")

        self._build_live_logs_view(self.log_subframe)
        self._build_terminal_view(self.term_subframe)

        # Show Live Logs by default
        self.log_subframe.pack(fill="both", expand=True)

    def _on_right_tab_changed(self, value: str):
        if value == "📜 Live Logs":
            self.term_subframe.pack_forget()
            self.log_subframe.pack(fill="both", expand=True)
        else:
            self.log_subframe.pack_forget()
            self.term_subframe.pack(fill="both", expand=True)
            self.after(50, lambda: self.term_entry.focus_set())

    def _build_live_logs_view(self, parent):
        # Log header
        log_header = ctk.CTkFrame(parent, height=32, fg_color="transparent")
        log_header.pack(fill="x", padx=8, pady=(2, 4))
        
        ctk.CTkLabel(
            log_header,
            text="Real-Time Logcat Stream",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#94a3b8"
        ).pack(side="left")
        
        self.log_count_label = ctk.CTkLabel(
            log_header,
            text="0 lines",
            font=ctk.CTkFont(size=11),
            text_color="#94a3b8"
        )
        self.log_count_label.pack(side="right")
        
        # Search bar & Clear
        search_frame = ctk.CTkFrame(parent, fg_color="transparent")
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
            text="🗑 Clear",
            width=60,
            height=30,
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color=("#dc2626", "#b91c1c"),
            hover_color=("#b91c1c", "#991b1b"),
            command=self._clear_logs
        )
        clear_btn.pack(side="right")
        
        # Package / App selector row
        pkg_frame = ctk.CTkFrame(parent, fg_color="transparent")
        pkg_frame.pack(fill="x", padx=8, pady=(0, 4))
        
        ctk.CTkLabel(pkg_frame, text="📦 App:", font=ctk.CTkFont(size=11, weight="bold"), text_color="#94a3b8").pack(side="left", padx=(0, 4))
        
        self._selected_package = "All Apps"
        self._active_package = ""
        self._discovered_packages = set()
        
        self.pkg_option = ctk.CTkOptionMenu(
            pkg_frame,
            values=["All Apps"],
            height=26,
            font=ctk.CTkFont(size=11),
            dropdown_font=ctk.CTkFont(size=11),
            fg_color=("#334155", "#1e293b"),
            button_color=("#475569", "#334155"),
            command=self._on_package_selected
        )
        self.pkg_option.pack(side="left", fill="x", expand=True, padx=(0, 4))
        
        self.active_app_btn = ctk.CTkButton(
            pkg_frame,
            text="⚡ Active App",
            width=78,
            height=26,
            font=ctk.CTkFont(size=10, weight="bold"),
            fg_color=("#0284c7", "#0369a1"),
            hover_color=("#0369a1", "#0284c7"),
            command=self._filter_active_app
        )
        self.active_app_btn.pack(side="right")
        
        # Log level filter badges
        filter_frame = ctk.CTkFrame(parent, fg_color="transparent")
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
            parent,
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
        log_bottom = ctk.CTkFrame(parent, height=32, fg_color="transparent")
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
        
        # Setup copy shortcuts & right click menu
        self._setup_log_interactions()

    def _build_terminal_view(self, parent):
        """Build interactive remote terminal & online debugging console."""
        self._term_history = []
        self._term_history_idx = 0

        # Quick actions / shortcuts toolbar
        tools_frame = ctk.CTkFrame(parent, fg_color="transparent")
        tools_frame.pack(fill="x", padx=8, pady=(2, 4))

        quick_cmds = [
            ("🔌 ADB Bridge", "__ADB_BRIDGE__"),
            ("🔋 Battery", "dumpsys battery"),
            ("📱 Specs", "getprop ro.product.model; getprop ro.build.version.release"),
            ("📦 Apps", "pm list packages -3"),
            ("💾 Disk", "df -h /data"),
            ("⚡ Focus", "dumpsys window | grep -E 'mCurrentFocus|mFocusedApp'"),
            ("🧹 Clear", "__CLEAR__")
        ]

        for label, cmd in quick_cmds:
            if cmd == "__CLEAR__":
                btn = ctk.CTkButton(
                    tools_frame,
                    text=label,
                    width=54,
                    height=24,
                    font=ctk.CTkFont(size=10, weight="bold"),
                    fg_color=("#dc2626", "#991b1b"),
                    hover_color=("#b91c1c", "#7f1d1d"),
                    command=self._clear_terminal
                )
            elif cmd == "__ADB_BRIDGE__":
                btn = ctk.CTkButton(
                    tools_frame,
                    text=label,
                    width=86,
                    height=24,
                    font=ctk.CTkFont(size=10, weight="bold"),
                    fg_color=("#0284c7", "#0369a1"),
                    hover_color=("#0369a1", "#0284c7"),
                    command=self._toggle_adb_bridge
                )
            else:
                btn = ctk.CTkButton(
                    tools_frame,
                    text=label,
                    width=68,
                    height=24,
                    font=ctk.CTkFont(size=10, weight="bold"),
                    fg_color=("#334155", "#1e293b"),
                    hover_color=("#475569", "#334155"),
                    command=lambda c=cmd: self._execute_terminal_command(cmd_override=c)
                )
            btn.pack(side="left", padx=2)

        # Terminal text area
        self.term_textbox = ctk.CTkTextbox(
            parent,
            font=ctk.CTkFont(family="Menlo, Consolas, monospace", size=11),
            fg_color=("#090d16", "#050811"),
            text_color="#e2e8f0",
            corner_radius=6,
            wrap="char"
        )
        self.term_textbox.pack(fill="both", expand=True, padx=8, pady=(0, 4))
        
        # Tags for styling terminal output
        self.term_textbox.tag_config("prompt", foreground="#38bdf8")
        self.term_textbox.tag_config("stdout", foreground="#f8fafc")
        self.term_textbox.tag_config("stderr", foreground="#f87171")
        self.term_textbox.tag_config("done_ok", foreground="#4ade80")
        self.term_textbox.tag_config("done_err", foreground="#ef4444")
        self.term_textbox.tag_config("info", foreground="#fbbf24")

        # Welcome banner
        self.term_textbox.insert("end", "╔════════════════════════════════════════════════════════════╗\n", "info")
        self.term_textbox.insert("end", "║  💻 AxeCast Remote Interactive Terminal & ADB Shell        ║\n", "info")
        self.term_textbox.insert("end", "║  P2P Direct Execution via WebRTC DataChannel               ║\n", "info")
        self.term_textbox.insert("end", "╚════════════════════════════════════════════════════════════╝\n\n", "info")
        self.term_textbox.configure(state="disabled")

        # Command input bar
        cmd_bar = ctk.CTkFrame(parent, height=36, fg_color="transparent")
        cmd_bar.pack(fill="x", padx=8, pady=(0, 4))

        prompt_lbl = ctk.CTkLabel(
            cmd_bar,
            text="shell:~$",
            font=ctk.CTkFont(family="Menlo, Consolas, monospace", size=11, weight="bold"),
            text_color="#38bdf8"
        )
        prompt_lbl.pack(side="left", padx=(0, 4))

        self.term_entry = ctk.CTkEntry(
            cmd_bar,
            placeholder_text="Enter shell / adb command (e.g. pm list packages)",
            height=32,
            font=ctk.CTkFont(family="Menlo, Consolas, monospace", size=11)
        )
        self.term_entry.pack(side="left", fill="x", expand=True, padx=(0, 4))
        self.term_entry.bind("<Return>", lambda e: self._execute_terminal_command())
        self.term_entry.bind("<Up>", self._on_term_history_up)
        self.term_entry.bind("<Down>", self._on_term_history_down)

        self.term_run_btn = ctk.CTkButton(
            cmd_bar,
            text="▶ Run",
            width=64,
            height=32,
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color=("#16a34a", "#15803d"),
            hover_color=("#15803d", "#166534"),
            command=self._execute_terminal_command
        )
        self.term_run_btn.pack(side="right")

        # Bottom options (Auto-scroll)
        term_bottom = ctk.CTkFrame(parent, height=24, fg_color="transparent")
        term_bottom.pack(fill="x", padx=8, pady=(0, 6))

        self.term_autoscroll_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            term_bottom,
            text="Auto-scroll",
            variable=self.term_autoscroll_var,
            font=ctk.CTkFont(size=10),
            height=20,
            checkbox_width=16,
            checkbox_height=16
        ).pack(side="left")

        ctk.CTkLabel(
            term_bottom,
            text="💡 Tip: Use Up/Down arrow keys for command history",
            font=ctk.CTkFont(size=10),
            text_color="#64748b"
        ).pack(side="right")

    def _clear_terminal(self):
        self.term_textbox.configure(state="normal")
        self.term_textbox.delete("1.0", "end")
        self.term_textbox.configure(state="disabled")

    def _execute_terminal_command(self, event=None, cmd_override=None):
        cmd = cmd_override if cmd_override is not None else self.term_entry.get().strip()
        if not cmd:
            return
        
        if cmd_override is None:
            self.term_entry.delete(0, "end")
            if not self._term_history or self._term_history[-1] != cmd:
                self._term_history.append(cmd)
            self._term_history_idx = len(self._term_history)
        
        if not self.session.connected:
            self._on_shell_output("sys", "❌ Not connected to remote device.", True)
            return

        self.term_textbox.configure(state="normal")
        self.term_textbox.insert("end", f"axecast@remote:~$ {cmd}\n", "prompt")
        self.term_textbox.see("end")
        self.term_textbox.configure(state="disabled")
        
        self.term_run_btn.configure(state="disabled", text="⏳ ...")
        self.session.send_shell_command(cmd)

    def _on_term_history_up(self, event):
        if self._term_history and self._term_history_idx > 0:
            self._term_history_idx -= 1
            self.term_entry.delete(0, "end")
            self.term_entry.insert(0, self._term_history[self._term_history_idx])
        return "break"

    def _on_term_history_down(self, event):
        if self._term_history and self._term_history_idx < len(self._term_history) - 1:
            self._term_history_idx += 1
            self.term_entry.delete(0, "end")
            self.term_entry.insert(0, self._term_history[self._term_history_idx])
        else:
            self._term_history_idx = len(self._term_history)
            self.term_entry.delete(0, "end")
        return "break"

    def _on_shell_output(self, cmd_id: str, text: str, is_err: bool):
        def _update():
            if not self._is_alive:
                return
            try:
                self.term_textbox.configure(state="normal")
                tag = "stderr" if is_err else "stdout"
                self.term_textbox.insert("end", text + "\n", tag)
                if self.term_autoscroll_var.get():
                    self.term_textbox.see("end")
                self.term_textbox.configure(state="disabled")
            except Exception:
                pass
        self.after(0, _update)

    def _on_shell_done(self, cmd_id: str, exit_code: int):
        def _update():
            if not self._is_alive:
                return
            try:
                self.term_textbox.configure(state="normal")
                code_tag = "done_ok" if exit_code == 0 else "done_err"
                self.term_textbox.insert("end", f"[Process exited with code {exit_code}]\n\n", code_tag)
                if self.term_autoscroll_var.get():
                    self.term_textbox.see("end")
                self.term_textbox.configure(state="disabled")
                self.term_run_btn.configure(state="normal", text="▶ Run")
            except Exception:
                pass
        self.after(0, _update)

    def _toggle_adb_bridge(self):
        """Toggle local TCP bridge for 1-click ADB connection in Android Studio."""
        if self.session.is_adb_bridge_running():
            self.session.stop_adb_bridge()
            self.adb_btn.configure(
                text="🔌 Connect ADB",
                fg_color=("#334155", "#1e293b"),
                hover_color=("#0284c7", "#0369a1")
            )
            self._on_shell_output("adb", "🔌 [Remote ADB Bridge Disconnected]", False)
            return

        self.adb_btn.configure(text="⏳ Linking...", state="disabled")
        ok, port, msg = self.session.start_adb_bridge(5555)
        if not ok:
            self.adb_btn.configure(text="❌ Failed", state="normal")
            self._on_shell_output("adb", f"❌ Failed to start ADB bridge: {msg}", True)
            return

        def _connect_worker():
            adb_bin = "adb"
            if hasattr(self.master, "adb") and self.master.adb and hasattr(self.master.adb, "adb_path"):
                adb_bin = self.master.adb.adb_path
            
            try:
                res = subprocess.run([adb_bin, "connect", f"127.0.0.1:{port}"], capture_output=True, text=True, timeout=2.5)
                out = (res.stdout.strip() or res.stderr.strip())
            except Exception as e:
                out = f"Connection timeout: {e}"

            is_connected = ("connected to" in out.lower() or "already connected" in out.lower()) and "cannot connect" not in out.lower() and "failed" not in out.lower()

            def _update_ui():
                if not self._is_alive or not self.winfo_exists():
                    return
                if is_connected:
                    self.adb_btn.configure(
                        state="normal",
                        text=f"🟢 ADB: {port}",
                        fg_color=("#16a34a", "#15803d"),
                        hover_color=("#15803d", "#166534")
                    )
                    self._on_shell_output(
                        "adb",
                        f"╔════════════════════════════════════════════════════════════╗\n"
                        f"║  🟢 Remote ADB Bridge is LIVE on 127.0.0.1:{port}             ║\n"
                        f"║  👉 Android Studio / VS Code can now Deploy & Debug!        ║\n"
                        f"║  Status: {out:<47}║\n"
                        f"╚════════════════════════════════════════════════════════════╝",
                        False
                    )
                else:
                    self.adb_btn.configure(
                        state="normal",
                        text=f"🟡 ADB: {port}",
                        fg_color=("#d97706", "#b45309"),
                        hover_color=("#b45309", "#92400e")
                    )
                    self._on_shell_output(
                        "adb",
                        f"⚠️ ADB Tunnel active on 127.0.0.1:{port}, but adbd is not responding.\n"
                        f"👉 Response: {out}\n"
                        f"💡 Note: Ensure 'Wireless Debugging' is enabled in Developer Options on your phone.",
                        True
                    )
            self.after(0, _update_ui)

        threading.Thread(target=_connect_worker, daemon=True).start()

    def _setup_log_interactions(self):
        """Cross-platform copy shortcuts and right-click context menu for log viewer."""
        raw_text = self.log_textbox._textbox
        
        def copy_selection(event=None):
            try:
                selected = raw_text.get("sel.first", "sel.last")
                if selected:
                    self.clipboard_clear()
                    self.clipboard_append(selected)
                    return "break"
            except Exception:
                pass
            return "break"

        def select_all(event=None):
            try:
                raw_text.tag_add("sel", "1.0", "end")
                return "break"
            except Exception:
                pass
            return "break"

        # Explicitly bind all copy and select all shortcut keys
        for key in ("<Command-c>", "<Command-C>", "<Control-c>", "<Control-C>", "<<Copy>>"):
            raw_text.bind(key, copy_selection)
            self.log_textbox.bind(key, copy_selection)
        for key in ("<Command-a>", "<Command-A>", "<Control-a>", "<Control-A>"):
            raw_text.bind(key, select_all)
            self.log_textbox.bind(key, select_all)
            
        # Modern Right-Click Popup Context Menu
        self.log_context_menu = tk.Menu(
            self,
            tearoff=0,
            bg="#1e293b",
            fg="#f8fafc",
            activebackground="#0284c7",
            activeforeground="#ffffff",
            bd=1,
            relief="solid",
            font=("Helvetica", 11)
        )
        self.log_context_menu.add_command(label="📋 Copy Selected (Cmd+C / Ctrl+C)", command=lambda: copy_selection())
        self.log_context_menu.add_command(label="📑 Select All (Cmd+A / Ctrl+A)", command=lambda: select_all())
        self.log_context_menu.add_separator()
        self.log_context_menu.add_command(label="💾 Export All Logs...", command=self._export_logs)
        self.log_context_menu.add_command(label="🗑 Clear All Logs", command=self._clear_logs)

        def show_context_menu(event):
            try:
                self.log_context_menu.tk_popup(event.x_root, event.y_root)
            finally:
                self.log_context_menu.grab_release()

        # Bind right click (Button-2 on Mac, Button-3 on Win/Linux, Control-Click on Mac)
        for b in ("<Button-2>", "<Button-3>", "<Control-Button-1>"):
            raw_text.bind(b, show_context_menu)
            self.log_textbox.bind(b, show_context_menu)
    
    # ── Session Connection ──
    def _connect_session(self):
        self.session.connect(
            server_url=self.server_url,
            room_code=self.room_code,
            pin=self.pin,
            on_frame=self._on_frame,
            on_log=self._on_log,
            on_status=self._on_status,
            on_device_info=self._on_device_info,
            on_packages=self._on_packages_list,
            on_active_app=self._on_active_app_detected,
            on_shell_output=self._on_shell_output,
            on_shell_done=self._on_shell_done
        )
        self._update_display_loop()
        self._update_stats_loop()
    
    def _schedule_pkg_update(self):
        now = time.time()
        if hasattr(self, "_last_pkg_ui_update") and now - self._last_pkg_ui_update < 2.0:
            return
        self._last_pkg_ui_update = now
        
        def _do_update():
            if not self._is_alive:
                return
            try:
                if not self.winfo_exists():
                    return
                vals = ["All Apps"] + sorted(list(self._discovered_packages))
                self.pkg_option.configure(values=vals)
            except Exception:
                pass
        self.after(500, _do_update)

    def _on_packages_list(self, pkgs: list):
        for p in pkgs:
            if p:
                self._discovered_packages.add(p)
        self._schedule_pkg_update()

    def _on_active_app_detected(self, pkg: str):
        def _update():
            if not self._is_alive:
                return
            try:
                if not self.winfo_exists():
                    return
                if pkg:
                    self._active_package = pkg
                    self._discovered_packages.add(pkg)
                    short_name = pkg.split(".")[-1]
                    self.active_app_btn.configure(text=f"⚡ {short_name}")
                    if self._selected_package == "Active App":
                        self._rerender_logs()
                self._schedule_pkg_update()
            except Exception:
                pass
        self.after(0, _update)

    def _on_log(self, entry: LogEntry):
        self._log_entries.append(entry)
        
        # Track discovered packages & active app
        if entry.package and entry.package not in self._discovered_packages:
            self._discovered_packages.add(entry.package)
            if not entry.package.startswith("com.android.systemui") and not entry.package.startswith("com.axecast.stream"):
                self._active_package = entry.package
            self._schedule_pkg_update()
        
        if entry.package and not entry.package.startswith("com.android.systemui") and not entry.package.startswith("com.axecast.stream"):
            self._active_package = entry.package

        self.after(0, lambda e=entry: self._append_log_ui(e))
    
    def _on_status(self, status: str, message: str):
        def _update():
            if not self._is_alive:
                return
            try:
                if status == "connected":
                    self.conn_badge.configure(text=f"🟢 {message}", text_color="#22c55e")
                elif status == "connecting":
                    self.conn_badge.configure(text=f"⏳ {message}", text_color="#f59e0b")
                elif status == "error":
                    self.conn_badge.configure(text=f"❌ {message}", text_color="#ef4444")
                elif status == "closed" or status == "disconnected":
                    self.conn_badge.configure(text=f"⚫ {message}", text_color="#94a3b8")
            except Exception:
                pass
        self.after(0, _update)
    
    def _on_device_info(self, info: dict):
        def _update():
            if not self._is_alive:
                return
            try:
                name = info.get("model", info.get("name", "Unknown"))
                ver = info.get("version", "v1.0.6")
                battery = info.get("battery", "—")
                self.device_badge.configure(text=f"📱 {name} ({ver})")
                if hasattr(self, "battery_badge"):
                    self.battery_badge.configure(text=f"🔋 {battery}%")
                self.title(f"🌐 AxeCast Remote — {name} {ver} ({self.room_code})")
            except Exception:
                pass
        self.after(0, _update)
    
    def _on_frame(self, img: Image.Image):
        with self._frame_lock:
            self._current_frame = img
            self._frame_seq = getattr(self, "_frame_seq", 0) + 1
    
    # ── Display Loop ──
    def _update_display_loop(self):
        if not self._is_alive:
            return
        
        try:
            if not self.winfo_exists():
                return
        except Exception:
            return

        win_w = self.canvas_frame.winfo_width()
        win_h = self.canvas_frame.winfo_height()
        last_dim = getattr(self, "_last_rendered_dim", (0, 0))
        dim_changed = (win_w, win_h) != last_dim and win_w > 50 and win_h > 50

        frame = None
        with self._frame_lock:
            cur_seq = getattr(self, "_frame_seq", 0)
            last_seq = getattr(self, "_last_rendered_seq", -1)
            if (cur_seq != last_seq or dim_changed) and self._current_frame is not None:
                frame = self._current_frame
                self._last_rendered_seq = cur_seq
        
        if frame is not None and win_w > 50 and win_h > 50:
            try:
                fw, fh = frame.size
                scale = min(win_w / fw, win_h / fh)
                new_w = max(1, int(fw * scale))
                new_h = max(1, int(fh * scale))
                
                # Fast & crisp scaling
                resized = frame.resize((new_w, new_h), Image.Resampling.BILINEAR if min(new_w, new_h) > 300 else Image.Resampling.NEAREST)
                ctk_img = ctk.CTkImage(light_image=resized, dark_image=resized, size=(new_w, new_h))
                self.video_label.configure(image=ctk_img, text="")
                self.video_label._image = ctk_img
                self._last_rendered_dim = (win_w, win_h)
            except Exception:
                pass
        
        self.after(16, self._update_display_loop)  # ~60 FPS UI refresh
    
    def _update_stats_loop(self):
        if not self._is_alive:
            return
        
        fps = self.session.fps
        latency = self.session.latency_ms
        speed_mbps = self.session.speed_mbps
        speed_kbps = self.session.speed_kbps
        is_p2p = self.session.is_p2p
        
        if is_p2p:
            self.mode_badge.configure(text="🟢 P2P Direct (WebRTC)", text_color="#22c55e")
        else:
            self.mode_badge.configure(text="🔵 Relay Mode", text_color="#38bdf8")
            
        if speed_mbps >= 1.0:
            self.speed_badge.configure(text=f"🚀 {speed_mbps:.2f} Mbps")
        else:
            self.speed_badge.configure(text=f"🚀 {speed_kbps:.0f} KB/s")

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
    def _on_package_selected(self, choice: str):
        self._selected_package = choice
        self._rerender_logs()

    def _filter_active_app(self):
        """Snap filter to the app currently running in foreground."""
        if hasattr(self.master, "adb") and self.master.adb:
            for dev in getattr(self.master, "devices", []):
                serial = dev.get("serial")
                if serial and not dev.get("is_apk"):
                    try:
                        res = subprocess.run([self.master.adb.adb_path, "-s", serial, "shell", "dumpsys", "window"], capture_output=True, text=True, timeout=2)
                        for line in res.stdout.splitlines():
                            if "mCurrentFocus" in line or "mFocusedApp" in line:
                                m = re.search(r"([a-zA-Z0-9_]+(?:\.[a-zA-Z0-9_]+)+)", line)
                                if m:
                                    found_pkg = m.group(1)
                                    if not found_pkg.startswith("com.android.systemui") and not found_pkg.startswith("com.axecast.stream"):
                                        self._active_package = found_pkg
                                        self._discovered_packages.add(found_pkg)
                                        break
                    except Exception:
                        pass
                    break

        if self._active_package:
            self._selected_package = self._active_package
            self.pkg_option.set(self._active_package)
            short_name = self._active_package.split(".")[-1]
            self.active_app_btn.configure(text=f"⚡ {short_name}")
        else:
            self._selected_package = "All Apps"
            self.pkg_option.set("All Apps")
        self._rerender_logs()

    def _append_log_ui(self, entry: LogEntry):
        if not self._is_alive:
            return
        try:
            if not self.winfo_exists():
                return
        except Exception:
            return

        # Level filter
        if self._log_filter_level != "ALL" and entry.level != self._log_filter_level:
            return
        
        # Package filter
        if self._selected_package != "All Apps":
            target = self._selected_package.lower()
            # Ignore OS window compositor spam
            if entry.tag in ("SurfaceFlinger", "Layer", "RenderThread", "libprocessgroup"):
                return

            pkg_match = bool(entry.package and (target in entry.package.lower() or entry.package.lower() in target))
            tag_match = bool(entry.tag and (target in entry.tag.lower() or entry.tag.lower() in target))
            
            # Meaningful token matching (e.g., "oishidrink", "oishiclub", "lite")
            meaningful_tokens = [t for t in target.split(".") if len(t) >= 3 and t not in ("com", "org", "net", "app", "android", "google", "sec")]
            token_match = any(
                token in (entry.package or "").lower() or 
                token in (entry.tag or "").lower() or 
                token in (entry.message or "").lower()
                for token in meaningful_tokens
            )
            
            # Framework tag matching (e.g. flutter, reactnative logs when package matches or is active)
            fw_tags = ("flutter", "dart", "reactnative", "reactnativejs", "unity", "chromium", "okhttp", "retrofit", "dio")
            fw_match = bool(entry.tag and entry.tag.lower() in fw_tags and (pkg_match or token_match or entry.package == self._selected_package))

            if not (pkg_match or tag_match or token_match or fw_match):
                return
        
        # Search text filter
        if self._log_search and self._log_search.lower() not in entry.display_text.lower():
            return
        
        try:
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
        except Exception:
            pass
    
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
        if not self._is_alive:
            return
        try:
            if not self.winfo_exists():
                return
        except Exception:
            return

        try:
            self.log_textbox.configure(state="normal")
            self.log_textbox.delete("1.0", "end")
            
            for entry in self._log_entries[-2000:]:
                # Level filter
                if self._log_filter_level != "ALL" and entry.level != self._log_filter_level:
                    continue
                # Package filter
                if self._selected_package != "All Apps":
                    target = self._selected_package.lower()
                    if entry.tag in ("SurfaceFlinger", "Layer", "RenderThread", "libprocessgroup"):
                        continue
                    pkg_match = bool(entry.package and (target in entry.package.lower() or entry.package.lower() in target))
                    tag_match = bool(entry.tag and (target in entry.tag.lower() or entry.tag.lower() in target))
                    meaningful_tokens = [t for t in target.split(".") if len(t) >= 3 and t not in ("com", "org", "net", "app", "android", "google", "sec")]
                    token_match = any(
                        token in (entry.package or "").lower() or 
                        token in (entry.tag or "").lower() or 
                        token in (entry.message or "").lower()
                        for token in meaningful_tokens
                    )
                    fw_tags = ("flutter", "dart", "reactnative", "reactnativejs", "unity", "chromium", "okhttp", "retrofit", "dio")
                    fw_match = bool(entry.tag and entry.tag.lower() in fw_tags and (pkg_match or token_match or entry.package == self._selected_package))
                    if not (pkg_match or tag_match or token_match or fw_match):
                        continue
                # Search filter
                if self._log_search and self._log_search.lower() not in entry.display_text.lower():
                    continue
                tag = entry.level if entry.level in ("V", "D", "I", "W", "E", "F") else "I"
                self.log_textbox.insert("end", entry.display_text + "\n", tag)
            
            if self.autoscroll_var.get():
                self.log_textbox.see("end")
            
            self.log_textbox.configure(state="disabled")
        except Exception:
            pass
    
    def _clear_logs(self):
        """Clears all logs in memory and from the UI display."""
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
