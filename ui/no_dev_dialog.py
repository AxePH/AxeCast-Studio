import os
import subprocess
import customtkinter as ctk
from core.stream_receiver import StreamReceiver

class NoDevDialog(ctk.CTkToplevel):
    """English No-Dev dialog with Companion APK installer & iOS guide."""
    
    def __init__(self, master, streamer=None, save_dir="captures"):
        super().__init__(master)
        self.title("📱 Wireless Screen Stream (No Dev Mode Required)")
        self.geometry("580x540")
        self.resizable(False, False)
        self.save_dir = save_dir
        self.transient(master)
        self.grab_set()
        self._build_ui()

    def _build_ui(self):
        tabview = ctk.CTkTabview(self, corner_radius=10)
        tabview.pack(padx=16, pady=12, fill="both", expand=True)
        
        t1 = tabview.add("⚡ AxeCast APK (Recommended)")
        self._build_apk_tab(t1)
        
        t2 = tabview.add("🍏 iOS (iPhone / iPad)")
        self._build_ios_tab(t2)

    def _build_apk_tab(self, parent):
        ctk.CTkLabel(parent, text="📲 Stream Screen via AxeCast APK v1.0.5", font=ctk.CTkFont(size=15, weight="bold")).pack(pady=(8, 4))
        
        guide = (
            "✨ Quick Steps (No Developer Mode Needed / Supports Android 5.0 - 16):\n"
            "1. Copy axecast_stream.apk to your phone and install it\n"
            "2. Open the app on your phone and tap 'START STREAMING'\n"
            "3. Your device will automatically appear on the main screen!\n"
            "4. Or enter the Stream URL below to connect directly:"
        )
        ctk.CTkLabel(parent, text=guide, font=ctk.CTkFont(size=12), justify="left", text_color=("#64748b", "#94a3b8")).pack(padx=16, pady=(2, 8))
        
        ctk.CTkButton(
            parent,
            text="📁 1. Open APK File Location (axecast_stream.apk)",
            height=34,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=("#0284c7", "#0369a1"),
            command=self._open_apk_folder
        ).pack(fill="x", padx=16, pady=4)
        
        input_frame = ctk.CTkFrame(parent, fg_color="transparent")
        input_frame.pack(fill="x", padx=16, pady=8)
        
        ctk.CTkLabel(input_frame, text="Stream URL:", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=(0, 8))
        self.url_entry = ctk.CTkEntry(input_frame, placeholder_text="http://192.168.1.xxx:8080/stream", width=300, height=36)
        self.url_entry.pack(side="left", fill="x", expand=True)
        
        self.status_lbl = ctk.CTkLabel(parent, text="", font=ctk.CTkFont(size=12))
        self.status_lbl.pack(pady=2)
        
        ctk.CTkButton(
            parent,
            text="🚀 2. Connect Stream & Open Mirror",
            height=40,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color=("#16a34a", "#15803d"),
            hover_color=("#15803d", "#166534"),
            command=self._on_connect_stream
        ).pack(fill="x", padx=16, pady=8)
        
        ctk.CTkLabel(
            parent,
            text="💡 You can also open the same URL in Google Chrome / Edge to view in browser",
            font=ctk.CTkFont(size=11),
            text_color=("#64748b", "#94a3b8")
        ).pack(pady=4)

    def _build_ios_tab(self, parent):
        ctk.CTkLabel(parent, text="🍏 iPhone / iPad Screen Mirroring (AirPlay)", font=ctk.CTkFont(size=15, weight="bold")).pack(pady=(12, 6))
        
        guide = (
            "iOS devices feature built-in screen mirroring (AirPlay):\n\n"
            "1. Connect iPhone and PC to the same Wi-Fi network\n"
            "2. Swipe down from top-right corner to open Control Center\n"
            "3. Tap the 'Screen Mirroring' icon (overlapping rectangles)\n"
            "4. Select your PC to stream 60 FPS video and audio!"
        )
        ctk.CTkLabel(parent, text=guide, font=ctk.CTkFont(size=13), justify="left").pack(padx=16, pady=10)

    def _open_apk_folder(self):
        apk_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "axecast_stream.apk")
        target_path = apk_path if os.path.exists(apk_path) else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        
        if sys.platform.startswith("win"):
            if os.path.exists(apk_path):
                subprocess.run(["explorer.exe", f"/select,{os.path.abspath(apk_path)}"])
            else:
                subprocess.run(["explorer.exe", target_path])
        elif sys.platform == "darwin":
            if os.path.exists(apk_path):
                subprocess.run(["open", "-R", os.path.abspath(apk_path)])
            else:
                subprocess.run(["open", target_path])
        else:
            subprocess.run(["xdg-open", os.path.dirname(os.path.abspath(target_path))])

    def _on_connect_stream(self):
        url = self.url_entry.get().strip()
        if not url:
            self.status_lbl.configure(text="⚠ Please enter a stream URL", text_color="#ef4444")
            return
            
        if not url.startswith("http"):
            url = "http://" + url
            
        if not url.endswith("/stream") and not url.endswith("/video"):
            if ":" in url and url.count(":") == 2:
                url = url.rstrip("/") + "/stream"
                
        self.status_lbl.configure(text="⏳ Connecting...", text_color="#38bdf8")
        self.update()
        
        from ui.stream_viewer import StreamViewer
        receiver = StreamReceiver()
        StreamViewer(
            self.master,
            stream_receiver=receiver,
            stream_url=url,
            device_name="Mobile (AxeCast)",
            save_dir=self.save_dir
        )
        
        self.status_lbl.configure(text="✅ Stream viewer opened!", text_color="#22c55e")
        self.after(800, self.destroy)
