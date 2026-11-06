from pathlib import Path
import unittest
import time
from unittest import mock

from PyQt6.QtWidgets import QApplication
from pypdf import PdfWriter

from ocrmath.core import config
from ocrmath.core import webdav
from ocrmath.ocr import llm_client
from ocrmath.ocr.llm_client import transcribe, cache_key
from ocrmath.ocr.llm_store import LlmStore
from ocrmath.ocr.llm_pdf import LlmPdfWorker, selected_pages
from ocrmath.ocr.pdf_jobs import PdfJobStore
from ocrmath.ocr.pdf_service import PdfService
from ocrmath.core.storage import Storage
from tests.helpers import TempConfigTestCase

SETTINGS = {"api_key": "test-secret", "model": "gpt-6-luna", "base_url": "https://api.openai.com/v1"}


def response(text="$$x^2$$", *, id="resp-1", status="completed"):
    return {"id": id, "model": "gpt-6-luna", "status": status,
            "output": [{"type": "message", "content": [{"type": "output_text", "text": text}]}],
            "usage": {"input_tokens": 100, "output_tokens": 20,
                      "input_tokens_details": {"cached_tokens": 30}}}


def http(body=None, status=200):
    result = mock.Mock(status_code=status)
    result.json.return_value = body or response()
    return result


class LlmApiTest(TempConfigTestCase):
    def setUp(self):
        super().setUp()
        self.ledger = LlmStore(config.CONFIG_PATH.parent / "tokens.db")

    def test_image_request_schema_and_usage(self):
        with mock.patch.object(llm_client.requests, "post", return_value=http()) as post:
            result = transcribe(b"PNG", SETTINGS, "image", self.ledger)
        payload = post.call_args.kwargs["json"]
        self.assertEqual(post.call_args.args[0], SETTINGS["base_url"] + "/responses")
        self.assertEqual(payload["model"], "gpt-6-luna")
        self.assertFalse(payload["store"])
        self.assertEqual(payload["input"][0]["content"][0]["type"], "input_image")
        self.assertEqual(result["latex_styled"], "x^2")
        row = self.ledger.summary()[0]
        self.assertEqual((row["input_tokens"], row["cached_tokens"], row["output_tokens"]), (100, 30, 20))

    def test_pdf_request_uses_file_input_and_future_model(self):
        settings = {**SETTINGS, "model": "future-vision-model"}
        with mock.patch.object(llm_client.requests, "post", return_value=http()) as post:
            transcribe(b"PDF", settings, "pdf_page", self.ledger)
        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["model"], "future-vision-model")
        item = payload["input"][0]["content"][0]
        self.assertEqual(item["type"], "input_file")
        self.assertTrue(item["file_data"].startswith("data:application/pdf;base64,"))

    def test_incomplete_and_refusal_are_not_accepted_but_usage_is_recorded(self):
        incomplete = response(status="incomplete")
        refusal = response(id="resp-2")
        refusal["output"][0]["content"] = [{"type": "refusal", "refusal": "No"}]
        for body in (incomplete, refusal):
            with mock.patch.object(llm_client.requests, "post", return_value=http(body)):
                with self.assertRaises(RuntimeError):
                    transcribe(b"PNG", SETTINGS, "image", self.ledger)
        self.assertEqual(self.ledger.summary()[0]["requests"], 2)
        self.assertEqual(self.ledger.summary()[0]["input_tokens"], 200)

    def test_http_errors_do_not_leak_key_or_retry(self):
        with mock.patch.object(llm_client.requests, "post", return_value=http(status=401)) as post:
            with self.assertRaises(RuntimeError) as error:
                transcribe(b"PNG", SETTINGS, "image", self.ledger)
        self.assertNotIn(SETTINGS["api_key"], str(error.exception))
        self.assertEqual(post.call_count, 1)

    def test_usage_dedup_and_missing_usage(self):
        for _ in range(2):
            with mock.patch.object(llm_client.requests, "post", return_value=http()):
                transcribe(b"PNG", SETTINGS, "image", self.ledger)
        self.ledger.record("unknown", "other", "image", None)
        rows = {r["model"]: r for r in self.ledger.summary()}
        self.assertEqual(rows["gpt-6-luna"]["requests"], 1)
        self.assertEqual(rows["other"]["unknown"], 1)
        self.assertEqual(self.ledger.summary(10**12), [])

    def test_cache_separates_model_endpoint_and_workload_not_api_key(self):
        key = cache_key(b"same", SETTINGS, "image")
        self.assertEqual(key, cache_key(b"same", {**SETTINGS, "api_key": "rotated"}, "image"))
        self.assertNotEqual(key, cache_key(b"same", {**SETTINGS, "model": "new"}, "image"))
        self.assertNotEqual(key, cache_key(b"same", {**SETTINGS, "base_url": "https://other/v1"}, "image"))
        self.assertNotEqual(key, cache_key(b"same", SETTINGS, "pdf_page"))

    def test_credentials_roundtrip_and_travel_through_webdav(self):
        config.save_settings({"image_provider": "llm", "pdf_provider": "llm",
                              "llm_api_key": "test-secret", "llm_model": "future-model",
                              "llm_base_url": "https://example.org/v1"})
        self._reset_caches()
        self.assertTrue(config.has_image_credentials())
        self.assertEqual(config.get_llm()["model"], "future-model")
        payload = config.get_syncable_payload()
        self.assertEqual(payload["llm_api_key"], "test-secret")
        self.assertEqual(payload["llm_model"], "future-model")

    def test_llm_only_settings_do_not_erase_other_devices_mathpix_credentials(self):
        config.save_settings({"app_id": "", "app_key": "", "llm_api_key": "secret"})
        payload = config.get_syncable_payload()
        merged = webdav.merge(payload, 200, {"app_id": "remote-id", "app_key": "remote-key"}, 100)
        self.assertEqual(merged["app_id"], "remote-id")
        self.assertEqual(merged["app_key"], "remote-key")

    def test_endpoint_validation(self):
        for url in ("https://api.openai.com/v1", "http://127.0.0.1:1234/v1"):
            self.assertEqual(llm_client.validate_endpoint(url), url)
        for url in ("ftp://host", "http://remote/v1", "https://u:p@host/v1", "https://host/v1?key=x"):
            with self.assertRaises(ValueError):
                llm_client.validate_endpoint(url)

    def test_mathpix_backfill_excludes_llm_recognitions(self):
        storage = Storage(config.CONFIG_PATH.parent / "history")
        self.addCleanup(storage.close)
        storage.insert("a" * 64, b"png", {"text": "x", "_provider": "llm"})
        storage.insert("b" * 64, b"png", {"text": "y"})
        self.assertEqual(storage.backfill_image_usage(.002), 1)


class LlmPdfTest(TempConfigTestCase):
    def setUp(self):
        super().setUp()
        root = config.CONFIG_PATH.parent
        self.source = root / "source.pdf"
        writer = PdfWriter()
        writer.add_blank_page(200, 300)
        writer.add_blank_page(250, 350)
        writer.write(self.source)
        self.store = PdfJobStore(root / "jobs.db")
        self.ledger = LlmStore(root / "tokens.db")
        self.job = self.store.create_llm(self.source, {"page_ranges": None}, root / "out", SETTINGS)

    def worker(self):
        return LlmPdfWorker(self.store, self.store.get(self.job["id"]), SETTINGS, usage_store=self.ledger)

    def test_partial_failure_then_resume_without_source_or_rebilling_page_one(self):
        with mock.patch.object(llm_client.requests, "post", side_effect=[http(response("one")), http(status=500)]):
            self.worker().run()
        job = self.store.get(self.job["id"])
        self.assertEqual(job["page_results"], {"1": "one"})
        self.assertEqual(job["status"], "可重试")
        self.source.unlink()
        with mock.patch.object(llm_client.requests, "post", return_value=http(response("two", id="resp-2"))) as post:
            self.worker().run()
        self.assertEqual(post.call_count, 1)
        job = self.store.get(self.job["id"])
        self.assertEqual(job["status"], "已完成")
        output = Path(job["files"]["md"]["path"])
        self.assertLess(output.read_text().find("one"), output.read_text().find("two"))
        self.assertEqual(self.ledger.summary()[0]["requests"], 2)
        self.assertNotIn(SETTINGS["api_key"], str(job))
        output.unlink()
        Path(job["source_snapshot"]).unlink()
        with mock.patch.object(llm_client.requests, "post") as post:
            self.worker().run()
        post.assert_not_called()
        self.assertTrue(Path(self.store.get(self.job["id"])["files"]["md"]["path"]).is_file())

    def test_new_job_reuses_page_cache_and_separate_model_does_not(self):
        with mock.patch.object(llm_client.requests, "post", side_effect=[http(response("one")), http(response("two", id="2"))]):
            self.worker().run()
        self.job = self.store.create_llm(self.source, {"page_ranges": None}, self.source.parent / "out", SETTINGS)
        with mock.patch.object(llm_client.requests, "post") as post:
            self.worker().run()
        post.assert_not_called()
        self.assertEqual(self.store.get(self.job["id"])["status"], "已完成")
        self.job = self.store.create_llm(self.source, {"page_ranges": "1"}, self.source.parent / "out",
                                         {**SETTINGS, "model": "future-model"})
        with mock.patch.object(llm_client.requests, "post", return_value=http(response("new", id="3"))) as post:
            self.worker().run()
        self.assertEqual(post.call_args.kwargs["json"]["model"], "future-model")

    def test_cancel_before_request_and_changed_snapshot(self):
        worker = self.worker()
        worker.isInterruptionRequested = lambda: True
        with mock.patch.object(llm_client.requests, "post") as post:
            worker.run()
        post.assert_not_called()
        with mock.patch.object(llm_client.requests, "post", return_value=http(status=500)):
            self.worker().run()
        job = self.store.get(self.job["id"])
        Path(job["source_snapshot"]).write_bytes(b"changed")
        with mock.patch.object(llm_client.requests, "post") as post:
            self.worker().run()
        post.assert_not_called()
        self.assertIn("已变化", self.store.get(self.job["id"])["error"])

    def test_ranges(self):
        self.assertEqual(selected_pages(" 2, 1-2, 4 ", 4), [1, 2, 4])
        for value in ("0", "2-1", "5", "1,,2", "-1", "1.5"):
            with self.assertRaises(ValueError):
                selected_pages(value, 4)


class LlmCostTest(TempConfigTestCase):
    def setUp(self):
        super().setUp()
        self.ledger = LlmStore(config.CONFIG_PATH.parent / "tokens.db")

    def test_cached_tokens_are_billed_at_their_own_rate(self):
        config.save_settings({"llm_prices": {"gpt-6-luna": {"input": 2, "cached": .5, "output": 8}}})
        with mock.patch.object(llm_client.requests, "post", return_value=http()):
            result = transcribe(b"PNG", SETTINGS, "image", self.ledger)
        expected = (70 * 2 + 30 * .5 + 20 * 8) / 1_000_000
        self.assertAlmostEqual(result["_cost_usd"], expected)
        row = self.ledger.summary()[0]
        self.assertAlmostEqual(row["cost_usd"], expected)
        self.assertEqual(row["unpriced"], 0)

    def test_dated_model_falls_back_to_the_requested_models_price(self):
        config.save_settings({"llm_prices": {"gpt-6-luna": {"input": 1, "cached": 1, "output": 1}}})
        body = {**response(), "model": "gpt-6-luna-2026-11-01"}
        with mock.patch.object(llm_client.requests, "post", return_value=http(body)):
            result = transcribe(b"PNG", SETTINGS, "image", self.ledger)
        self.assertIn("_cost_usd", result)

    def test_unpriced_request_stays_unpriced_after_a_price_is_set(self):
        with mock.patch.object(llm_client.requests, "post", return_value=http()):
            result = transcribe(b"PNG", SETTINGS, "image", self.ledger)
        self.assertNotIn("_cost_usd", result)
        config.save_settings({"llm_prices": {"gpt-6-luna": {"input": 1, "cached": 1, "output": 1}}})
        row = self.ledger.summary()[0]
        self.assertEqual((row["unpriced"], row["cost_usd"]), (1, 0))

    def test_changing_a_price_does_not_rewrite_history(self):
        price = {"input": 1_000_000, "cached": 0, "output": 0}
        self.ledger.record("a", "m", "image", {"input_tokens": 1, "output_tokens": 0}, price=price)
        self.ledger.record("b", "m", "image", {"input_tokens": 1, "output_tokens": 0},
                           price={**price, "input": 2_000_000})
        self.assertAlmostEqual(self.ledger.summary()[0]["cost_usd"], 3)

    def test_unknown_usage_has_no_cost(self):
        cost = self.ledger.record("a", "m", "image", None,
                                  price={"input": 1, "cached": 1, "output": 1})
        self.assertIsNone(cost)
        row = self.ledger.summary()[0]
        self.assertEqual((row["unknown"], row["unpriced"]), (1, 0))

    def test_existing_ledger_is_migrated(self):
        import sqlite3
        path = config.CONFIG_PATH.parent / "old.db"
        conn = sqlite3.connect(path)
        conn.execute("CREATE TABLE requests (id TEXT PRIMARY KEY, created REAL NOT NULL, model TEXT NOT NULL,"
                     " kind TEXT NOT NULL, input_tokens INTEGER NOT NULL, output_tokens INTEGER NOT NULL,"
                     " cached_tokens INTEGER NOT NULL, usage_known INTEGER NOT NULL)")
        conn.execute("INSERT INTO requests VALUES ('a', 1, 'm', 'image', 5, 5, 0, 1)")
        conn.commit()
        conn.close()
        row = LlmStore(path).summary()[0]
        self.assertEqual((row["input_tokens"], row["unpriced"], row["cost_usd"]), (5, 1, 0))


class LlmPdfServiceTest(TempConfigTestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_real_thread_runs_llm_and_restores_job_after_model_setting_changes(self):
        config.save_settings({"pdf_provider": "llm", "llm_api_key": "secret"})
        root = config.CONFIG_PATH.parent
        source = root / "one.pdf"
        writer = PdfWriter()
        writer.add_blank_page(200, 300)
        writer.write(source)
        jobs = PdfJobStore(root / "jobs.db")
        service = PdfService(lambda: None, job_store=jobs)
        self.addCleanup(service.deleteLater)
        def wait():
            deadline = time.monotonic() + 5
            while service._worker is not None and time.monotonic() < deadline:
                self.app.processEvents()
                time.sleep(.005)
            self.assertIsNone(service._worker)
        with mock.patch.object(llm_client.requests, "post", return_value=http()) as post, \
             mock.patch("ocrmath.ocr.pdf_service.os.startfile", create=True):
            service.start({"path": str(source), "provider": "llm", "page_ranges": "",
                           "out_dir": str(root / "out")})
            wait()
            self.assertEqual(post.call_count, 1)
            job = jobs.recent()[0]
            self.assertEqual(job["status"], "已完成")
            Path(job["files"]["md"]["path"]).unlink()
            self.assertTrue(service.state()["jobs"][0]["can_resume"])
            config.save_settings({"llm_model": "new-model"})
            service.resume(job["id"])
            wait()
        self.assertEqual(post.call_count, 1)
        self.assertEqual(jobs.recent()[0]["model"], "gpt-6-luna")
        self.assertEqual(config.get_counters(), (0, 0))
        self.assertEqual(LlmStore().summary()[0]["input_tokens"], 100)
