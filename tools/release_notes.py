"""Write one version's section of CHANGELOG.md, used as its GitHub Release body.

    python tools/release_notes.py 2.0.0 notes.md

Fails if the version has no section, so a release can't ship without notes.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def section(changelog: str, version: str) -> str:
    match = re.search(rf"^## \[{re.escape(version)}\][^\n]*\n(.*?)(?=^## \[|^\[Unreleased\]:)",
                      changelog, re.MULTILINE | re.DOTALL)
    body = match.group(1).strip() if match else ""
    if not body:
        raise SystemExit(f"CHANGELOG.md has no notes for {version}")
    link = re.search(rf"^\[{re.escape(version)}\]: (\S+)$", changelog, re.MULTILINE)
    return body + (f"\n\n**完整改动**：{link.group(1)}\n" if link else "\n")


def main() -> int:
    version, out = sys.argv[1:3]
    text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    Path(out).write_text(section(text, version), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
