"""Mathpix /v3/text image OCR client."""
from __future__ import annotations

import base64
import json
from typing import Any

import requests
from PyQt6.QtCore import QThread, pyqtSignal

API_URL = "https://api.mathpix.com/v3/text"


def recognize(
    png_bytes: bytes,
    app_id: str,
    app_key: str,
    *,
    inline_delim: tuple[str, str] = ("$", "$"),
    display_delim: tuple[str, str] = ("$$", "$$"),
    rm_spaces: bool = True,
    timeout: int = 30,
) -> dict[str, Any]:
    b64 = base64.b64encode(png_bytes).decode()
    payload = {
        "src": f"data:image/png;base64,{b64}",
        "formats": ["text", "latex_styled"],
        "data_options": {"include_latex": True, "include_asciimath": False},
        "math_inline_delimiters": list(inline_delim),
        "math_display_delimiters": list(display_delim),
        "rm_spaces": rm_spaces,
    }
    resp = requests.post(
        API_URL,
        headers={
            "app_id": app_id,
            "app_key": app_key,
            "Content-Type": "application/json",
        },
        data=json.dumps(payload),
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.json()


class ImageOcrWorker(QThread):
    """Run /v3/text in a background thread; emit finished/failed signals."""

    finished_ok = pyqtSignal(dict)
    failed = pyqtSignal(str)

    def __init__(self, png_bytes: bytes, app_id: str, app_key: str, parent=None):
        super().__init__(parent)
        self._png = png_bytes
        self._id = app_id
        self._key = app_key

    def run(self) -> None:
        try:
            result = recognize(self._png, self._id, self._key)
            if "error" in result:
                self.failed.emit(str(result.get("error")))
                return
            self.finished_ok.emit(result)
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else "?"
            body = exc.response.text if exc.response is not None else ""
            self.failed.emit(f"HTTP {status}: {body[:300]}")
        except requests.RequestException as exc:
            self.failed.emit(f"Network error: {exc}")
        except Exception as exc:
            self.failed.emit(f"Unexpected: {exc}")
