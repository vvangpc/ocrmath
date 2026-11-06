"""PDF conversion workflow behind the web UI: one worker, persistent jobs."""
from __future__ import annotations

import os
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Callable

from PyQt6.QtCore import QObject, pyqtSignal

import config
from llm_client import validate_endpoint
from llm_pdf import LlmPdfWorker, selected_pages
from pdf_client import PdfOptions, PdfWorker
from pdf_jobs import PdfJobStore
from ui_utils import UserError, format_cost

# Asking before this many pages guards against an expensive slip.
CONFIRM_PAGES = 100
MATHPIX_FORMATS = ("mmd", "md", "docx", "tex.zip", "html", "pdf")
# Statuses a worker writes while running. Seen on a job with no live worker,
# they mean the app was closed mid-run.
_ACTIVE_STATUSES = ("待提交", "待处理", "上传中", "处理中", "逐页识别中", "下载中")


def count_pdf_pages(path: Path) -> int | None:
    """Return page count, or None if the file is unreadable."""
    try:
        from pypdf import PdfReader
        return len(PdfReader(str(path)).pages)
    except Exception:
        return None


class PdfService(QObject):
    changed = pyqtSignal()            # jobs or live progress changed
    activity_finished = pyqtSignal()  # a worker has fully wound down

    def __init__(self, get_creds: Callable[[], dict | None],
                 on_pages_processed: Callable[[int, str | None], None] | None = None,
                 parent=None, *, job_store: PdfJobStore | None = None):
        super().__init__(parent)
        self._get_creds = get_creds
        self._on_pages_processed = on_pages_processed
        self.jobs = job_store or PdfJobStore()
        self._worker: PdfWorker | LlmPdfWorker | None = None
        self._billing_page_count: int | None = None
        self._inspected: tuple[str, int | None] | None = None
        self._percent = 0
        self._status = ""
        self._log: list[str] = []

    def is_busy(self) -> bool:
        return self._worker is not None and self._worker.isRunning()

    # ---- preparing a job ---------------------------------------------------

    def inspect(self, path: str) -> dict:
        p = Path(path)
        if p.suffix.lower() != ".pdf" or not p.is_file():
            raise UserError("请选择 PDF 文件。")
        pages = count_pdf_pages(p)
        self._inspected = (str(p), pages)
        memory = config.get_ui_state()
        out_dir = memory.get("pdf_out_dir")
        if not (isinstance(out_dir, str) and Path(out_dir).is_dir()):
            out_dir = str(p.parent)
        formats = memory.get("pdf_formats")
        if isinstance(formats, list):
            formats = [f for f in formats if f in MATHPIX_FORMATS]
        else:
            formats = None
        rm_spaces = memory.get("pdf_rm_spaces")
        return {"path": str(p), "name": p.name, "pages": pages, "out_dir": out_dir,
                "formats": formats, "rm_spaces": rm_spaces if isinstance(rm_spaces, bool) else None}

    def _page_count(self, path: Path) -> int | None:
        if self._inspected is None or self._inspected[0] != str(path):
            self._inspected = (str(path), count_pdf_pages(path))
        return self._inspected[1]

    def _pages(self, path: Path, page_ranges: str | None) -> int | None:
        """Pages this job would process; None if the document can't be read."""
        total = self._page_count(path)
        if total is None:
            return None
        try:
            return len(selected_pages(page_ranges, total))
        except ValueError as exc:
            raise UserError(str(exc)) from None

    def estimate(self, path: str, provider: str, page_ranges: str = "") -> str:
        pages = self._pages(Path(path), page_ranges.strip() or None)
        if provider == "llm":
            count = f"{pages} 页" if pages else "所选页面"
            return f"逐页识别 {count}，输出 Markdown，按实际 Token 计费"
        if pages is None:
            return "预估成本未知，按 API 实际处理页数计费"
        return f"预估 {format_cost(pages * config.get_pdf_price())}"

    def start(self, params: dict, confirmed: bool = False) -> dict:
        """Create a job and launch its worker. Returns {"confirm": message}
        instead when the user has to agree to the cost first."""
        if self._worker is not None:
            raise UserError("已有任务正在运行，请等它结束。")
        path = Path(params.get("path") or "")
        if not path.is_file():
            raise UserError("请先选择 PDF 文件。")
        provider = params.get("provider")
        page_ranges = (params.get("page_ranges") or "").strip() or None
        pages = self._pages(path, page_ranges)
        out_dir = Path((params.get("out_dir") or "").strip() or path.parent)
        if provider == "llm":
            message = self._prepare_llm(pages)
        else:
            message = self._prepare_mathpix(params, pages)
        if message and not confirmed:
            return {"confirm": message}
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise UserError(f"无法创建输出目录：{out_dir}\n{exc}") from None
        # Remember a folder only if the user chose one; the default follows each file.
        memory = {"pdf_out_dir": None if out_dir == path.parent else str(out_dir)}
        if provider != "llm":
            memory.update(pdf_formats=list(params["formats"]),
                          pdf_rm_spaces=bool(params.get("rm_spaces", True)))
        config.update_ui_state(**memory)
        if provider == "llm":
            settings = config.get_llm()
            job = self.jobs.create_llm(path, {"page_ranges": page_ranges}, out_dir, settings)
            self._worker = LlmPdfWorker(self.jobs, job, settings, parent=self)
        else:
            creds = self._get_creds()
            opts = PdfOptions(formats=tuple(params["formats"]), page_ranges=page_ranges,
                              rm_spaces=bool(params.get("rm_spaces", True)))
            # Snapshot for billing. The local count is the whole document, so
            # it is only a valid fallback when no page range was requested.
            self._billing_page_count = self._page_count(path) if not page_ranges else None
            job = self.jobs.create(path, asdict(opts), out_dir, creds["app_id"],
                                   self._billing_page_count)
            self._worker = PdfWorker(path, opts, out_dir, creds["app_id"], creds["app_key"],
                                     parent=self, job_store=self.jobs, job=job)
        self._launch()
        return {}

    def _prepare_llm(self, pages: int | None) -> str:
        settings = config.get_llm()
        if not settings["api_key"]:
            raise UserError("请先在设置中填写大模型 API Key。")
        try:
            validate_endpoint(settings["base_url"])
        except ValueError as exc:
            raise UserError(str(exc)) from None
        if pages and pages > CONFIRM_PAGES:
            return f"将逐页识别 {pages} 页，按实际 Token 计费。继续？"
        return ""

    def _prepare_mathpix(self, params: dict, pages: int | None) -> str:
        formats = params.get("formats") or []
        if not formats:
            raise UserError("请至少勾选一种输出格式。")
        if any(f not in MATHPIX_FORMATS for f in formats):
            raise UserError("不支持的输出格式。")
        if not self._get_creds():
            raise UserError("请先在设置中填入 Mathpix API Key。")
        if pages is None:
            return "无法读取该 PDF 的页数，将按 API 实际处理页数计费。继续？"
        if pages > CONFIRM_PAGES:
            return f"将转换 {pages} 页，预估消耗约 {format_cost(pages * config.get_pdf_price())}。继续？"
        return ""

    def resume(self, job_id: str) -> None:
        if self._worker is not None:
            raise UserError("已有任务正在运行，请等它结束。")
        try:
            job = self.jobs.get(job_id)
        except ValueError as exc:
            raise UserError(str(exc)) from None
        if job.get("provider") == "llm":
            settings = config.get_llm()
            if not settings["api_key"] or settings["base_url"] != job["base_url"]:
                raise UserError("请先在设置中配置此任务原 API 地址及其有效密钥。")
            self._worker = LlmPdfWorker(self.jobs, job, settings, parent=self)
        else:
            if not job.get("pdf_id"):
                raise UserError("未取得远端任务 ID，无法恢复。请先检查 Mathpix 端是否已接收任务，"
                                "再决定是否重新转换。")
            creds = self._get_creds()
            if not creds or creds["app_id"] != job["app_id"]:
                raise UserError("请在设置中使用提交此任务时的 Mathpix app_id 和有效密钥。")
            self._billing_page_count = job.get("page_count")
            self._worker = PdfWorker(Path(job["source"]), PdfOptions(**job["options"]),
                                     Path(job["out_dir"]), creds["app_id"], creds["app_key"],
                                     parent=self, job_store=self.jobs, job=job)
        self._launch()

    def cancel(self) -> None:
        if self._worker:
            self._worker.cancel()
            self._status = "正在停止，等待当前请求返回…"
            self.changed.emit()

    # ---- worker ------------------------------------------------------------

    def _launch(self) -> None:
        self._percent, self._status, self._log = 0, "", []
        worker = self._worker
        worker.progress.connect(self._on_progress)
        worker.log.connect(self._on_log)
        worker.billed.connect(self._on_billed)
        worker.finished_ok.connect(self._on_done)
        worker.failed.connect(self._on_failed)
        worker.finished.connect(self._cleanup_worker)
        worker.start()
        self.changed.emit()

    def _on_progress(self, percent: int, text: str) -> None:
        self._percent, self._status = percent, text
        self.changed.emit()

    def _on_log(self, line: str) -> None:
        self._log = (self._log + [line])[-200:]
        self.changed.emit()

    def _on_billed(self, num_pages: int) -> None:
        # Emitted for every submitted job, including cancelled / failed ones
        # (Mathpix still bills them). Prefer the page count reported by the
        # API; fall back to the local count snapshot.
        job_id = self._worker.job_id if self._worker else None
        pages = num_pages if job_id else (num_pages or self._billing_page_count or 0)
        if not pages:
            return
        try:
            if job_id:
                config.record_pdf_pages(job_id, pages)
            else:
                config.bump_pdf_pages(pages)
        except Exception as exc:
            sys.stderr.write(f"counter bump failed: {exc}\n")
        if self._on_pages_processed:
            try:
                self._on_pages_processed(pages, job_id)
            except Exception:
                pass

    def _on_done(self, paths: list) -> None:
        self._percent = 100
        self.changed.emit()
        if paths:
            try:
                os.startfile(Path(paths[0]).parent)  # type: ignore[attr-defined]
            except Exception:
                pass

    def _on_failed(self, message: str) -> None:
        self._log = (self._log + [f"错误: {message}"])[-200:]
        self.changed.emit()

    def _cleanup_worker(self) -> None:
        worker, self._worker = self._worker, None
        if worker is not None:
            worker.deleteLater()
        self.changed.emit()
        self.activity_finished.emit()

    # ---- what the page shows -----------------------------------------------

    def state(self, limit: int = 30) -> dict:
        running = self._worker.job_id if self._worker else None
        return {"busy": self._worker is not None,
                "provider": config.get_provider("pdf"),
                "jobs": [self._job_view(job, running) for job in self.jobs.recent(limit)]}

    def _job_view(self, job: dict, running: str | None) -> dict:
        llm = job.get("provider") == "llm"
        live = job["id"] == running
        status = job.get("status", "")
        if not live and status in _ACTIVE_STATUSES:
            status = "已中断"
        error = job.get("error") or ""
        if error == "Cancelled by user":
            error = "已停止等待，Mathpix 可能继续处理。点继续可以接着取结果，不会重新上传。"
        files = job.get("files") or {}
        missing = any(not Path(f["path"]).is_file() for f in files.values())
        recoverable = llm or bool(job.get("pdf_id"))
        selected = job.get("selected_pages") or []
        results = job.get("page_results") or {}
        return {
            "id": job["id"],
            "name": Path(job["source"]).name,
            "provider": "llm" if llm else "mathpix",
            "model": job.get("model", "Mathpix"),
            "status": status,
            "error": error,
            "running": live,
            "percent": self._percent if live else 0,
            "status_text": self._status if live else "",
            "log": list(self._log) if live else [],
            "pages": job.get("pages", 0),
            "pages_done": job.get("pages_done", 0),
            "pages_total": job.get("pages_total", 0),
            "has_range": bool((job.get("options") or {}).get("page_ranges")),
            "page_map": [str(p) in results for p in selected],
            "extensions": [f".{ext}" for ext in files],
            "out_dir": job.get("out_dir", ""),
            "can_open": bool(files) and Path(job.get("out_dir", "")).is_dir(),
            "can_resume": recoverable and not live and (status != "已完成" or missing or not files),
        }

    def active_count(self) -> int:
        """Jobs that still need attention; the float window's footer shows it."""
        return sum(j.get("status") != "已完成"
                   and bool(j.get("pdf_id") or j.get("provider") == "llm")
                   for j in self.jobs.recent())
