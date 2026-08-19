import os
import sys
import subprocess
import ctypes
from pathlib import Path

class SystemClipboardHelper:
    """100% Cross-Platform Clipboard Engine (Windows, macOS, Linux) with 64-bit API safety."""
    
    @staticmethod
    def get_copied_files() -> list[str]:
        """Reads copied file paths from Windows Explorer, macOS Finder, or Linux file managers."""
        files = []
        
        # 1. Windows Native CF_HDROP Clipboard
        if sys.platform.startswith("win"):
            try:
                user32 = ctypes.windll.user32
                shell32 = ctypes.windll.shell32
                
                user32.OpenClipboard.argtypes = [ctypes.c_void_p]
                user32.GetClipboardData.argtypes = [ctypes.c_uint]
                user32.GetClipboardData.restype = ctypes.c_void_p
                user32.CloseClipboard.argtypes = []
                shell32.DragQueryFileW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_wchar_p, ctypes.c_uint]
                shell32.DragQueryFileW.restype = ctypes.c_uint
                
                CF_HDROP = 15
                
                if user32.OpenClipboard(None):
                    try:
                        hDrop = user32.GetClipboardData(CF_HDROP)
                        if hDrop:
                            count = shell32.DragQueryFileW(hDrop, 0xFFFFFFFF, None, 0)
                            buf = ctypes.create_unicode_buffer(1024)
                            for i in range(count):
                                shell32.DragQueryFileW(hDrop, i, buf, 1024)
                                p = buf.value
                                if os.path.exists(p):
                                    files.append(p)
                    finally:
                        user32.CloseClipboard()
            except Exception:
                pass
                
        # 2. macOS Finder AppleScript Clipboard
        elif sys.platform == "darwin":
            try:
                osa_cmd = 'try\nset f to (the clipboard as «class furl»)\nPOSIX path of f\nend try'
                res = subprocess.run(["osascript", "-e", osa_cmd], capture_output=True, text=True, timeout=2)
                out = res.stdout.strip()
                if out and os.path.exists(out):
                    files.append(out)
            except Exception:
                pass
                
        # 3. Linux xclip / wl-paste
        elif sys.platform.startswith("linux"):
            try:
                res = subprocess.run(["wl-paste", "-t", "text/uri-list"], capture_output=True, text=True, timeout=1)
                for line in res.stdout.splitlines():
                    if line.startswith("file://"):
                        p = line.replace("file://", "").strip()
                        if os.path.exists(p):
                            files.append(p)
            except Exception:
                try:
                    res = subprocess.run(["xclip", "-selection", "clipboard", "-t", "text/uri-list", "-o"], capture_output=True, text=True, timeout=1)
                    for line in res.stdout.splitlines():
                        if line.startswith("file://"):
                            p = line.replace("file://", "").strip()
                            if os.path.exists(p):
                                files.append(p)
                except Exception:
                    pass

        if files:
            return files
            
        # 4. Universal Fallback: Text clipboard file paths (Win32 CF_UNICODETEXT safe)
        if sys.platform.startswith("win"):
            try:
                user32 = ctypes.windll.user32
                kernel32 = ctypes.windll.kernel32
                CF_UNICODETEXT = 13
                if user32.OpenClipboard(None):
                    try:
                        hMem = user32.GetClipboardData(CF_UNICODETEXT)
                        if hMem:
                            pData = kernel32.GlobalLock(hMem)
                            if pData:
                                text = ctypes.c_wchar_p(pData).value
                                kernel32.GlobalUnlock(hMem)
                                if text:
                                    for line in text.splitlines():
                                        clean = line.strip().strip('"').strip("'")
                                        if clean and os.path.exists(clean):
                                            files.append(clean)
                    finally:
                        user32.CloseClipboard()
            except Exception:
                pass
                
        return files

    @staticmethod
    def set_copied_files(file_paths: list[str]) -> bool:
        """Sets the OS clipboard to contain local file paths on Windows, macOS, or Linux."""
        valid_files = [os.path.abspath(f) for f in file_paths if os.path.exists(f)]
        if not valid_files:
            return False
            
        # 1. Windows CF_HDROP (64-bit API Safe)
        if sys.platform.startswith("win"):
            try:
                user32 = ctypes.windll.user32
                kernel32 = ctypes.windll.kernel32
                
                kernel32.GlobalAlloc.restype = ctypes.c_void_p
                kernel32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
                kernel32.GlobalLock.restype = ctypes.c_void_p
                kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
                kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]

                user32.OpenClipboard.argtypes = [ctypes.c_void_p]
                user32.EmptyClipboard.argtypes = []
                user32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]
                user32.SetClipboardData.restype = ctypes.c_void_p
                user32.CloseClipboard.argtypes = []
                
                CF_HDROP = 15
                GHND = 0x0042
                
                null_char = chr(0)
                files_str = null_char.join(valid_files) + null_char + null_char
                files_bytes = files_str.encode("utf-16le")
                
                total_size = 20 + len(files_bytes)
                hGlobal = kernel32.GlobalAlloc(GHND, total_size)
                if not hGlobal:
                    return False
                    
                pGlobal = kernel32.GlobalLock(hGlobal)
                if not pGlobal:
                    return False
                    
                header = bytearray(20)
                header[0] = 20  # pFiles offset = 20 bytes
                header[16] = 1  # fWide = 1 (Unicode UTF-16LE)
                
                ctypes.memmove(pGlobal, bytes(header), 20)
                ctypes.memmove(pGlobal + 20, files_bytes, len(files_bytes))
                kernel32.GlobalUnlock(hGlobal)
                
                if not user32.OpenClipboard(None):
                    kernel32.GlobalFree(hGlobal)
                    return False
                    
                user32.EmptyClipboard()
                user32.SetClipboardData(CF_HDROP, hGlobal)
                user32.CloseClipboard()
                return True
            except Exception:
                pass
                
        # 2. macOS AppleScript Clipboard
        elif sys.platform == "darwin":
            try:
                if len(valid_files) == 1:
                    cmd = f'set the clipboard to (POSIX file "{valid_files[0]}")'
                else:
                    posix_list = ", ".join([f'POSIX file "{f}"' for f in valid_files])
                    cmd = f'set the clipboard to {{{posix_list}}}'
                subprocess.run(["osascript", "-e", cmd], timeout=3)
                return True
            except Exception:
                pass
                
        # 3. Linux xclip / wl-copy
        elif sys.platform.startswith("linux"):
            try:
                uri_list = "\n".join([f"file://{f}" for f in valid_files])
                subprocess.run(["xclip", "-selection", "clipboard", "-t", "text/uri-list"], input=uri_list.encode("utf-8"), timeout=1)
                return True
            except Exception:
                pass
                
        return False
