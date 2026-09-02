"""
AxePrint Studio Dialog - Virtual Bluetooth & Network Thermal Printer 🖨️
Interactive UI for simulating Woosim WSP-R241, Sewoo LK-P30, Sewoo LK-P21,
and Generic ESC/POS thermal printers with live canvas, export, and history.
"""

import os
import sys
import time
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import customtkinter as ctk
from PIL import Image, ImageTk

from core.thermal_printer_engine import (
    PRINTER_PROFILES,
    DEFAULT_PROFILE_ID,
    PrinterModelProfile,
    ReceiptDocument,
    ESCPOSParser,
    VirtualReceiptRenderer,
    SerialPrinterListener,
    TCPPrinterListener,
    create_sample_receipt_bytes,
    get_bluetooth_device_info,
    HAS_SERIAL
)


class ThermalPrinterDialog(ctk.CTkToplevel):
    """Modern Virtual Thermal Printer Studio with Model Profiles & Live Paper Preview."""

    def __init__(self, master=None):
        super().__init__(master)

        self.title("🖨️ AxePrint Studio - Virtual Thermal Printer")
        self.geometry("1120x780")
        self.minsize(920, 600)

        # Selected state
        self.current_profile_id = DEFAULT_PROFILE_ID
        self.profile = PRINTER_PROFILES[self.current_profile_id]
        self.connection_mode = "serial"  # "serial" or "tcp"
        self.zoom_level = 1.0
        self.receipt_history: list[ReceiptDocument] = []
        self.active_receipt: ReceiptDocument | None = None
        self.total_bytes = 0

        # Parser & Listeners
        self.parser = ESCPOSParser(self.profile, on_receipt_complete=self._on_receipt_arrived)
        self.serial_listener = SerialPrinterListener(self.parser, on_status_change=self._on_connection_status)
        self.tcp_listener = TCPPrinterListener(self.parser, on_status_change=self._on_connection_status)

        self._setup_theme()
        self._build_top_toolbar()
        self._build_main_workspace()
        self._setup_shortcuts()

        # Load initial sample receipt on launch
        self.after(100, self.print_sample_receipt)

        # Refresh COM ports
        self.after(200, self._refresh_com_ports)

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _setup_theme(self):
        is_dark = ctk.get_appearance_mode() == "Dark"
        self.configure(fg_color=("#f1f5f9", "#0b0f19"))
        self.font_family = "SF Pro Text" if sys.platform == "darwin" else ("Segoe UI" if sys.platform.startswith("win") else "Ubuntu")

    def _build_top_toolbar(self):
        self.toolbar = ctk.CTkFrame(self, height=48, corner_radius=0, fg_color=("#e2e8f0", "#1e293b"))
        self.toolbar.pack(side="top", fill="x", padx=0, pady=0)

        # 1. Printer Model Profile Selector
        ctk.CTkLabel(self.toolbar, text="🖨️ Model:", font=(self.font_family, 12, "bold")).pack(side="left", padx=(10, 4), pady=8)
        
        self.profile_options = [p.display_name for p in PRINTER_PROFILES.values()]
        self.profile_var = ctk.StringVar(value=self.profile.display_name)
        self.profile_menu = ctk.CTkOptionMenu(
            self.toolbar,
            values=self.profile_options,
            variable=self.profile_var,
            width=210,
            height=30,
            font=(self.font_family, 11, "bold"),
            fg_color=("#0284c7", "#0369a1"),
            dropdown_fg_color=("#1e293b", "#0f172a"),
            command=self._on_profile_selected
        )
        self.profile_menu.pack(side="left", padx=(0, 10), pady=8)

        # 2. Connection Mode Toggle
        self.mode_var = ctk.StringVar(value="Bluetooth / COM")
        self.mode_seg = ctk.CTkSegmentedButton(
            self.toolbar,
            values=["Bluetooth / COM", "TCP 9100 / Wi-Fi"],
            variable=self.mode_var,
            height=30,
            font=(self.font_family, 11),
            command=self._on_mode_toggled
        )
        self.mode_seg.pack(side="left", padx=4, pady=8)

        # 3. COM Port Selector (shown when mode == "Bluetooth / COM")
        self.port_frame = ctk.CTkFrame(self.toolbar, fg_color="transparent")
        self.port_frame.pack(side="left", padx=4, pady=8)

        self.port_var = ctk.StringVar(value="Select Port")
        self.port_menu = ctk.CTkOptionMenu(
            self.port_frame,
            values=["Scanning..."],
            variable=self.port_var,
            width=120,
            height=30,
            font=(self.font_family, 11)
        )
        self.port_menu.pack(side="left", padx=(0, 2))

        self.refresh_port_btn = ctk.CTkButton(
            self.port_frame,
            text="🔄",
            width=30,
            height=30,
            command=self._refresh_com_ports
        )
        self.refresh_port_btn.pack(side="left", padx=(0, 4))

        # 4. Start/Stop Listening Button
        self.listen_btn = ctk.CTkButton(
            self.toolbar,
            text="▶ Start Listening",
            width=130,
            height=30,
            fg_color=("#16a34a", "#15803d"),
            hover_color=("#15803d", "#166534"),
            font=(self.font_family, 11, "bold"),
            command=self._toggle_listening
        )
        self.listen_btn.pack(side="left", padx=6, pady=8)

        # 5. Quick Test Print Button
        self.test_btn = ctk.CTkButton(
            self.toolbar,
            text="🧪 Test Print",
            width=100,
            height=30,
            fg_color=("#475569", "#334155"),
            hover_color=("#334155", "#1e293b"),
            command=self.print_sample_receipt
        )
        self.test_btn.pack(side="left", padx=4, pady=8)

        # Right side: Actions (Copy / Export PNG / Export PDF)
        self.pdf_btn = ctk.CTkButton(
            self.toolbar,
            text="📄 PDF",
            width=65,
            height=30,
            fg_color=("#475569", "#334155"),
            command=self._save_as_pdf
        )
        self.pdf_btn.pack(side="right", padx=(4, 10), pady=8)

        self.png_btn = ctk.CTkButton(
            self.toolbar,
            text="💾 PNG",
            width=65,
            height=30,
            fg_color=("#475569", "#334155"),
            command=self._save_as_png
        )
        self.png_btn.pack(side="right", padx=4, pady=8)

        self.copy_btn = ctk.CTkButton(
            self.toolbar,
            text="📋 Copy",
            width=70,
            height=30,
            fg_color=("#0284c7", "#0369a1"),
            command=self._copy_to_clipboard
        )
        self.copy_btn.pack(side="right", padx=4, pady=8)

    def _build_main_workspace(self):
        # PanedWindow: Left Sidebar + Right Receipt Viewer
        self.paned = tk.PanedWindow(self, orient="horizontal", bg="#0f172a", sashwidth=4, bd=0)
        self.paned.pack(fill="both", expand=True, padx=4, pady=4)

        # ─── LEFT SIDEBAR: PROFILE INFO, METRICS & RECEIPT HISTORY ───
        self.sidebar_frame = ctk.CTkFrame(self.paned, width=280, corner_radius=6, fg_color=("#f8fafc", "#0f172a"))
        self.paned.add(self.sidebar_frame, minsize=240)

        # Connection Status Badge Box
        self.status_card = ctk.CTkFrame(self.sidebar_frame, fg_color=("#e2e8f0", "#1e293b"), corner_radius=8)
        self.status_card.pack(fill="x", padx=8, pady=(8, 4))

        self.status_lbl = ctk.CTkLabel(
            self.status_card,
            text="🟡 Standby / Stopped",
            font=(self.font_family, 11, "bold"),
            text_color="#f59e0b"
        )
        self.status_lbl.pack(anchor="w", padx=10, pady=(6, 2))

        self.info_lbl = ctk.CTkLabel(
            self.status_card,
            text=f"{self.profile.paper_width_mm}mm ({self.profile.printable_dots} dots) | {self.profile.cpl_font_a} CPL | {self.profile.thai_codepage}",
            font=(self.font_family, 10),
            text_color="#94a3b8"
        )
        self.info_lbl.pack(anchor="w", padx=10, pady=(0, 6))

        # Metrics Card (Bytes & Receipts)
        metrics_box = ctk.CTkFrame(self.sidebar_frame, fg_color="transparent")
        metrics_box.pack(fill="x", padx=8, pady=4)

        self.bytes_badge = ctk.CTkLabel(
            metrics_box,
            text="📥 0 B",
            font=(self.font_family, 11, "bold"),
            fg_color=("#e2e8f0", "#1e293b"),
            corner_radius=6,
            padx=8,
            pady=3
        )
        self.bytes_badge.pack(side="left", fill="x", expand=True, padx=(0, 4))

        self.receipts_badge = ctk.CTkLabel(
            metrics_box,
            text="🧾 0 Tickets",
            font=(self.font_family, 11, "bold"),
            fg_color=("#e2e8f0", "#1e293b"),
            corner_radius=6,
            padx=8,
            pady=3
        )
        self.receipts_badge.pack(side="left", fill="x", expand=True, padx=(4, 0))

        # Bluetooth Device Pairing Card (shows Name + MAC address for pairing)
        self.bt_card = ctk.CTkFrame(self.sidebar_frame, fg_color=("#e2e8f0", "#1e293b"), corner_radius=8)
        self.bt_card.pack(fill="x", padx=8, pady=4)

        bt_header = ctk.CTkFrame(self.bt_card, fg_color="transparent")
        bt_header.pack(fill="x", padx=8, pady=(6, 2))

        ctk.CTkLabel(bt_header, text="📶 Bluetooth Pairing Info", font=(self.font_family, 11, "bold"), text_color="#10b981").pack(side="left")

        # Resolve Bluetooth MAC and Name
        self.bt_mac, self.bt_name = get_bluetooth_device_info()

        info_box = ctk.CTkFrame(self.bt_card, fg_color=("#f1f5f9", "#0f172a"), corner_radius=6)
        info_box.pack(fill="x", padx=8, pady=(2, 6))

        # Device Name
        name_row = ctk.CTkFrame(info_box, fg_color="transparent")
        name_row.pack(fill="x", padx=6, pady=(4, 1))
        ctk.CTkLabel(name_row, text="Name:", font=(self.font_family, 10, "bold"), text_color="#94a3b8", width=42, anchor="w").pack(side="left")
        self.bt_name_lbl = ctk.CTkLabel(name_row, text=self.bt_name or "PC-Bluetooth", font=(self.font_family, 10, "bold"), text_color="#38bdf8", anchor="w")
        self.bt_name_lbl.pack(side="left", fill="x", expand=True)

        # MAC Address
        mac_row = ctk.CTkFrame(info_box, fg_color="transparent")
        mac_row.pack(fill="x", padx=6, pady=(1, 4))
        ctk.CTkLabel(mac_row, text="MAC:", font=(self.font_family, 10, "bold"), text_color="#94a3b8", width=42, anchor="w").pack(side="left")
        self.bt_mac_lbl = ctk.CTkLabel(mac_row, text=self.bt_mac or "Not Detected", font=(self.font_family, 10, "bold"), text_color="#f59e0b", anchor="w")
        self.bt_mac_lbl.pack(side="left", fill="x", expand=True)

        if self.bt_mac:
            self.copy_mac_btn = ctk.CTkButton(
                mac_row,
                text="📋 Copy",
                width=50,
                height=20,
                font=(self.font_family, 9),
                fg_color=("#0284c7", "#0369a1"),
                command=self._copy_bt_mac
            )
            self.copy_mac_btn.pack(side="right")

        # Quick action buttons to make Windows Bluetooth discoverable and configure COM
        btn_row = ctk.CTkFrame(self.bt_card, fg_color="transparent")
        btn_row.pack(fill="x", padx=8, pady=(0, 6))

        ctk.CTkButton(
            btn_row,
            text="⚙️ เปิดหน้าบลูทูธ (เปิดการมองเห็น)",
            height=24,
            font=(self.font_family, 10),
            fg_color=("#334155", "#1e293b"),
            hover_color=("#475569", "#334155"),
            command=self._open_windows_bt_settings
        ).pack(side="left", fill="x", expand=True, padx=(0, 2))

        ctk.CTkButton(
            btn_row,
            text="🔧 จัดการ COM Port",
            height=24,
            font=(self.font_family, 10),
            fg_color=("#334155", "#1e293b"),
            hover_color=("#475569", "#334155"),
            command=self._open_windows_bt_properties
        ).pack(side="left", fill="x", expand=True, padx=(2, 0))

        # Guide Card
        guide_card = ctk.CTkFrame(self.sidebar_frame, fg_color=("#e2e8f0", "#1e293b"), corner_radius=8)
        guide_card.pack(fill="x", padx=8, pady=4)

        guide_title = ctk.CTkLabel(guide_card, text="💡 Quick Connection Tips", font=(self.font_family, 11, "bold"), text_color="#38bdf8")
        guide_title.pack(anchor="w", padx=8, pady=(6, 2))

        guide_text = (
            "• Bluetooth: Pair phone with PC → In Windows Settings, add 'Incoming COM Port' → Select COM port above.\n"
            "• Wi-Fi / ADB: Switch to TCP 9100. Over USB, run:\n"
            "  'adb forward tcp:9100 tcp:9100'"
        )
        ctk.CTkLabel(guide_card, text=guide_text, font=(self.font_family, 9), text_color="#94a3b8", justify="left").pack(anchor="w", padx=8, pady=(0, 6))

        # Receipt History Header with Clear button
        hist_header = ctk.CTkFrame(self.sidebar_frame, fg_color="transparent")
        hist_header.pack(fill="x", padx=8, pady=(6, 2))

        ctk.CTkLabel(hist_header, text="📜 Captured Receipts", font=(self.font_family, 11, "bold")).pack(side="left")
        
        ctk.CTkButton(
            hist_header,
            text="🗑 Clear",
            width=55,
            height=22,
            font=(self.font_family, 10),
            fg_color=("#ef4444", "#dc2626"),
            command=self._clear_history
        ).pack(side="right")

        # History Treeview
        tree_container = tk.Frame(self.sidebar_frame, bg="#0f172a")
        tree_container.pack(fill="both", expand=True, padx=8, pady=(2, 8))

        style = ttk.Style()
        style.configure("ReceiptHistory.Treeview", background="#0f172a", foreground="#f8fafc", fieldbackground="#0f172a", rowheight=24, font=(self.font_family, 10), borderwidth=0)
        style.map("ReceiptHistory.Treeview", background=[("selected", "#0284c7")])

        self.hist_tree = ttk.Treeview(tree_container, columns=("time", "model", "size"), show="headings", style="ReceiptHistory.Treeview", selectmode="browse")
        self.hist_tree.heading("time", text="Time")
        self.hist_tree.heading("model", text="Model")
        self.hist_tree.heading("size", text="Elements")
        self.hist_tree.column("time", width=70, anchor="w")
        self.hist_tree.column("model", width=90, anchor="w")
        self.hist_tree.column("size", width=60, anchor="center")
        self.hist_tree.pack(side="left", fill="both", expand=True)

        hist_scroll = ttk.Scrollbar(tree_container, orient="vertical", command=self.hist_tree.yview)
        hist_scroll.pack(side="right", fill="y")
        self.hist_tree.configure(yscrollcommand=hist_scroll.set)
        self.hist_tree.bind("<<TreeviewSelect>>", self._on_history_select)

        # ─── RIGHT MAIN VIEW: THERMAL PAPER CANVAS ───
        self.canvas_container = ctk.CTkFrame(self.paned, corner_radius=6, fg_color=("#cbd5e1", "#0b0f19"))
        self.paned.add(self.canvas_container, minsize=400)

        # Zoom Bar
        zoom_bar = ctk.CTkFrame(self.canvas_container, height=34, corner_radius=0, fg_color=("#e2e8f0", "#1e293b"))
        zoom_bar.pack(side="top", fill="x")

        self.zoom_lbl = ctk.CTkLabel(zoom_bar, text="🔍 Zoom: 100%", font=(self.font_family, 11, "bold"), text_color="#38bdf8")
        self.zoom_lbl.pack(side="left", padx=(10, 4))

        ctk.CTkButton(zoom_bar, text="➖", width=28, height=22, command=lambda: self._adjust_zoom(-0.15)).pack(side="left", padx=2)
        ctk.CTkButton(zoom_bar, text="100%", width=45, height=22, command=lambda: self._set_zoom(1.0)).pack(side="left", padx=2)
        ctk.CTkButton(zoom_bar, text="➕", width=28, height=22, command=lambda: self._adjust_zoom(0.15)).pack(side="left", padx=2)

        # Paper Size Selector (58mm / 80mm / Auto-Fit)
        ctk.CTkLabel(zoom_bar, text="| 📄 Paper:", font=(self.font_family, 11, "bold"), text_color="#38bdf8").pack(side="left", padx=(12, 4))
        self.paper_mode_var = ctk.StringVar(value="80 mm" if self.profile.paper_width_mm >= 80 else "58 mm")
        self.paper_seg = ctk.CTkSegmentedButton(
            zoom_bar,
            values=["58 mm", "80 mm", "Auto-Fit"],
            variable=self.paper_mode_var,
            height=24,
            font=(self.font_family, 10, "bold"),
            command=self._on_paper_mode_changed
        )
        self.paper_seg.pack(side="left", padx=4)

        # Auto-wrap toggle checkbox
        self.wrap_var = ctk.BooleanVar(value=True)
        self.wrap_cb = ctk.CTkCheckBox(
            zoom_bar,
            text="Wrap Text",
            variable=self.wrap_var,
            font=(self.font_family, 10),
            height=20,
            checkbox_width=16,
            checkbox_height=16,
            command=self._render_active_receipt
        )
        self.wrap_cb.pack(side="left", padx=(6, 2))

        self.paper_dim_lbl = ctk.CTkLabel(zoom_bar, text="", font=(self.font_family, 10), text_color="#94a3b8")
        self.paper_dim_lbl.pack(side="right", padx=10)

        # Scrollable Canvas
        canvas_box = tk.Frame(self.canvas_container, bg="#0b0f19")
        canvas_box.pack(fill="both", expand=True, padx=4, pady=4)

        self.v_scroll = ttk.Scrollbar(canvas_box, orient="vertical")
        self.v_scroll.pack(side="right", fill="y")

        self.h_scroll = ttk.Scrollbar(canvas_box, orient="horizontal")
        self.h_scroll.pack(side="bottom", fill="x")

        self.canvas = tk.Canvas(
            canvas_box,
            bg="#0b0f19",
            highlightthickness=0,
            yscrollcommand=self.v_scroll.set,
            xscrollcommand=self.h_scroll.set
        )
        self.canvas.pack(side="left", fill="both", expand=True)

        self.v_scroll.config(command=self.canvas.yview)
        self.h_scroll.config(command=self.canvas.xview)

        # Mouse wheel scrolling
        self.canvas.bind("<MouseWheel>", lambda e: self.canvas.yview_scroll(int(-1 * (e.delta / 120)), "units"))

    def _setup_shortcuts(self):
        self.bind("<Control-p>", lambda e: self.print_sample_receipt())
        self.bind("<Control-P>", lambda e: self.print_sample_receipt())
        self.bind("<Control-c>", lambda e: self._copy_to_clipboard())
        self.bind("<Control-C>", lambda e: self._copy_to_clipboard())
        self.bind("<Control-s>", lambda e: self._save_as_png())
        self.bind("<Control-S>", lambda e: self._save_as_png())

    # ─── EVENT HANDLERS & PROFILE SELECTION ───

    def _on_profile_selected(self, display_name: str):
        for pid, p in PRINTER_PROFILES.items():
            if p.display_name == display_name:
                self.current_profile_id = pid
                self.profile = p
                self.parser.set_profile(p)
                self.info_lbl.configure(
                    text=f"{p.paper_width_mm}mm ({p.printable_dots} dots) | {p.cpl_font_a} CPL | {p.thai_codepage}"
                )
                if hasattr(self, "paper_mode_var"):
                    self.paper_mode_var.set("80 mm" if p.paper_width_mm >= 80 else "58 mm")
                if self.active_receipt:
                    self.active_receipt.profile = p
                    self._render_active_receipt()
                break

    def _on_paper_mode_changed(self, mode: str):
        """Switches paper width between 58mm, 80mm, and Auto-Fit."""
        if mode == "80 mm":
            if self.profile.paper_width_mm < 80:
                for p in PRINTER_PROFILES.values():
                    if p.paper_width_mm >= 80:
                        self.profile = p
                        self.profile_var.set(p.display_name)
                        self.parser.set_profile(p)
                        self.info_lbl.configure(
                            text=f"{p.paper_width_mm}mm ({p.printable_dots} dots) | {p.cpl_font_a} CPL | {p.thai_codepage}"
                        )
                        break
        elif mode == "58 mm":
            if self.profile.paper_width_mm >= 80:
                for p in PRINTER_PROFILES.values():
                    if p.paper_width_mm <= 58:
                        self.profile = p
                        self.profile_var.set(p.display_name)
                        self.parser.set_profile(p)
                        self.info_lbl.configure(
                            text=f"{p.paper_width_mm}mm ({p.printable_dots} dots) | {p.cpl_font_a} CPL | {p.thai_codepage}"
                        )
                        break

        self._render_active_receipt()

    def _on_mode_toggled(self, mode: str):
        self._stop_listeners()
        if mode == "Bluetooth / COM":
            self.connection_mode = "serial"
            self.port_frame.pack(side="left", padx=4, pady=8)
            self._refresh_com_ports()
        else:
            self.connection_mode = "tcp"
            self.port_frame.pack_forget()

    def _copy_bt_mac(self):
        """Copies the PC Bluetooth MAC address to clipboard for easy phone pairing."""
        if self.bt_mac:
            self.clipboard_clear()
            self.clipboard_append(self.bt_mac)
            if hasattr(self, "copy_mac_btn"):
                self.copy_mac_btn.configure(text="✓ Copied")
                self.after(1200, lambda: self.copy_mac_btn.configure(text="📋 Copy"))

    def _open_windows_bt_settings(self):
        """Opens OS Bluetooth settings to put PC into discoverable pairing mode."""
        try:
            if sys.platform.startswith("win"):
                os.system("start ms-settings:bluetooth")
            elif sys.platform == "darwin":
                os.system("open /System/Library/PreferencePanes/Bluetooth.prefPane")
        except Exception:
            pass

    def _open_windows_bt_properties(self):
        """Opens classic Bluetooth properties to configure COM ports and discoverability checkbox."""
        try:
            if sys.platform.startswith("win"):
                os.system("start bthprops.cpl")
        except Exception:
            pass

    def _ensure_pyserial(self) -> bool:
        """Checks if pyserial is available, offers 1-click auto-install if missing."""
        import core.thermal_printer_engine as tpe
        if tpe.HAS_SERIAL:
            return True
        try:
            import serial
            import serial.tools.list_ports
            tpe.HAS_SERIAL = True
            tpe.serial = serial
            return True
        except ImportError:
            pass

        ans = messagebox.askyesno(
            "AxePrint Studio",
            "pyserial library is required for Bluetooth & Serial COM ports.\n\nWould you like AxeCast Studio to install it automatically now?"
        )
        if ans:
            try:
                import subprocess
                subprocess.check_call([sys.executable, "-m", "pip", "install", "pyserial"])
                import serial
                import serial.tools.list_ports
                tpe.HAS_SERIAL = True
                tpe.serial = serial
                self._refresh_com_ports()
                messagebox.showinfo("AxePrint Studio", "pyserial installed successfully!")
                return True
            except Exception as e:
                messagebox.showerror("AxePrint Studio", f"Failed to install pyserial automatically:\n{e}\n\nPlease run in terminal: pip install pyserial")
                return False
        return False

    def _refresh_com_ports(self):
        import core.thermal_printer_engine as tpe
        if not tpe.HAS_SERIAL:
            try:
                import serial
                import serial.tools.list_ports
                tpe.HAS_SERIAL = True
                tpe.serial = serial
            except ImportError:
                pass

        ports = SerialPrinterListener.get_available_ports()
        if ports:
            port_labels = []
            incoming = [p for p in ports if p.get("is_incoming")]
            if incoming:
                inc_summary = "/".join([p["device"] for p in incoming])
                port_labels.append(f"⭐ Auto ({inc_summary})")

            for p in ports:
                tag = " (Incoming BT)" if p.get("is_incoming") else (" (BT)" if p.get("is_bluetooth") else "")
                port_labels.append(f"{p['device']}{tag}")

            self.port_menu.configure(values=port_labels)
            self.port_var.set(port_labels[0])
        else:
            self.port_menu.configure(values=["No COM Ports"])
            self.port_var.set("No COM Ports")

    def _toggle_listening(self):
        is_running = self.serial_listener._running or self.tcp_listener._running
        if is_running:
            self._stop_listeners()
        else:
            self._start_listening()

    def _start_listening(self):
        if self.connection_mode == "serial":
            if not self._ensure_pyserial():
                return

            raw_port_choice = self.port_var.get()
            if not raw_port_choice or raw_port_choice.startswith("No"):
                messagebox.showwarning("AxePrint Studio", "Please select a valid COM port.\nIf your phone is paired via Bluetooth, ensure Windows has an Incoming COM port.")
                return

            # Pass raw_port_choice directly (if Auto, it listens on all incoming BT ports!)
            success = self.serial_listener.start(raw_port_choice, baudrate=115200)
            if success:
                self.listen_btn.configure(text="🛑 Stop Listening", fg_color=("#dc2626", "#b91c1c"), hover_color=("#b91c1c", "#991b1b"))
        else:
            success = self.tcp_listener.start(port=9100)
            if success:
                self.listen_btn.configure(text="🛑 Stop Listening", fg_color=("#dc2626", "#b91c1c"), hover_color=("#b91c1c", "#991b1b"))

    def _stop_listeners(self):
        self.serial_listener.stop()
        self.tcp_listener.stop()
        self.listen_btn.configure(text="▶ Start Listening", fg_color=("#16a34a", "#15803d"), hover_color=("#15803d", "#166534"))

    def _on_connection_status(self, status_msg: str, is_active: bool):
        self.after(0, lambda: self._update_status_ui(status_msg, is_active))

    def _update_status_ui(self, status_msg: str, is_active: bool):
        col = "#10b981" if is_active else ("#f59e0b" if "Waiting" in status_msg else "#ef4444")
        self.status_lbl.configure(text=status_msg, text_color=col)

    # ─── RECEIPT CAPTURE & RENDERING ───

    def _on_receipt_arrived(self, doc: ReceiptDocument):
        """Called by parser engine when a print job / cut command arrives."""
        self.after(0, lambda: self._handle_new_receipt(doc))

    def _handle_new_receipt(self, doc: ReceiptDocument):
        self.total_bytes += doc.raw_bytes_count
        self.bytes_badge.configure(text=f"📥 {self._format_bytes(self.total_bytes)}")
        self.receipt_history.append(doc)
        self.receipts_badge.configure(text=f"🧾 {len(self.receipt_history)} Tickets")

        # Smart Auto-Detection for 80mm content (if lines > 34 chars, switch to 80mm)
        has_wide_content = False
        for elem in doc.elements:
            if hasattr(elem, "text") and len(elem.text) > 34:
                has_wide_content = True
                break

        if has_wide_content and hasattr(self, "paper_seg") and self.paper_mode_var.get() == "58 mm":
            self.paper_mode_var.set("80 mm")
            self._on_paper_mode_changed("80 mm")

        # Add to Treeview
        idx = len(self.receipt_history) - 1
        t_str = time.strftime("%H:%M:%S", time.localtime(doc.created_at))
        self.hist_tree.insert("", 0, iid=str(idx), values=(t_str, doc.profile.name[:12], f"{len(doc.elements)} items"))

        # Select and render
        self.active_receipt = doc
        self._render_active_receipt()

    def print_sample_receipt(self):
        """Injects a sample ESC/POS byte sequence simulating an authentic Thai POS receipt."""
        sample_bytes = create_sample_receipt_bytes(self.profile)
        self.parser.parse_bytes(sample_bytes)

    def _render_active_receipt(self):
        if not self.active_receipt:
            return

        mode_val = self.paper_mode_var.get() if hasattr(self, "paper_mode_var") else "80 mm"
        wrap_val = self.wrap_var.get() if hasattr(self, "wrap_var") else True

        if mode_val == "80 mm":
            target_mm = 80
            auto_fit = False
            mm_label = "80mm"
        elif mode_val == "Auto-Fit":
            target_mm = None
            auto_fit = True
            mm_label = "Auto-Fit"
        else:
            target_mm = 58
            auto_fit = False
            mm_label = "58mm"

        img = VirtualReceiptRenderer.render(
            self.active_receipt,
            target_width_mm=target_mm,
            auto_fit=auto_fit,
            auto_wrap=wrap_val
        )
        if not img:
            return

        # Apply zoom
        if self.zoom_level != 1.0:
            new_w = max(100, int(img.width * self.zoom_level))
            new_h = max(100, int(img.height * self.zoom_level))
            display_img = img.resize((new_w, new_h), Image.LANCZOS)
        else:
            display_img = img

        self.tk_img = ImageTk.PhotoImage(display_img)
        self.canvas.delete("all")

        # Center image on canvas if canvas is wider
        cw = self.canvas.winfo_width()
        cx = max(display_img.width // 2 + 20, cw // 2)
        cy = display_img.height // 2 + 20

        # Draw drop shadow
        shadow_off = 6
        self.canvas.create_rectangle(
            cx - display_img.width // 2 + shadow_off,
            cy - display_img.height // 2 + shadow_off,
            cx + display_img.width // 2 + shadow_off,
            cy + display_img.height // 2 + shadow_off,
            fill="#030712",
            outline=""
        )

        self.canvas.create_image(cx, cy, image=self.tk_img)
        self.canvas.config(scrollregion=(0, 0, max(cw, display_img.width + 40), display_img.height + 40))

        # Update dimension label
        self.paper_dim_lbl.configure(
            text=f"📐 Size: {img.width}x{img.height} px ({mm_label})"
        )

    def _on_history_select(self, event):
        sel = self.hist_tree.selection()
        if sel:
            idx = int(sel[0])
            if 0 <= idx < len(self.receipt_history):
                self.active_receipt = self.receipt_history[idx]
                self._render_active_receipt()

    def _clear_history(self):
        self.receipt_history.clear()
        self.active_receipt = None
        for item in self.hist_tree.get_children():
            self.hist_tree.delete(item)
        self.canvas.delete("all")
        self.receipts_badge.configure(text="🧾 0 Tickets")
        self.paper_dim_lbl.configure(text="")

    # ─── ZOOM & EXPORTS ───

    def _adjust_zoom(self, delta: float):
        self._set_zoom(max(0.4, min(2.5, self.zoom_level + delta)))

    def _set_zoom(self, level: float):
        self.zoom_level = round(level, 2)
        self.zoom_lbl.configure(text=f"🔍 Zoom: {int(self.zoom_level * 100)}%")
        self._render_active_receipt()

    def _copy_to_clipboard(self):
        if not self.active_receipt:
            return
        img = VirtualReceiptRenderer.render(self.active_receipt)
        if img:
            ok = VirtualReceiptRenderer.copy_image_to_clipboard(img)
            if ok:
                self.copy_btn.configure(text="✓ Copied!")
                self.after(1500, lambda: self.copy_btn.configure(text="📋 Copy"))
            else:
                messagebox.showinfo("AxePrint Studio", "Receipt image copied (or saved to clipboard buffer).")

    def _save_as_png(self):
        if not self.active_receipt:
            return
        img = VirtualReceiptRenderer.render(self.active_receipt)
        if not img:
            return
        
        filename = f"receipt_{self.active_receipt.profile.name.replace(' ', '_')}_{int(time.time())}.png"
        path = filedialog.asksaveasfilename(
            parent=self,
            title="Save Receipt Image (PNG)",
            initialfile=filename,
            defaultextension=".png",
            filetypes=[("PNG Image", "*.png"), ("All Files", "*.*")]
        )
        if path:
            img.save(path, "PNG")
            messagebox.showinfo("AxePrint Studio", f"Receipt saved successfully to:\n{path}")

    def _save_as_pdf(self):
        if not self.active_receipt:
            return
        img = VirtualReceiptRenderer.render(self.active_receipt)
        if not img:
            return

        filename = f"receipt_{self.active_receipt.profile.name.replace(' ', '_')}_{int(time.time())}.pdf"
        path = filedialog.asksaveasfilename(
            parent=self,
            title="Save Receipt as PDF",
            initialfile=filename,
            defaultextension=".pdf",
            filetypes=[("PDF Document", "*.pdf"), ("All Files", "*.*")]
        )
        if path:
            VirtualReceiptRenderer.save_image_as_pdf(img, path)
            messagebox.showinfo("AxePrint Studio", f"PDF receipt saved successfully to:\n{path}")

    def _format_bytes(self, num: int) -> str:
        for unit in ["B", "KB", "MB"]:
            if abs(num) < 1024.0:
                return f"{num:.1f} {unit}" if unit != "B" else f"{num} B"
            num /= 1024.0
        return f"{num:.1f} GB"

    def _on_close(self):
        self._stop_listeners()
        self.destroy()
