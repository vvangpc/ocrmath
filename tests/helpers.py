"""Shared test fixtures."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import config


class TempConfigTestCase(unittest.TestCase):
    """Points config at a throwaway file so tests never touch the real one."""

    def setUp(self) -> None:
        super().setUp()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        orig = config.CONFIG_PATH
        self.addCleanup(setattr, config, "CONFIG_PATH", orig)
        self.addCleanup(self._reset_caches)
        config.CONFIG_PATH = Path(tmp.name) / "config.dat"
        self._reset_caches()

    @staticmethod
    def _reset_caches() -> None:
        config._BLOB_CACHE = None
        config._SETTINGS_CACHE = None
