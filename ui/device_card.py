import os
import time
import threading
import customtkinter as ctk
from PIL import Image
from .file_explorer_view import DeviceFileExplorerView
from .performance_graph_view import PerformanceGraphView

class DeviceCard(ctk.CTkFrame):
    """Interactive device card with strict single-instance per device controls."""
    
    def __init__(self, master, device_info, adb_mgr, mirror_engine, settings_cb, on_notify=None, on_dock_screen=None, **kwargs):
        super().__init__(master, corner_radius=12, fg_color=("#f1f5f9", "#1e293b"), border_width=1, border_color=("#cbd5e1", "#334155"), **kwargs)
        
        self.device = device_info
        self.serial = device_info.get("serial", device_info.get("ip", "Unknown"))
        self.model = device_info.get("model", "Android Device")
        self.state = device_info.get("state", "device")
        self.conn_type = device_info.get("type", "Wi-Fi")
        self.battery = device_info.get("battery", "N/A")
        
        self.is_apk = device_info.get("is_apk", False) or (":8080" in self.serial)
        self.version = "AxeCast App" if self.is_apk else device_info.get("version", "Android")
        
        if self.is_apk:
            ip = self.serial.split(":")[0]
            self.stream_url = device_info.get("url", f"http://{ip}:8080/stream")
        else:
            self.stream_url = ""
            
        self.adb = adb_mgr
        self.mirror_engine = mirror_engine
        self.get_settings = settings_cb
        self.notify = on_notify or (lambda msg: None)
        self.on_dock_screen = on_dock_screen
        
        # Single-instance tracker for this device
        self.explorer_open = False
        self.explorer_view = None
        self.floating_explorer_dialog = None
        self.floating_stream_viewer = None
        self.logcat_dialog = None
        self.perf_open = False
        self.perf_view = None
        self.floating_perf_dialog = None
        self.perf_action_btn = None
        
        # Telemetry metrics state & unit toggle modes (0: GB, 1: MB, 2: %)
        self.metrics = None
        self.ram_unit_mode = 0
        self.storage_unit_mode = 0
        self.global_unit_mode = 0
        self._metrics_busy = False
        self._last_metrics_poll = 0
        
        self._build_ui()
        if not self.is_apk:
            self._update_timer()

    def _build_ui(self):
        self.card_header = ctk.CTkFrame(self, fg_color="transparent")
        self.card_header.pack(fill="x", padx=10, pady=8)
        self.card_header.grid_columnconfigure(1, weight=1)
        
        icon_frame = ctk.CTkFrame(self.card_header, fg_color="transparent", width=40)
        icon_frame.grid(row=0, column=0, rowspan=2, padx=(4, 8), pady=4, sticky="ns")
        
        phone_icon = "📱" if self.conn_type == "USB" else "📶"
        icon_label = ctk.CTkLabel(icon_frame, text=phone_icon, font=ctk.CTkFont(size=28))
        icon_label.pack(pady=(4, 0))
        
        info_frame = ctk.CTkFrame(self.card_header, fg_color="transparent")
        info_frame.grid(row=0, column=1, padx=4, pady=(4, 2), sticky="nw")
        
        title_row = ctk.CTkFrame(info_frame, fg_color="transparent")
        title_row.pack(anchor="w", fill="x")
        
        name_label = ctk.CTkLabel(title_row, text=self.model, font=ctk.CTkFont(size=15, weight="bold"))
        name_label.pack(side="left", padx=(0, 8))
        
        badge_text = " ⚡ AxeCast App " if self.is_apk else f" {self.conn_type} "
        badge_color = ("#7c3aed", "#6d28d9") if self.is_apk else ("#0284c7", "#0369a1")
        
        type_badge = ctk.CTkLabel(
            title_row,
            text=badge_text,
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color=badge_color,
            text_color="white",
            corner_radius=6
        )
        type_badge.pack(side="left", padx=4)
        
        self.bat_badge = ctk.CTkLabel(
            title_row,
            text=f" 🔋 {self.battery} " if self.battery != "N/A" else " 🔋 --% ",
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color=("#10b981", "#065f46"),
            text_color="white",
            corner_radius=6
        )
        self.bat_badge.pack(side="left", padx=3)
        
        if not self.is_apk:
            # CPU Usage Badge
            self.cpu_badge = ctk.CTkLabel(
                title_row,
                text=" ⚡ --% ",
                font=ctk.CTkFont(size=11, weight="bold"),
                fg_color=("#0284c7", "#0369a1"),
                text_color="white",
                corner_radius=6
            )
            self.cpu_badge.pack(side="left", padx=3)
            
            # GPU Usage Badge
            self.gpu_badge = ctk.CTkLabel(
                title_row,
                text=" 🎮 --% ",
                font=ctk.CTkFont(size=11, weight="bold"),
                fg_color=("#10b981", "#059669"),
                text_color="white",
                corner_radius=6
            )
            self.gpu_badge.pack(side="left", padx=3)
            
            # RAM Usage Badge (Clickable to cycle GB -> MB -> %)
            self.ram_badge = ctk.CTkButton(
                title_row,
                text=" 🧠 -- ",
                width=1,
                height=22,
                font=ctk.CTkFont(size=11, weight="bold"),
                fg_color=("#7c3aed", "#6d28d9"),
                hover_color=("#6d28d9", "#5b21b6"),
                corner_radius=6,
                command=self._toggle_ram_unit
            )
            self.ram_badge.pack(side="left", padx=3)
            
            # Storage Badge (Clickable to cycle GB -> MB -> %)
            self.storage_badge = ctk.CTkButton(
                title_row,
                text=" 💾 -- ",
                width=1,
                height=22,
                font=ctk.CTkFont(size=11, weight="bold"),
                fg_color=("#d97706", "#b45309"),
                hover_color=("#b45309", "#92400e"),
                corner_radius=6,
                command=self._toggle_storage_unit
            )
            self.storage_badge.pack(side="left", padx=3)
            
            # Unit Switcher Icon Button (⇄)
            self.unit_toggle_btn = ctk.CTkButton(
                title_row,
                text="⇄",
                width=24,
                height=22,
                font=ctk.CTkFont(size=11, weight="bold"),
                fg_color=("#475569", "#334155"),
                hover_color=("#334155", "#1e293b"),
                corner_radius=6,
                command=self._toggle_all_units
            )
            self.unit_toggle_btn.pack(side="left", padx=2)
            
        sub_text = f"ID: {self.serial} • {self.version}"
        if self.state != "device" and not self.is_apk:
            sub_text += f" • ⚠ {self.state.upper()} (Please confirm on phone)"
            
        sub_label = ctk.CTkLabel(info_frame, text=sub_text, font=ctk.CTkFont(size=12), text_color=("#64748b", "#94a3b8"))
        sub_label.pack(anchor="w", pady=(2, 0))
        
        btn_frame = ctk.CTkFrame(self.card_header, fg_color="transparent")
        btn_frame.grid(row=0, column=2, padx=4, pady=4, sticky="ne")
        
        self.mirror_btn = ctk.CTkButton(
            btn_frame,
            text="▶ Mirror",
            width=85,
            height=34,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=("#16a34a", "#15803d"),
            hover_color=("#15803d", "#166534"),
            command=self._on_mirror
        )
        self.mirror_btn.pack(side="left", padx=3)
        
        if not self.is_apk:
            self.files_btn = ctk.CTkButton(
                btn_frame,
                text="📁 Files",
                width=75,
                height=34,
                font=ctk.CTkFont(size=13),
                fg_color=("#475569", "#334155"),
                hover_color=("#334155", "#1e293b"),
                command=self._toggle_inline_explorer
            )
            self.files_btn.pack(side="left", padx=3)

            self.logs_btn = ctk.CTkButton(
                btn_frame,
                text="📜 Logs",
                width=75,
                height=34,
                font=ctk.CTkFont(size=13),
                fg_color=("#0284c7", "#0369a1"),
                hover_color=("#0369a1", "#075985"),
                command=self._open_logcat_dialog
            )
            self.logs_btn.pack(side="left", padx=3)
            
            self.snap_btn = ctk.CTkButton(
                btn_frame,
                text="📸 Capture",
                width=85,
                height=34,
                font=ctk.CTkFont(size=13),
                fg_color=("#2563eb", "#1d4ed8"),
                hover_color=("#1d4ed8", "#1e40af"),
                command=self._on_screenshot
            )
            self.snap_btn.pack(side="left", padx=3)
            
            self.rec_btn = ctk.CTkButton(
                btn_frame,
                text="🎥 Record",
                width=85,
                height=34,
                font=ctk.CTkFont(size=13),
                fg_color=("#dc2626", "#b91c1c"),
                hover_color=("#b91c1c", "#991b1b"),
                command=self._on_toggle_record
            )
            self.rec_btn.pack(side="left", padx=3)
            
            ctrl_bar = ctk.CTkFrame(self.card_header, fg_color=("#e2e8f0", "#0f172a"), corner_radius=8, height=30)
            ctrl_bar.grid(row=1, column=1, columnspan=2, padx=4, pady=(6, 2), sticky="ew")
            
            quick_btns = [
                ("🏠 Home", lambda: self.adb.send_keyevent(self.serial, 3)),
                ("◀ Back", lambda: self.adb.send_keyevent(self.serial, 4)),
                ("🔲 Apps", lambda: self.adb.send_keyevent(self.serial, 187)),
                ("💡 Screen Off", lambda: self.adb.send_keyevent(self.serial, 26)),
                ("🔊 Vol+", lambda: self.adb.send_keyevent(self.serial, 24)),
                ("🔉 Vol-", lambda: self.adb.send_keyevent(self.serial, 25)),
                ("📊 Graph", self._toggle_inline_performance),
            ]
            
            for text, cmd in quick_btns:
                btn = ctk.CTkButton(
                    ctrl_bar,
                    text=text,
                    height=24,
                    width=65,
                    font=ctk.CTkFont(size=11),
                    fg_color="transparent",
                    text_color=("#334155", "#cbd5e1"),
                    hover_color=("#cbd5e1", "#1e293b"),
                    command=cmd
                )
                btn.pack(side="left", padx=2, pady=2)
                if "Graph" in text:
                    self.perf_action_btn = btn

        self.perf_drawer = ctk.CTkFrame(self, fg_color="transparent")
        self.explorer_drawer = ctk.CTkFrame(self, fg_color="transparent")

    def _toggle_inline_explorer(self):
        if self.floating_explorer_dialog and self.floating_explorer_dialog.winfo_exists():
            self.floating_explorer_dialog.lift()
            self.floating_explorer_dialog.focus()
            return
            
        if self.explorer_open:
            self._close_inline_explorer()
        else:
            self._open_inline_explorer()

    def _open_inline_explorer(self):
        self.explorer_open = True
        self.files_btn.configure(fg_color=("#0284c7", "#0369a1"))
        self.explorer_drawer.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        
        self.explorer_view = DeviceFileExplorerView(
            self.explorer_drawer,
            serial=self.serial,
            model_name=self.model,
            on_toggle_dock=self._pop_out_explorer,
            is_docked=True,
            height=340
        )
        self.explorer_view.pack(fill="both", expand=True)
        self.notify(f"📁 Opened File Explorer for {self.model}")

    def _close_inline_explorer(self):
        self.explorer_open = False
        self.files_btn.configure(fg_color=("#475569", "#334155"))
        if self.explorer_view:
            self.explorer_view.destroy()
            self.explorer_view = None
        self.explorer_drawer.pack_forget()

    def _pop_out_explorer(self):
        from ui.file_explorer_dialog import DeviceFileExplorerDialog
        self._close_inline_explorer()
        
        if self.floating_explorer_dialog and self.floating_explorer_dialog.winfo_exists():
            self.floating_explorer_dialog.lift()
            self.floating_explorer_dialog.focus()
            return
            
        self.floating_explorer_dialog = DeviceFileExplorerDialog(
            self.winfo_toplevel(),
            serial=self.serial,
            model_name=self.model,
            on_dock=lambda s, m: self._open_inline_explorer()
        )
        self.notify(f"↗ Detached File Explorer window for {self.model}")

    def _toggle_inline_performance(self):
        if self.floating_perf_dialog and self.floating_perf_dialog.winfo_exists():
            self.floating_perf_dialog.lift()
            self.floating_perf_dialog.focus()
            return
            
        if self.perf_open:
            self._close_inline_performance()
        else:
            self._open_inline_performance()

    def _open_inline_performance(self):
        self.perf_open = True
        if hasattr(self, 'perf_action_btn') and self.perf_action_btn:
            self.perf_action_btn.configure(fg_color=("#0284c7", "#0369a1"), text_color="white")
        # Pack performance drawer right above explorer drawer if both are open
        self.perf_drawer.pack(fill="both", expand=True, padx=10, pady=(0, 8), before=self.explorer_drawer if self.explorer_open else None)
        
        self.perf_view = PerformanceGraphView(
            self.perf_drawer,
            serial=self.serial,
            model_name=self.model,
            adb_mgr=self.adb,
            on_toggle_dock=self._pop_out_performance,
            is_docked=True,
            height=280
        )
        self.perf_view.pack(fill="both", expand=True)
        self.notify(f"📊 Opened Live Performance Monitor for {self.model}")

    def _close_inline_performance(self):
        self.perf_open = False
        if hasattr(self, 'perf_action_btn') and self.perf_action_btn:
            self.perf_action_btn.configure(fg_color="transparent", text_color=("#334155", "#cbd5e1"))
        if self.perf_view:
            self.perf_view.destroy()
            self.perf_view = None
        self.perf_drawer.pack_forget()

    def _pop_out_performance(self):
        self._close_inline_performance()
        if self.floating_perf_dialog and self.floating_perf_dialog.winfo_exists():
            self.floating_perf_dialog.lift()
            self.floating_perf_dialog.focus()
            return
            
        dlg = ctk.CTkToplevel(self.winfo_toplevel())
        dlg.title(f"📊 Live Performance Monitor — {self.model}")
        dlg.geometry("780x420")
        dlg.minsize(580, 320)
        
        def on_dock():
            dlg.destroy()
            self._open_inline_performance()
            
        pv = PerformanceGraphView(
            dlg,
            serial=self.serial,
            model_name=self.model,
            adb_mgr=self.adb,
            on_toggle_dock=on_dock,
            is_docked=False
        )
        pv.pack(fill="both", expand=True, padx=10, pady=10)
        
        self.floating_perf_dialog = dlg
        self.notify(f"↗ Detached Performance Monitor for {self.model}")

    def _open_logcat_dialog(self):
        if self.logcat_dialog and self.logcat_dialog.winfo_exists():
            self.logcat_dialog.lift()
            self.logcat_dialog.focus()
            return
            
        from ui.logcat_dialog import LogcatDialog
        self.logcat_dialog = LogcatDialog(
            self.winfo_toplevel(),
            serial=self.serial,
            model=self.model,
            adb=self.adb
        )
        self.notify(f"📜 Opened Logcat Studio for {self.model}")

    def _on_mirror(self):
        if self.is_apk:
            # Check if floating stream viewer is already active
            if self.floating_stream_viewer and self.floating_stream_viewer.winfo_exists():
                self.floating_stream_viewer.lift()
                self.floating_stream_viewer.focus()
                return
                
            if self.on_dock_screen:
                self.on_dock_screen(self.serial, self.model, self.stream_url)
            else:
                from ui.stream_viewer import StreamViewer
                from core.stream_receiver import StreamReceiver
                opts = self.get_settings()
                save_dir = opts.get("save_dir", "captures")
                receiver = StreamReceiver()
                self.floating_stream_viewer = StreamViewer(
                    self.winfo_toplevel(),
                    stream_receiver=receiver,
                    stream_url=self.stream_url,
                    device_name=self.model,
                    save_dir=save_dir
                )
            self.notify(f"🚀 Started live mirror for {self.model}")
        else:
            if self.mirror_engine.is_mirroring(self.serial):
                self.notify(f"ℹ {self.model} is already mirroring")
                return
                
            opts = self.get_settings()
            success, msg = self.mirror_engine.start_mirror(self.serial, self.model, opts)
            if success:
                self.notify(f"🚀 Mirroring {self.model} successfully")
            else:
                self.notify(f"⚠ Failed to mirror: {msg}")

    def _on_screenshot(self):
        opts = self.get_settings()
        save_dir = opts.get("save_dir", "captures")
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        clean_model = "".join(c for c in self.model if c.isalnum() or c in (" ", "_", "-")).strip()
        filename = f"SNAP_{clean_model}_{timestamp}.png"
        filepath = os.path.join(save_dir, filename)
        
        success = self.adb.take_screenshot(self.serial, filepath)
        if success:
            self.notify(f"📸 Screenshot saved: {filename}")
        else:
            self.notify(f"⚠ Failed to capture screenshot for {self.model}")

    def _on_toggle_record(self):
        if self.mirror_engine.is_recording(self.serial):
            self.rec_btn.configure(text="⏳ Finalizing...", state="disabled")
            self.notify("⏳ Finalizing recorded video file...")
            
            def stop_in_thread():
                saved_file = self.mirror_engine.stop_recording(self.serial)
                self.after(0, lambda: self.rec_btn.configure(text="🎥 Record", fg_color=("#dc2626", "#b91c1c"), state="normal"))
                if saved_file and os.path.exists(saved_file):
                    size_kb = os.path.getsize(saved_file) // 1024
                    self.after(0, lambda: self.notify(f"🎬 Video recorded ({size_kb} KB): {os.path.basename(saved_file)}"))
                else:
                    self.after(0, lambda: self.notify("⚠ Video recording completed"))
                    
            threading.Thread(target=stop_in_thread, daemon=True).start()
        else:
            opts = self.get_settings()
            save_dir = opts.get("save_dir", "captures")
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            clean_model = "".join(c for c in self.model if c.isalnum() or c in (" ", "_", "-")).strip()
            fmt = opts.get("format", "mp4")
            filename = f"REC_{clean_model}_{timestamp}.{fmt}"
            filepath = os.path.join(save_dir, filename)
            
            success = self.mirror_engine.start_recording(self.serial, self.model, filepath, opts)
            if success:
                self.notify(f"🔴 Recording video for {self.model}...")
            else:
                self.notify(f"⚠ Failed to start video recording")

    def _toggle_ram_unit(self):
        self.ram_unit_mode = (self.ram_unit_mode + 1) % 3
        self._refresh_metric_labels()

    def _toggle_storage_unit(self):
        self.storage_unit_mode = (self.storage_unit_mode + 1) % 3
        self._refresh_metric_labels()

    def _toggle_all_units(self):
        self.global_unit_mode = (self.global_unit_mode + 1) % 3
        self.ram_unit_mode = self.global_unit_mode
        self.storage_unit_mode = self.global_unit_mode
        self._refresh_metric_labels()

    def _refresh_metric_labels(self):
        if not self.metrics:
            return
        try:
            # Battery
            bat_text = f" 🔋 {self.metrics.get('battery_level', 'N/A')} "
            if self.metrics.get("battery_charging"):
                bat_text = f" 🔋 {self.metrics.get('battery_level', 'N/A')} ⚡ "
            self.bat_badge.configure(text=bat_text)
            
            # CPU
            if hasattr(self, 'cpu_badge'):
                self.cpu_badge.configure(text=f" ⚡ {self.metrics.get('cpu_pct', '10%')} ")
                
            # GPU
            if hasattr(self, 'gpu_badge'):
                self.gpu_badge.configure(text=f" 🎮 {self.metrics.get('gpu_pct', '0%')} ")
                
            # RAM
            if hasattr(self, 'ram_badge'):
                if self.ram_unit_mode == 0:
                    # GB mode
                    ram_text = f" 🧠 {self.metrics['ram_used_gb']}/{self.metrics['ram_total_gb']} GB "
                elif self.ram_unit_mode == 1:
                    # MB mode
                    ram_text = f" 🧠 {self.metrics['ram_used_mb']}/{self.metrics['ram_total_mb']} MB "
                else:
                    # % mode
                    ram_text = f" 🧠 {self.metrics['ram_pct']}% "
                self.ram_badge.configure(text=ram_text)
                
            # Storage
            if hasattr(self, 'storage_badge'):
                if self.storage_unit_mode == 0:
                    # GB mode
                    stor_text = f" 💾 {self.metrics['storage_used_gb']}/{self.metrics['storage_total_gb']} GB "
                elif self.storage_unit_mode == 1:
                    # MB mode
                    stor_text = f" 💾 {self.metrics['storage_used_mb']}/{self.metrics['storage_total_mb']} MB "
                else:
                    # % mode
                    stor_text = f" 💾 {self.metrics['storage_pct']}% "
                self.storage_badge.configure(text=stor_text)
        except Exception:
            pass

    def _fetch_metrics_async(self):
        if self._metrics_busy or self.is_apk:
            return
        self._metrics_busy = True
        
        def run_query():
            try:
                data = self.adb.get_device_metrics(self.serial)
                self.metrics = data
                self.after(0, self._refresh_metric_labels)
            except Exception:
                pass
            finally:
                self._metrics_busy = False
                
        threading.Thread(target=run_query, daemon=True).start()

    def _update_timer(self):
        now = time.time()
        # Poll hardware telemetry metrics every 3.5 seconds
        if now - self._last_metrics_poll >= 3.5:
            self._last_metrics_poll = now
            self._fetch_metrics_async()

        if self.mirror_engine.is_recording(self.serial):
            duration = self.mirror_engine.get_record_duration(self.serial)
            if self.rec_btn.cget("state") != "disabled":
                self.rec_btn.configure(text=f"⏹ {duration}", fg_color=("#ea580c", "#c2410c"))
        elif self.rec_btn.cget("text").startswith("⏹"):
            self.rec_btn.configure(text="🎥 Record", fg_color=("#dc2626", "#b91c1c"), state="normal")
            
        self.after(1000, self._update_timer)
