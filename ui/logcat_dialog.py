import os
import sys
import time
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import customtkinter as ctk
from typing import List, Dict, Any, Optional

from core.logcat_manager import LogcatManager
from ui.modern_context_menu import ModernContextMenu

class LogcatDialog(ctk.CTkToplevel):
    """
    Real-time Android Studio-grade Logcat Viewer with multi-layer filtering,
    toggleable timestamp/PID headers, clean copy support, and live color-coding.
    """

    def __init__(self, master, serial: str, model: str = "", adb = None):
        super().__init__(master)
        
        self.serial = serial
        self.model = model or serial
        self.adb = adb
        
        self.title(f"📜 AxeCast Studio - Logcat Viewer [{self.model}] ({self.serial})")
        self.geometry("1120x700")
        self.minsize(820, 480)
        
        self.manager = LogcatManager(self.adb, self.serial)
        
        # In-memory log entries (Ring buffer up to 10,000)
        self.all_entries: List[Dict[str, Any]] = []
        self.filtered_count = 0
        self.error_count = 0
        self.warning_count = 0
        
        # State
        self.is_paused = False
        self.auto_scroll = True
        self.show_timestamp = True
        self.show_pid = True
        self.show_tag = True
        self.current_level = "All"
        self.search_filter = ""
        self.tag_filter = ""
        self.package_filter = ""
        
        self._pending_entries: List[Dict[str, Any]] = []
        self._flush_timer = None
        self.is_destroyed = False
        
        self.font_family = "Consolas" if sys.platform.startswith("win") else "Menlo"
        self.is_dark = ctk.get_appearance_mode() == "Dark"

        self._build_ui()
        self._bind_events()
        
        # Handle clean window close
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        
        # Start streaming fresh logs (clears old buffer)
        self.manager.start(self._on_incoming_log, clear_buffer=True)
        self._schedule_flush()

    def _build_ui(self):
        # 1. Top Control Bar (Filtering & Search)
        top_bar = ctk.CTkFrame(self, fg_color=("#f1f5f9", "#0f172a"), corner_radius=0)
        top_bar.pack(fill="x", side="top", padx=0, pady=0)
        
        row1 = ctk.CTkFrame(top_bar, fg_color="transparent")
        row1.pack(fill="x", padx=12, pady=(10, 4))
        
        # Search Entry
        ctk.CTkLabel(row1, text="🔍", font=ctk.CTkFont(size=14)).pack(side="left", padx=(0, 4))
        self.search_entry = ctk.CTkEntry(row1, placeholder_text="Filter message text...", width=200, height=32)
        self.search_entry.pack(side="left", padx=(0, 8))
        self.search_entry.bind("<KeyRelease>", lambda e: self._on_filter_changed())
        
        # Tag Entry
        ctk.CTkLabel(row1, text="🏷", font=ctk.CTkFont(size=14)).pack(side="left", padx=(0, 4))
        self.tag_entry = ctk.CTkEntry(row1, placeholder_text="Tag...", width=130, height=32)
        self.tag_entry.pack(side="left", padx=(0, 8))
        self.tag_entry.bind("<KeyRelease>", lambda e: self._on_filter_changed())
        
        # Package Selector / Entry
        ctk.CTkLabel(row1, text="📦", font=ctk.CTkFont(size=14)).pack(side="left", padx=(0, 4))
        self.pkg_entry = ctk.CTkEntry(row1, placeholder_text="Package (e.g. com.app)...", width=180, height=32)
        self.pkg_entry.pack(side="left", padx=(0, 4))
        self.pkg_entry.bind("<KeyRelease>", lambda e: self._on_filter_changed())
        
        self.fg_app_btn = ctk.CTkButton(
            row1,
            text="🎯 Active App",
            width=90,
            height=32,
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color=("#7c3aed", "#6d28d9"),
            hover_color=("#6d28d9", "#5b21b6"),
            command=self._detect_foreground_app
        )
        self.fg_app_btn.pack(side="left", padx=(0, 8))
        
        # Level Selector
        ctk.CTkLabel(row1, text="📊", font=ctk.CTkFont(size=14)).pack(side="left", padx=(0, 4))
        self.level_opt = ctk.CTkOptionMenu(
            row1,
            values=["All Levels", "Debug+ (D)", "Info+ (I)", "Warning+ (W)", "Error+ (E)", "Fatal (F)"],
            width=115,
            height=32,
            font=ctk.CTkFont(size=11),
            command=self._on_level_changed
        )
        self.level_opt.set("All Levels")
        self.level_opt.pack(side="left", padx=(0, 8))
        
        # Right Actions in Row 1
        self.pause_btn = ctk.CTkButton(
            row1,
            text="⏸ Pause",
            width=75,
            height=32,
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color=("#334155", "#1e293b"),
            hover_color=("#475569", "#334155"),
            command=self._toggle_pause
        )
        self.pause_btn.pack(side="right", padx=(4, 0))
        
        self.clear_btn = ctk.CTkButton(
            row1,
            text="🧹 Clear",
            width=70,
            height=32,
            font=ctk.CTkFont(size=11),
            fg_color=("#475569", "#334155"),
            hover_color=("#334155", "#1e293b"),
            command=self._clear_logs
        )
        self.clear_btn.pack(side="right", padx=4)

        self.export_btn = ctk.CTkButton(
            row1,
            text="💾 Export",
            width=75,
            height=32,
            font=ctk.CTkFont(size=11),
            fg_color=("#0284c7", "#0369a1"),
            hover_color=("#0369a1", "#075985"),
            command=self._export_logs
        )
        self.export_btn.pack(side="right", padx=4)

        # Row 2: Display Formatting Toggles & Metrics Badges (User-Requested Clean View)
        row2 = ctk.CTkFrame(top_bar, fg_color="transparent")
        row2.pack(fill="x", padx=12, pady=(2, 8))

        # Checkboxes for toggling view details
        self.chk_time_var = tk.BooleanVar(value=True)
        self.chk_time = ctk.CTkCheckBox(
            row2,
            text="📅 Date/Time",
            variable=self.chk_time_var,
            font=ctk.CTkFont(size=11),
            checkbox_width=18,
            checkbox_height=18,
            command=self._on_format_toggled
        )
        self.chk_time.pack(side="left", padx=(0, 12))

        self.chk_tag_var = tk.BooleanVar(value=True)
        self.chk_tag = ctk.CTkCheckBox(
            row2,
            text="🏷 Tag & Level",
            variable=self.chk_tag_var,
            font=ctk.CTkFont(size=11),
            checkbox_width=18,
            checkbox_height=18,
            command=self._on_format_toggled
        )
        self.chk_tag.pack(side="left", padx=(0, 12))

        self.chk_pid_var = tk.BooleanVar(value=False)
        self.chk_pid = ctk.CTkCheckBox(
            row2,
            text="🔢 PID/TID",
            variable=self.chk_pid_var,
            font=ctk.CTkFont(size=11),
            checkbox_width=18,
            checkbox_height=18,
            command=self._on_format_toggled
        )
        self.chk_pid.pack(side="left", padx=(0, 12))

        self.chk_scroll_var = tk.BooleanVar(value=True)
        self.chk_scroll = ctk.CTkCheckBox(
            row2,
            text="📜 Auto-Scroll",
            variable=self.chk_scroll_var,
            font=ctk.CTkFont(size=11),
            checkbox_width=18,
            checkbox_height=18,
            command=self._on_scroll_toggled
        )
        self.chk_scroll.pack(side="left", padx=(0, 12))

        # Metrics Badges
        self.badge_total = ctk.CTkLabel(
            row2,
            text="Total: 0",
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color=("#e2e8f0", "#1e293b"),
            text_color=("#334155", "#94a3b8"),
            corner_radius=4,
            padx=8,
            pady=2
        )
        self.badge_total.pack(side="right", padx=(4, 0))

        self.badge_err = ctk.CTkLabel(
            row2,
            text="🔴 Errors: 0",
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color=("#fee2e2", "#7f1d1d"),
            text_color=("#dc2626", "#fca5a5"),
            corner_radius=4,
            padx=8,
            pady=2
        )
        self.badge_err.pack(side="right", padx=4)

        self.badge_warn = ctk.CTkLabel(
            row2,
            text="🟡 Warn: 0",
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color=("#fef3c7", "#78350f"),
            text_color=("#d97706", "#fcd34d"),
            corner_radius=4,
            padx=8,
            pady=2
        )
        self.badge_warn.pack(side="right", padx=4)

        # 2. Main Log Display
        display_frame = tk.Frame(self, bg="#0f172a" if self.is_dark else "#ffffff")
        display_frame.pack(fill="both", expand=True, padx=2, pady=2)

        self.v_scroll = ttk.Scrollbar(display_frame, orient="vertical")
        self.v_scroll.pack(side="right", fill="y")
        
        self.h_scroll = ttk.Scrollbar(display_frame, orient="horizontal")
        self.h_scroll.pack(side="bottom", fill="x")

        text_bg = "#090d16" if self.is_dark else "#ffffff"
        text_fg = "#f8fafc" if self.is_dark else "#0f172a"

        self.log_text = tk.Text(
            display_frame,
            bg=text_bg,
            fg=text_fg,
            insertbackground=text_fg,
            selectbackground="#0284c7",
            selectforeground="#ffffff",
            font=(self.font_family, 10),
            wrap="none",
            bd=0,
            padx=8,
            pady=6,
            yscrollcommand=self.v_scroll.set,
            xscrollcommand=self.h_scroll.set
        )
        self.log_text.pack(fill="both", expand=True)
        self.v_scroll.config(command=self.log_text.yview)
        self.h_scroll.config(command=self.log_text.xview)

        self._setup_text_tags()
        self._setup_context_menu()

    def _setup_text_tags(self):
        # Color coding for log levels
        self.log_text.tag_config("level_V", foreground="#94a3b8")
        self.log_text.tag_config("level_D", foreground="#38bdf8")
        self.log_text.tag_config("level_I", foreground="#22c55e")
        self.log_text.tag_config("level_W", foreground="#f59e0b")
        self.log_text.tag_config("level_E", foreground="#ef4444", font=(self.font_family, 10, "bold"))
        self.log_text.tag_config("level_F", foreground="#ec4899", font=(self.font_family, 10, "bold"))
        self.log_text.tag_config("ts", foreground="#64748b")
        self.log_text.tag_config("tag", foreground="#a855f7", font=(self.font_family, 10, "bold"))
        self.log_text.tag_config("pid", foreground="#0ea5e9")

    def _setup_context_menu(self):
        self.context_menu = ModernContextMenu(self)
        self.context_menu.add_item(icon="📋", label="Copy Selected (Message Only)", shortcut="Ctrl+C", command=self._copy_selected_clean)
        self.context_menu.add_item(icon="📑", label="Copy Full Lines (with Timestamp)", command=self._copy_selected_full)
        self.context_menu.add_item(icon="🔲", label="Select All", shortcut="Ctrl+A", command=self._select_all)
        self.context_menu.add_separator()
        self.context_menu.add_item(icon="🧹", label="Clear Logs", command=self._clear_logs)

        self.log_text.bind("<Button-3>", self._show_context_menu)
        self.log_text.bind("<Button-2>", self._show_context_menu)
        self.log_text.bind("<Control-c>", lambda e: self._copy_selected_clean())
        self.log_text.bind("<Control-C>", lambda e: self._copy_selected_clean())
        self.log_text.bind("<Command-c>", lambda e: self._copy_selected_clean())
        self.log_text.bind("<Command-C>", lambda e: self._copy_selected_clean())
        self.log_text.bind("<Control-a>", lambda e: self._select_all())
        self.log_text.bind("<Control-A>", lambda e: self._select_all())
        self.log_text.bind("<Command-a>", lambda e: self._select_all())
        self.log_text.bind("<Command-A>", lambda e: self._select_all())

    def _show_context_menu(self, event):
        self.context_menu.show(event.x_root, event.y_root)
        return "break"

    def _bind_events(self):
        self.bind("<F5>", lambda e: self._reapply_filter())
        self.bind("<Control-f>", lambda e: self.search_entry.focus_set())
        self.bind("<Control-F>", lambda e: self.search_entry.focus_set())
        self.bind("<Command-f>", lambda e: self.search_entry.focus_set())
        self.bind("<Command-F>", lambda e: self.search_entry.focus_set())
        self.bind("<Control-l>", lambda e: self._clear_logs())
        self.bind("<Control-L>", lambda e: self._clear_logs())
        self.bind("<Command-l>", lambda e: self._clear_logs())
        self.bind("<Command-L>", lambda e: self._clear_logs())

    def _on_incoming_log(self, entry: Dict[str, Any]):
        """Thread-safe incoming log listener."""
        if self.is_destroyed or self.is_paused:
            return
            
        self._pending_entries.append(entry)
        if len(self._pending_entries) > 2000:
            self._pending_entries = self._pending_entries[-1000:]

    def _schedule_flush(self):
        if self.is_destroyed:
            return
        self._flush_pending_logs()
        self._flush_timer = self.after(80, self._schedule_flush)

    def _flush_pending_logs(self):
        if not self._pending_entries or self.is_destroyed:
            return

        batch = self._pending_entries
        self._pending_entries = []

        # Update metrics and memory buffer
        for entry in batch:
            self.all_entries.append(entry)
            if entry["level"] in ("E", "F"):
                self.error_count += 1
            elif entry["level"] == "W":
                self.warning_count += 1

        # Keep buffer bounded (max 10,000 entries)
        if len(self.all_entries) > 10000:
            self.all_entries = self.all_entries[-8000:]

        self.badge_total.configure(text=f"Total: {len(self.all_entries)}")
        self.badge_err.configure(text=f"🔴 Errors: {self.error_count}")
        self.badge_warn.configure(text=f"🟡 Warn: {self.warning_count}")

        # Render matching lines in batch
        to_render = [e for e in batch if self._matches_filter(e)]
        if to_render:
            self.log_text.config(state="normal")
            for entry in to_render:
                self._append_entry_widget(entry)
            
            if self.chk_scroll_var.get():
                self.log_text.see("end")
            self.log_text.config(state="disabled")

    def _matches_filter(self, entry: Dict[str, Any]) -> bool:
        # 1. Level Filter
        lvl = entry["level"]
        order = {"V": 1, "D": 2, "I": 3, "W": 4, "E": 5, "F": 6}
        entry_rank = order.get(lvl, 1)

        target = self.current_level
        if target == "Debug+ (D)" and entry_rank < 2: return False
        if target == "Info+ (I)" and entry_rank < 3: return False
        if target == "Warning+ (W)" and entry_rank < 4: return False
        if target == "Error+ (E)" and entry_rank < 5: return False
        if target == "Fatal (F)" and entry_rank < 6: return False

        # 2. Tag Filter
        if self.tag_filter and self.tag_filter.lower() not in entry["tag"].lower():
            return False

        # 3. Search Filter
        if self.search_filter and self.search_filter.lower() not in entry["message"].lower():
            return False

        # 4. Package Filter
        if self.package_filter:
            pkg = entry.get("package", "")
            if self.package_filter.lower() not in pkg.lower() and self.package_filter.lower() not in entry["tag"].lower():
                return False

        return True

    def _append_entry_widget(self, entry: Dict[str, Any]):
        lvl = entry["level"]
        level_tag = f"level_{lvl}" if lvl in ("V", "D", "I", "W", "E", "F") else "level_I"

        parts = []
        if self.chk_time_var.get() and entry["timestamp"]:
            self.log_text.insert("end", f"{entry['timestamp']} ", "ts")

        if self.chk_pid_var.get() and entry["pid"]:
            self.log_text.insert("end", f"[{entry['pid']}:{entry['tid']}] ", "pid")

        if self.chk_tag_var.get():
            self.log_text.insert("end", f"{lvl}/{entry['tag']}: ", level_tag)

        self.log_text.insert("end", f"{entry['message']}\n", level_tag)

    def _reapply_filter(self):
        """Full re-render of log buffer with current filter settings."""
        self.search_filter = self.search_entry.get().strip()
        self.tag_filter = self.tag_entry.get().strip()
        self.package_filter = self.pkg_entry.get().strip()
        self.current_level = self.level_opt.get()

        self.log_text.config(state="normal")
        self.log_text.delete("1.0", "end")

        f_total = 0
        f_err = 0
        f_warn = 0

        for entry in self.all_entries:
            if self._matches_filter(entry):
                f_total += 1
                if entry["level"] in ("E", "F"):
                    f_err += 1
                elif entry["level"] == "W":
                    f_warn += 1
                self._append_entry_widget(entry)

        # Dynamic Badge Update based on active filter
        self.badge_total.configure(text=f"Total: {f_total}")
        self.badge_err.configure(text=f"🔴 Errors: {f_err}")
        self.badge_warn.configure(text=f"🟡 Warn: {f_warn}")

        if self.chk_scroll_var.get():
            self.log_text.see("end")
        self.log_text.config(state="disabled")

    def _on_filter_changed(self):
        self._reapply_filter()

    def _on_level_changed(self, choice):
        self.current_level = choice
        self._reapply_filter()

    def _on_format_toggled(self):
        self._reapply_filter()

    def _on_scroll_toggled(self):
        if self.chk_scroll_var.get():
            self.log_text.see("end")

    def _toggle_pause(self):
        self.is_paused = not self.is_paused
        if self.is_paused:
            self.pause_btn.configure(text="▶ Resume", fg_color=("#16a34a", "#15803d"))
        else:
            self.pause_btn.configure(text="⏸ Pause", fg_color=("#334155", "#1e293b"))

    def _clear_logs(self):
        self.all_entries.clear()
        self._pending_entries.clear()
        self.error_count = 0
        self.warning_count = 0
        self.badge_total.configure(text="Total: 0")
        self.badge_err.configure(text="🔴 Errors: 0")
        self.badge_warn.configure(text="🟡 Warn: 0")
        
        self.log_text.config(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.config(state="disabled")

    def _detect_foreground_app(self):
        """Queries the active app package on the phone screen."""
        self.fg_app_btn.configure(text="⏳ Scanning...")
        def worker():
            pkg = self.manager.get_foreground_package()
            self.manager.refresh_package_pids()
            self.after(0, lambda: self._apply_detected_app(pkg))
        threading.Thread(target=worker, daemon=True).start()

    def _apply_detected_app(self, pkg: str):
        self.fg_app_btn.configure(text="🎯 Active App")
        if pkg:
            self.pkg_entry.delete(0, "end")
            self.pkg_entry.insert(0, pkg)
            self._reapply_filter()
        else:
            messagebox.showinfo("Active App Detection", "Could not detect active 3rd party foreground app.", parent=self)

    def _copy_selected_clean(self):
        """Copies selected text directly without timestamps clutter."""
        try:
            sel = self.log_text.get("sel.first", "sel.last")
            if sel:
                self.clipboard_clear()
                self.clipboard_append(sel)
        except Exception:
            pass
        return "break"

    def _copy_selected_full(self):
        """Copies full lines including timestamp and tag."""
        try:
            sel_first = self.log_text.index("sel.first linestart")
            sel_last = self.log_text.index("sel.last lineend")
            sel = self.log_text.get(sel_first, sel_last)
            if sel:
                self.clipboard_clear()
                self.clipboard_append(sel)
        except Exception:
            pass
        return "break"

    def _select_all(self):
        self.log_text.tag_add("sel", "1.0", "end")
        return "break"

    def _export_logs(self):
        """Exports currently displayed logs to file."""
        content = self.log_text.get("1.0", "end-1c")
        if not content.strip():
            messagebox.showwarning("Export Logs", "No logs to export.", parent=self)
            return

        ts_str = time.strftime("%Y%m%d_%H%M%S")
        fn = f"logcat_{self.serial}_{ts_str}.log"
        dest = filedialog.asksaveasfilename(
            parent=self,
            title="Export Logcat to File",
            initialfile=fn,
            defaultextension=".log",
            filetypes=[("Log Files (*.log)", "*.log"), ("Text Files (*.txt)", "*.txt"), ("All Files (*.*)", "*.*")]
        )
        if dest:
            try:
                with open(dest, "w", encoding="utf-8") as f:
                    f.write(content)
                messagebox.showinfo("Export Successful", f"Logs successfully saved to:\n{dest}", parent=self)
            except Exception as e:
                messagebox.showerror("Export Error", f"Failed to save logs:\n{e}", parent=self)

    def _on_close(self):
        """Stops background ADB streaming process cleanly and closes dialog."""
        self.is_destroyed = True
        if self._flush_timer:
            try:
                self.after_cancel(self._flush_timer)
            except Exception:
                pass
        self.manager.stop()
        self.destroy()
