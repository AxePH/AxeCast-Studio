"""
AxePrint Studio - Virtual Thermal Printer Engine 🖨️
Supports Bluetooth SPP (Serial COM), Network (TCP Port 9100 / ADB),
ESC/POS Thai CP874/TIS-620 parsing, GS v 0 raster bitmaps, QR codes,
and printer profiles (Woosim WSP-R241, Sewoo LK-P30, Sewoo LK-P21, Generic).
"""

import os
import sys
import time
import socket
import select
import threading
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Callable, Tuple, Any
from io import BytesIO

from PIL import Image, ImageDraw, ImageFont
import qrcode

# Try importing pyserial with graceful fallback
try:
    import serial
    import serial.tools.list_ports
    HAS_SERIAL = True
except ImportError:
    HAS_SERIAL = False
    serial = None


def get_bluetooth_device_info() -> Tuple[Optional[str], Optional[str]]:
    """
    Returns (bluetooth_mac, device_name) for this computer across Windows, macOS, and Linux.
    Used for easy Bluetooth pairing when mobile phone discovers PC as 'Unknown'.
    """
    import socket
    hostname = socket.gethostname()

    # 1. Windows / Common: psutil network interfaces
    try:
        import psutil
        for if_name, addrs in psutil.net_if_addrs().items():
            if "bluetooth" in if_name.lower() or "bth" in if_name.lower():
                for a in addrs:
                    if hasattr(psutil, "AF_LINK") and a.family == psutil.AF_LINK and a.address:
                        return a.address.upper().replace("-", ":"), hostname
    except Exception:
        pass

    # 2. macOS: system_profiler SPBluetoothDataType
    if sys.platform == "darwin":
        try:
            import subprocess
            import re
            out = subprocess.check_output(["system_profiler", "SPBluetoothDataType"], text=True, timeout=2.0)
            m = re.search(r"Address:\s*([0-9A-Fa-f]{2}[:-][0-9A-Fa-f]{2}[:-][0-9A-Fa-f]{2}[:-][0-9A-Fa-f]{2}[:-][0-9A-Fa-f]{2}[:-][0-9A-Fa-f]{2})", out)
            if m:
                return m.group(1).upper().replace("-", ":"), hostname
        except Exception:
            pass

    # 3. Linux: /sys/class/bluetooth/hci0/address or bluetoothctl
    elif sys.platform.startswith("linux"):
        try:
            for p in ("/sys/class/bluetooth/hci0/address", "/sys/class/bluetooth/hci1/address"):
                if os.path.exists(p):
                    with open(p, "r") as f:
                        addr = f.read().strip().upper().replace("-", ":")
                        if addr:
                            return addr, hostname
            import subprocess
            import re
            out = subprocess.check_output(["bluetoothctl", "show"], text=True, timeout=2.0)
            m = re.search(r"Controller\s+([0-9A-Fa-f:]{17})", out)
            if m:
                return m.group(1).upper(), hostname
        except Exception:
            pass

    return None, hostname


# ==============================================================================
# 1. PRINTER MODEL PROFILES
# ==============================================================================

@dataclass
class PrinterModelProfile:
    """Hardware specifications & configuration for virtual thermal printer models."""
    id: str
    name: str
    brand: str
    paper_width_mm: int
    printable_dots: int
    dots_per_mm: int = 8  # 203 DPI = 8 dots/mm
    cpl_font_a: int = 32  # 12 dots width
    cpl_font_b: int = 42  # 9 dots width
    default_encoding: str = "cp874"  # x-IBM874 / TIS-620
    engine: str = "GENERIC_ESCPOS"   # GENERIC_ESCPOS or SEWOO_SDK
    thai_codepage: str = "x-IBM874 / Table 30"
    has_cutter: bool = True
    description: str = ""

    @property
    def display_name(self) -> str:
        return f"{self.name} ({self.paper_width_mm}mm)"


PRINTER_PROFILES: Dict[str, PrinterModelProfile] = {
    "woosim_wsp_r241": PrinterModelProfile(
        id="woosim_wsp_r241",
        name="Woosim WSP-R241",
        brand="Woosim",
        paper_width_mm=58,
        printable_dots=384,
        dots_per_mm=8,
        cpl_font_a=32,
        cpl_font_b=42,
        default_encoding="cp874",
        engine="GENERIC_ESCPOS",
        thai_codepage="x-IBM874 / Table 30",
        has_cutter=False,
        description="2-inch Ultra Compact Mobile Bluetooth Printer (384 dots, 203 DPI, 32 CPL)"
    ),
    "sewoo_lk_p30": PrinterModelProfile(
        id="sewoo_lk_p30",
        name="Sewoo LK-P30",
        brand="Sewoo",
        paper_width_mm=80,
        printable_dots=576,
        dots_per_mm=8,
        cpl_font_a=48,
        cpl_font_b=64,
        default_encoding="cp874",
        engine="SEWOO_SDK",
        thai_codepage="TIS-620",
        has_cutter=True,
        description="3-inch Rugged Mobile & POS Bluetooth/Wi-Fi Printer (576 dots, 203 DPI, 48 CPL)"
    ),
    "sewoo_lk_p21": PrinterModelProfile(
        id="sewoo_lk_p21",
        name="Sewoo LK-P21",
        brand="Sewoo",
        paper_width_mm=58,
        printable_dots=384,
        dots_per_mm=8,
        cpl_font_a=32,
        cpl_font_b=42,
        default_encoding="cp874",
        engine="SEWOO_SDK",
        thai_codepage="TIS-620",
        has_cutter=False,
        description="2-inch Lightweight Mobile Bluetooth Printer (384 dots, 203 DPI, 32 CPL)"
    ),
    "generic_58mm": PrinterModelProfile(
        id="generic_58mm",
        name="Generic ESC/POS (58mm)",
        brand="Generic",
        paper_width_mm=58,
        printable_dots=384,
        dots_per_mm=8,
        cpl_font_a=32,
        cpl_font_b=42,
        default_encoding="cp874",
        engine="GENERIC_ESCPOS",
        thai_codepage="x-IBM874 / Table 30",
        has_cutter=False,
        description="Standard 58mm Thermal Printer (384 dots, 203 DPI, 32 CPL)"
    ),
    "generic_80mm": PrinterModelProfile(
        id="generic_80mm",
        name="Generic ESC/POS (80mm)",
        brand="Generic",
        paper_width_mm=80,
        printable_dots=576,
        dots_per_mm=8,
        cpl_font_a=48,
        cpl_font_b=64,
        default_encoding="cp874",
        engine="GENERIC_ESCPOS",
        thai_codepage="x-IBM874 / Table 30",
        has_cutter=True,
        description="Standard 80mm High-Speed POS Thermal Printer (576 dots, 203 DPI, 48 CPL)"
    )
}

DEFAULT_PROFILE_ID = "woosim_wsp_r241"


# ==============================================================================
# 2. RECEIPT DOCUMENT & ELEMENT MODEL
# ==============================================================================

@dataclass
class ReceiptElement:
    """Base element on a virtual receipt."""
    align: str = "left"  # "left", "center", "right"


@dataclass
class TextElement(ReceiptElement):
    text: str = ""
    font_size: int = 1  # 1 = Normal, 2 = Double Height, 3 = Double Width/Height, etc.
    bold: bool = False
    underline: bool = False
    invert: bool = False
    font_type: str = "A"  # "A" (12x24) or "B" (9x24)


@dataclass
class ImageElement(ReceiptElement):
    image: Image.Image = None
    width: int = 0
    height: int = 0


@dataclass
class QRCodeElement(ReceiptElement):
    data: str = ""
    module_size: int = 4
    error_correction: str = "M"


@dataclass
class BarcodeElement(ReceiptElement):
    data: str = ""
    system: str = "CODE128"
    height: int = 64


@dataclass
class LineElement(ReceiptElement):
    line_style: str = "solid"  # "solid", "dashed", "double"


@dataclass
class FeedElement(ReceiptElement):
    lines: int = 1


@dataclass
class CutElement(ReceiptElement):
    cut_type: str = "partial"  # "full", "partial"


class ReceiptDocument:
    """Represents a fully parsed receipt containing sequential elements."""
    def __init__(self, profile: PrinterModelProfile):
        self.profile = profile
        self.elements: List[ReceiptElement] = []
        self.created_at = time.time()
        self.raw_bytes_count = 0
        self._rendered_image: Optional[Image.Image] = None

    def add_element(self, elem: ReceiptElement):
        self.elements.append(elem)
        self._rendered_image = None

    def is_empty(self) -> bool:
        return len(self.elements) == 0


# ==============================================================================
# 3. ESC/POS & THAI CP874 PARSER ENGINE
# ==============================================================================

class ESCPOSParser:
    """
    High-performance, robust byte-stream parser for ESC/POS commands with full
    Thai CP874/TIS-620, GS v 0 raster bitmaps, QR code, and barcode decoding.
    """

    def __init__(self, profile: PrinterModelProfile, on_receipt_complete: Optional[Callable[[ReceiptDocument], None]] = None):
        self.profile = profile
        self.on_receipt_complete = on_receipt_complete
        self.current_receipt = ReceiptDocument(profile)
        
        # Parser formatting state
        self.align = "left"
        self.bold = False
        self.underline = False
        self.font_size = 1
        self.font_type = "A"
        self.invert = False
        self.line_spacing = 30
        self.encoding = profile.default_encoding
        
        # Buffer for continuous text
        self._text_buffer = []
        self._qr_buffer = ""
        self._last_data_time = time.time()
        self._lock = threading.Lock()

    def set_profile(self, profile: PrinterModelProfile):
        with self._lock:
            self.profile = profile
            if self.current_receipt.is_empty():
                self.current_receipt.profile = profile

    def _flush_text(self):
        """Flushes accumulated character buffer into a TextElement."""
        if not self._text_buffer:
            return
        
        raw_bytes = bytes(self._text_buffer)
        self._text_buffer.clear()
        
        # 1. Smart Thai & Unicode Decoder
        # In modern mobile apps (TechServ, Android, React Native, Kotlin), strings are sent as UTF-8.
        # Check UTF-8 first: strict UTF-8 decoding avoids false positives.
        decoded = ""
        try:
            decoded = raw_bytes.decode("utf-8")
        except UnicodeDecodeError:
            decoded = ""
        
        # 2. If UTF-8 failed, try Thai legacy codepages (CP874, TIS-620, ISO-8859-11)
        if not decoded:
            for enc in (self.encoding, "cp874", "tis-620", "iso-8859-11", "windows-874"):
                try:
                    decoded = raw_bytes.decode(enc)
                    break
                except Exception:
                    continue

        # 3. Fallback to Latin-1 with replacement
        if not decoded:
            decoded = raw_bytes.decode("latin1", errors="replace")

        if decoded:
            self.current_receipt.add_element(TextElement(
                align=self.align,
                text=decoded,
                font_size=self.font_size,
                bold=self.bold,
                underline=self.underline,
                invert=self.invert,
                font_type=self.font_type
            ))

    def parse_bytes(self, data: bytes):
        """Feed a stream of bytes into the parser."""
        if not data:
            return

        with self._lock:
            self.current_receipt.raw_bytes_count += len(data)
            self._last_data_time = time.time()
            i = 0
            n = len(data)

            while i < n:
                b = data[i]

                # 1. ESC Commands (0x1B)
                if b == 0x1B and i + 1 < n:
                    cmd = data[i + 1]

                    # ESC @ : Initialize Printer
                    if cmd == 0x40:
                        self._flush_text()
                        self.align = "left"
                        self.bold = False
                        self.underline = False
                        self.font_size = 1
                        self.font_type = "A"
                        self.invert = False
                        i += 2
                        continue

                    # ESC a n : Select Justification (0=L, 1=C, 2=R)
                    elif cmd == 0x61 and i + 2 < n:
                        self._flush_text()
                        val = data[i + 2]
                        if val in (0, 48):
                            self.align = "left"
                        elif val in (1, 49):
                            self.align = "center"
                        elif val in (2, 50):
                            self.align = "right"
                        i += 3
                        continue

                    # ESC E n : Turn Bold On/Off
                    elif cmd == 0x45 and i + 2 < n:
                        self._flush_text()
                        self.bold = bool(data[i + 2] & 1)
                        i += 3
                        continue

                    # ESC - n : Turn Underline On/Off
                    elif cmd == 0x2D and i + 2 < n:
                        self._flush_text()
                        self.underline = bool(data[i + 2] & 1)
                        i += 3
                        continue

                    # ESC ! n : Select Print Mode
                    elif cmd == 0x21 and i + 2 < n:
                        self._flush_text()
                        val = data[i + 2]
                        self.font_type = "B" if (val & 1) else "A"
                        self.bold = bool(val & 8)
                        dbl_h = bool(val & 16)
                        dbl_w = bool(val & 32)
                        self.underline = bool(val & 128)
                        self.font_size = 3 if (dbl_h and dbl_w) else (2 if (dbl_h or dbl_w) else 1)
                        i += 3
                        continue

                    # ESC M n : Select Font (0=Font A, 1=Font B)
                    elif cmd == 0x4D and i + 2 < n:
                        self._flush_text()
                        self.font_type = "B" if data[i + 2] in (1, 49) else "A"
                        i += 3
                        continue

                    # ESC d n : Print and Feed n lines
                    elif cmd == 0x64 and i + 2 < n:
                        self._flush_text()
                        lines = data[i + 2]
                        self.current_receipt.add_element(FeedElement(lines=max(1, lines)))
                        i += 3
                        continue

                    # ESC 2 / ESC 3 n : Line Spacing
                    elif cmd == 0x32:
                        self.line_spacing = 30
                        i += 2
                        continue
                    elif cmd == 0x33 and i + 2 < n:
                        self.line_spacing = data[i + 2]
                        i += 3
                        continue

                    # ESC t n : Character Code Table
                    elif cmd == 0x74 and i + 2 < n:
                        table = data[i + 2]
                        # 30 (0x1E): Woosim / x-IBM874 Table 30, 21, 26, 47, 48: Standard ESC/POS Thai
                        if table in (30, 0x1E, 21, 26, 47, 48):
                            self.encoding = "cp874"
                        i += 3
                        continue

                    # ESC i / ESC m : Paper Cut
                    elif cmd in (0x69, 0x6D):
                        self._flush_text()
                        self._emit_cut(cut_type="partial")
                        i += 2
                        continue

                    # ESC * m nL nH d1...dk : Column Format Bit Image
                    elif cmd == 0x2A and i + 4 < n:
                        m = data[i + 2]
                        nL = data[i + 3]
                        nH = data[i + 4]
                        num_cols = nL + (nH << 8)
                        bytes_per_col = 3 if m in (32, 33) else 1
                        img_bytes_len = num_cols * bytes_per_col
                        if i + 5 + img_bytes_len <= n:
                            raw_img = data[i + 5 : i + 5 + img_bytes_len]
                            self._flush_text()
                            img = self._decode_column_bitmap(raw_img, num_cols, bytes_per_col)
                            if img:
                                self.current_receipt.add_element(ImageElement(
                                    align=self.align, image=img, width=img.width, height=img.height
                                ))
                            i += 5 + img_bytes_len
                            continue

                # 2. GS Commands (0x1D)
                elif b == 0x1D and i + 1 < n:
                    cmd = data[i + 1]

                    # GS ! n : Character Size Multiplier
                    if cmd == 0x21 and i + 2 < n:
                        self._flush_text()
                        val = data[i + 2]
                        w_mult = ((val >> 4) & 0x07) + 1
                        h_mult = (val & 0x07) + 1
                        self.font_size = max(w_mult, h_mult)
                        i += 3
                        continue

                    # GS B n : White/Black Reverse Printing (Invert)
                    elif cmd == 0x42 and i + 2 < n:
                        self._flush_text()
                        self.invert = bool(data[i + 2] & 1)
                        i += 3
                        continue

                    # GS V m [n] : Cut Paper
                    elif cmd == 0x56 and i + 2 < n:
                        self._flush_text()
                        m_val = data[i + 2]
                        skip = 3
                        if m_val in (65, 66, 97, 98) and i + 3 < n:
                            skip = 4
                        self._emit_cut(cut_type="full" if m_val in (0, 48, 65) else "partial")
                        i += skip
                        continue

                    # GS v 0 m xL xH yL yH d1...dk : Raster Bit Image (Standard in Mobile Printing)
                    elif cmd == 0x76 and i + 7 < n and data[i + 2] == 0x30:
                        m_mode = data[i + 3]
                        xL = data[i + 4]
                        xH = data[i + 5]
                        yL = data[i + 6]
                        yH = data[i + 7]
                        x_bytes = xL + (xH << 8)
                        y_dots = yL + (yH << 8)
                        total_img_len = x_bytes * y_dots

                        if i + 8 + total_img_len <= n:
                            raw_raster = data[i + 8 : i + 8 + total_img_len]
                            self._flush_text()
                            img = self._decode_raster_bitmap(raw_raster, x_bytes, y_dots, m_mode)
                            if img:
                                self.current_receipt.add_element(ImageElement(
                                    align=self.align, image=img, width=img.width, height=img.height
                                ))
                            i += 8 + total_img_len
                            continue

                    # GS ( k pL pH cn fn m ... : QR Code Function
                    elif cmd == 0x28 and i + 6 < n and data[i + 2] == 0x6B:
                        pL = data[i + 3]
                        pH = data[i + 4]
                        param_len = pL + (pH << 8)
                        cn = data[i + 5]
                        fn = data[i + 6]

                        # Store QR Code Data (fn = 80)
                        if cn == 49 and fn == 80 and i + 7 + (param_len - 3) <= n:
                            qr_data_bytes = data[i + 7 : i + 7 + (param_len - 3)]
                            try:
                                self._qr_buffer = qr_data_bytes.decode("utf-8")
                            except Exception:
                                self._qr_buffer = qr_data_bytes.decode("latin1", errors="replace")
                            i += 4 + param_len
                            continue

                        # Print QR Code (fn = 81)
                        elif cn == 49 and fn == 81:
                            self._flush_text()
                            if self._qr_buffer:
                                self.current_receipt.add_element(QRCodeElement(
                                    align=self.align, data=self._qr_buffer, module_size=4
                                ))
                                self._qr_buffer = ""
                            i += 7
                            continue
                        else:
                            i += 4 + param_len
                            continue

                    # GS k m [n] d1...dk : Barcode
                    elif cmd == 0x6B and i + 3 < n:
                        m_sys = data[i + 2]
                        self._flush_text()
                        # Form B with length prefix
                        if m_sys >= 65:
                            b_len = data[i + 3]
                            if i + 4 + b_len <= n:
                                b_data = data[i + 4 : i + 4 + b_len].decode("latin1", errors="replace")
                                self.current_receipt.add_element(BarcodeElement(align=self.align, data=b_data))
                                i += 4 + b_len
                                continue
                        else:
                            # NUL terminated
                            nul_idx = data.find(b"\x00", i + 3)
                            if nul_idx != -1:
                                b_data = data[i + 3 : nul_idx].decode("latin1", errors="replace")
                                self.current_receipt.add_element(BarcodeElement(align=self.align, data=b_data))
                                i = nul_idx + 1
                                continue

                # 3. Line Feeds & Form Feeds
                elif b == 0x0A:  # LF
                    self._flush_text()
                    self.current_receipt.add_element(FeedElement(lines=1))
                    i += 1
                    continue
                elif b == 0x0D:  # CR (ignore if followed by LF)
                    i += 1
                    continue
                elif b == 0x0C:  # FF (Form Feed / Page Cut)
                    self._flush_text()
                    self._emit_cut(cut_type="full")
                    i += 1
                    continue

                # 4. Standard Text Bytes
                else:
                    self._text_buffer.append(b)
                    i += 1

    def _decode_raster_bitmap(self, raw_bytes: bytes, width_bytes: int, height_dots: int, mode: int = 0) -> Optional[Image.Image]:
        """Converts ESC/POS GS v 0 1-bit raster data to a PIL Image."""
        try:
            width = width_bytes * 8
            height = height_dots
            # Mode '1' image from bytes (1 = black, 0 = white)
            img = Image.frombytes("1", (width, height), raw_bytes, "raw", "1;I")
            img = img.convert("L")
            
            # Apply scaling mode if requested
            scale_x = 2 if mode in (1, 3) else 1
            scale_y = 2 if mode in (2, 3) else 1
            if scale_x > 1 or scale_y > 1:
                img = img.resize((width * scale_x, height * scale_y), Image.NEAREST)

            # Restrict image to printable width
            max_w = self.profile.printable_dots
            if img.width > max_w:
                ratio = max_w / img.width
                img = img.resize((max_w, int(img.height * ratio)), Image.LANCZOS)

            return img
        except Exception as e:
            print(f"Error decoding raster bitmap: {e}")
            return None

    def _decode_column_bitmap(self, raw_bytes: bytes, num_cols: int, bytes_per_col: int) -> Optional[Image.Image]:
        """Converts ESC * column-oriented bitmap to a standard PIL Image."""
        try:
            height = bytes_per_col * 8
            width = num_cols
            img = Image.new("L", (width, height), 255)
            pixels = img.load()

            idx = 0
            for x in range(width):
                for b_idx in range(bytes_per_col):
                    if idx >= len(raw_bytes):
                        break
                    byte_val = raw_bytes[idx]
                    idx += 1
                    for bit in range(8):
                        y = b_idx * 8 + bit
                        if y < height:
                            is_black = (byte_val >> (7 - bit)) & 1
                            pixels[x, y] = 0 if is_black else 255
            return img
        except Exception as e:
            print(f"Error decoding column bitmap: {e}")
            return None

    def _emit_cut(self, cut_type: str = "partial"):
        """Finalizes the current receipt and notifies the listener."""
        self._flush_text()
        if not self.current_receipt.is_empty():
            self.current_receipt.add_element(CutElement(cut_type=cut_type))
            completed = self.current_receipt
            self.current_receipt = ReceiptDocument(self.profile)
            if self.on_receipt_complete:
                self.on_receipt_complete(completed)

    def check_timeout_autocut(self, timeout_sec: float = 0.8):
        """If data has stopped arriving and there is uncommitted content, auto-cut."""
        with self._lock:
            has_pending = (not self.current_receipt.is_empty()) or (len(self._text_buffer) > 0)
            if has_pending and (time.time() - self._last_data_time > timeout_sec):
                self._flush_text()
                if not self.current_receipt.is_empty():
                    self._emit_cut(cut_type="partial")


# ==============================================================================
# 4. VIRTUAL RECEIPT CANVAS RENDERER
# ==============================================================================

class VirtualReceiptRenderer:
    """
    Renders ReceiptDocument into photorealistic thermal paper receipts
    with accurate typography, Thai combining characters, barcodes, and logos.
    """

    FONT_CANDIDATES = [
        # macOS Thai & Receipt Monospace Fonts (Ayuthaya & Tahoma produce the exact authentic thermal look!)
        "Ayuthaya.ttf", "Tahoma.ttf", "Tahoma Bold.ttf", "Sathu.ttf", "Silom.ttf",
        "Thonburi.ttc", "SukhumvitSet.ttc", "Krungthep.ttf",
        # Windows Thai Fonts
        "tahoma.ttf", "tahomabd.ttf", "leelawad.ttf", "leelawdb.ttf", "Leelawadee.ttf",
        "cordia.ttc", "cordiab.ttc", "angsana.ttc", "angsanab.ttc", "seguisb.ttf",
        # Linux Thai Fonts
        "Loma.ttf", "Loma-Bold.ttf", "Waree.ttf", "Garuda.ttf", "Norasi.ttf", "Umpush.ttf", "DejaVuSans.ttf"
    ]

    FONT_DIRS = [
        # macOS (Supplemental holds all Thai fonts including Ayuthaya on modern macOS!)
        "/System/Library/Fonts/Supplemental",
        "/Library/Fonts",
        os.path.expanduser("~/Library/Fonts"),
        "/System/Library/Fonts",
        # Windows
        os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts"),
        # Linux
        "/usr/share/fonts/truetype/tlwg",
        "/usr/share/fonts/truetype",
        "/usr/share/fonts/opentype",
        "/usr/share/fonts",
        "/usr/local/share/fonts",
        os.path.expanduser("~/.fonts")
    ]

    @classmethod
    def get_thai_font(cls, size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
        """Finds best available TrueType font supporting Thai & Unicode across Windows, macOS, and Linux."""
        test_char = "ก"
        dummy_draw = ImageDraw.Draw(Image.new("L", (1, 1)))

        for font_dir in cls.FONT_DIRS:
            if not os.path.exists(font_dir):
                continue
            for font_name in cls.FONT_CANDIDATES:
                if bold:
                    # Prefer bold variant if present
                    name_lower = font_name.lower()
                    if "bold" not in name_lower and "bd" not in name_lower:
                        bold_cand = font_name.replace(".ttf", " Bold.ttf").replace(".ttf", "bd.ttf")
                        bold_path = os.path.join(font_dir, bold_cand)
                        if os.path.exists(bold_path):
                            try:
                                f = ImageFont.truetype(bold_path, size)
                                bbox = dummy_draw.textbbox((0, 0), test_char, font=f)
                                if bbox[2] - bbox[0] > 0:
                                    return f
                            except Exception:
                                pass
                full_path = os.path.join(font_dir, font_name)
                if os.path.exists(full_path):
                    try:
                        font = ImageFont.truetype(full_path, size)
                        # Verify that this font actually renders Thai characters properly (not empty tofu boxes)
                        bbox = dummy_draw.textbbox((0, 0), test_char, font=font)
                        if bbox[2] - bbox[0] > 0:
                            return font
                    except Exception:
                        continue
        
        # Fallback to default
        try:
            return ImageFont.load_default()
        except Exception:
            return None

    @classmethod
    def _wrap_text(cls, text: str, font, max_w: int, draw: ImageDraw.Draw) -> List[str]:
        """Wraps text cleanly without splitting Thai consonants from vowels/tone marks."""
        THAI_COMBINING = set('\u0e31\u0e34\u0e35\u0e36\u0e37\u0e38\u0e39\u0e3a\u0e47\u0e48\u0e49\u0e4a\u0e4b\u0e4c\u0e4d\u0e4e')
        lines = []
        cur = ""
        for ch in text:
            test = cur + ch
            bbox = draw.textbbox((0, 0), test, font=font)
            if bbox[2] - bbox[0] > max_w and cur and ch not in THAI_COMBINING:
                lines.append(cur)
                cur = ch
            else:
                cur = test
        if cur:
            lines.append(cur)
        return lines or [text]

    @classmethod
    def render(cls, doc: ReceiptDocument, target_width_mm: Optional[int] = None, auto_fit: bool = False, auto_wrap: bool = True) -> Image.Image:
        """Renders complete ReceiptDocument into a crisp PIL Image with custom or auto-fit paper width."""
        profile = doc.profile

        # Dynamic paper width selection
        if auto_fit:
            base_font_size = 18
            f_meas = cls.get_thai_font(base_font_size)
            dummy = Image.new("RGB", (100, 100))
            d_meas = ImageDraw.Draw(dummy)
            max_w = 384
            for elem in doc.elements:
                if isinstance(elem, TextElement):
                    bb = d_meas.textbbox((0, 0), elem.text, font=f_meas)
                    max_w = max(max_w, bb[2] - bb[0])
                elif isinstance(elem, ImageElement) and elem.image:
                    max_w = max(max_w, elem.image.width)
            paper_dots = max(384, max_w + 16)
        elif target_width_mm == 80:
            paper_dots = 576
        elif target_width_mm == 58:
            paper_dots = 384
        elif target_width_mm:
            paper_dots = int(target_width_mm * 8)
        else:
            paper_dots = profile.printable_dots

        side_margin = 16
        content_width = paper_dots
        canvas_width = content_width + (side_margin * 2)

        # Base typography sizes (scaled for 203 DPI)
        effective_mm = target_width_mm or (int(paper_dots / 8) if auto_fit else profile.paper_width_mm)
        base_font_size = 20 if effective_mm >= 80 else 18
        font_regular = cls.get_thai_font(base_font_size, bold=False)
        font_bold = cls.get_thai_font(base_font_size, bold=True)
        font_large = cls.get_thai_font(int(base_font_size * 1.5), bold=True)
        font_xlarge = cls.get_thai_font(int(base_font_size * 2.0), bold=True)
        font_small = cls.get_thai_font(int(base_font_size * 0.85), bold=False)

        # Measure total height required
        y = 24  # Top padding
        line_h = base_font_size + 8

        # Dummy draw for measurement
        dummy_img = Image.new("RGB", (canvas_width, 100))
        dummy_draw = ImageDraw.Draw(dummy_img)

        # First pass: Calculate layout and element positions
        layout_items = []

        for elem in doc.elements:
            if isinstance(elem, TextElement):
                # Choose appropriate font
                if elem.font_size >= 3:
                    f = font_xlarge
                    lh = int(line_h * 2.0)
                elif elem.font_size == 2:
                    f = font_large
                    lh = int(line_h * 1.5)
                elif elem.font_type == "B":
                    f = font_small
                    lh = int(line_h * 0.85)
                elif elem.bold:
                    f = font_bold
                    lh = line_h
                else:
                    f = font_regular
                    lh = line_h

                # Calculate text width
                bbox = dummy_draw.textbbox((0, 0), elem.text, font=f)
                tw = bbox[2] - bbox[0]
                th = bbox[3] - bbox[1]

                # Auto-wrap if text exceeds content width
                if auto_wrap and tw > content_width and len(elem.text) > 1 and not auto_fit:
                    wrapped_lines = cls._wrap_text(elem.text, f, content_width, dummy_draw)
                    for line_text in wrapped_lines:
                        l_bbox = dummy_draw.textbbox((0, 0), line_text, font=f)
                        l_tw = l_bbox[2] - l_bbox[0]
                        l_th = l_bbox[3] - l_bbox[1]
                        if elem.align == "center":
                            x = side_margin + max(0, (content_width - l_tw) // 2)
                        elif elem.align == "right":
                            x = side_margin + max(0, content_width - l_tw)
                        else:
                            x = side_margin
                        layout_items.append(("text", elem, x, y, f, l_tw, l_th, line_text))
                        y += max(lh, l_th + 4)
                else:
                    if elem.align == "center":
                        x = side_margin + max(0, (content_width - tw) // 2)
                    elif elem.align == "right":
                        x = side_margin + max(0, content_width - tw)
                    else:
                        x = side_margin
                    layout_items.append(("text", elem, x, y, f, tw, th, elem.text))
                    y += max(lh, th + 4)

            elif isinstance(elem, ImageElement):
                img = elem.image
                if img:
                    # Scale to fit width if necessary
                    iw, ih = img.size
                    if iw > content_width:
                        ratio = content_width / iw
                        iw = content_width
                        ih = int(ih * ratio)
                        img = img.resize((iw, ih), Image.LANCZOS)

                    if elem.align == "center":
                        x = side_margin + max(0, (content_width - iw) // 2)
                    elif elem.align == "right":
                        x = side_margin + max(0, content_width - iw)
                    else:
                        x = side_margin

                    layout_items.append(("image", img, x, y, iw, ih))
                    y += ih + 10

            elif isinstance(elem, QRCodeElement):
                qr_img = cls._generate_qr_image(elem.data, content_width)
                if qr_img:
                    qw, qh = qr_img.size
                    if elem.align == "center":
                        x = side_margin + max(0, (content_width - qw) // 2)
                    elif elem.align == "right":
                        x = side_margin + max(0, content_width - qw)
                    else:
                        x = side_margin
                    layout_items.append(("qr", qr_img, x, y, qw, qh))
                    y += qh + 12

            elif isinstance(elem, BarcodeElement):
                bc_img = cls._generate_barcode_image(elem.data, content_width)
                if bc_img:
                    bw, bh = bc_img.size
                    x = side_margin + max(0, (content_width - bw) // 2)
                    layout_items.append(("barcode", bc_img, x, y, bw, bh))
                    y += bh + 10

            elif isinstance(elem, FeedElement):
                y += elem.lines * (line_h // 2)

            elif isinstance(elem, CutElement):
                layout_items.append(("cut", elem, side_margin, y, content_width, 16))
                y += 24

        total_height = max(180, y + 24)

        # Second pass: Render onto final canvas
        canvas = Image.new("RGB", (canvas_width, total_height), "#FFFFFF")
        draw = ImageDraw.Draw(canvas)

        # Thermal print ink color (dark charcoal)
        ink_color = (17, 24, 39)

        for item in layout_items:
            kind = item[0]
            if kind == "text":
                _, elem, x, item_y, f, tw, th, line_text = item
                if elem.invert:
                    # Inverted text background
                    draw.rectangle([x - 2, item_y - 2, x + tw + 2, item_y + th + 2], fill=ink_color)
                    draw.text((x, item_y), line_text, font=f, fill=(255, 255, 255))
                else:
                    draw.text((x, item_y), line_text, font=f, fill=ink_color)
                if elem.underline:
                    draw.line([x, item_y + th + 2, x + tw, item_y + th + 2], fill=ink_color, width=2)

            elif kind == "image":
                _, img, x, item_y, _, _ = item
                canvas.paste(img, (x, item_y))

            elif kind in ("qr", "barcode"):
                _, img, x, item_y, _, _ = item
                canvas.paste(img, (x, item_y))

            elif kind == "cut":
                _, _, x, item_y, w, _ = item
                # Draw zigzag tear / perforated cutter line
                dash_len = 8
                gap = 6
                cx = x
                while cx < x + w:
                    draw.line([cx, item_y + 8, min(cx + dash_len, x + w), item_y + 8], fill=(148, 163, 184), width=1)
                    cx += dash_len + gap
                # Label
                cut_lbl = "--- [ CUT / ฉีกกระดาษ ] ---"
                cut_bbox = draw.textbbox((0, 0), cut_lbl, font=font_small)
                cut_w = cut_bbox[2] - cut_bbox[0]
                draw.text((x + (w - cut_w) // 2, item_y), cut_lbl, font=font_small, fill=(148, 163, 184))

        doc._rendered_image = canvas
        return canvas

    @classmethod
    def save_image_as_pdf(cls, img: Image.Image, filepath: str):
        """Saves receipt image as a standard vector-wrapped PDF at 203 DPI."""
        rgb_img = img.convert("RGB")
        rgb_img.save(filepath, "PDF", resolution=203.0)

    @classmethod
    def copy_image_to_clipboard(cls, img: Image.Image) -> bool:
        """Copies receipt image to OS clipboard (supports Windows native DIB, macOS, Linux)."""
        if sys.platform.startswith("win"):
            try:
                import ctypes
                import io
                kernel32 = ctypes.windll.kernel32
                user32 = ctypes.windll.user32
                
                kernel32.GlobalAlloc.restype = ctypes.c_void_p
                kernel32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
                kernel32.GlobalLock.restype = ctypes.c_void_p
                kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
                kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
                user32.OpenClipboard.argtypes = [ctypes.c_void_p]
                user32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]
                
                output = io.BytesIO()
                img.convert("RGB").save(output, "BMP")
                data = output.getvalue()[14:]  # Extract DIB data (exclude BMP file header)
                output.close()
                
                hMem = kernel32.GlobalAlloc(0x0002, len(data))  # GMEM_MOVEABLE
                pMem = kernel32.GlobalLock(hMem)
                ctypes.memmove(pMem, data, len(data))
                kernel32.GlobalUnlock(hMem)
                
                user32.OpenClipboard(None)
                user32.EmptyClipboard()
                user32.SetClipboardData(8, hMem)  # CF_DIB
                user32.CloseClipboard()
                return True
            except Exception as e:
                print(f"Windows clipboard error: {e}")
                return False
        elif sys.platform == "darwin":
            try:
                import tempfile
                import subprocess
                with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
                    temp_path = f.name
                    img.save(temp_path, "PNG")
                cmd = f'set the clipboard to (read (POSIX file "{temp_path}") as «class PNGf»)'
                subprocess.run(["osascript", "-e", cmd], check=True, capture_output=True)
                os.remove(temp_path)
                return True
            except Exception as e:
                print(f"macOS clipboard error: {e}")
                return False
        else:
            try:
                import tempfile
                import subprocess
                with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
                    temp_path = f.name
                    img.save(temp_path, "PNG")
                if subprocess.run(["which", "xclip"], capture_output=True).returncode == 0:
                    subprocess.run(["xclip", "-selection", "clipboard", "-target", "image/png", "-i", temp_path], check=True)
                    os.remove(temp_path)
                    return True
                elif subprocess.run(["which", "wl-copy"], capture_output=True).returncode == 0:
                    with open(temp_path, "rb") as f:
                        subprocess.run(["wl-copy", "--type", "image/png"], stdin=f, check=True)
                    os.remove(temp_path)
                    return True
            except Exception:
                pass
        return False

    @classmethod
    def _generate_qr_image(cls, data: str, max_width: int) -> Optional[Image.Image]:
        """Generates a high-contrast QR code image."""
        try:
            qr = qrcode.QRCode(
                version=None,
                error_correction=qrcode.constants.ERROR_CORRECT_M,
                box_size=5,
                border=2,
            )
            qr.add_data(data)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")
            img = img.convert("RGB")
            
            # Limit size
            max_qr = min(max_width, 180)
            if img.width > max_qr:
                img = img.resize((max_qr, max_qr), Image.NEAREST)
            return img
        except Exception as e:
            print(f"Error generating QR code: {e}")
            return None

    @classmethod
    def _generate_barcode_image(cls, data: str, max_width: int) -> Optional[Image.Image]:
        """Generates simple 1D barcode simulation with text underneath."""
        try:
            bw = min(max_width, 240)
            bh = 60
            img = Image.new("RGB", (bw, bh + 18), "white")
            draw = ImageDraw.Draw(img)

            # Draw barcode lines based on simple hash
            x = 10
            import hashlib
            h_bytes = hashlib.md5(data.encode()).digest()
            while x < bw - 10:
                for b in h_bytes:
                    w1 = 1 if (b & 1) else 2
                    w2 = 1 if (b & 2) else 3
                    draw.rectangle([x, 5, x + w1, bh], fill="black")
                    x += w1 + w2
                    if x >= bw - 10:
                        break

            # Draw barcode text below
            font = cls.get_thai_font(12)
            bbox = draw.textbbox((0, 0), data, font=font)
            tw = bbox[2] - bbox[0]
            draw.text(((bw - tw) // 2, bh + 2), data, font=font, fill="black")
            return img
        except Exception:
            return None


# ==============================================================================
# 5. MULTI-CHANNEL LISTENERS (BLUETOOTH SERIAL COM & TCP PORT 9100)
# ==============================================================================

class SerialPrinterListener:
    """Listens on Inbound Bluetooth COM / Serial ports for ESC/POS byte streams."""

    @staticmethod
    def get_available_ports() -> List[Dict[str, Any]]:
        """Returns list of available serial COM ports with friendly descriptions and incoming flags."""
        if not HAS_SERIAL:
            return []
        incoming_ports = set()
        if sys.platform.startswith("win"):
            try:
                import winreg
                key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'SYSTEM\CurrentControlSet\Enum\BTHENUM')
                for i in range(winreg.QueryInfoKey(key)[0]):
                    sub_name = winreg.EnumKey(key, i)
                    if 'LOCALMFG' in sub_name or '000000000000' in sub_name:
                        sub = winreg.OpenKey(key, sub_name)
                        for j in range(winreg.QueryInfoKey(sub)[0]):
                            dev_name = winreg.EnumKey(sub, j)
                            if '000000000000' in dev_name:
                                try:
                                    dp = winreg.OpenKey(sub, dev_name + r'\Device Parameters')
                                    p, _ = winreg.QueryValueEx(dp, 'PortName')
                                    incoming_ports.add(p)
                                except Exception:
                                    pass
            except Exception:
                pass

        ports = []
        try:
            for p in serial.tools.list_ports.comports():
                is_inc = p.device in incoming_ports
                is_bt = "bluetooth" in p.description.lower() or "bth" in str(p.hwid).lower() or is_inc
                ports.append({
                    "device": p.device,
                    "description": p.description,
                    "is_bluetooth": is_bt,
                    "is_incoming": is_inc
                })
        except Exception:
            pass

        ports.sort(key=lambda x: (not x.get("is_incoming", False), not x.get("is_bluetooth", False), x["device"]))
        return ports

    def __init__(self, parser: ESCPOSParser, on_status_change: Optional[Callable[[str, bool], None]] = None):
        self.parser = parser
        self.on_status_change = on_status_change
        self.ports: List[str] = []
        self.baudrate = 115200
        self._running = False
        self._threads: List[threading.Thread] = []
        self._serials: List[Any] = []
        self._lock = threading.Lock()

    def start(self, port_or_mode: str, baudrate: int = 115200) -> bool:
        if not HAS_SERIAL:
            if self.on_status_change:
                self.on_status_change("pyserial is not installed", False)
            return False

        self.stop()
        self.baudrate = baudrate
        self._running = True

        available = self.get_available_ports()
        incoming = [p["device"] for p in available if p.get("is_incoming")]

        if "all" in port_or_mode.lower() or "auto" in port_or_mode.lower() or "incoming" in port_or_mode.lower():
            target_ports = incoming if incoming else [p["device"] for p in available if p.get("is_bluetooth")]
            if not target_ports and available:
                target_ports = [available[0]["device"]]
        else:
            clean_port = port_or_mode.split()[0]
            target_ports = [clean_port]

        self.ports = target_ports
        if not self.ports:
            if self.on_status_change:
                self.on_status_change("No valid ports found", False)
            return False

        if self.on_status_change:
            port_str = ", ".join(self.ports)
            self.on_status_change(f"🟢 Listening on {port_str} (Ready for mobile)", True)

        for p in self.ports:
            t = threading.Thread(target=self._listen_single_port, args=(p,), daemon=True)
            self._threads.append(t)
            t.start()

        return True

    def _listen_single_port(self, port_name: str):
        ser = None
        while self._running:
            try:
                ser = serial.Serial(port_name, self.baudrate, timeout=0.2)
                with self._lock:
                    self._serials.append(ser)

                while self._running and ser.is_open:
                    if ser.in_waiting > 0:
                        data = ser.read(ser.in_waiting)
                        if data:
                            self.parser.parse_bytes(data)
                    else:
                        time.sleep(0.05)
                        self.parser.check_timeout_autocut()

            except Exception:
                if self._running:
                    time.sleep(1.0)
            finally:
                if ser:
                    self.parser._flush_text()
                    if not self.parser.current_receipt.is_empty():
                        self.parser._emit_cut(cut_type="partial")
                    with self._lock:
                        if ser in self._serials:
                            self._serials.remove(ser)
                    try:
                        ser.close()
                    except Exception:
                        pass
                    ser = None

    def stop(self):
        self._running = False
        with self._lock:
            for s in self._serials:
                try:
                    s.close()
                except Exception:
                    pass
            self._serials.clear()
        self._threads.clear()
        if self.on_status_change:
            self.on_status_change("Standby / Stopped", False)


class TCPPrinterListener:
    """Listens on TCP Port 9100 (Standard RAW ESC/POS Network & ADB Forward)."""

    def __init__(self, parser: ESCPOSParser, on_status_change: Optional[Callable[[str, bool], None]] = None):
        self.parser = parser
        self.on_status_change = on_status_change
        self.port = 9100
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._server_sock: Optional[socket.socket] = None

    def start(self, port: int = 9100) -> bool:
        self.stop()
        self.port = port
        self._running = True
        self._thread = threading.Thread(target=self._server_loop, daemon=True)
        self._thread.start()
        return True

    def stop(self):
        self._running = False
        if self._server_sock:
            try:
                self._server_sock.close()
            except Exception:
                pass
            self._server_sock = None
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=0.5)
        self._thread = None
        if self.on_status_change:
            self.on_status_change("Stopped", False)

    def _server_loop(self):
        try:
            self._server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._server_sock.bind(("0.0.0.0", self.port))
            self._server_sock.listen(5)
            self._server_sock.settimeout(0.5)

            if self.on_status_change:
                self.on_status_change(f"🟢 TCP Port {self.port} (RAW ESC/POS / ADB Ready)", True)

            while self._running:
                try:
                    client, addr = self._server_sock.accept()
                    client.settimeout(0.2)
                    
                    while self._running:
                        try:
                            chunk = client.recv(4096)
                            if not chunk:
                                break
                            self.parser.parse_bytes(chunk)
                        except socket.timeout:
                            self.parser.check_timeout_autocut()
                        except Exception:
                            break

                    client.close()
                    # Trigger auto-cut when client closes connection
                    self.parser._emit_cut(cut_type="partial")

                except socket.timeout:
                    self.parser.check_timeout_autocut()
                except Exception:
                    if self._running:
                        time.sleep(0.1)

        except Exception as e:
            if self._running and self.on_status_change:
                self.on_status_change(f"🔴 TCP Error: {e}", False)
        finally:
            if self._server_sock:
                try:
                    self._server_sock.close()
                except Exception:
                    pass
                self._server_sock = None


# ==============================================================================
# 6. SAMPLE RECEIPT GENERATOR (FOR INSTANT TESTING)
# ==============================================================================

def create_sample_receipt_bytes(profile: PrinterModelProfile) -> bytes:
    """
    Generates authentic Thai ESC/POS byte sequence simulating a real POS receipt
    with Thai CP874 text, alignments, bold, item tables, totals, QR Code, and Cut.
    """
    is_80mm = profile.paper_width_mm >= 80
    sep = "=" * (42 if is_80mm else 32)
    dash = "-" * (42 if is_80mm else 32)

    buf = bytearray()

    # 1. Initialize
    buf.extend(b"\x1B\x40")          # ESC @ : Init
    if profile.engine == "GENERIC_ESCPOS":
        buf.extend(b"\x1B\x74\x1E")  # ESC t 30 : x-IBM874 (Woosim / Generic Table 30)
    else:
        buf.extend(b"\x1B\x74\x15")  # ESC t 21 : TIS-620 (Sewoo SDK standard)

    # 2. Header (Center, Bold, Double Height)
    buf.extend(b"\x1B\x61\x01")      # Center
    buf.extend(b"\x1B\x21\x38")      # Double Height + Double Width + Bold
    buf.extend("AXE DIGITAL CAFE\n".encode("cp874"))
    buf.extend(b"\x1B\x21\x00")      # Normal font
    buf.extend("สาขา: อาคาร AxeCast Studio ชั้น 1\n".encode("cp874"))
    buf.extend("โทร: 02-123-4567 | TAX ID: 0105566778899\n".encode("cp874"))
    buf.extend("ใบเสร็จรับเงิน / ใบกำกับภาษีอย่างย่อ\n".encode("cp874"))
    buf.extend(f"{sep}\n".encode("cp874"))

    # 3. Transaction Details (Left)
    buf.extend(b"\x1B\x61\x00")      # Left
    buf.extend(f"วันที่: {time.strftime('%d/%m/%Y %H:%M:%S')}\n".encode("cp874"))
    buf.extend("เลขที่บิล: REC-20260902-0089\n".encode("cp874"))
    buf.extend("พนักงาน: แคชเชียร์ 01 (TechServ)\n".encode("cp874"))
    buf.extend(f"{dash}\n".encode("cp874"))

    # 4. Item List
    items = [
        ("1x ข้าวกะเพราหมูกรอบไข่ดาว", "85.00"),
        ("1x กาแฟเอสเปรสโซ่เย็น (Espresso)", "65.00"),
        ("1x ชาเขียวมัทฉะลาเต้ (Matcha)", "75.00"),
        ("2x ครัวซองต์เนยสดฝรั่งเศส", "120.00"),
    ]

    for name, price in items:
        total_width = 42 if is_80mm else 30
        p_len = len(price)
        n_len = len(name)
        space_count = max(2, total_width - n_len - p_len)
        line = name + (" " * space_count) + price + "\n"
        buf.extend(line.encode("cp874"))

    buf.extend(f"{dash}\n".encode("cp874"))

    # 5. Totals
    buf.extend(f"รวมเป็นเงิน (Subtotal):           345.00\n".encode("cp874") if is_80mm else f"ยอดรวม (Subtotal):        345.00\n".encode("cp874"))
    buf.extend(f"ภาษีมูลค่าเพิ่ม (VAT 7%):            22.57\n".encode("cp874") if is_80mm else f"VAT 7%:                    22.57\n".encode("cp874"))
    
    # Grand Total (Bold, Double-Height)
    buf.extend(b"\x1B\x45\x01")      # Bold
    buf.extend(b"\x1B\x21\x10")      # Double Height
    buf.extend("ยอดสุทธิ (Total):         THB 345.00\n".encode("cp874") if is_80mm else "ยอดสุทธิ:          THB 345.00\n".encode("cp874"))
    buf.extend(b"\x1B\x21\x00")      # Normal
    buf.extend(b"\x1B\x45\x00")      # Bold off

    buf.extend(f"{sep}\n".encode("cp874"))

    # 6. Payment & PromptPay QR Code (Center)
    buf.extend(b"\x1B\x61\x01")      # Center
    buf.extend("ชำระด้วย: PromptPay QR (ชำระสำเร็จ)\n".encode("cp874"))
    buf.extend("สแกนเพื่อตรวจสอบ e-Tax Invoice\n\n".encode("cp874"))

    # GS ( k : Store & Print QR Code
    qr_data = "https://axecast.app/tax/invoice/20260902-0089?total=345.00"
    qr_bytes = qr_data.encode("utf-8")
    pL = (len(qr_bytes) + 3) & 0xFF
    pH = ((len(qr_bytes) + 3) >> 8) & 0xFF

    # Store QR Data (fn 80)
    buf.extend(b"\x1D\x28\x6B" + bytes([pL, pH, 49, 80, 48]) + qr_bytes)
    # Print QR (fn 81)
    buf.extend(b"\x1D\x28\x6B\x03\x00\x31\x51\x30")

    # 7. Footer & Paper Cut
    buf.extend("\n\nขอบคุณที่ใช้บริการ / Thank you!\n".encode("cp874"))
    buf.extend("WiFi: AxeCast-Guest | Pass: 88888888\n".encode("cp874"))
    buf.extend(b"\x1B\x64\x03")      # Feed 3 lines
    buf.extend(b"\x1D\x56\x01")      # GS V 1 : Cut Paper

    return bytes(buf)
