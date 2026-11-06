"""Regression tests for source protection, interrupted downloads and UI state."""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import requests
from PyQt6.QtWidgets import QApplication, QMessageBox

import pdf_client
from pdf_panel import PdfPanel
from pdf_jobs import PdfJobStore


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


class PdfPanelSafetyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.panel = PdfPanel(lambda: {"app_id": "id", "app_key": "key"},
                              job_store=PdfJobStore(Path(tmp.name) / "jobs.db"))
        self.addCleanup(self.panel.deleteLater)

    def test_empty_custom_range_does_not_start_whole_document(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "paper.pdf"
            path.write_bytes(b"test")
            self.panel._pdf_path = path
            self.panel.range_combo.setCurrentIndex(1)
            with mock.patch("pdf_panel.PdfWorker") as worker, \
                 mock.patch.object(QMessageBox, "warning") as warning:
                self.panel._start()
            worker.assert_not_called()
            warning.assert_called_once()

    def test_completion_opens_actual_output_directory(self):
        self.panel.out_edit.setText("changed-after-start")
        with mock.patch.object(QMessageBox, "information"), \
             mock.patch("pdf_panel.os.startfile", create=True) as open_folder:
            self.panel._on_done([Path("actual-output/paper.mmd")])
        open_folder.assert_called_once_with(Path("actual-output"))

    def test_cleanup_releases_parented_worker(self):
        worker = mock.Mock()
        self.panel._worker = worker
        self.panel._cleanup_worker()
        worker.deleteLater.assert_called_once()
        self.assertIsNone(self.panel._worker)


if __name__ == "__main__":
    unittest.main()
