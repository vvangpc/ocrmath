"""Encrypted local storage for Mathpix API credentials + user preferences.

Uses Windows DPAPI (CryptProtectData) on Windows so the blob is bound to the
current user account. Falls back to plaintext JSON elsewhere — this app is
Windows-first, the fallback is just to keep dev tools usable on other OSes.

Stored fields:
    app_id, app_key (required), hotkey (optional),
    image_count, pdf_page_count, image_price_usd, pdf_price_usd, usd_cny_rate,
    webdav_url, webdav_user, webdav_password, webdav_path,
    webdav_sync_interval, cache_retention_days, usage_backfilled,
    settings_modified_at, last_synced_at
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from pathlib import Path
from typing import TypedDict

DEFAULT_HOTKEY = "ctrl+alt+m"
DEFAULT_IMAGE_PRICE = 0.002
DEFAULT_PDF_PRICE = 0.005
DEFAULT_USD_CNY_RATE = 7.0
DEFAULT_WEBDAV_PATH = "/ocrmath/sync.json"

# Guards read-modify-write cycles for counter bumps and sync writes.
_LOCK = threading.RLock()


class Settings(TypedDict, total=False):
    app_id: str
    app_key: str
    hotkey: str
    image_count: int
    pdf_page_count: int
    image_price_usd: float
    pdf_price_usd: float
    usd_cny_rate: float            # display conversion, USD -> CNY
    webdav_url: str
    webdav_user: str
    webdav_password: str
    webdav_path: str
    webdav_sync_interval: int      # minutes; 0 = no periodic timer
    cache_retention_days: int      # 0 = no auto-purge
    usage_backfilled: bool         # one-shot migration guard
    settings_modified_at: float    # last local edit of syncable settings
    last_synced_at: float


def _config_path() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", str(Path.home() / "AppData/Roaming")))
    else:
        base = Path.home() / ".config"
    return base / "ocrmath" / "config.dat"


CONFIG_PATH = _config_path()


# Cache of the decrypted blob, keyed by (st_mtime_ns, st_size) — load_all()
# is called several times per UI refresh and each call would otherwise
# re-read the file and round-trip DPAPI. A single tuple global keeps the
# (key, data) pair consistent for lock-free readers on other threads.
_BLOB_CACHE: tuple[tuple[int, int], bytes] | None = None


def _stat_key() -> tuple[int, int] | None:
    try:
        st = CONFIG_PATH.stat()
        return (st.st_mtime_ns, st.st_size)
    except OSError:
        return None


def _write_blob(payload: bytes) -> None:
    global _BLOB_CACHE
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    if sys.platform == "win32":
        import win32crypt
        blob = win32crypt.CryptProtectData(payload, "ocrmath", None, None, None, 0)
    else:
        blob = payload
    # Atomic replace so a crash mid-write can't corrupt the stored credentials.
    tmp = CONFIG_PATH.with_suffix(".tmp")
    tmp.write_bytes(blob)
    os.replace(tmp, CONFIG_PATH)
    key = _stat_key()
    _BLOB_CACHE = (key, payload) if key is not None else None


def _read_blob() -> bytes | None:
    global _BLOB_CACHE
    key = _stat_key()
    if key is None:
        return None
    cached = _BLOB_CACHE
    if cached is not None and cached[0] == key:
        return cached[1]
    raw = CONFIG_PATH.read_bytes()
    if sys.platform == "win32":
        import win32crypt
        try:
            _, plain = win32crypt.CryptUnprotectData(raw, None, None, None, 0)
        except Exception:
            # Undecryptable (different user account / machine). Preserve the
            # blob for diagnostics instead of letting the next save clobber it.
            try:
                os.replace(CONFIG_PATH, CONFIG_PATH.with_suffix(".corrupt"))
                sys.stderr.write(
                    f"config: cannot decrypt {CONFIG_PATH}, "
                    f"moved to {CONFIG_PATH.with_suffix('.corrupt')}\n")
            except Exception:
                pass
            return None
    else:
        plain = raw
    _BLOB_CACHE = (key, plain)
    return plain


_STR_KEYS = ("app_id", "app_key", "hotkey",
             "webdav_url", "webdav_user", "webdav_password", "webdav_path")
_INT_KEYS = ("image_count", "pdf_page_count",
             "webdav_sync_interval", "cache_retention_days")
_FLOAT_KEYS = ("image_price_usd", "pdf_price_usd", "usd_cny_rate",
               "settings_modified_at", "last_synced_at")
_BOOL_KEYS: tuple[str, ...] = ("usage_backfilled",)


# Parsed-settings cache keyed by the decrypted blob object (identity): while
# _BLOB_CACHE is valid, _read_blob returns the same bytes object, so `is`
# comparison is both cheap and race-free.
_SETTINGS_CACHE: tuple[bytes, Settings] | None = None


def load_all() -> Settings:
    """Return everything stored, or {} if no config / corrupt."""
    global _SETTINGS_CACHE
    blob = _read_blob()
    if blob is None:
        return {}
    cached = _SETTINGS_CACHE
    if cached is not None and cached[0] is blob:
        return dict(cached[1])  # shallow copy: callers mutate the result
    try:
        data = json.loads(blob.decode())
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    out: Settings = {}
    for k in _STR_KEYS:
        if k in data and isinstance(data[k], str):
            out[k] = data[k]  # type: ignore[literal-required]
    for k in _INT_KEYS:
        if k in data and isinstance(data[k], int) and not isinstance(data[k], bool):
            out[k] = data[k]  # type: ignore[literal-required]
    for k in _FLOAT_KEYS:
        if k in data and isinstance(data[k], (int, float)) and not isinstance(data[k], bool):
            out[k] = float(data[k])  # type: ignore[literal-required]
    for k in _BOOL_KEYS:
        if k in data and isinstance(data[k], bool):
            out[k] = data[k]  # type: ignore[literal-required]
    _SETTINGS_CACHE = (blob, dict(out))
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
    with _LOCK:
        cur = load_all()
        if cur.get("app_id") != app_id or cur.get("app_key") != app_key:
            cur["settings_modified_at"] = time.time()
        cur["app_id"] = app_id
        cur["app_key"] = app_key
        save_all(cur)


def get_hotkey() -> str:
    return load_all().get("hotkey", DEFAULT_HOTKEY) or DEFAULT_HOTKEY


def set_hotkey(hotkey: str) -> None:
    with _LOCK:
        cur = load_all()
        cur["hotkey"] = hotkey
        save_all(cur)


def clear() -> None:
    if CONFIG_PATH.exists():
        CONFIG_PATH.unlink()


# ---- prices ----------------------------------------------------------------

def get_image_price() -> float:
    return float(load_all().get("image_price_usd", DEFAULT_IMAGE_PRICE))


def get_pdf_price() -> float:
    return float(load_all().get("pdf_price_usd", DEFAULT_PDF_PRICE))


def get_usd_cny_rate() -> float:
    return float(load_all().get("usd_cny_rate", DEFAULT_USD_CNY_RATE)) \
        or DEFAULT_USD_CNY_RATE


# ---- counters --------------------------------------------------------------

def get_counters() -> tuple[int, int]:
    s = load_all()
    return int(s.get("image_count", 0) or 0), int(s.get("pdf_page_count", 0) or 0)


def bump_image_count(n: int = 1) -> None:
    with _LOCK:
        cur = load_all()
        cur["image_count"] = int(cur.get("image_count", 0) or 0) + int(n)
        save_all(cur)


def bump_pdf_pages(n: int) -> None:
    if n <= 0:
        return
    with _LOCK:
        cur = load_all()
        cur["pdf_page_count"] = int(cur.get("pdf_page_count", 0) or 0) + int(n)
        save_all(cur)


# ---- webdav ----------------------------------------------------------------

def get_webdav() -> dict:
    s = load_all()
    return {
        "url": s.get("webdav_url", "") or "",
        "user": s.get("webdav_user", "") or "",
        "password": s.get("webdav_password", "") or "",
        "path": s.get("webdav_path", "") or DEFAULT_WEBDAV_PATH,
        "interval": int(s.get("webdav_sync_interval", 0) or 0),
    }


def get_cache_retention() -> int:
    """Return the cache retention in days. 0 = disabled (no auto-purge)."""
    return int(load_all().get("cache_retention_days", 0) or 0)


def is_usage_backfilled() -> bool:
    return bool(load_all().get("usage_backfilled", False))


def mark_usage_backfilled() -> None:
    with _LOCK:
        cur = load_all()
        cur["usage_backfilled"] = True
        save_all(cur)


def get_last_synced() -> float:
    return float(load_all().get("last_synced_at", 0.0) or 0.0)


def get_modified_at() -> float:
    """Last local edit of syncable settings (creds / prices / rate).
    Old configs without the field fall back to last_synced_at so merge
    behaviour matches the previous release."""
    s = load_all()
    return float(s.get("settings_modified_at",
                       s.get("last_synced_at", 0.0)) or 0.0)


# ---- sync payload ----------------------------------------------------------

_SYNCABLE_KEYS = ("app_id", "app_key",
                  "image_count", "pdf_page_count",
                  "image_price_usd", "pdf_price_usd", "usd_cny_rate")


def get_syncable_payload() -> dict:
    """Fields that travel through WebDAV. Excludes hotkey + webdav creds."""
    s = load_all()
    out: dict = {}
    for k in _SYNCABLE_KEYS:
        if k in s:
            out[k] = s[k]
    out.setdefault("image_count", 0)
    out.setdefault("pdf_page_count", 0)
    out.setdefault("image_price_usd", DEFAULT_IMAGE_PRICE)
    out.setdefault("pdf_price_usd", DEFAULT_PDF_PRICE)
    out.setdefault("usd_cny_rate", DEFAULT_USD_CNY_RATE)
    return out


def apply_synced_payload(merged: dict, synced_at: float) -> None:
    """Persist a merged sync result and stamp last_synced_at."""
    with _LOCK:
        cur = load_all()
        for k in _SYNCABLE_KEYS:
            if k in merged:
                cur[k] = merged[k]  # type: ignore[literal-required]
        cur["last_synced_at"] = float(synced_at)
        save_all(cur)


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
