"""Durable local PDF jobs. API keys are never stored in this database."""
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import time
import uuid

import config


class PdfJobStore:
    def __init__(self, path: Path | None = None):
        self.path = path or config.CONFIG_PATH.parent / "pdf_jobs.db"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path)) as conn, conn:
            conn.execute("CREATE TABLE IF NOT EXISTS jobs "
                         "(id TEXT PRIMARY KEY, updated REAL NOT NULL, data TEXT NOT NULL)")

    def create(self, source: Path, options: dict, out_dir: Path,
               app_id: str, page_count: int | None = None) -> dict:
        job = {"id": uuid.uuid4().hex, "source": str(source.resolve()),
               "options": options, "out_dir": str(out_dir.resolve()),
               "app_id": app_id, "pdf_id": None, "status": "待提交",
               "files": {}, "pages": 0, "page_count": page_count, "error": ""}
        self.save(job)
        return job

    def save(self, job: dict) -> None:
        job["updated"] = time.time()
        with closing(sqlite3.connect(self.path)) as conn, conn:
            conn.execute("INSERT INTO jobs VALUES (?, ?, ?) ON CONFLICT(id) "
                         "DO UPDATE SET updated=excluded.updated, data=excluded.data",
                         (job["id"], job["updated"], json.dumps(job, ensure_ascii=False)))

    def create_llm(self, source: Path, options: dict, out_dir: Path, settings: dict) -> dict:
        from llm_client import PROMPT_VERSION
        job = {"id": uuid.uuid4().hex, "source": str(source.resolve()),
               "options": options, "out_dir": str(out_dir.resolve()),
               "provider": "llm", "model": settings["model"],
               "base_url": settings["base_url"], "prompt_version": PROMPT_VERSION,
               "status": "待处理", "files": {}, "pages": 0, "page_results": {}, "error": ""}
        self.save(job)
        return job

    def get(self, job_id: str) -> dict:
        with closing(sqlite3.connect(self.path)) as conn:
            row = conn.execute("SELECT data FROM jobs WHERE id=?", (job_id,)).fetchone()
        if row is None:
            raise ValueError("任务记录不存在")
        return json.loads(row[0])

    def recent(self, limit=100) -> list[dict]:
        with closing(sqlite3.connect(self.path)) as conn:
            rows = conn.execute("SELECT data FROM jobs ORDER BY updated DESC LIMIT ?",
                                (limit,)).fetchall()
        return [json.loads(row[0]) for row in rows]
