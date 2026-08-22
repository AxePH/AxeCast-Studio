"""
AxeCast Remote Room Dialog & PIN Verification
Modern popup modal with two tabs:
  - Tab 1: Join Remote Room (enter 6-digit code + PIN auth)
  - Tab 2: Host Server (start/stop embedded relay)
"""

import json
import socket
import threading
import tkinter as tk
from tkinter import messagebox
import customtkinter as ctk
from typing import Optional, Callable
from PIL import Image


class PinInputDialog(ctk.CTkToplevel):
    """Modern popup dialog for entering 4-digit room PIN."""
    
    def __init__(self, master, room_code: str, on_verify: Callable[[str, Callable[[bool, str], None]], None]):
        super().__init__(master)
        self.title("🔐 Room PIN Required")
        self.geometry("420x330")
        self.resizable(False, False)
        self.transient(master)
        
        self.room_code = room_code
        self.on_verify = on_verify
        
        self._build_ui()
        self.lift()
        self.focus_force()
        self.pin_entry.focus_set()

    def _build_ui(self):
        # Header
        header = ctk.CTkFrame(self, height=50, fg_color=("#0f172a", "#090d16"), corner_radius=0)
        header.pack(fill="x")
        
        ctk.CTkLabel(
            header,
            text="🔐 Protected Room Authentication",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color="#38bdf8"
        ).pack(side="left", padx=16, pady=12)
        
        # Body
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=20, pady=12)
        
        ctk.CTkLabel(
            body,
            text=f"Room {self.room_code} is protected by a PIN.",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(pady=(4, 2))
        
        ctk.CTkLabel(
            body,
            text="Please enter the 4-digit PIN displayed on your mobile screen:",
            font=ctk.CTkFont(size=12),
            text_color=("#64748b", "#94a3b8")
        ).pack(pady=(0, 12))
        
        # PIN Input row
        pin_frame = ctk.CTkFrame(body, fg_color="transparent")
        pin_frame.pack(pady=4)
        
        self.pin_entry = ctk.CTkEntry(
            pin_frame,
            placeholder_text="••••",
            width=140,
            height=44,
            font=ctk.CTkFont(size=24, weight="bold"),
            justify="center",
            border_color=("#0284c7", "#0ea5e9"),
            border_width=2
        )
        self.pin_entry.pack(side="left", padx=(0, 8))
        self.pin_entry.bind("<KeyRelease>", self._on_pin_key_release)
        self.pin_entry.bind("<Return>", lambda e: self._on_submit())
        
        paste_btn = ctk.CTkButton(
            pin_frame,
            text="📋 Paste",
            width=70,
            height=44,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=("#334155", "#1e293b"),
            hover_color=("#475569", "#334155"),
            command=self._paste_pin
        )
        paste_btn.pack(side="left")
        
        self._enable_clipboard_shortcuts(self.pin_entry)
        
        # Status Label
        self.status_label = ctk.CTkLabel(body, text="", font=ctk.CTkFont(size=12))
        self.status_label.pack(pady=6)
        
        # Buttons row
        btn_frame = ctk.CTkFrame(body, fg_color="transparent")
        btn_frame.pack(fill="x", pady=(4, 0))
        
        cancel_btn = ctk.CTkButton(
            btn_frame,
            text="Cancel",
            width=100,
            height=38,
            font=ctk.CTkFont(size=12),
            fg_color=("#475569", "#334155"),
            hover_color=("#64748b", "#475569"),
            command=self.destroy
        )
        cancel_btn.pack(side="left", padx=(0, 8))
        
        self.submit_btn = ctk.CTkButton(
            btn_frame,
            text="🚀 Verify & Join",
            height=38,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=("#0284c7", "#0369a1"),
            hover_color=("#0369a1", "#0284c7"),
            command=self._on_submit
        )
        self.submit_btn.pack(side="left", fill="x", expand=True)

    def _enable_clipboard_shortcuts(self, entry):
        """Cross-platform clipboard shortcuts (Mac Cmd+C/V/A, Win/Linux Ctrl+C/V/A)."""
        targets = [entry]
        if hasattr(entry, "_entry"):
            targets.append(entry._entry)

        def on_paste(event=None):
            self._paste_pin()
            return "break"

        def on_copy(event=None):
            try:
                text = entry.selection_get()
                self.clipboard_clear()
                self.clipboard_append(text)
            except Exception:
                pass
            return "break"

        def on_select_all(event=None):
            try:
                entry.select_range(0, "end")
                entry.icursor("end")
            except Exception:
                pass
            return "break"

        for target in targets:
            for key in ("<Command-v>", "<Command-V>", "<Control-v>", "<Control-V>", "<<Paste>>"):
                target.bind(key, on_paste)
            for key in ("<Command-c>", "<Command-C>", "<Control-c>", "<Control-C>", "<<Copy>>"):
                target.bind(key, on_copy)
            for key in ("<Command-a>", "<Command-A>", "<Control-a>", "<Control-A>"):
                target.bind(key, on_select_all)

    def _on_pin_key_release(self, event):
        if event.keysym in ("Delete", "Left", "Right", "Up", "Down", "Tab", "Return", "Escape", "Home", "End"):
            return
        current = self.pin_entry.get()
        digits = "".join(c for c in current if c.isdigit())[:4]
        if digits != current:
            self.pin_entry.delete(0, "end")
            self.pin_entry.insert(0, digits)
            self.pin_entry.icursor("end")

    def _paste_pin(self):
        try:
            text = self.clipboard_get().strip()
            digits = "".join(c for c in text if c.isdigit())[:4]
            if digits:
                self.pin_entry.delete(0, "end")
                self.pin_entry.insert(0, digits)
                self.pin_entry.icursor("end")
        except Exception:
            pass

    def _on_submit(self):
        pin = self.pin_entry.get().strip()
        if len(pin) < 4:
            self.status_label.configure(text="⚠ Please enter the full 4-digit PIN", text_color="#ef4444")
            return
        
        self.status_label.configure(text="⏳ Verifying PIN...", text_color="#38bdf8")
        self.submit_btn.configure(text="⏳ Verifying...", state="disabled")
        
        def handle_result(success: bool, msg: str):
            if not self.winfo_exists():
                return
            if success:
                self.status_label.configure(text="🟢 PIN verified! Entering room...", text_color="#22c55e")
                self.destroy()
            else:
                self.submit_btn.configure(text="🚀 Verify & Join", state="normal")
                self.status_label.configure(text=f"❌ {msg}", text_color="#ef4444")
        
        self.on_verify(pin, handle_result)


class RemoteRoomDialog(ctk.CTkToplevel):
    """Dialog for joining or hosting AxeCast Remote Sessions."""
    
    def __init__(self, master, on_join: Optional[Callable] = None):
        super().__init__(master)
        self.title("🌐 AxeCast Remote Room")
        self.geometry("540x500")
        self.resizable(False, False)
        self.transient(master)
        
        self.on_join = on_join
        self._embedded_server = None
        
        # Auto-start embedded relay server on port 9820 so local connections always succeed
        try:
            from core.remote_session_manager import get_or_start_embedded_server
            self._embedded_server = get_or_start_embedded_server(port=9820)
        except Exception:
            pass

        self._build_ui()
        self.lift()
        self.focus_force()
    
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
        
        # Instructions
        ctk.CTkLabel(
            tab,
            text="Enter the 6-Digit Room Code",
            font=ctk.CTkFont(size=16, weight="bold")
        ).pack(pady=(16, 4))
        
        ctk.CTkLabel(
            tab,
            text="Ask your friend to open AxeCast App on their phone\nand tap 'Start Share' to get the 6-digit code",
            font=ctk.CTkFont(size=12),
            text_color=("#64748b", "#94a3b8"),
            justify="center"
        ).pack(pady=(0, 14))
        
        # Room code input row with Paste button
        code_frame = ctk.CTkFrame(tab, fg_color="transparent")
        code_frame.pack(pady=4)
        
        self.code_entry = ctk.CTkEntry(
            code_frame,
            placeholder_text="XXX-XXX",
            width=210,
            height=48,
            font=ctk.CTkFont(size=24, weight="bold"),
            justify="center",
            border_color=("#0284c7", "#0ea5e9"),
            border_width=2
        )
        self.code_entry.pack(side="left", padx=(0, 8))
        self.code_entry.bind("<KeyRelease>", self._on_code_key_release)
        self.code_entry.bind("<Return>", lambda e: self._on_join_click())
        
        paste_code_btn = ctk.CTkButton(
            code_frame,
            text="📋 Paste",
            width=76,
            height=48,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=("#334155", "#1e293b"),
            hover_color=("#475569", "#334155"),
            command=self._paste_room_code
        )
        paste_code_btn.pack(side="left")
        
        # Server URL row with Paste Button
        server_frame = ctk.CTkFrame(tab, fg_color="transparent")
        server_frame.pack(fill="x", padx=24, pady=(12, 4))
        
        ctk.CTkLabel(
            server_frame,
            text="Server:",
            font=ctk.CTkFont(size=12, weight="bold")
        ).pack(side="left", padx=(0, 6))
        
        self.server_entry = ctk.CTkEntry(
            server_frame,
            placeholder_text="ws://<server-ip>:9820 or wss://<server-domain>",
            height=34,
            font=ctk.CTkFont(size=12)
        )
        self.server_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        
        last_srv = ""
        if hasattr(self.master, "settings") and isinstance(self.master.settings, dict):
            last_srv = self.master.settings.get("last_remote_server", "")
        if not last_srv:
            import os
            try:
                from dotenv import load_dotenv
                load_dotenv()
                env_url = os.getenv("AXECAST_SERVER_URL")
                if env_url:
                    last_srv = env_url
            except ImportError:
                pass
                
        if not last_srv:
            last_srv = f"ws://{self._get_local_ip()}:9820"
        self.server_entry.insert(0, last_srv)

        self._enable_clipboard_shortcuts(self.server_entry)
        self._enable_clipboard_shortcuts(self.code_entry)
        
        paste_btn = ctk.CTkButton(
            server_frame,
            text="📋 Paste",
            width=68,
            height=34,
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color=("#334155", "#1e293b"),
            hover_color=("#475569", "#334155"),
            command=self._paste_server_url
        )
        paste_btn.pack(side="right")
        
        # Status
        self.join_status = ctk.CTkLabel(
            tab,
            text="",
            font=ctk.CTkFont(size=12)
        )
        self.join_status.pack(pady=4)
        
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
        
        # Visual guide & Note
        guide_frame = ctk.CTkFrame(tab, fg_color=("#f0f9ff", "#0c1929"), corner_radius=8)
        guide_frame.pack(fill="x", padx=24, pady=(4, 0))
        
        ctk.CTkLabel(
            guide_frame,
            text="📱 Remote Room (Live Stream & Real-time Logs):\n"
                 "• 📺 Screen canvas is non-touch (all menus, navigation & log tools are active).\n"
                 "• 🔐 Enter the 6-digit code displayed on your phone, then enter PIN if prompted.\n"
                 "• 🖱️ For direct on-screen mouse/touch control, use 'Local Mirror' mode.",
            font=ctk.CTkFont(size=11),
            text_color=("#475569", "#94a3b8"),
            justify="left"
        ).pack(padx=12, pady=8)
    
    # ── Tab 2: Host Server ──
    def _build_host_tab(self):
        tab = self.tab_host
        
        ctk.CTkLabel(
            tab,
            text="Host an Embedded Relay Server",
            font=ctk.CTkFont(size=16, weight="bold")
        ).pack(pady=(16, 4))
        
        ctk.CTkLabel(
            tab,
            text="Allow mobile devices to connect directly to your PC\nover LAN or via your own IP.",
            font=ctk.CTkFont(size=12),
            text_color=("#64748b", "#94a3b8"),
            justify="center"
        ).pack(pady=(0, 16))
        
        # Port config
        port_frame = ctk.CTkFrame(tab, fg_color="transparent")
        port_frame.pack(pady=4)
        
        ctk.CTkLabel(port_frame, text="Port:", font=ctk.CTkFont(size=13)).pack(side="left", padx=8)
        
        self.port_entry = ctk.CTkEntry(port_frame, width=100, height=36, font=ctk.CTkFont(size=14))
        self.port_entry.insert(0, "9820")
        self.port_entry.pack(side="left")
        self._enable_clipboard_shortcuts(self.port_entry)
        
        # Status box
        self.host_status_frame = ctk.CTkFrame(tab, fg_color=("#f1f5f9", "#0f172a"), corner_radius=8)
        self.host_status_frame.pack(fill="x", padx=24, pady=16)
        
        self.host_status_icon = ctk.CTkLabel(
            self.host_status_frame,
            text="⚫ Server Stopped",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#64748b"
        )
        self.host_status_icon.pack(pady=(12, 4))
        
        # Get local IP
        local_ip = self._get_local_ip()
        
        self.host_url_label = ctk.CTkLabel(
            self.host_status_frame,
            text=f"Local IP: {local_ip}",
            font=ctk.CTkFont(size=12),
            text_color=("#64748b", "#64748b")
        )
        self.host_url_label.pack(pady=(0, 12))
        
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
        
        if not server:
            self.join_status.configure(text="⚠ Please enter Relay Server URL", text_color="#ef4444")
            self.server_entry.focus_set()
            return

        digits = "".join(c for c in code if c.isdigit())
        if len(digits) < 6:
            self.join_status.configure(text="⚠ Please enter a valid 6-digit room code", text_color="#ef4444")
            return

        # Save last used server to settings
        if hasattr(self.master, "settings") and isinstance(self.master.settings, dict):
            self.master.settings["last_remote_server"] = server
            if hasattr(self.master, "_on_settings_saved"):
                self.master._on_settings_saved(self.master.settings)
        
        # Auto-start embedded relay server if connecting locally
        if "localhost" in server or "127.0.0.1" in server or self._get_local_ip() in server:
            from core.remote_session_manager import get_or_start_embedded_server
            get_or_start_embedded_server()

        # Update UI to verifying state
        self.join_status.configure(text="⏳ Connecting and verifying room...", text_color="#38bdf8")
        self.join_btn.configure(text="⏳ Verifying...", state="disabled")
        
        def _verify_and_open():
            from core.remote_session_manager import check_room_availability
            success, msg = check_room_availability(server, code, pin="", timeout=7.0)
            
            def _on_result():
                if msg == "PIN_REQUIRED":
                    # Prompt for PIN
                    self.join_btn.configure(text="🚀 Connect to Room", state="normal")
                    self.join_status.configure(text="🔐 PIN Required. Please enter PIN...", text_color="#f59e0b")
                    
                    def on_pin_entered(entered_pin: str, done_cb: Callable[[bool, str], None]):
                        def _check_pin_thread():
                            ok, res_msg = check_room_availability(server, code, pin=entered_pin, timeout=7.0)
                            
                            def _on_pin_result():
                                if ok:
                                    done_cb(True, "Success")
                                    callback = self.on_join
                                    if callback:
                                        callback(server, code, entered_pin)
                                    self.destroy()
                                else:
                                    done_cb(False, "Incorrect PIN. Please check your phone screen.")
                            
                            self.after(0, _on_pin_result)
                            
                        threading.Thread(target=_check_pin_thread, daemon=True).start()
                    
                    PinInputDialog(self, room_code=code, on_verify=on_pin_entered)
                    
                elif success:
                    self.join_status.configure(text="🟢 Connected! Opening Viewer...", text_color="#22c55e")
                    callback = self.on_join
                    if callback:
                        callback(server, code, "")
                    self.destroy()
                else:
                    self.join_btn.configure(text="🚀 Connect to Room", state="normal")
                    self.join_status.configure(text=f"❌ {msg}", text_color="#ef4444")
                    try:
                        messagebox.showerror(
                            "Cannot Connect to Room",
                            f"Failed to connect to Room '{code}':\n\n{msg}\n\nPlease verify that the AxeCast app on your mobile is streaming."
                        )
                    except Exception:
                        pass
            
            self.after(0, _on_result)

        threading.Thread(target=_verify_and_open, daemon=True).start()
    
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

        def _on_auto_room_created(room_code: str, pin: str):
            def _open():
                try:
                    callback = self.on_join
                    self.destroy()
                    if callback:
                        callback(f"ws://localhost:{port}", room_code, pin)
                except Exception:
                    pass
            self.after(0, _open)

        self._embedded_server = EmbeddedRelayServer(port=port, on_room_created=_on_auto_room_created)
        url = self._embedded_server.start()
        
        local_ip = self._get_local_ip()
        
        self.host_status_icon.configure(text="🟢 Server Running (Listening for phones)", text_color="#22c55e")
        self.host_url_label.configure(
            text=f"ws://{local_ip}:{port}",
            text_color="#38bdf8"
        )
        self.host_btn.configure(
            text="⏹ Stop Server",
            fg_color=("#dc2626", "#b91c1c"),
            hover_color=("#b91c1c", "#991b1b")
        )
        
        self._update_host_qr(local_ip, port)
        
        self.join_status.configure(
            text=f"Host running at ws://{local_ip}:{port}",
            text_color="#22c55e"
        )
    
    def _stop_host(self):
        if self._embedded_server:
            self._embedded_server.stop()
            self._embedded_server = None
        
        local_ip = self._get_local_ip()
        try:
            port = int(self.port_entry.get().strip())
        except ValueError:
            port = 9820

        self.host_status_icon.configure(text="⚫ Server Stopped", text_color="#64748b")
        self.host_url_label.configure(
            text=f"Local IP: {local_ip}",
            text_color=("#64748b", "#64748b")
        )
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
        """Cross-platform clipboard shortcuts (Mac Cmd+C/V/A, Win/Linux Ctrl+C/V/A) and Right-Click Menu."""
        targets = [entry]
        if hasattr(entry, "_entry"):
            targets.append(entry._entry)

        def on_paste(event=None):
            try:
                text = self.clipboard_get().strip()
                if hasattr(self, "code_entry") and entry == self.code_entry:
                    digits = "".join(c for c in text if c.isdigit())[:6]
                    formatted = f"{digits[:3]}-{digits[3:]}" if len(digits) > 3 else digits
                    entry.delete(0, "end")
                    entry.insert(0, formatted)
                    entry.icursor("end")
                else:
                    try:
                        entry.delete("sel.first", "sel.last")
                    except Exception:
                        pass
                    entry.insert(entry.index("insert"), text)
                return "break"
            except Exception:
                pass
            return "break"

        def on_copy(event=None):
            try:
                text = entry.selection_get()
                self.clipboard_clear()
                self.clipboard_append(text)
                return "break"
            except Exception:
                pass
            return "break"

        def on_select_all(event=None):
            try:
                entry.select_range(0, "end")
                entry.icursor("end")
                return "break"
            except Exception:
                pass
            return "break"

        # Explicitly bind on both CTkEntry and inner Entry
        for target in targets:
            for key in ("<Command-v>", "<Command-V>", "<Control-v>", "<Control-V>", "<<Paste>>"):
                target.bind(key, on_paste)
            for key in ("<Command-c>", "<Command-C>", "<Control-c>", "<Control-C>", "<<Copy>>"):
                target.bind(key, on_copy)
            for key in ("<Command-a>", "<Command-A>", "<Control-a>", "<Control-A>"):
                target.bind(key, on_select_all)

        # Right-click context menu
        ctx_menu = tk.Menu(
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
        ctx_menu.add_command(label="📋 Paste (Cmd+V / Ctrl+V)", command=lambda: on_paste())
        ctx_menu.add_command(label="📋 Copy (Cmd+C / Ctrl+C)", command=lambda: on_copy())
        ctx_menu.add_command(label="📑 Select All (Cmd+A)", command=lambda: on_select_all())
        ctx_menu.add_separator()
        ctx_menu.add_command(label="🗑 Clear", command=lambda: entry.delete(0, "end"))

        def show_menu(event):
            try:
                ctx_menu.tk_popup(event.x_root, event.y_root)
            finally:
                ctx_menu.grab_release()

        for target in targets:
            for b in ("<Button-2>", "<Button-3>", "<Control-Button-1>"):
                target.bind(b, show_menu)

    def _on_code_key_release(self, event):
        """Auto-format digits cleanly on key release without blocking clipboard shortcuts."""
        if event.keysym in ("Delete", "Left", "Right", "Up", "Down", "Tab", "Return", "Escape", "Home", "End"):
            return
        
        current = self.code_entry.get()
        digits = "".join(c for c in current if c.isdigit())[:6]
        if len(digits) > 3:
            formatted = f"{digits[:3]}-{digits[3:]}"
        else:
            formatted = digits
            
        if formatted != current:
            self.code_entry.delete(0, "end")
            self.code_entry.insert(0, formatted)
            self.code_entry.icursor("end")

    def _paste_room_code(self):
        """Quick paste room code from clipboard."""
        try:
            text = self.clipboard_get().strip()
            digits = "".join(c for c in text if c.isdigit())[:6]
            if digits:
                formatted = f"{digits[:3]}-{digits[3:]}" if len(digits) > 3 else digits
                self.code_entry.delete(0, "end")
                self.code_entry.insert(0, formatted)
                self.code_entry.icursor("end")
        except Exception:
            pass

    def _paste_server_url(self):
        """Quick paste server URL from clipboard."""
        try:
            text = self.clipboard_get().strip()
            if text:
                self.server_entry.delete(0, "end")
                self.server_entry.insert(0, text)
        except Exception:
            pass
