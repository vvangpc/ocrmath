"""The only door between the web pages and Python.

Pages call `invoke(name, json_args)` over QWebChannel and receive
`{"ok": true, "result": ...}` or `{"ok": false, "error": ...}`. Only methods
listed in RPC_METHODS can be reached. Python talks back through `pushed`.
"""
from __future__ import annotations

import base64
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QObject, QUrl, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import QFileDialog

import config
import mathjax_view
import settings_service
import webdav
from llm_store import LlmStore
from result_format import history_copy_text
from ui_utils import UserError

RPC_METHODS = frozenset({
    "mathjax_url", "copy_text", "open_tool", "open_folder",
    "float_state", "float_format", "float_latex_style", "float_primary",
    "float_recapture", "float_toggle_provider", "float_source", "float_hide",
    "tool_state", "back_to_float",
    "pdf_state", "pdf_pick", "pdf_pick_dir", "pdf_inspect", "pdf_estimate",
    "pdf_set_provider", "pdf_start", "pdf_resume", "pdf_cancel",
    "history_list", "history_open", "history_copy", "history_delete", "history_clear",
    "usage_summary", "sync_now",
    "settings_get", "settings_save", "settings_test_webdav", "settings_sync",
    "settings_purge", "settings_clear_credentials",
})


def _period_start(period: str) -> float:
    now = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    if period == "today":
        return now.timestamp()
    if period == "month":
        return now.replace(day=1).timestamp()
    return 0.0


class Bridge(QObject):
    pushed = pyqtSignal(str)

    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.app = app
        self._llm_store: LlmStore | None = None
        self._sync_worker = None
        self._test_worker = None

    def push(self, name: str, data=None) -> None:
        self.pushed.emit(json.dumps({"name": name, "data": data}, ensure_ascii=False))

    @pyqtSlot(str, str, result=str)
    def invoke(self, name: str, args: str) -> str:
        try:
            if name not in RPC_METHODS:
                raise UserError(f"未知操作：{name}")
            result = getattr(self, name)(*json.loads(args or "[]"))
            return json.dumps({"ok": True, "result": result}, ensure_ascii=False)
        except UserError as exc:
            return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)
        except Exception as exc:
            sys.stderr.write(f"bridge {name} failed: {exc}\n")
            return json.dumps({"ok": False, "error": f"操作失败：{exc}"}, ensure_ascii=False)

    # ---- shared ------------------------------------------------------------

    def mathjax_url(self) -> str:
        ready = mathjax_view.ensure_available(
            on_ready=lambda _path: self.push("mathjax"),
            on_failed=lambda msg: sys.stderr.write(f"MathJax download failed: {msg}\n"))
        return QUrl.fromLocalFile(str(mathjax_view.mathjax_path())).toString() if ready else ""

    def copy_text(self, text: str) -> None:
        QGuiApplication.clipboard().setText(text)

    def open_tool(self, page: str) -> None:
        self.app._open_tool(page)

    def open_folder(self, path: str) -> None:
        if not Path(path).is_dir():
            raise UserError("输出目录不存在。")
        os.startfile(path)  # type: ignore[attr-defined]

    # ---- float window ------------------------------------------------------

    @property
    def _model(self):
        return self.app.result_win.model

    def float_state(self) -> dict:
        return self._model.snapshot()

    def float_format(self, key: str) -> None:
        self._model.select_format(key)
        self.app.result_win.refresh()

    def float_latex_style(self, index: int) -> None:
        self._model.set_latex_style(index)
        self.app.result_win.refresh()

    def float_primary(self) -> dict:
        action = self._model.primary_action()
        if action == "capture":
            self.app.on_snip()
        elif action == "retry":
            self.app._retry_last_image()
        elif action == "copy":
            self.copy_text(self._model.copy_text())
            self.app.result_win.hide_after_copy()
            return {"copied": True}
        return {"copied": False}

    def float_recapture(self) -> None:
        if not self._model.busy:
            self.app.on_snip()

    def float_toggle_provider(self) -> None:
        if self._model.busy:
            return
        next_provider = "mathpix" if config.get_provider() == "llm" else "llm"
        config.save_settings({"image_provider": next_provider})
        self.app.result_win.refresh()

    def float_source(self) -> str:
        png = self._model.source
        return "data:image/png;base64," + base64.b64encode(png).decode() if png else ""

    def float_hide(self) -> None:
        self.app.result_win.hide()

    # ---- tool window -------------------------------------------------------

    def tool_state(self) -> dict:
        return {"page": self.app.main_win.page}

    def back_to_float(self) -> None:
        self.app._show_main()

    # ---- pdf ---------------------------------------------------------------

    @property
    def _pdf(self):
        return self.app.main_win.pdf_service

    def pdf_state(self) -> dict:
        return self._pdf.state()

    def pdf_pick(self) -> dict | None:
        name, _ = QFileDialog.getOpenFileName(
            self.app.main_win, "选择 PDF 文件", "", "PDF Files (*.pdf);;All files (*)")
        return self._pdf.inspect(name) if name else None

    def pdf_pick_dir(self, current: str) -> str:
        return QFileDialog.getExistingDirectory(self.app.main_win, "选择输出目录", current)

    def pdf_inspect(self, path: str) -> dict:
        return self._pdf.inspect(path)

    def pdf_estimate(self, path: str, provider: str, page_ranges: str) -> str:
        return self._pdf.estimate(path, provider, page_ranges)

    def pdf_set_provider(self, provider: str) -> None:
        config.save_settings({"pdf_provider": "llm" if provider == "llm" else "mathpix"})

    def pdf_start(self, params: dict, confirmed: bool = False) -> dict:
        return self._pdf.start(params, confirmed)

    def pdf_resume(self, job_id: str) -> None:
        self._pdf.resume(job_id)

    def pdf_cancel(self) -> None:
        self._pdf.cancel()

    # ---- history -----------------------------------------------------------

    def history_list(self, query: str = "") -> dict:
        storage = self.app.storage
        rows = []
        for rec in storage.list_recent(query=query.strip(), limit=300):
            png = storage._png_path(rec.image_sha256)
            rows.append({
                "id": rec.id,
                "thumb": QUrl.fromLocalFile(str(png)).toString(),
                "text": rec.latex or rec.text or "(空)",
                "created_at": rec.created_at,
                "confidence": rec.confidence,
                "model": rec.result.get("model") if rec.result.get("_provider") == "llm" else None,
            })
        return {"rows": rows, "stats": storage.stats()}

    def _record(self, rec_id: int):
        rec = self.app.storage.get(rec_id)
        if rec is None:
            raise UserError("这条记录已不存在。")
        return rec

    def history_open(self, rec_id: int) -> None:
        self.app._on_history_open(self._record(rec_id))

    def history_copy(self, rec_id: int) -> None:
        rec = self._record(rec_id)
        text = history_copy_text(rec.latex, rec.text)
        if text:
            self.copy_text(text)

    def history_delete(self, rec_id: int) -> None:
        self.app.storage.delete(rec_id)

    def history_clear(self) -> None:
        self.app.storage.clear_all()

    # ---- usage -------------------------------------------------------------

    def _ledger(self) -> LlmStore:
        if self._llm_store is None:
            self._llm_store = LlmStore()
        return self._llm_store

    def usage_summary(self, period: str = "month") -> dict:
        since = _period_start(period)
        local = self.app.storage.usage_summary(since)
        models = self._ledger().summary(since)
        llm_cost = sum(m["cost_usd"] for m in models)
        images, pages = config.get_counters()
        image_price, pdf_price = config.get_image_price(), config.get_pdf_price()
        counter_state = config.load_all().get("counter_state") or {}
        return {
            "rate": config.get_usd_cny_rate(),
            "mathpix": local,
            "models": models,
            "llm_cost": llm_cost,
            "unpriced": sum(m["unpriced"] for m in models),
            "unknown": sum(m["unknown"] for m in models),
            "total": local["total_cost"] + llm_cost,
            "devices": {
                "images": images, "pages": pages,
                "cost": images * image_price + pages * pdf_price,
                "count": len(counter_state.get("devices") or {}),
            },
            "last_synced_at": config.get_last_synced(),
            "sync_needs_passphrase": self._needs_passphrase(),
            "sync_busy": self.app._sync_worker is not None,
        }

    @staticmethod
    def _needs_passphrase() -> bool:
        wd = config.get_webdav()
        return bool(wd["url"] and wd["user"] and not wd["passphrase"])

    def sync_now(self) -> None:
        self.app._sync_now_manual()

    # ---- settings ----------------------------------------------------------

    def settings_get(self) -> dict:
        return settings_service.load_form()

    def settings_save(self, form: dict) -> None:
        old, new = settings_service.save_form(form)
        self.app._on_settings_changed(old, new)

    def settings_test_webdav(self, form: dict) -> None:
        if self._test_worker is not None:
            return
        worker = webdav.ConnectionTestWorker(str(form.get("webdav_url", "")).strip(),
                                             str(form.get("webdav_user", "")).strip(),
                                             str(form.get("webdav_password", "")))
        worker.done.connect(lambda ok, msg: self.push("webdav", {"ok": ok, "message": msg}))
        worker.finished.connect(self._test_finished)
        self._test_worker = worker
        worker.start()

    def _test_finished(self) -> None:
        self._test_worker = None

    def settings_sync(self, form: dict, overwrite: bool = False) -> None:
        if self._sync_worker is not None:
            return
        worker = webdav.WebDavSyncWorker(wd=settings_service.webdav_from_form(form),
                                         overwrite=bool(overwrite))
        worker.finished_ok.connect(self._form_sync_ok)
        worker.failed.connect(self._form_sync_failed)
        worker.finished.connect(self._form_sync_finished)
        self._sync_worker = worker
        worker.start()

    def _form_sync_ok(self, ts: float) -> None:
        self.push("webdav", {"ok": True, "synced_at": ts, "merged": True,
                             "message": "同步完成 " + time.strftime("%H:%M", time.localtime(ts))})
        self.app.main_win.refresh_stats()

    def _form_sync_failed(self, message: str) -> None:
        self.push("webdav", {"ok": False, "message": f"同步失败：{message}",
                             "undecryptable": message == str(webdav.SyncPassphraseError())})

    def _form_sync_finished(self) -> None:
        self._sync_worker = None

    def settings_purge(self, days: int) -> int:
        if int(days) <= 0:
            raise UserError("请先填入大于 0 的保留天数。")
        return self.app._purge_now(int(days))

    def settings_clear_credentials(self) -> None:
        config.save_settings({}, drop=("app_id", "app_key", "llm_api_key"))
