"""Regressions for result context, exact copying and the compact entry points."""
from unittest import mock

from PyQt6.QtCore import QByteArray, QBuffer, QIODevice, Qt
from PyQt6.QtGui import QImage
from PyQt6.QtWidgets import QApplication

from result_window import ResultWindow
from tests.helpers import TempConfigTestCase


class FocusWindowTest(TempConfigTestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        super().setUp()
        # These tests exercise Qt state and clipboard, not the browser/downloader.
        patch = mock.patch("result_window.WEBENGINE_AVAILABLE", False)
        patch.start()
        self.addCleanup(patch.stop)
        self.recapture, self.retry = mock.Mock(), mock.Mock()
        self.pdf, self.history, self.usage, self.settings = [mock.Mock() for _ in range(4)]
        self.window = ResultWindow(self.recapture, on_retry=self.retry,
            on_open_pdf=self.pdf, on_open_history=self.history,
            on_open_usage=self.usage, on_open_settings=self.settings)
        self.addCleanup(self.window.deleteLater)
        self.addCleanup(self.window.close)

    def test_formula_formats_copy_exactly_and_keep_window_open(self):
        self.window.show_result({"latex_styled": "$$x^2$$", "text": "$$x^2$$"})
        self.window.copy_btn.click()
        self.assertEqual(self.app.clipboard().text(), "x^2")
        self.assertTrue(self.window.isVisible())
        self.window.format_buttons["latex"].click()
        self.window.latex_style.setCurrentIndex(1)
        self.window.copy_btn.click()
        self.assertEqual(self.app.clipboard().text(), "$x^2$")
        self.window.latex_style.setCurrentIndex(2)
        self.window.copy_btn.click()
        self.assertEqual(self.app.clipboard().text(), "$$x^2$$")

    def test_mixed_markdown_is_copied_without_wrapping_the_prose(self):
        text = "这是公式 $x^2$ 的说明。\n\n下一段。"
        self.window.show_result({"text": text, "latex_styled": "x^2"})
        self.assertEqual(self.window.copy_btn.text(), "复制 Markdown")
        self.window.copy_btn.click()
        self.assertEqual(self.app.clipboard().text(), text)

    def test_llm_prose_hides_unavailable_latex_and_has_no_confidence(self):
        self.window.show_result({"_provider": "llm", "model": "custom-model",
            "text": "普通文字", "usage": {"input_tokens": 120, "output_tokens": 20}})
        self.assertTrue(self.window.format_buttons["latex"].isHidden())
        self.assertIn("custom-model", self.window.meta.text())
        self.assertNotIn("置信度", self.window.meta.text())
        self.assertEqual(self.window.preview.text(), "普通文字")

    def test_loading_cannot_copy_previous_result_or_change_provider(self):
        self.window.show_result({"text": "$x$", "latex_styled": "x"})
        self.window.show_loading()
        self.assertFalse(self.window.copy_btn.isEnabled())
        self.assertFalse(self.window.provider_combo.isEnabled())
        self.assertFalse(self.window.recapture_btn.isEnabled())
        self.assertEqual(self.window._copy_text(), "")

    def test_error_retry_is_disabled_until_worker_has_finished(self):
        self.window.show_loading()
        self.window.show_error("网络连接失败")
        self.window.copy_btn.click()
        self.retry.assert_not_called()
        self.window.set_busy(False)
        self.window.copy_btn.click()
        self.retry.assert_called_once()
        self.assertEqual(self.window.warn.text(), "网络连接失败")

    def test_new_history_without_png_cannot_show_a_previous_source(self):
        image = QImage(40, 20, QImage.Format.Format_RGB32)
        image.fill(Qt.GlobalColor.white)
        data = QByteArray()
        buffer = QBuffer(data)
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        image.save(buffer, "PNG")
        self.window.set_source(bytes(data))
        self.window.show_result({"text": "$x$", "latex_styled": "x"})
        self.window.source_btn.click()
        self.assertTrue(self.window.source_frame.isVisible())
        self.app.processEvents()
        self.assertGreaterEqual(self.window.source_label.height(),
                                self.window.source_label.pixmap().height())
        self.window.set_source(None)
        self.assertTrue(self.window.source_frame.isHidden())
        self.assertFalse(self.window.source_btn.isEnabled())
        self.assertTrue(self.window._source.isNull())

    def test_footer_and_empty_primary_action_reach_their_real_callbacks(self):
        self.window.copy_btn.click()
        self.recapture.assert_called_once()
        for button, callback in ((self.window.pdf_btn, self.pdf),
                                 (self.window.history_btn, self.history),
                                 (self.window.usage_btn, self.usage),
                                 (self.window.settings_btn, self.settings)):
            button.click()
            callback.assert_called_once()

    def test_cache_badge_and_blank_result_do_not_offer_stale_copy(self):
        self.window.show_result({"text": "$x$", "latex_styled": "x"}, from_cache=True)
        self.assertEqual(self.window.cache_badge.text(), "本地缓存")
        self.window.show_result({"text": "", "_provider": "llm"})
        self.assertFalse(self.window.copy_btn.isEnabled())

    def test_result_is_not_unlocked_before_the_worker_finishes(self):
        self.window.show_loading()
        self.window.show_result({"text": "$x$", "latex_styled": "x"})
        self.assertFalse(self.window.copy_btn.isEnabled())
        self.window.set_busy(False)
        self.assertTrue(self.window.copy_btn.isEnabled())

    def test_tool_window_navigation_returns_to_the_existing_result(self):
        from main_window import MainWindow
        from storage import Storage
        import config
        storage = Storage(config.CONFIG_PATH.parent)
        self.addCleanup(storage.close)
        back = mock.Mock()
        tools = MainWindow(self.recapture, self.settings, lambda: None, storage,
                           self.history, on_show_result=back)
        self.addCleanup(tools.deleteLater)
        tools.show_page("history")
        self.assertIs(tools._tabs.currentWidget(), tools.history_panel)
        tools.close()
        self.assertFalse(tools.isVisible())
        back.assert_called_once()
