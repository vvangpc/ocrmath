"""Encrypted local storage for Mathpix API credentials + user preferences.

Uses Windows DPAPI (CryptProtectData) on Windows so the blob is bound to the
current user account. Falls back to plaintext JSON elsewhere — this app is
Windows-first, the fallback is just to keep dev tools usable on other OSes.

Stored fields:
    app_id, app_key (required), hotkey (optional, default 'ctrl+alt+m')
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import TypedDict

DEFAULT_HOTKEY = "ctrl+alt+m"


class Settings(TypedDict, total=False):
    app_id: str
    app_key: str
    hotkey: str


def _config_path() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", str(Path.home() / "AppData/Roaming")))
    else:
        base = Path.home() / ".config"
    return base / "ocrmath" / "config.dat"


CONFIG_PATH = _config_path()


def _write_blob(payload: bytes) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    if sys.platform == "win32":
        import win32crypt
        blob = win32crypt.CryptProtectData(payload, "ocrmath", None, None, None, 0)
        CONFIG_PATH.write_bytes(blob)
    else:
        CONFIG_PATH.write_bytes(payload)


def _read_blob() -> bytes | None:
    if not CONFIG_PATH.exists():
        return None
    raw = CONFIG_PATH.read_bytes()
    if sys.platform == "win32":
        import win32crypt
        try:
            _, plain = win32crypt.CryptUnprotectData(raw, None, None, None, 0)
            return plain
        except Exception:
            return None
    return raw


def load_all() -> Settings:
    """Return everything stored, or {} if no config / corrupt."""
    blob = _read_blob()
    if blob is None:
        return {}
    try:
        data = json.loads(blob.decode())
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    out: Settings = {}
    for k in ("app_id", "app_key", "hotkey"):
        if k in data and isinstance(data[k], str):
            out[k] = data[k]  # type: ignore[literal-required]
    return out


def save_all(settings: Settings) -> None:
    payload = json.dumps(dict(settings)).encode()
    _write_blob(payload)


def load() -> dict | None:
    """Backward-compat: return creds dict {app_id, app_key} or None."""
    s = load_all()
    if "app_id" in s and "app_key" in s:
        return {"app_id": s["app_id"], "app_key": s["app_key"]}
    return None


def save(app_id: str, app_key: str) -> None:
    """Backward-compat: preserves any existing hotkey."""
    cur = load_all()
    cur["app_id"] = app_id
    cur["app_key"] = app_key
    save_all(cur)


def get_hotkey() -> str:
    return load_all().get("hotkey", DEFAULT_HOTKEY) or DEFAULT_HOTKEY


def set_hotkey(hotkey: str) -> None:
    cur = load_all()
    cur["hotkey"] = hotkey
    save_all(cur)


def clear() -> None:
    if CONFIG_PATH.exists():
        CONFIG_PATH.unlink()


# ---- hotkey format conversion ---------------------------------------------

def qt_to_keyboard(seq: str) -> str:
    """Convert Qt QKeySequence text ('Ctrl+Alt+M') to keyboard lib format
    ('ctrl+alt+m'). Returns '' if seq is empty/invalid."""
    if not seq:
        return ""
    parts = [p.strip() for p in seq.split("+") if p.strip()]
    if not parts:
        return ""
    mapping = {
        "ctrl": "ctrl", "control": "ctrl",
        "shift": "shift",
        "alt": "alt",
        "meta": "windows", "win": "windows", "windows": "windows",
    }
    out = []
    for p in parts:
        low = p.lower()
        out.append(mapping.get(low, low))
    return "+".join(out)


def keyboard_to_qt(seq: str) -> str:
    """Convert keyboard lib format ('ctrl+alt+m') to Qt display format
    ('Ctrl+Alt+M')."""
    if not seq:
        return ""
    parts = [p.strip().lower() for p in seq.split("+") if p.strip()]
    pretty = {"ctrl": "Ctrl", "shift": "Shift", "alt": "Alt", "windows": "Meta"}
    return "+".join(pretty.get(p, p.upper() if len(p) == 1 else p.capitalize())
                    for p in parts)


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("cmd", choices=["save", "load", "clear", "path", "hotkey"])
    p.add_argument("--app-id")
    p.add_argument("--app-key")
    p.add_argument("--set")
    args = p.parse_args()
    if args.cmd == "save":
        if not (args.app_id and args.app_key):
            raise SystemExit("save needs --app-id and --app-key")
        save(args.app_id, args.app_key)
        print(f"saved to {CONFIG_PATH}")
    elif args.cmd == "load":
        print(load_all() or "(empty)")
    elif args.cmd == "clear":
        clear()
        print("cleared")
    elif args.cmd == "path":
        print(CONFIG_PATH)
    elif args.cmd == "hotkey":
        if args.set:
            set_hotkey(args.set)
            print(f"hotkey = {args.set}")
        else:
            print(get_hotkey())
