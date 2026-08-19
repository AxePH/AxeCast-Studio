import os
import sys
import threading
import time
import subprocess
import customtkinter as ctk
from pathlib import Path

from core.system_detector import SystemDetector
from core.adb_manager import ADBManager
from core.mirror_engine import MirrorEngine
from core.auto_discovery import NetworkDiscovery
from core.stream_receiver import StreamReceiver
from core.resource_monitor import ResourceMonitor
from core.studio_logger import logger

import tkinter as tk
from .device_card import DeviceCard
from .wireless_dialog import WirelessDialog
from .settings_dialog import SettingsDialog
from .no_dev_dialog import NoDevDialog
from .stream_viewer import StreamViewer
from .docked_screen_card import DockedScreenCard
try:
    from tkinterdnd2 import TkinterDnD
    _has_tkdnd = True
except ImportError:
    _has_tkdnd = False

if _has_tkdnd:
    class BaseWindow(ctk.CTk, TkinterDnD.DnDWrapper):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            try:
                self.TkdndVersion = TkinterDnD._require(self)
            except Exception:
                pass
else:
    class BaseWindow(ctk.CTk):
        pass

class MainWindow(BaseWindow):
    """Main application window - 100% Cross-Platform (Windows, macOS, Linux) with Pixel-Perfect UI."""
    
    def __init__(self):
        super().__init__()
        
        self.sys = SystemDetector()
        self.adb = ADBManager(self.sys)
        self.mirror_engine = MirrorEngine(self.sys)
        
        self.settings = {
            "format": "mp4",
            "max_size": "1080",
            "bitrate": "8M",
            "max_fps": "60",
            "always_on_top": False,
            "turn_screen_off": False,
            "stay_awake": True,
            "audio": True,
            "save_dir": str(Path(__file__).resolve().parent.parent / "captures")
        }
        Path(self.settings["save_dir"]).mkdir(parents=True, exist_ok=True)
        # Clean up any leftover temporary clipboard cache on startup
        self._cleanup_clipboard_cache()
        
        self.title("AxeCast Studio 🪓 - Mobile Screen Mirror & Capture")
        self.geometry("1180x720")
        self.minsize(880, 540)
        
        # Set Window Icon
        icon_path = Path(__file__).resolve().parent.parent / "assets" / "icon.ico"
        if not icon_path.exists():
            icon_path = Path(__file__).resolve().parent.parent / "icon.ico"
        if icon_path.exists() and sys.platform.startswith("win"):
            try:
                self.iconbitmap(str(icon_path))
            except Exception:
                pass
        
        self.devices = []
        self.is_scanning = False
        self.auto_refresh_enabled = True
        self.docked_screens = {}
        self.studio_log_dialog = None
        
        self.discovery = NetworkDiscovery(on_device_found=lambda dev: self.after(0, self.refresh_devices_async))
        self.discovery.start()
        
        self.res_monitor = ResourceMonitor(update_interval=1.5)
        
        self._build_header()
        self._build_toolbar()
        self._build_main_layout()
        self._build_statusbar()
        
        self._start_auto_refresh()
        self.res_monitor.start(on_update=lambda c, g, r, d: self.after(0, lambda: self._update_resource_badges(c, g, r, d)))
        
        # Keyboard Shortcuts for Refresh & Open Folder
        self.bind("<F5>", lambda e: self.refresh_devices_async())
        self.bind("<Control-r>", lambda e: self.refresh_devices_async())
        self.bind("<Control-R>", lambda e: self.refresh_devices_async())
        self.bind("<Control-o>", lambda e: self._open_captures_folder())
        self.bind("<Control-O>", lambda e: self._open_captures_folder())
        
        # Cleanly shut down all child windows, mirror processes, and background threads on exit
        self.protocol("WM_DELETE_WINDOW", self._on_app_close)
        
        # Silent Background Update Check after 3 seconds
        self.after(3000, self._check_update_startup)

    def _check_update_startup(self):
        try:
            from core.updater import check_for_updates_async
            def on_check(res):
                if res.get("has_update") and self.winfo_exists():
                    self.after(0, lambda: self._prompt_update(res))
            check_for_updates_async(callback=on_check)
        except Exception:
            pass

    def _prompt_update(self, res: dict):
        try:
            from ui.update_dialog import UpdateDialog
            UpdateDialog(self, res)
        except Exception:
            pass

    def _build_header(self):
        header_frame = ctk.CTkFrame(self, height=58, corner_radius=0, fg_color=("#0f172a", "#090d16"))
        header_frame.pack(fill="x", side="top")
        
        logo_frame = ctk.CTkFrame(header_frame, fg_color="transparent")
        logo_frame.pack(side="left", padx=20, pady=10)
        
        title_label = ctk.CTkLabel(
            logo_frame,
            text="🪓 AxeCast Studio",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color="#38bdf8"
        )
        title_label.pack(side="left")
        
        ver_badge = ctk.CTkLabel(
            logo_frame,
            text=" Multi-Screen Studio ",
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color="#0369a1",
            text_color="white",
            corner_radius=6
        )
        ver_badge.pack(side="left", padx=(10, 0))
        
        # Right Header: Resource Monitor Badges + Theme Button
        right_frame = ctk.CTkFrame(header_frame, fg_color="transparent")
        right_frame.pack(side="right", padx=16, pady=10)
        
        self.theme_btn = ctk.CTkButton(
            right_frame,
            text="🌙 Theme",
            width=75,
            height=30,
            font=ctk.CTkFont(size=11),
            fg_color=("#334155", "#1e293b"),
            hover_color=("#475569", "#334155"),
            command=self._toggle_theme
        )
        self.theme_btn.pack(side="right", padx=(6, 0))
        
        self.sqlite_btn = ctk.CTkButton(
            right_frame,
            text="🗄 AxeSQL Studio",
            width=120,
            height=30,
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color=("#0284c7", "#0369a1"),
            hover_color=("#0369a1", "#075985"),
            command=self._open_sqlite_studio
        )
        self.sqlite_btn.pack(side="right", padx=(6, 0))
        
        self.res_container = ctk.CTkFrame(right_frame, fg_color=("#1e293b", "#0f172a"), corner_radius=8)
        self.res_container.pack(side="right", padx=(0, 4))
        
        self.cpu_badge = ctk.CTkLabel(
            self.res_container,
            text="⚡ CPU: 0.2%",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#38bdf8"
        )
        self.cpu_badge.pack(side="left", padx=(8, 4), pady=4)
        
        ctk.CTkLabel(self.res_container, text="|", font=ctk.CTkFont(size=10), text_color="#475569").pack(side="left")
        
        self.gpu_badge = ctk.CTkLabel(
            self.res_container,
            text="🎮 GPU: 0.4%",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#10b981"
        )
        self.gpu_badge.pack(side="left", padx=4, pady=4)
        
        ctk.CTkLabel(self.res_container, text="|", font=ctk.CTkFont(size=10), text_color="#475569").pack(side="left")
        
        self.ram_badge = ctk.CTkLabel(
            self.res_container,
            text="🧠 RAM: 35 MB",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#a855f7"
        )
        self.ram_badge.pack(side="left", padx=4, pady=4)
        
        ctk.CTkLabel(self.res_container, text="|", font=ctk.CTkFont(size=10), text_color="#475569").pack(side="left")
        
        self.disk_badge = ctk.CTkLabel(
            self.res_container,
            text="💾 Disk: 1.5 MB",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#f59e0b"
        )
        self.disk_badge.pack(side="left", padx=(4, 8), pady=4)

    def _update_resource_badges(self, cpu: float, gpu: float, ram: float, disk: float):
        try:
            self.cpu_badge.configure(text=f"⚡ CPU: {cpu:.1f}%")
            self.gpu_badge.configure(text=f"🎮 GPU: {gpu:.1f}%")
            self.ram_badge.configure(text=f"🧠 RAM: {ram:.0f} MB")
            self.disk_badge.configure(text=f"💾 Disk: {disk:.1f} MB")
        except Exception:
            pass

    def _build_toolbar(self):
        toolbar = ctk.CTkFrame(self, height=46, corner_radius=0, fg_color=("#f8fafc", "#0f172a"))
        toolbar.pack(fill="x", side="top", padx=16, pady=(10, 4))
        
        left_tb = ctk.CTkFrame(toolbar, fg_color="transparent")
        left_tb.pack(side="left", fill="y", pady=4)
        
        self.refresh_btn = ctk.CTkButton(
            left_tb,
            text="🔄 Refresh",
            height=32,
            width=85,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=("#0284c7", "#0369a1"),
            command=self.refresh_devices_async
        )
        self.refresh_btn.pack(side="left", padx=4)
        
        self.wifi_btn = ctk.CTkButton(
            left_tb,
            text="📶 Wireless (Wi-Fi)",
            height=32,
            font=ctk.CTkFont(size=12),
            fg_color=("#0284c7", "#0369a1"),
            command=self._open_wireless_dialog
        )
        self.wifi_btn.pack(side="left", padx=4)
        
        self.mirror_all_btn = ctk.CTkButton(
            left_tb,
            text="⚡ Mirror All",
            height=32,
            width=95,
            font=ctk.CTkFont(size=12),
            fg_color=("#16a34a", "#15803d"),
            command=self._mirror_all
        )
        self.mirror_all_btn.pack(side="left", padx=4)
        
        self.snap_all_btn = ctk.CTkButton(
            left_tb,
            text="📸 Capture All",
            height=32,
            width=100,
            font=ctk.CTkFont(size=12),
            fg_color=("#2563eb", "#1d4ed8"),
            command=self._screenshot_all
        )
        self.snap_all_btn.pack(side="left", padx=4)

        self.logs_btn = ctk.CTkButton(
            left_tb,
            text="📜 Logs",
            height=32,
            width=80,
            font=ctk.CTkFont(size=12),
            fg_color=("#0284c7", "#0369a1"),
            hover_color=("#0369a1", "#075985"),
            command=self._open_studio_logs
        )
        self.logs_btn.pack(side="left", padx=4)

        right_tb = ctk.CTkFrame(toolbar, fg_color="transparent")
        right_tb.pack(side="right", fill="y", pady=4)
        
        self.apk_btn = ctk.CTkButton(
            right_tb,
            text="📲 Companion APK",
            height=32,
            width=120,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=("#7c3aed", "#6d28d9"),
            command=self._open_nodev_dialog
        )
        self.apk_btn.pack(side="left", padx=4)
        
        self.folder_btn = ctk.CTkButton(
            right_tb,
            text="📁 Open Folder",
            height=32,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=("#0284c7", "#0369a1"),
            hover_color=("#0369a1", "#075985"),
            command=self._open_captures_folder
        )
        self.folder_btn.pack(side="left", padx=4)
        
        self.settings_btn = ctk.CTkButton(
            right_tb,
            text="⚙ Settings",
            height=32,
            width=80,
            font=ctk.CTkFont(size=12),
            fg_color=("#475569", "#334155"),
            command=self._open_settings_dialog
        )
        self.settings_btn.pack(side="left", padx=4)

    def _build_main_layout(self):
        self.main_split = ctk.CTkFrame(self, fg_color="transparent")
        self.main_split.pack(fill="both", expand=True, padx=16, pady=4)
        
        self.left_panel = ctk.CTkFrame(self.main_split, fg_color="transparent")
        self.left_panel.pack(side="left", fill="both", expand=True, padx=(0, 6))
        
        self.scroll_frame = ctk.CTkScrollableFrame(
            self.left_panel,
            corner_radius=8,
            fg_color="transparent"
        )
        self.scroll_frame.pack(fill="both", expand=True)
        
        self.empty_frame = ctk.CTkFrame(self.scroll_frame, fg_color=("#f1f5f9", "#1e293b"), corner_radius=12)
        self._build_empty_state()
        
        self.right_dock_panel = ctk.CTkFrame(self.main_split, fg_color=("#f1f5f9", "#1e293b"), corner_radius=10, width=0)

    def _build_empty_state(self):
        for widget in self.empty_frame.winfo_children():
            widget.destroy()
            
        icon = ctk.CTkLabel(self.empty_frame, text="📱🔌", font=ctk.CTkFont(size=44))
        icon.pack(pady=(36, 12))
        
        title = ctk.CTkLabel(
            self.empty_frame,
            text="No Connected Mobile Devices Found",
            font=ctk.CTkFont(size=18, weight="bold")
        )
        title.pack(pady=4)
        
        guide_text = (
            "📌 Choose your preferred connection method:\n\n"
            "Method 1 (Wireless / No Dev Mode):\n"
            "• Open AxeCast Stream app on phone and tap 'START STREAMING'\n"
            "• Your device will appear automatically here!\n\n"
            "Method 2 (USB Cable / 60 FPS Pro Mode):\n"
            "• Enable USB Debugging in phone Developer Options and plug in USB cable"
        )
        guide_label = ctk.CTkLabel(
            self.empty_frame,
            text=guide_text,
            font=ctk.CTkFont(size=13),
            justify="center",
            text_color=("#64748b", "#94a3b8")
        )
        guide_label.pack(padx=24, pady=12)
        
        scan_btn = ctk.CTkButton(
            self.empty_frame,
            text="🔍 Scan for Devices",
            height=38,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=("#0284c7", "#0369a1"),
            command=self.refresh_devices_async
        )
        scan_btn.pack(pady=(8, 36))

    def _build_statusbar(self):
        self.status_bar = ctk.CTkFrame(self, height=30, corner_radius=0, fg_color=("#e2e8f0", "#0f172a"))
        self.status_bar.pack(fill="x", side="bottom")
        
        self.status_label = ctk.CTkLabel(
            self.status_bar,
            text="🟢 Ready",
            font=ctk.CTkFont(size=12),
            text_color=("#475569", "#94a3b8")
        )
        self.status_label.pack(side="left", padx=16)
        
        self.count_label = ctk.CTkLabel(
            self.status_bar,
            text="📱 Connected Devices: 0",
            font=ctk.CTkFont(size=12),
            text_color=("#475569", "#94a3b8")
        )
        self.count_label.pack(side="right", padx=16)

    def refresh_devices_async(self):
        if self.is_scanning:
            return
            
        def run():
            self.is_scanning = True
            adb_devs = self.adb.get_devices()
            apk_devs = self.discovery.get_devices()
            combined = list(adb_devs)
            
            for apk in apk_devs:
                if not any(apk["ip"] in d["serial"] for d in adb_devs):
                    combined.append({
                        "serial": f"{apk['ip']}:{apk['port']}",
                        "model": apk["model"],
                        "state": "device",
                        "type": "Wi-Fi",
                        "battery": "N/A",
                        "version": "AxeCast App",
                        "is_apk": True,
                        "url": apk["url"]
                    })
                    
            if len(combined) != len(self.devices) or not hasattr(self, "_logged_init_scan"):
                self._logged_init_scan = True
                logger.info("DEVICE", f"Discovered {len(combined)} device(s) connected.")

            try:
                self.after(0, lambda: self._update_device_list(combined))
            except Exception:
                pass
            self.is_scanning = False
            
        threading.Thread(target=run, daemon=True).start()

    def _update_device_list(self, new_devices):
        curr_keys = [(d.get("serial", d.get("ip")), d.get("state"), d.get("is_apk", False)) for d in self.devices]
        new_keys = [(d.get("serial", d.get("ip")), d.get("state"), d.get("is_apk", False)) for d in new_devices]
        
        if curr_keys == new_keys and (len(self.devices) > 0 or self.empty_frame.winfo_ismapped()):
            return
            
        self.devices = new_devices
        self.count_label.configure(text=f"📱 Connected Devices: {len(self.devices)}")
        
        for widget in self.scroll_frame.winfo_children():
            widget.pack_forget()
            
        if not self.devices:
            self.empty_frame.pack(fill="both", expand=True, padx=20, pady=20)
        else:
            for dev in self.devices:
                card = DeviceCard(
                    self.scroll_frame,
                    device_info=dev,
                    adb_mgr=self.adb,
                    mirror_engine=self.mirror_engine,
                    settings_cb=lambda: self.settings,
                    on_notify=self.show_notification,
                    on_dock_screen=self.dock_screen_on_right
                )
                card.pack(fill="x", pady=6, padx=4)

    def dock_screen_on_right(self, serial: str, model_name: str, stream_url: str):
        if serial in self.docked_screens:
            return
            
        if not self.docked_screens:
            self.right_dock_panel.pack(side="right", fill="both", padx=(6, 0))
            for w in self.right_dock_panel.winfo_children():
                w.destroy()
                
            hdr = ctk.CTkFrame(self.right_dock_panel, height=32, fg_color="transparent")
            hdr.pack(fill="x", padx=8, pady=(8, 4))
            ctk.CTkLabel(hdr, text="📱 Multi-Screen Live Studio", font=ctk.CTkFont(size=13, weight="bold"), text_color="#38bdf8").pack(side="left")
            
            self.dock_screens_container = ctk.CTkScrollableFrame(
                self.right_dock_panel,
                orientation="horizontal",
                fg_color="transparent"
            )
            self.dock_screens_container.pack(fill="both", expand=True, padx=4, pady=4)
            
        receiver = StreamReceiver()
        card = DockedScreenCard(
            self.dock_screens_container,
            serial=serial,
            model_name=model_name,
            stream_url=stream_url,
            receiver=receiver,
            on_pop_out=self.pop_out_screen,
            on_close=self.undock_screen,
            save_dir=self.settings.get("save_dir", "captures")
        )
        card.pack(side="left", padx=4, pady=2, fill="both")
        
        self.docked_screens[serial] = {
            "card": card,
            "receiver": receiver,
            "model": model_name,
            "url": stream_url
        }
        self.show_notification(f"📱 Docked screen for {model_name} on right panel")

    def undock_screen(self, serial: str):
        if serial in self.docked_screens:
            del self.docked_screens[serial]
            
        if not self.docked_screens:
            self.right_dock_panel.pack_forget()

    def pop_out_screen(self, serial: str, model_name: str, stream_url: str):
        if serial in self.docked_screens:
            info = self.docked_screens[serial]
            info["card"].destroy()
            self.undock_screen(serial)
            
        receiver = StreamReceiver()
        StreamViewer(
            self,
            stream_receiver=receiver,
            stream_url=stream_url,
            device_name=model_name,
            save_dir=self.settings.get("save_dir", "captures")
        )
        self.show_notification(f"↗ Detached {model_name} to floating window")

    def _start_auto_refresh(self):
        def auto_poll():
            while self.auto_refresh_enabled:
                time.sleep(5.0)
                if not self.is_scanning:
                    self.refresh_devices_async()
                        
        threading.Thread(target=auto_poll, daemon=True).start()

    def show_notification(self, msg: str):
        self.status_label.configure(text=msg)
        self.after(4000, lambda: self.status_label.configure(text="🟢 Ready"))

    def _mirror_all(self):
        if not self.devices:
            self.show_notification("⚠ No devices available for mirroring")
            return
            
        count = 0
        for dev in self.devices:
            if dev.get("is_apk"):
                self.dock_screen_on_right(dev["serial"], dev["model"], dev["url"])
                count += 1
            elif dev["state"] == "device":
                self.mirror_engine.start_mirror(dev["serial"], dev["model"], self.settings)
                count += 1
        self.show_notification(f"🚀 Mirrored all {count} device(s)")

    def _screenshot_all(self):
        if not self.devices:
            self.show_notification("⚠ No devices available for capture")
            return
            
        save_dir = self.settings.get("save_dir", "captures")
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        count = 0
        
        for dev in self.devices:
            if not dev.get("is_apk") and dev["state"] == "device":
                clean_model = "".join(c for c in dev["model"] if c.isalnum() or c in (" ", "_", "-")).strip()
                filename = f"SNAP_{clean_model}_{timestamp}.png"
                filepath = os.path.join(save_dir, filename)
                if self.adb.take_screenshot(dev["serial"], filepath):
                    count += 1
                    
        self.show_notification(f"📸 Captured screenshot from {count} device(s)")

    def _open_captures_folder(self):
        path = self.settings.get("save_dir", "captures")
        Path(path).mkdir(parents=True, exist_ok=True)
        
        if self.sys.os_name == "Windows":
            os.startfile(path)
        elif self.sys.os_name == "Darwin":
            subprocess.run(["open", path])
        else:
            subprocess.run(["xdg-open", path])

    def _open_wireless_dialog(self):
        WirelessDialog(self, self.adb, on_connected=self.refresh_devices_async)

    def _open_settings_dialog(self):
        SettingsDialog(self, self.settings, on_save=self._on_settings_saved)

    def _open_nodev_dialog(self):
        NoDevDialog(self, save_dir=self.settings.get("save_dir", "captures"))

    def _on_settings_saved(self, new_settings):
        self.settings.update(new_settings)
        self.show_notification("💾 Settings saved successfully")

    def _toggle_theme(self):
        current = ctk.get_appearance_mode()
        if current == "Dark":
            ctk.set_appearance_mode("Light")
            self.theme_btn.configure(text="☀ Theme")
        else:
            ctk.set_appearance_mode("Dark")
            self.theme_btn.configure(text="🌙 Theme")

        # Recursively propagate theme update to all embedded views and child windows
        self._propagate_theme(self)
        for child in self.winfo_children():
            if isinstance(child, (ctk.CTkToplevel, tk.Toplevel)):
                self._propagate_theme(child)

    def _propagate_theme(self, widget):
        if hasattr(widget, "apply_theme") and callable(widget.apply_theme):
            try:
                widget.apply_theme()
            except Exception:
                pass
        if hasattr(widget, "winfo_children"):
            try:
                for sub in widget.winfo_children():
                    self._propagate_theme(sub)
            except Exception:
                pass

    def _open_sqlite_studio(self):
        """Opens standalone SQLite Studio dialog."""
        from ui.sqlite_studio_dialog import SQLiteStudioDialog
        dlg = SQLiteStudioDialog(self)
        dlg.focus_set()

    def _open_studio_logs(self):
        """Opens Main Program / Studio System Logs & Diagnostics dialog."""
        if hasattr(self, "studio_log_dialog") and self.studio_log_dialog and self.studio_log_dialog.winfo_exists():
            self.studio_log_dialog.lift()
            self.studio_log_dialog.focus()
            return
            
        from ui.studio_log_dialog import StudioLogDialog
        self.studio_log_dialog = StudioLogDialog(self)
        self.studio_log_dialog.focus_set()
            
    def _on_app_close(self):
        """Cleanly close all child windows, stop all mirroring processes, and exit cleanly."""
        self.auto_refresh_enabled = False
        
        # 1. Stop background discovery and resource monitor
        if hasattr(self, 'discovery'):
            try:
                self.discovery.stop()
            except Exception:
                pass
                
        if hasattr(self, 'res_monitor'):
            try:
                self.res_monitor.stop()
            except Exception:
                pass
                
        # 2. Terminate all active mirroring processes & recordings (e.g. phone screens)
        if hasattr(self, 'mirror_engine'):
            try:
                self.mirror_engine.stop_all()
            except Exception:
                pass
                
        # 3. Stop all docked screen card video streams
        if hasattr(self, 'docked_screens'):
            for s, data in list(self.docked_screens.items()):
                try:
                    if "receiver" in data and data["receiver"]:
                        data["receiver"].stop_stream()
                except Exception:
                    pass
            self.docked_screens.clear()
            
        # 4. Destroy all child windows (Toplevel dialogs, stream viewers, floating explorers)
        try:
            for child in list(self.winfo_children()):
                if isinstance(child, (ctk.CTkToplevel, tk.Toplevel)):
                    try:
                        child.destroy()
                    except Exception:
                        pass
        except Exception:
            pass
            
        # 5. Clean up temporary clipboard cache files
        self._cleanup_clipboard_cache()

        # 6. Destroy main window
        try:
            super().destroy()
        except Exception:
            pass

    def _cleanup_clipboard_cache(self):
        """Removes all temporary cache files from captures/clipboard_cache on startup and shutdown."""
        try:
            cache_dir = Path(__file__).resolve().parent.parent / "captures" / "clipboard_cache"
            if cache_dir.exists():
                import shutil
                for item in cache_dir.iterdir():
                    try:
                        if item.is_file() or item.is_symlink():
                            item.unlink()
                        elif item.is_dir():
                            shutil.rmtree(item)
                    except Exception:
                        pass
            else:
                cache_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

    def destroy(self):
        self._on_app_close()

