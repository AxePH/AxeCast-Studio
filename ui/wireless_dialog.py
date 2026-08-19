import customtkinter as ctk

class WirelessDialog(ctk.CTkToplevel):
    def __init__(self, master, adb_mgr, on_connected=None):
        super().__init__(master)
        self.title("📶 Wireless Connection (Wi-Fi)")
        self.geometry("460x320")
        self.resizable(False, False)
        self.adb = adb_mgr
        self.on_connected = on_connected
        self.transient(master)
        self.grab_set()
        self._build_ui()

    def _build_ui(self):
        ctk.CTkLabel(self, text="📶 Connect Device over Wi-Fi", font=ctk.CTkFont(size=17, weight="bold")).pack(pady=(18, 4))
        ctk.CTkLabel(self, text="Enter device IP address (Must be on the same Wi-Fi network)", font=ctk.CTkFont(size=12), text_color=("#64748b", "#94a3b8")).pack(pady=(0, 16))
        
        input_frame = ctk.CTkFrame(self, fg_color="transparent")
        input_frame.pack(padx=24, fill="x", pady=4)
        
        ctk.CTkLabel(input_frame, text="IP Address: ", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=(0, 8))
        self.ip_entry = ctk.CTkEntry(input_frame, placeholder_text="192.168.1.xxx", width=260, height=36)
        self.ip_entry.pack(side="left", fill="x", expand=True)
        
        self.status_label = ctk.CTkLabel(self, text="", font=ctk.CTkFont(size=12))
        self.status_label.pack(pady=6)
        
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(pady=4, fill="x", padx=24)
        
        connect_btn = ctk.CTkButton(
            btn_frame,
            text="🚀 Connect",
            height=38,
            font=ctk.CTkFont(weight="bold"),
            fg_color=("#0284c7", "#0369a1"),
            command=self._on_connect
        )
        connect_btn.pack(fill="x", pady=4)
        
        help_label = ctk.CTkLabel(
            self,
            text="💡 Supports both AxeCast Stream App (port 8080) and Wireless ADB (port 5555)",
            font=ctk.CTkFont(size=11),
            text_color=("#64748b", "#94a3b8"),
            justify="center"
        )
        help_label.pack(pady=(8, 0))

    def _on_connect(self):
        target = self.ip_entry.get().strip()
        if not target:
            self.status_label.configure(text="⚠ Please enter device IP address", text_color="#ef4444")
            return
            
        target_ip = target.replace("http://", "").replace("https://", "").split("/")[0]
        
        self.status_label.configure(text="⏳ Connecting...", text_color="#38bdf8")
        self.update()
        
        if ":8080" in target_ip or ":" not in target_ip:
            ip_only = target_ip.split(":")[0]
            url = f"http://{ip_only}:8080/stream"
            try:
                import requests
                r = requests.get(url, timeout=2, stream=True)
                if r.status_code == 200:
                    from ui.stream_viewer import StreamViewer
                    from core.stream_receiver import StreamReceiver
                    receiver = StreamReceiver()
                    StreamViewer(
                        self.master,
                        stream_receiver=receiver,
                        stream_url=url,
                        device_name="Mobile (AxeCast App)"
                    )
                    self.status_label.configure(text="✅ Connected to AxeCast Stream successfully!", text_color="#22c55e")
                    self.after(800, self.destroy)
                    return
            except Exception:
                pass

        success, msg = self.adb.connect_wireless(target_ip)
        if success:
            self.status_label.configure(text=f"✅ {msg}", text_color="#22c55e")
            if self.on_connected:
                self.on_connected()
            self.after(1200, self.destroy)
        else:
            self.status_label.configure(text=f"❌ {msg}", text_color="#ef4444")
