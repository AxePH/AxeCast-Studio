import customtkinter as ctk

class CustomPromptDialog(ctk.CTkToplevel):
    """Modern themed input dialog that perfectly matches AxeCast Studio styling."""
    
    def __init__(self, master, title: str = "Input", prompt: str = "Enter value:", initial_value: str = "", placeholder: str = ""):
        super().__init__(master)
        
        self.title(title)
        self.geometry("420x210")
        self.resizable(False, False)
        
        self.result = None
        self.transient(master)
        self.grab_set()
        
        # Center dialog over parent
        self.update_idletasks()
        try:
            px = master.winfo_rootx() + (master.winfo_width() // 2) - 210
            py = master.winfo_rooty() + (master.winfo_height() // 2) - 105
            self.geometry(f"+{max(10, px)}+{max(10, py)}")
        except Exception:
            pass
            
        self._build_ui(title, prompt, initial_value, placeholder)
        self.wait_window()

    def _build_ui(self, title, prompt, initial_value, placeholder):
        # Container
        container = ctk.CTkFrame(self, fg_color=("#f8fafc", "#0f172a"), corner_radius=12)
        container.pack(fill="both", expand=True, padx=8, pady=8)
        
        # Title
        hdr = ctk.CTkLabel(container, text=title, font=ctk.CTkFont(size=14, weight="bold"), text_color="#38bdf8")
        hdr.pack(anchor="w", padx=18, pady=(14, 4))
        
        # Prompt text
        lbl = ctk.CTkLabel(container, text=prompt, font=ctk.CTkFont(size=12), text_color=("#64748b", "#94a3b8"))
        lbl.pack(anchor="w", padx=18, pady=(0, 8))
        
        # Input Entry
        self.entry = ctk.CTkEntry(
            container,
            height=36,
            placeholder_text=placeholder,
            font=ctk.CTkFont(size=13),
            fg_color=("#ffffff", "#1e293b"),
            border_color=("#cbd5e1", "#334155")
        )
        self.entry.pack(fill="x", padx=18, pady=(0, 14))
        if initial_value:
            self.entry.insert(0, initial_value)
            self.entry.select_range(0, "end")
            
        self.entry.focus_set()
        self.entry.bind("<Return>", lambda e: self._on_ok())
        self.entry.bind("<Escape>", lambda e: self._on_cancel())
        self.bind("<Escape>", lambda e: self._on_cancel())
        
        # Bottom Buttons
        btn_bar = ctk.CTkFrame(container, fg_color="transparent")
        btn_bar.pack(fill="x", padx=18, pady=(0, 10))
        
        cancel_btn = ctk.CTkButton(
            btn_bar,
            text="Cancel",
            width=90,
            height=32,
            font=ctk.CTkFont(size=12),
            fg_color=("#475569", "#334155"),
            hover_color=("#334155", "#1e293b"),
            command=self._on_cancel
        )
        cancel_btn.pack(side="right", padx=(8, 0))
        
        ok_btn = ctk.CTkButton(
            btn_bar,
            text="OK",
            width=90,
            height=32,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=("#0284c7", "#0369a1"),
            hover_color=("#0369a1", "#075985"),
            command=self._on_ok
        )
        ok_btn.pack(side="right")

    def _on_ok(self):
        val = self.entry.get().strip()
        if val:
            self.result = val
        self.destroy()

    def _on_cancel(self):
        self.result = None
        self.destroy()


class CustomConfirmDialog(ctk.CTkToplevel):
    """Modern themed confirmation dialog for delete and sensitive actions."""
    
    def __init__(self, master, title: str = "Confirm Action", message: str = "Are you sure?", confirm_text: str = "Delete", is_destructive: bool = True):
        super().__init__(master)
        
        self.title(title)
        self.geometry("440x200")
        self.resizable(False, False)
        
        self.result = False
        self.transient(master)
        self.grab_set()
        
        self.update_idletasks()
        try:
            px = master.winfo_rootx() + (master.winfo_width() // 2) - 220
            py = master.winfo_rooty() + (master.winfo_height() // 2) - 100
            self.geometry(f"+{max(10, px)}+{max(10, py)}")
        except Exception:
            pass
            
        self._build_ui(title, message, confirm_text, is_destructive)
        self.wait_window()

    def _build_ui(self, title, message, confirm_text, is_destructive):
        container = ctk.CTkFrame(self, fg_color=("#f8fafc", "#0f172a"), corner_radius=12)
        container.pack(fill="both", expand=True, padx=8, pady=8)
        
        icon = "🗑" if is_destructive else "❓"
        title_color = "#ef4444" if is_destructive else "#38bdf8"
        
        hdr = ctk.CTkLabel(container, text=f"{icon}  {title}", font=ctk.CTkFont(size=15, weight="bold"), text_color=title_color)
        hdr.pack(anchor="w", padx=18, pady=(16, 6))
        
        msg_lbl = ctk.CTkLabel(container, text=message, font=ctk.CTkFont(size=12), text_color=("#64748b", "#cbd5e1"), justify="left", wraplength=380)
        msg_lbl.pack(anchor="w", padx=18, pady=(0, 18))
        
        btn_bar = ctk.CTkFrame(container, fg_color="transparent")
        btn_bar.pack(fill="x", padx=18, pady=(0, 10))
        
        cancel_btn = ctk.CTkButton(
            btn_bar,
            text="Cancel",
            width=90,
            height=32,
            font=ctk.CTkFont(size=12),
            fg_color=("#475569", "#334155"),
            hover_color=("#334155", "#1e293b"),
            command=self._on_cancel
        )
        cancel_btn.pack(side="right", padx=(8, 0))
        
        confirm_btn_color = ("#dc2626", "#b91c1c") if is_destructive else ("#0284c7", "#0369a1")
        confirm_btn = ctk.CTkButton(
            btn_bar,
            text=confirm_text,
            width=90,
            height=32,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=confirm_btn_color,
            hover_color=("#991b1b" if is_destructive else "#075985"),
            command=self._on_confirm
        )
        confirm_btn.pack(side="right")
        
        self.bind("<Escape>", lambda e: self._on_cancel())
        self.bind("<Return>", lambda e: self._on_confirm())

    def _on_confirm(self):
        self.result = True
        self.destroy()

    def _on_cancel(self):
        self.result = False
        self.destroy()


def ask_string(parent, title: str, prompt: str, initial_value: str = "", placeholder: str = "") -> str | None:
    dlg = CustomPromptDialog(parent, title=title, prompt=prompt, initial_value=initial_value, placeholder=placeholder)
    return dlg.result

def ask_confirm(parent, title: str, message: str, confirm_text: str = "Delete", is_destructive: bool = True) -> bool:
    dlg = CustomConfirmDialog(parent, title=title, message=message, confirm_text=confirm_text, is_destructive=is_destructive)
    return dlg.result
