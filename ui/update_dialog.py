import sys
import webbrowser
import customtkinter as ctk

class UpdateDialog(ctk.CTkToplevel):
    """Smart Cross-Platform Update Dialog presenting release notes and 1-click downloads."""
    
    def __init__(self, master, update_info: dict):
        super().__init__(master)
        
        self.update_info = update_info
        self.title("🎉 New Version Available — AxeCast Studio")
        self.geometry("560x500")
        self.minsize(480, 400)
        
        self.transient(master)
        self.grab_set()
        
        self._build_ui()

    def _build_ui(self):
        # 1. Header Banner
        header = ctk.CTkFrame(self, fg_color=("#0284c7", "#0369a1"), corner_radius=0, height=76)
        header.pack(fill="x", side="top")
        header.pack_propagate(False)
        
        h_box = ctk.CTkFrame(header, fg_color="transparent")
        h_box.pack(fill="both", expand=True, padx=20, pady=12)
        
        ctk.CTkLabel(
            h_box,
            text="🚀 A New Version is Available!",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color="white"
        ).pack(anchor="w")
        
        cur_v = self.update_info.get("current_version", "1.0.0")
        lat_v = self.update_info.get("latest_version", "1.0.0")
        tag_v = self.update_info.get("tag_name", f"v{lat_v}")
        
        ctk.CTkLabel(
            h_box,
            text=f"AxeCast Studio {tag_v} is now available (Current: v{cur_v})",
            font=ctk.CTkFont(size=12),
            text_color="#e0f2fe"
        ).pack(anchor="w", pady=(2, 0))

        # 2. Main Content
        content = ctk.CTkFrame(self, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=20, pady=14)

        # Release Title
        rel_name = self.update_info.get("release_name") or f"Release {tag_v}"
        ctk.CTkLabel(
            content,
            text=f"📌 {rel_name}",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(anchor="w", pady=(0, 6))

        # Changelog / Release Notes Box
        ctk.CTkLabel(
            content,
            text="📝 What's New & Improvements:",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=("#475569", "#94a3b8")
        ).pack(anchor="w", pady=(0, 4))
        
        changelog_text = self.update_info.get("changelog", "").strip() or "No detailed changelog provided."
        
        notes_box = ctk.CTkTextbox(
            content,
            wrap="word",
            font=ctk.CTkFont(family="Consolas" if sys.platform.startswith("win") else "Monospace", size=11),
            fg_color=("#f1f5f9", "#090d16"),
            border_width=1,
            border_color=("#cbd5e1", "#1e293b"),
            corner_radius=8
        )
        notes_box.pack(fill="both", expand=True, pady=(0, 10))
        notes_box.insert("1.0", changelog_text)
        notes_box.configure(state="disabled")

        # 3. Action Buttons Bar
        btn_bar = ctk.CTkFrame(self, height=54, fg_color=("#f8fafc", "#0f172a"))
        btn_bar.pack(fill="x", side="bottom", padx=0, pady=0)
        
        btn_inner = ctk.CTkFrame(btn_bar, fg_color="transparent")
        btn_inner.pack(fill="both", expand=True, padx=20, pady=10)

        # Detect OS label
        os_label = "Windows" if sys.platform.startswith("win") else ("macOS" if sys.platform == "darwin" else "Linux")
        asset_name = self.update_info.get("os_asset_name")
        btn_text = f"⬇️ Download for {os_label}" if not asset_name else f"⬇️ Download ({os_label})"

        # Direct Download Button
        ctk.CTkButton(
            btn_inner,
            text=btn_text,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=("#16a34a", "#15803d"),
            hover_color=("#15803d", "#166534"),
            height=34,
            command=self._on_download_click
        ).pack(side="right", padx=(6, 0))

        # View on GitHub Webpage Button
        ctk.CTkButton(
            btn_inner,
            text="🌐 View on GitHub",
            font=ctk.CTkFont(size=12),
            fg_color=("#0284c7", "#0369a1"),
            hover_color=("#0369a1", "#075985"),
            height=34,
            command=self._on_view_github
        ).pack(side="right", padx=(6, 0))

        # Close Button
        ctk.CTkButton(
            btn_inner,
            text="Later",
            font=ctk.CTkFont(size=12),
            fg_color=("#64748b", "#334155"),
            hover_color=("#475569", "#1e293b"),
            height=34,
            width=70,
            command=self.destroy
        ).pack(side="left")

    def _on_download_click(self):
        download_url = self.update_info.get("os_download_url") or self.update_info.get("release_url")
        if download_url:
            webbrowser.open(download_url)
        self.destroy()

    def _on_view_github(self):
        rel_url = self.update_info.get("release_url")
        if rel_url:
            webbrowser.open(rel_url)
        self.destroy()
