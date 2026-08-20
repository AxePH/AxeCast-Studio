import re
import sys
import time
import tkinter as tk
from tkinter import ttk
import customtkinter as ctk

SQL_KEYWORDS = [
    "SELECT", "FROM", "WHERE", "INNER JOIN", "LEFT JOIN", "RIGHT JOIN", "FULL JOIN",
    "CROSS JOIN", "JOIN", "ON", "GROUP BY", "ORDER BY", "HAVING", "LIMIT", "OFFSET",
    "INSERT INTO", "INSERT", "VALUES", "UPDATE", "SET", "DELETE FROM", "DELETE",
    "CREATE TABLE", "CREATE VIEW", "CREATE INDEX", "CREATE TRIGGER", "CREATE",
    "DROP TABLE", "DROP VIEW", "DROP INDEX", "DROP", "ALTER TABLE", "ALTER",
    "ADD COLUMN", "RENAME TO", "TABLE", "VIEW", "INDEX", "TRIGGER", "DATABASE",
    "AND", "OR", "NOT", "IN", "IS NULL", "IS NOT NULL", "IS", "NULL", "LIKE", "GLOB",
    "BETWEEN", "EXISTS", "CASE", "WHEN", "THEN", "ELSE", "END", "AS", "DISTINCT",
    "ALL", "UNION ALL", "UNION", "INTERSECT", "EXCEPT", "WITH RECURSIVE", "WITH",
    "PRAGMA", "VACUUM", "BEGIN TRANSACTION", "COMMIT", "ROLLBACK", "TRANSACTION",
    "PRIMARY KEY", "FOREIGN KEY", "REFERENCES", "NOT NULL", "UNIQUE", "CHECK", "DEFAULT",
    "AUTOINCREMENT", "CASCADE", "RESTRICT", "NO ACTION"
]

SQL_FUNCTIONS = [
    "COUNT", "SUM", "AVG", "MIN", "MAX", "TOTAL", "LENGTH", "LOWER", "UPPER",
    "SUBSTR", "TRIM", "LTRIM", "RTRIM", "REPLACE", "INSTR", "HEX", "QUOTE",
    "COALESCE", "IFNULL", "NULLIF", "ROUND", "ABS", "RANDOM", "ZEROBLOB",
    "TYPEOF", "LAST_INSERT_ROWID", "CHANGES", "TOTAL_CHANGES",
    "DATE", "TIME", "DATETIME", "JULIANDAY", "STRFTIME",
    "JSON", "JSON_ARRAY", "JSON_OBJECT", "JSON_EXTRACT", "GROUP_CONCAT"
]

SQL_TYPES = [
    "INTEGER", "INT", "BIGINT", "SMALLINT", "TINYINT",
    "TEXT", "VARCHAR", "CHAR", "CLOB", "NVARCHAR",
    "REAL", "DOUBLE", "FLOAT", "NUMERIC", "DECIMAL",
    "BLOB", "BOOLEAN", "DATE", "DATETIME", "TIMESTAMP"
]

class SQLEditorWidget(ctk.CTkFrame):
    """Modern SQL Editor with Line Numbers, Real-time Syntax Highlighting & Intellisense."""

    def __init__(self, master, on_execute=None, on_cancel=None, on_format=None, on_save=None, on_refresh=None, on_new_tab=None, on_close_tab=None, **kwargs):
        super().__init__(master, fg_color=("#f8fafc", "#0f172a"), corner_radius=8, **kwargs)
        
        self.on_execute = on_execute
        self.on_cancel = on_cancel
        self.on_format = on_format
        self.on_save = on_save
        self.on_refresh = on_refresh
        self.on_new_tab = on_new_tab
        self.on_close_tab = on_close_tab
        self.schema_tables = []
        self.schema_columns = []
        self._highlight_job = None  # Debounce timer for syntax highlighting
        self._intellisense_job = None  # Debounce timer for IntelliSense popup
        
        self.font_family = "Consolas" if sys.platform.startswith("win") else "Menlo"
        self.editor_font = (self.font_family, 11)
        self.gutter_font = (self.font_family, 11)
        
        self._build_ui()
        self._setup_highlighting_tags()
        self._setup_intellisense_popup()
        self._setup_context_menu()
        self._bind_events()

    def _build_ui(self):
        # Container frame
        self.container = tk.Frame(self, bg="#0f172a")
        self.container.pack(fill="both", expand=True, padx=2, pady=2)

        # Line numbers gutter
        self.gutter = tk.Text(
            self.container,
            width=4,
            padx=4,
            pady=6,
            takefocus=0,
            border=0,
            background="#1e293b",
            foreground="#64748b",
            font=self.gutter_font,
            state="disabled",
            wrap="none",
            cursor="arrow"
        )
        self.gutter.pack(side="left", fill="y")

        # Scrollbars
        self.v_scroll = ttk.Scrollbar(self.container, orient="vertical")
        self.v_scroll.pack(side="right", fill="y")
        
        self.h_scroll = ttk.Scrollbar(self.container, orient="horizontal")
        self.h_scroll.pack(side="bottom", fill="x")

        # Main text editor
        self.text = tk.Text(
            self.container,
            wrap="none",
            undo=True,
            maxundo=50,
            border=0,
            padx=8,
            pady=6,
            background="#0f172a",
            foreground="#f8fafc",
            insertbackground="#38bdf8",  # Cyan blinking cursor
            selectbackground="#0369a1",  # Blue selection
            selectforeground="#ffffff",
            font=self.editor_font,
            yscrollcommand=self._on_text_vscroll,
            xscrollcommand=self.h_scroll.set
        )
        self.text.pack(side="left", fill="both", expand=True)
        
        self.v_scroll.config(command=self._on_vscroll_move)
        self.h_scroll.config(command=self.text.xview)

    def _on_text_vscroll(self, *args):
        self.v_scroll.set(*args)
        self.gutter.yview_moveto(args[0])

    def _on_vscroll_move(self, *args):
        self.text.yview(*args)
        self.gutter.yview(*args)

    def _setup_highlighting_tags(self):
        self.apply_theme()

    def apply_theme(self):
        """Dynamically adapts editor colors and syntax highlighting between Light and Dark mode."""
        is_dark = ctk.get_appearance_mode() == "Dark"
        
        bg_main = "#0f172a" if is_dark else "#ffffff"
        fg_main = "#f8fafc" if is_dark else "#0f172a"
        bg_gutter = "#1e293b" if is_dark else "#f1f5f9"
        fg_gutter = "#64748b" if is_dark else "#94a3b8"
        insert_bg = "#38bdf8" if is_dark else "#0284c7"
        sel_bg = "#0369a1" if is_dark else "#bae6fd"
        sel_fg = "#ffffff" if is_dark else "#0f172a"

        if hasattr(self, "container"):
            self.container.config(bg=bg_main)
        if hasattr(self, "gutter"):
            self.gutter.config(background=bg_gutter, foreground=fg_gutter)
        if hasattr(self, "text"):
            self.text.config(
                background=bg_main,
                foreground=fg_main,
                insertbackground=insert_bg,
                selectbackground=sel_bg,
                selectforeground=sel_fg
            )

            # Syntax colors — use same font size without bold to prevent cursor jitter
            if is_dark:
                self.text.tag_configure("kw", foreground="#38bdf8")
                self.text.tag_configure("func", foreground="#fbbf24")
                self.text.tag_configure("type", foreground="#34d399")
                self.text.tag_configure("str", foreground="#a3e635")
                self.text.tag_configure("num", foreground="#c084fc")
                self.text.tag_configure("comment", foreground="#64748b")
                self.text.tag_configure("table", foreground="#f472b6")
            else:
                self.text.tag_configure("kw", foreground="#0284c7")
                self.text.tag_configure("func", foreground="#d97706")
                self.text.tag_configure("type", foreground="#059669")
                self.text.tag_configure("str", foreground="#15803d")
                self.text.tag_configure("num", foreground="#7c3aed")
                self.text.tag_configure("comment", foreground="#94a3b8")
                self.text.tag_configure("table", foreground="#db2777")

        if hasattr(self, "suggest_list"):
            self.suggest_list.config(
                bg=bg_main,
                fg=fg_main,
                selectbackground="#0284c7",
                selectforeground="#ffffff"
            )

        if hasattr(self, "text"):
            self.highlight_syntax()

    def _setup_intellisense_popup(self):
        self.popup = tk.Toplevel(self)
        self.popup.withdraw()
        self.popup.overrideredirect(True)
        self.popup.attributes("-topmost", True)
        
        frame = tk.Frame(self.popup, bg="#1e293b", bd=1, relief="solid")
        frame.pack(fill="both", expand=True)

        self.suggest_list = tk.Listbox(
            frame,
            bg="#0f172a",
            fg="#f8fafc",
            selectbackground="#0284c7",
            selectforeground="#ffffff",
            font=self.editor_font,
            bd=0,
            highlightthickness=0,
            height=6,
            activestyle="none"
        )
        self.suggest_list.pack(fill="both", expand=True, padx=1, pady=1)
        self.suggest_list.bind("<Double-Button-1>", lambda e: self._insert_selected_suggestion())

    def _bind_events(self):
        # Core keyboard handlers — _on_key_press handles ALL Ctrl/Cmd shortcuts
        # to avoid Tkinter's buggy NumLock modifier matching on Windows.
        self.text.bind("<KeyRelease>", self._on_key_release)
        self.text.bind("<Key>", self._on_key_press)
        self.text.bind("<Tab>", self._handle_tab)
        self.text.bind("<Shift-Tab>", self._handle_shift_tab)
        self.text.bind("<Button-1>", lambda e: self._hide_popup())

        # Non-letter shortcuts (safe from NumLock bug)
        self.text.bind("<F5>", lambda e: self._trigger_execute())
        self.text.bind("<Control-Return>", lambda e: self._trigger_execute())
        self.text.bind("<Control-space>", lambda e: self._trigger_intellisense_manual())

        # Right-Click Context Menu
        self.text.bind("<Button-3>", self._show_context_menu)
        self.text.bind("<Button-2>", self._show_context_menu)

    def _copy_text(self, event=None):
        """Copies selected text to system clipboard with 100% reliability."""
        try:
            sel = self.text.get("sel.first", "sel.last")
            if sel:
                self.clipboard_clear()
                self.clipboard_append(sel)
        except Exception:
            pass
        return "break"

    def _cut_text(self, event=None):
        """Cuts selected text to system clipboard with 100% reliability."""
        try:
            sel = self.text.get("sel.first", "sel.last")
            if sel:
                self.clipboard_clear()
                self.clipboard_append(sel)
                self.text.delete("sel.first", "sel.last")
                self._update_line_numbers()
                self.highlight_syntax()
        except Exception:
            pass
        return "break"

    def _paste_text(self, event=None):
        """Pastes text from system clipboard with 100% reliability."""
        try:
            clip = self.clipboard_get()
            if clip:
                if self.text.tag_ranges("sel"):
                    self.text.delete("sel.first", "sel.last")
                self.text.insert("insert", clip)
                self._update_line_numbers()
                self.highlight_syntax()
        except Exception:
            pass
        return "break"

    def _setup_context_menu(self):
        from ui.modern_context_menu import ModernContextMenu
        self.context_menu = ModernContextMenu(self)

        self.context_menu.add_item(icon="▶", label="Run Selected / All", shortcut="F5", command=self._trigger_execute)
        self.context_menu.add_item(icon="⚡", label="Format SQL", shortcut="Ctrl+Shift+F", command=self._trigger_format)
        self.context_menu.add_item(icon="💬", label="Toggle Comment", shortcut="Ctrl+/", command=self._toggle_comment)
        self.context_menu.add_item(icon="📋", label="Duplicate Line", shortcut="Ctrl+D", command=self._duplicate_line)
        self.context_menu.add_separator()
        self.context_menu.add_item(icon="✂", label="Cut", shortcut="Ctrl+X", command=self._cut_text)
        self.context_menu.add_item(icon="📋", label="Copy", shortcut="Ctrl+C", command=self._copy_text)
        self.context_menu.add_item(icon="📥", label="Paste", shortcut="Ctrl+V", command=self._paste_text)
        self.context_menu.add_item(icon="🔲", label="Select All", shortcut="Ctrl+A", command=self._select_all)
        self.context_menu.add_separator()
        if self.on_save:
            self.context_menu.add_item(icon="💾", label="Save & Sync to Phone", shortcut="Ctrl+S", command=self._trigger_save)
        if self.on_refresh:
            self.context_menu.add_item(icon="🔄", label="Refresh Schema", shortcut="Ctrl+R", command=self._trigger_refresh)
        if self.on_new_tab:
            self.context_menu.add_item(icon="📑", label="New Tab", shortcut="Ctrl+T", command=self._trigger_new_tab)
        self.context_menu.add_item(icon="🗑", label="Clear Editor", command=self._clear_editor)

    def _show_context_menu(self, event):
        """Displays rich 2-column right-click context menu inside SQL Editor."""
        now = time.time()
        if hasattr(self, "_last_ctx_time") and now - self._last_ctx_time < 0.25:
            return "break"
        self._last_ctx_time = now
        
        self._hide_popup()
        if not hasattr(self, "context_menu") or not self.context_menu:
            self._setup_context_menu()
        self.context_menu.show(event.x_root, event.y_root)
        return "break"

    def _toggle_comment(self, event=None):
        """Toggles SQL line comment '-- ' on current line or all selected lines."""
        try:
            sel_start = self.text.index("sel.first linestart")
            sel_end = self.text.index("sel.last lineend")
            start_line = int(sel_start.split(".")[0])
            end_line = int(sel_end.split(".")[0])
        except Exception:
            start_line = int(self.text.index("insert").split(".")[0])
            end_line = start_line

        lines = []
        for l in range(start_line, end_line + 1):
            line_txt = self.text.get(f"{l}.0", f"{l}.end")
            lines.append(line_txt)

        all_commented = all(l.strip().startswith("--") for l in lines if l.strip())

        for l in range(start_line, end_line + 1):
            line_txt = self.text.get(f"{l}.0", f"{l}.end")
            if all_commented:
                if line_txt.startswith("-- "):
                    self.text.delete(f"{l}.0", f"{l}.3")
                elif line_txt.startswith("--"):
                    self.text.delete(f"{l}.0", f"{l}.2")
            else:
                self.text.insert(f"{l}.0", "-- ")

        self._update_line_numbers()
        self.highlight_syntax()
        return "break"

    def _duplicate_line(self, event=None):
        """Duplicates the current line below."""
        line_num = self.text.index("insert").split(".")[0]
        line_content = self.text.get(f"{line_num}.0", f"{line_num}.end")
        self.text.insert(f"{line_num}.end", "\n" + line_content)
        self._update_line_numbers()
        self.highlight_syntax()
        return "break"

    def _select_all(self, event=None):
        self.text.tag_add("sel", "1.0", "end-1c")
        self.text.mark_set("insert", "1.0")
        return "break"

    def _clear_editor(self):
        self.text.delete("1.0", "end")
        self._update_line_numbers()
        self.highlight_syntax()

    def _trigger_format(self, event=None):
        if self.on_format:
            self.on_format()
        return "break"

    def _trigger_save(self, event=None):
        if self.on_save:
            self.on_save()
        return "break"

    def _trigger_refresh(self, event=None):
        if self.on_refresh:
            self.on_refresh()
        return "break"

    def _trigger_new_tab(self, event=None):
        if self.on_new_tab:
            self.on_new_tab()
        return "break"

    def _trigger_close_tab(self, event=None):
        if self.on_close_tab:
            self.on_close_tab()
        return "break"

    def update_schema_symbols(self, schema_dict: dict):
        """Updates the vocabulary of tables and columns for autocompletion and highlighting."""
        tables = []
        columns = []
        for t_name, t_data in schema_dict.get("tables", {}).items():
            tables.append(t_name)
            for c in t_data.get("columns", []):
                columns.append(c["name"])
        for v_name, v_data in schema_dict.get("views", {}).items():
            tables.append(v_name)
            for c in v_data.get("columns", []):
                columns.append(c["name"])
                
        self.schema_tables = sorted(list(set(tables)))
        self.schema_columns = sorted(list(set(columns)))
        self.highlight_syntax()

    def set_text(self, sql_content: str):
        self.text.delete("1.0", "end")
        self.text.insert("1.0", sql_content)
        self._update_line_numbers()
        self.highlight_syntax()

    def get_text(self) -> str:
        return self.text.get("1.0", "end-1c")

    def get_selected_text_or_all(self) -> str:
        try:
            sel = self.text.get("sel.first", "sel.last")
            if sel.strip():
                return sel
        except Exception:
            pass
        return self.get_text()

    def _trigger_execute(self):
        self._hide_popup()
        if self.on_execute:
            self.on_execute(self.get_selected_text_or_all())
        return "break"

    def _handle_tab(self, event):
        if self.popup.winfo_ismapped():
            self._insert_selected_suggestion()
            return "break"
        # Otherwise insert 4 spaces
        self.text.insert("insert", "    ")
        return "break"

    def _handle_shift_tab(self, event):
        # Remove up to 4 leading spaces from current line
        line = self.text.get("insert linestart", "insert lineend")
        if line.startswith("    "):
            self.text.delete("insert linestart", "insert linestart + 4 chars")
        elif line.startswith("  "):
            self.text.delete("insert linestart", "insert linestart + 2 chars")
        return "break"

    def _on_key_press(self, event):
        # Universal Shortcut Router (captures English, Thai, CapsLock, Ctrl/Cmd)
        # Fix: On Windows/Linux, bit 0x8 is NumLock (not Ctrl). Only use bit 0x4 for Ctrl.
        # On macOS, bit 0x8 is Command ⌘ which is the correct primary modifier.
        if sys.platform == "darwin":
            is_ctrl = bool(event.state & 4) or bool(event.state & 8)  # Ctrl or Command ⌘
        else:
            is_ctrl = bool(event.state & 4)  # Ctrl only (Windows/Linux)
        kc = getattr(event, "keycode", 0)
        ks = str(getattr(event, "keysym", "")).lower()
        ch = getattr(event, "char", "")

        if is_ctrl:
            # Copy: Ctrl+C (Keycode 67, char \x03, or keysym c/thai)
            if kc == 67 or ks in ('c', 'thai_saraae') or ch == '\x03':
                return self._copy_text()
            # Paste: Ctrl+V (Keycode 86, char \x16, or keysym v/thai)
            if kc == 86 or ks in ('v', 'thai_oang') or ch == '\x16':
                return self._paste_text()
            # Cut: Ctrl+X (Keycode 88, char \x18, or keysym x/thai)
            if kc == 88 or ks in ('x', 'thai_khokhai') or ch == '\x18':
                return self._cut_text()
            # Select All: Ctrl+A (Keycode 65, char \x01, or keysym a/thai)
            if kc == 65 or ks in ('a', 'thai_fofan') or ch == '\x01':
                return self._select_all()
            # Save: Ctrl+S (Keycode 83, char \x13, or keysym s/thai)
            if kc == 83 or ks in ('s', 'thai_sowso') or ch == '\x13':
                return self._trigger_save()
            # Refresh: Ctrl+R (Keycode 82, char \x12, or keysym r/thai)
            if kc == 82 or ks in ('r', 'thai_phosamphao') or ch == '\x12':
                return self._trigger_refresh()
            # New Tab: Ctrl+T (Keycode 84, char \x14, or keysym t/thai)
            if kc == 84 or ks in ('t', 'thai_thothahan') or ch == '\x14':
                return self._trigger_new_tab()
            # Close Tab: Ctrl+W (Keycode 87, char \x17, or keysym w/thai)
            if kc == 87 or ks in ('w', 'thai_wowaen') or ch == '\x17':
                return self._trigger_close_tab()
            # Duplicate Line: Ctrl+D (Keycode 68, char \x04, or keysym d/thai)
            if kc == 68 or ks in ('d', 'thai_dodek') or ch == '\x04':
                return self._duplicate_line()
            # Comment: Ctrl+/
            if ks in ('slash', 'question', 'thai_saraam'):
                return self._toggle_comment()

        if self.popup.winfo_ismapped():
            if event.keysym in ("Up", "Down"):
                cur = self.suggest_list.curselection()
                idx = cur[0] if cur else 0
                if event.keysym == "Up":
                    idx = max(0, idx - 1)
                else:
                    idx = min(self.suggest_list.size() - 1, idx + 1)
                self.suggest_list.selection_clear(0, "end")
                self.suggest_list.selection_set(idx)
                self.suggest_list.activate(idx)
                self.suggest_list.see(idx)
                return "break"
            elif event.keysym in ("Return", "KP_Enter"):
                self._insert_selected_suggestion()
                return "break"
            elif event.keysym == "Escape":
                self._hide_popup()
                return "break"

    def _on_key_release(self, event):
        self._update_line_numbers()
        self._schedule_highlight()
        
        # Don't trigger intellisense on navigation keys
        if event.keysym in ("Up", "Down", "Left", "Right", "Escape", "Control_L", "Control_R", "Shift_L", "Shift_R", "Alt_L", "Alt_R", "Return", "F5", "Tab", "BackSpace", "Delete"):
            return

        # Debounce IntelliSense popup (300ms delay to avoid jitter)
        if self._intellisense_job:
            self.after_cancel(self._intellisense_job)
        self._intellisense_job = self.after(300, self._check_intellisense)

    def _check_intellisense(self):
        """Debounced IntelliSense check — runs 300ms after last keystroke."""
        self._intellisense_job = None
        word, start_idx = self._get_current_word()
        if len(word) >= 2:
            self._show_intellisense(word, start_idx)
        else:
            self._hide_popup()

    def _schedule_highlight(self):
        """Debounced syntax highlighting — runs 150ms after last keystroke to reduce jitter."""
        if self._highlight_job:
            self.after_cancel(self._highlight_job)
        self._highlight_job = self.after(150, self._do_highlight)

    def _do_highlight(self):
        """Execute the actual syntax highlighting after debounce."""
        self._highlight_job = None
        self.highlight_syntax()

    def _update_line_numbers(self):
        line_count = int(self.text.index("end-1c").split(".")[0])
        lines_text = "\n".join(str(i) for i in range(1, line_count + 1))
        
        self.gutter.config(state="normal")
        self.gutter.delete("1.0", "end")
        self.gutter.insert("1.0", lines_text)
        self.gutter.config(state="disabled")
        
        # Match vertical scroll
        self.gutter.yview_moveto(self.text.yview()[0])

    def highlight_syntax(self):
        """Applies SQL syntax highlighting using fast regex token matching."""
        content = self.text.get("1.0", "end-1c")
        if not content:
            return

        # Remove existing tags
        for tag in ("kw", "func", "type", "str", "num", "comment", "table"):
            self.text.tag_remove(tag, "1.0", "end")

        # 1. Comments: -- to end of line
        for match in re.finditer(r"--.*?$", content, re.MULTILINE):
            self._apply_tag_for_match("comment", match)

        # 2. Block Comments: /* ... */
        for match in re.finditer(r"/\*.*?\*/", content, re.DOTALL):
            self._apply_tag_for_match("comment", match)

        # 3. Strings: '...' or "..."
        for match in re.finditer(r"'(?:''|[^'])*'|\"(?:\"\"|[^\"])*\"", content):
            self._apply_tag_for_match("str", match)

        # 4. Numbers
        for match in re.finditer(r"\b\d+(?:\.\d+)?\b", content):
            self._apply_tag_for_match("num", match)

        # 5. Keywords & Functions (case-insensitive words)
        words = re.finditer(r"\b[A-Za-z_][A-Za-z0-9_]*\b", content)
        for match in words:
            w = match.group().upper()
            w_raw = match.group()
            
            if w in SQL_KEYWORDS:
                self._apply_tag_for_match("kw", match)
            elif w in SQL_FUNCTIONS:
                self._apply_tag_for_match("func", match)
            elif w in SQL_TYPES:
                self._apply_tag_for_match("type", match)
            elif w_raw in self.schema_tables or w in [t.upper() for t in self.schema_tables]:
                self._apply_tag_for_match("table", match)

    def _apply_tag_for_match(self, tag_name: str, match):
        start_idx = f"1.0 + {match.start()} chars"
        end_idx = f"1.0 + {match.end()} chars"
        self.text.tag_add(tag_name, start_idx, end_idx)

    def _get_current_word(self):
        cursor_pos = self.text.index("insert")
        line_start = f"{cursor_pos} linestart"
        text_before = self.text.get(line_start, cursor_pos)
        
        match = re.search(r"([A-Za-z0-9_]+)$", text_before)
        if match:
            word = match.group(1)
            start_idx = f"{cursor_pos} - {len(word)} chars"
            return word, start_idx
        return "", cursor_pos

    def _trigger_intellisense_manual(self):
        word, start_idx = self._get_current_word()
        self._show_intellisense(word, start_idx, force_all=True)
        return "break"

    def _show_intellisense(self, word: str, start_idx: str, force_all: bool = False):
        query = word.lower()
        suggestions = []

        # 1. Schema Tables
        for t in self.schema_tables:
            if force_all or query in t.lower():
                suggestions.append((f"📋 {t}", t))

        # 2. Schema Columns
        for c in self.schema_columns:
            if force_all or query in c.lower():
                suggestions.append((f"🔹 {c}", c))

        # 3. SQL Keywords
        for kw in SQL_KEYWORDS:
            if force_all or query in kw.lower():
                suggestions.append((f"⚡ {kw}", kw))

        # 4. Functions
        for fn in SQL_FUNCTIONS:
            if force_all or query in fn.lower():
                suggestions.append((f"⚙ {fn}()", f"{fn}()"))

        if not suggestions:
            self._hide_popup()
            return

        # Deduplicate while preserving order
        seen = set()
        unique_suggestions = []
        for label, val in suggestions:
            if val not in seen:
                seen.add(val)
                unique_suggestions.append((label, val))

        self.current_suggestions = unique_suggestions[:15]
        self.suggest_list.delete(0, "end")
        for label, _ in self.current_suggestions:
            self.suggest_list.insert("end", f" {label} ")

        self.suggest_list.selection_set(0)
        self.suggest_list.activate(0)

        # Position popup directly under cursor
        bbox = self.text.bbox("insert")
        if bbox:
            x, y, _, h = bbox
            root_x = self.text.winfo_rootx() + x
            root_y = self.text.winfo_rooty() + y + h + 2
            
            # Bound check within screen
            popup_h = min(150, len(self.current_suggestions) * 22 + 6)
            self.popup.geometry(f"220x{popup_h}+{root_x}+{root_y}")
            self.popup.deiconify()
            self.popup.lift()
        else:
            self._hide_popup()

    def _insert_selected_suggestion(self):
        if not self.popup.winfo_ismapped() or not hasattr(self, "current_suggestions"):
            return
        cur = self.suggest_list.curselection()
        if not cur:
            return
        idx = cur[0]
        _, replacement = self.current_suggestions[idx]
        
        word, start_idx = self._get_current_word()
        if word:
            self.text.delete(start_idx, "insert")
        self.text.insert("insert", replacement)
        if replacement.endswith("()"):
            self.text.mark_set("insert", "insert - 1 chars")
            
        self._hide_popup()
        self._update_line_numbers()
        self.highlight_syntax()

    def _hide_popup(self):
        if self.popup.winfo_ismapped():
            self.popup.withdraw()

    _highlight_syntax = highlight_syntax
