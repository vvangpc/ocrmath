"""Regressions for result context, exact copying and the float window's rules."""
import config
from result_format import FloatModel, history_copy_text
from tests.helpers import TempConfigTestCase


class FloatModelTest(TempConfigTestCase):
    def setUp(self):
        super().setUp()
        self.model = FloatModel()

    def test_formula_offers_latex_only_and_copies_each_style_exactly(self):
        self.model.show_result({"latex_styled": "$$x^2$$", "text": "$$x^2$$"})
        self.assertEqual(self.model.formats(), ["preview", "latex"])
        self.assertEqual(self.model.snapshot()["primary"]["label"], "复制 LaTeX")
        self.assertEqual(self.model.copy_text(), "x^2")
        self.model.select_format("latex")
        self.model.set_latex_style(1)
        self.assertEqual(self.model.copy_text(), "$x^2$")
        self.model.set_latex_style(2)
        self.assertEqual(self.model.copy_text(), "$$x^2$$")

    def test_mixed_text_offers_markdown_only_and_keeps_the_prose(self):
        text = "这是公式 $x^2$ 的说明。\n\n下一段。"
        self.model.show_result({"text": text, "latex_styled": "x^2"})
        self.assertEqual(self.model.formats(), ["preview", "markdown"])
        self.assertEqual(self.model.snapshot()["primary"]["label"], "复制 Markdown")
        self.assertEqual(self.model.copy_text(), text)
        self.assertFalse(self.model.snapshot()["preview"]["is_math"])

    def test_latex_style_is_remembered_and_applies_from_the_preview(self):
        self.model.set_latex_style(1)
        remembered = FloatModel()
        self.assertEqual(remembered.latex_style, 1)
        remembered.show_result({"latex_styled": "x", "text": "$x$"})
        self.assertEqual(remembered.format, "preview")
        self.assertEqual(remembered.copy_text(), "$x$")

    def test_remembered_style_does_not_touch_mixed_text(self):
        self.model.set_latex_style(2)
        self.model.show_result({"text": "公式 $x$ 的说明"})
        self.assertEqual(self.model.copy_text(), "公式 $x$ 的说明")

    def test_corrupt_remembered_style_falls_back_to_plain(self):
        config.update_ui_state(latex_style="bad")
        self.assertEqual(FloatModel().latex_style, 0)

    def test_format_the_result_does_not_offer_cannot_be_selected(self):
        self.model.show_result({"latex_styled": "x", "text": "$x$"})
        self.model.select_format("markdown")
        self.assertEqual(self.model.format, "preview")

    def test_code_view_shows_exactly_what_is_copied(self):
        self.model.show_result({"latex_styled": "x", "text": "$x$"})
        self.assertEqual(self.model.snapshot()["code"], "")
        self.model.select_format("latex")
        self.model.set_latex_style(2)
        self.assertEqual(self.model.snapshot()["code"], "$$x$$")

    def test_llm_prose_has_tokens_and_no_confidence(self):
        self.model.show_result({"_provider": "llm", "model": "custom-model", "text": "普通文字",
                                "usage": {"input_tokens": 120, "output_tokens": 20},
                                "_cost_usd": .0012})
        self.assertIn("custom-model", self.model.meta)
        self.assertIn("$0.001", self.model.meta)
        self.assertNotIn("置信度", self.model.meta)
        self.assertEqual(self.model.snapshot()["preview"]["content"], "普通文字")

    def test_mathpix_meta_and_low_confidence_warning(self):
        self.model.show_result({"latex_styled": "x", "text": "$x$", "confidence": .42,
                                "is_handwritten": True})
        self.assertIn("手写", self.model.meta)
        self.assertIn("42", self.model.warning)
        self.assertFalse(self.model.warning_is_error)
        self.model.show_result({"latex_styled": "x", "text": "$x$", "confidence": .9})
        self.assertEqual(self.model.warning, "")

    def test_loading_cannot_copy_previous_result_or_change_provider(self):
        self.model.show_result({"text": "$x$", "latex_styled": "x"})
        self.model.show_loading()
        snap = self.model.snapshot()
        self.assertFalse(snap["primary"]["enabled"])
        self.assertFalse(snap["provider"]["enabled"])
        self.assertFalse(snap["can_recapture"])
        self.assertEqual(self.model.copy_text(), "")

    def test_error_retry_is_disabled_until_worker_has_finished(self):
        self.model.show_loading()
        self.model.show_error("网络连接失败")
        self.assertIsNone(self.model.primary_action())
        self.model.set_busy(False)
        self.assertEqual(self.model.primary_action(), "retry")
        snap = self.model.snapshot()
        self.assertEqual(snap["warning"], "网络连接失败")
        self.assertTrue(snap["warning_is_error"])
        self.assertEqual(snap["primary"]["label"], "重试原图")

    def test_history_without_png_cannot_show_a_previous_source(self):
        self.model.set_source(b"png")
        rev = self.model.snapshot()["source_rev"]
        self.assertTrue(self.model.snapshot()["has_source"])
        self.model.set_source(None)
        snap = self.model.snapshot()
        self.assertFalse(snap["has_source"])
        self.assertNotEqual(snap["source_rev"], rev)

    def test_empty_state_captures_and_shows_the_hotkey(self):
        self.assertEqual(self.model.primary_action(), "capture")
        self.assertEqual(self.model.snapshot()["meta"],
                         config.keyboard_to_qt(config.get_hotkey()))

    def test_cache_and_blank_results_do_not_offer_stale_copy(self):
        self.model.show_result({"text": "$x$", "latex_styled": "x"}, from_cache=True)
        self.assertIn("本地缓存", self.model.meta)
        self.model.show_result({"text": "", "_provider": "llm"})
        self.assertIsNone(self.model.primary_action())
        self.assertFalse(self.model.snapshot()["primary"]["enabled"])

    def test_result_is_not_unlocked_before_the_worker_finishes(self):
        self.model.show_loading()
        self.model.show_result({"text": "$x$", "latex_styled": "x"})
        self.assertIsNone(self.model.primary_action())
        self.model.set_busy(False)
        self.assertEqual(self.model.primary_action(), "copy")

    def test_provider_follows_config(self):
        self.assertEqual(self.model.snapshot()["provider"]["key"], "mathpix")
        config.save_settings({"image_provider": "llm", "llm_model": "m"})
        snap = self.model.snapshot()["provider"]
        self.assertEqual((snap["key"], snap["label"]), ("llm", "大模型"))
        self.assertIn("m", snap["title"])

    def test_history_copy_text(self):
        self.assertEqual(history_copy_text("", "公式 $x$ 的说明"), "公式 $x$ 的说明")
        self.assertEqual(history_copy_text("$$x$$", "ignored"), "$x$")
