import copy
from unittest import mock

from ocrmath.core import config
from ocrmath.core import counters
from ocrmath.core import webdav
from tests.helpers import TempConfigTestCase
from tests.test_webdav import FakeDav, V3, encrypted


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
        dav = FakeDav()
        dav.conflicts = 1
        reads = []
        def another_device_writes():
            reads.append(1)
            if len(reads) == 2:
                dav.files[V3] = encrypted(other)
        dav.during = another_device_writes
        dav.sync()
        self.assertEqual(config.get_counters()[0], 5)
        self.assertEqual(dav.etags, [None, '"etag"'])
        self.assertEqual(dav.puts, [V3])
        self.assertEqual(dav.plain()["image_count"], 5)

    def test_failed_upload_does_not_mark_synced(self):
        dav = FakeDav()
        with mock.patch.object(dav, "upload", side_effect=RuntimeError("offline")):
            with self.assertRaises(RuntimeError):
                dav.sync()
        self.assertEqual(config.get_last_synced(), 0)

    def test_conflict_retries_are_bounded(self):
        dav = FakeDav({V3: encrypted(counters.fields(counters.state({})))})
        dav.conflicts = 99
        with self.assertRaisesRegex(RuntimeError, "连续"):
            dav.sync()
        self.assertEqual(len(dav.etags), 4)

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
