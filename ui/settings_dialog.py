import os
from tkinter import filedialog
import customtkinter as ctk

class SettingsDialog(ctk.CTkToplevel):
    def __init__(self, master, current_settings: dict, on_save=None):
        super().__init__(master)
        self.title("⚙ Mirror & Recording Settings")
        self.geometry("540x580")
        self.resizable(False, False)
        
        self.settings = current_settings.copy()
        self.on_save = on_save
        
        self.transient(master)
        self.grab_set()
        
        self._build_ui()

    def _build_ui(self):
        title = ctk.CTkLabel(self, text="⚙ Stream & Capture Settings", font=ctk.CTkFont(size=18, weight="bold"))
        title.pack(pady=(16, 12))
        
        container = ctk.CTkScrollableFrame(self, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=20, pady=4)
        
        # 1. Video Resolution
        row1 = ctk.CTkFrame(container, fg_color="transparent")
        row1.pack(fill="x", pady=6)
        ctk.CTkLabel(row1, text="Max Resolution:", width=160, anchor="w", font=ctk.CTkFont(weight="bold")).pack(side="left")
        self.res_var = ctk.StringVar(value=self.settings.get("max_size", "1080"))
        res_opts = ["Original", "1920", "1080", "720", "480"]
        ctk.CTkOptionMenu(row1, values=res_opts, variable=self.res_var, width=180).pack(side="right")
        
        # 2. Video Bitrate
        row2 = ctk.CTkFrame(container, fg_color="transparent")
        row2.pack(fill="x", pady=6)
        ctk.CTkLabel(row2, text="Video Bitrate:", width=160, anchor="w", font=ctk.CTkFont(weight="bold")).pack(side="left")
        self.bitrate_var = ctk.StringVar(value=self.settings.get("bitrate", "8M"))
        bitrate_opts = ["16M", "12M", "8M", "4M", "2M"]
        ctk.CTkOptionMenu(row2, values=bitrate_opts, variable=self.bitrate_var, width=180).pack(side="right")
        
        # 3. Max FPS
        row3 = ctk.CTkFrame(container, fg_color="transparent")
        row3.pack(fill="x", pady=6)
        ctk.CTkLabel(row3, text="Max Frame Rate (FPS):", width=160, anchor="w", font=ctk.CTkFont(weight="bold")).pack(side="left")
        self.fps_var = ctk.StringVar(value=self.settings.get("max_fps", "60"))
        fps_opts = ["120", "90", "60", "30"]
        ctk.CTkOptionMenu(row3, values=fps_opts, variable=self.fps_var, width=180).pack(side="right")
        
        # 4. Recording Format
        row4 = ctk.CTkFrame(container, fg_color="transparent")
        row4.pack(fill="x", pady=6)
        ctk.CTkLabel(row4, text="Recording Video Format:", width=160, anchor="w", font=ctk.CTkFont(weight="bold")).pack(side="left")
        self.fmt_var = ctk.StringVar(value=self.settings.get("format", "mp4"))
        fmt_opts = ["mp4", "mkv"]
        ctk.CTkOptionMenu(row4, values=fmt_opts, variable=self.fmt_var, width=180).pack(side="right")

        # Separator
        ctk.CTkFrame(container, height=1, fg_color=("#cbd5e1", "#334155")).pack(fill="x", pady=10)

        # 5. Checkbox Options
        self.always_top_var = ctk.BooleanVar(value=self.settings.get("always_on_top", False))
        ctk.CTkCheckBox(container, text="Always on Top (Keep window in front)", variable=self.always_top_var).pack(anchor="w", pady=4)
        
        self.screen_off_var = ctk.BooleanVar(value=self.settings.get("turn_screen_off", False))
        ctk.CTkCheckBox(container, text="Turn Phone Screen Off during Mirror (Saves Battery)", variable=self.screen_off_var).pack(anchor="w", pady=4)
        
        self.stay_awake_var = ctk.BooleanVar(value=self.settings.get("stay_awake", True))
        ctk.CTkCheckBox(container, text="Stay Awake (Prevent device from sleeping)", variable=self.stay_awake_var).pack(anchor="w", pady=4)
        
        self.audio_var = ctk.BooleanVar(value=self.settings.get("audio", True))
        ctk.CTkCheckBox(container, text="Forward Audio to PC Speakers (Android 11+)", variable=self.audio_var).pack(anchor="w", pady=4)

        # Separator
        ctk.CTkFrame(container, height=1, fg_color=("#cbd5e1", "#334155")).pack(fill="x", pady=10)

        # 6. Save Directory
        row_dir = ctk.CTkFrame(container, fg_color="transparent")
        row_dir.pack(fill="x", pady=4)
        ctk.CTkLabel(row_dir, text="Captures Save Directory:", font=ctk.CTkFont(weight="bold")).pack(anchor="w", pady=(0, 4))
        
        dir_input = ctk.CTkFrame(row_dir, fg_color="transparent")
        dir_input.pack(fill="x")
        self.save_dir_entry = ctk.CTkEntry(dir_input, height=32)
        self.save_dir_entry.insert(0, self.settings.get("save_dir", "captures"))
        self.save_dir_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        
        ctk.CTkButton(dir_input, text="Browse...", width=80, height=32, command=self._browse_dir).pack(side="right")

        # Separator
        ctk.CTkFrame(container, height=1, fg_color=("#cbd5e1", "#334155")).pack(fill="x", pady=10)

        # 7. Updates & Version Section
        upd_box = ctk.CTkFrame(container, fg_color=("#f1f5f9", "#090d16"), corner_radius=8)
        upd_box.pack(fill="x", pady=4)
        
        upd_inner = ctk.CTkFrame(upd_box, fg_color="transparent")
        upd_inner.pack(fill="both", expand=True, padx=12, pady=10)
        
        upd_left = ctk.CTkFrame(upd_inner, fg_color="transparent")
        upd_left.pack(side="left", fill="both", expand=True)
        
        from core.updater import CURRENT_VERSION
        ctk.CTkLabel(
            upd_left,
            text=f"AxeCast Studio v{CURRENT_VERSION}",
            font=ctk.CTkFont(size=12, weight="bold")
        ).pack(anchor="w")
        
        self.update_status_lbl = ctk.CTkLabel(
            upd_left,
            text="Check for software updates from GitHub",
            font=ctk.CTkFont(size=11),
            text_color=("#64748b", "#94a3b8")
        )
        self.update_status_lbl.pack(anchor="w")
        
        self.check_update_btn = ctk.CTkButton(
            upd_inner,
            text="🔄 Check Updates",
            width=130,
            height=30,
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color=("#0284c7", "#0369a1"),
            command=self._on_manual_check_update
        )
        self.check_update_btn.pack(side="right", padx=(6, 0))

        # Bottom Buttons
        btn_bar = ctk.CTkFrame(self, height=50, fg_color="transparent")
        btn_bar.pack(fill="x", side="bottom", padx=20, pady=12)
        
        ctk.CTkButton(
            btn_bar, text="Save Settings", height=36, font=ctk.CTkFont(weight="bold"),
            fg_color=("#16a34a", "#15803d"), command=self._save
        ).pack(side="right", padx=4)
        
        ctk.CTkButton(
            btn_bar, text="Cancel", height=36, fg_color=("#475569", "#334155"), command=self.destroy
        ).pack(side="right", padx=4)

    def _on_manual_check_update(self):
        self.check_update_btn.configure(state="disabled", text="Checking...")
        self.update_status_lbl.configure(text="Connecting to GitHub...", text_color="#38bdf8")
        
        from core.updater import check_for_updates_async
        check_for_updates_async(callback=self._on_update_result)
        
    def _on_update_result(self, res: dict):
        def ui_callback():
            if not self.winfo_exists():
                return
            self.check_update_btn.configure(state="normal", text="🔄 Check Updates")
            if res.get("has_update"):
                self.update_status_lbl.configure(
                    text=f"🎉 New version v{res.get('latest_version')} available!",
                    text_color="#10b981"
                )
                from ui.update_dialog import UpdateDialog
                UpdateDialog(self.master, res)
            elif res.get("success"):
                self.update_status_lbl.configure(
                    text="✅ You are running the latest version!",
                    text_color="#10b981"
                )
            else:
                err = res.get("error", "Failed to reach GitHub")
                self.update_status_lbl.configure(
                    text=f"ℹ️ {err}",
                    text_color="#94a3b8"
                )
        self.after(0, ui_callback)

    def _browse_dir(self):
        chosen = filedialog.askdirectory(initialdir=self.save_dir_entry.get())
        if chosen:
            self.save_dir_entry.delete(0, "end")
            self.save_dir_entry.insert(0, chosen)

    def _save(self):
        new_settings = {
            "max_size": self.res_var.get(),
            "bitrate": self.bitrate_var.get(),
            "max_fps": self.fps_var.get(),
            "format": self.fmt_var.get(),
            "always_on_top": self.always_top_var.get(),
            "turn_screen_off": self.screen_off_var.get(),
            "stay_awake": self.stay_awake_var.get(),
            "audio": self.audio_var.get(),
            "save_dir": self.save_dir_entry.get().strip() or "captures"
        }
        if self.on_save:
            self.on_save(new_settings)
        self.destroy()
