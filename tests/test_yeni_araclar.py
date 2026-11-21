from hashlib import sha256
from pathlib import Path
import stat
import sys
import tempfile
from threading import Event
import unittest
from unittest.mock import patch


source = Path(__file__).resolve().parents[1] / "config/includes.chroot/usr/share/kage"
sys.path.insert(0, str(source))

from bakim import journal_records
from donanim import firmware_warnings, hardware_rows, pci_names
from rapor import ReportStopped
from terminal import command_packages, suggested_packages
import vaka


class NewToolsTests(unittest.TestCase):
    def test_missing_commands_use_the_packaged_debian_index(self):
        baseline = command_packages()
        self.assertEqual(suggested_packages("ifconfig", baseline), ["net-tools"])
        self.assertIn("fd-find", suggested_packages("fdfind", baseline))
        self.assertEqual(suggested_packages("kage-no-such-command-0d25e", baseline), [])
        self.assertEqual(suggested_packages("../../fdfind", baseline), [])

    def test_inventory_reads_driver_symlinks_and_firmware_not_found(self):
        with tempfile.TemporaryDirectory() as directory:
            sysfs = Path(directory)
            address = "0000:00:02.0"
            video = sysfs / "bus/pci/devices" / address
            video.mkdir(parents=True)
            (video / "class").write_text("0x030000\n")
            (video / "driver").symlink_to("../../../drivers/virtio_gpu")
            wireless = sysfs / "class/net/wlan0"
            (wireless / "wireless").mkdir(parents=True)
            (wireless / "device").mkdir()
            (wireless / "device/driver").symlink_to("../../../drivers/iwlwifi")
            ethernet = sysfs / "class/net/eth0/device"
            ethernet.mkdir(parents=True)
            (ethernet / "driver").symlink_to("../../../drivers/r8152")
            names = pci_names('0000:00:02.0 "VGA compatible controller" "Fixture" "Graphics"')
            self.assertEqual(hardware_rows(sysfs, names), [
                ("Ekran", "Fixture Graphics", "virtio_gpu"), ("Ağ arayüzü", "eth0", "r8152"), ("Wi-Fi", "wlan0", "iwlwifi"),
            ])
        self.assertEqual(firmware_warnings(
            "iwlwifi: Direct firmware load for fixture.ucode failed with error -2\n"
            "iwlwifi: firmware: failed to load fixture.ucode (-2)\n"
            "fixture: Direct firmware load for timedout.bin failed with error -110\n"
        ), ["fixture.ucode"])

    def test_case_keeps_a_private_reference_with_digest_and_reports(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "Kage-Vakalar"
            evidence = Path(directory) / "example.pcap"
            digest = sha256(b"Fixture evidence bytes").hexdigest()
            evidence.write_bytes(b"Fixture evidence bytes")
            with patch.object(vaka, "case_root", return_value=root):
                case_id = vaka.create_case("  DNS incelemesi  ")
                self.assertEqual(vaka.list_cases(), [(case_id, "DNS incelemesi")])
                case = vaka.case_path(case_id)
                abort = Event()
                abort.set()
                with self.assertRaises(ReportStopped):
                    vaka.register_file(case_id, evidence, abort)
                self.assertEqual(vaka.read_case(case)["files"], [])
                self.assertTrue(vaka.register_file(case_id, evidence, Event()))
                self.assertFalse(vaka.register_file(case_id, evidence, Event()))
                entry, = vaka.read_case(case)["files"]
                self.assertEqual((entry["path"], entry["sha256"], entry["kind"]),
                                 (str(evidence), digest, "Ağ kaydı"))
                self.assertEqual(entry["size"], evidence.stat().st_size)
                self.assertTrue(entry["added"].endswith("+00:00"))
                self.assertEqual(sha256(evidence.read_bytes()).hexdigest(), digest)
                self.assertEqual(vaka.report_destination(case_id), ("DNS incelemesi", case / "raporlar"))
                self.assertEqual(stat.S_IMODE(case.stat().st_mode), 0o700)
                self.assertEqual(stat.S_IMODE((case / "vaka.json").stat().st_mode), 0o600)
                with self.assertRaises(ValueError):
                    vaka.report_destination("../example.pcap")

    def test_offline_samples_have_matching_checksum_and_filterable_logs(self):
        samples = source / "ornekler"
        checksum, filename = (samples / "ornek-belge.sha256").read_text().split()
        self.assertEqual(sha256((samples / filename).read_bytes()).hexdigest(), checksum)
        logs = journal_records((samples / "sistem-gunlugu.jsonl").read_text())
        self.assertEqual(len(logs), 5)
        self.assertTrue(any(unit == "NetworkManager.service" and priority <= 4 for _, unit, priority, _ in logs))
