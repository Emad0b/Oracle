from __future__ import annotations

import os
import subprocess
import webbrowser
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus


ALLOWED_APPS = {
    "notepad": "notepad.exe",
    "calculator": "calc.exe",
    "explorer": "explorer.exe",
    "cmd": "cmd.exe",
    "powershell": "powershell.exe",
    "chrome": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    "edge": r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    "spotify": os.path.expandvars(r"%APPDATA%\Spotify\Spotify.exe"),
}


def open_url(url: str) -> dict[str, Any]:
    cleaned = url.strip()
    if not cleaned.startswith(("http://", "https://")):
        cleaned = f"https://{cleaned}"
    webbrowser.open(cleaned)
    return {"status": "opened", "url": cleaned}


def open_app(app_name: str) -> dict[str, Any]:
    key = app_name.strip().lower()
    target = ALLOWED_APPS.get(key)
    if not target:
        return {
            "error": f"Unknown app '{app_name}'. Allowed: {', '.join(sorted(ALLOWED_APPS))}."
        }

    path = Path(target)
    if path.suffix.lower() == ".exe" and not path.exists() and key not in {"notepad", "calculator", "explorer", "cmd", "powershell"}:
        return {"error": f"App path not found on this PC: {target}"}

    try:
        if key in {"notepad", "calculator", "explorer", "cmd", "powershell"}:
            subprocess.Popen([target], shell=False)
        else:
            subprocess.Popen([str(path)], shell=False)
    except OSError as exc:
        return {"error": f"Could not open {app_name}: {exc}"}

    return {"status": "opened", "app": key, "path": target}


def web_search(query: str) -> dict[str, Any]:
    url = f"https://www.google.com/search?q={quote_plus(query)}"
    webbrowser.open(url)
    return {"status": "opened_search", "query": query, "url": url}
