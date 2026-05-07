"""SQLite-backed cache + history for image OCR results.

One row in `recognitions` represents both a cache entry (looked up by image
SHA256) and a history entry (listed by created_at). PNG files live on disk
in a hash-bucketed cache directory; the row stores a relative path.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS recognitions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    image_sha256  TEXT    NOT NULL UNIQUE,
    created_at    REAL    NOT NULL,
    image_rel     TEXT    NOT NULL,
    text          TEXT,
    latex         TEXT,
    confidence    REAL,
    is_printed    INTEGER,
    is_handwritten INTEGER,
    request_id    TEXT,
    raw_json      TEXT
);
CREATE INDEX IF NOT EXISTS idx_created ON recognitions(created_at DESC);

CREATE TABLE IF NOT EXISTS usage (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at  REAL    NOT NULL,
    kind        TEXT    NOT NULL,    -- 'image' or 'pdf'
    count       INTEGER NOT NULL,    -- 1 for image, page_count for PDF
    cost_usd    REAL    NOT NULL     -- frozen at event time
);
CREATE INDEX IF NOT EXISTS idx_usage_created ON usage(created_at);
"""


def default_base_dir() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", str(Path.home() / "AppData/Roaming")))
    else:
        base = Path.home() / ".local" / "share"
    return base / "ocrmath"


@dataclass
class Recognition:
    id: int
    image_sha256: str
    created_at: float
    image_rel: str
    text: str
    latex: str
    confidence: float | None
    is_printed: bool
    is_handwritten: bool
    request_id: str
    result: dict          # the full Mathpix response dict


class Storage:
    def __init__(self, base_dir: Path | None = None):
        self.base_dir = base_dir or default_base_dir()
        self.cache_dir = self.base_dir / "cache"
        self.db_path = self.base_dir / "ocrmath.db"
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(
            str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)
        self._conn.commit()
        self._lock = threading.RLock()

    # ---- helpers -----------------------------------------------------------

    def _png_path(self, sha: str) -> Path:
        return self.cache_dir / sha[:2] / f"{sha}.png"

    def _row_to_recognition(self, row: sqlite3.Row) -> Recognition:
        try:
            result = json.loads(row["raw_json"]) if row["raw_json"] else {}
        except Exception:
            result = {}
        # Fall back to per-column fields if raw_json is missing/corrupt
        if not result:
            result = {
                "text": row["text"] or "",
                "latex_styled": row["latex"] or "",
                "confidence": row["confidence"],
                "is_printed": bool(row["is_printed"]),
                "is_handwritten": bool(row["is_handwritten"]),
                "request_id": row["request_id"] or "",
            }
        return Recognition(
            id=row["id"],
            image_sha256=row["image_sha256"],
            created_at=row["created_at"],
            image_rel=row["image_rel"],
            text=row["text"] or "",
            latex=row["latex"] or "",
            confidence=row["confidence"],
            is_printed=bool(row["is_printed"]),
            is_handwritten=bool(row["is_handwritten"]),
            request_id=row["request_id"] or "",
            result=result,
        )

    # ---- public API --------------------------------------------------------

    def lookup(self, sha256: str) -> Recognition | None:
        with self._lock:
            cur = self._conn.execute(
                "SELECT * FROM recognitions WHERE image_sha256 = ?", (sha256,))
            row = cur.fetchone()
        return self._row_to_recognition(row) if row else None

    def insert(self, sha256: str, png_bytes: bytes, result: dict) -> int:
        rel = f"{sha256[:2]}/{sha256}.png"
        path = self._png_path(sha256)
        path.parent.mkdir(parents=True, exist_ok=True)
        # Write PNG first (so DB row never points at a missing file)
        path.write_bytes(png_bytes)
        try:
            with self._lock:
                cur = self._conn.execute(
                    "INSERT INTO recognitions "
                    "(image_sha256, created_at, image_rel, text, latex, "
                    " confidence, is_printed, is_handwritten, request_id, raw_json) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (
                        sha256,
                        time.time(),
                        rel,
                        result.get("text", ""),
                        result.get("latex_styled", ""),
                        result.get("confidence"),
                        1 if result.get("is_printed") else 0,
                        1 if result.get("is_handwritten") else 0,
                        result.get("request_id", ""),
                        json.dumps(result),
                    ),
                )
                self._conn.commit()
                return cur.lastrowid or 0
        except sqlite3.IntegrityError:
            # Already cached under same hash — just keep the existing row
            with self._lock:
                cur = self._conn.execute(
                    "SELECT id FROM recognitions WHERE image_sha256 = ?",
                    (sha256,))
                row = cur.fetchone()
                return int(row["id"]) if row else 0
        except Exception:
            # Roll back the orphan PNG
            try:
                path.unlink(missing_ok=True)
            except Exception:
                pass
            raise

    def list_recent(self, query: str = "", limit: int = 200) -> list[Recognition]:
        with self._lock:
            if query:
                pat = f"%{query}%"
                cur = self._conn.execute(
                    "SELECT * FROM recognitions "
                    "WHERE text LIKE ? OR latex LIKE ? "
                    "ORDER BY created_at DESC LIMIT ?",
                    (pat, pat, limit),
                )
            else:
                cur = self._conn.execute(
                    "SELECT * FROM recognitions ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                )
            rows = cur.fetchall()
        return [self._row_to_recognition(r) for r in rows]

    def get(self, rec_id: int) -> Recognition | None:
        with self._lock:
            cur = self._conn.execute(
                "SELECT * FROM recognitions WHERE id = ?", (rec_id,))
            row = cur.fetchone()
        return self._row_to_recognition(row) if row else None

    def delete(self, rec_id: int) -> None:
        with self._lock:
            cur = self._conn.execute(
                "SELECT image_sha256 FROM recognitions WHERE id = ?", (rec_id,))
            row = cur.fetchone()
            if not row:
                return
            sha = row["image_sha256"]
            self._conn.execute("DELETE FROM recognitions WHERE id = ?", (rec_id,))
            self._conn.commit()
        # Best-effort: remove file
        try:
            self._png_path(sha).unlink(missing_ok=True)
        except Exception:
            pass

    # ---- usage events ------------------------------------------------------

    def log_usage(self, kind: str, count: int, unit_price_usd: float) -> None:
        """Record one billable event (image OCR call or PDF conversion)."""
        if count <= 0:
            return
        cost = float(count) * float(unit_price_usd)
        with self._lock:
            self._conn.execute(
                "INSERT INTO usage (created_at, kind, count, cost_usd) "
                "VALUES (?, ?, ?, ?)",
                (time.time(), kind, int(count), cost),
            )
            self._conn.commit()

    def usage_summary(self, since_ts: float) -> dict[str, Any]:
        """Aggregate usage events on/after `since_ts`. Returns:
        {'image_count': N, 'pdf_pages': M, 'total_cost': X}"""
        with self._lock:
            cur = self._conn.execute(
                "SELECT kind, "
                "       COALESCE(SUM(count), 0) AS c, "
                "       COALESCE(SUM(cost_usd), 0) AS s "
                "FROM usage WHERE created_at >= ? GROUP BY kind",
                (since_ts,),
            )
            rows = cur.fetchall()
        out = {"image_count": 0, "pdf_pages": 0, "total_cost": 0.0}
        for r in rows:
            kind = r["kind"]
            if kind == "image":
                out["image_count"] = int(r["c"] or 0)
            elif kind == "pdf":
                out["pdf_pages"] = int(r["c"] or 0)
            out["total_cost"] += float(r["s"] or 0.0)
        return out

    def backfill_image_usage(self, unit_price_usd: float) -> int:
        """One-shot migration: populate `usage` from existing recognitions.

        For users who recognized images before the `usage` table existed.
        Each recognition row → one image event with the given unit price
        (we have to assume the current price; the historical one is unknown).
        Caller is responsible for guarding against double-runs (use
        `config.usage_backfilled` flag)."""
        with self._lock:
            cur = self._conn.execute(
                "SELECT created_at FROM recognitions ORDER BY created_at")
            timestamps = [r["created_at"] for r in cur.fetchall()]
            if not timestamps:
                return 0
            cost = float(unit_price_usd)
            self._conn.executemany(
                "INSERT INTO usage (created_at, kind, count, cost_usd) "
                "VALUES (?, 'image', 1, ?)",
                [(ts, cost) for ts in timestamps],
            )
            self._conn.commit()
            return len(timestamps)

    def purge_older_than(self, days: int) -> int:
        """Delete recognitions older than `days` days, plus their PNG files.
        Returns the number of recognitions deleted."""
        if days <= 0:
            return 0
        cutoff = time.time() - days * 86400
        with self._lock:
            cur = self._conn.execute(
                "SELECT image_sha256 FROM recognitions WHERE created_at < ?",
                (cutoff,),
            )
            shas = [r["image_sha256"] for r in cur.fetchall()]
            if shas:
                self._conn.execute(
                    "DELETE FROM recognitions WHERE created_at < ?",
                    (cutoff,),
                )
                self._conn.commit()
        for sha in shas:
            try:
                self._png_path(sha).unlink(missing_ok=True)
            except Exception:
                pass
        return len(shas)

    def purge_old_usage(self, days: int) -> int:
        """Drop usage events older than `days` days. Returns count deleted."""
        if days <= 0:
            return 0
        cutoff = time.time() - days * 86400
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM usage WHERE created_at < ?", (cutoff,))
            self._conn.commit()
            return cur.rowcount or 0

    # ---- bulk ops ----------------------------------------------------------

    def clear_all(self) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM recognitions")
            self._conn.commit()
        # Wipe cache directory contents (keep the dir itself)
        for sub in self.cache_dir.iterdir():
            if sub.is_dir():
                for f in sub.iterdir():
                    try:
                        f.unlink()
                    except Exception:
                        pass
                try:
                    sub.rmdir()
                except Exception:
                    pass

    def png_bytes(self, sha256: str) -> bytes | None:
        p = self._png_path(sha256)
        if not p.exists():
            return None
        try:
            return p.read_bytes()
        except Exception:
            return None

    def close(self) -> None:
        try:
            self._conn.close()
        except Exception:
            pass

    def stats(self) -> dict[str, Any]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT COUNT(*) AS n, MIN(created_at) AS first, "
                "MAX(created_at) AS last FROM recognitions")
            row = cur.fetchone()
        # Disk usage of cache dir
        size = 0
        for sub in self.cache_dir.glob("**/*.png"):
            try:
                size += sub.stat().st_size
            except Exception:
                pass
        return {
            "count": int(row["n"] or 0),
            "first_at": row["first"],
            "last_at": row["last"],
            "cache_bytes": size,
        }


# ---- self-test ------------------------------------------------------------

def _selftest() -> int:
    import tempfile
    print("running storage self-test...")
    with tempfile.TemporaryDirectory() as tmp:
        st = Storage(Path(tmp) / "ocrmath")
        # initial empty
        assert st.list_recent() == []
        assert st.lookup("deadbeef") is None
        # insert two
        r1 = st.insert("a" * 64, b"\x89PNG fake1",
                       {"text": "$x$", "latex_styled": "x", "confidence": 0.9})
        r2 = st.insert("b" * 64, b"\x89PNG fake2",
                       {"text": "$y$", "latex_styled": "y", "confidence": 0.5})
        assert r1 != r2 and r1 > 0 and r2 > 0
        assert len(st.list_recent()) == 2
        # search
        assert len(st.list_recent("y")) == 1
        # cache hit returns same row
        r1b = st.insert("a" * 64, b"\x89PNG fake1",
                        {"text": "$x$", "latex_styled": "x", "confidence": 0.9})
        assert r1 == r1b, f"expected dedupe, got {r1} vs {r1b}"
        # lookup
        rec = st.lookup("a" * 64)
        assert rec is not None and rec.latex == "x" and rec.result["text"] == "$x$"
        # delete one
        st.delete(rec.id)
        assert st.lookup("a" * 64) is None
        assert len(st.list_recent()) == 1
        # clear all
        st.clear_all()
        assert st.list_recent() == []
        # cache dir should have no png files
        pngs = list((Path(tmp) / "ocrmath" / "cache").glob("**/*.png"))
        assert pngs == [], f"expected empty cache, got {pngs}"
        st.close()
        print("OK")
    return 0


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        sys.exit(_selftest())
    if len(sys.argv) > 1 and sys.argv[1] == "stats":
        s = Storage().stats()
        print(s)
        sys.exit(0)
    print(f"storage at {default_base_dir()}")
    print(Storage().stats())
