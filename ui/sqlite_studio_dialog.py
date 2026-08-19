import os
import re
import sys
import time
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import customtkinter as ctk

from core.sqlite_engine import SQLiteEngine, QueryResult
from core.file_manager import DeviceFileManager
from ui.sql_editor_widget import SQLEditorWidget

class SQLiteStudioDialog(ctk.CTkToplevel):
    """Modern Lightweight SQLite Studio with Multi-Tabs, Auto-complete, Metrics & 2-Way Phone Sync."""

    def __init__(self, master, db_path: str = None, serial: str = None, model_name: str = "Device", remote_path: str = None, initial_sql: str = None, on_saved=None):
        super().__init__(master)
        
        self.db_path = db_path
        self.serial = serial
        self.model_name = model_name
        self.remote_path = remote_path
        self.initial_sql = initial_sql
        self.on_saved = on_saved
        
        self.engine = SQLiteEngine()
        self.fm = DeviceFileManager()
        self.tab_count = 0
        self.tabs = {}  # tab_id -> dict of widgets and data
        self.query_history = []
        
        # Setup Window
        title_prefix = f"📱 {model_name}: " if remote_path else "💻 "
        db_title = os.path.basename(remote_path or db_path or "New Database")
        self.title(f"🗄 AxeSQL Studio - {title_prefix}{db_title}")
        self.geometry("1180x760")
        self.minsize(900, 560)
        
        self._setup_theme()
        self._build_top_toolbar()
        self._build_main_workspace()
        self._setup_shortcuts()
        
        # Open initial database if provided
        if self.db_path and os.path.exists(self.db_path):
            self.load_database(self.db_path)
        else:
            self._create_new_tab("SQL Editor 1", self.initial_sql or "SELECT 'Welcome to AxeSQL Studio 🪓!' AS Message, datetime('now') AS CurrentTime;")

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _setup_theme(self):
        is_dark = ctk.get_appearance_mode() == "Dark"
        self.configure(fg_color=("#f1f5f9", "#0b0f19"))
        self.font_family = "SF Pro Text" if sys.platform == "darwin" else ("Segoe UI" if sys.platform.startswith("win") else "Ubuntu")
        
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass

        # Dynamic Theme Colors
        if is_dark:
            tree_bg = "#0f172a"
            tree_fg = "#f8fafc"
            hdr_bg = "#1e293b"
            hdr_fg = "#38bdf8"
            sel_bg = "#0284c7"
            tab_bg = "#1e293b"
            tab_fg = "#94a3b8"
        else:
            tree_bg = "#ffffff"
            tree_fg = "#0f172a"
            hdr_bg = "#e2e8f0"
            hdr_fg = "#0369a1"
            sel_bg = "#0284c7"
            tab_bg = "#e2e8f0"
            tab_fg = "#475569"

        # Treeview (Data Grid, Schema Tree & History)
        style.configure(
            "SqlStudio.Treeview",
            background=tree_bg,
            foreground=tree_fg,
            fieldbackground=tree_bg,
            rowheight=26,
            font=(self.font_family, 10),
            borderwidth=0
        )
        style.map(
            "SqlStudio.Treeview",
            background=[("selected", sel_bg)],
            foreground=[("selected", "#ffffff")]
        )
        style.configure(
            "SqlStudio.Treeview.Heading",
            background=hdr_bg,
            foreground=hdr_fg,
            font=(self.font_family, 10, "bold"),
            relief="flat",
            padding=5
        )
        style.map(
            "SqlStudio.Treeview.Heading",
            background=[("active", "#0284c7" if not is_dark else "#334155")],
            foreground=[("active", "#ffffff")]
        )

        # Notebook tabs (Data Grid / History / Structure)
        style.configure(
            "SqlStudio.TNotebook",
            background=tree_bg,
            borderwidth=0
        )
        style.configure(
            "SqlStudio.TNotebook.Tab",
            background=tab_bg,
            foreground=tab_fg,
            font=(self.font_family, 9, "bold"),
            padding=[10, 4],
            borderwidth=0
        )
        style.map(
            "SqlStudio.TNotebook.Tab",
            background=[("selected", sel_bg), ("active", "#93c5fd" if not is_dark else "#334155")],
            foreground=[("selected", "#ffffff"), ("active", "#0f172a" if not is_dark else "#f8fafc")]
        )

    def apply_theme(self):
        """Updates all SQLite Studio components when theme toggles."""
        self._setup_theme()
        is_dark = ctk.get_appearance_mode() == "Dark"
        bg_col = "#0f172a" if is_dark else "#ffffff"
        pane_bg = "#0f172a" if is_dark else "#f1f5f9"
        bar_bg = "#0f172a" if is_dark else "#e2e8f0"
        
        if hasattr(self, "paned"):
            self.paned.config(bg=pane_bg)
        if hasattr(self, "tab_buttons_container"):
            self.tab_buttons_container.config(bg=bar_bg)
        if hasattr(self, "tab_pages_container"):
            self.tab_pages_container.config(bg=pane_bg)
        if hasattr(self, "theme_btn"):
            self.theme_btn.configure(text="☀ Theme" if not is_dark else "🌙 Theme")

        for tab_id, data in self.tabs.items():
            if "editor" in data:
                data["editor"].apply_theme()
            if "struct_text" in data:
                data["struct_text"].config(
                    bg=bg_col,
                    fg="#f8fafc" if is_dark else "#0f172a"
                )
            if "frame" in data:
                data["frame"].config(bg=pane_bg)
            if "button_frame" in data:
                is_active = (getattr(self, "active_tab_id", None) == tab_id)
                btn_bg = "#0284c7" if is_active else ("#1e293b" if is_dark else "#cbd5e1")
                btn_fg = "#ffffff" if is_active else ("#cbd5e1" if is_dark else "#334155")
                data["button_frame"].config(bg=btn_bg)
                data["button_label"].config(bg=btn_bg, fg=btn_fg)

    def _toggle_theme(self):
        current = ctk.get_appearance_mode()
        if current == "Dark":
            ctk.set_appearance_mode("Light")
        else:
            ctk.set_appearance_mode("Dark")
        self.apply_theme()

    def _build_top_toolbar(self):
        self.toolbar = ctk.CTkFrame(self, height=44, corner_radius=0, fg_color=("#e2e8f0", "#1e293b"))
        self.toolbar.pack(side="top", fill="x", padx=0, pady=0)
        
        # 1. Open Button
        self.open_btn = ctk.CTkButton(
            self.toolbar, text="📂 Open File...", width=100, height=30,
            fg_color=("#0284c7", "#0369a1"), hover_color=("#0369a1", "#075985"),
            command=self._choose_and_open_file
        )
        self.open_btn.pack(side="left", padx=(8, 4), pady=7)

        # 2. Save & Sync to Device (only active if remote_path is present)
        if self.remote_path and self.serial:
            self.sync_btn = ctk.CTkButton(
                self.toolbar, text="💾 Save & Sync to Phone", width=160, height=30,
                fg_color=("#16a34a", "#15803d"), hover_color=("#15803d", "#166534"),
                command=self._sync_to_phone
            )
            self.sync_btn.pack(side="left", padx=4, pady=7)

        # 3. Run Query
        self.run_btn = ctk.CTkButton(
            self.toolbar, text="▶ Run (F5)", width=95, height=30,
            fg_color=("#2563eb", "#1d4ed8"), hover_color=("#1d4ed8", "#1e40af"),
            font=(self.font_family, 12, "bold"),
            command=self._run_current_tab_query
        )
        self.run_btn.pack(side="left", padx=4, pady=7)

        # 4. Cancel Query
        self.cancel_btn = ctk.CTkButton(
            self.toolbar, text="🛑 Stop", width=70, height=30,
            fg_color=("#dc2626", "#b91c1c"), hover_color=("#b91c1c", "#991b1b"),
            state="disabled",
            command=self._cancel_query
        )
        self.cancel_btn.pack(side="left", padx=4, pady=7)

        # 5. New Tab
        self.new_tab_btn = ctk.CTkButton(
            self.toolbar, text="📑 New Tab (+)", width=105, height=30,
            fg_color=("#475569", "#334155"), hover_color=("#334155", "#1e293b"),
            command=lambda: self._create_new_tab()
        )
        self.new_tab_btn.pack(side="left", padx=4, pady=7)

        # 6. Export Menu
        self.export_btn = ctk.CTkButton(
            self.toolbar, text="📤 Export", width=85, height=30,
            fg_color=("#475569", "#334155"), hover_color=("#334155", "#1e293b"),
            command=self._export_current_results
        )
        self.export_btn.pack(side="left", padx=4, pady=7)

        # 7. Format SQL
        self.format_btn = ctk.CTkButton(
            self.toolbar, text="🧹 Format", width=80, height=30,
            fg_color=("#475569", "#334155"), hover_color=("#334155", "#1e293b"),
            command=self._format_sql
        )
        self.format_btn.pack(side="left", padx=4, pady=7)

        # 8. Refresh Schema Button
        self.refresh_btn = ctk.CTkButton(
            self.toolbar, text="🔄 Refresh", width=85, height=30,
            fg_color=("#475569", "#334155"), hover_color=("#334155", "#1e293b"),
            command=self.refresh_schema
        )
        self.refresh_btn.pack(side="left", padx=4, pady=7)

        # Right side: Theme button + DB Name Label
        is_dark = ctk.get_appearance_mode() == "Dark"
        self.theme_btn = ctk.CTkButton(
            self.toolbar,
            text="🌙 Theme" if is_dark else "☀ Theme",
            width=75,
            height=30,
            font=ctk.CTkFont(size=11),
            fg_color=("#334155", "#1e293b"),
            hover_color=("#475569", "#334155"),
            command=self._toggle_theme
        )
        self.theme_btn.pack(side="right", padx=(4, 10), pady=7)

        self.db_label = ctk.CTkLabel(
            self.toolbar, 
            text=f"📁 {os.path.basename(self.remote_path or self.db_path or 'No DB')}",
            font=(self.font_family, 11),
            text_color="#94a3b8"
        )
        self.db_label.pack(side="right", padx=6, pady=7)

    def _build_main_workspace(self):
        # PanedWindow: Left Sidebar + Right Workspace
        self.paned = tk.PanedWindow(self, orient="horizontal", bg="#0f172a", sashwidth=4, bd=0)
        self.paned.pack(fill="both", expand=True, padx=4, pady=4)

        # ─── LEFT SIDEBAR: SCHEMA & TABLES ───
        self.sidebar_frame = ctk.CTkFrame(self.paned, width=240, corner_radius=6, fg_color=("#f8fafc", "#0f172a"))
        self.paned.add(self.sidebar_frame, minsize=180)

        # Search / Filter Box with Reload button
        filter_box = ctk.CTkFrame(self.sidebar_frame, fg_color="transparent")
        filter_box.pack(fill="x", padx=6, pady=(6, 4))

        self.filter_var = tk.StringVar()
        self.filter_var.trace("w", lambda *args: self._filter_schema_tree())
        self.filter_entry = ctk.CTkEntry(
            filter_box, 
            placeholder_text="🔍 Filter by name...",
            textvariable=self.filter_var,
            height=28,
            font=(self.font_family, 11)
        )
        self.filter_entry.pack(side="left", fill="x", expand=True, padx=(0, 4))

        self.side_refresh_btn = ctk.CTkButton(
            filter_box,
            text="🔄",
            width=28,
            height=28,
            font=(self.font_family, 12),
            fg_color=("#334155", "#1e293b"),
            hover_color=("#475569", "#334155"),
            command=self.refresh_schema
        )
        self.side_refresh_btn.pack(side="right")

        # Treeview for Tables & Schema
        tree_container = tk.Frame(self.sidebar_frame, bg="#0f172a")
        tree_container.pack(fill="both", expand=True, padx=4, pady=4)

        self.schema_tree = ttk.Treeview(tree_container, selectmode="browse", show="tree", style="SqlStudio.Treeview")
        self.schema_tree.pack(side="left", fill="both", expand=True)

        schema_scroll = ttk.Scrollbar(tree_container, orient="vertical", command=self.schema_tree.yview)
        schema_scroll.pack(side="right", fill="y")
        self.schema_tree.configure(yscrollcommand=schema_scroll.set)

        self.schema_tree.bind("<Double-1>", self._on_schema_item_double_click)
        self.schema_tree.bind("<Button-3>", self._on_schema_context_menu)

        # ─── RIGHT WORKSPACE: MULTI-TAB NOTEBOOK ───
        self.workspace_frame = ctk.CTkFrame(self.paned, corner_radius=6, fg_color=("#f8fafc", "#0f172a"))
        self.paned.add(self.workspace_frame, minsize=450)

        # Tab Navigation Bar
        self.tab_bar = ctk.CTkFrame(self.workspace_frame, height=32, corner_radius=0, fg_color=("#1e293b", "#0f172a"))
        self.tab_bar.pack(side="top", fill="x", padx=2, pady=(2, 0))

        self.tab_buttons_container = tk.Frame(self.tab_bar, bg="#0f172a")
        self.tab_buttons_container.pack(side="left", fill="y")

        # Container for tab pages
        self.tab_pages_container = tk.Frame(self.workspace_frame, bg="#0f172a")
        self.tab_pages_container.pack(side="top", fill="both", expand=True)

        # Global Bottom Status Bar
        self.status_bar = ctk.CTkFrame(self.workspace_frame, height=26, corner_radius=0, fg_color=("#1e293b", "#0f172a"))
        self.status_bar.pack(side="bottom", fill="x")

        self.status_time_lbl = ctk.CTkLabel(self.status_bar, text="⏱ Ready", font=(self.font_family, 11, "bold"), text_color="#38bdf8")
        self.status_time_lbl.pack(side="left", padx=8)

        self.status_metric_lbl = ctk.CTkLabel(self.status_bar, text="", font=(self.font_family, 11), text_color="#94a3b8")
        self.status_metric_lbl.pack(side="left", padx=8)

        self.status_thread_lbl = ctk.CTkLabel(self.status_bar, text="", font=(self.font_family, 11), text_color="#a855f7")
        self.status_thread_lbl.pack(side="right", padx=8)

    def _setup_shortcuts(self):
        self.bind("<F5>", lambda e: self._run_current_tab_query())
        self.bind("<Control-Return>", lambda e: self._run_current_tab_query())
        self.bind("<Control-r>", lambda e: self.refresh_schema())
        self.bind("<Control-R>", lambda e: self.refresh_schema())
        self.bind("<Control-Shift-f>", lambda e: self._format_sql())
        self.bind("<Control-Shift-F>", lambda e: self._format_sql())
        self.bind("<Alt-Shift-f>", lambda e: self._format_sql())
        self.bind("<Alt-Shift-F>", lambda e: self._format_sql())
        self.bind("<Control-t>", lambda e: self._create_new_tab())
        self.bind("<Control-w>", lambda e: self._close_current_tab())

    def _create_new_tab(self, title: str = None, initial_sql: str = ""):
        self.tab_count += 1
        tab_id = f"tab_{self.tab_count}"
        tab_title = title or f"SQL Editor {self.tab_count}"

        # 1. Tab Content Frame
        tab_frame = tk.PanedWindow(self.tab_pages_container, orient="vertical", bg="#0f172a", sashwidth=4, bd=0)

        # Top: SQL Editor
        editor = SQLEditorWidget(
            tab_frame,
            on_execute=lambda sql: self._execute_sql(sql, tab_id),
            on_format=self._format_sql,
            on_save=self._sync_to_phone if (self.remote_path and self.serial) else None,
            on_refresh=self.refresh_schema,
            on_new_tab=lambda: self._create_new_tab(),
            on_close_tab=lambda: self._close_current_tab()
        )
        if initial_sql:
            editor.set_text(initial_sql)
        tab_frame.add(editor, minsize=90, height=160)

        # Bottom: Results View (Notebook with Data Grid, History, Structure)
        results_container = tk.Frame(tab_frame, bg="#0f172a")
        tab_frame.add(results_container, minsize=220)

        # Results Notebook
        res_notebook = ttk.Notebook(results_container, style="SqlStudio.TNotebook")
        res_notebook.pack(fill="both", expand=True)

        # Sub-tab 1: Data Grid
        grid_frame = tk.Frame(res_notebook, bg="#0f172a")
        res_notebook.add(grid_frame, text=" 📊 Data Grid ")

        grid_tree_frame = tk.Frame(grid_frame, bg="#0f172a")
        grid_tree_frame.pack(fill="both", expand=True)

        tree = ttk.Treeview(grid_tree_frame, selectmode="extended", show="headings", style="SqlStudio.Treeview")
        tree.pack(side="left", fill="both", expand=True)

        # Setup in-place cell editing, right-click context menu, and Ctrl+C copy
        self._setup_grid_events(tree, tab_id)

        tree_vscroll = ttk.Scrollbar(grid_tree_frame, orient="vertical", command=tree.yview)
        tree_vscroll.pack(side="right", fill="y")
        tree_hscroll = ttk.Scrollbar(grid_frame, orient="horizontal", command=tree.xview)
        tree_hscroll.pack(side="bottom", fill="x")
        tree.configure(yscrollcommand=tree_vscroll.set, xscrollcommand=tree_hscroll.set)

        # Pagination & Controls Bar
        page_bar = tk.Frame(grid_frame, bg="#1e293b", height=28)
        page_bar.pack(side="bottom", fill="x")

        page_lbl = tk.Label(page_bar, text="Page 1 / 1 (0 rows)", bg="#1e293b", fg="#94a3b8", font=(self.font_family, 10))
        page_lbl.pack(side="left", padx=8)

        # Sub-tab 2: History
        hist_frame = tk.Frame(res_notebook, bg="#0f172a")
        res_notebook.add(hist_frame, text=" 🕒 History ")
        hist_tree = ttk.Treeview(hist_frame, columns=("time", "query", "duration", "rows", "status"), show="headings", style="SqlStudio.Treeview")
        for col, width in (("time", 90), ("query", 350), ("duration", 90), ("rows", 70), ("status", 120)):
            hist_tree.heading(col, text=col.capitalize())
            hist_tree.column(col, width=width)
        hist_tree.pack(fill="both", expand=True)

        # Sub-tab 3: Structure / DDL
        struct_frame = tk.Frame(res_notebook, bg="#0f172a")
        res_notebook.add(struct_frame, text=" 📐 Structure ")
        struct_text = tk.Text(struct_frame, bg="#0f172a", fg="#f8fafc", font=("Consolas", 10), wrap="none", padx=8, pady=6)
        struct_text.pack(fill="both", expand=True)

        # Store tab info
        self.tabs[tab_id] = {
            "title": tab_title,
            "frame": tab_frame,
            "editor": editor,
            "res_notebook": res_notebook,
            "tree": tree,
            "page_lbl": page_lbl,
            "hist_tree": hist_tree,
            "struct_text": struct_text,
            "last_result": None,
            "button_frame": None
        }

        # Update vocabulary for editor if schema exists
        if hasattr(self, "current_schema"):
            editor.update_schema_symbols(self.current_schema)

        # Build tab header button
        self._build_tab_button(tab_id, tab_title)
        self._switch_to_tab(tab_id)
        return tab_id

    def _build_tab_button(self, tab_id: str, title: str):
        btn_frame = tk.Frame(self.tab_buttons_container, bg="#1e293b", padx=6, pady=2)
        btn_frame.pack(side="left", padx=2)

        lbl = tk.Label(btn_frame, text=f" 📋 {title} ", bg="#1e293b", fg="#cbd5e1", font=(self.font_family, 10, "bold"), cursor="hand2")
        lbl.pack(side="left")
        lbl.bind("<Button-1>", lambda e: self._switch_to_tab(tab_id))

        close_lbl = tk.Label(btn_frame, text=" × ", bg="#1e293b", fg="#94a3b8", font=(self.font_family, 11, "bold"), cursor="hand2")
        close_lbl.pack(side="left")
        close_lbl.bind("<Button-1>", lambda e: self._close_tab(tab_id))
        close_lbl.bind("<Enter>", lambda e: close_lbl.config(fg="#ef4444"))
        close_lbl.bind("<Leave>", lambda e: close_lbl.config(fg="#94a3b8"))

        self.tabs[tab_id]["button_frame"] = btn_frame
        self.tabs[tab_id]["button_label"] = lbl

    def _switch_to_tab(self, tab_id: str):
        if tab_id not in self.tabs:
            return
        self.active_tab_id = tab_id
        for t_id, data in self.tabs.items():
            if t_id == tab_id:
                data["frame"].pack(fill="both", expand=True)
                data["button_frame"].config(bg="#0284c7")
                data["button_label"].config(bg="#0284c7", fg="#ffffff")
                data["editor"].text.focus_set()
            else:
                data["frame"].pack_forget()
                data["button_frame"].config(bg="#1e293b")
                data["button_label"].config(bg="#1e293b", fg="#cbd5e1")

    def _close_tab(self, tab_id: str):
        if len(self.tabs) <= 1:
            return  # Keep at least one tab
        if tab_id in self.tabs:
            self.tabs[tab_id]["frame"].destroy()
            self.tabs[tab_id]["button_frame"].destroy()
            del self.tabs[tab_id]
            # Switch to remaining tab
            remaining_id = list(self.tabs.keys())[-1]
            self._switch_to_tab(remaining_id)

    def _close_current_tab(self):
        if hasattr(self, "active_tab_id"):
            self._close_tab(self.active_tab_id)

    # ─── DATABASE LOADING & SCHEMA ───
    def load_database(self, filepath: str):
        """Loads a SQLite database and refreshes the schema tree."""
        try:
            self.engine.connect(filepath)
            self.db_path = filepath
            db_name = os.path.basename(self.remote_path or filepath)
            self.db_label.configure(text=f"📁 {db_name}")
            self.title(f"🗄 SQLite Studio - {db_name}")
            self.refresh_schema()
            
            if not self.tabs:
                first_table = list(self.current_schema.get("tables", {}).keys())
                init_sql = f'SELECT * FROM "{first_table[0]}" LIMIT 100;' if first_table else "SELECT 'Connected to SQLite database' AS Status;"
                self._create_new_tab("SQL Editor 1", init_sql)

            # Update editors with new schema symbols
            for t_data in self.tabs.values():
                t_data["editor"].update_schema_symbols(self.current_schema)
                
            self.status_time_lbl.configure(text="✅ Connected", text_color="#22c55e")
            self.status_metric_lbl.configure(
                text=f"Tables: {len(self.current_schema.get('tables', {}))} │ Views: {len(self.current_schema.get('views', {}))}"
            )
        except Exception as e:
            messagebox.showerror("Connection Error", f"Failed to open database:\n{str(e)}")

    def refresh_schema(self):
        self.current_schema = self.engine.get_schema()
        self._filter_schema_tree()

    def _filter_schema_tree(self):
        self.schema_tree.delete(*self.schema_tree.get_children())
        if not hasattr(self, "current_schema"):
            return
        
        filter_text = self.filter_var.get().lower().strip()
        tables = self.current_schema.get("tables", {})
        views = self.current_schema.get("views", {})

        # Root node: Tables
        t_root = self.schema_tree.insert("", "end", text=f"📋 Tables ({len(tables)})", open=True)
        for name, data in tables.items():
            if filter_text and filter_text not in name.lower():
                continue
            cnt = data.get("row_count", 0)
            t_node = self.schema_tree.insert(t_root, "end", text=f"{name} ({cnt})", values=("table", name))
            for col in data.get("columns", []):
                pk_tag = " 🔑" if col["pk"] else ""
                self.schema_tree.insert(t_node, "end", text=f"  🔹 {col['name']} ({col['type']}){pk_tag}", values=("column", name, col["name"]))

        # Root node: Views
        if views:
            v_root = self.schema_tree.insert("", "end", text=f"👁 Views ({len(views)})", open=True)
            for name, data in views.items():
                if filter_text and filter_text not in name.lower():
                    continue
                v_node = self.schema_tree.insert(v_root, "end", text=name, values=("view", name))
                for col in data.get("columns", []):
                    self.schema_tree.insert(v_node, "end", text=f"  🔹 {col['name']} ({col['type']})", values=("column", name, col["name"]))

    def _on_schema_item_double_click(self, event):
        item = self.schema_tree.focus()
        if not item:
            return
        vals = self.schema_tree.item(item, "values")
        if vals and vals[0] in ("table", "view"):
            tbl_name = vals[1]
            sql = f'SELECT * FROM "{tbl_name}" LIMIT 500;'
            tab_id = self._create_new_tab(f"Table: {tbl_name}", sql)
            self._execute_sql(sql, tab_id)

    def _on_schema_context_menu(self, event):
        item = self.schema_tree.identify_row(event.y)
        if not item:
            return
        self.schema_tree.selection_set(item)
        vals = self.schema_tree.item(item, "values")
        if not vals:
            return

        item_type, tbl_name = vals[0], vals[1]
        from ui.modern_context_menu import ModernContextMenu
        menu = ModernContextMenu(self)
        menu.add_item(icon="📊", label="Browse Data (LIMIT 500)", command=lambda: self._open_table_data(tbl_name))
        menu.add_item(icon="📝", label="Generate SELECT Statement", command=lambda: self._generate_sql("select", tbl_name))
        menu.add_item(icon="➕", label="Generate INSERT Statement", command=lambda: self._generate_sql("insert", tbl_name))
        menu.add_separator()
        menu.add_item(icon="📋", label="Copy Table Name", command=lambda: self._copy_to_clip(tbl_name))
        menu.add_item(icon="📤", label="Export Table (CSV)...", command=lambda: self._export_table_csv(tbl_name))
        menu.show(event.x_root, event.y_root)

    def _open_table_data(self, table_name: str):
        sql = f'SELECT * FROM "{table_name}" LIMIT 500;'
        tab_id = self._create_new_tab(f"Data: {table_name}", sql)
        self._execute_sql(sql, tab_id)

    def _generate_sql(self, gen_type: str, table_name: str):
        if not hasattr(self, "current_schema"):
            return
        t_data = self.current_schema.get("tables", {}).get(table_name, {})
        cols = [f'"{c["name"]}"' for c in t_data.get("columns", [])]
        if gen_type == "select":
            cols_str = ",\n    ".join(cols) if cols else "*"
            sql = f'SELECT\n    {cols_str}\nFROM "{table_name}"\nLIMIT 100;'
        else:
            cols_str = ", ".join(cols)
            vals_str = ", ".join(["?" for _ in cols])
            sql = f'INSERT INTO "{table_name}" ({cols_str})\nVALUES ({vals_str});'
            
        self._create_new_tab(f"SQL: {table_name}", sql)

    def _copy_to_clip(self, text: str):
        self.clipboard_clear()
        self.clipboard_append(text)

    # ─── QUERY EXECUTION (NON-BLOCKING BACKGROUND THREAD) ───
    def _run_current_tab_query(self):
        if not hasattr(self, "active_tab_id") or self.active_tab_id not in self.tabs:
            return
        tab_data = self.tabs[self.active_tab_id]
        sql = tab_data["editor"].get_selected_text_or_all()
        if sql.strip():
            self._execute_sql(sql, self.active_tab_id)

    def _execute_sql(self, sql: str, tab_id: str):
        if tab_id not in self.tabs:
            return
        tab_data = self.tabs[tab_id]

        # Update UI to Running state
        self.run_btn.configure(state="disabled")
        self.cancel_btn.configure(state="normal")
        self.status_time_lbl.configure(text="⏳ Executing...", text_color="#f59e0b")
        self.status_metric_lbl.configure(text="Processing query in background thread...")
        self.status_thread_lbl.configure(text="Thread: Running")

        def run_thread():
            result = self.engine.execute_query(sql)
            self.after(0, lambda: self._on_query_finished(tab_id, sql, result))

        threading.Thread(target=run_thread, daemon=True).start()

    def _cancel_query(self):
        self.engine.interrupt()
        self.status_time_lbl.configure(text="🛑 Cancelled", text_color="#ef4444")
        self.cancel_btn.configure(state="disabled")
        self.run_btn.configure(state="normal")

    def _on_query_finished(self, tab_id: str, sql: str, result: QueryResult):
        self.run_btn.configure(state="normal")
        self.cancel_btn.configure(state="disabled")
        self.status_thread_lbl.configure(text="Thread: Idle")

        if tab_id not in self.tabs:
            return
        tab_data = self.tabs[tab_id]
        tab_data["last_result"] = result

        # Format execution time
        if result.execution_time_ms < 1000.0:
            time_str = f"⏱ {result.execution_time_ms:.1f} ms"
        else:
            time_str = f"⏱ {result.execution_time_ms / 1000.0:.2f} s"

        # Record History
        timestamp = time.strftime("%H:%M:%S")
        status_text = "🟢 Success" if not result.error else f"🔴 Error: {result.error[:40]}"
        rows_text = str(result.total_rows if result.is_select else result.rowcount)
        tab_data["hist_tree"].insert("", 0, values=(timestamp, sql.replace("\n", " ")[:80], time_str, rows_text, status_text))

        if result.error:
            self.status_time_lbl.configure(text=f"❌ Failed ({time_str})", text_color="#ef4444")
            self.status_metric_lbl.configure(text=f"Error: {result.error}")
            messagebox.showerror("SQL Error", f"Query Execution Error:\n\n{result.error}")
            return

        # Success - populate Data Grid
        if result.is_select:
            self._populate_grid(tab_data, result)
            self.status_time_lbl.configure(text=f"✅ Finished in {time_str}", text_color="#22c55e")
            self.status_metric_lbl.configure(text=f"📊 {result.total_rows} row(s) retrieved")
            tab_data["res_notebook"].select(0)  # Select Data Grid tab
        else:
            self.status_time_lbl.configure(text=f"✅ Executed in {time_str}", text_color="#22c55e")
            self.status_metric_lbl.configure(text=f"✅ {result.rowcount} row(s) affected")
            self.refresh_schema()

    def _populate_grid(self, tab_data: dict, result: QueryResult):
        tree = tab_data["tree"]
        tree.delete(*tree.get_children())

        # Setup columns with auto-fitted widths and stretch=False (so user manual expansion never bounces back!)
        tree["columns"] = result.columns
        sample_rows = result.rows[:60]

        for i, col in enumerate(result.columns):
            # Calculate optimal column width from column name and sample row values
            max_len = len(str(col))
            for r in sample_rows:
                if i < len(r) and r[i] is not None:
                    max_len = max(max_len, len(str(r[i])))
            
            # Auto-fit width between 90px and 450px
            col_width = max(90, min(450, max_len * 9 + 32))
            
            tree.heading(col, text=col, command=lambda c=col: self._sort_grid_column(tree, c, False))
            tree.column(col, width=col_width, minwidth=60, stretch=False)

        # Insert rows
        for row in result.rows:
            tree.insert("", "end", values=[str(v) if v is not None else "NULL" for v in row])

        tab_data["page_lbl"].config(text=f"Showing 1 - {result.total_rows} of {result.total_rows} rows")

    def _setup_grid_events(self, tree: ttk.Treeview, tab_id: str):
        """Sets up double-click inline cell editing, context menu, and copy shortcuts for Data Grid."""
        tree.bind("<Double-1>", lambda e: self._on_grid_cell_double_click(e, tree, tab_id))
        tree.bind("<Button-3>", lambda e: self._on_grid_context_menu(e, tree, tab_id))
        tree.bind("<Control-c>", lambda e: self._copy_grid_selection(tree, tab_id))
        tree.bind("<Control-C>", lambda e: self._copy_grid_selection(tree, tab_id))
        tree.bind("<F2>", lambda e: self._edit_selected_grid_cell(tree, tab_id))
        tree.bind("<Delete>", lambda e: self._delete_selected_grid_row(tree, tab_id))

    def _on_grid_cell_double_click(self, event, tree: ttk.Treeview, tab_id: str):
        """Opens in-place Entry widget over the double-clicked cell for inline editing."""
        region = tree.identify_region(event.x, event.y)
        if region != "cell":
            return
            
        item_id = tree.identify_row(event.y)
        col_str = tree.identify_column(event.x)
        if not item_id or not col_str:
            return
            
        col_idx = int(col_str.replace("#", "")) - 1
        cols = list(tree["columns"])
        if col_idx < 0 or col_idx >= len(cols):
            return
            
        col_name = cols[col_idx]
        bbox = tree.bbox(item_id, col_str)
        if not bbox:
            return
            
        row_values = list(tree.item(item_id, "values"))
        current_val = row_values[col_idx] if col_idx < len(row_values) else ""
        if current_val == "NULL":
            current_val = ""

        # Create inline Entry overlay
        entry = tk.Entry(
            tree,
            font=(self.font_family, 10),
            bg="#0284c7",
            fg="#ffffff",
            insertbackground="#ffffff",
            relief="solid",
            bd=1
        )
        entry.insert(0, str(current_val))
        entry.place(x=bbox[0], y=bbox[1], width=bbox[2], height=bbox[3])
        entry.focus_set()
        entry.select_range(0, tk.END)

        def save_and_close(e=None):
            new_val = entry.get()
            try:
                entry.destroy()
            except Exception:
                pass
                
            if new_val == current_val:
                return
                
            # 1. Update UI Treeview cell
            row_values[col_idx] = new_val
            tree.item(item_id, values=row_values)
            
            # 2. Update SQLite Database
            self._apply_cell_update_to_db(tab_id, col_name, new_val, cols, row_values, current_val)

        def cancel_edit(e=None):
            try:
                entry.destroy()
            except Exception:
                pass

        entry.bind("<Return>", save_and_close)
        entry.bind("<Escape>", cancel_edit)
        entry.bind("<FocusOut>", save_and_close)

    def _edit_selected_grid_cell(self, tree: ttk.Treeview, tab_id: str):
        selected = tree.selection()
        if not selected:
            return
        item_id = selected[0]
        bbox = tree.bbox(item_id, "#1")
        if bbox:
            # Simulate double click on first column
            class DummyEvent:
                x = bbox[0] + 5
                y = bbox[1] + 5
            self._on_grid_cell_double_click(DummyEvent(), tree, tab_id)

    def _apply_cell_update_to_db(self, tab_id: str, col_name: str, new_val: str, cols: list, row_values: list, old_val: str):
        """Executes UPDATE statement on SQLite database for the edited cell."""
        if tab_id not in self.tabs:
            return
            
        tab_data = self.tabs[tab_id]
        tab_title = tab_data.get("title", "")
        editor_sql = tab_data["editor"].get_text()
        
        # Determine table name from tab title or SQL query
        table_name = None
        if tab_title.startswith("Table: "):
            table_name = tab_title.replace("Table: ", "").strip()
        elif tab_title.startswith("Data: "):
            table_name = tab_title.replace("Data: ", "").strip()
        else:
            match = re.search(r'\bFROM\s+["`\']?([a-zA-Z0-9_]+)["`\']?', editor_sql, re.IGNORECASE)
            if match:
                table_name = match.group(1)
                
        if not table_name:
            self.status_time_lbl.configure(text=f"⚠ Edited in view (Table unknown)", text_color="#f59e0b")
            return

        # Find Primary Key columns or construct WHERE clause from unique row attributes
        t_meta = self.current_schema.get("tables", {}).get(table_name, {}) if hasattr(self, "current_schema") else {}
        pk_cols = [c["name"] for c in t_meta.get("columns", []) if c.get("pk")]
        
        row_dict = {cols[i]: row_values[i] for i in range(min(len(cols), len(row_values)))}
        row_dict_old = dict(row_dict)
        row_dict_old[col_name] = old_val

        where_parts = []
        params = [new_val]
        
        if pk_cols and all(pk in row_dict_old for pk in pk_cols):
            for pk in pk_cols:
                where_parts.append(f'"{pk}" = ?')
                params.append(row_dict_old[pk])
        else:
            for k, v in row_dict_old.items():
                if v == "NULL" or v is None:
                    where_parts.append(f'"{k}" IS NULL')
                else:
                    where_parts.append(f'"{k}" = ?')
                    params.append(v)
                    
        where_clause = " AND ".join(where_parts)
        update_sql = f'UPDATE "{table_name}" SET "{col_name}" = ? WHERE {where_clause};'
        
        res = self.engine.execute_query(update_sql, tuple(params))
        if not res.error:
            self.status_time_lbl.configure(text=f"✅ Saved [{col_name} = '{new_val}']", text_color="#22c55e")
            self.status_metric_lbl.configure(text=f"Updated 1 row in {table_name}")
        else:
            self.status_time_lbl.configure(text=f"❌ DB Update Error: {res.error[:30]}", text_color="#ef4444")

    def _on_grid_context_menu(self, event, tree: ttk.Treeview, tab_id: str):
        """Right-click menu for copying and editing grid cells."""
        item = tree.identify_row(event.y)
        col_str = tree.identify_column(event.x)
        if item:
            tree.selection_set(item)
            
        selected_items = tree.selection()
        if not selected_items:
            return
            
        col_idx = int(col_str.replace("#", "")) - 1 if col_str else 0
        cols = list(tree["columns"])
        curr_val = ""
        if item and 0 <= col_idx < len(cols):
            row_vals = tree.item(item, "values")
            curr_val = row_vals[col_idx] if col_idx < len(row_vals) else ""

        from ui.modern_context_menu import ModernContextMenu
        menu = ModernContextMenu(self)
        if curr_val:
            val_preview = str(curr_val)[:22] + "..." if len(str(curr_val)) > 22 else str(curr_val)
            menu.add_item(icon="📋", label=f"Copy Cell ('{val_preview}')", command=lambda: self._copy_to_clip(str(curr_val)))
            menu.add_separator()
            
        menu.add_item(icon="📑", label="Copy Row(s) as TSV (Excel)", command=lambda: self._copy_grid_tsv(tree))
        menu.add_item(icon="📄", label="Copy Row(s) as CSV", command=lambda: self._copy_grid_csv(tree))
        menu.add_item(icon="📦", label="Copy Row(s) as JSON", command=lambda: self._copy_grid_json(tree))
        menu.add_item(icon="📝", label="Copy Row(s) as SQL INSERT", command=lambda: self._copy_grid_insert(tree, tab_id))
        menu.add_separator()
        if item and col_str:
            menu.add_item(icon="✏", label="Edit Cell Value", shortcut="Double-Click", command=lambda: self._on_grid_cell_double_click(event, tree, tab_id))
        menu.add_item(icon="🗑", label="Delete Selected Row(s)", command=lambda: self._delete_selected_grid_row(tree, tab_id))
        menu.show(event.x_root, event.y_root)

    def _copy_grid_selection(self, tree: ttk.Treeview, tab_id: str):
        """Default Ctrl+C copy handler for Data Grid."""
        self._copy_grid_tsv(tree)

    def _copy_grid_tsv(self, tree: ttk.Treeview):
        selected = tree.selection()
        if not selected:
            return
        lines = []
        for item in selected:
            vals = tree.item(item, "values")
            lines.append("\t".join(str(v) for v in vals))
        text = "\n".join(lines)
        self._copy_to_clip(text)
        self.status_time_lbl.configure(text=f"📋 Copied {len(selected)} row(s) (TSV)", text_color="#38bdf8")

    def _copy_grid_csv(self, tree: ttk.Treeview):
        selected = tree.selection()
        if not selected:
            return
        import csv
        import io
        out = io.StringIO()
        writer = csv.writer(out)
        cols = list(tree["columns"])
        writer.writerow(cols)
        for item in selected:
            writer.writerow(tree.item(item, "values"))
        self._copy_to_clip(out.getvalue().strip())
        self.status_time_lbl.configure(text=f"📋 Copied {len(selected)} row(s) (CSV)", text_color="#38bdf8")

    def _copy_grid_json(self, tree: ttk.Treeview):
        selected = tree.selection()
        if not selected:
            return
        import json
        cols = list(tree["columns"])
        rows = [dict(zip(cols, tree.item(item, "values"))) for item in selected]
        self._copy_to_clip(json.dumps(rows, indent=2, ensure_ascii=False))
        self.status_time_lbl.configure(text=f"📋 Copied {len(selected)} row(s) (JSON)", text_color="#38bdf8")

    def _copy_grid_insert(self, tree: ttk.Treeview, tab_id: str):
        selected = tree.selection()
        if not selected:
            return
        tab_data = self.tabs.get(tab_id, {})
        tab_title = tab_data.get("title", "table")
        tbl_name = tab_title.replace("Table: ", "").replace("Data: ", "").strip()
        if not tbl_name or tbl_name.startswith("SQL Editor"):
            tbl_name = "target_table"
            
        cols = list(tree["columns"])
        cols_str = ", ".join([f'"{c}"' for c in cols])
        statements = []
        for item in selected:
            vals = tree.item(item, "values")
            val_strs = [f"'{str(v).replace(chr(39), chr(39)+chr(39))}'" if v != "NULL" else "NULL" for v in vals]
            statements.append(f'INSERT INTO "{tbl_name}" ({cols_str}) VALUES ({", ".join(val_strs)});')
        self._copy_to_clip("\n".join(statements))
        self.status_time_lbl.configure(text=f"📋 Copied {len(selected)} INSERT statement(s)", text_color="#38bdf8")

    def _delete_selected_grid_row(self, tree: ttk.Treeview, tab_id: str):
        selected = tree.selection()
        if not selected:
            return
        if not messagebox.askyesno("Delete Row", f"Are you sure you want to delete {len(selected)} selected row(s)?", parent=self):
            return
            
        tab_data = self.tabs.get(tab_id, {})
        tab_title = tab_data.get("title", "")
        editor_sql = tab_data["editor"].get_text()
        
        table_name = None
        if tab_title.startswith("Table: "):
            table_name = tab_title.replace("Table: ", "").strip()
        elif tab_title.startswith("Data: "):
            table_name = tab_title.replace("Data: ", "").strip()
        else:
            match = re.search(r'\bFROM\s+["`\']?([a-zA-Z0-9_]+)["`\']?', editor_sql, re.IGNORECASE)
            if match:
                table_name = match.group(1)
                
        cols = list(tree["columns"])
        t_meta = self.current_schema.get("tables", {}).get(table_name, {}) if table_name and hasattr(self, "current_schema") else {}
        pk_cols = [c["name"] for c in t_meta.get("columns", []) if c.get("pk")]
        
        deleted_count = 0
        for item in selected:
            row_values = list(tree.item(item, "values"))
            row_dict = {cols[i]: row_values[i] for i in range(min(len(cols), len(row_values)))}
            
            if table_name:
                where_parts = []
                params = []
                if pk_cols and all(pk in row_dict for pk in pk_cols):
                    for pk in pk_cols:
                        where_parts.append(f'"{pk}" = ?')
                        params.append(row_dict[pk])
                else:
                    for k, v in row_dict.items():
                        if v == "NULL" or v is None:
                            where_parts.append(f'"{k}" IS NULL')
                        else:
                            where_parts.append(f'"{k}" = ?')
                            params.append(v)
                where_clause = " AND ".join(where_parts)
                del_sql = f'DELETE FROM "{table_name}" WHERE {where_clause};'
                self.engine.execute_query(del_sql, tuple(params))
                
            tree.delete(item)
            deleted_count += 1
            
        self.status_time_lbl.configure(text=f"🗑 Deleted {deleted_count} row(s)", text_color="#ef4444")

    def _copy_to_clip(self, text: str):
        self.clipboard_clear()
        self.clipboard_append(text)
        self.update()

    def _sort_grid_column(self, tree, col, reverse):
        items = [(tree.set(k, col), k) for k in tree.get_children("")]
        try:
            items.sort(key=lambda t: float(t[0]), reverse=reverse)
        except ValueError:
            items.sort(reverse=reverse)
        for index, (val, k) in enumerate(items):
            tree.move(k, "", index)
        tree.heading(col, command=lambda: self._sort_grid_column(tree, col, not reverse))

    # ─── EXPORT & TOOLS ───
    def _export_current_results(self):
        if not hasattr(self, "active_tab_id") or self.active_tab_id not in self.tabs:
            return
        tab_data = self.tabs[self.active_tab_id]
        sql = tab_data["editor"].get_selected_text_or_all()
        if not sql.strip():
            return

        out_path = filedialog.asksaveasfilename(
            parent=self,
            title="Export Query Results",
            defaultextension=".csv",
            filetypes=[("CSV File", "*.csv"), ("JSON File", "*.json")]
        )
        if not out_path:
            return

        if out_path.endswith(".json"):
            ok, msg = self.engine.export_to_json(sql, out_path)
        else:
            ok, msg = self.engine.export_to_csv(sql, out_path)

        if ok:
            messagebox.showinfo("Export Successful", f"Data exported successfully to:\n{out_path}")
        else:
            messagebox.showerror("Export Failed", f"Export error: {msg}")

    def _export_table_csv(self, table_name: str):
        out_path = filedialog.asksaveasfilename(
            parent=self,
            title=f"Export Table {table_name}",
            initialfile=f"{table_name}.csv",
            defaultextension=".csv",
            filetypes=[("CSV File", "*.csv")]
        )
        if out_path:
            ok, msg = self.engine.export_to_csv(table_name, out_path)
            if ok:
                messagebox.showinfo("Export Successful", f"Table '{table_name}' exported to:\n{out_path}")
            else:
                messagebox.showerror("Export Failed", msg)

    def _format_sql(self):
        if not hasattr(self, "active_tab_id") or self.active_tab_id not in self.tabs:
            return
            
        editor = self.tabs[self.active_tab_id]["editor"]
        sql = editor.get_text()
        if not sql or not sql.strip():
            return

        # 1. Protect comments & quoted literals ('...', "...", `...`, -- ..., /* ... */)
        placeholders = []
        def save_token(match):
            placeholders.append(match.group(0))
            return f"__SQL_TOK_{len(placeholders) - 1}__"

        protected = re.sub(r"(--[^\r\n]*|/\*[\s\S]*?\*/|'(?:''|[^'])*'|\"(?:\"\"|[^\"])*\"|`[^`]*`)", save_token, sql)

        # 2. Normalize glued operators and punctuation
        protected = re.sub(r"(\bSELECT|\bselect)\s*\*", r"\1 *", protected, flags=re.IGNORECASE)
        protected = re.sub(r"\*\s*(\bFROM|\bfrom)", r"* \1", protected, flags=re.IGNORECASE)
        protected = re.sub(r",\s*", r", ", protected)
        protected = re.sub(r"\s*;\s*$", r";", protected.strip())

        # 3. Uppercase SQL keywords
        keywords = [
            "INNER JOIN", "LEFT JOIN", "RIGHT JOIN", "CROSS JOIN", "FULL JOIN", "NATURAL JOIN",
            "INSERT OR REPLACE INTO", "INSERT OR IGNORE INTO", "INSERT INTO", "DELETE FROM",
            "CREATE TABLE IF NOT EXISTS", "CREATE TABLE", "CREATE INDEX IF NOT EXISTS", "CREATE INDEX",
            "CREATE VIEW IF NOT EXISTS", "CREATE VIEW", "DROP TABLE IF EXISTS", "DROP TABLE",
            "DROP INDEX IF EXISTS", "DROP INDEX", "DROP VIEW IF EXISTS", "DROP VIEW",
            "ALTER TABLE", "ADD COLUMN", "RENAME TO", "PRIMARY KEY", "AUTOINCREMENT", "NOT NULL",
            "DEFAULT CURRENT_TIMESTAMP", "DEFAULT", "UNIQUE", "FOREIGN KEY", "REFERENCES", "CHECK",
            "UNION ALL", "UNION", "INTERSECT", "EXCEPT", "GROUP BY", "ORDER BY", "IS NOT NULL", "IS NULL",
            "SELECT", "DISTINCT", "FROM", "JOIN", "WHERE", "HAVING", "LIMIT", "OFFSET",
            "VALUES", "UPDATE", "SET", "AND", "OR", "AS", "ON", "USING",
            "IN", "IS", "NOT", "LIKE", "GLOB", "BETWEEN", "EXISTS", "CASE", "WHEN", "THEN", "ELSE", "END",
            "COUNT", "SUM", "AVG", "MIN", "MAX", "COALESCE", "IFNULL", "PRAGMA", "ASC", "DESC",
            "INTEGER", "TEXT", "REAL", "BLOB", "NUMERIC", "BOOLEAN", "VARCHAR", "DATETIME", "TIMESTAMP"
        ]
        for kw in keywords:
            kw_regex = r"\s+".join(re.escape(w) for w in kw.split())
            protected = re.sub(r"\b" + kw_regex + r"\b", kw, protected, flags=re.IGNORECASE)

        # 4. Handle CREATE TABLE with parenthesized column definitions
        if re.search(r"\bCREATE\s+TABLE\b", protected, flags=re.IGNORECASE):
            m = re.match(r"(CREATE\s+TABLE(?:\s+IF\s+NOT\s+EXISTS)?\s+[^\(]+)\(([\s\S]*)\)([\s\S]*?);?", protected.strip(), re.IGNORECASE)
            if m:
                head = m.group(1).strip()
                cols_body = m.group(2).strip()
                tail = m.group(3).strip().rstrip(";")
                col_lines = [c.strip() for c in cols_body.split(",") if c.strip()]
                formatted_cols = ",\n    ".join(col_lines)
                res = f"{head} (\n    {formatted_cols}\n){tail};"
                for i, tok in enumerate(placeholders):
                    res = res.replace(f"__SQL_TOK_{i}__", tok)
                editor.set_text(res.strip())
                self.status_time_lbl.configure(text="🧹 Formatted SQL", text_color="#38bdf8")
                return

        # 5. General queries (SELECT, UPDATE, INSERT, DELETE, etc.)
        normalized = re.sub(r"\s+", " ", protected).strip()

        major_clauses = [
            "SELECT", "INSERT OR REPLACE INTO", "INSERT OR IGNORE INTO", "INSERT INTO", "DELETE FROM",
            "UPDATE", "SET", "VALUES",
            "FROM", "INNER JOIN", "LEFT JOIN", "RIGHT JOIN", "CROSS JOIN", "FULL JOIN", "JOIN",
            "WHERE", "GROUP BY", "HAVING", "ORDER BY", "LIMIT",
            "UNION ALL", "UNION", "INTERSECT", "EXCEPT"
        ]
        for kw in major_clauses:
            kw_regex = r"\s+".join(re.escape(w) for w in kw.split())
            if kw == "JOIN":
                pattern = r"(?<!INNER\s)(?<!LEFT\s)(?<!RIGHT\s)(?<!FULL\s)(?<!CROSS\s)(?<!NATURAL\s)\bJOIN\b"
                normalized = re.sub(pattern, r"\nJOIN", normalized)
            elif kw == "FROM":
                pattern = r"(?<!DELETE\s)\bFROM\b"
                normalized = re.sub(pattern, r"\nFROM", normalized)
            else:
                normalized = re.sub(r"\s*\b(" + kw_regex + r")\b\s*", r"\n\1 ", normalized)

        lines = [line.strip() for line in normalized.split("\n") if line.strip()]

        formatted_lines = []
        for line in lines:
            # Multi-column SELECT formatting
            if line.startswith("SELECT ") and line != "SELECT *":
                cols_part = line[7:].strip()
                if "," in cols_part and len(cols_part) > 40:
                    cols = [c.strip() for c in cols_part.split(",")]
                    formatted_lines.append("SELECT")
                    for i, c in enumerate(cols):
                        comma = "," if i < len(cols) - 1 else ""
                        formatted_lines.append(f"    {c}{comma}")
                    continue

            # Multi-assignment UPDATE SET formatting
            if line.startswith("SET ") and "," in line:
                set_part = line[4:].strip()
                assignments = [a.strip() for a in set_part.split(",")]
                formatted_lines.append("SET")
                for i, a in enumerate(assignments):
                    comma = "," if i < len(assignments) - 1 else ""
                    formatted_lines.append(f"    {a}{comma}")
                continue

            # Multi-condition WHERE with AND/OR
            if line.startswith("WHERE ") and (" AND " in line or " OR " in line) and len(line) > 60:
                where_part = line[6:].strip()
                cond_tokens = re.split(r"\s+\b(AND|OR)\b\s+", where_part)
                if len(cond_tokens) > 1:
                    formatted_lines.append(f"WHERE {cond_tokens[0]}")
                    idx = 1
                    while idx < len(cond_tokens):
                        op = cond_tokens[idx]
                        cond = cond_tokens[idx + 1] if idx + 1 < len(cond_tokens) else ""
                        formatted_lines.append(f"    {op} {cond}")
                        idx += 2
                    continue

            formatted_lines.append(line)

        result_sql = "\n".join(formatted_lines)

        # 6. Restore comments & quoted literals
        for i, tok in enumerate(placeholders):
            result_sql = result_sql.replace(f"__SQL_TOK_{i}__", tok)

        editor.set_text(result_sql.strip())
        self.status_time_lbl.configure(text="🧹 Formatted SQL", text_color="#38bdf8")

    def _choose_and_open_file(self):
        filepath = filedialog.askopenfilename(
            parent=self,
            title="Open Database or SQL Script",
            filetypes=[
                ("All Files", "*.*"),
                ("SQLite Databases", "*.db;*.sqlite;*.sqlite3;*.db3;*.dat"),
                ("SQL Scripts", "*.sql")
            ]
        )
        if filepath:
            if filepath.endswith(".sql"):
                with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                self._create_new_tab(os.path.basename(filepath), content)
            else:
                self.load_database(filepath)

    def _sync_to_phone(self):
        """Pushes the modified database back to the connected phone and updates File Explorer."""
        if not self.db_path or not self.remote_path or not self.serial:
            return
        
        self.sync_btn.configure(text="⏳ Syncing to Phone...", state="disabled")
        
        def run_sync():
            # 1. Flush any pending transactions and WAL journals into the main DB file
            self.engine.checkpoint()
            
            # 2. Upload main database file
            remote_dir = os.path.dirname(self.remote_path).replace("\\", "/")
            ok, msg = self.fm.upload_file(self.serial, self.db_path, remote_dir)
            
            # 3. If companion WAL/SHM files exist, sync them too
            wal_local = self.db_path + "-wal"
            shm_local = self.db_path + "-shm"
            if os.path.exists(wal_local):
                self.fm.upload_file(self.serial, wal_local, remote_dir)
            if os.path.exists(shm_local):
                self.fm.upload_file(self.serial, shm_local, remote_dir)
            
            def on_done():
                self.sync_btn.configure(text="💾 Save & Sync to Phone", state="normal")
                if ok:
                    self.status_time_lbl.configure(text="✅ Synced to Phone", text_color="#22c55e")
                    
                    # Refresh File Explorer so Date Modified & Size update in real-time
                    if self.on_saved:
                        try: self.on_saved()
                        except Exception: pass
                    elif hasattr(self.master, "load_directory") and hasattr(self.master, "current_path"):
                        try: self.master.load_directory(self.master.current_path, force_refresh=True)
                        except Exception: pass
                        
                    messagebox.showinfo(
                        "Sync Successful", 
                        f"Database successfully synced and updated on phone:\n{self.remote_path}\n\n(File Explorer Date Modified and Size have been updated!)"
                    )
                else:
                    messagebox.showerror("Sync Failed", f"Failed to push database to phone:\n{msg}")
            self.after(0, on_done)

        threading.Thread(target=run_sync, daemon=True).start()

    def _on_close(self):
        self.engine.close()
        self.destroy()
