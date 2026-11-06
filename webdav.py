"""WebDAV sync layer for OCRMath.

Synchronizes a small JSON blob (API keys + counters + prices) so the user
can share state across machines via their own WebDAV server (Nextcloud,
JianGuoYun, hacdias/webdav, etc.). The blob is encrypted here before upload
and decrypted here after download; see sync_crypto.py.

Conflict resolution (see merge()):
    counters: shared legacy baseline + per-device grow-only components
    creds + LLM settings + prices + rate: last-write-wins by
    settings_modified_at (when the user last edited them), carried inside the
    data; files written by older versions lack it and fall back to their
    envelope's synced_at

Older versions wrote plaintext files (sync.v2.json and the configured path).
Every sync merges any it finds and deletes them once the encrypted copy is up.
"""
from __future__ import annotations

import json
import threading
import time
from typing import Callable
from urllib.parse import urlsplit, urlunsplit

import requests
from requests.auth import HTTPBasicAuth
from PyQt6.QtCore import Qt, QThread, pyqtSignal

import config
import counters
import sync_crypto
from sync_crypto import SyncPassphraseError


# Process-wide lock so manual + auto sync don't race on PUT.
_SYNC_LOCK = threading.Lock()


class SyncConflict(RuntimeError):
    """The remote resource changed after we read it."""


def _v2_path(path: str) -> str:
    path = path or config.DEFAULT_WEBDAV_PATH
    return path[:-5] + ".v2.json" if path.endswith(".json") else path + ".v2.json"


def _v3_path(path: str) -> str:
    path = path or config.DEFAULT_WEBDAV_PATH
    return path[:-5] + ".v3.json" if path.endswith(".json") else path + ".v3.json"


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
           payload: dict, timeout: float = 15, *, etag: str | None = None) -> None:
    full = _build_url(url, remote_path)
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    headers.update({"If-Match": etag} if etag else {"If-None-Match": "*"})
    r = requests.put(full, data=body,
                     auth=HTTPBasicAuth(user, pw),
                     headers=headers,
                     timeout=timeout)
    if r.status_code in (404, 409):
        # Parent collection might not exist yet — create then retry once.
        ensure_collection(url, user, pw, remote_path, timeout=timeout)
        r = requests.put(full, data=body,
                         auth=HTTPBasicAuth(user, pw),
                         headers=headers,
                         timeout=timeout)
    if r.status_code == 412:
        raise SyncConflict("远端数据已更新，正在重新合并")
    if not 200 <= r.status_code < 300:
        raise RuntimeError(f"上传失败 HTTP {r.status_code}: {r.text[:200]}")


def download(url: str, user: str, pw: str, remote_path: str,
             timeout: float = 15, *, with_etag: bool = False):
    """GET the sync envelope. Returns None if remote file (or its parent dir)
    is absent — Jianguoyun returns 409 'AncestorsNotFound' instead of 404."""
    full = _build_url(url, remote_path)
    r = requests.get(full, auth=HTTPBasicAuth(user, pw), timeout=timeout)
    if r.status_code == 404:
        return (None, None) if with_etag else None
    if r.status_code == 409:
        # AncestorsNotFound on Jianguoyun, or generic conflict — treat as
        # "no remote yet" so the upload step can create the parent collection.
        return (None, None) if with_etag else None
    if r.status_code >= 400:
        raise RuntimeError(f"下载失败 HTTP {r.status_code}: {r.text[:200]}")
    try:
        value = json.loads(r.content.decode("utf-8"))
        if not isinstance(value, dict) or not (
                isinstance(value.get("data"), dict) or isinstance(value.get("ciphertext"), str)):
            raise ValueError("同步文件结构无效")
    except Exception as exc:
        raise RuntimeError(f"远端 JSON 解析失败: {exc}") from None
    etag = r.headers.get("ETag")
    if with_etag and (not etag or etag.startswith("W/")):
        raise RuntimeError("WebDAV 未提供强 ETag，无法安全合并多机写入；请启用服务器 ETag 支持")
    return (value, etag) if with_etag else value


def delete(url: str, user: str, pw: str, remote_path: str,
           timeout: float = 15) -> bool:
    """Remove a remote file. True if it is gone afterwards."""
    try:
        r = requests.delete(_build_url(url, remote_path),
                            auth=HTTPBasicAuth(user, pw), timeout=timeout)
    except requests.RequestException:
        return False
    return 200 <= r.status_code < 300 or r.status_code == 404


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
    out = counters.merge(local_data, remote_data)
    remote_wins = remote_ts > local_ts
    winner = remote_data if remote_wins else local_data
    other = local_data if remote_wins else remote_data
    for k in config.LWW_KEYS:
        if k in winner:
            out[k] = winner[k]
        elif k in other:
            out[k] = other[k]
    out["settings_modified_at"] = remote_ts if remote_wins else local_ts
    return out


def _plaintext_files(wd: dict) -> list[tuple[str, dict, float]]:
    """Files left by older versions, as (path, data, edit time)."""
    found = []
    for path in (_v2_path(wd["path"]), wd["path"] or config.DEFAULT_WEBDAV_PATH):
        env = download(wd["url"], wd["user"], wd["password"], path)
        if env is None or not isinstance(env.get("data"), dict):
            continue
        data = env["data"]
        if env.get("version") == 2 and "counter_state" not in data:
            raise RuntimeError("旧版同步文件缺少设备计数，未覆盖远端文件")
        found.append((path, data,
                      float(data.get("settings_modified_at", env.get("synced_at", 0)) or 0)))
    return found


def sync_once(wd: dict | None = None, *, overwrite: bool = False) -> float:
    """Download → decrypt → merge → encrypt → upload. Returns the new
    synced_at epoch.

    `wd` overrides the stored WebDAV settings (used by the settings page
    so "sync now" works on unsaved form values without persisting them).
    `overwrite` replaces a remote file that can't be decrypted, for a forgotten
    passphrase; other devices merge their data back once they use the new one.
    Raises RuntimeError if WebDAV is not configured or the network call fails,
    and SyncPassphraseError if the remote file can't be decrypted.
    """
    wd = wd or config.get_webdav()
    if not wd["url"] or not wd["user"]:
        raise RuntimeError("WebDAV 未配置")
    passphrase = wd.get("passphrase") or ""
    if not passphrase:
        raise RuntimeError("请先在设置中填写同步口令")

    if not _SYNC_LOCK.acquire(blocking=False):
        raise RuntimeError("另一次同步正在进行")
    try:
        path = _v3_path(wd["path"])
        for attempt in range(4):
            local_data = config.get_syncable_payload()
            local_ts = float(local_data["settings_modified_at"])
            remote_env, etag = download(
                wd["url"], wd["user"], wd["password"], path, with_etag=True)
            if remote_env is not None and remote_env.get("version") != sync_crypto.VERSION:
                raise RuntimeError("不支持的同步协议版本，未覆盖远端文件")
            merged = dict(local_data)
            merged_ts = local_ts
            if remote_env is not None and not overwrite:
                remote_data = sync_crypto.decrypt(remote_env, passphrase)
                merged = merge(merged, merged_ts, remote_data,
                               float(remote_data.get("settings_modified_at", 0) or 0))
                merged_ts = float(merged["settings_modified_at"])
            old_files = _plaintext_files(wd)
            for _old_path, old_data, old_ts in old_files:
                merged = merge(merged, merged_ts, old_data, old_ts)
                merged_ts = float(merged["settings_modified_at"])
            now = time.time()
            try:
                upload(wd["url"], wd["user"], wd["password"], path,
                       sync_crypto.encrypt(merged, passphrase), etag=etag)
            except SyncConflict:
                continue
            config.apply_synced_payload(merged, now, base_modified_at=local_ts)
            # Only now is everything in the old files safely in the new one.
            left = [p for p, _d, _t in old_files
                    if not delete(wd["url"], wd["user"], wd["password"], p)]
            config.update_ui_state(remote_plaintext_left=left)
            return now
        raise RuntimeError("远端连续发生写入冲突，请稍后重试同步")
    finally:
        _SYNC_LOCK.release()


# ---- Qt worker -------------------------------------------------------------


# Keeps running workers alive even if their owner (e.g. a closed settings
# dialog) drops the last reference — a QThread garbage-collected while its
# thread is still running aborts the whole app.
_ACTIVE_WORKERS: set[QThread] = set()


def _keep_alive(worker: QThread) -> None:
    _ACTIVE_WORKERS.add(worker)
    # Queued so the discard (possibly the last reference) runs on the
    # main thread after the worker thread has fully wound down.
    worker.finished.connect(lambda: _ACTIVE_WORKERS.discard(worker),
                            Qt.ConnectionType.QueuedConnection)


def any_running() -> bool:
    return any(w.isRunning() for w in list(_ACTIVE_WORKERS))


class ConnectionTestWorker(QThread):
    """Runs test_connection() off the UI thread (it can block for 10s+)."""
    done = pyqtSignal(bool, str)      # ok, message

    def __init__(self, url: str, user: str, pw: str, parent=None):
        super().__init__(parent)
        self._args = (url, user, pw)
        _keep_alive(self)

    def run(self) -> None:
        try:
            ok, msg = test_connection(*self._args)
        except Exception as exc:
            ok, msg = False, str(exc)
        self.done.emit(ok, msg)


class WebDavSyncWorker(QThread):
    finished_ok = pyqtSignal(float)   # synced_at epoch
    failed = pyqtSignal(str)

    def __init__(self, wd: dict | None = None, parent=None, *, overwrite: bool = False):
        super().__init__(parent)
        self._wd = wd
        self._overwrite = overwrite
        _keep_alive(self)

    def run(self) -> None:
        try:
            ts = sync_once(self._wd, overwrite=self._overwrite)
        except Exception as exc:
            self.failed.emit(str(exc))
            return
        self.finished_ok.emit(ts)


def start_worker(on_ok: Callable[[float], None] | None = None,
                 on_fail: Callable[[str], None] | None = None,
                 on_finished: Callable[[], None] | None = None,
                 wd: dict | None = None) -> WebDavSyncWorker:
    """Create, wire and start a sync worker. Caller may keep the return
    value as a reentrancy guard; _ACTIVE_WORKERS keeps it alive regardless."""
    w = WebDavSyncWorker(wd=wd)
    if on_ok:
        w.finished_ok.connect(on_ok)
    if on_fail:
        w.failed.connect(on_fail)
    if on_finished:
        w.finished.connect(on_finished)
    w.start()
    return w
