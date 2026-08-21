"""
AxeCast Remote Room Dialog
Modern popup modal with two tabs:
  - Tab 1: Join Remote Room (enter 6-digit code)
  - Tab 2: Host Server (start/stop embedded relay)
"""

import socket
import customtkinter as ctk
from typing import Optional, Callable


class RemoteRoomDialog(ctk.CTkToplevel):
    """Dialog for joining or hosting AxeCast Remote Sessions."""
    
    def __init__(self, master, on_join: Optional[Callable] = None):
        super().__init__(master)
        self.title("🌐 AxeCast Remote Room")
        self.geometry("520x480")
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()
        
        self.on_join = on_join
        self._embedded_server = None
        
        self._build_ui()
    
    def _build_ui(self):
        # Header
        header = ctk.CTkFrame(self, height=60, fg_color=("linear", "#0f172a"), corner_radius=0)
        header.pack(fill="x")
        
        ctk.CTkLabel(
            header,
            text="🌐 AxeCast Remote Room",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color="#38bdf8"
        ).pack(side="left", padx=20, pady=14)
        
        # Tab view
        self.tabview = ctk.CTkTabview(self, fg_color=("gray92", "#1e293b"))
        self.tabview.pack(fill="both", expand=True, padx=16, pady=(8, 16))
        
        self.tab_join = self.tabview.add("🔗 Join Room")
        self.tab_host = self.tabview.add("🖥 Host Server")
        
        self._build_join_tab()
        self._build_host_tab()
    
    # ── Tab 1: Join Room ──
    def _build_join_tab(self):
        tab = self.tab_join
        
        ctk.CTkLabel(
            tab,
            text="🔑 Enter Room Code",
            font=ctk.CTkFont(size=16, weight="bold")
        ).pack(pady=(16, 4))
        
        ctk.CTkLabel(
            tab,
            text="Ask your friend to open AxeCast App on their phone\nand tap 'Start Share' to get the 6-digit code",
            font=ctk.CTkFont(size=12),
            text_color=("#64748b", "#94a3b8"),
            justify="center"
        ).pack(pady=(0, 16))
        
        # Room code input
        code_frame = ctk.CTkFrame(tab, fg_color="transparent")
        code_frame.pack(pady=4)
        
        self.code_entry = ctk.CTkEntry(
            code_frame,
            placeholder_text="XXX-XXX",
            width=200,
            height=48,
            font=ctk.CTkFont(size=24, weight="bold"),
            justify="center",
            border_color=("#0284c7", "#0ea5e9"),
            border_width=2
        )
        self.code_entry.pack()
        self.code_entry.bind("<Return>", lambda e: self._on_join_click())
        
        # Server URL row with Preset & Paste Buttons
        server_frame = ctk.CTkFrame(tab, fg_color="transparent")
        server_frame.pack(fill="x", padx=24, pady=(10, 2))
        
        ctk.CTkLabel(
            server_frame,
            text="Server:",
            font=ctk.CTkFont(size=12, weight="bold")
        ).pack(side="left", padx=(0, 6))
        
        self.server_entry = ctk.CTkEntry(
            server_frame,
            placeholder_text="wss://axecast-relay.onrender.com",
            height=32,
            font=ctk.CTkFont(size=12)
        )
        self.server_entry.pack(side="left", fill="x", expand=True, padx=(0, 4))
        self.server_entry.insert(0, "wss://axecast-relay.onrender.com")
        self._enable_clipboard_shortcuts(self.server_entry)
        self._enable_clipboard_shortcuts(self.code_entry)
        
        paste_btn = ctk.CTkButton(
            server_frame,
            text="📋 Paste",
            width=64,
            height=32,
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color=("#334155", "#1e293b"),
            hover_color=("#475569", "#334155"),
            command=self._paste_server_url
        )
        paste_btn.pack(side="right")

        # Quick Server Presets Row
        presets_frame = ctk.CTkFrame(tab, fg_color="transparent")
        presets_frame.pack(fill="x", padx=24, pady=(2, 6))
        
        ctk.CTkLabel(
            presets_frame,
            text="Presets:",
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color="#64748b"
        ).pack(side="left", padx=(0, 4))

        cloud_btn = ctk.CTkButton(
            presets_frame,
            text="☁️ Render Cloud (Global)",
            height=22,
            font=ctk.CTkFont(size=10),
            fg_color=("#0369a1", "#0284c7"),
            hover_color=("#0284c7", "#38bdf8"),
            command=lambda: self._set_server_preset("wss://axecast-relay.onrender.com")
        )
        cloud_btn.pack(side="left", padx=2)

        local_btn = ctk.CTkButton(
            presets_frame,
            text="🏠 Local (LAN)",
            height=22,
            font=ctk.CTkFont(size=10),
            fg_color=("#334155", "#475569"),
            hover_color=("#475569", "#64748b"),
            command=lambda: self._set_server_preset("ws://localhost:9820")
        )
        local_btn.pack(side="left", padx=2)
        
        # Status
        self.join_status = ctk.CTkLabel(
            tab,
            text="",
            font=ctk.CTkFont(size=12)
        )
        self.join_status.pack(pady=6)
        
        # Connect button
        self.join_btn = ctk.CTkButton(
            tab,
            text="🚀 Connect to Room",
            height=42,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color=("#0284c7", "#0369a1"),
            hover_color=("#0369a1", "#075985"),
            command=self._on_join_click
        )
        self.join_btn.pack(fill="x", padx=24, pady=(4, 8))
        
        # Visual guide
        guide_frame = ctk.CTkFrame(tab, fg_color=("#f0f9ff", "#0c1929"), corner_radius=8)
        guide_frame.pack(fill="x", padx=24, pady=(4, 0))
        
        ctk.CTkLabel(
            guide_frame,
            text="📱 How your friend shares:\n"
                 "1️⃣  Open AxeCast App  →  2️⃣  Tap 'Start Share'\n"
                 "3️⃣  Tell you the 6-digit code  →  4️⃣  You enter it here!",
            font=ctk.CTkFont(size=11),
            text_color=("#475569", "#94a3b8"),
            justify="left"
        ).pack(padx=12, pady=8)
    
    # ── Tab 2: Host Server ──
    def _build_host_tab(self):
        tab = self.tab_host
        
        ctk.CTkLabel(
            tab,
            text="🖥 Embedded Relay Server",
            font=ctk.CTkFont(size=16, weight="bold")
        ).pack(pady=(16, 4))
        
        ctk.CTkLabel(
            tab,
            text="Start a relay server on this computer so your team\ncan connect without needing an external server",
            font=ctk.CTkFont(size=12),
            text_color=("#64748b", "#94a3b8"),
            justify="center"
        ).pack(pady=(0, 16))
        
        # Port config
        port_frame = ctk.CTkFrame(tab, fg_color="transparent")
        port_frame.pack(fill="x", padx=24, pady=4)
        
        ctk.CTkLabel(port_frame, text="Port:", font=ctk.CTkFont(size=12, weight="bold")).pack(side="left", padx=(0, 8))
        
        self.port_entry = ctk.CTkEntry(port_frame, width=100, height=32, font=ctk.CTkFont(size=12))
        self.port_entry.pack(side="left")
        self.port_entry.insert(0, "9820")
        
        # Server status
        self.host_status_frame = ctk.CTkFrame(tab, fg_color=("#f8fafc", "#0f172a"), corner_radius=8, border_width=1, border_color=("#e2e8f0", "#334155"))
        self.host_status_frame.pack(fill="x", padx=24, pady=12)
        
        self.host_status_icon = ctk.CTkLabel(
            self.host_status_frame,
            text="⚫ Server Offline",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=("#64748b", "#94a3b8")
        )
        self.host_status_icon.pack(pady=(10, 2))
        
        # Get local IP
        local_ip = self._get_local_ip()
        
        self.host_url_label = ctk.CTkLabel(
            self.host_status_frame,
            text=f"Local IP: {local_ip}",
            font=ctk.CTkFont(size=12),
            text_color=("#64748b", "#64748b")
        )
        self.host_url_label.pack(pady=(0, 10))
        
        # Start/Stop button
        self.host_btn = ctk.CTkButton(
            tab,
            text="▶ Start Server",
            height=42,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color=("#16a34a", "#15803d"),
            hover_color=("#15803d", "#166534"),
            command=self._toggle_host
        )
        self.host_btn.pack(fill="x", padx=24, pady=(0, 8))
        
        # Info
        info_frame = ctk.CTkFrame(tab, fg_color=("#fef3c7", "#3b1a03"), corner_radius=8)
        info_frame.pack(fill="x", padx=24, pady=(4, 0))
        
        ctk.CTkLabel(
            info_frame,
            text="💡 Once started, anyone on the same network can connect.\n"
                 "For internet access, set up port forwarding or use a VPS.",
            font=ctk.CTkFont(size=11),
            text_color=("#92400e", "#fde68a"),
            justify="left"
        ).pack(padx=12, pady=8)
    
    def _on_join_click(self):
        code = self.code_entry.get().strip()
        server = self.server_entry.get().strip()
        
        if not code:
            self.join_status.configure(text="⚠ Please enter a room code", text_color="#ef4444")
            return
        
        if not server:
            self.join_status.configure(text="⚠ Please enter a server URL", text_color="#ef4444")
            return
        
        # Auto-start embedded relay server if connecting locally
        if "localhost" in server or "127.0.0.1" in server or self._get_local_ip() in server:
            from core.remote_session_manager import get_or_start_embedded_server
            get_or_start_embedded_server()

        self.join_status.configure(text="⏳ Connecting...", text_color="#38bdf8")
        self.join_btn.configure(state="disabled")
        self.update()
        
        if self.on_join:
            self.on_join(server, code)
        
        self.join_status.configure(text="✅ Opening Remote Viewer...", text_color="#22c55e")
        self.after(600, self.destroy)
    
    def _toggle_host(self):
        if self._embedded_server and self._embedded_server.running:
            self._stop_host()
        else:
            self._start_host()
    
    def _start_host(self):
        try:
            port = int(self.port_entry.get().strip())
        except ValueError:
            port = 9820
        
        from core.remote_session_manager import EmbeddedRelayServer
        self._embedded_server = EmbeddedRelayServer(port=port)
        url = self._embedded_server.start()
        
        local_ip = self._get_local_ip()
        
        self.host_status_icon.configure(text="🟢 Server Running", text_color="#22c55e")
        self.host_url_label.configure(
            text=f"ws://{local_ip}:{port}",
            text_color="#38bdf8"
        )
        self.host_btn.configure(
            text="⏹ Stop Server",
            fg_color=("#dc2626", "#b91c1c"),
            hover_color=("#b91c1c", "#991b1b")
        )
        
        # Auto-fill the join tab server URL
        self.server_entry.delete(0, "end")
        self.server_entry.insert(0, f"ws://localhost:{port}")
    
    def _stop_host(self):
        if self._embedded_server:
            self._embedded_server.stop()
            self._embedded_server = None
        
        self.host_status_icon.configure(text="⚫ Server Offline", text_color=("#64748b", "#94a3b8"))
        self.host_url_label.configure(text=f"Local IP: {self._get_local_ip()}", text_color=("#64748b", "#64748b"))
        self.host_btn.configure(
            text="▶ Start Server",
            fg_color=("#16a34a", "#15803d"),
            hover_color=("#15803d", "#166534")
        )
    
    def _get_local_ip(self) -> str:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"
    
    def _enable_clipboard_shortcuts(self, entry):
        """Enable standard macOS/Windows Cmd+V, Cmd+C, Cmd+A clipboard shortcuts on Entry widget."""
        def on_paste(event=None):
            try:
                text = self.clipboard_get()
                if text:
                    try:
                        sel_start = entry.index("sel.first")
                        sel_end = entry.index("sel.last")
                        entry.delete(sel_start, sel_end)
                    except Exception:
                        pass
                    entry.insert(entry.index("insert"), text)
                return "break"
            except Exception:
                pass

        def on_copy(event=None):
            try:
                text = entry.selection_get()
                self.clipboard_clear()
                self.clipboard_append(text)
                return "break"
            except Exception:
                pass

        def on_select_all(event=None):
            try:
                entry.select_range(0, "end")
                entry.icursor("end")
                return "break"
            except Exception:
                pass

        entry.bind("<Command-v>", on_paste)
        entry.bind("<Command-V>", on_paste)
        entry.bind("<Control-v>", on_paste)
        entry.bind("<Control-V>", on_paste)
        entry.bind("<Command-c>", on_copy)
        entry.bind("<Command-C>", on_copy)
        entry.bind("<Control-c>", on_copy)
        entry.bind("<Control-C>", on_copy)
        entry.bind("<Command-a>", on_select_all)
        entry.bind("<Command-A>", on_select_all)
        entry.bind("<Control-a>", on_select_all)
        entry.bind("<Control-A>", on_select_all)

    def _paste_server_url(self):
        """Quick paste from clipboard button action."""
        try:
            text = self.clipboard_get().strip()
            if text:
                self.server_entry.delete(0, "end")
                self.server_entry.insert(0, text)
        except Exception:
            pass

    def _set_server_preset(self, url: str):
        """Quick preset button action."""
        self.server_entry.delete(0, "end")
        self.server_entry.insert(0, url)

    def destroy(self):
        # Don't stop the embedded server on dialog close - it should keep running
        super().destroy()
