import os
import subprocess
from pathlib import Path
from .system_detector import SystemDetector

class DeviceFileManager:
    """Android filesystem engine with smart symlink redirection, Copy/Cut/Paste, Auto-increment (+1), Rename, Delete."""
    
    def __init__(self, system_detector: SystemDetector = None):
        self.sys = system_detector or SystemDetector()
        self.adb = self.sys.get_adb_path()
        self.cache = {}

    def normalize_path(self, path: str) -> str:
        path = path.replace("\\", "/").strip()
        if not path.startswith("/"):
            path = "/" + path
            
        while "//" in path:
            path = path.replace("//", "/")
            
        if path in ("/storage/emulated", "/storage/emulated/emulated", "/storage/self", "/storage/self/primary"):
            return "/sdcard"
            
        return path

    def list_directory(self, serial: str, remote_path: str = "/sdcard", use_cache: bool = True) -> tuple[bool, list, str]:
        remote_path = self.normalize_path(remote_path)
        search_path = remote_path.rstrip("/") + "/"
        if search_path == "//":
            search_path = "/"
            
        cache_key = (serial, remote_path)
        if use_cache and cache_key in self.cache:
            return True, self.cache[cache_key], ""
            
        cmd1 = f"ls -la '{search_path}' 2>/dev/null"
        cmd2 = f"toybox ls -la '{search_path}' 2>/dev/null"
        cmd3 = f"su 0 ls -la '{search_path}' 2>/dev/null"
        cmd4 = f"find '{search_path}' -maxdepth 1 2>/dev/null"
        shell_cmd = f"{cmd1} || {cmd2} || {cmd3} || {cmd4}"
        
        code, out, err = self.sys.run_command_hidden(
            [self.adb, "-s", serial, "shell", shell_cmd],
            timeout=8
        )
        
        lines = [line.strip() for line in out.splitlines() if line.strip()]
        
        if not lines and code != 0:
            return False, [], "Permission Denied: This system folder is restricted by Android OS"
            
        items = []
        for line in lines:
            if line.startswith("total ") or not line:
                continue
                
            parts = line.split()
            if len(parts) >= 8 and (parts[0].startswith("-") or parts[0].startswith("d") or parts[0].startswith("l") or parts[0].startswith("c") or parts[0].startswith("b") or parts[0].startswith("?")):
                perms = parts[0]
                is_dir = perms.startswith("d") or "d" in perms[:4]
                is_link = perms.startswith("l")
                
                try:
                    size_bytes = int(parts[4])
                except ValueError:
                    try:
                        size_bytes = int(parts[3])
                    except ValueError:
                        size_bytes = 0
                        
                date_str = f"{parts[5]} {parts[6]}"
                if "?" in date_str:
                    date_str = "--"
                    
                name = " ".join(parts[7:])
                link_target = ""
                if " -> " in name:
                    link_parts = name.split(" -> ")
                    name = link_parts[0]
                    link_target = link_parts[1]
            else:
                name = os.path.basename(line)
                is_dir = not "." in name
                is_link = False
                perms = "drwxr-xr-x" if is_dir else "-rw-r--r--"
                size_bytes = 0
                date_str = "--"
                link_target = ""
                
            if name in (".", "..") or not name:
                continue
                
            name = "".join(c for c in name if c.isprintable() or ord(c) > 127).strip()
            if not name:
                continue
                
            if is_link and (name in ("sdcard", "primary", "self", "0") or "storage" in link_target or "data" in link_target):
                is_dir = True
                
            base_dir = remote_path.rstrip("/")
            if not base_dir:
                base_dir = ""
            full_item_path = f"{base_dir}/{name}"
            
            if is_dir:
                size_formatted = "--"
            elif size_bytes < 1024:
                size_formatted = f"{size_bytes} B"
            elif size_bytes < 1024 * 1024:
                size_formatted = f"{size_bytes / 1024:.1f} KB"
            elif size_bytes < 1024 * 1024 * 1024:
                size_formatted = f"{size_bytes / (1024 * 1024):.1f} MB"
            else:
                size_formatted = f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"
                
            ext = os.path.splitext(name)[1].lower()
            if is_dir:
                icon = "📁"
            elif ext in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"):
                icon = "🖼️"
            elif ext in (".mp4", ".mkv", ".avi", ".mov", ".webm", ".3gp"):
                icon = "🎬"
            elif ext in (".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"):
                icon = "🎵"
            elif ext in (".apk", ".apks", ".xapk"):
                icon = "📦"
            elif ext in (".pdf", ".doc", ".docx", ".txt", ".json", ".xml", ".log"):
                icon = "📄"
            elif ext in (".zip", ".rar", ".7z", ".tar", ".gz"):
                icon = "🗜️"
            else:
                icon = "📃"
                
            items.append({
                "name": name,
                "path": full_item_path,
                "is_dir": is_dir,
                "is_link": is_link,
                "perms": perms,
                "size_bytes": size_bytes,
                "size_formatted": size_formatted,
                "date": date_str,
                "icon": icon
            })
            
        items.sort(key=lambda x: (not x["is_dir"], x["name"].lower()))
        self.cache[cache_key] = items
        return True, items, ""

    def clear_cache(self, serial: str = None):
        if serial:
            keys = [k for k in self.cache if k[0] == serial]
            for k in keys:
                del self.cache[k]
        else:
            self.cache.clear()

    def get_existing_names(self, serial: str, remote_dir: str) -> set:
        remote_dir = self.normalize_path(remote_dir)
        ok, items, _ = self.list_directory(serial, remote_dir, use_cache=False)
        if ok:
            return {it["name"] for it in items}
        return set()

    def generate_unique_name(self, existing_names: set, original_name: str, is_dir: bool = False) -> str:
        if original_name not in existing_names:
            return original_name
            
        if is_dir:
            name_base = original_name
            ext = ""
        else:
            name_base, ext = os.path.splitext(original_name)
            
        counter = 1
        while True:
            candidate = f"{name_base} ({counter}){ext}"
            if candidate not in existing_names:
                return candidate
            counter += 1

    def copy_item(self, serial: str, src_path: str, dst_dir: str, is_dir: bool = False) -> tuple[bool, str]:
        self.clear_cache(serial)
        src_path = self.normalize_path(src_path)
        dst_dir = self.normalize_path(dst_dir)
        
        src_name = os.path.basename(src_path)
        existing = self.get_existing_names(serial, dst_dir)
        new_name = self.generate_unique_name(existing, src_name, is_dir=is_dir)
        dst_path = f"{dst_dir.rstrip('/')}/{new_name}"
        
        shell_cmd = f"cp -r '{src_path}' '{dst_path}' 2>/dev/null || cat '{src_path}' > '{dst_path}' 2>/dev/null"
        code, out, err = self.sys.run_command_hidden(
            [self.adb, "-s", serial, "shell", shell_cmd],
            timeout=60
        )
        if code == 0:
            return True, f"Copied to {new_name}"
        return False, err.strip() or out.strip() or "Copy failed"

    def move_item(self, serial: str, src_path: str, dst_dir: str, is_dir: bool = False) -> tuple[bool, str]:
        self.clear_cache(serial)
        src_path = self.normalize_path(src_path)
        dst_dir = self.normalize_path(dst_dir)
        
        src_name = os.path.basename(src_path)
        existing = self.get_existing_names(serial, dst_dir)
        
        # If moving to the same parent directory with the same name, nothing to do
        if os.path.dirname(src_path).rstrip("/") == dst_dir.rstrip("/"):
            return True, "Item already at destination"
            
        new_name = self.generate_unique_name(existing, src_name, is_dir=is_dir)
        dst_path = f"{dst_dir.rstrip('/')}/{new_name}"
        
        shell_cmd = f"mv '{src_path}' '{dst_path}'"
        code, out, err = self.sys.run_command_hidden(
            [self.adb, "-s", serial, "shell", shell_cmd],
            timeout=30
        )
        if code == 0:
            return True, f"Moved to {new_name}"
        return False, err.strip() or out.strip() or "Move failed"

    def rename_item(self, serial: str, old_path: str, new_name: str) -> tuple[bool, str]:
        self.clear_cache(serial)
        old_path = self.normalize_path(old_path)
        parent_dir = os.path.dirname(old_path).rstrip("/") or "/"
        new_path = f"{parent_dir.rstrip('/')}/{new_name.strip()}"
        
        shell_cmd = f"mv '{old_path}' '{new_path}'"
        code, out, err = self.sys.run_command_hidden(
            [self.adb, "-s", serial, "shell", shell_cmd],
            timeout=15
        )
        if code == 0:
            return True, f"Renamed to {new_name}"
        return False, err.strip() or out.strip() or "Rename failed"

    def upload_file(self, serial: str, local_path: str, remote_dir: str) -> tuple[bool, str]:
        if not os.path.exists(local_path):
            return False, "Local file does not exist"
            
        self.clear_cache(serial)
        target_dir = self.normalize_path(remote_dir)
        code, out, err = self.sys.run_command_hidden(
            [self.adb, "-s", serial, "push", local_path, target_dir],
            timeout=180
        )
        if code == 0:
            return True, f"Uploaded {os.path.basename(local_path)} successfully"
        return False, err.strip() or out.strip()

    def download_file(self, serial: str, remote_path: str, local_dir: str) -> tuple[bool, str]:
        Path(local_dir).mkdir(parents=True, exist_ok=True)
        target_path = self.normalize_path(remote_path)
        code, out, err = self.sys.run_command_hidden(
            [self.adb, "-s", serial, "pull", target_path, local_dir],
            timeout=180
        )
        if code == 0:
            filename = os.path.basename(remote_path)
            return True, f"Downloaded {filename} to {local_dir}"
        return False, err.strip() or out.strip()

    def create_folder(self, serial: str, remote_path: str) -> tuple[bool, str]:
        self.clear_cache(serial)
        target_path = self.normalize_path(remote_path)
        code, out, err = self.sys.run_command_hidden(
            [self.adb, "-s", serial, "shell", f"mkdir -p '{target_path}'"],
            timeout=10
        )
        if code == 0:
            return True, "Folder created successfully"
        return False, err.strip() or out.strip()

    def delete_item(self, serial: str, remote_path: str) -> tuple[bool, str]:
        self.clear_cache(serial)
        target_path = self.normalize_path(remote_path)
        code, out, err = self.sys.run_command_hidden(
            [self.adb, "-s", serial, "shell", f"rm -rf '{target_path}'"],
            timeout=15
        )
        if code == 0:
            return True, "Item deleted successfully"
        return False, err.strip() or out.strip()
