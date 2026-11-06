"""The release workflow publishes CHANGELOG.md's section for the current version."""
import importlib.util
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("release_notes", ROOT / "tools" / "release_notes.py")
release_notes = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release_notes)

SAMPLE = """## [Unreleased]

## [2.0.0] - 2026-11-06

### Added

- new

## [1.0.0] - 2026-05-07

### Added

- first

[Unreleased]: https://e/compare/v2.0.0...HEAD
[2.0.0]: https://e/compare/v1.0.0...v2.0.0
[1.0.0]: https://e/releases/tag/v1.0.0
"""


class ReleaseNotesTest(unittest.TestCase):
    def test_extracts_only_that_version_with_its_link(self):
        notes = release_notes.section(SAMPLE, "2.0.0")
        self.assertIn("- new", notes)
        self.assertNotIn("first", notes)
        self.assertIn("https://e/compare/v1.0.0...v2.0.0", notes)
        self.assertNotIn("[Unreleased]", notes)

    def test_last_version_stops_before_the_link_list(self):
        self.assertNotIn("HEAD", release_notes.section(SAMPLE, "1.0.0"))

    def test_missing_or_empty_section_fails(self):
        for version in ("9.9.9", "Unreleased"):
            with self.assertRaises(SystemExit):
                release_notes.section(SAMPLE, version)

    def test_current_version_has_notes(self):
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        version = re.search(r'^version\s*=\s*"([^"]+)"', pyproject, re.MULTILINE).group(1)
        changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        self.assertIn("###", release_notes.section(changelog, version))
