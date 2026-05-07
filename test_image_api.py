"""Manual smoke test for /v3/text. Usage:

    python test_image_api.py path/to/equation.png

Reads APP_ID/APP_KEY from env vars MATHPIX_APP_ID and MATHPIX_APP_KEY,
or from %APPDATA%\\ocrmath\\config.dat if config.py is set up.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from image_client import recognize


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: python test_image_api.py <image.png>")
        return 2
    img_path = Path(sys.argv[1])
    if not img_path.exists():
        print(f"file not found: {img_path}")
        return 2

    app_id = os.environ.get("MATHPIX_APP_ID")
    app_key = os.environ.get("MATHPIX_APP_KEY")
    if not (app_id and app_key):
        try:
            import config
            creds = config.load()
            if creds:
                app_id, app_key = creds["app_id"], creds["app_key"]
        except Exception:
            pass
    if not (app_id and app_key):
        print("set MATHPIX_APP_ID and MATHPIX_APP_KEY env vars, or run the app once to save config")
        return 2

    result = recognize(img_path.read_bytes(), app_id, app_key)
    print("--- text ---")
    print(result.get("text", ""))
    print("--- latex_styled ---")
    print(result.get("latex_styled", ""))
    print(f"--- confidence: {result.get('confidence')} ---")
    print(f"is_printed={result.get('is_printed')} is_handwritten={result.get('is_handwritten')}")
    print(f"request_id={result.get('request_id')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
