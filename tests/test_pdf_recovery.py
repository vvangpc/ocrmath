from dataclasses import asdict
from pathlib import Path
import tempfile
import unittest
import time
from unittest import mock

import requests

from ocrmath.ocr import pdf_client
from ocrmath.ocr.pdf_jobs import PdfJobStore
from ocrmath.core.storage import Storage
from ocrmath.core import config
from tests.helpers import TempConfigTestCase
from PyQt6.QtWidgets import QApplication
from ocrmath.ocr.pdf_service import PdfService
from ocrmath.core.utils import UserError


class PdfRecoveryTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.store = PdfJobStore(self.root / "jobs.db")
        self.options = pdf_client.PdfOptions(formats=("mmd", "docx"))
        self.job = self.store.create(self.root / "source.pdf", asdict(self.options),
                                     self.root / "out", "id", 3)

    def worker(self):
        job = self.store.get(self.job["id"])
        worker = pdf_client.PdfWorker(Path(job["source"]), self.options,
                    Path(job["out_dir"]), "id", "secret",
                    job_store=PdfJobStore(self.store.path), job=job)
        worker.POLL_INTERVAL_S = 0
        return worker

    def run_worker(self, worker, transfer):
        result = []
        worker.finished_ok.connect(lambda paths: result.append(paths))
        worker.failed.connect(lambda message: result.append(message))
        status = {"status": "completed", "num_pages": 3, "num_pages_completed": 3}
        with mock.patch.object(pdf_client, "submit_file", return_value="server-id") as submit, \
             mock.patch.object(pdf_client, "get_status", return_value=status), \
             mock.patch.object(pdf_client, "download", side_effect=transfer):
            worker.run()
        return result, submit.call_count

    def test_partial_failure_reopens_store_and_downloads_only_missing_format(self):
        seen = []
        def first(job_id, ext, dest, *_a, **_kw):
            # Server ID is durable before even the first download.
            self.assertEqual(self.store.get(self.job["id"])["pdf_id"], "server-id")
            if ext == "docx":
                raise requests.ConnectionError("offline")
            dest.write_bytes(b"markdown")
        result, uploads = self.run_worker(self.worker(), first)
        self.assertEqual(uploads, 1)
        self.assertIsInstance(result[0], str)
        self.assertEqual(self.store.get(self.job["id"])["status"], "可重试")
        def second(job_id, ext, dest, *_a, **_kw):
            seen.append(ext)
            dest.write_bytes(b"word document")
        result, uploads = self.run_worker(self.worker(), second)
        self.assertEqual(uploads, 0)
        self.assertEqual(seen, ["docx"])
        self.assertEqual(len(result[0]), 2)
        job = self.store.get(self.job["id"])
        self.assertEqual(job["status"], "已完成")
        self.assertEqual(job["pages"], 3)
        self.assertNotIn("secret", str(job))

    def test_modified_export_is_preserved_and_redownloaded(self):
        def transfer(_job, ext, dest, *_a, **_kw):
            dest.write_bytes(ext.encode())
        self.run_worker(self.worker(), transfer)
        job = self.store.get(self.job["id"])
        original = Path(job["files"]["mmd"]["path"])
        original.write_bytes(b"user edit")
        seen = []
        def retry(job_id, ext, dest, *_a, **_kw):
            seen.append(ext)
            dest.write_bytes(ext.encode())
        result, uploads = self.run_worker(self.worker(), retry)
        self.assertEqual(uploads, 0)
        self.assertEqual(seen, ["mmd"])
        self.assertEqual(original.read_bytes(), b"user edit")
        self.assertNotEqual(result[0][0], original)

    def test_not_ready_is_retried_without_publishing_json(self):
        self.options.formats = ("mmd",)
        attempts = []
        def transfer(_job, ext, dest, *_a, **_kw):
            attempts.append(ext)
            if len(attempts) == 1:
                raise pdf_client._NotReady()
            dest.write_bytes(b"ready")
        result, uploads = self.run_worker(self.worker(), transfer)
        self.assertEqual(attempts, ["mmd", "mmd"])
        self.assertEqual(uploads, 1)
        self.assertEqual(result[0][0].read_bytes(), b"ready")

    def test_202_download_leaves_destination_untouched(self):
        response = mock.MagicMock(status_code=202)
        response.__enter__.return_value = response
        dest = self.root / "result.docx"
        with mock.patch.object(pdf_client._SESSION, "get", return_value=response):
            with self.assertRaises(pdf_client._NotReady):
                pdf_client.download("id", "docx", dest, "id", "key")
        self.assertFalse(dest.exists())

    def test_expired_job_fails_without_upload(self):
        self.job["pdf_id"] = "expired"
        self.store.save(self.job)
        worker = self.worker()
        response = requests.Response()
        response.status_code = 404
        with mock.patch.object(pdf_client, "submit_file") as submit, \
             mock.patch.object(pdf_client, "get_status", side_effect=requests.HTTPError(response=response)):
            worker.run()
        submit.assert_not_called()
        self.assertIn("已过期", self.store.get(self.job["id"])["error"])

    def test_usage_is_idempotent_after_reopen_and_price_change(self):
        base = self.root / "storage"
        storage = Storage(base)
        storage.log_pdf_usage("job", 3, .01)
        storage.close()
        storage = Storage(base)
        self.addCleanup(storage.close)
        storage.log_pdf_usage("job", 3, .02)
        storage.log_pdf_usage("job", 5, .02)
        summary = storage.usage_summary(0)
        self.assertEqual(summary["pdf_pages"], 5)
        self.assertAlmostEqual(summary["total_cost"], .05)


class PdfRecoveryServiceTest(TempConfigTestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_real_worker_restart_skips_upload_and_deduplicates_billing(self):
        root = config.CONFIG_PATH.parent
        store = PdfJobStore(root / "jobs.db")
        storage = Storage(root / "data")
        self.addCleanup(storage.close)
        source = root / "paper.pdf"
        source.write_bytes(b"fake PDF")
        def service():
            s = PdfService(lambda: {"app_id": "id", "app_key": "key"},
                           lambda n, job: storage.log_pdf_usage(job, n, .005), job_store=store)
            self.addCleanup(s.deleteLater)
            return s
        def wait(s):
            deadline = time.monotonic() + 5
            while s._worker is not None and time.monotonic() < deadline:
                self.app.processEvents()
                time.sleep(.005)
            self.assertIsNone(s._worker)
        first = service()
        seen = []
        fail = [True]
        def transfer(_id, ext, dest, *_a, **_kw):
            seen.append(ext)
            if fail[0] and ext == "docx":
                raise requests.ConnectionError("offline")
            dest.write_bytes(ext.encode())
        params = {"path": str(source), "provider": "mathpix", "formats": ["mmd", "docx"],
                  "page_ranges": "", "out_dir": str(root / "out")}
        with mock.patch.object(pdf_client.PdfWorker, "POLL_INTERVAL_S", 0), \
             mock.patch.object(pdf_client, "submit_file", return_value="server-id") as submit, \
             mock.patch.object(pdf_client, "get_status", return_value={
                 "status": "completed", "num_pages": 2, "num_pages_completed": 2}), \
             mock.patch.object(pdf_client, "download", side_effect=transfer), \
             mock.patch("ocrmath.ocr.pdf_service.os.startfile", create=True):
            self.assertIn("confirm", first.start(params))  # page count unreadable
            first.start(params, confirmed=True)
            wait(first)
            self.assertEqual(config.get_counters()[1], 2)
            source.unlink()  # Recovery must not require the original file.
            second = service()
            fail[0] = False
            second.resume(store.recent()[0]["id"])
            wait(second)
        self.assertEqual(submit.call_count, 1)
        self.assertEqual(seen, ["mmd", "docx", "docx"])
        self.assertEqual(config.get_counters()[1], 2)
        self.assertEqual(storage.usage_summary(0)["pdf_pages"], 2)

    def test_missing_server_id_cannot_silently_resubmit(self):
        store = PdfJobStore(config.CONFIG_PATH.parent / "jobs.db")
        job = store.create(Path("missing.pdf"), asdict(pdf_client.PdfOptions()), Path("out"), "id")
        service = PdfService(lambda: {"app_id": "id", "app_key": "key"}, job_store=store)
        self.addCleanup(service.deleteLater)
        self.assertFalse(service.state()["jobs"][0]["can_resume"])
        with mock.patch("ocrmath.ocr.pdf_service.PdfWorker") as worker, self.assertRaises(UserError):
            service.resume(job["id"])
        worker.assert_not_called()
