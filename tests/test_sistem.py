import importlib.util
from pathlib import Path
import stat
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch


source = Path(__file__).resolve().parents[1] / "config/includes.chroot/usr/share/kage/sistem.py"
spec = importlib.util.spec_from_file_location("sistem", source)
sistem = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sistem)


class CenterTests(unittest.TestCase):
    def test_live_mode_depends_on_the_actual_home_mount(self):
        args = "quiet boot=live persistence persistence-label=kage-persistence"
        self.assertIn("bulunamadı", sistem.session_mode(args, "/"))
        self.assertIn("bulunamadı", sistem.session_mode(args, "/mnt"))
        self.assertIn("kalıcı depolamada", sistem.session_mode(args, "/home"))
        self.assertIn("şifreli kalıcı depolamada", sistem.session_mode(args, "/home", encrypted=True))
        self.assertIn("bulunamadı", sistem.session_mode(args, "/", encrypted=True))
        self.assertIn("Geçici", sistem.session_mode("quiet boot=live", "/home"))
        self.assertEqual(sistem.session_mode("quiet", "/"), "Yerel oturum")

    def test_secure_boot_status_uses_the_efivar_byte(self):
        with tempfile.TemporaryDirectory() as directory:
            efi = Path(directory) / "efi"
            self.assertEqual(sistem.boot_mode(efi), "BIOS")
            (efi / "efivars").mkdir(parents=True)
            variable = efi / "efivars/SecureBoot-example"
            variable.write_bytes(b"\x07\0\0\0\x01")
            self.assertEqual(sistem.boot_mode(efi), "UEFI · Secure Boot açık")
            variable.write_bytes(b"\x07\0\0\0\x00")
            self.assertEqual(sistem.boot_mode(efi), "UEFI · Secure Boot kapalı")
            variable.write_bytes(b"\x07\0\0\0")
            self.assertEqual(sistem.boot_mode(efi), "UEFI")

    def test_missing_apt_indexes_are_distinct_from_an_empty_updates_list(self):
        with patch.object(Path, "glob", return_value=iter(())):
            self.assertIsNone(sistem.package_updates())
        with patch.object(Path, "glob", return_value=iter((Path("example_Packages"),))):
            with patch.dict(sys.modules, {"apt": SimpleNamespace(Cache=lambda **_: [])}):
                self.assertEqual(sistem.package_updates(), [])

    def test_only_upgradable_installed_packages_are_listed(self):
        current = SimpleNamespace(version="1")
        candidate = SimpleNamespace(version="2")
        packages = [
            SimpleNamespace(name="one", is_upgradable=False, installed=current, candidate=current),
            SimpleNamespace(name="two", is_upgradable=True, installed=current, candidate=candidate),
            SimpleNamespace(name="three", is_upgradable=False, installed=None, candidate=candidate),
        ]
        with patch.object(Path, "glob", return_value=iter((Path("example_Packages"),))):
            with patch.dict(sys.modules, {"apt": SimpleNamespace(Cache=lambda **_: packages)}):
                self.assertEqual(sistem.package_updates(), [("two", "1", "2")])

    def test_security_view_uses_trusted_debian_fixes_in_the_candidate(self):
        debian = SimpleNamespace(trusted=True, origin="Debian", label="Debian-Security", codename="trixie-security")
        untrusted = SimpleNamespace(trusted=False, origin="Debian", label="Debian-Security", codename="trixie-security")
        regular = SimpleNamespace(trusted=True, origin="Debian", label="Debian", codename=None)

        def package(name, version, origin):
            candidate = SimpleNamespace(version="4", origins=[regular])
            return SimpleNamespace(
                name=name, is_upgradable=True, installed=SimpleNamespace(version="2"), candidate=candidate,
                versions=[candidate, SimpleNamespace(version=version, origins=[origin])],
            )

        packages = [package("fixed", "3", debian), package("regular", "3", regular),
                    package("untrusted", "3", untrusted), package("already-fixed", "2", debian),
                    package("pinned-older", "5", debian)]
        with (
            patch.object(Path, "glob", return_value=iter((Path("example_Packages"),))) as indexes,
            patch.dict(sys.modules, {"apt": SimpleNamespace(Cache=lambda **_: packages),
                                     "apt_pkg": SimpleNamespace(version_compare=lambda first, second: int(first) - int(second))}),
        ):
            self.assertEqual(sistem.package_updates(security_only=True), [("fixed", "2", "4")])
            indexes.assert_called_once_with("*_dists_*security_*_Packages*")

    def test_package_snapshot_shares_one_apt_cache_and_tracks_missing_security_data(self):
        origin = SimpleNamespace(trusted=True, origin="Debian", label="Debian-Security", codename="trixie-security")
        candidate = SimpleNamespace(version="2", origins=[origin])
        package = SimpleNamespace(name="fixed", is_upgradable=True, installed=SimpleNamespace(version="1"),
                                  candidate=candidate, versions=[candidate])
        cache = Mock(return_value=[package])
        with tempfile.TemporaryDirectory() as directory:
            lists = Path(directory)
            (lists / "debian_dists_trixie_main_binary-amd64_Packages.lz4").touch()
            with (
                patch.object(sistem, "APT_LISTS", lists),
                patch.dict(sys.modules, {"apt": SimpleNamespace(Cache=cache),
                                         "apt_pkg": SimpleNamespace(version_compare=lambda first, second: int(first) - int(second))}),
            ):
                self.assertEqual(sistem.package_snapshot(), ([("fixed", "1", "2")], None))
                (lists / "debian_dists_trixie-security_main_binary-amd64_Packages.lz4").touch()
                cache.reset_mock()
                self.assertEqual(sistem.package_snapshot(), ([("fixed", "1", "2")], [("fixed", "1", "2")]))
                cache.assert_called_once_with(memonly=True)

    def test_package_index_state_changes_when_dpkg_replaces_its_status_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            installed = root / "status"
            installed.write_text("original")
            with patch.object(sistem, "APT_LISTS", root), patch.object(sistem, "DPKG_STATUS", installed):
                original = sistem.package_index_state()
                candidate = root / "status-new"
                candidate.write_text("updated")
                candidate.replace(installed)
                self.assertNotEqual(original, sistem.package_index_state())

    def test_report_replaces_the_destination_with_a_private_file(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "rapor.txt"
            target.write_text("eski veri", encoding="utf-8")
            sistem.save_diagnostics(target, [("Dağıtım", "Kage OS"), ("Ağ arayüzleri", "1 etkin")])
            data = target.read_text(encoding="utf-8")
            self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)
            self.assertIn("Dağıtım\tKage OS", data)
            self.assertIn("Ağ arayüzleri\t1 etkin", data)
            self.assertNotIn("eski veri", data)
            self.assertEqual(list(Path(directory).iterdir()), [target])
