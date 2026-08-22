import sys
import re
import threading
import requests
from typing import Dict, Any, Optional, Callable

CURRENT_VERSION = "1.0.3"
GITHUB_REPO = "AxePH/AxeCast-Studio"  # Official repository identifier

def parse_version_tuple(v_str: str) -> tuple:
    """Extracts integer version tuple from string (e.g. 'v1.2.3' -> (1, 2, 3))."""
    if not v_str:
        return (0, 0, 0)
    clean = re.sub(r'^[^\d]*', '', str(v_str).strip())
    parts = []
    for part in re.split(r'[.\-_]', clean):
        digits = re.findall(r'\d+', part)
        if digits:
            parts.append(int(digits[0]))
        else:
            break
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])

def is_newer_version(latest_str: str, current_str: str = CURRENT_VERSION) -> bool:
    """Returns True if latest_str is strictly newer than current_str."""
    return parse_version_tuple(latest_str) > parse_version_tuple(current_str)

def get_platform_asset(assets: list) -> tuple:
    """Finds the most suitable release asset for the current operating system."""
    if not assets or not isinstance(assets, list):
        return None, None
        
    is_win = sys.platform.startswith("win")
    is_mac = sys.platform == "darwin"
    is_linux = sys.platform.startswith("linux")
    
    # Priority matching
    for asset in assets:
        name = asset.get("name", "").lower()
        url = asset.get("browser_download_url", "")
        if is_win and ("windows" in name or name.endswith(".zip") or name.endswith(".exe")):
            return asset.get("name"), url
        elif is_mac and ("macos" in name or "darwin" in name or "arm64" in name or name.endswith(".dmg") or (name.endswith(".tar.gz") and "mac" in name)):
            return asset.get("name"), url
        elif is_linux and ("linux" in name or (name.endswith(".tar.gz") and "linux" in name)):
            return asset.get("name"), url
            
    # Fallback to first asset if no exact OS match
    if assets:
        return assets[0].get("name"), assets[0].get("browser_download_url")
    return None, None

def check_for_updates(repo: str = GITHUB_REPO, current_version: str = CURRENT_VERSION) -> Dict[str, Any]:
    """Queries GitHub Releases API synchronously to check for newer versions."""
    api_url = f"https://api.github.com/repos/{repo}/releases/latest"
    headers = {
        "User-Agent": f"AxeCast-Studio/{current_version}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    try:
        resp = requests.get(api_url, headers=headers, timeout=5.0)
        if resp.status_code == 200:
            data = resp.json()
            tag_name = data.get("tag_name", "")
            release_name = data.get("name") or tag_name
            changelog = data.get("body", "No release notes provided.")
            html_url = data.get("html_url", f"https://github.com/{repo}/releases")
            assets = data.get("assets", [])
            
            asset_name, asset_url = get_platform_asset(assets)
            has_update = is_newer_version(tag_name, current_version)
            
            return {
                "success": True,
                "has_update": has_update,
                "current_version": current_version,
                "latest_version": tag_name.lstrip("v"),
                "tag_name": tag_name,
                "release_name": release_name,
                "changelog": changelog,
                "release_url": html_url,
                "os_asset_name": asset_name,
                "os_download_url": asset_url or html_url,
                "error": None
            }
        elif resp.status_code == 404:
            return {
                "success": True,
                "has_update": False,
                "current_version": current_version,
                "latest_version": current_version,
                "tag_name": f"v{current_version}",
                "release_name": "Latest Release",
                "changelog": "",
                "release_url": f"https://github.com/{repo}/releases",
                "os_asset_name": None,
                "os_download_url": f"https://github.com/{repo}/releases",
                "error": "No public releases found yet on GitHub."
            }
        else:
            return {
                "success": False,
                "has_update": False,
                "current_version": current_version,
                "error": f"GitHub API responded with HTTP {resp.status_code}"
            }
    except Exception as e:
        return {
            "success": False,
            "has_update": False,
            "current_version": current_version,
            "error": str(e)
        }

def check_for_updates_async(
    callback: Callable[[Dict[str, Any]], None],
    repo: str = GITHUB_REPO,
    current_version: str = CURRENT_VERSION
) -> threading.Thread:
    """Runs version check in a daemon background thread to keep UI ultra responsive."""
    def worker():
        res = check_for_updates(repo=repo, current_version=current_version)
        if callback:
            callback(res)
            
    th = threading.Thread(target=worker, daemon=True)
    th.start()
    return th
