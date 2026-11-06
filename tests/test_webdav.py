import base64
import copy
import json
import unittest
from unittest import mock

import config
import counters
import sync_crypto
import webdav
from tests.helpers import TempConfigTestCase

WD = {"url": "https://dav.example", "user": "u", "password": "p",
      "passphrase": "correct horse", "path": "/ocrmath/sync.json", "interval": 0}


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


V3 = "/ocrmath/sync.v3.json"
V2 = "/ocrmath/sync.v2.json"
LEGACY = "/ocrmath/sync.json"


class FakeDav:
    """In-memory server behind webdav.download / upload / delete. `during`
    runs at each read of the encrypted file, to simulate writes landing mid-sync."""

    def __init__(self, files=None):
        self.files = dict(files or {})
        self.during = None
        self.conflicts = 0
        self.undeletable = set()
        self.puts = []
        self.etags = []

    def download(self, _url, _user, _pw, path, timeout=15, *, with_etag=False):
        if with_etag and self.during:
            self.during()
        env = copy.deepcopy(self.files.get(path))
        if not with_etag:
            return env
        return (env, '"etag"') if env else (None, None)

    def upload(self, _url, _user, _pw, path, payload, timeout=15, *, etag=None):
        self.etags.append(etag)
        if self.conflicts:
            self.conflicts -= 1
            raise webdav.SyncConflict()
        self.puts.append(path)
        self.files[path] = json.loads(json.dumps(payload))

    def delete(self, _url, _user, _pw, path, timeout=15):
        if path in self.undeletable:
            return False
        self.files.pop(path, None)
        return True

    def sync(self, wd=None, **kwargs):
        with mock.patch.object(webdav, "download", self.download), \
             mock.patch.object(webdav, "upload", self.upload), \
             mock.patch.object(webdav, "delete", self.delete):
            return webdav.sync_once(wd or WD, **kwargs)

    def plain(self, passphrase=None):
        return sync_crypto.decrypt(self.files[V3], passphrase or WD["passphrase"])


def encrypted(data, passphrase=None):
    return sync_crypto.encrypt(data, passphrase or WD["passphrase"])


class SyncOnceTest(TempConfigTestCase):
    def test_counter_bump_during_sync_survives(self):
        config.save_all({"image_count": 10})
        dav = FakeDav({V3: encrypted({"image_count": 5})})
        dav.during = lambda: config.bump_image_count(1)
        dav.sync()
        self.assertEqual(config.get_counters()[0], 11)

    def test_settings_saved_during_sync_are_kept_then_pushed(self):
        config.save_all({"app_id": "A", "app_key": "OLD", "settings_modified_at": 100.0})
        dav = FakeDav({V3: encrypted({"app_id": "A", "app_key": "REMOTE",
                                      "settings_modified_at": 300.0})})
        dav.during = lambda: config.save_settings({"app_key": "NEW"})
        dav.sync()
        self.assertEqual(config.load_all()["app_key"], "NEW")
        dav.during = None
        dav.sync()
        self.assertEqual(dav.plain()["app_key"], "NEW")

    def test_unsynced_older_edit_beats_a_later_plain_sync(self):
        # Another device synced later but last *edited* at t=10; our edit at
        # t=200 is newer and must win.
        config.save_all({"app_id": "A", "app_key": "K", "image_price_usd": 0.003,
                         "settings_modified_at": 200.0})
        dav = FakeDav({V3: encrypted({"app_id": "A", "app_key": "K", "image_price_usd": 0.002,
                                      "settings_modified_at": 10.0})})
        dav.sync()
        self.assertEqual(config.get_image_price(), 0.003)
        self.assertEqual(dav.plain()["image_price_usd"], 0.003)
        self.assertEqual(dav.plain()["settings_modified_at"], 200.0)

    def test_empty_remote_uploads_local(self):
        config.save_all({"app_id": "A", "app_key": "K", "image_count": 4})
        dav = FakeDav()
        dav.sync()
        self.assertEqual(dav.plain()["app_key"], "K")
        self.assertEqual(dav.plain()["image_count"], 4)
        self.assertGreater(config.get_last_synced(), 0)


class EncryptionTest(TempConfigTestCase):
    def test_nothing_readable_reaches_the_server(self):
        config.save_all({"app_id": "MY-APP-ID", "app_key": "MY-APP-KEY",
                         "llm_api_key": "MY-LLM-KEY", "image_count": 123456,
                         "sync_passphrase": WD["passphrase"]})
        dav = FakeDav()
        dav.sync()
        wire = json.dumps(dav.files)
        for secret in ("MY-APP-ID", "MY-APP-KEY", "MY-LLM-KEY", "123456",
                       WD["passphrase"], "counter_state"):
            self.assertNotIn(secret, wire)
        self.assertEqual(dav.plain()["llm_api_key"], "MY-LLM-KEY")

    def test_passphrase_stays_out_of_the_sync_data(self):
        config.save_all({"sync_passphrase": "local secret"})
        self.assertNotIn("local secret", str(config.get_syncable_payload()))

    def test_every_upload_uses_a_fresh_salt_and_nonce(self):
        first, second = encrypted({"a": 1}), encrypted({"a": 1})
        self.assertNotEqual(first["ciphertext"], second["ciphertext"])
        self.assertNotEqual(first["salt"], second["salt"])

    def test_wrong_passphrase_changes_nothing(self):
        config.save_all({"app_key": "local"})
        original = encrypted({"app_key": "remote", "settings_modified_at": 9e9}, "the other one")
        dav = FakeDav({V3: original})
        with self.assertRaises(webdav.SyncPassphraseError):
            dav.sync()
        self.assertEqual(dav.files[V3], original)
        self.assertEqual(dav.puts, [])
        self.assertEqual(config.load_all()["app_key"], "local")
        self.assertEqual(config.get_last_synced(), 0)

    def test_tampered_or_malformed_files_are_refused(self):
        good = encrypted({"a": 1})
        cipher = base64.b64decode(good["ciphertext"])
        flipped = base64.b64encode(bytes([cipher[0] ^ 1]) + cipher[1:]).decode()
        for bad in ({**good, "ciphertext": flipped}, {**good, "nonce": "!!"},
                    {"version": 3}, {**good, "salt": 5}):
            with self.assertRaises(sync_crypto.SyncPassphraseError):
                sync_crypto.decrypt(bad, WD["passphrase"])

    def test_overwrite_replaces_what_cannot_be_decrypted(self):
        config.save_all({"app_id": "A", "app_key": "local"})
        dav = FakeDav({V3: encrypted({"app_key": "lost"}, "forgotten")})
        dav.sync(overwrite=True)
        self.assertEqual(dav.plain()["app_key"], "local")
        self.assertEqual(dav.etags, ['"etag"'])  # still refuses to race another writer

    def test_passphrase_is_required(self):
        dav = FakeDav()
        with self.assertRaisesRegex(RuntimeError, "口令"):
            dav.sync({**WD, "passphrase": ""})
        self.assertEqual(dav.files, {})

    def test_unknown_version_is_not_overwritten(self):
        dav = FakeDav({V3: {"version": 4, "ciphertext": "x"}})
        with self.assertRaisesRegex(RuntimeError, "版本"):
            dav.sync()
        self.assertEqual(dav.puts, [])

    def test_same_characters_derive_the_same_key_after_normalization(self):
        env = sync_crypto.encrypt({"a": 1}, "ｐａｓｓ１２３４")  # full-width input
        self.assertEqual(sync_crypto.decrypt(env, "pass1234"), {"a": 1})


class PlaintextMigrationTest(TempConfigTestCase):
    def test_old_files_are_merged_then_deleted(self):
        config.save_all({"image_count": 10})
        other = {"image_count": 0}
        counters.increment(other, "other", "image_count", 3)
        dav = FakeDav({V2: {"version": 2, "synced_at": 1, "data": other},
                       LEGACY: {"version": 1, "synced_at": 1, "data": {"image_count": 12}}})
        dav.sync()
        self.assertEqual(config.get_counters()[0], 15)
        self.assertEqual(set(dav.files), {V3})
        self.assertEqual(config.get_ui_state()["remote_plaintext_left"], [])

    def test_old_format_settings_fall_back_to_synced_at(self):
        config.save_all({"app_id": "A", "app_key": "K", "settings_modified_at": 200.0})
        dav = FakeDav({LEGACY: {"synced_at": 900, "data": {"app_id": "A", "app_key": "OLDFMT"}}})
        dav.sync()
        self.assertEqual(config.load_all()["app_key"], "OLDFMT")

    def test_old_files_survive_a_failed_upload(self):
        dav = FakeDav({LEGACY: {"data": {"image_count": 1}}})
        with mock.patch.object(dav, "upload", side_effect=RuntimeError("offline")):
            with self.assertRaises(RuntimeError):
                dav.sync()
        self.assertIn(LEGACY, dav.files)

    def test_undeletable_file_is_reported_and_retried(self):
        dav = FakeDav({LEGACY: {"data": {"image_count": 1}}})
        dav.undeletable = {LEGACY}
        dav.sync()
        self.assertEqual(config.get_ui_state()["remote_plaintext_left"], [LEGACY])
        dav.undeletable = set()
        dav.sync()
        self.assertEqual(config.get_ui_state()["remote_plaintext_left"], [])
        self.assertNotIn(LEGACY, dav.files)

    def test_v2_file_without_device_counts_is_not_trusted(self):
        dav = FakeDav({V2: {"version": 2, "data": {"image_count": 1}}})
        with self.assertRaisesRegex(RuntimeError, "设备计数"):
            dav.sync()
        self.assertEqual(dav.puts, [])

    def test_delete_treats_missing_as_gone_and_errors_as_not(self):
        for status, expected in ((204, True), (404, True), (403, False)):
            with mock.patch.object(webdav.requests, "delete",
                                   return_value=mock.Mock(status_code=status)):
                self.assertEqual(webdav.delete("https://e", "u", "p", "/s"), expected)


if __name__ == "__main__":
    unittest.main()
