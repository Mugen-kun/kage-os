from hashlib import sha256
from io import BytesIO
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from threading import Event
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "config/includes.chroot/usr/share/kage"))
from bakim import UsbDrive, compare_usb, describe_firewall, hash_prefix, journal_records, verify_media
from rapor import ReportStopped


class MaintenanceTests(unittest.TestCase):
    def test_iso_hash_matches_supplied_checksum_and_usb_prefix(self):
        with TemporaryDirectory() as directory:
            image = Path(directory) / "sample.iso"
            image.write_bytes(b"sample")
            digest = sha256(b"sample").hexdigest()
            disk = UsbDrive("/dev/example", "8:16", 16, "Example")
            with patch("bakim.read_usb_hash", return_value=digest) as read_usb:
                self.assertEqual(verify_media(image, digest, disk, Event()), (digest, True, True))
                self.assertEqual(read_usb.call_args.args[:2], (disk, 6))
            with patch("bakim.read_usb_hash", return_value="0" * 64):
                self.assertEqual(verify_media(image, "0" * 64, disk, Event()), (digest, False, False))

    def test_usb_refuses_internal_or_changed_device(self):
        with patch("bakim.usb_drives", return_value=[UsbDrive("/dev/example", "8:16", 4, "Example")]):
            with patch("bakim.os.open") as opener:
                for path, number, size in (("/dev/internal", "8:0", 2), ("/dev/example", "8:17", 2), ("/dev/example", "8:16", 5)):
                    with self.assertRaises(ValueError):
                        compare_usb(path, number, size)
                opener.assert_not_called()

    def test_short_and_cancelled_reads_have_no_digest(self):
        with self.assertRaises(ValueError):
            hash_prefix(BytesIO(b"a"), 2, Event())
        event = Event()
        event.set()
        with self.assertRaises(ReportStopped):
            hash_prefix(BytesIO(b"abc"), 2, event)

    def test_nft_rules_do_not_confuse_empty_chains_with_policy(self):
        data = {
            "nftables": [
                {"chain": {"family": "inet", "table": "filter", "name": "input", "hook": "input", "policy": "drop"}},
                {"rule": {"family": "inet", "table": "filter", "chain": "input"}},
            ]
        }
        self.assertEqual(describe_firewall(data), (1, [("inet", "filter / input", "Gelen", "Reddet", "1")]))
        self.assertEqual(describe_firewall({"nftables": []}), (0, []))

    def test_journal_accepts_binary_messages_and_missing_fields(self):
        text = '\n'.join(('{"MESSAGE":"Connected","_SYSTEMD_UNIT":"NetworkManager.service","PRIORITY":"4"}',
                          '{"MESSAGE":[0,1],"PRIORITY":"unknown"}', 'this is not JSON'))
        self.assertEqual(journal_records(text), [
            ("—", "NetworkManager.service", 4, "Connected"),
            ("—", "Sistem", 6, "İkili günlük verisi"),
        ])
