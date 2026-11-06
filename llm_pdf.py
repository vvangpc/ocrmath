"""Resumable page-by-page PDF transcription through the Responses API."""
import io
import os
from pathlib import Path
import re
import shutil
import tempfile

from pypdf import PdfReader, PdfWriter
from PyQt6.QtCore import QThread, pyqtSignal

import config
from llm_client import cache_key, transcribe, PROMPT_VERSION
from llm_store import LlmStore
from pdf_client import _file_hash


def selected_pages(value: str | None, count: int) -> list[int]:
    if not value:
        return list(range(1, count + 1))
    pages = set()
    for part in value.split(","):
        match = re.fullmatch(r"\s*([1-9]\d*)\s*(?:-\s*([1-9]\d*)\s*)?", part)
        if not match:
            raise ValueError("页码格式应为 2,4-6，使用英文逗号")
        start, end = int(match[1]), int(match[2] or match[1])
        if start > end or end > count:
            raise ValueError(f"页码超出范围或顺序错误：{part}（共 {count} 页）")
        pages.update(range(start, end + 1))
    return sorted(pages)


class LlmPdfWorker(QThread):
    progress = pyqtSignal(int, str)
    log = pyqtSignal(str)
    billed = pyqtSignal(int)  # Mathpix compatibility; LLM usage is in the token ledger.
    finished_ok = pyqtSignal(list)
    failed = pyqtSignal(str)

    def __init__(self, job_store, job: dict, settings: dict, parent=None, *, usage_store=None):
        super().__init__(parent)
        self.store, self.job = job_store, job
        self.settings = dict(settings)
        self.settings.update(model=job["model"], base_url=job["base_url"])
        self.usage = usage_store

    @property
    def job_id(self):
        return self.job["id"]

    def cancel(self):
        self.requestInterruption()

    def check_cancel(self):
        if self.isInterruptionRequested():
            raise RuntimeError("已暂停，已完成的页面已保存，可继续任务")

    def save(self, **changes):
        self.job.update(changes)
        self.store.save(self.job)

    def run(self):
        try:
            paths = self.convert()
            self.save(status="已完成", error="")
        except Exception as exc:
            message = str(exc)
            try:
                self.save(status="可重试", error=message)
            except Exception as save_error:
                message += f"；任务保存失败：{save_error}"
            self.failed.emit(message)
            return
        self.finished_ok.emit(paths)

    def convert(self):
        self.check_cancel()
        if self.job.get("prompt_version") != PROMPT_VERSION:
            raise ValueError("任务使用旧版识别提示，请使用原版本恢复，或新建任务")
        usage = self.usage or LlmStore()
        usage.purge(config.get_cache_retention())
        results = self.job.setdefault("page_results", {})
        pages = self.job.get("selected_pages")
        pending = pages is None or any(str(p) not in results for p in pages)
        if pending:
            snapshot = self.job.get("source_snapshot")
            if not snapshot:
                target = self.store.path.parent / "pdf_sources" / f"{self.job_id}.pdf"
                target.parent.mkdir(parents=True, exist_ok=True)
                temp = target.with_suffix(".tmp")
                try:
                    shutil.copyfile(self.job["source"], temp)
                    os.replace(temp, target)
                finally:
                    temp.unlink(missing_ok=True)
                self.save(source_snapshot=str(target.resolve()), source_hash=_file_hash(target))
                snapshot = str(target)
            source = Path(snapshot)
            if _file_hash(source) != self.job["source_hash"]:
                raise ValueError("本地 PDF 副本已变化，无法将新内容混入旧任务")
            # Keep the stream open only while pages are being read.
            with source.open("rb") as stream:
                reader = PdfReader(stream)
                pages = selected_pages(self.job["options"].get("page_ranges"), len(reader.pages))
                if not pages:
                    raise ValueError("PDF 没有可识别的页面")
                self.save(selected_pages=pages, status="逐页识别中")
                for index, page in enumerate(pages):
                    self.check_cancel()
                    if str(page) not in results:
                        writer = PdfWriter()
                        writer.add_page(reader.pages[page - 1])
                        buffer = io.BytesIO()
                        writer.write(buffer)
                        data = buffer.getvalue()
                        if len(data) >= 50 * 1024 * 1024:
                            raise ValueError(f"第 {page} 页超过 API 文件大小限制")
                        key = cache_key(data, self.settings, "pdf_page")
                        result = usage.lookup(key)
                        if result is None:
                            self.log.emit(f"正在识别第 {page} 页 · {self.settings['model']}")
                            result = transcribe(data, self.settings, "pdf_page", usage)
                            usage.cache(key, result)
                        else:
                            self.log.emit(f"第 {page} 页命中本地缓存")
                        results[str(page)] = result["text"]
                        self.save(page_results=results, pages=len(results))
                    self.progress.emit(int((index + 1) / len(pages) * 95),
                                       f"已完成 {index + 1}/{len(pages)} 页")
        self.check_cancel()
        previous = self.job.get("files", {}).get("md")
        if previous:
            path = Path(previous["path"])
            if path.is_file() and _file_hash(path) == previous["sha256"]:
                return [path]
        out = Path(self.job["out_dir"])
        out.mkdir(parents=True, exist_ok=True)
        stem = Path(self.job["source"]).stem
        dest = out / f"{stem}.md"
        index = 1
        while dest.exists():
            dest = out / f"{stem} ({index}).md"
            index += 1
        # Page boundaries are preserved as invisible Markdown comments.
        markdown = "\n\n".join(f"<!-- page {p} -->\n\n{results[str(p)]}" for p in pages) + "\n"
        tmp = None
        try:
            with tempfile.NamedTemporaryFile(dir=out, prefix=".ocrmath-", suffix=".part",
                                             mode="w", encoding="utf-8", delete=False) as file:
                tmp = Path(file.name)
                file.write(markdown)
            self.check_cancel()
            os.replace(tmp, dest)
        finally:
            if tmp is not None:
                tmp.unlink(missing_ok=True)
        self.save(files={"md": {"path": str(dest.resolve()), "sha256": _file_hash(dest)}})
        self.progress.emit(100, "完成")
        return [dest]
