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
    raw_json      TEXT,
    png_size      INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_created ON recognitions(created_at DESC);

CREATE TABLE IF NOT EXISTS usage (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at  REAL    NOT NULL,
    kind        TEXT    NOT NULL,    -- 'image' or 'pdf'
    count       INTEGER NOT NULL,    -- 1 for image, page_count for PDF
    cost_usd    REAL    NOT NULL,    -- frozen at event time
    source      TEXT    NOT NULL DEFAULT 'live'  -- 'live' or 'backfill'
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
        self._migrate()
        self._conn.commit()
        self._lock = threading.RLock()

    # ---- helpers -----------------------------------------------------------

    def _migrate(self) -> None:
        """Upgrade databases created before newer columns existed."""
        cols = {r[1] for r in self._conn.execute(
            "PRAGMA table_info(recognitions)")}
        if "png_size" not in cols:
            self._conn.execute(
                "ALTER TABLE recognitions "
                "ADD COLUMN png_size INTEGER NOT NULL DEFAULT 0")
            # One-time backfill from disk so stats() can rely on the DB.
            rows = self._conn.execute(
                "SELECT id, image_sha256 FROM recognitions").fetchall()
            for row in rows:
                try:
                    size = self._png_path(row["image_sha256"]).stat().st_size
                except OSError:
                    size = 0
                self._conn.execute(
                    "UPDATE recognitions SET png_size = ? WHERE id = ?",
                    (size, row["id"]))
        ucols = {r[1] for r in self._conn.execute("PRAGMA table_info(usage)")}
        if "source" not in ucols:
            self._conn.execute(
                "ALTER TABLE usage "
                "ADD COLUMN source TEXT NOT NULL DEFAULT 'live'")
        self._conn.commit()

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
        # Write PNG first (so DB row never points at a missing file); the
        # same image may already be cached on disk from a concurrent insert.
        if not path.exists():
            path.write_bytes(png_bytes)
        try:
            with self._lock:
                cur = self._conn.execute(
                    "INSERT INTO recognitions "
                    "(image_sha256, created_at, image_rel, text, latex, "
                    " confidence, is_printed, is_handwritten, request_id, "
                    " raw_json, png_size) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
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
                        len(png_bytes),
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
                esc = (query.replace("\\", "\\\\")
                       .replace("%", "\\%").replace("_", "\\_"))
                pat = f"%{esc}%"
                cur = self._conn.execute(
                    "SELECT * FROM recognitions "
                    "WHERE text LIKE ? ESCAPE '\\' OR latex LIKE ? ESCAPE '\\' "
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
                "INSERT INTO usage (created_at, kind, count, cost_usd, source) "
                "VALUES (?, ?, ?, ?, 'live')",
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
        Idempotent regardless of the config-side flag: skips if backfill rows
        already exist, and only fills recognitions older than the earliest
        live image event (newer ones were logged in real time)."""
        with self._lock:
            if self._conn.execute(
                    "SELECT 1 FROM usage WHERE source = 'backfill' LIMIT 1"
                    ).fetchone():
                return 0
            row = self._conn.execute(
                "SELECT MIN(created_at) AS m FROM usage WHERE kind = 'image'"
                ).fetchone()
            if row["m"] is None:
                cur = self._conn.execute(
                    "SELECT created_at FROM recognitions ORDER BY created_at")
            else:
                cur = self._conn.execute(
                    "SELECT created_at FROM recognitions "
                    "WHERE created_at < ? ORDER BY created_at", (row["m"],))
            timestamps = [r["created_at"] for r in cur.fetchall()]
            if not timestamps:
                return 0
            cost = float(unit_price_usd)
            self._conn.executemany(
                "INSERT INTO usage (created_at, kind, count, cost_usd, source) "
                "VALUES (?, 'image', 1, ?, 'backfill')",
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
        """Delete all recognitions + cached PNGs.
        Usage/cost records are intentionally kept."""
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
                "MAX(created_at) AS last, "
                "COALESCE(SUM(png_size), 0) AS cache_bytes FROM recognitions")
            row = cur.fetchone()
        return {
            "count": int(row["n"] or 0),
            "first_at": row["first"],
            "last_at": row["last"],
            "cache_bytes": int(row["cache_bytes"] or 0),
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
        # cache size comes from the DB, not a directory walk
        expected = len(b"\x89PNG fake1") + len(b"\x89PNG fake2")
        assert st.stats()["cache_bytes"] == expected
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
        # LIKE wildcard escaping: % and _ match literally, not as wildcards
        st.insert("d" * 64, b"png-d", {"text": "50% off", "latex_styled": ""})
        st.insert("e" * 64, b"png-e", {"text": "a_b", "latex_styled": ""})
        assert len(st.list_recent("%")) == 1
        assert len(st.list_recent("_")) == 1
        assert len(st.list_recent("50%")) == 1
        # usage records survive clear_all
        st.log_usage("image", 1, 0.002)
        st.clear_all()
        assert st.usage_summary(0)["image_count"] == 1
        st.close()
    # backfill idempotency: second run is a no-op
    with tempfile.TemporaryDirectory() as tmp:
        st = Storage(Path(tmp) / "ocrmath")
        st.insert("a" * 64, b"p1", {"text": "x"})
        st.insert("b" * 64, b"p2", {"text": "y"})
        assert st.backfill_image_usage(0.002) == 2
        assert st.backfill_image_usage(0.002) == 0
        assert st.usage_summary(0)["image_count"] == 2
        st.close()
    # backfill guard 2: only recognitions older than the earliest live
    # image event are filled (newer ones were logged in real time)
    with tempfile.TemporaryDirectory() as tmp:
        st = Storage(Path(tmp) / "ocrmath")
        st.log_usage("image", 1, 0.002)
        st._conn.execute(
            "INSERT INTO recognitions (image_sha256, created_at, image_rel) "
            "VALUES (?, ?, ?)", ("f" * 64, time.time() - 1000, "ff/old.png"))
        st._conn.execute(
            "INSERT INTO recognitions (image_sha256, created_at, image_rel) "
            "VALUES (?, ?, ?)", ("0" * 64, time.time() + 10, "00/new.png"))
        st._conn.commit()
        assert st.backfill_image_usage(0.002) == 1
        st.close()
    # migration: a pre-png_size database gets the column backfilled from disk
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp) / "ocrmath"
        sha = "c" * 64
        png_dir = base / "cache" / sha[:2]
        png_dir.mkdir(parents=True)
        (png_dir / f"{sha}.png").write_bytes(b"\x89PNG old")
        conn = sqlite3.connect(str(base / "ocrmath.db"))
        conn.execute(
            "CREATE TABLE recognitions ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "image_sha256 TEXT NOT NULL UNIQUE, created_at REAL NOT NULL,"
            "image_rel TEXT NOT NULL, text TEXT, latex TEXT, confidence REAL,"
            "is_printed INTEGER, is_handwritten INTEGER, request_id TEXT,"
            "raw_json TEXT)")
        conn.execute(
            "INSERT INTO recognitions (image_sha256, created_at, image_rel) "
            "VALUES (?, ?, ?)", (sha, time.time(), f"{sha[:2]}/{sha}.png"))
        # pre-`source` usage table gets the column added, old rows -> 'live'
        conn.execute(
            "CREATE TABLE usage ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, created_at REAL NOT NULL,"
            "kind TEXT NOT NULL, count INTEGER NOT NULL,"
            "cost_usd REAL NOT NULL)")
        conn.execute(
            "INSERT INTO usage (created_at, kind, count, cost_usd) "
            "VALUES (?, 'image', 1, 0.002)", (time.time(),))
        conn.commit()
        conn.close()
        st = Storage(base)
        assert st.stats()["cache_bytes"] == len(b"\x89PNG old"), \
            f"migration backfill failed: {st.stats()}"
        row = st._conn.execute("SELECT source FROM usage").fetchone()
        assert row["source"] == "live", f"usage migration failed: {row}"
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
