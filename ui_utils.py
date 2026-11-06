"""Shared helpers for showing things to the user.

Pure functions + config dependency only — must not import Qt.
"""
from __future__ import annotations

import config


class UserError(Exception):
    """A problem the user can fix; its message is shown as is."""


def format_cost(usd: float) -> str:
    """Aggregate cost with CNY conversion: '$0.152 (¥1.06)'."""
    rate = config.get_usd_cny_rate()
    return f"${usd:.3f} (¥{usd * rate:.2f})"
