import os
import sys
import shutil
import threading
import subprocess
import customtkinter as ctk

class ToolInstallerDialog(ctk.CTkToplevel):
    """Modern dialog to automatically install scrcpy & adb on macOS/Linux with real-time logs."""
    
    def __init__(self, master, on_complete=None):
        super().__init__(master)
        
        self.title("AxeCast Tool Installer 🪓")
        self.geometry("560x420")
        self.minsize(480, 340)
        self.on_complete = on_complete
        
        self.transient(master)
        self.grab_set()
        
        # Center dialog
        self.update_idletasks()
        try:
            px = master.winfo_rootx() + (master.winfo_width() // 2) - 280
            py = master.winfo_rooty() + (master.winfo_height() // 2) - 210
            self.geometry(f"+{max(10, px)}+{max(10, py)}")
        except Exception:
            pass
            
        self._proc = None
        self._is_running = False
        self._build_ui()
        self._start_installation()

    def _build_ui(self):
        container = ctk.CTkFrame(self, fg_color=("#f8fafc", "#0f172a"), corner_radius=12)
        container.pack(fill="both", expand=True, padx=12, pady=12)
        
        # Header
        hdr_frame = ctk.CTkFrame(container, fg_color="transparent")
        hdr_frame.pack(fill="x", padx=16, pady=(14, 8))
        
        icon_lbl = ctk.CTkLabel(hdr_frame, text="⚡", font=ctk.CTkFont(size=22))
        icon_lbl.pack(side="left", padx=(0, 8))
        
        title_box = ctk.CTkFrame(hdr_frame, fg_color="transparent")
        title_box.pack(side="left", fill="x")
        
        self.title_lbl = ctk.CTkLabel(
            title_box,
            text="Installing Required Tools (scrcpy & adb)",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color="#38bdf8"
        )
        self.title_lbl.pack(anchor="w")
        
        self.subtitle_lbl = ctk.CTkLabel(
            title_box,
            text="Downloading and configuring mirroring engine for macOS...",
            font=ctk.CTkFont(size=12),
            text_color=("#64748b", "#94a3b8")
        )
        self.subtitle_lbl.pack(anchor="w")
        
        # Progress Bar
        self.pbar = ctk.CTkProgressBar(container, height=6, mode="indeterminate", progress_color="#0284c7")
        self.pbar.pack(fill="x", padx=16, pady=(4, 10))
        self.pbar.start()
        
        # Console Log Box
        log_frame = ctk.CTkFrame(container, fg_color=("#0b0f19", "#06090e"), corner_radius=8)
        log_frame.pack(fill="both", expand=True, padx=16, pady=(0, 12))
        
        self.log_text = ctk.CTkTextbox(
            log_frame,
            font=ctk.CTkFont(family="Menlo" if sys.platform == "darwin" else "Consolas", size=11),
            fg_color="transparent",
            text_color="#e2e8f0",
            wrap="char"
        )
        self.log_text.pack(fill="both", expand=True, padx=6, pady=6)
        
        # Footer Action Bar
        self.footer = ctk.CTkFrame(container, fg_color="transparent")
        self.footer.pack(fill="x", padx=16, pady=(0, 10))
        
        self.status_lbl = ctk.CTkLabel(
            self.footer,
            text="⏳ Please do not close this window...",
            font=ctk.CTkFont(size=12),
            text_color="#f59e0b"
        )
        self.status_lbl.pack(side="left")
        
        self.close_btn = ctk.CTkButton(
            self.footer,
            text="Cancel",
            width=90,
            height=30,
            font=ctk.CTkFont(size=12),
            fg_color=("#475569", "#334155"),
            hover_color=("#334155", "#1e293b"),
            command=self._on_close
        )
        self.close_btn.pack(side="right")
        
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _append_log(self, text: str):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", text)
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _find_brew(self) -> str:
        for p in ["/opt/homebrew/bin/brew", "/usr/local/bin/brew"]:
            if os.path.exists(p):
                return p
        return shutil.which("brew") or ""

    def _start_installation(self):
        self._is_running = True
        threading.Thread(target=self._run_install_thread, daemon=True).start()

    def _run_install_thread(self):
        is_mac = sys.platform == "darwin"
        
        if is_mac:
            brew_path = self._find_brew()
            if not brew_path:
                self.after(0, lambda: self._append_log("❌ Error: Homebrew (brew) is not installed on this Mac.\n\n"))
                self.after(0, lambda: self._append_log("👉 Please install Homebrew first by running in Terminal:\n"))
                self.after(0, lambda: self._append_log('/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"\n\n'))
                self.after(0, lambda: self._append_log("Then run: brew install scrcpy android-platform-tools\n"))
                self.after(0, self._on_fail)
                return
                
            cmd = [brew_path, "install", "scrcpy", "android-platform-tools"]
            self.after(0, lambda: self._append_log(f"📦 Executing: {' '.join(cmd)}\n\n"))
        else:
            cmd = ["sudo", "apt", "update", "&&", "sudo", "apt", "install", "-y", "scrcpy", "adb"]
            self.after(0, lambda: self._append_log(f"📦 Executing: {' '.join(cmd)}\n\n"))
            
        try:
            self._proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )
            
            for line in iter(self._proc.stdout.readline, ''):
                if not line:
                    break
                self.after(0, lambda l=line: self._append_log(l))
                
            self._proc.stdout.close()
            ret = self._proc.wait()
            
            if ret == 0:
                self.after(0, self._on_success)
            else:
                self.after(0, lambda: self._append_log(f"\n⚠️ Process exited with code {ret}\n"))
                self.after(0, self._on_fail)
        except Exception as e:
            self.after(0, lambda: self._append_log(f"\n❌ Error during installation: {e}\n"))
            self.after(0, self._on_fail)

    def _on_success(self):
        self._is_running = False
        self.pbar.stop()
        self.pbar.configure(mode="determinate")
        self.pbar.set(1.0)
        
        self.title_lbl.configure(text="✅ Installation Complete!", text_color="#10b981")
        self.subtitle_lbl.configure(text="All required tools (scrcpy & adb) are ready to use.")
        self.status_lbl.configure(text="🎉 Tools configured successfully!", text_color="#10b981")
        
        self.close_btn.configure(
            text="Close & Refresh",
            fg_color=("#0284c7", "#0369a1"),
            hover_color=("#0369a1", "#075985")
        )
        
        if self.on_complete:
            try:
                self.on_complete()
            except Exception:
                pass

    def _on_fail(self):
        self._is_running = False
        self.pbar.stop()
        self.title_lbl.configure(text="⚠️ Installation Incomplete", text_color="#ef4444")
        self.status_lbl.configure(text="Manual setup may be required.", text_color="#ef4444")
        self.close_btn.configure(text="Close")

    def _on_close(self):
        if self._is_running and self._proc:
            try:
                self._proc.terminate()
            except Exception:
                pass
        self.destroy()
