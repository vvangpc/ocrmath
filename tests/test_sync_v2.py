import copy
import json
from unittest import mock

import config
import counters
import webdav
from tests.helpers import TempConfigTestCase
from tests.test_webdav import WD


class CounterV2Test(TempConfigTestCase):
    def test_offline_devices_merge_without_loss_or_double_count(self):
        a = {"image_count": 10, "pdf_page_count": 20}
        b = copy.deepcopy(a)
        counters.increment(a, "A", "image_count", 2)
        counters.increment(b, "B", "image_count", 3)
        counters.increment(a, "A", "pdf_page_count", 4)
        counters.increment(b, "B", "pdf_page_count", 5)
        merged = counters.merge(a, b)
        self.assertEqual((merged["image_count"], merged["pdf_page_count"]), (15, 29))
        self.assertEqual(counters.merge(merged, b), merged)
        self.assertEqual(counters.merge(b, a), merged)
        counters.increment(b, "B", "image_count", 1)
        self.assertEqual(counters.merge(merged, b)["image_count"], 16)

    def test_migration_and_identity_survive_reload(self):
        config.save_all({"image_count": 10})
        config.bump_image_count(2)
        first = config.get_syncable_payload()
        device = config.load_all()["device_id"]
        self._reset_caches()
        config.bump_image_count(3)
        self.assertEqual(config.load_all()["device_id"], device)
        merged = counters.merge(first, config.get_syncable_payload())
        self.assertEqual(merged["image_count"], 15)
        self.assertNotIn("device_id", first)

    def test_mid_sync_increment_and_remote_increment_both_survive(self):
        config.save_all({"image_count": 10})
        local = config.get_syncable_payload()
        remote = copy.deepcopy(local)
        counters.increment(remote, "other", "image_count", 3)
        config.bump_image_count(2)
        config.apply_synced_payload(counters.merge(local, remote), 10, 0)
        self.assertEqual(config.get_counters()[0], 15)

    def test_nested_config_cache_cannot_be_mutated_by_reader(self):
        config.bump_image_count()
        snapshot = config.load_all()
        snapshot["counter_state"]["devices"].clear()
        self.assertEqual(config.load_all()["image_count"], 1)
        self.assertTrue(config.load_all()["counter_state"]["devices"])

    def test_pdf_pages_are_idempotent_and_incremental(self):
        self.assertEqual(config.record_pdf_pages("job", 5), 5)
        self._reset_caches()
        self.assertEqual(config.record_pdf_pages("job", 5), 0)
        self.assertEqual(config.record_pdf_pages("job", 3), 0)
        self.assertEqual(config.record_pdf_pages("job", 8), 3)
        self.assertEqual(config.get_counters()[1], 8)

    def test_conditional_conflict_reloads_and_merges(self):
        config.bump_image_count(2)
        other = {"image_count": 0}
        counters.increment(other, "other", "image_count", 3)
        env = {"version": 2, "data": other}
        with mock.patch.object(webdav, "download", side_effect=[(None, None), None, (env, '"new"')]), \
             mock.patch.object(webdav, "upload", side_effect=[webdav.SyncConflict(), None]) as put:
            webdav.sync_once(WD)
        self.assertEqual(config.get_counters()[0], 5)
        self.assertEqual(put.call_args.kwargs["etag"], '"new"')
        self.assertEqual(put.call_args.args[3], "/ocrmath/sync.v2.json")
        self.assertEqual(put.call_args.args[4]["data"]["image_count"], 5)

    def test_failed_upload_does_not_mark_synced(self):
        with mock.patch.object(webdav, "download", return_value=(None, None)) as get, \
             mock.patch.object(webdav, "upload", side_effect=RuntimeError("offline")):
            get.side_effect = [(None, None), None]
            with self.assertRaises(RuntimeError):
                webdav.sync_once(WD)
        self.assertEqual(config.get_last_synced(), 0)

    def test_conflict_retries_are_bounded(self):
        env = {"version": 2, "data": counters.fields(counters.state({}))}
        with mock.patch.object(webdav, "download", return_value=(env, '"etag"')), \
             mock.patch.object(webdav, "upload", side_effect=webdav.SyncConflict()) as put:
            with self.assertRaisesRegex(RuntimeError, "连续"):
                webdav.sync_once(WD)
        self.assertEqual(put.call_count, 4)

    def test_legacy_remote_import_keeps_old_file_untouched(self):
        config.save_all({"image_count": 10})
        old = {"version": 1, "data": {"image_count": 12}}
        with mock.patch.object(webdav, "download", side_effect=[(None, None), old]), \
             mock.patch.object(webdav, "upload") as put:
            webdav.sync_once(WD)
        self.assertEqual(config.get_counters()[0], 12)
        self.assertEqual(put.call_args.args[3], "/ocrmath/sync.v2.json")

    def test_put_uses_conditions_and_reports_conflicts(self):
        response = mock.Mock(status_code=204)
        with mock.patch.object(webdav.requests, "put", return_value=response) as put:
            webdav.upload("https://example", "u", "p", "/sync", {}, etag='"1"')
            self.assertEqual(put.call_args.kwargs["headers"]["If-Match"], '"1"')
            webdav.upload("https://example", "u", "p", "/sync", {})
            self.assertEqual(put.call_args.kwargs["headers"]["If-None-Match"], "*")
            response.status_code = 412
            with self.assertRaises(webdav.SyncConflict):
                webdav.upload("https://example", "u", "p", "/sync", {})

    def test_download_requires_etag_and_valid_envelope(self):
        response = mock.Mock(status_code=200, headers={}, content=b'{"data": {}}')
        with mock.patch.object(webdav.requests, "get", return_value=response):
            with self.assertRaisesRegex(RuntimeError, "ETag"):
                webdav.download("https://example", "u", "p", "/s", with_etag=True)
            response.headers = {"ETag": '"1"'}
            env, etag = webdav.download("https://example", "u", "p", "/s", with_etag=True)
            self.assertEqual((env, etag), ({"data": {}}, '"1"'))
            response.content = b'[]'
            with self.assertRaises(RuntimeError):
                webdav.download("https://example", "u", "p", "/s", with_etag=True)
