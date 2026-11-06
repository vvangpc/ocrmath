"""Image routing and retry tests without registering hotkeys or creating a tray."""
from types import SimpleNamespace
from unittest import mock

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QMessageBox
QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)

from ocrmath.app import App
from ocrmath.core import config
from tests.helpers import TempConfigTestCase


class ImageRoutingTest(TempConfigTestCase):
    def fake_app(self):
        return SimpleNamespace(_worker=None, _retry_png=None,
            storage=mock.Mock(), result_win=mock.Mock(), main_win=mock.Mock(),
            open_settings=mock.Mock(), _start_busy=mock.Mock(), _stop_busy=mock.Mock(),
            _on_ocr_ok=mock.Mock(), _on_ocr_failed=mock.Mock(), _clear_image_worker=mock.Mock(),
            _on_captured=mock.Mock(), _pending_sha=None, _pending_png=None, _failed_png=None)

    def test_llm_routes_without_mathpix_credentials_and_uses_scoped_cache(self):
        config.save_settings({"image_provider": "llm", "llm_api_key": "secret"})
        app = self.fake_app()
        app.storage.lookup.return_value = None
        with mock.patch("ocrmath.app.LlmImageWorker") as llm, mock.patch("ocrmath.app.ImageOcrWorker") as mathpix:
            App._on_captured(app, b"png")
        llm.assert_called_once()
        mathpix.assert_not_called()
        self.assertEqual(app._pending_png, b"png")
        app._worker = None
        app.storage.lookup.return_value = SimpleNamespace(result={"text": "cached"})
        with mock.patch("ocrmath.app.LlmImageWorker") as llm:
            App._on_captured(app, b"png")
        llm.assert_not_called()
        app.result_win.show_result.assert_called_once_with({"text": "cached"}, from_cache=True)
        app.result_win.set_source.assert_called_with(b"png")

    def test_mathpix_route_remains_available(self):
        config.save_settings({"app_id": "id", "app_key": "key"})
        app = self.fake_app()
        app.storage.lookup.return_value = None
        with mock.patch("ocrmath.app.ImageOcrWorker") as mathpix, mock.patch("ocrmath.app.LlmImageWorker") as llm:
            App._on_captured(app, b"png")
        mathpix.assert_called_once_with(b"png", "id", "key")
        llm.assert_not_called()

    def test_llm_result_never_bumps_mathpix_counters(self):
        app = self.fake_app()
        App._on_ocr_ok(app, {"text": "$x$", "_provider": "llm"})
        self.assertEqual(config.get_counters(), (0, 0))
        app.storage.log_usage.assert_not_called()
        app.main_win.on_counters_changed.assert_called_once()

    def test_retry_waits_until_worker_finished(self):
        app = self.fake_app()
        app._worker = object()
        app._pending_png = b"same image"
        App._on_ocr_failed(app, "retry")
        app.result_win.show_error.assert_called_once_with("retry")
        self.assertEqual(app._failed_png, b"same image")
        App._retry_last_image(app)
        self.assertEqual(app._retry_png, b"same image")
        with mock.patch("ocrmath.app.QTimer.singleShot", side_effect=lambda _ms, callback: callback()):
            App._clear_image_worker(app)
        app._on_captured.assert_called_once_with(b"same image")
        self.assertIsNone(app._retry_png)
