import customtkinter as ctk
from .file_explorer_view import DeviceFileExplorerView

class DeviceFileExplorerDialog(ctk.CTkToplevel):
    """Standalone floating window for Device File Explorer with Dock back feature."""
    
    def __init__(self, master, serial: str, model_name: str = "Device", on_dock=None):
        super().__init__(master)
        self.title(f"📁 Device File Explorer - {model_name} ({serial})")
        self.geometry("880x600")
        self.minsize(700, 420)
        
        self.serial = serial
        self.model = model_name
        self.on_dock = on_dock
        
        self.view = DeviceFileExplorerView(
            self,
            serial=serial,
            model_name=model_name,
            on_toggle_dock=self._handle_dock,
            is_docked=False
        )
        self.view.pack(fill="both", expand=True, padx=4, pady=4)
        
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _handle_dock(self):
        if self.on_dock:
            self.on_dock(self.serial, self.model)
        self.destroy()

    def apply_theme(self):
        if hasattr(self, "view") and hasattr(self.view, "apply_theme"):
            self.view.apply_theme()

    def _on_close(self):
        self.destroy()
