#!/usr/bin/env python3
"""Assemble and verify Kage OS release media from the verified Kage OS 0.4.0 ISO."""

import argparse
from fcntl import LOCK_EX, flock
from hashlib import file_digest, sha256
import os
from pathlib import Path
import re
import subprocess
import tempfile


PROJECT = Path(__file__).resolve().parents[1]
BOOTLOADERS = PROJECT / "config/bootloaders"
VERSION = (PROJECT / "VERSION").read_text().strip()
XORRISO = os.environ.get("KAGE_BUILD_XORRISO", "xorriso")
EXPECTED_BASE = (PROJECT / "scripts/base.sha256").read_text().split()[0]
VOLUME = "KAGE_" + VERSION.replace(".", "_")
LBA_PATTERN = re.compile(r"^File data lba:\s+\d+\s*,\s*(\d+)\s*,\s*\d+\s*,\s*(\d+)\s*,\s+'(.*)'$")


def iso_command(*args, capture=False):
    return subprocess.run([XORRISO, *map(str, args)], check=True, text=True, capture_output=capture)


def digest(p):
    with p.open("rb") as f:
        return file_digest(f, "sha256").hexdigest()


def verify_base(base):
    if digest(base) != EXPECTED_BASE:
        raise SystemExit("Kage OS 0.4.0 taban imajının SHA-256 özeti eşleşmedi.")


def render_boot_configs(grub, bios):
    def read_directives(path, directive):
        return [
            row.split(None, 1)[1]
            for line in path.read_text().splitlines()
            if (row := line.lstrip()).startswith(directive + "\t") or row.startswith(directive + " ")
        ]

    def render(template, output, values):
        contents = template.read_text(encoding="utf-8")
        for marker, value in values.items():
            contents = contents.replace(f"@{marker}@", value)
        if re.search(r"@[A-Z_]+@", contents):
            raise SystemExit(f"Açılış şablonunda eksik değer: {template.name}")
        output.write_text(contents, encoding="utf-8")

    linux_entries = read_directives(grub, "linux")
    live = linux_entries[0]
    compatible = next(entry for entry in linux_entries if "nomodeset" in entry.split())
    verify = next(entry for entry in linux_entries if "verify-checksums" in entry.split())
    kernel, normal_args = live.split(None, 1)
    grub_initrd = read_directives(grub, "initrd")[0]
    bios_initrd = read_directives(bios, "initrd")[0]
    render(BOOTLOADERS / "grub-pc/grub.cfg", grub, {
        "KERNEL_LIVE": kernel,
        "INITRD_LIVE": grub_initrd,
        "APPEND_LIVE": normal_args,
        "LB_BOOTAPPEND_LIVE_FAILSAFE": compatible.split(None, 1)[1],
        "ENABLE_VERIFY_CHECKSUMS": "true",
        "APPEND_VERIFY_CHECKSUMS": verify.split(None, 1)[1],
    })
    append_entries = read_directives(bios, "append")
    normal = append_entries[0]
    failsafe = next(entry for entry in append_entries if "nomodeset" in entry.split())
    render(BOOTLOADERS / "syslinux_common/live.cfg.in", bios, {
        "FLAVOUR": "amd64",
        "LINUX": read_directives(bios, "linux")[0],
        "INITRD": bios_initrd,
        "APPEND_LIVE": normal,
        "APPEND_LIVE_FAILSAFE": failsafe,
    })
    return {grub_initrd, bios_initrd}


def update_checksums(original, replacements):
    pending = dict(replacements)
    lines = []
    for line in original.read_text(encoding="utf-8").splitlines():
        old_sum, name = line.split("  ", 1)
        replacement = pending.pop(name.removeprefix("."), None)
        lines.append(f"{digest(replacement) if replacement else old_sum}  {name}")
    if pending:
        raise SystemExit("Taban ISO sağlama listesinde eksik dosya: " + ", ".join(pending))
    return "\n".join(lines) + "\n"


def verify_media(iso, checksums):
    boot_info = iso_command("-indev", iso, "-report_el_torito", "plain", "-report_system_area", "plain",
                            "-pvd_info", "-end", capture=True)
    content = boot_info.stdout + boot_info.stderr
    markers = (VOLUME, "El Torito boot img", "BIOS", "UEFI", "MBR isohybrid")
    if not all(marker in content for marker in markers):
        raise SystemExit("ISO açılış kayıtları doğrulanamadı.")
    result = iso_command("-indev", iso, "-find", "/", "-type", "f", "-exec", "report_lba", "--", "-end",
                         capture=True)
    extents = {}
    for line in result.stdout.splitlines():
        entry = LBA_PATTERN.match(line)
        if entry:
            offset, length, name = entry.groups()
            extents[name] = (int(offset) * 2048, int(length))
    with iso.open("rb") as image:
        for line in checksums.splitlines():
            expected, name = line.split("  ", 1)
            offset, remaining = extents[name.removeprefix(".")]
            image.seek(offset)
            checksum = sha256()
            while remaining:
                chunk = image.read(min(remaining, 1024 * 1024))
                if not chunk:
                    raise EOFError(name)
                checksum.update(chunk)
                remaining -= len(chunk)
            if checksum.hexdigest() != expected:
                raise SystemExit(f"ISO içindeki dosya doğrulanamadı: {name}")
    print(f"ISO içindeki {len(checksums.splitlines())} dosya SHA-256 ile doğrulandı.")


def pack(base, rootfs, output):
    verify_base(base)
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".kage-iso-", dir=output) as temporary:
        staging = Path(temporary)
        original_sums = staging / "original-sha256.txt"
        grub = staging / "grub.cfg"
        bios = staging / "menu.cfg"
        bios_live = staging / "live.cfg"
        disk = staging / "disk-info"
        for source, destination in (
            ("/sha256sum.txt", original_sums),
            ("/boot/grub/grub.cfg", grub),
            ("/isolinux/live.cfg", bios_live),
        ):
            iso_command("-osirrox", "on", "-indev", base, "-extract", source, destination, "-end", capture=True)
        # xorriso extracts ISO files with the original read-only mode.
        for p in (grub, bios_live):
            p.chmod(0o644)
        initrd_paths = render_boot_configs(grub, bios_live)
        source_menu = (BOOTLOADERS / "syslinux_common/menu.cfg").read_text(encoding="utf-8")
        bios.write_text(source_menu.replace("@OPTIONAL_INSTALLER_INCLUDE@\n", ""), encoding="utf-8")
        disk.write_text(f"Kage OS {VERSION} (Debian GNU/Linux 13 Trixie) amd64 LIVE\n", encoding="utf-8")
        files = {
            "/.disk/info": disk,
            "/isolinux/menu.cfg": bios,
            "/isolinux/live.cfg": bios_live,
            "/isolinux/stdmenu.cfg": BOOTLOADERS / "syslinux_common/stdmenu.cfg",
            "/isolinux/splash.png": BOOTLOADERS / "syslinux_common/splash.png",
            "/boot/grub/grub.cfg": grub,
            "/boot/grub/live-theme/theme.txt": BOOTLOADERS / "grub-pc/live-theme/theme.txt",
            "/boot/grub/splash.png": BOOTLOADERS / "grub-pc/splash.png",
            "/live/filesystem.packages": rootfs / "filesystem.packages",
            "/live/filesystem.squashfs": rootfs / "filesystem.squashfs",
        }
        files.update(dict.fromkeys(sorted(initrd_paths), rootfs / "initrd.img"))
        checksums = update_checksums(original_sums, files)
        sums = staging / "sha256sum.txt"
        sums.write_text(checksums, encoding="utf-8")
        files["/sha256sum.txt"] = sums
        name = f"kage-{VERSION}-amd64.iso"
        iso = staging / name
        args = ["-abort_on", "FAILURE", "-indev", base, "-outdev", iso,
                "-boot_image", "any", "replay", "-volid", VOLUME, "-application_id", f"Kage OS {VERSION}",
                "-overwrite", "nondir"]
        for destination, source in files.items():
            args.extend(("-map", source, destination))
        iso_command(*args, "-commit", "-end")
        verify_media(iso, checksums)
        sidecar = staging / (name + ".sha256")
        sidecar.write_text(f"{digest(iso)}  {name}\n", encoding="ascii")
        iso.chmod(0o644)
        sidecar.chmod(0o644)
        # Commit both files under the output directory lock, with the checksum last.
        output_lock = os.open(output, os.O_RDONLY | os.O_DIRECTORY)
        try:
            flock(output_lock, LOCK_EX)
            final_checksum = output / sidecar.name
            final_checksum.unlink(missing_ok=True)
            iso.replace(output / name)
            sidecar.replace(final_checksum)
        finally:
            os.close(output_lock)
        print(output / name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base", type=Path)
    parser.add_argument("rootfs", type=Path, nargs="?")
    parser.add_argument("output", type=Path, nargs="?")
    parser.add_argument("--check-base", action="store_true")
    args = parser.parse_args()
    if args.check_base:
        verify_base(args.base.resolve(strict=True))
    elif args.rootfs is None or args.output is None:
        parser.error("rootfs and output are required")
    else:
        pack(args.base.resolve(strict=True), args.rootfs.resolve(strict=True), args.output.resolve())


if __name__ == "__main__":
    main()
