"""Manual smoke test for /v3/pdf. Usage:

    python test_pdf_api.py path/to/input.pdf [out_dir]

Use a SMALL pdf (1-2 pages) to avoid wasting credits.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

from pdf_client import PdfOptions, submit_file, get_status, download


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: python test_pdf_api.py <input.pdf> [out_dir]")
        return 2
    pdf_path = Path(sys.argv[1])
    out_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else pdf_path.parent / "out"
    if not pdf_path.exists():
        print(f"file not found: {pdf_path}")
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
        print("set MATHPIX_APP_ID and MATHPIX_APP_KEY env vars first")
        return 2

    opts = PdfOptions(formats=("mmd", "docx"))
    print(f"Submitting {pdf_path}...")
    pdf_id = submit_file(pdf_path, opts, app_id, app_key)
    print(f"pdf_id={pdf_id}")

    print("Polling...")
    while True:
        time.sleep(2)
        s = get_status(pdf_id, app_id, app_key)
        print(f"  status={s.get('status')} {s.get('percent_done')}% "
              f"({s.get('num_pages_completed')}/{s.get('num_pages')})")
        if s.get("status") == "completed":
            break
        if s.get("status") == "error":
            print(f"server error: {s}")
            return 1

    out_dir.mkdir(parents=True, exist_ok=True)
    for ext in opts.formats:
        dest = out_dir / f"{pdf_path.stem}.{ext}"
        print(f"Downloading {dest}...")
        download(pdf_id, ext, dest, app_id, app_key)
    print("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
