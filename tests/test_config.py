import unittest

import config
from tests.helpers import TempConfigTestCase


class HotkeyFormatTest(unittest.TestCase):
    def test_qt_to_keyboard(self):
        self.assertEqual(config.qt_to_keyboard("Ctrl+Alt+M"), "ctrl+alt+m")
        self.assertEqual(config.qt_to_keyboard("Meta+Shift+F5"),
                         "windows+shift+f5")
        self.assertEqual(config.qt_to_keyboard(""), "")

    def test_keyboard_to_qt(self):
        self.assertEqual(config.keyboard_to_qt("ctrl+alt+m"), "Ctrl+Alt+M")
        self.assertEqual(config.keyboard_to_qt("windows+f5"), "Meta+F5")

    def test_round_trip(self):
        for hk in ("ctrl+alt+m", "ctrl+shift+f2", "alt+windows+q"):
            self.assertEqual(
                config.qt_to_keyboard(config.keyboard_to_qt(hk)), hk)


class SaveSettingsTest(TempConfigTestCase):
    def test_stamps_modified_at_only_for_lww_changes(self):
        config.save_settings({"app_id": "A", "app_key": "K"})
        first = config.get_modified_at()
        self.assertGreater(first, 0)
        # Non-synced field: no stamp.
        config.save_settings({"hotkey": "ctrl+alt+q"})
        self.assertEqual(config.get_modified_at(), first)
        # Unchanged synced field: no stamp.
        config.save_settings({"app_id": "A"})
        self.assertEqual(config.get_modified_at(), first)

    def test_drop(self):
        config.save_settings({"app_id": "A", "app_key": "K", "hotkey": "f9"})
        config.save_settings({}, drop=("app_id", "app_key"))
        self.assertIsNone(config.load())
        self.assertEqual(config.get_hotkey(), "f9")


class ApplySyncedPayloadTest(TempConfigTestCase):
    def test_counters_never_go_backwards(self):
        config.save_all({"image_count": 11})
        config.apply_synced_payload({"image_count": 10}, 1.0,
                                    base_modified_at=0.0)
        self.assertEqual(config.get_counters()[0], 11)

    def test_lww_skipped_when_settings_changed_mid_sync(self):
        config.save_all({"app_key": "NEW", "settings_modified_at": 200.0})
        config.apply_synced_payload(
            {"app_key": "OLD", "settings_modified_at": 50.0}, 300.0,
            base_modified_at=100.0)
        s = config.load_all()
        self.assertEqual(s["app_key"], "NEW")
        self.assertEqual(s["settings_modified_at"], 200.0)
        self.assertEqual(s["last_synced_at"], 300.0)

    def test_lww_applied_when_untouched(self):
        config.save_all({"app_key": "OLD", "settings_modified_at": 100.0})
        config.apply_synced_payload(
            {"app_key": "REMOTE", "settings_modified_at": 150.0}, 300.0,
            base_modified_at=100.0)
        s = config.load_all()
        self.assertEqual(s["app_key"], "REMOTE")
        self.assertEqual(s["settings_modified_at"], 150.0)


if __name__ == "__main__":
    unittest.main()
