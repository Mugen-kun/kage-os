from pathlib import Path
import sys
import tempfile
from threading import Event
from types import SimpleNamespace
import unittest
from unittest.mock import patch


source = Path(__file__).resolve().parents[1] / "config/includes.chroot/usr/share/kage"
sys.path.insert(0, str(source))

from aygitlar import GPU, desktop_arguments, gpu_variables, power_status, set_power
import kalicilik
import kurtarma
import sistem_kurtarma
from tercihler import validated
import toolbox
import vaka


class ManagementTests(unittest.TestCase):
    def test_power_profiles_use_only_the_options_returned_by_the_service(self):
        listing = "  performance:\n    CpuDriver: intel_pstate\n* balanced:\n  power-saver:\n"
        with patch("aygitlar.read_command", side_effect=[listing, "balanced"]):
            self.assertEqual(power_status(), (["performance", "balanced", "power-saver"], "balanced"))
        with (
            patch("aygitlar.power_status", return_value=(["balanced", "power-saver"], "balanced")),
            patch("aygitlar.read_command") as command,
        ):
            with self.assertRaises(ValueError):
                set_power("performance")
            command.assert_not_called()

    def test_hybrid_gpu_generates_explicit_mesa_and_nvidia_launch_variables(self):
        intel = GPU("0000:00:02.0", "Intel", "Intel test", "i915")
        nvidia = GPU("0000:01:00.0", "NVIDIA", "RTX test", "nvidia")
        self.assertEqual(gpu_variables(intel), {"DRI_PRIME": "pci-0000_00_02_0"})
        self.assertEqual(gpu_variables(nvidia)["__NV_PRIME_RENDER_OFFLOAD"], "1")
        self.assertEqual(gpu_variables(GPU("0000:01:00.0", "NVIDIA", "RTX test", "Sürücü yok")), {})
        self.assertEqual(desktop_arguments('/usr/bin/viewer --profile "Photos and PDF" %U %%'),
                         ["/usr/bin/viewer", "--profile", "Photos and PDF", "%"])
        with self.assertRaises(ValueError):
            desktop_arguments("viewer %z")

    def test_power_authorization_fallback_saves_the_resulting_selection(self):
        with (
            patch("aygitlar.apply_power_profile", side_effect=ValueError("org.freedesktop.DBus.Error.AccessDenied")),
            patch("aygitlar.config_file", return_value=Path("guc-profili")),
            patch("aygitlar.write_setting_file") as save,
            patch("aygitlar.restore_power") as authorize,
        ):
            set_power("power-saver", authorize=authorize)
            authorize.assert_called_once_with("power-saver")
            save.assert_called_once_with(Path("guc-profili"), "power-saver\n")

    def test_setup_choices_allow_supported_values_and_deduplicate_package_groups(self):
        choices = validated({"keyboard": "tr:f", "language": "en_US.UTF-8", "groups": ["media", "media", "office"]})
        self.assertEqual(choices["groups"], ["media", "office"])
        self.assertEqual(choices["theme"], "koyu")
        for value in ({"keyboard": "-language"}, {"driver": 2}, {"groups": ["arbitrary-package"]}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validated(value)

    def test_usb_selection_accepts_only_empty_unmounted_removable_partitions(self):
        with tempfile.TemporaryDirectory() as work:
            sysfs = Path(work) / "sys"
            parent = sysfs / "devices/sdz"
            (parent / "sdz1/holders").mkdir(parents=True)
            (parent / "diskseq").write_text("28\n")
            dev = sysfs / "dev/block"
            dev.mkdir(parents=True)
            (dev / "8:17").symlink_to(parent / "sdz1")
            primary = {"name": "/dev/sdz1", "type": "part", "maj:min": "8:17",
                       "size": 4294967296, "mountpoints": [None]}
            data = {"blockdevices": [
                {"type": "disk", "tran": "usb", "rm": True, "model": "QA", "children": [
                    primary, dict(primary, name="/dev/sdz2", fstype="ext4"),
                    dict(primary, name="/dev/sdz3", mountpoints=["/mnt/source"]),
                ]},
                {"type": "disk", "tran": "sata", "rm": False, "children": [primary]},
            ]}
            eligible, = kalicilik.usb_partitions(data, sysfs)
            self.assertEqual((eligible.path, eligible.identity), ("/dev/sdz1", "8:17/28"))
            (parent / "sdz1/holders/fixture").touch()
            self.assertEqual(kalicilik.usb_partitions(data, sysfs), [])
            with patch.object(kalicilik, "usb_partitions", return_value=[eligible]), patch.object(kalicilik, "admin") as admin:
                with self.assertRaises(ValueError):
                    kalicilik.format_persistence(eligible.path, "8:17/old-sequence")
                admin.assert_not_called()

    def test_system_snapshot_requires_at_root_and_separate_home_on_the_same_filesystem(self):
        fstab = "UUID=testing / btrfs defaults,subvol=@ 0 0\n"
        self.assertTrue(sistem_kurtarma.uses_at_root(fstab))
        self.assertFalse(sistem_kurtarma.uses_at_root(fstab.replace("subvol=@", "subvolid=256")))
        self.assertFalse(sistem_kurtarma.uses_at_root(fstab.replace("subvol=@", "subvol=@,subvolid=256")))
        root = {"source": "/dev/sdb1[/@]", "target": "/", "fsroot": "/@", "fstype": "btrfs"}
        home = {"source": "/dev/sdb1[/@home]", "target": "/home", "fsroot": "/@home", "fstype": "btrfs"}

        def mounts(path):
            return home if path == "/home" else root

        with patch("sistem_kurtarma.live_session", return_value=False), patch("sistem_kurtarma.read_text", return_value=fstab):
            with patch("sistem_kurtarma.root_mount", side_effect=mounts):
                self.assertEqual(sistem_kurtarma.active_device(), "/dev/sdb1")
            with patch("sistem_kurtarma.root_mount", side_effect=lambda path: {"target": "/boot"} if path == "/boot" else mounts(path)):
                self.assertEqual(sistem_kurtarma.active_device(), "")

    def test_personal_points_restore_only_allowlisted_xfce_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with (
                patch.object(kurtarma, "recovery_directory", return_value=root / "points"),
                patch.object(kurtarma, "config_file", side_effect=lambda name: root / "settings" / name),
                patch.object(kurtarma, "power_status", return_value=([], "")),
                patch.object(kurtarma, "keyboard_status", return_value=("tr", "f")),
                patch.object(kurtarma, "get_setting", side_effect=lambda channel, prop: "Adwaita-dark" if prop == "/Net/ThemeName" else None),
                patch.object(kurtarma, "write_setting") as setting,
                patch.object(kurtarma, "xfconf"), patch.object(kurtarma, "set_keyboard") as keyboard,
                patch.object(kurtarma, "theme_timer"),
            ):
                point = kurtarma.create_user_point("Before setup")
                self.assertEqual(kurtarma.user_points(), [(point, "Before setup")])
                kurtarma.restore_user_point(point)
                self.assertEqual(len(kurtarma.user_points()), 2)
                setting.assert_called_once_with("xsettings", "/Net/ThemeName", "string", "Adwaita-dark")
                keyboard.assert_called_once_with("tr", "f")

    def test_toolbox_prefers_a_trusted_metapackage(self):
        group = toolbox.GROUPS["media"]
        trusted = SimpleNamespace(trusted=True, origin="Kage OS")
        untrusted = SimpleNamespace(trusted=False, origin="Kage OS")
        for origin in (trusted, untrusted):
            cache = {group.name: SimpleNamespace(candidate=SimpleNamespace(origins=[origin]))}
            with patch.dict(sys.modules, {"apt": SimpleNamespace(Cache=lambda **_kwargs: cache)}):
                self.assertEqual(toolbox.packages_to_install(["media"]), [group.name] if origin.trusted else list(group.packages))

    def test_ctf_notes_and_profiles_preserve_existing_case_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = root / "note.txt"
            evidence.write_text("fixture")
            with patch.object(vaka, "case_root", return_value=root / "cases"):
                identifier = vaka.create_case("Quiet workspace")
                self.assertEqual(vaka.read_workspace(identifier)["shell"], "bash")
                vaka.register_file(identifier, evidence, Event())
                link = "https://example.test/local-work"
                vaka.save_workspace(identifier, "Ders notu", [link, link], "zsh")
                self.assertEqual(vaka.read_workspace(identifier), {"notes": "Ders notu", "links": [link], "shell": "zsh"})
                self.assertEqual(len(vaka.read_case(vaka.case_path(identifier))["files"]), 1)
                with self.assertRaises(ValueError):
                    vaka.save_workspace(identifier, "Ders notu", ["file:///tmp/fixture"], "zsh")
