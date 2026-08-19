import sys
import time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import customtkinter as ctk
from typing import Dict, Any, List

from core.studio_logger import logger
from ui.modern_context_menu import ModernContextMenu

class StudioLogDialog(ctk.CTkToplevel):
    """
    Main Application Diagnostics & Studio Event Log Viewer.
    Displays internal GUI operations, ADB daemon status, casting engine events, and error traces.
    """

    def __init__(self, master):
        super().__init__(master)
        
        self.title("📜 AxeCast Studio - Application System Logs & Diagnostics")
        self.geometry("960x620")
        self.minsize(720, 420)
        
        self.font_family = "Consolas" if sys.platform.startswith("win") else "Menlo"
        self.is_dark = ctk.get_appearance_mode() == "Dark"
        
        self.search_filter = ""
        self.level_filter = "All"
        self.auto_scroll = True
        
        self.error_count = 0
        self.warn_count = 0
        self.is_destroyed = False
        
        self._build_ui()
        self._load_existing_logs()
        
        # Subscribe to new incoming logs
        logger.subscribe(self._on_new_log)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self):
        # 1. Top Control Bar
        top_bar = ctk.CTkFrame(self, fg_color=("#f1f5f9", "#0f172a"), corner_radius=0)
        top_bar.pack(fill="x", side="top", padx=0, pady=0)
        
        row1 = ctk.CTkFrame(top_bar, fg_color="transparent")
        row1.pack(fill="x", padx=12, pady=(10, 6))
        
        # Search Entry
        ctk.CTkLabel(row1, text="🔍", font=ctk.CTkFont(size=14)).pack(side="left", padx=(0, 4))
        self.search_entry = ctk.CTkEntry(row1, placeholder_text="Search studio logs...", width=240, height=32)
        self.search_entry.pack(side="left", padx=(0, 10))
        self.search_entry.bind("<KeyRelease>", lambda e: self._reapply_filter())
        
        # Level Option
        ctk.CTkLabel(row1, text="📊", font=ctk.CTkFont(size=14)).pack(side="left", padx=(0, 4))
        self.level_opt = ctk.CTkOptionMenu(
            row1,
            values=["All", "Info", "Warning", "Error", "Success"],
            width=110,
            height=32,
            font=ctk.CTkFont(size=11),
            command=lambda v: self._reapply_filter()
        )
        self.level_opt.set("All")
        self.level_opt.pack(side="left", padx=(0, 10))
        
        # Auto-Scroll Checkbox
        self.chk_scroll_var = tk.BooleanVar(value=True)
        self.chk_scroll = ctk.CTkCheckBox(
            row1,
            text="📜 Auto-Scroll",
            variable=self.chk_scroll_var,
            font=ctk.CTkFont(size=11),
            checkbox_width=18,
            checkbox_height=18
        )
        self.chk_scroll.pack(side="left", padx=6)
        
        # Right Actions
        self.export_btn = ctk.CTkButton(
            row1,
            text="💾 Export",
            width=75,
            height=32,
            font=ctk.CTkFont(size=11),
            fg_color=("#0284c7", "#0369a1"),
            command=self._export_logs
        )
        self.export_btn.pack(side="right", padx=(4, 0))

        self.clear_btn = ctk.CTkButton(
            row1,
            text="🧹 Clear",
            width=70,
            height=32,
            font=ctk.CTkFont(size=11),
            fg_color=("#475569", "#334155"),
            command=self._clear_logs
        )
        self.clear_btn.pack(side="right", padx=4)

        # Row 2: Badges
        row2 = ctk.CTkFrame(top_bar, fg_color="transparent")
        row2.pack(fill="x", padx=12, pady=(0, 8))
        
        ctk.CTkLabel(row2, text="🖥 Application Engine & Diagnostic Console", font=ctk.CTkFont(size=11), text_color=("#64748b", "#94a3b8")).pack(side="left")
        
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

        # 2. Main Log Display Area
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

        # Tags
        self.log_text.tag_config("lvl_INFO", foreground="#38bdf8")
        self.log_text.tag_config("lvl_WARN", foreground="#f59e0b", font=(self.font_family, 10, "bold"))
        self.log_text.tag_config("lvl_ERROR", foreground="#ef4444", font=(self.font_family, 10, "bold"))
        self.log_text.tag_config("lvl_SUCCESS", foreground="#22c55e", font=(self.font_family, 10, "bold"))
        self.log_text.tag_config("ts", foreground="#64748b")
        self.log_text.tag_config("tag", foreground="#a855f7")

        self._setup_context_menu()

    def _setup_context_menu(self):
        self.context_menu = ModernContextMenu(self)
        self.context_menu.add_item(icon="📋", label="Copy Selected", shortcut="Ctrl+C", command=self._copy_selected)
        self.context_menu.add_item(icon="🔲", label="Select All", shortcut="Ctrl+A", command=self._select_all)
        self.context_menu.add_separator()
        self.context_menu.add_item(icon="🧹", label="Clear Logs", command=self._clear_logs)

        self.log_text.bind("<Button-3>", lambda e: self.context_menu.show(e.x_root, e.y_root))
        self.log_text.bind("<Button-2>", lambda e: self.context_menu.show(e.x_root, e.y_root))
        self.log_text.bind("<Control-c>", lambda e: self._copy_selected())
        self.log_text.bind("<Command-c>", lambda e: self._copy_selected())
        self.log_text.bind("<Control-a>", lambda e: self._select_all())
        self.log_text.bind("<Command-a>", lambda e: self._select_all())

    def _load_existing_logs(self):
        self._reapply_filter()

    def _on_new_log(self, entry: Dict[str, Any]):
        if self.is_destroyed:
            return
        self.after(0, lambda: self._append_single_log(entry))

    def _matches_filter(self, entry: Dict[str, Any]) -> bool:
        lvl = entry["level"]
        target_lvl = self.level_opt.get().upper()
        if target_lvl == "WARNING": target_lvl = "WARN"
        
        if target_lvl != "ALL" and lvl != target_lvl:
            return False
            
        q = self.search_entry.get().strip().lower()
        if q:
            full_text = f"{entry['tag']} {entry['message']}".lower()
            if q not in full_text:
                return False
                
        return True

    def _append_single_log(self, entry: Dict[str, Any]):
        if not self._matches_filter(entry):
            return
            
        self.log_text.config(state="normal")
        self._insert_entry(entry)
        if self.chk_scroll_var.get():
            self.log_text.see("end")
        self.log_text.config(state="disabled")
        self._update_badges()

    def _insert_entry(self, entry: Dict[str, Any]):
        lvl = entry["level"]
        tag_style = f"lvl_{lvl}"
        self.log_text.insert("end", f"{entry['timestamp']} ", "ts")
        self.log_text.insert("end", f"[{entry['level']}] ", tag_style)
        self.log_text.insert("end", f"[{entry['tag']}] ", "tag")
        self.log_text.insert("end", f"{entry['message']}\n", tag_style)

    def _reapply_filter(self):
        self.log_text.config(state="normal")
        self.log_text.delete("1.0", "end")
        
        all_logs = logger.get_all_logs()
        for entry in all_logs:
            if self._matches_filter(entry):
                self._insert_entry(entry)
                
        if self.chk_scroll_var.get():
            self.log_text.see("end")
        self.log_text.config(state="disabled")
        self._update_badges()

    def _update_badges(self):
        all_logs = logger.get_all_logs()
        total = len(all_logs)
        errors = sum(1 for l in all_logs if l["level"] == "ERROR")
        warns = sum(1 for l in all_logs if l["level"] == "WARN")
        
        self.badge_total.configure(text=f"Total: {total}")
        self.badge_err.configure(text=f"🔴 Errors: {errors}")
        self.badge_warn.configure(text=f"🟡 Warn: {warns}")

    def _copy_selected(self):
        try:
            sel = self.log_text.get("sel.first", "sel.last")
            if sel:
                self.clipboard_clear()
                self.clipboard_append(sel)
        except Exception:
            pass
        return "break"

    def _select_all(self):
        self.log_text.tag_add("sel", "1.0", "end")
        return "break"

    def _clear_logs(self):
        logger.clear()
        self._reapply_filter()

    def _export_logs(self):
        content = self.log_text.get("1.0", "end-1c")
        if not content.strip():
            messagebox.showwarning("Export Logs", "No logs to export.", parent=self)
            return

        ts_str = time.strftime("%Y%m%d_%H%M%S")
        fn = f"axecast_studio_log_{ts_str}.log"
        dest = filedialog.asksaveasfilename(
            parent=self,
            title="Export Studio Logs to File",
            initialfile=fn,
            defaultextension=".log",
            filetypes=[("Log Files (*.log)", "*.log"), ("Text Files (*.txt)", "*.txt"), ("All Files (*.*)", "*.*")]
        )
        if dest:
            try:
                with open(dest, "w", encoding="utf-8") as f:
                    f.write(content)
                messagebox.showinfo("Export Successful", f"Studio logs saved to:\n{dest}", parent=self)
            except Exception as e:
                messagebox.showerror("Export Error", f"Failed to save logs:\n{e}", parent=self)

    def _on_close(self):
        self.is_destroyed = True
        logger.unsubscribe(self._on_new_log)
        self.destroy()
