from hashlib import sha256
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

APP = Path(__file__).resolve().parents[1] / "config/includes.chroot/usr/share/kage"
sys.path.insert(0, str(APP))
from rapor import STOPPED, create_report, expected_sha256


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.TemporaryDirectory()
        self.addCleanup(self.work.cleanup)
        self.root = Path(self.work.name)
        self.source = self.root / "örnek dosya.txt"
        self.contents = b"Kage release fixture"
        self.source.write_bytes(self.contents)
        self.expected = sha256(self.contents).hexdigest()
        self.reports = self.root / "reports"

    def test_sha256_and_source_integrity(self):
        folder, message = create_report("sha256", self.source, None, self.reports)
        self.assertEqual(message, "Rapor hazır.")
        self.assertIn(self.expected, (folder / "sha256.txt").read_text())
        self.assertEqual(self.source.read_bytes(), self.contents)

    def test_sha256_verification_accepts_a_copied_checksum(self):
        line = f"{self.expected.upper()}  {self.source.name}"
        folder, message = create_report("sha256", self.source, None, self.reports, expected=line)
        self.assertEqual(message, "SHA-256 eşleşti.")
        self.assertIn("eşleşti", (folder / "islem.txt").read_text())

    def test_sha256_mismatch_is_explicit(self):
        _, message = create_report("sha256", self.source, None, self.reports, expected="0" * 64)
        self.assertEqual(message, "SHA-256 eşleşmedi.")

    def test_invalid_checksum_creates_no_report(self):
        with self.assertRaises(ValueError):
            create_report("sha256", self.source, None, self.reports, expected="123")
        self.assertFalse(self.reports.exists())

    def test_miscellaneous_file_names_still_work_with_sha256sum(self):
        source = self.root / "a\nb\\c"
        source.write_bytes(self.contents)
        folder, message = create_report("sha256", source, None, self.reports, expected=self.expected)
        self.assertEqual(message, "SHA-256 eşleşti.")
        result = subprocess.run(["sha256sum", "--check", str(folder / "sha256.txt")], capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr.decode())

    def test_only_regular_sources(self):
        with self.assertRaises(ValueError):
            create_report("sha256", self.root, None, self.reports)

    def test_cancel_before_subprocess(self):
        cancel = threading.Event()
        cancel.set()
        folder, message = create_report("sha256", self.source, None, self.reports, cancel=cancel)
        self.assertEqual(message, STOPPED)
        self.assertFalse((folder / "sha256.txt").exists())
        self.assertIn(STOPPED, (folder / "islem.txt").read_text())

    def test_cancel_stops_a_running_command(self):
        cancel = threading.Event()
        command = [sys.executable, "-c", "import time; time.sleep(30)"]
        timer = threading.Timer(0.3, cancel.set)
        timer.start()
        try:
            with patch("rapor.command_for", return_value=command):
                folder, message = create_report("interfaces", None, None, self.reports, cancel=cancel)
        finally:
            timer.cancel()
        self.assertEqual(message, STOPPED)
        self.assertFalse((folder / "ag-arayuzleri.txt").exists())

    def test_failed_command_keeps_diagnostics(self):
        command = [sys.executable, "-c", "import sys; print('partial'); sys.stderr.write('error'); sys.exit(3)"]
        with patch("rapor.command_for", return_value=command):
            folder, message = create_report("interfaces", None, None, self.reports)
        self.assertIn("(3)", message)
        self.assertFalse((folder / "ag-arayuzleri.txt").exists())
        self.assertIn("partial", (folder / "tamamlanmayan-ag-arayuzleri.txt").read_text())
        self.assertIn("error", (folder / "uyarilar.txt").read_text())

    def test_empty_expected_value_is_optional(self):
        self.assertIsNone(expected_sha256(" \t "))
        first, _ = create_report("sha256", self.source, None, self.reports)
        second, _ = create_report("sha256", self.source, None, self.reports)
        self.assertNotEqual(first, second)
        self.assertEqual(first.stat().st_mode & 0o777, 0o700)


if __name__ == "__main__":
    unittest.main()
