"""Btrfs system checkpoints for the supported Kage @ and @home layout."""

from contextlib import contextmanager
from fcntl import LOCK_EX, flock
import json
import os
from pathlib import Path
import stat
import tempfile

from aygitlar import live_session
from gunluk_dosyalar import AT_FDCWD, RENAME
from kalicilik import admin
from kurtarma import POINT, point_id
from sistem import command_output, read_text


SNAPSHOTS = ".kage-checkpoints"
PREVIOUS = ".kage-previous-roots"
RENAME_EXCHANGE = 2


def root_mount(path):
    text = command_output("findmnt", "--json", "--first-only", "--target", str(path),
                          "--output", "SOURCE,TARGET,FSTYPE,FSROOT")
    mounts = json.loads(text).get("filesystems", ()) if text else ()
    return mounts[0] if mounts else {}


def mount_device(info):
    return (info.get("source") or "").split("[", 1)[0]


def uses_at_root(fstab):
    for line in fstab.splitlines():
        fields = line.split("#", 1)[0].split()
        if len(fields) >= 4 and fields[1] == "/" and fields[2] == "btrfs":
            options = fields[3].split(",")
            return any(item in options for item in ("subvol=@", "subvol=/@")) and not any(
                item.startswith("subvolid=") for item in options
            )
    return False


def active_device():
    if live_session():
        return ""
    root = root_mount("/")
    home = root_mount("/home")
    device = mount_device(root)
    if (root.get("fstype") != "btrfs" or root.get("fsroot") != "/@" or not device.startswith("/dev/")
            or mount_device(home) != device or home.get("fsroot") != "/@home" or home.get("target") != "/home"):
        return ""
    for directory in ("/boot", "/usr", "/etc", "/var/lib/dpkg"):
        if root_mount(directory).get("target") != "/":
            return ""
    return device if uses_at_root(read_text("/etc/fstab")) else ""


@contextmanager
def top_mount(device, *, readonly=False):
    with tempfile.TemporaryDirectory(prefix="kage-btrfs-", dir="/run") as path:
        options = "subvolid=5,nodev,nosuid,noexec" + (",ro,rescue=nologreplay" if readonly else "")
        admin("/usr/bin/mount", "-t", "btrfs", "-o", options, device, path)
        try:
            yield Path(path)
        finally:
            admin("/usr/bin/umount", path)


def reserved_directory(top, name, *, create=False):
    directory = top / name
    if directory.is_symlink():
        raise ValueError("Kage kurtarma dizini geçersiz.")
    if create:
        directory.mkdir(mode=0o700, exist_ok=True)
    return directory


def kage_root(top, path):
    if path.is_symlink() or not path.is_dir() or not (path / "etc").resolve().is_relative_to(top):
        raise ValueError("Kage kök alt birimi bulunamadı.")
    if not read_text(path / "etc/kage-release").startswith("Kage OS ") or not uses_at_root(read_text(path / "etc/fstab")):
        raise ValueError("Bu disk Kage’nin @ kök düzenini kullanmıyor.")
    admin("/usr/bin/btrfs", "subvolume", "show", str(path))


def snapshot_root(top):
    root = top / "@"
    kage_root(top, root)
    if admin("/usr/bin/btrfs", "subvolume", "list", "-o", str(root)).strip():
        raise ValueError("Kök altında iç içe Btrfs alt birimleri bulundu.")
    destination = reserved_directory(top, SNAPSHOTS, create=True)
    identifier = point_id()
    admin("/usr/bin/btrfs", "subvolume", "snapshot", "-r", str(root), str(destination / identifier))
    return identifier


@contextmanager
def operation_lock():
    with open("/run/lock/kage-system-recovery.lock", "a", encoding="ascii") as lock:
        flock(lock, LOCK_EX)
        yield


def create_system_point():
    device = active_device()
    if not device:
        raise ValueError("Sistem noktası için /@ ve ayrı /@home alt birimleri olan bir Kage kurulumu gerekir.")
    with operation_lock(), top_mount(device) as top:
        return snapshot_root(top)


def offline_device(path):
    if not live_session():
        raise ValueError("Sistem geri alma işlemini canlı Kage oturumunda çalıştır.")
    device = Path(path).resolve(strict=True)
    if not device.is_relative_to("/dev") or not stat.S_ISBLK(device.stat().st_mode):
        raise ValueError("Bir Btrfs disk bölümü seç.")
    filesystem = admin("/usr/sbin/blkid", "-p", "-s", "TYPE", "-o", "value", str(device)).strip()
    if filesystem != "btrfs":
        raise ValueError("Seçilen aygıt Btrfs kullanmıyor.")
    identity = admin("/usr/sbin/blkid", "-p", "-s", "UUID", "-o", "value", str(device)).strip()
    # Compare filesystem UUID so that a second member of a mounted Btrfs pool is rejected too.
    mounted = command_output("findmnt", "--noheadings", "--types", "btrfs", "--output", "UUID").split()
    if not identity or identity in mounted:
        raise ValueError("Kurtarılacak Btrfs dosya sistemi bağlı. Önce bağlantısını kes.")
    return str(device)


def offline_points(path):
    with operation_lock(), top_mount(offline_device(path), readonly=True) as top:
        kage_root(top, top / "@")
        return sorted((item.name for item in reserved_directory(top, SNAPSHOTS).glob("*")
                       if POINT.fullmatch(item.name) and item.is_dir() and not item.is_symlink()), reverse=True)


def restore_offline(path, identifier):
    if not POINT.fullmatch(identifier):
        raise ValueError("Sistem noktası kimliği geçersiz.")
    with operation_lock():
        device = offline_device(path)
        with top_mount(device, readonly=True) as top:
            validate_offline_point(top, identifier)
        with top_mount(offline_device(device)) as top:
            return exchange_roots(top, identifier)


def validate_offline_point(top, identifier):
    kage_root(top, top / "@")
    home = top / "@home"
    if home.is_symlink():
        raise ValueError("Ayrı @home alt birimi bulunamadı.")
    admin("/usr/bin/btrfs", "subvolume", "show", str(home))
    point = reserved_directory(top, SNAPSHOTS) / identifier
    kage_root(top, point)
    if admin("/usr/bin/btrfs", "property", "get", "-t", "subvol", str(point), "ro").strip() != "ro=true":
        raise ValueError("Kurtarma noktası salt okunur değil.")
    return point


def exchange_roots(top, identifier):
    point = validate_offline_point(top, identifier)
    previous = reserved_directory(top, PREVIOUS, create=True) / point_id()
    admin("/usr/bin/btrfs", "subvolume", "snapshot", str(point), str(previous))
    if RENAME(AT_FDCWD, os.fsencode(top / "@"), AT_FDCWD, os.fsencode(previous), RENAME_EXCHANGE) != 0:
        admin("/usr/bin/btrfs", "subvolume", "delete", str(previous))
        raise ValueError("Bu disk atomik alt birim değişimini desteklemiyor. Etkin kök korunuyor.")
    admin("/usr/bin/btrfs", "filesystem", "sync", str(top))
    return str(previous.relative_to(top))
