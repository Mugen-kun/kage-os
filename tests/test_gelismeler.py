import csv
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from threading import Event
import unittest
from unittest.mock import patch


source = Path(__file__).resolve().parents[1] / "config/includes.chroot/usr/share/kage"
sys.path.insert(0, str(source))


import paket_profili
import paket_tanila
from rapor import ReportStopped
from toolbox import GROUPS
import vaka
import zaman_cizelgesi as zaman


class DiagnosticsTests(unittest.TestCase):
    def test_lock_check_matches_identity_and_ignores_waiters(self):
        data = (
            "1: POSIX ADVISORY WRITE 100 00:ff:42 0 EOF\n"
            "1: -> POSIX ADVISORY WRITE 101 00:01:88 0 EOF\n"
            "2: FLOCK ADVISORY WRITE 200 00:01:90 0 EOF\n"
        )
        identities = {(0, 255, 42): "dpkg", (0, 1, 88): "waiter", (0, 1, 42): "different files"}
        self.assertEqual(paket_tanila.locks_in_use(data, identities), {"dpkg"})

    def test_local_diagnosis_uses_no_network_and_reports_package_resolution(self):
        policy = subprocess.CompletedProcess([], 0, "tree:\n  Installed: (none)\n  Candidate: 2.0.4-1\n", "")
        plan = subprocess.CompletedProcess([], 0, "Inst tree (2.0.4-1 Debian:13/stable [amd64])\n", "")
        empty = paket_tanila.Finding("Fixture", "Hazır", "")
        with (
            patch.object(paket_tanila, "lock_finding", return_value=empty),
            patch.object(paket_tanila, "storage_finding", return_value=empty),
            patch.object(paket_tanila, "index_finding", return_value=empty),
            patch.object(paket_tanila, "route_finding", return_value=empty),
            patch.object(paket_tanila, "clock_finding", return_value=empty),
            patch.object(paket_tanila, "run", side_effect=[policy, plan]) as run,
            patch.object(paket_tanila, "connection_findings") as network,
        ):
            findings = paket_tanila.diagnose("tree", previous_error="E: Temporary failure resolving fixture.invalid")
            network.assert_not_called()
        self.assertIn("DNS", findings[0].detail)
        self.assertIn("Aday 2.0.4-1", findings[-2].detail)
        self.assertIn("1 paket", findings[-1].detail)
        self.assertIn("--simulate", run.call_args_list[1].args)
        with self.assertRaises(ValueError):
            paket_tanila.diagnose("bad*")

    def test_online_connection_reports_dns_and_certificate_independently(self):
        lookup = subprocess.CompletedProcess([], 2, "", "")
        failed_tls = subprocess.CompletedProcess([], 60, "000", "SSL certificate problem")
        with patch.object(paket_tanila, "run", side_effect=[lookup, failed_tls]) as run:
            findings = paket_tanila.connection_findings()
        self.assertEqual([line.name for line in findings], ["Debian DNS", "Debian HTTPS"])
        self.assertEqual([line.state for line in findings], ["Sorun var", "Sorun var"])
        self.assertIn("Sertifika", findings[1].detail)
        self.assertEqual(run.call_args_list[1].args[-1], paket_tanila.DEBIAN_INDEX)
        self.assertNotIn("--insecure", run.call_args_list[1].args)


class PackageProfileTests(unittest.TestCase):
    def test_profile_persists_and_can_be_carried_between_sessions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = root / "user" / "paket-profili.json"
            exported = root / "profile.json"
            with patch.object(paket_profili, "config_file", return_value=state):
                self.assertIsNone(paket_profili.read_profile())
                paket_profili.save_profile(["network", "media", "network"])
                self.assertEqual(paket_profili.read_profile(), ["network", "media"])
                paket_profili.save_profile(paket_profili.read_profile(), exported)
                self.assertEqual(paket_profili.read_profile(exported), ["network", "media"])
                self.assertEqual(paket_profili.missing_groups(paket_profili.read_profile(), set(GROUPS["network"].packages)), ["media"])
                paket_profili.save_profile([])
                self.assertEqual(paket_profili.read_profile(), [])

    def test_profile_accepts_only_known_categories(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad-profile.json"
            for payload in (
                {"format": paket_profili.FORMAT, "version": 1, "groups": ["unlisted"]},
                {"format": paket_profili.FORMAT, "version": True, "groups": ["office"]},
                {"format": "foreign", "version": 1, "groups": ["office"]},
            ):
                path.write_text(json.dumps(payload))
                with self.assertRaises(ValueError):
                    paket_profili.read_profile(path)


class TimelineTests(unittest.TestCase):
    def test_timeline_merges_utc_journal_notes_and_file_records(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            log = root / "journal.jsonl"
            journal_line = json.dumps({"__REALTIME_TIMESTAMP": "1759999999000000", "MESSAGE": "Örnek bağlantı"})
            log.write_text(journal_line + "\n", encoding="utf-8")
            with patch.object(vaka, "case_root", return_value=root / "cases"):
                case = vaka.create_case("Örnek")
                vaka.register_file(case, log, Event())
                zaman.add_note(case, "2025-10-09 11:53:20+03:00", "Zaman notu")
                rows, warnings = zaman.list_events(case, Event())
                self.assertEqual(warnings, [])
                self.assertEqual([row.time for row in rows], sorted(row.time for row in rows))
                notes = [row for row in rows if row.category == "Not"]
                self.assertEqual(zaman.display_time(notes[0].time), "2025-10-09 08:53:20Z")
                self.assertEqual(len([row for row in rows if row.category == "Sistem günlüğü"]), 1)
                self.assertEqual(len([row for row in rows if row.category == "Dosya zamanı"]), 1)
                self.assertEqual(log.read_text(encoding="utf-8"), journal_line + "\n")
                cancel = Event()
                cancel.set()
                with self.assertRaises(ReportStopped):
                    zaman.list_events(case, cancel)

    def test_changed_source_is_excluded_and_unchanged_content_can_be_rechecked(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "before.jsonl"
            source.write_text('{"__REALTIME_TIMESTAMP":"1759999999000000","MESSAGE":"FIRST"}\n')
            with patch.object(vaka, "case_root", return_value=root / "cases"):
                case = vaka.create_case("Kaynak")
                vaka.register_file(case, source, Event())
                old = source.stat()
                os.utime(source, ns=(old.st_atime_ns, old.st_mtime_ns + 2_000_000_000))
                original_rows, original_warnings = zaman.list_events(case, Event())
                self.assertFalse(original_warnings)
                self.assertTrue(any("FIRST" in row.detail for row in original_rows))
                source.write_text('{"__REALTIME_TIMESTAMP":"1759999999000000","MESSAGE":"AFTER"}\n')
                os.utime(source, ns=(old.st_atime_ns, old.st_mtime_ns + 3_000_000_000))
                rows, warnings = zaman.list_events(case, Event())
                self.assertTrue(any("değişmiş" in message for message in warnings))
                self.assertFalse(any(row.category == "Sistem günlüğü" for row in rows))

    def test_journal_preview_is_bounded_and_csv_preserves_literal_text(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            log = root / "journal.jsonl"
            record = '{"__REALTIME_TIMESTAMP":"1759999999000000","MESSAGE":"fixture"}\n'
            log.write_text(record * 3)
            rows, truncated = zaman.journal_events(log, 2, Event())
            self.assertEqual(len(rows), 2)
            self.assertTrue(truncated)
            with self.assertRaises(ValueError):
                zaman.epoch_time("1e999999", 1_000_000)
            destination = root / "events.csv"
            zaman.export_csv(destination, [zaman.Event(rows[0].time, "Not", "=1+1", "  @metin")])
            with destination.open(encoding="utf-8-sig", newline="") as stream:
                _, row = list(csv.reader(stream))
                self.assertEqual(row[2:], ["'=1+1", "'  @metin"])
