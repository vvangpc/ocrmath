"""Helpers shared by the Mathpix API clients."""
from __future__ import annotations

import requests


def format_request_error(exc: Exception) -> str:
    """Human-readable one-liner for errors raised by a requests call."""
    if isinstance(exc, requests.HTTPError):
        resp = exc.response
        status = resp.status_code if resp is not None else "?"
        body = resp.text if resp is not None else ""
        return f"HTTP {status}: {body[:300]}"
    if isinstance(exc, requests.RequestException):
        return f"Network error: {exc}"
    return f"Unexpected: {exc}"
