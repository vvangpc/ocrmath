"""Regression tests for source protection, interrupted downloads and UI state."""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import requests
from PyQt6.QtWidgets import QApplication
from pypdf import PdfWriter

from ocrmath.core import config
from ocrmath.ocr import pdf_client
from ocrmath.ocr.pdf_service import PdfService
from ocrmath.ocr.pdf_jobs import PdfJobStore
from tests.helpers import TempConfigTestCase
from ocrmath.core.utils import UserError


class DownloadSafetyTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.dest = self.root / "result.mmd"
        self.dest.write_bytes(b"previous result")

    def transfer(self, chunks, check_cancel=None):
        response = mock.MagicMock()
        response.__enter__.return_value = response
        response.iter_content.return_value = chunks
        with mock.patch.object(pdf_client._SESSION, "get", return_value=response):
            pdf_client.download("job", "mmd", self.dest, "id", "key",
                                check_cancel=check_cancel)

    def assert_original_preserved(self):
        self.assertEqual(self.dest.read_bytes(), b"previous result")
        self.assertEqual(list(self.root.iterdir()), [self.dest])

    def test_network_failure_preserves_previous_file_and_cleans_partial(self):
        def chunks():
            yield b"partial"
            raise requests.ConnectionError("connection lost")
        with self.assertRaises(requests.ConnectionError):
            self.transfer(chunks())
        self.assert_original_preserved()

    def test_cancel_preserves_previous_file_and_cleans_partial(self):
        cancel = mock.Mock(side_effect=[None, pdf_client._JobFailed("cancel")])
        with self.assertRaises(pdf_client._JobFailed):
            self.transfer([b"first", b"second"], cancel)
        self.assert_original_preserved()

    def test_timeout_preserves_previous_file(self):
        with mock.patch.object(pdf_client, "DOWNLOAD_TOTAL_TIMEOUT_S", -1):
            with self.assertRaises(requests.Timeout):
                self.transfer([b"partial"])
        self.assert_original_preserved()

    def test_success_publishes_complete_file(self):
        self.transfer([b"first", b"", b"second"])
        self.assertEqual(self.dest.read_bytes(), b"firstsecond")
        self.assertEqual(list(self.root.iterdir()), [self.dest])

    def test_worker_preserves_source_and_existing_exports(self):
        source = self.root / "paper.pdf"
        source.write_bytes(b"original PDF")
        existing = self.root / "paper_ocr.pdf"
        existing.write_bytes(b"previous PDF")
        archive = self.root / "paper.tex.zip"
        archive.write_bytes(b"previous archive")
        worker = pdf_client.PdfWorker(source,
            pdf_client.PdfOptions(formats=("pdf", "tex.zip")), self.root, "id", "key")
        worker.POLL_INTERVAL_S = 0
        def download(_job, _ext, dest, *_args, **_kwargs):
            dest.write_bytes(b"new export")
        with mock.patch.object(pdf_client, "submit_file", return_value="job"), \
             mock.patch.object(pdf_client, "get_status", return_value={"status": "completed"}), \
             mock.patch.object(pdf_client, "download", side_effect=download):
            saved = worker._do_run()
        self.assertEqual([p.name for p in saved],
                         ["paper_ocr (1).pdf", "paper (1).tex.zip"])
        self.assertEqual(source.read_bytes(), b"original PDF")
        self.assertEqual(existing.read_bytes(), b"previous PDF")
        self.assertEqual(archive.read_bytes(), b"previous archive")

    def test_cancel_before_start_does_not_upload_or_bill(self):
        worker = pdf_client.PdfWorker(self.root / "paper.pdf",
            pdf_client.PdfOptions(), self.root, "id", "key")
        worker.isInterruptionRequested = lambda: True
        billed = mock.Mock()
        worker.billed.connect(billed)
        with mock.patch.object(pdf_client, "submit_file") as submit:
            worker.run()
        submit.assert_not_called()
        billed.assert_not_called()


class PdfServiceSafetyTest(TempConfigTestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        super().setUp()
        self.root = config.CONFIG_PATH.parent
        self.service = PdfService(lambda: {"app_id": "id", "app_key": "key"},
                                  job_store=PdfJobStore(self.root / "jobs.db"))
        self.addCleanup(self.service.deleteLater)
        self.path = self.root / "paper.pdf"
        writer = PdfWriter()
        for _ in range(3):
            writer.add_blank_page(100, 100)
        writer.write(self.path)
        self.params = {"path": str(self.path), "provider": "mathpix", "formats": ["mmd"],
                       "page_ranges": "", "out_dir": str(self.root / "out")}

    def test_invalid_range_does_not_start_anything(self):
        for value in ("9", "2-1", "a"):
            with mock.patch("ocrmath.ocr.pdf_service.PdfWorker") as worker, self.assertRaises(UserError):
                self.service.start({**self.params, "page_ranges": value})
            worker.assert_not_called()
        self.assertEqual(self.service.jobs.recent(), [])

    def test_no_format_or_unknown_format_is_refused(self):
        for formats in ([], ["exe"]):
            with self.assertRaises(UserError):
                self.service.start({**self.params, "formats": formats})

    def test_large_job_asks_first_and_creates_nothing_until_confirmed(self):
        with mock.patch("ocrmath.ocr.pdf_service.count_pdf_pages", return_value=101), \
             mock.patch("ocrmath.ocr.pdf_service.PdfWorker") as worker:
            reply = self.service.start(self.params)
            self.assertIn("101", reply["confirm"])
            worker.assert_not_called()
            self.assertEqual(self.service.jobs.recent(), [])

    def test_estimate_honors_the_page_range(self):
        whole = self.service.estimate(str(self.path), "mathpix")
        part = self.service.estimate(str(self.path), "mathpix", "1")
        self.assertIn("0.015", whole)
        self.assertIn("0.005", part)
        self.assertIn("Token", self.service.estimate(str(self.path), "llm", "1"))

    def test_inspect_defaults_output_next_to_the_file_and_refuses_others(self):
        info = self.service.inspect(str(self.path))
        self.assertEqual((info["pages"], info["out_dir"]), (3, str(self.root)))
        with self.assertRaises(UserError):
            self.service.inspect(str(self.root / "note.txt"))

    def test_options_are_remembered_only_once_a_job_really_starts(self):
        chosen = self.root / "chosen"
        params = {**self.params, "formats": ["docx"], "rm_spaces": False, "out_dir": str(chosen)}
        with self.assertRaises(UserError):
            self.service.start({**params, "page_ranges": "9"})
        self.assertIsNone(self.service.inspect(str(self.path))["formats"])
        with mock.patch("ocrmath.ocr.pdf_service.PdfWorker"), mock.patch.object(self.service, "_launch"):
            self.service.start(params)
        self.service._worker = None
        info = self.service.inspect(str(self.path))
        self.assertEqual((info["formats"], info["rm_spaces"], info["out_dir"]),
                         (["docx"], False, str(chosen)))

    def test_default_folder_is_not_remembered_and_a_missing_one_is_ignored(self):
        with mock.patch("ocrmath.ocr.pdf_service.PdfWorker"), mock.patch.object(self.service, "_launch"):
            self.service.start({**self.params, "out_dir": str(self.root)})
        self.assertIsNone(config.get_ui_state()["pdf_out_dir"])
        config.update_ui_state(pdf_out_dir=str(self.root / "gone"))
        self.assertEqual(self.service.inspect(str(self.path))["out_dir"], str(self.root))

    def test_completion_opens_actual_output_directory(self):
        with mock.patch("ocrmath.ocr.pdf_service.os.startfile", create=True) as open_folder:
            self.service._on_done([Path("actual-output/paper.mmd")])
        open_folder.assert_called_once_with(Path("actual-output"))

    def test_cleanup_releases_parented_worker(self):
        worker = mock.Mock()
        self.service._worker = worker
        self.service._cleanup_worker()
        worker.deleteLater.assert_called_once()
        self.assertIsNone(self.service._worker)

    def test_job_left_running_by_a_closed_app_reads_as_interrupted(self):
        job = self.service.jobs.create(self.path, {"formats": ["mmd"]}, self.root, "id")
        job.update(pdf_id="server", status="处理中")
        self.service.jobs.save(job)
        view = self.service.state()["jobs"][0]
        self.assertEqual(view["status"], "已中断")
        self.assertTrue(view["can_resume"])
        self.assertFalse(view["running"])


if __name__ == "__main__":
    unittest.main()
