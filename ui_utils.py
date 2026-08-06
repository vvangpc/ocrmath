"""Shared display formatting helpers (cost, unit price, sync timestamp).

Pure functions + config dependency only — must not import Qt.
"""
from __future__ import annotations

from datetime import datetime

import config


def format_cost(usd: float) -> str:
    """Aggregate cost with CNY conversion: '$0.152 (¥1.06)'."""
    rate = config.get_usd_cny_rate()
    return f"${usd:.3f} (¥{usd * rate:.2f})"


def format_unit_price(usd: float, cny: bool = True) -> str:
    """Unit price: '$0.0020 (¥0.014)'; cny=False for compact contexts."""
    if not cny:
        return f"${usd:.4f}"
    rate = config.get_usd_cny_rate()
    return f"${usd:.4f} (¥{usd * rate:.3f})"


def format_synced(ts: float) -> str:
    if not ts:
        return "上次同步: 从未"
    try:
        return "上次同步: " + datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return "上次同步: —"
