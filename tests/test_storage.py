import contextlib
import io
import tempfile
import time
import unittest
from pathlib import Path

import storage


class StorageTest(unittest.TestCase):
    def test_builtin_selftest(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(storage._selftest(), 0)

    def test_purge_keeps_usage_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            st = storage.Storage(Path(tmp) / "ocrmath")
            try:
                st.insert("a" * 64, b"png", {"text": "x"})
                st._conn.execute(
                    "UPDATE recognitions SET created_at = ?",
                    (time.time() - 10 * 86400,))
                st._conn.execute(
                    "INSERT INTO usage (created_at, kind, count, cost_usd) "
                    "VALUES (?, 'image', 1, 0.002)",
                    (time.time() - 10 * 86400,))
                st._conn.commit()
                self.assertEqual(st.purge_older_than(7), 1)
                self.assertEqual(st.list_recent(), [])
                self.assertEqual(st.usage_summary(0)["image_count"], 1)
            finally:
                st.close()


if __name__ == "__main__":
    unittest.main()
