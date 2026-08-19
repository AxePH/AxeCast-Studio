import os
import sys
import threading
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog
import customtkinter as ctk

from core.file_manager import DeviceFileManager
from core.system_clipboard import SystemClipboardHelper
from ui.custom_dialogs import ask_confirm

try:
    from tkinterdnd2 import DND_FILES, COPY, MOVE
    _has_tkdnd = True
except ImportError:
    _has_tkdnd = False


try:
    import windnd
except ImportError:
    windnd = None

class DeviceFileExplorerView(ctk.CTkFrame):
    """2-Way Cross-OS File Explorer: Drag & Drop, Windows/Mac Copy-Paste Bridge, and Robust Inline Renaming."""
    
    def __init__(self, master, serial: str, model_name: str = "Device", on_toggle_dock=None, is_docked: bool = False, **kwargs):
        super().__init__(master, fg_color=("#f8fafc", "#0f172a"), corner_radius=10, **kwargs)
        
        self.serial = serial
        self.model = model_name
        self.fm = DeviceFileManager()
        self.on_toggle_dock = on_toggle_dock
        self.is_docked = is_docked
        
        self.is_mac = sys.platform == "darwin"
        self.mod_key = "⌘" if self.is_mac else "Ctrl+"
        
        self.current_path = "/sdcard"
        self.history_stack = []
        self.items_by_iid = {}
        self._is_loading = False
        
        # Staging folder for OS copy/paste
        self.staging_dir = str(Path(__file__).resolve().parent.parent / "captures" / "clipboard_cache")
        os.makedirs(self.staging_dir, exist_ok=True)
        
        self.clipboard = {"mode": None, "items": []}
        self.inline_entry = None
        self._is_renaming = False
        self._pending_rename_name = None
        
        self._setup_styles()
        self._build_ui()
        self._setup_context_menu()
        self._bind_shortcuts()
        self._setup_drag_and_drop()
        self.load_directory(self.current_path)

    def _setup_styles(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass
            
        is_dark = ctk.get_appearance_mode() == "Dark"
        bg_color = "#1e293b" if is_dark else "#ffffff"
        fg_color = "#f8fafc" if is_dark else "#0f172a"
        hdr_bg = "#0f172a" if is_dark else "#e2e8f0"
        hdr_fg = "#94a3b8" if is_dark else "#475569"
        sel_bg = "#0284c7"
        
        font_family = "SF Pro Text" if self.is_mac else ("Segoe UI" if sys.platform.startswith("win") else "Ubuntu")
        
        style.configure(
            "DeviceTree.Treeview",
            background=bg_color,
            foreground=fg_color,
            fieldbackground=bg_color,
            rowheight=28,
            font=(font_family, 10),
            borderwidth=0
        )
        style.map(
            "DeviceTree.Treeview",
            background=[("selected", sel_bg)],
            foreground=[("selected", "#ffffff")]
        )
        style.configure(
            "DeviceTree.Treeview.Heading",
            background=hdr_bg,
            foreground=hdr_fg,
            font=(font_family, 10, "bold"),
            relief="flat",
            padding=4
        )

    def apply_theme(self):
        """Re-applies ttk.Style for DeviceTree and context menu when appearance mode changes."""
        self._setup_styles()
        is_dark = ctk.get_appearance_mode() == "Dark"
        menu_bg = "#1e293b" if is_dark else "#ffffff"
        menu_fg = "#f8fafc" if is_dark else "#0f172a"
        active_bg = "#0284c7"
        active_fg = "#ffffff"
        disabled_fg = "#64748b" if is_dark else "#94a3b8"
        if hasattr(self, "context_menu"):
            try:
                self.context_menu.config(
                    bg=menu_bg,
                    fg=menu_fg,
                    activebackground=active_bg,
                    activeforeground=active_fg,
                    disabledforeground=disabled_fg
                )
            except Exception:
                pass

    def _build_ui(self):
        # 1. Top Header Bar
        top_bar = ctk.CTkFrame(self, height=44, fg_color=("#e2e8f0", "#090d16"), corner_radius=8)
        top_bar.pack(fill="x", side="top", padx=6, pady=6)
        
        self.back_btn = ctk.CTkButton(
            top_bar, text="◀ Back", width=65, height=30,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=("#cbd5e1", "#1e293b"),
            hover_color=("#94a3b8", "#334155"),
            text_color=("#0f172a", "#f8fafc"),
            command=self._go_back
        )
        self.back_btn.pack(side="left", padx=(8, 3), pady=6)
        
        self.up_btn = ctk.CTkButton(
            top_bar, text="⬆ Up", width=55, height=30,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=("#cbd5e1", "#1e293b"),
            hover_color=("#94a3b8", "#334155"),
            text_color=("#0f172a", "#f8fafc"),
            command=self._go_up
        )
        self.up_btn.pack(side="left", padx=3, pady=6)
        
        self.refresh_btn = ctk.CTkButton(
            top_bar, text="🔄", width=34, height=30,
            font=ctk.CTkFont(size=13),
            fg_color=("#cbd5e1", "#1e293b"),
            hover_color=("#94a3b8", "#334155"),
            text_color=("#0f172a", "#f8fafc"),
            command=lambda: self.load_directory(self.current_path, force_refresh=True)
        )
        self.refresh_btn.pack(side="left", padx=3, pady=6)
        
        self.path_entry = ctk.CTkEntry(
            top_bar,
            height=30,
            font=ctk.CTkFont(size=12),
            fg_color=("#ffffff", "#0f172a"),
            text_color=("#0f172a", "#f8fafc"),
            border_color=("#cbd5e1", "#334155")
        )
        self.path_entry.pack(side="left", fill="x", expand=True, padx=6, pady=6)
        self.path_entry.bind("<Return>", lambda e: self.load_directory(self.path_entry.get().strip()))
        
        go_btn = ctk.CTkButton(
            top_bar, text="Go", width=46, height=30,
            font=ctk.CTkFont(weight="bold"),
            fg_color=("#0284c7", "#0369a1"),
            command=lambda: self.load_directory(self.path_entry.get().strip())
        )
        go_btn.pack(side="left", padx=(0, 6), pady=6)
        
        if self.on_toggle_dock:
            dock_text = "↗ Pop Out" if self.is_docked else "↙ Dock"
            self.dock_btn = ctk.CTkButton(
                top_bar,
                text=dock_text,
                width=90,
                height=30,
                font=ctk.CTkFont(size=11, weight="bold"),
                fg_color=("#7c3aed", "#6d28d9"),
                command=self.on_toggle_dock
            )
            self.dock_btn.pack(side="right", padx=8, pady=6)

        # 2. Dynamic Action Toolbar
        action_bar = ctk.CTkFrame(self, height=36, fg_color="transparent")
        action_bar.pack(fill="x", side="top", padx=6, pady=(0, 4))
        
        self.upload_btn = ctk.CTkButton(
            action_bar, text="⬆ Upload", height=28, width=75, font=ctk.CTkFont(size=11, weight="bold"),
            fg_color=("#16a34a", "#15803d"),
            command=self._upload_file
        )
        self.upload_btn.pack(side="left", padx=2)
        
        self.download_btn = ctk.CTkButton(
            action_bar, text="⬇ Download", height=28, width=88, font=ctk.CTkFont(size=11),
            fg_color=("#2563eb", "#1d4ed8"), state="disabled",
            command=self._download_selected
        )
        self.download_btn.pack(side="left", padx=2)
        
        self.copy_btn = ctk.CTkButton(
            action_bar, text="📋 Copy", height=28, width=65, font=ctk.CTkFont(size=11),
            fg_color=("#475569", "#334155"), state="disabled",
            command=self._copy_selected
        )
        self.copy_btn.pack(side="left", padx=2)
        
        self.cut_btn = ctk.CTkButton(
            action_bar, text="✂ Cut", height=28, width=55, font=ctk.CTkFont(size=11),
            fg_color=("#475569", "#334155"), state="disabled",
            command=self._cut_selected
        )
        self.cut_btn.pack(side="left", padx=2)
        
        self.paste_btn = ctk.CTkButton(
            action_bar, text="📋 Paste", height=28, width=65, font=ctk.CTkFont(size=11),
            fg_color=("#0284c7", "#0369a1"), state="normal",
            command=self._paste_clipboard
        )
        self.paste_btn.pack(side="left", padx=2)
        
        self.rename_btn = ctk.CTkButton(
            action_bar, text="✏ Rename", height=28, width=72, font=ctk.CTkFont(size=11),
            fg_color=("#475569", "#334155"), state="disabled",
            command=self._rename_selected
        )
        self.rename_btn.pack(side="left", padx=2)
        
        self.new_folder_btn = ctk.CTkButton(
            action_bar, text="➕ Folder", height=28, width=65, font=ctk.CTkFont(size=11),
            fg_color=("#475569", "#334155"),
            command=self._create_folder
        )
        self.new_folder_btn.pack(side="left", padx=2)
        
        self.delete_btn = ctk.CTkButton(
            action_bar, text="🗑 Delete", height=28, width=65, font=ctk.CTkFont(size=11),
            fg_color=("#dc2626", "#b91c1c"), state="disabled",
            command=self._delete_selected
        )
        self.delete_btn.pack(side="left", padx=2)

        # 3. Main Split View (Bookmarks Sidebar + Native Treeview)
        self.split_container = ctk.CTkFrame(self, fg_color="transparent")
        self.split_container.pack(fill="both", expand=True, padx=6, pady=2)
        
        sidebar = ctk.CTkFrame(self.split_container, width=170, fg_color=("#f1f5f9", "#1e293b"), corner_radius=8)
        sidebar.pack(side="left", fill="y", padx=(0, 6))
        sidebar.pack_propagate(False)
        
        ctk.CTkLabel(sidebar, text="📌 Quick Access", font=ctk.CTkFont(size=11, weight="bold"), text_color=("#64748b", "#94a3b8")).pack(anchor="w", padx=10, pady=(8, 4))
        
        bookmarks = [
            ("💾 Internal Storage", "/sdcard"),
            ("📥 Downloads", "/sdcard/Download"),
            ("📷 Camera (DCIM)", "/sdcard/DCIM"),
            ("🖼 Pictures", "/sdcard/Pictures"),
            ("📄 Documents", "/sdcard/Documents"),
            ("🎵 Music", "/sdcard/Music"),
            ("🎬 Movies", "/sdcard/Movies"),
            ("⚙ Root System (/)", "/"),
        ]
        
        for label, path in bookmarks:
            btn = ctk.CTkButton(
                sidebar, text=label, height=26, anchor="w",
                font=ctk.CTkFont(size=11),
                fg_color="transparent",
                text_color=("#334155", "#cbd5e1"),
                hover_color=("#cbd5e1", "#334155"),
                command=lambda p=path: self.load_directory(p)
            )
            btn.pack(fill="x", padx=4, pady=1)

        tree_frame = ctk.CTkFrame(self.split_container, fg_color="transparent")
        tree_frame.pack(side="right", fill="both", expand=True)
        
        columns = ("size", "date", "perms")
        self.tree = ttk.Treeview(
            tree_frame,
            columns=columns,
            style="DeviceTree.Treeview",
            selectmode="extended"
        )
        
        self.tree.heading("#0", text="  Name", anchor="w")
        self.tree.heading("size", text="Size", anchor="e")
        self.tree.heading("date", text="Date Modified", anchor="w")
        self.tree.heading("perms", text="Permissions", anchor="w")
        
        self.tree.column("#0", width=260, minwidth=180, stretch=True)
        self.tree.column("size", width=85, minwidth=65, anchor="e", stretch=False)
        self.tree.column("date", width=125, minwidth=90, anchor="w", stretch=False)
        self.tree.column("perms", width=100, minwidth=80, anchor="w", stretch=False)
        
        v_scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=v_scroll.set)
        
        self.tree.pack(side="left", fill="both", expand=True)
        v_scroll.pack(side="right", fill="y")
        
        self.tree.bind("<Double-1>", self._on_double_click)
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        
        self.tree.bind("<Button-3>", self._show_context_menu)
        if self.is_mac:
            self.tree.bind("<Button-2>", self._show_context_menu)
            self.tree.bind("<Control-Button-1>", self._show_context_menu)

        # 4. Status Bar
        self.status_bar = ctk.CTkFrame(self, height=24, fg_color=("#e2e8f0", "#090d16"), corner_radius=0)
        self.status_bar.pack(fill="x", side="bottom")
        
        self.status_lbl = ctk.CTkLabel(self.status_bar, text="Ready", font=ctk.CTkFont(size=11), text_color=("#475569", "#94a3b8"))
        self.status_lbl.pack(side="left", padx=10)
        
        self.count_lbl = ctk.CTkLabel(self.status_bar, text="0 items", font=ctk.CTkFont(size=11), text_color=("#475569", "#94a3b8"))
        self.count_lbl.pack(side="right", padx=10)

    def _setup_drag_and_drop(self):
        # 1. Primary: Cross-Platform tkinterdnd2 (macOS, Windows, Linux)
        if _has_tkdnd:
            try:
                targets = [self.tree, self, self.split_container]
                if hasattr(self, "tree_frame"):
                    targets.append(self.tree_frame)
                for target in targets:
                    try:
                        # Drop Target: OS -> App
                        target.drop_target_register(DND_FILES)
                        target.dnd_bind("<<Drop>>", self._on_tkdnd_dropped)
                    except Exception:
                        pass
                        
                # Drag Source: App -> OS (Windows Explorer / Desktop / macOS Finder)
                try:
                    self.tree.drag_source_register(1, DND_FILES)
                    self.tree.dnd_bind("<<DragInitCmd>>", self._on_drag_init)
                    self.tree.dnd_bind("<<DragEndCmd>>", self._on_drag_end)
                except Exception:
                    pass
            except Exception:
                pass
                
        # 2. Secondary fallback for Windows: windnd
        elif windnd:
            try:
                windnd.hook_dropfiles(self.tree, func=self._on_windnd_dropped)
                windnd.hook_dropfiles(self, func=self._on_windnd_dropped)
                windnd.hook_dropfiles(self.split_container, func=self._on_windnd_dropped)
            except Exception:
                pass

    def _on_drag_init(self, event):
        """Initiates dragging files OUT of the app into Windows Explorer or Desktop."""
        row_id = self.tree.identify_row(event.y)
        sel = list(self.tree.selection())
        if row_id and row_id not in sel:
            self.tree.selection_set(row_id)
            sel = [row_id]
            
        if not sel:
            return None
            
        items = [self.items_by_iid[iid] for iid in sel if iid in self.items_by_iid]
        if not items:
            return None
            
        staged_paths = []
        for it in items:
            local_p = os.path.join(self.staging_dir, os.path.basename(it["path"]))
            ok, _ = self.fm.download_file(self.serial, it["path"], self.staging_dir)
            if ok and os.path.exists(local_p):
                staged_paths.append(os.path.abspath(local_p))
                
        if not staged_paths:
            return None
            
        self.status_lbl.configure(text=f"🚀 Dragging {len(staged_paths)} item(s) to computer...")
        
        # Always use a tuple so Tkinter properly formats it as a Tcl list (handles spaces in paths)
        return (COPY, DND_FILES, tuple(staged_paths))

    def _on_drag_end(self, event):
        """Handler for drag out completion."""
        self.status_lbl.configure(text="✅ Drag & Drop export finished!")

    def _on_tkdnd_dropped(self, event):
        """Handler for tkinterdnd2 cross-platform drop events (macOS, Windows, Linux)."""
        raw_data = getattr(event, "data", "")
        if not raw_data:
            return
        try:
            files = list(self.tk.splitlist(raw_data))
        except Exception:
            files = [raw_data]
        self._process_dropped_files(files)

    def _on_windnd_dropped(self, files):
        """Handler for Windows-specific windnd drop events."""
        self._process_dropped_files(files)

    def _process_dropped_files(self, files):
        """Process and upload dropped files/folders into active mobile directory."""
        if not files:
            return
            
        decoded_files = []
        for f in files:
            if isinstance(f, bytes):
                decoded_files.append(f.decode("utf-8", errors="replace"))
            else:
                decoded_files.append(str(f).strip("{}"))
                
        valid_files = [f for f in decoded_files if os.path.exists(f)]
        if not valid_files:
            return
            
        self.status_lbl.configure(text=f"⏳ Uploading {len(valid_files)} dropped item(s) to phone...")
        
        def run_upload():
            count = 0
            for local_file in valid_files:
                ok, _ = self.fm.upload_file(self.serial, local_file, self.current_path)
                if ok:
                    count += 1
            self.after(0, lambda: self.status_lbl.configure(text=f"✅ Uploaded {count} dropped file(s) from computer!"))
            self.after(0, lambda: self.load_directory(self.current_path, force_refresh=True))
            
        threading.Thread(target=run_upload, daemon=True).start()

    def _setup_context_menu(self):
        from ui.modern_context_menu import ModernContextMenu
        self.context_menu = ModernContextMenu(self)
        self.context_menu.add_item(icon="🗄", label="Open in AxeSQL", command=self._open_selected_in_sqlite_studio, item_id="open_db")
        self.context_menu.add_separator()
        self.context_menu.add_item(icon="📋", label="Copy", shortcut=f"{self.mod_key}C", command=self._copy_selected, item_id="copy")
        self.context_menu.add_item(icon="✂", label="Cut", shortcut=f"{self.mod_key}X", command=self._cut_selected, item_id="cut")
        self.context_menu.add_item(icon="📥", label="Paste", shortcut=f"{self.mod_key}V", command=self._paste_clipboard, item_id="paste")
        self.context_menu.add_separator()
        self.context_menu.add_item(icon="✏", label="Rename", shortcut="F2", command=self._rename_selected, item_id="rename")
        self.context_menu.add_item(icon="🗑", label="Delete", shortcut="Del", command=self._delete_selected, item_id="delete")
        self.context_menu.add_separator()
        self.context_menu.add_item(icon="⬇", label="Download to Computer...", command=self._download_selected, item_id="download")
        self.context_menu.add_item(icon="➕", label="New Folder", command=self._create_folder, item_id="new_folder")

    def _bind_shortcuts(self):
        widgets_to_bind = [self.tree, self, self.split_container]
        if hasattr(self, "tree_frame"):
            widgets_to_bind.append(self.tree_frame)
            
        for widget in widgets_to_bind:
            # Universal KeyPress Router (captures English, Thai, CapsLock, Ctrl/Cmd)
            widget.bind("<Key>", self._on_key_press)
            
            # Standard explicit sequences for redundancy
            widget.bind("<Control-c>", lambda e: self._handle_shortcut("copy"))
            widget.bind("<Control-C>", lambda e: self._handle_shortcut("copy"))
            widget.bind("<Control-x>", lambda e: self._handle_shortcut("cut"))
            widget.bind("<Control-X>", lambda e: self._handle_shortcut("cut"))
            widget.bind("<Control-v>", lambda e: self._handle_shortcut("paste"))
            widget.bind("<Control-V>", lambda e: self._handle_shortcut("paste"))
            widget.bind("<Control-a>", lambda e: self._select_all())
            widget.bind("<Control-A>", lambda e: self._select_all())
            
            widget.bind("<Command-c>", lambda e: self._handle_shortcut("copy"))
            widget.bind("<Command-C>", lambda e: self._handle_shortcut("copy"))
            widget.bind("<Command-x>", lambda e: self._handle_shortcut("cut"))
            widget.bind("<Command-X>", lambda e: self._handle_shortcut("cut"))
            widget.bind("<Command-v>", lambda e: self._handle_shortcut("paste"))
            widget.bind("<Command-V>", lambda e: self._handle_shortcut("paste"))
            widget.bind("<Command-a>", lambda e: self._select_all())
            widget.bind("<Command-A>", lambda e: self._select_all())
            
            widget.bind("<F2>", lambda e: self._rename_selected())
            widget.bind("<Delete>", lambda e: self._delete_selected())
            widget.bind("<BackSpace>", lambda e: self._delete_selected() if self.is_mac else None)

            # Auto-focus tree when hovering or clicking
            widget.bind("<Enter>", lambda e: self.tree.focus_set(), add="+")
            widget.bind("<Button-1>", lambda e: self.tree.focus_set(), add="+")

        self.tree.bind("<Button-1>", lambda e: self.tree.focus_set(), add="+")

    def _on_key_press(self, event):
        """Universal key handler supporting English, Thai, CapsLock, and all keyboard layouts."""
        if self._is_renaming:
            return  # Allow inline Entry widget to handle typing normally
            
        # Detect Ctrl (Windows/Linux) or Command (macOS)
        is_ctrl = bool(event.state & 4) or bool(event.state & 8) or bool(event.state & 0x40000)
        kc = getattr(event, "keycode", 0)
        ks = str(getattr(event, "keysym", "")).lower()
        ch = getattr(event, "char", "")
        
        # Copy: Ctrl+C (Keycode 67, char \x03, or keysym c/thai)
        if is_ctrl and (kc == 67 or ks in ('c', 'thai_saraae') or ch == '\x03'):
            self._handle_shortcut("copy")
            return "break"
            
        # Paste: Ctrl+V (Keycode 86, char \x16, or keysym v/thai)
        if is_ctrl and (kc == 86 or ks in ('v', 'thai_oang') or ch == '\x16'):
            self._handle_shortcut("paste")
            return "break"
            
        # Cut: Ctrl+X (Keycode 88, char \x18, or keysym x/thai)
        if is_ctrl and (kc == 88 or ks in ('x', 'thai_khokhai') or ch == '\x18'):
            self._handle_shortcut("cut")
            return "break"
            
        # Select All: Ctrl+A (Keycode 65, char \x01, or keysym a/thai)
        if is_ctrl and (kc == 65 or ks in ('a', 'thai_fofan') or ch == '\x01'):
            self._select_all()
            return "break"
            
        # Rename: F2 (Keycode 113 or keysym f2)
        if ks == "f2" or kc == 113:
            self._rename_selected()
            return "break"
            
        # Delete: Del / Backspace
        if ks in ("delete", "backspace") or kc in (46, 8):
            self._delete_selected()
            return "break"

    def _handle_shortcut(self, action: str):
        if self._is_renaming:
            return
        if action == "copy":
            self._copy_selected()
        elif action == "cut":
            self._cut_selected()
        elif action == "paste":
            self._paste_clipboard()

    def _select_all(self):
        if self._is_renaming:
            return
        all_children = self.tree.get_children()
        if all_children:
            self.tree.selection_set(all_children)

    def _on_select(self, event):
        if self._is_renaming:
            return
            
        self._destroy_inline_entry()
        sel = self.tree.selection()
        count = len(sel)
        
        if count == 0:
            self.download_btn.configure(state="disabled", text="⬇ Download")
            self.copy_btn.configure(state="disabled", text="📋 Copy")
            self.cut_btn.configure(state="disabled", text="✂ Cut")
            self.rename_btn.configure(state="disabled")
            self.delete_btn.configure(state="disabled", text="🗑 Delete")
            self.status_lbl.configure(text=f"Location: {self.current_path}")
        elif count == 1:
            it = self.items_by_iid.get(sel[0])
            self.download_btn.configure(state="normal", text="⬇ Download")
            self.copy_btn.configure(state="normal", text="📋 Copy")
            self.cut_btn.configure(state="normal", text="✂ Cut")
            self.rename_btn.configure(state="normal")
            self.delete_btn.configure(state="normal", text="🗑 Delete")
            if it:
                self.status_lbl.configure(text=f"Selected: {it['name']} ({it['size_formatted']})")
        else:
            self.download_btn.configure(state="normal", text=f"⬇ Download ({count})")
            self.copy_btn.configure(state="normal", text=f"📋 Copy ({count})")
            self.cut_btn.configure(state="normal", text=f"✂ Cut ({count})")
            self.rename_btn.configure(state="disabled")
            self.delete_btn.configure(state="normal", text=f"🗑 Delete ({count})")
            self.status_lbl.configure(text=f"Selected {count} items")

    def _show_context_menu(self, event):
        if self._is_renaming:
            return
            
        row_id = self.tree.identify_row(event.y)
        if row_id:
            if row_id not in self.tree.selection():
                self.tree.selection_set(row_id)
                
        sel = self.tree.selection()
        count = len(sel)
        
        # Determine if selected item is a database file
        is_db = False
        # Determine if selected item is a file (can be opened in Database Studio)
        is_file = False
        if count == 1:
            it = self.items_by_iid.get(sel[0])
            if it and not it["is_dir"]:
                is_file = True

        rename_state = "normal" if count == 1 else "disabled"
        action_state = "normal" if count > 0 else "disabled"
        db_state = "normal" if is_file else "disabled"

        self.context_menu.set_item_state("open_db", db_state)
        self.context_menu.set_item_state("copy", action_state)
        self.context_menu.set_item_state("cut", action_state)
        self.context_menu.set_item_state("rename", rename_state)
        self.context_menu.set_item_state("delete", action_state)
        self.context_menu.set_item_state("download", action_state)

        self.context_menu.show(event.x_root, event.y_root)

    # In-Place Inline Renaming with Protected State & Active Caret
    def _rename_selected(self):
        sel = self.tree.selection()
        if len(sel) != 1:
            return
        iid = sel[0]
        self._start_inline_rename(iid)

    def _start_inline_rename(self, iid):
        self._is_renaming = True
        it = self.items_by_iid.get(iid)
        if not it:
            self._is_renaming = False
            return
            
        self.tree.see(iid)
        
        bbox = self.tree.bbox(iid, "#0") or self.tree.bbox(iid)
        if not bbox:
            self.after(50, lambda: self._start_inline_rename(iid))
            return
            
        x, y, w, h = bbox
        icon_offset = 26
        entry_x = x + icon_offset
        entry_w = max(200, w - icon_offset)
        
        is_dark = ctk.get_appearance_mode() == "Dark"
        bg_color = "#0f172a" if is_dark else "#ffffff"
        fg_color = "#38bdf8" if is_dark else "#0284c7"
        caret_color = "#38bdf8" if is_dark else "#0284c7"
        
        font_family = "SF Pro Text" if self.is_mac else ("Segoe UI" if sys.platform.startswith("win") else "Ubuntu")
        
        if self.inline_entry:
            try:
                self.inline_entry.destroy()
            except Exception:
                pass
                
        self.inline_entry = tk.Entry(
            self.tree,
            bg=bg_color,
            fg=fg_color,
            insertbackground=caret_color,
            insertwidth=2,
            insertontime=600,
            insertofftime=300,
            selectbackground="#0284c7",
            selectforeground="#ffffff",
            relief="solid",
            bd=1,
            font=(font_family, 10, "bold")
        )
        self.inline_entry.place(x=entry_x, y=y, width=entry_w, height=h)
        self.inline_entry.insert(0, it["name"])
        
        if it["is_dir"] or not "." in it["name"]:
            self.inline_entry.select_range(0, "end")
            self.inline_entry.icursor("end")
        else:
            base_len = len(os.path.splitext(it["name"])[0])
            self.inline_entry.select_range(0, base_len)
            self.inline_entry.icursor(base_len)
            
        self.inline_entry.focus_force()
        self.after(30, lambda: self.inline_entry.focus_force() if self.inline_entry else None)
        
        self.inline_entry.bind("<Return>", lambda e: self._commit_inline_rename(iid))
        self.inline_entry.bind("<Escape>", lambda e: self._cancel_inline_rename())

    def _commit_inline_rename(self, iid):
        if not self.inline_entry:
            self._is_renaming = False
            return
            
        new_name = self.inline_entry.get().strip()
        self._destroy_inline_entry()
        self._is_renaming = False
        
        it = self.items_by_iid.get(iid)
        if not it or not new_name or new_name == it["name"]:
            return
            
        self.status_lbl.configure(text=f"⏳ Renaming to {new_name}...")
        
        def run():
            ok, msg = self.fm.rename_item(self.serial, it["path"], new_name)
            if ok:
                self.after(0, lambda: self.status_lbl.configure(text=f"✅ Renamed to {new_name}"))
            else:
                self.after(0, lambda: self.status_lbl.configure(text=f"❌ {msg}"))
            self.after(0, lambda: self.load_directory(self.current_path, force_refresh=True))
            
        threading.Thread(target=run, daemon=True).start()

    def _cancel_inline_rename(self):
        self._destroy_inline_entry()
        self._is_renaming = False

    def _destroy_inline_entry(self):
        if self.inline_entry:
            try:
                self.inline_entry.destroy()
            except Exception:
                pass
            self.inline_entry = None

    # Instant New Folder with Protected Caret
    def _create_folder(self):
        self._destroy_inline_entry()
        self._is_renaming = False
        
        existing = self.fm.get_existing_names(self.serial, self.current_path)
        new_folder_name = self.fm.generate_unique_name(existing, "New Folder", is_dir=True)
        new_folder_path = f"{self.current_path}/{new_folder_name}".replace("//", "/")
        
        self.status_lbl.configure(text=f"⏳ Creating folder...")
        
        def run():
            ok, msg = self.fm.create_folder(self.serial, new_folder_path)
            if ok:
                self.after(0, lambda: self._on_new_folder_created(new_folder_name))
            else:
                self.after(0, lambda: self.status_lbl.configure(text=f"❌ {msg}"))
                
        threading.Thread(target=run, daemon=True).start()

    def _on_new_folder_created(self, folder_name):
        self._pending_rename_name = folder_name
        self.load_directory(self.current_path, force_refresh=True)

    # 2-Way Cross-OS Copy (Instant Phone Clipboard + Background OS Staging for Windows)
    def _copy_selected(self):
        sel = self.tree.selection()
        if not sel:
            self.status_lbl.configure(text="ℹ Please select a file or folder to copy first.")
            return
        items = [self.items_by_iid[iid] for iid in sel if iid in self.items_by_iid]
        if not items:
            return
            
        # 1. Immediately store in app's internal clipboard for instant phone-to-phone paste
        self.clipboard = {"mode": "copy", "items": items}
        self.paste_btn.configure(text=f"📋 Paste ({len(items)})", fg_color=("#0284c7", "#0369a1"))
        self.status_lbl.configure(text=f"📋 Copied {len(items)} item(s)! Ready to Paste in app or Windows (Ctrl+V)")
        
        # 2. Asynchronously stage to computer in background so user can also Ctrl+V on Windows Desktop/Explorer!
        def run_stage_to_os():
            staged_paths = []
            for it in items:
                ok, _ = self.fm.download_file(self.serial, it["path"], self.staging_dir)
                if ok:
                    local_p = os.path.join(self.staging_dir, os.path.basename(it["path"]))
                    if os.path.exists(local_p):
                        staged_paths.append(os.path.abspath(local_p))
            if staged_paths:
                # Set OS clipboard on main UI thread (Windows API requirement)
                self.after(0, lambda: self._set_os_clipboard(staged_paths, len(items)))
                
        threading.Thread(target=run_stage_to_os, daemon=True).start()

    def _set_os_clipboard(self, staged_paths, total_count):
        """Must run on main UI thread - Windows clipboard API requirement."""
        if staged_paths:
            ok = SystemClipboardHelper.set_copied_files(staged_paths)
            if ok:
                self.status_lbl.configure(
                    text=f"✅ Copied {len(staged_paths)} item(s)! Ready to Paste (Ctrl+V) in app or on Windows Desktop/Explorer."
                )

    def _cut_selected(self):
        sel = self.tree.selection()
        if not sel:
            self.status_lbl.configure(text="ℹ Please select a file or folder to cut first.")
            return
        items = [self.items_by_iid[iid] for iid in sel if iid in self.items_by_iid]
        if not items:
            return
            
        self.clipboard = {"mode": "cut", "items": items}
        self.paste_btn.configure(text=f"✂ Paste ({len(items)})", fg_color=("#ea580c", "#c2410c"))
        self.status_lbl.configure(text=f"✂ Cut {len(items)} item(s)! Ready to Paste (Ctrl+V) in any folder.")

    # 2-Way Cross-OS Paste (Windows/Mac -> Phone OR Phone Internal Duplicate)
    def _paste_clipboard(self):
        # 1. Check if user copied EXTERNAL files from Windows Explorer / Desktop (files NOT in our internal staging cache)
        host_files = SystemClipboardHelper.get_copied_files()
        external_host_files = [
            f for f in host_files 
            if os.path.exists(f) and not os.path.abspath(f).startswith(os.path.abspath(self.staging_dir))
        ]
        
        # If external OS files are present, upload them from computer to phone
        if external_host_files:
            self.status_lbl.configure(text=f"⏳ Uploading {len(external_host_files)} file(s) from computer clipboard...")
            def run_host_upload():
                count = 0
                for f in external_host_files:
                    ok, _ = self.fm.upload_file(self.serial, f, self.current_path)
                    if ok:
                        count += 1
                self.after(0, lambda: self.status_lbl.configure(text=f"✅ Pasted & uploaded {count} file(s) from computer to phone!"))
                self.after(0, lambda: self.load_directory(self.current_path, force_refresh=True))
            threading.Thread(target=run_host_upload, daemon=True).start()
            return
            
        # 2. Otherwise, perform internal phone-to-phone copy/move (with +1 auto-increment)
        if self.clipboard.get("items"):
            items = list(self.clipboard["items"])
            mode = self.clipboard.get("mode", "copy")
            target_dir = self.current_path
            
            action_word = "Copying" if mode == "copy" else "Moving"
            self.status_lbl.configure(text=f"⏳ {action_word} {len(items)} item(s)...")
            
            def run_internal():
                count = 0
                for it in items:
                    if mode == "copy":
                        ok, _ = self.fm.copy_item(self.serial, it["path"], target_dir, is_dir=it["is_dir"])
                    else:
                        ok, _ = self.fm.move_item(self.serial, it["path"], target_dir, is_dir=it["is_dir"])
                    if ok:
                        count += 1
                        
                if mode == "cut":
                    self.clipboard = {"mode": None, "items": []}
                    self.after(0, lambda: self.paste_btn.configure(text="📋 Paste", fg_color=("#334155", "#1e293b")))
                    
                self.after(0, lambda: self._on_paste_finished(count, mode))
                
            threading.Thread(target=run_internal, daemon=True).start()
            return

        # 3. Fallback: If host_files has staged files (e.g. from earlier copy)
        if host_files:
            valid_host_files = [f for f in host_files if os.path.exists(f)]
            if valid_host_files:
                self.status_lbl.configure(text=f"⏳ Pasting {len(valid_host_files)} file(s) from clipboard...")
                def run_fallback_upload():
                    count = 0
                    for f in valid_host_files:
                        ok, _ = self.fm.upload_file(self.serial, f, self.current_path)
                        if ok:
                            count += 1
                    self.after(0, lambda: self.status_lbl.configure(text=f"✅ Pasted {count} file(s) successfully!"))
                    self.after(0, lambda: self.load_directory(self.current_path, force_refresh=True))
                threading.Thread(target=run_fallback_upload, daemon=True).start()
                return

        self.status_lbl.configure(text="ℹ Clipboard is empty. Copy files first with Ctrl+C (in app or from Windows).")

    def _on_paste_finished(self, count, mode):
        action_word = "Copied" if mode == "copy" else "Moved"
        self.status_lbl.configure(text=f"✅ {action_word} {count} item(s) successfully (+1 auto-increment handled)")
        self.load_directory(self.current_path, force_refresh=True)

    def load_directory(self, remote_path: str, force_refresh: bool = False, is_back: bool = False):
        self._destroy_inline_entry()
        self._is_renaming = False
        if self._is_loading:
            return
            
        remote_path = self.fm.normalize_path(remote_path)
        self.path_entry.delete(0, "end")
        self.path_entry.insert(0, remote_path)
        
        if not force_refresh:
            cache_key = (self.serial, remote_path)
            if cache_key in self.fm.cache:
                items = self.fm.cache[cache_key]
                self._on_dir_loaded(remote_path, True, items, "", is_back=is_back)
                return
                
        self._is_loading = True
        self.status_lbl.configure(text=f"⏳ Loading {remote_path}...")
        
        def run():
            success, items, err = self.fm.list_directory(self.serial, remote_path, use_cache=not force_refresh)
            self._is_loading = False
            self.after(0, lambda: self._on_dir_loaded(remote_path, success, items, err, is_back=is_back))
            
        threading.Thread(target=run, daemon=True).start()

    def _on_dir_loaded(self, path, success, items, err, is_back: bool = False):
        if not success:
            self.status_lbl.configure(text=f"⚠ {err or 'Failed to load directory'}")
            return
            
        if not is_back and self.current_path != path:
            self.history_stack.append(self.current_path)
            
        self.current_path = path
        self.items_by_iid.clear()
        
        self.tree.delete(*self.tree.get_children())
        
        target_rename_iid = None
        
        for it in items:
            name_text = f" {it['icon']}  {it['name']}"
            values = (it["size_formatted"], it["date"], it.get("perms", ""))
            iid = self.tree.insert("", "end", text=name_text, values=values)
            self.items_by_iid[iid] = it
            
            if self._pending_rename_name and self._pending_rename_name == it["name"]:
                target_rename_iid = iid
                self._pending_rename_name = None
                
        self.count_lbl.configure(text=f"{len(items)} items")
        self.status_lbl.configure(text=f"Location: {path}")
        self._on_select(None)
        
        if target_rename_iid:
            self.tree.selection_set(target_rename_iid)
            self.after(100, lambda: self._start_inline_rename(target_rename_iid))

    def _on_double_click(self, event):
        if self._is_renaming:
            return
        sel = self.tree.selection()
        if not sel:
            return
        iid = sel[0]
        it = self.items_by_iid.get(iid)
        if not it:
            return
        if it["is_dir"]:
            self.load_directory(it["path"])
        else:
            # Check if file has database or sql extension
            name_lower = it["name"].lower()
            if any(name_lower.endswith(ext) for ext in (".db", ".sqlite", ".sqlite3", ".db3", ".sql", ".dat")) or "database" in name_lower or "sqlite" in name_lower:
                self._open_selected_in_sqlite_studio()

    def _open_selected_in_sqlite_studio(self):
        sel = self.tree.selection()
        if not sel:
            self.status_lbl.configure(text="ℹ Please select a file first.")
            return
        it = self.items_by_iid.get(sel[0])
        if not it or it["is_dir"]:
            self.status_lbl.configure(text="ℹ Please select a file, not a directory.")
            return
            
        self.status_lbl.configure(text=f"⏳ Pulling {it['name']} from phone to SQLite Studio...")
        
        def run_pull():
            # Pull main file
            ok, _ = self.fm.download_file(self.serial, it["path"], self.staging_dir)
            if not ok:
                self.after(0, lambda: self.status_lbl.configure(text=f"❌ Failed to download {it['name']}"))
                return
                
            local_file = os.path.join(self.staging_dir, os.path.basename(it["path"]))
            
            # Pull WAL & SHM companions if present
            self.fm.download_file(self.serial, it["path"] + "-wal", self.staging_dir)
            self.fm.download_file(self.serial, it["path"] + "-shm", self.staging_dir)
            
            def open_dialog():
                self.status_lbl.configure(text=f"✅ Opened {it['name']} in SQLite Studio")
                from ui.sqlite_studio_dialog import SQLiteStudioDialog
                
                # Smart Header & Content Detection (Magic Header bytes b'SQLite format 3\x00' or SQL script)
                is_sqlite = False
                is_sql_script = False
                initial_sql = None
                
                if os.path.exists(local_file):
                    try:
                        with open(local_file, "rb") as f:
                            header = f.read(16)
                            if header.startswith(b"SQLite format 3\x00"):
                                is_sqlite = True
                    except Exception:
                        pass
                        
                    if not is_sqlite:
                        try:
                            with open(local_file, "r", encoding="utf-8", errors="replace") as f:
                                content = f.read(2048)
                                kw_matches = ["SELECT", "CREATE", "INSERT", "UPDATE", "DELETE", "PRAGMA", "DROP", "ALTER", "--", "/*"]
                                if any(kw in content.upper() for kw in kw_matches):
                                    is_sql_script = True
                                    f.seek(0)
                                    initial_sql = f.read()
                        except Exception:
                            pass

                # If SQLite database or unknown binary/data file, open as DB; if SQL script, open script in tab
                db_to_open = local_file if (is_sqlite or not is_sql_script) else None

                dlg = SQLiteStudioDialog(
                    self,
                    db_path=db_to_open,
                    serial=self.serial,
                    model_name=self.model,
                    remote_path=it["path"],
                    initial_sql=initial_sql,
                    on_saved=lambda: self.load_directory(self.current_path, force_refresh=True)
                )
                dlg.focus_set()
                
            self.after(0, open_dialog)
            
        threading.Thread(target=run_pull, daemon=True).start()

    def _go_back(self):
        self._destroy_inline_entry()
        self._is_renaming = False
        if self.history_stack:
            prev = self.history_stack.pop()
            self.load_directory(prev, is_back=True)

    def _go_up(self):
        self._destroy_inline_entry()
        self._is_renaming = False
        if self.current_path in ("/", ""):
            return
        parent = os.path.dirname(self.current_path.rstrip("/"))
        if not parent:
            parent = "/"
        self.load_directory(parent)

    def _upload_file(self):
        self._destroy_inline_entry()
        self._is_renaming = False
        local_files = filedialog.askopenfilenames(title="Select file(s) to upload to phone")
        if not local_files:
            return
            
        self.status_lbl.configure(text=f"⏳ Uploading {len(local_files)} file(s)...")
        
        def run():
            count = 0
            for f in local_files:
                ok, msg = self.fm.upload_file(self.serial, f, self.current_path)
                if ok:
                    count += 1
            self.after(0, lambda: self._on_upload_finished(count))
            
        threading.Thread(target=run, daemon=True).start()

    def _on_upload_finished(self, count):
        self.status_lbl.configure(text=f"✅ Uploaded {count} file(s) successfully!")
        self.load_directory(self.current_path, force_refresh=True)

    def _download_selected(self):
        self._destroy_inline_entry()
        self._is_renaming = False
        sel = self.tree.selection()
        if not sel:
            self.status_lbl.configure(text="⚠ Please select item(s) to download")
            return
            
        save_folder = filedialog.askdirectory(title="Select folder on computer to save file(s)")
        if not save_folder:
            return
            
        items_to_dl = [self.items_by_iid[iid] for iid in sel if iid in self.items_by_iid]
        self.status_lbl.configure(text=f"⏳ Downloading {len(items_to_dl)} item(s)...")
        
        def run():
            count = 0
            for it in items_to_dl:
                ok, msg = self.fm.download_file(self.serial, it["path"], save_folder)
                if ok:
                    count += 1
            self.after(0, lambda: self.status_lbl.configure(text=f"✅ Downloaded {count} item(s) to {save_folder}"))
            
        threading.Thread(target=run, daemon=True).start()

    def _delete_selected(self):
        self._destroy_inline_entry()
        self._is_renaming = False
        sel = self.tree.selection()
        if not sel:
            self.status_lbl.configure(text="⚠ Please select item(s) to delete")
            return
            
        items_to_del = [self.items_by_iid[iid] for iid in sel if iid in self.items_by_iid]
        count = len(items_to_del)
        
        if count == 1:
            item_name = items_to_del[0]["name"]
            msg = f"Are you sure you want to delete '{item_name}' permanently from the phone?"
            confirm_btn_text = "Delete"
        else:
            names_preview = ", ".join(it["name"] for it in items_to_del[:3])
            if count > 3:
                names_preview += f" and {count - 3} more"
            msg = f"Are you sure you want to delete {count} items ({names_preview}) permanently from the phone?"
            confirm_btn_text = f"Delete ({count})"
            
        confirmed = ask_confirm(
            self.winfo_toplevel(),
            title="Delete Confirmation",
            message=msg,
            confirm_text=confirm_btn_text,
            is_destructive=True
        )
        
        if confirmed:
            def run():
                for it in items_to_del:
                    self.fm.delete_item(self.serial, it["path"])
                self.after(0, lambda: self.load_directory(self.current_path, force_refresh=True))
                
            threading.Thread(target=run, daemon=True).start()
