"""The web pages' only door to Python, and the settings form behind it."""
import json
from types import SimpleNamespace
from unittest import mock

from PyQt6.QtWidgets import QApplication

from ocrmath.ui import bridge as bridge_module
from ocrmath.core import config
from ocrmath.ui import settings_service
from ocrmath.core import webdav
from ocrmath.ui.bridge import Bridge
from ocrmath.ocr.llm_store import LlmStore
from ocrmath.ui.result_format import FloatModel
from ocrmath.core.storage import Storage
from tests.helpers import TempConfigTestCase
from ocrmath.core.utils import UserError

FORM = {"image_provider": "llm", "pdf_provider": "llm", "app_id": "", "app_key": "",
        "llm_api_key": "secret", "llm_model": "next-model",
        "llm_base_url": "https://api.openai.com/v1", "llm_prices": [],
        "hotkey": "Ctrl+Alt+M", "cache_retention_days": "0",
        "image_price_usd": "0.002", "pdf_price_usd": "0.005", "usd_cny_rate": "7",
        "webdav_url": "", "webdav_user": "", "webdav_password": "", "sync_passphrase": "",
        "webdav_path": "", "webdav_sync_interval": "0"}


class BridgeTest(TempConfigTestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt = QApplication.instance() or QApplication([])

    def setUp(self):
        super().setUp()
        self.storage = Storage(config.CONFIG_PATH.parent / "data")
        self.addCleanup(self.storage.close)
        self.app = mock.Mock()
        self.app.storage = self.storage
        self.app._sync_worker = None
        self.app.result_win = SimpleNamespace(model=FloatModel(), refresh=mock.Mock(), hide=mock.Mock(),
                                              hide_after_copy=mock.Mock())
        self.bridge = Bridge(self.app)

    def call(self, name, *args):
        return json.loads(self.bridge.invoke(name, json.dumps(args)))

    def test_only_listed_methods_can_be_called(self):
        for name in ("push", "deleteLater", "__class__"):
            reply = self.call(name)
            self.assertFalse(reply["ok"], name)
        self.assertTrue(all(hasattr(Bridge, n) for n in bridge_module.RPC_METHODS))

    def test_errors_become_replies_instead_of_escaping_into_qt(self):
        self.app.result_win.model = None
        self.assertFalse(self.call("float_state")["ok"])
        self.assertFalse(self.call("float_format")["ok"])

    def test_primary_action_routes_by_state(self):
        model = self.app.result_win.model
        self.call("float_primary")
        self.app.on_snip.assert_called_once()
        model.show_error("boom")
        self.call("float_primary")
        self.app._retry_last_image.assert_called_once()
        model.show_result({"latex_styled": "x", "text": "$x$"})
        with mock.patch.object(self.bridge, "copy_text") as copy:
            self.assertEqual(self.call("float_primary")["result"], {"copied": True})
        copy.assert_called_once_with("x")
        self.app.result_win.hide_after_copy.assert_called_once()

    def test_blank_result_copies_nothing_and_stays_open(self):
        self.app.result_win.model.show_result({"text": ""})
        self.assertEqual(self.call("float_primary")["result"], {"copied": False})
        self.app.result_win.hide_after_copy.assert_not_called()

    def test_provider_toggle_is_locked_while_busy(self):
        self.call("float_toggle_provider")
        self.assertEqual(config.get_provider(), "llm")
        self.app.result_win.model.set_busy(True)
        self.call("float_toggle_provider")
        self.assertEqual(config.get_provider(), "llm")

    def test_history_lists_opens_and_deletes(self):
        self.storage.insert("a" * 64, b"png", {"text": "$x$", "latex_styled": "x", "confidence": .9})
        reply = self.call("history_list", "")["result"]
        self.assertEqual(reply["stats"]["count"], 1)
        row = reply["rows"][0]
        self.assertEqual(row["text"], "x")
        self.assertTrue(row["thumb"].startswith("file:"))
        self.call("history_open", row["id"])
        self.assertEqual(self.app._on_history_open.call_args.args[0].id, row["id"])
        self.call("history_delete", row["id"])
        self.assertFalse(self.call("history_open", row["id"])["ok"])

    def test_usage_combines_mathpix_and_frozen_llm_cost(self):
        self.storage.log_usage("image", 2, .002)
        ledger = LlmStore()
        ledger.record("a", "m", "image", {"input_tokens": 1_000_000, "output_tokens": 0},
                      price={"input": 2, "cached": 1, "output": 8})
        ledger.record("b", "other", "image", {"input_tokens": 1, "output_tokens": 1})
        ledger.record("c", "other", "image", None)
        u = self.call("usage_summary", "all")["result"]
        self.assertAlmostEqual(u["total"], 2.004)
        self.assertAlmostEqual(u["llm_cost"], 2.0)
        self.assertEqual((u["unpriced"], u["unknown"]), (1, 1))
        self.assertEqual(self.call("usage_summary", "today")["result"]["mathpix"]["image_count"], 2)

    def test_saved_settings_reach_the_app(self):
        self.assertTrue(self.call("settings_save", FORM)["ok"])
        self.app._on_settings_changed.assert_called_once()
        self.assertEqual(config.get_llm()["model"], "next-model")
        self.assertIsNone(config.load())
        self.assertIn("next-model", [r["model"] for r in self.call("settings_get")["result"]["llm_prices"]])


class SettingsFormTest(TempConfigTestCase):
    def test_required_fields_follow_the_chosen_providers(self):
        with self.assertRaises(UserError):
            settings_service.save_form({**FORM, "image_provider": "mathpix"})
        with self.assertRaises(UserError):
            settings_service.save_form({**FORM, "llm_api_key": ""})

    def test_unsafe_values_are_refused(self):
        for change in ({"hotkey": "M"}, {"llm_base_url": "http://remote/v1"},
                       {"usd_cny_rate": "abc"}, {"image_price_usd": "-1"},
                       {"webdav_url": "https://dav"}):
            with self.assertRaises(UserError, msg=change):
                settings_service.save_form({**FORM, **change})

    def test_function_key_and_modifier_hotkeys_are_allowed(self):
        self.assertEqual(settings_service.validate_hotkey("F9"), "f9")
        self.assertEqual(settings_service.validate_hotkey("Ctrl+Shift+Q"), "ctrl+shift+q")

    def test_prices_are_all_or_nothing_per_model(self):
        row = {"model": "m", "input": "2", "cached": "", "output": "8"}
        with self.assertRaises(UserError):
            settings_service.save_form({**FORM, "llm_prices": [row]})
        blank = {"model": "n", "input": "", "cached": "", "output": ""}
        settings_service.save_form({**FORM, "llm_prices": [{**row, "cached": ".5"}, blank]})
        self.assertEqual(config.get_llm_prices(), {"m": {"input": 2.0, "cached": .5, "output": 8.0}})

    def test_webdav_needs_a_passphrase_of_reasonable_length(self):
        connection = {"webdav_url": "https://dav", "webdav_user": "u"}
        for phrase in ("", "short"):
            form = {**FORM, **connection, "sync_passphrase": phrase}
            with self.assertRaisesRegex(UserError, "口令"):
                settings_service.save_form(form)
            with self.assertRaisesRegex(UserError, "口令"):
                settings_service.webdav_from_form(form)
        form = {**FORM, **connection, "sync_passphrase": "long enough"}
        settings_service.save_form(form)
        self.assertEqual(config.get_webdav()["passphrase"], "long enough")
        self.assertEqual(settings_service.webdav_from_form(form)["passphrase"], "long enough")
        self.assertEqual(settings_service.load_form()["sync_passphrase"], "long enough")

    def test_ui_memory_stays_on_this_device(self):
        config.update_ui_state(float_geometry="abc", pdf_out_dir="D:/x")
        self.assertEqual(config.get_ui_state()["pdf_out_dir"], "D:/x")
        self.assertNotIn("ui_state", config.get_syncable_payload())
        config.save_settings({"hotkey": "f9"})
        self.assertEqual(config.get_ui_state()["float_geometry"], "abc")

    def test_malformed_synced_prices_count_as_unpriced(self):
        config.save_settings({"llm_prices": {"a": "x", "b": {"input": 1}, "c": {"input": -1, "cached": 0, "output": 0}}})
        self.assertEqual(config.get_llm_prices(), {})

    def test_llm_settings_and_prices_travel_through_webdav(self):
        settings_service.save_form({**FORM, "llm_prices": [
            {"model": "m", "input": "1", "cached": "1", "output": "1"}]})
        payload = config.get_syncable_payload()
        self.assertEqual(payload["llm_api_key"], "secret")
        self.assertEqual(payload["llm_model"], "next-model")
        self.assertIn("m", payload["llm_prices"])
        merged = webdav.merge(payload, 200, {"llm_api_key": "old"}, 100)
        self.assertEqual(merged["llm_api_key"], "secret")
        merged = webdav.merge(payload, 100, {"llm_api_key": "new"}, 200)
        self.assertEqual(merged["llm_api_key"], "new")

    def test_missing_llm_key_does_not_erase_another_devices_key(self):
        config.save_settings({"llm_model": "m"})
        payload = config.get_syncable_payload()
        self.assertNotIn("llm_api_key", payload)
        merged = webdav.merge(payload, 200, {"llm_api_key": "remote"}, 100)
        self.assertEqual(merged["llm_api_key"], "remote")
