"""Local token ledger and reusable PDF-page OCR cache (no credentials)."""
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import time

import config


class LlmStore:
    def __init__(self, path: Path | None = None):
        self.path = path or config.CONFIG_PATH.parent / "llm_usage.db"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path)) as conn, conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS requests (
                    id TEXT PRIMARY KEY, created REAL NOT NULL, model TEXT NOT NULL,
                    kind TEXT NOT NULL, input_tokens INTEGER NOT NULL,
                    output_tokens INTEGER NOT NULL, cached_tokens INTEGER NOT NULL,
                    usage_known INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS page_cache (
                    key TEXT PRIMARY KEY, created REAL NOT NULL, result TEXT NOT NULL);
            """)
            columns = {row[1] for row in conn.execute("PRAGMA table_info(requests)")}
            if "cost_usd" not in columns:
                # NULL = unpriced: requests made before a price was set stay so.
                conn.execute("ALTER TABLE requests ADD COLUMN cost_usd REAL")

    def record(self, event_id: str, model: str, kind: str, usage: dict | None,
               *, price: dict | None = None) -> float | None:
        """Log one request; `price` (USD per million tokens) freezes its cost.
        Returns that cost, or None when the price or usage is unknown."""
        def count(value):
            return value if type(value) is int and value >= 0 else 0
        u = usage or {}
        known = all(type(u.get(k)) is int for k in ("input_tokens", "output_tokens"))
        details = u.get("input_tokens_details") or {}
        input_tokens, output_tokens = count(u.get("input_tokens")), count(u.get("output_tokens"))
        cached_tokens = count(details.get("cached_tokens"))
        cost = None
        if price is not None and known:
            # Cached tokens are a subset of input tokens, billed at their own rate.
            cost = (max(0, input_tokens - cached_tokens) * price["input"]
                    + min(cached_tokens, input_tokens) * price["cached"]
                    + output_tokens * price["output"]) / 1_000_000
        with closing(sqlite3.connect(self.path)) as conn, conn:
            conn.execute("""INSERT OR IGNORE INTO requests (id, created, model, kind, input_tokens,
                output_tokens, cached_tokens, usage_known, cost_usd) VALUES (?,?,?,?,?,?,?,?,?)""",
                (event_id, time.time(), model, kind, input_tokens, output_tokens,
                 cached_tokens, int(known), cost))
        return cost

    def summary(self, since=0) -> list[dict]:
        with closing(sqlite3.connect(self.path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""SELECT model, COUNT(*) AS requests,
                SUM(input_tokens) AS input_tokens, SUM(output_tokens) AS output_tokens,
                SUM(cached_tokens) AS cached_tokens, SUM(1-usage_known) AS unknown,
                COALESCE(SUM(cost_usd), 0) AS cost_usd,
                SUM(usage_known=1 AND cost_usd IS NULL) AS unpriced
                FROM requests WHERE created>=? GROUP BY model ORDER BY model""", (since,)).fetchall()
        return [dict(row) for row in rows]

    def models(self) -> list[str]:
        with closing(sqlite3.connect(self.path)) as conn:
            return [row[0] for row in conn.execute(
                "SELECT DISTINCT model FROM requests ORDER BY model")]

    def lookup(self, key: str) -> dict | None:
        with closing(sqlite3.connect(self.path)) as conn:
            row = conn.execute("SELECT result FROM page_cache WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else None

    def cache(self, key: str, result: dict) -> None:
        with closing(sqlite3.connect(self.path)) as conn, conn:
            conn.execute("INSERT OR REPLACE INTO page_cache VALUES (?, ?, ?)",
                         (key, time.time(), json.dumps(result, ensure_ascii=False)))

    def purge(self, days: int) -> None:
        if days > 0:
            with closing(sqlite3.connect(self.path)) as conn, conn:
                conn.execute("DELETE FROM page_cache WHERE created<?", (time.time()-days*86400,))
