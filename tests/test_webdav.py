import unittest
from unittest import mock

import config
import webdav
from tests.helpers import TempConfigTestCase

WD = {"url": "https://dav.example", "user": "u", "password": "p",
      "path": "/ocrmath/sync.json", "interval": 0}


class BuildUrlTest(unittest.TestCase):
    def test_joins_base_path_and_remote_path(self):
        self.assertEqual(
            webdav._build_url("https://h.example/dav/", "ocrmath/s.json"),
            "https://h.example/dav/ocrmath/s.json")

    def test_defaults_to_https(self):
        self.assertEqual(webdav._build_url("h.example", "/a.json"),
                         "https://h.example/a.json")


class MergeTest(unittest.TestCase):
    def test_counters_take_max(self):
        out = webdav.merge({"image_count": 3, "pdf_page_count": 9}, 0,
                           {"image_count": 5, "pdf_page_count": 1}, 0)
        self.assertEqual((out["image_count"], out["pdf_page_count"]), (5, 9))

    def test_newer_edit_wins_and_carries_its_timestamp(self):
        local = {"app_key": "L", "image_price_usd": 0.1}
        remote = {"app_key": "R", "image_price_usd": 0.2}
        out = webdav.merge(local, 100.0, remote, 200.0)
        self.assertEqual(out["app_key"], "R")
        self.assertEqual(out["settings_modified_at"], 200.0)
        out = webdav.merge(local, 300.0, remote, 200.0)
        self.assertEqual(out["app_key"], "L")
        self.assertEqual(out["settings_modified_at"], 300.0)

    def test_no_remote_returns_local(self):
        self.assertEqual(webdav.merge({"a": 1}, 0, None, 0), {"a": 1})


class SyncOnceTest(TempConfigTestCase):
    """sync_once against a fake server; `during` runs between download and
    upload to simulate main-thread writes landing mid-sync."""

    def sync(self, remote_env, during=None):
        uploaded = {}

        def fake_download(*_a, **_k):
            if during:
                during()
            return remote_env

        def fake_upload(_url, _user, _pw, _path, payload, **_k):
            uploaded.update(payload)

        with mock.patch.object(webdav, "download", fake_download), \
                mock.patch.object(webdav, "upload", fake_upload):
            webdav.sync_once(WD)
        return uploaded

    def test_counter_bump_during_sync_survives(self):
        config.save_all({"image_count": 10})
        self.sync({"synced_at": 50, "data": {"image_count": 5}},
                  during=lambda: config.bump_image_count(1))
        self.assertEqual(config.get_counters()[0], 11)

    def test_settings_saved_during_sync_are_kept_then_pushed(self):
        config.save_all({"app_id": "A", "app_key": "OLD",
                         "settings_modified_at": 100.0})
        remote = {"synced_at": 500, "data": {
            "app_id": "A", "app_key": "REMOTE",
            "settings_modified_at": 300.0}}
        self.sync(remote,
                  during=lambda: config.save_settings({"app_key": "NEW"}))
        self.assertEqual(config.load_all()["app_key"], "NEW")
        uploaded = self.sync(remote)
        self.assertEqual(uploaded["data"]["app_key"], "NEW")

    def test_unsynced_older_edit_beats_a_later_plain_sync(self):
        # Another device synced at t=900 but last *edited* at t=10; our
        # edit at t=200 is newer and must win.
        config.save_all({"app_id": "A", "app_key": "K",
                         "image_price_usd": 0.003,
                         "settings_modified_at": 200.0})
        uploaded = self.sync({"synced_at": 900, "data": {
            "app_id": "A", "app_key": "K", "image_price_usd": 0.002,
            "settings_modified_at": 10.0}})
        self.assertEqual(config.get_image_price(), 0.003)
        self.assertEqual(uploaded["data"]["image_price_usd"], 0.003)
        self.assertEqual(uploaded["data"]["settings_modified_at"], 200.0)

    def test_legacy_remote_falls_back_to_synced_at(self):
        config.save_all({"app_id": "A", "app_key": "K",
                         "settings_modified_at": 200.0})
        self.sync({"synced_at": 900,
                   "data": {"app_id": "A", "app_key": "OLDFMT"}})
        self.assertEqual(config.load_all()["app_key"], "OLDFMT")

    def test_empty_remote_uploads_local(self):
        config.save_all({"app_id": "A", "app_key": "K", "image_count": 4})
        uploaded = self.sync(None)
        self.assertEqual(uploaded["data"]["app_key"], "K")
        self.assertEqual(uploaded["data"]["image_count"], 4)
        self.assertGreater(config.get_last_synced(), 0)


if __name__ == "__main__":
    unittest.main()
