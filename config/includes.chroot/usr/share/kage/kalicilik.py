"""Inspect and prepare an empty partition for Debian Live persistence."""

from dataclasses import dataclass
import json
from pathlib import Path
import re
import subprocess
import tempfile
import uuid

from bakim import read_command
from sistem import command_output, read_text, session_mode


LABEL = "kage-persistence"
PARTITION_PATH = re.compile(r"/dev/[A-Za-z0-9][A-Za-z0-9_.-]*")


@dataclass(frozen=True)
class UsbPartition:
    path: str
    identity: str
    size: int
    model: str


def usb_partitions(data=None, sysfs=Path("/sys")):
    if data is None:
        data = json.loads(read_command(
            "/usr/bin/lsblk", "--json", "--tree", "--paths", "--bytes",
            "--output", "NAME,TYPE,TRAN,RM,RO,SIZE,MAJ:MIN,FSTYPE,LABEL,MODEL,MOUNTPOINTS",
        ))
    partitions = []
    for disk in data["blockdevices"]:
        if disk["type"] != "disk" or disk.get("tran") != "usb" or not disk.get("rm") or disk.get("ro"):
            continue
        for part in disk.get("children", []):
            number = part.get("maj:min", "")
            if (part.get("type") != "part" or part.get("ro") or part.get("fstype") or part.get("label")
                    or part.get("children") or any(part.get("mountpoints") or [])
                    or not PARTITION_PATH.fullmatch(part.get("name", ""))
                    or not re.fullmatch(r"[0-9]+:[0-9]+", number)):
                continue
            sysblock = sysfs / "dev/block" / number
            sequence = read_text(sysblock / "../diskseq")
            if not sequence.isascii() or not sequence.isdecimal():
                continue
            holders = sysblock / "holders"
            if holders.is_dir() and next(holders.iterdir(), None):
                continue
            partitions.append(UsbPartition(part["name"], f"{number}/{sequence}", int(part["size"]),
                                           (disk.get("model") or "USB bellek").strip()))
    return partitions


def persistence_status():
    args = read_text("/proc/cmdline")
    home = str(Path.home())
    target = command_output("findmnt", "--noheadings", "--output", "TARGET", "--target", home)
    source = command_output("findmnt", "--noheadings", "--output", "SOURCE", "--target", home).split("[", 1)[0]
    encrypted = source.startswith("/dev/") and command_output("lsblk", "-ndo", "TYPE", source) == "crypt"
    return session_mode(args, target, encrypted=encrypted)


def admin(*command, secret=None, timeout=120):
    result = subprocess.run(command, input=secret, capture_output=True, timeout=timeout)
    if result.returncode:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise ValueError(detail or f"{Path(command[0]).name} işlemi tamamlanamadı.")
    return result.stdout.decode("utf-8", errors="replace")


def empty_partition(path, identity):
    selected = next((part for part in usb_partitions() if (part.path, part.identity) == (path, identity)), None)
    if not selected:
        raise ValueError("Bağlı olmayan boş bir çıkarılabilir USB bölümü seç. Bölüm listesi değişmiş olabilir.")
    if selected.size < 64 * 1024**2:
        raise ValueError("Kalıcılık bölümü en az 64 MiB olmalı.")
    info = json.loads(admin("/usr/sbin/wipefs", "--no-act", "--json", "--output", "TYPE", "--", path))
    if info.get("signatures") is None or info["signatures"]:
        raise ValueError("Bölümde mevcut disk imzası bulundu.")
    swaps = read_text("/proc/swaps").splitlines()
    if any(line.split()[0] == path for line in swaps[1:] if line.split()):
        raise ValueError("Bu bölüm takas alanı olarak kullanılıyor.")
    return selected


def format_persistence(path, identity, secret=None):
    part = empty_partition(path, identity)
    mapper = "kage-persist-" + uuid.uuid4().hex[:12]
    target = part.path
    opened = False
    try:
        if secret is not None:
            if not 1 <= len(secret) <= 1024 or b"\0" in secret or b"\n" in secret:
                raise ValueError("Geçerli bir LUKS parolası gir.")
            admin("/usr/sbin/cryptsetup", "luksFormat", "--batch-mode", "--type", "luks2", "--label",
                  "persistence", "--key-file", "-", part.path, secret=secret)
            admin("/usr/sbin/cryptsetup", "open", "--key-file", "-", part.path, mapper, secret=secret)
            opened = True
            target = f"/dev/mapper/{mapper}"
        admin("/usr/sbin/mkfs.ext4", "-q", "-L", LABEL, target)
        with tempfile.TemporaryDirectory(prefix="kage-usb-", dir="/run") as temporary:
            admin("/usr/bin/mount", "-t", "ext4", "-o", "nodev,nosuid,noexec", target, temporary)
            try:
                config = Path(temporary) / "persistence.conf"
                with config.open("x", encoding="ascii") as stream:
                    stream.write("/home\n")
                config.chmod(0o644)
            finally:
                admin("/usr/bin/umount", temporary)
    finally:
        if opened:
            admin("/usr/sbin/cryptsetup", "close", mapper)
