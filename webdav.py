"""WebDAV sync layer for OCRMath.

Synchronizes a small JSON blob (API key + counters + prices) so the user
can share state across machines via their own WebDAV server (Nextcloud,
JianGuoYun, hacdias/webdav, etc.).

Envelope on the wire:
    {"version": 1, "synced_at": <epoch>, "data": {...}}

Conflict resolution (see merge()):
    counters: max(local, remote)              (offline accumulation safe)
    creds + prices: last-write-wins by synced_at timestamp
"""
from __future__ import annotations

import json
import sys
import threading
import time
from typing import Callable
from urllib.parse import urlsplit, urlunsplit

import requests
from requests.auth import HTTPBasicAuth
from PyQt6.QtCore import QThread, pyqtSignal

import config


# Process-wide lock so manual + auto sync don't race on PUT.
_SYNC_LOCK = threading.Lock()


def _build_url(base: str, remote_path: str) -> str:
    """Combine the server URL with the resource path safely."""
    base = (base or "").strip()
    if not base:
        raise ValueError("WebDAV URL is empty")
    if not base.startswith(("http://", "https://")):
        base = "https://" + base
    s = urlsplit(base)
    server = urlunsplit((s.scheme, s.netloc, "", "", ""))
    base_path = s.path.rstrip("/")
    rp = (remote_path or config.DEFAULT_WEBDAV_PATH).strip()
    if not rp.startswith("/"):
        rp = "/" + rp
    return server + base_path + rp


def _parent_path(full_url: str) -> str:
    s = urlsplit(full_url)
    parent = s.path.rsplit("/", 1)[0] or "/"
    if not parent.endswith("/"):
        parent += "/"
    return urlunsplit((s.scheme, s.netloc, parent, "", ""))


def ensure_collection(url: str, user: str, pw: str, remote_path: str,
                      timeout: float = 10) -> None:
    """Best-effort MKCOL on every ancestor of remote_path so deep paths like
    /backup/ocrmath/sync.json also work. Ignores 'already exists' replies."""
    full = _build_url(url, remote_path)
    s = urlsplit(full)
    server = urlunsplit((s.scheme, s.netloc, "", "", ""))

    # Build the list of ancestor collections to ensure, in order from
    # shallowest to deepest. Skip the file itself (last segment) and the
    # server root (which can't be MKCOL'd).
    segments = [seg for seg in s.path.split("/") if seg]
    if not segments:
        return
    ancestors = []
    acc = ""
    for seg in segments[:-1]:        # everything except the file
        acc += "/" + seg
        ancestors.append(server + acc + "/")

    for col_url in ancestors:
        try:
            r = requests.request(
                "MKCOL", col_url, auth=HTTPBasicAuth(user, pw),
                timeout=timeout)
            # 201 created, 405 method not allowed (already exists), 301 redirect.
            # 409 typically means an even deeper ancestor is missing — keep going.
            if r.status_code not in (201, 301, 405, 409):
                # Non-fatal: PUT will surface the real error if dir missing.
                pass
        except requests.RequestException:
            pass


def upload(url: str, user: str, pw: str, remote_path: str,
           payload: dict, timeout: float = 15) -> None:
    full = _build_url(url, remote_path)
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    r = requests.put(full, data=body,
                     auth=HTTPBasicAuth(user, pw),
                     headers={"Content-Type": "application/json"},
                     timeout=timeout)
    if r.status_code in (404, 409):
        # Parent collection might not exist yet — create then retry once.
        ensure_collection(url, user, pw, remote_path, timeout=timeout)
        r = requests.put(full, data=body,
                         auth=HTTPBasicAuth(user, pw),
                         headers={"Content-Type": "application/json"},
                         timeout=timeout)
    if r.status_code >= 400:
        raise RuntimeError(f"上传失败 HTTP {r.status_code}: {r.text[:200]}")


def download(url: str, user: str, pw: str, remote_path: str,
             timeout: float = 15) -> dict | None:
    """GET the sync envelope. Returns None if remote file (or its parent dir)
    is absent — Jianguoyun returns 409 'AncestorsNotFound' instead of 404."""
    full = _build_url(url, remote_path)
    r = requests.get(full, auth=HTTPBasicAuth(user, pw), timeout=timeout)
    if r.status_code == 404:
        return None
    if r.status_code == 409:
        # AncestorsNotFound on Jianguoyun, or generic conflict — treat as
        # "no remote yet" so the upload step can create the parent collection.
        return None
    if r.status_code >= 400:
        raise RuntimeError(f"下载失败 HTTP {r.status_code}: {r.text[:200]}")
    try:
        return json.loads(r.content.decode("utf-8"))
    except Exception as exc:
        raise RuntimeError(f"远端 JSON 解析失败: {exc}") from None


def test_connection(url: str, user: str, pw: str,
                    timeout: float = 10) -> tuple[bool, str]:
    """Quick PROPFIND on the server root. Returns (ok, message)."""
    if not url.strip():
        return False, "请填写 WebDAV URL"
    try:
        target = _build_url(url, "/")
    except Exception as exc:
        return False, f"URL 无效: {exc}"
    try:
        r = requests.request(
            "PROPFIND", target,
            auth=HTTPBasicAuth(user, pw),
            headers={"Depth": "0"},
            timeout=timeout)
    except requests.RequestException as exc:
        return False, f"连接失败: {exc}"
    if r.status_code in (200, 207):
        return True, "连接正常"
    if r.status_code == 401:
        return False, "认证失败 (HTTP 401)"
    if r.status_code == 404:
        return False, "路径不存在 (HTTP 404)"
    return False, f"HTTP {r.status_code}: {r.text[:120]}"


def merge(local_data: dict, local_ts: float,
          remote_data: dict | None, remote_ts: float) -> dict:
    """Combine local + remote payloads. See module docstring for rules."""
    if remote_data is None:
        return dict(local_data)
    out: dict = {}
    out["image_count"] = max(int(local_data.get("image_count", 0)),
                             int(remote_data.get("image_count", 0)))
    out["pdf_page_count"] = max(int(local_data.get("pdf_page_count", 0)),
                                int(remote_data.get("pdf_page_count", 0)))
    winner = remote_data if remote_ts > local_ts else local_data
    for k in ("app_id", "app_key", "image_price_usd", "pdf_price_usd"):
        if k in winner:
            out[k] = winner[k]
        elif k in local_data:
            out[k] = local_data[k]
    return out


def sync_once() -> float:
    """Download → merge → upload. Returns the new synced_at epoch.

    Raises RuntimeError if WebDAV is not configured or the network call fails.
    """
    wd = config.get_webdav()
    if not wd["url"] or not wd["user"]:
        raise RuntimeError("WebDAV 未配置")

    if not _SYNC_LOCK.acquire(blocking=False):
        raise RuntimeError("另一次同步正在进行")
    try:
        local_data = config.get_syncable_payload()
        local_ts = config.get_last_synced()

        remote_env = download(wd["url"], wd["user"], wd["password"], wd["path"])
        if remote_env is not None and isinstance(remote_env.get("data"), dict):
            merged = merge(local_data, local_ts,
                           remote_env["data"],
                           float(remote_env.get("synced_at", 0) or 0))
        else:
            merged = dict(local_data)

        now = time.time()
        config.apply_synced_payload(merged, now)
        upload(wd["url"], wd["user"], wd["password"], wd["path"],
               {"version": 1, "synced_at": now, "data": merged})
        return now
    finally:
        _SYNC_LOCK.release()


# ---- Qt worker -------------------------------------------------------------


class WebDavSyncWorker(QThread):
    finished_ok = pyqtSignal(float)   # synced_at epoch
    failed = pyqtSignal(str)

    def run(self) -> None:
        try:
            ts = sync_once()
        except Exception as exc:
            self.failed.emit(str(exc))
            return
        self.finished_ok.emit(ts)


def fire_and_forget(on_done: Callable[[float], None] | None = None,
                    on_fail: Callable[[str], None] | None = None
                    ) -> WebDavSyncWorker | None:
    """Best-effort background sync. Returns the worker (caller may keep ref)
    or None if WebDAV isn't configured."""
    wd = config.get_webdav()
    if not wd["url"] or not wd["user"]:
        return None
    w = WebDavSyncWorker()
    if on_done:
        w.finished_ok.connect(on_done)
    if on_fail:
        w.failed.connect(on_fail)
    else:
        w.failed.connect(lambda msg: sys.stderr.write(f"webdav sync failed: {msg}\n"))
    w.start()
    return w
