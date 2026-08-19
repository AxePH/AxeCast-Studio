import sys
import tkinter as tk
import customtkinter as ctk

class ModernContextMenu(ctk.CTkToplevel):
    """
    Modern 2-column Context Menu with distinct icon column (centered) and text column (left-aligned),
    matching CustomTkinter dynamic Dark & Light themes with smooth hover highlights and shortcuts.
    """
    
    _active_menu = None

    def __init__(self, master=None):
        # Always resolve to true toplevel window to avoid invalid nested window paths
        top = None
        if master and hasattr(master, "winfo_toplevel"):
            try:
                top = master.winfo_toplevel()
            except Exception:
                top = master
        else:
            top = master
            
        super().__init__(top)
        
        # Close any previous active menu safely
        if ModernContextMenu._active_menu and ModernContextMenu._active_menu != self:
            try:
                ModernContextMenu._active_menu.hide()
            except Exception:
                pass
        ModernContextMenu._active_menu = self

        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.withdraw()  # Hidden until show() is called
        
        self.is_dark = ctk.get_appearance_mode() == "Dark"
        self.bg_color = "#1e293b" if self.is_dark else "#ffffff"
        self.border_color = "#334155" if self.is_dark else "#cbd5e1"
        self.text_color = "#f8fafc" if self.is_dark else "#0f172a"
        self.hover_bg = "#0284c7"
        self.hover_fg = "#ffffff"
        self.disabled_fg = "#64748b" if self.is_dark else "#94a3b8"
        self.shortcut_fg = "#94a3b8" if self.is_dark else "#64748b"
        self.sep_color = "#334155" if self.is_dark else "#e2e8f0"

        self.font_family = "SF Pro Text" if sys.platform == "darwin" else ("Segoe UI" if sys.platform.startswith("win") else "Ubuntu")

        # Container Frame with border
        self.container = ctk.CTkFrame(
            self,
            fg_color=self.bg_color,
            border_color=self.border_color,
            border_width=1,
            corner_radius=8
        )
        self.container.pack(fill="both", expand=True, padx=0, pady=0)

        self.items = []
        self._item_widgets = {}

        # Global Dismiss Bindings
        self.bind("<FocusOut>", lambda e: self.hide())
        self.bind("<Escape>", lambda e: self.hide())
        if master:
            master_top = master.winfo_toplevel()
            master_top.bind("<Button-1>", self._on_global_click, add="+")
            master_top.bind("<Button-3>", self._on_global_click, add="+")

    def add_item(self, icon: str = "", label: str = "", shortcut: str = "", command=None, state: str = "normal", item_id: str = None):
        """Adds a 2-block row: [ Icon Column (~15% Centered) | Text Column (Left-Aligned) ]"""
        key = item_id or label
        self.items.append({
            "type": "command",
            "key": key,
            "icon": icon,
            "label": label,
            "shortcut": shortcut,
            "command": command,
            "state": state
        })

    def add_separator(self):
        """Adds a thin horizontal divider."""
        self.items.append({"type": "separator"})

    def set_item_state(self, key: str, state: str):
        """Dynamically enables/disables an item."""
        for it in self.items:
            if it.get("key") == key or it.get("label") == key:
                it["state"] = state
                if key in self._item_widgets:
                    w_info = self._item_widgets[key]
                    self._apply_state_to_widget(w_info, state)

    def _apply_state_to_widget(self, w_info, state):
        is_disabled = state == "disabled"
        fg = self.disabled_fg if is_disabled else self.text_color
        sh_fg = self.disabled_fg if is_disabled else self.shortcut_fg
        
        w_info["icon_lbl"].configure(fg=fg)
        w_info["text_lbl"].configure(fg=fg)
        if "sh_lbl" in w_info:
            w_info["sh_lbl"].configure(fg=sh_fg)
        w_info["row"].configure(cursor="arrow" if is_disabled else "hand2")

    def _render_menu(self):
        # Clear existing widgets in container
        for widget in self.container.winfo_children():
            widget.destroy()
        self._item_widgets.clear()

        # Update Theme Colors
        self.is_dark = ctk.get_appearance_mode() == "Dark"
        self.bg_color = "#1e293b" if self.is_dark else "#ffffff"
        self.border_color = "#334155" if self.is_dark else "#cbd5e1"
        self.text_color = "#f8fafc" if self.is_dark else "#0f172a"
        self.disabled_fg = "#64748b" if self.is_dark else "#94a3b8"
        self.shortcut_fg = "#94a3b8" if self.is_dark else "#64748b"
        self.sep_color = "#334155" if self.is_dark else "#e2e8f0"

        self.container.configure(fg_color=self.bg_color, border_color=self.border_color)

        # Padding top
        pad_top = tk.Frame(self.container, height=4, bg=self.bg_color)
        pad_top.pack(fill="x")

        for it in self.items:
            if it["type"] == "separator":
                sep = tk.Frame(self.container, height=1, bg=self.sep_color)
                sep.pack(fill="x", padx=8, pady=4)
                continue

            # Command Row Frame
            row = tk.Frame(self.container, bg=self.bg_color, cursor="hand2" if it["state"] == "normal" else "arrow")
            row.pack(fill="x", padx=4, pady=1)

            # Block 1: Icon Column (Centered, fixed ~32px width = ~15% of width)
            icon_box = tk.Frame(row, width=32, height=26, bg=self.bg_color)
            icon_box.pack(side="left", padx=(4, 2))
            icon_box.pack_propagate(False)

            is_disabled = it["state"] == "disabled"
            curr_fg = self.disabled_fg if is_disabled else self.text_color
            curr_sh_fg = self.disabled_fg if is_disabled else self.shortcut_fg

            icon_lbl = tk.Label(
                icon_box,
                text=it["icon"],
                font=(self.font_family, 11),
                fg=curr_fg,
                bg=self.bg_color,
                anchor="center"
            )
            icon_lbl.pack(fill="both", expand=True)

            # Block 2: Text Column (Left-Aligned)
            text_lbl = tk.Label(
                row,
                text=it["label"],
                font=(self.font_family, 10),
                fg=curr_fg,
                bg=self.bg_color,
                anchor="w"
            )
            text_lbl.pack(side="left", fill="both", expand=True, padx=(2, 10))

            # Optional Shortcut Column (Right-Aligned)
            sh_lbl = None
            if it.get("shortcut"):
                sh_lbl = tk.Label(
                    row,
                    text=it["shortcut"],
                    font=(self.font_family, 9),
                    fg=curr_sh_fg,
                    bg=self.bg_color,
                    anchor="e"
                )
                sh_lbl.pack(side="right", padx=(6, 8))

            w_info = {
                "row": row,
                "icon_box": icon_box,
                "icon_lbl": icon_lbl,
                "text_lbl": text_lbl,
                "item": it
            }
            if sh_lbl:
                w_info["sh_lbl"] = sh_lbl
            self._item_widgets[it["key"]] = w_info

            # Hover & Click Events
            def make_handlers(target_row, target_icon_box, target_icon_lbl, target_text_lbl, target_sh_lbl, target_it):
                def on_enter(e):
                    if target_it["state"] != "disabled":
                        target_row.configure(bg=self.hover_bg)
                        target_icon_box.configure(bg=self.hover_bg)
                        target_icon_lbl.configure(bg=self.hover_bg, fg=self.hover_fg)
                        target_text_lbl.configure(bg=self.hover_bg, fg=self.hover_fg)
                        if target_sh_lbl:
                            target_sh_lbl.configure(bg=self.hover_bg, fg="#e0f2fe")

                def on_leave(e):
                    target_row.configure(bg=self.bg_color)
                    target_icon_box.configure(bg=self.bg_color)
                    is_dis = target_it["state"] == "disabled"
                    fg = self.disabled_fg if is_dis else self.text_color
                    sh_fg = self.disabled_fg if is_dis else self.shortcut_fg
                    target_icon_lbl.configure(bg=self.bg_color, fg=fg)
                    target_text_lbl.configure(bg=self.bg_color, fg=fg)
                    if target_sh_lbl:
                        target_sh_lbl.configure(bg=self.bg_color, fg=sh_fg)

                def on_click(e):
                    if target_it["state"] != "disabled":
                        cmd = target_it["command"]
                        self.hide()
                        if cmd:
                            self.after(10, cmd)

                for w in (target_row, target_icon_box, target_icon_lbl, target_text_lbl) + ((target_sh_lbl,) if target_sh_lbl else ()):
                    w.bind("<Enter>", on_enter)
                    w.bind("<Leave>", on_leave)
                    w.bind("<Button-1>", on_click)

            make_handlers(row, icon_box, icon_lbl, text_lbl, sh_lbl, it)

        # Padding bottom
        pad_bot = tk.Frame(self.container, height=4, bg=self.bg_color)
        pad_bot.pack(fill="x")

    def show(self, x: int, y: int):
        """Renders and pops up context menu at (x, y) coordinates on screen."""
        self._render_menu()
        self.update_idletasks()

        menu_w = max(220, self.container.winfo_reqwidth() + 14)
        menu_h = self.container.winfo_reqheight() + 6

        # Keep menu inside screen boundaries
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()

        pos_x = min(x, screen_w - menu_w - 10)
        pos_y = min(y, screen_h - menu_h - 10)

        self.geometry(f"{menu_w}x{menu_h}+{max(0, pos_x)}+{max(0, pos_y)}")
        self.deiconify()
        self.focus_set()

    def hide(self):
        """Hides menu."""
        try:
            self.withdraw()
        except Exception:
            pass

    def _on_global_click(self, event):
        """Auto dismiss when clicking outside context menu."""
        if not self.winfo_ismapped():
            return
        # If click is outside menu geometry, dismiss
        try:
            mx, my = self.winfo_rootx(), self.winfo_rooty()
            mw, mh = self.winfo_width(), self.winfo_height()
            ex, ey = event.x_root, event.y_root
            if not (mx <= ex <= mx + mw and my <= ey <= my + mh):
                self.hide()
        except Exception:
            self.hide()
