from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from gtimer.auth import password_file_exists, set_password, verify_password


class AuthTests(unittest.TestCase):
    def test_password_hash_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            password_file = Path(tmpdir) / "admin_password.json"
            set_password("correct horse", password_file)

            self.assertTrue(password_file_exists(password_file))
            self.assertTrue(verify_password("correct horse", password_file))
            self.assertFalse(verify_password("wrong", password_file))
            self.assertEqual(password_file.stat().st_mode & 0o777, 0o600)

    def test_empty_password_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaises(ValueError):
                set_password("", Path(tmpdir) / "admin_password.json")


if __name__ == "__main__":
    unittest.main()
