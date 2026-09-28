"""PdfWorker billing: every submitted job reports its billable pages once,
before finished_ok / failed, whatever the outcome."""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import requests

import pdf_client

PROCESSING = {"status": "split", "percent_done": 20, "num_pages": 50,
              "num_pages_completed": 10}
COMPLETED = {"status": "completed", "percent_done": 100, "num_pages": 50,
             "num_pages_completed": 50}


class PdfWorkerBillingTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.out = Path(tmp.name)

    def run_worker(self, statuses, *, page_ranges=None, cancel_after=None,
                   download_error=None, submit_error=None, stall_s=None):
        polls = {"n": 0}

        def get_status(*_a, **_k):
            i = min(polls["n"], len(statuses) - 1)
            polls["n"] += 1
            return statuses[i]

        def submit(*_a, **_k):
            if submit_error:
                raise submit_error
            return "pdf123"

        def download(*_a, **_k):
            if download_error:
                raise download_error

        w = pdf_client.PdfWorker(
            Path("x.pdf"),
            pdf_client.PdfOptions(formats=("mmd",), page_ranges=page_ranges),
            self.out, "id", "key")
        w.POLL_INTERVAL_S = 0
        if stall_s is not None:
            w.STALL_TIMEOUT_S = stall_s
        if cancel_after is not None:
            w.isInterruptionRequested = lambda: polls["n"] >= cancel_after
        events = []
        w.billed.connect(lambda n: events.append(("billed", n)))
        w.finished_ok.connect(lambda paths: events.append(("ok", len(paths))))
        w.failed.connect(lambda msg: events.append(("failed", msg)))
        with mock.patch.object(pdf_client, "submit_file", submit), \
                mock.patch.object(pdf_client, "get_status", get_status), \
                mock.patch.object(pdf_client, "download", download):
            w.run()
        return events

    def test_completed(self):
        self.assertEqual(self.run_worker([PROCESSING, COMPLETED]),
                         [("billed", 50), ("ok", 1)])

    def test_cancel_bills_whole_document(self):
        ev = self.run_worker([PROCESSING], cancel_after=1)
        self.assertEqual(ev[0], ("billed", 50))
        self.assertEqual(ev[1][0], "failed")

    def test_cancel_with_page_range_bills_pages_done(self):
        ev = self.run_worker([PROCESSING], cancel_after=1, page_ranges="1-3")
        self.assertEqual(ev[0], ("billed", 10))

    def test_download_failure_still_bills(self):
        ev = self.run_worker([PROCESSING, COMPLETED],
                             download_error=requests.ConnectionError("x"))
        self.assertEqual(ev[0], ("billed", 50))
        self.assertEqual(ev[1][0], "failed")

    def test_server_error_bills_pages_done(self):
        ev = self.run_worker(
            [PROCESSING, {"status": "error", "num_pages_completed": 10}])
        self.assertEqual(ev[0], ("billed", 10))
        self.assertEqual(ev[1][0], "failed")

    def test_stall_timeout(self):
        ev = self.run_worker([PROCESSING], stall_s=0.05)
        self.assertEqual(ev[0], ("billed", 50))
        self.assertIn("No progress", ev[1][1])

    def test_rejected_upload_is_not_billed(self):
        ev = self.run_worker([COMPLETED],
                             submit_error=requests.ConnectionError("x"))
        self.assertEqual([e[0] for e in ev], ["failed"])


if __name__ == "__main__":
    unittest.main()
