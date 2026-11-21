"""Read local firewall, journal and media data for Kage Merkez."""

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import json
import os
import stat
import subprocess
from threading import Event

from rapor import ReportStopped, expected_sha256, file_stamp, regular_file


JOURNAL_LIMIT = 300


def read_command(*args):
    result = subprocess.run(args, capture_output=True, text=True, errors="replace", timeout=12)
    if result.returncode:
        detail = result.stderr.strip().splitlines()
        raise ValueError(detail[-1] if detail else "Sistem aracı veri döndürmedi.")
    return result.stdout


def describe_firewall(data):
    chains = {}
    counts = {}
    for record in data.get("nftables", []):
        if "chain" in record:
            chain = record["chain"]
            key = chain["family"], chain["table"], chain["name"]
            chains[key] = chain
        elif "rule" in record:
            rule = record["rule"]
            key = rule["family"], rule["table"], rule["chain"]
            counts[key] = counts.get(key, 0) + 1

    hooks = {"input": "Gelen", "output": "Giden", "forward": "Yönlendirilen"}
    policies = {"accept": "Kabul", "drop": "Reddet"}
    rows = [
        (
            family, f"{table} / {name}", hooks.get(chain.get("hook"), chain.get("hook", "—")),
            policies.get(chain.get("policy"), chain.get("policy", "—")), str(counts.get((family, table, name), 0)),
        )
        for (family, table, name), chain in sorted(chains.items())
    ]
    return sum(counts.values()), rows


def firewall_snapshot():
    return describe_firewall(json.loads(read_command("sudo", "-n", "--", "/usr/sbin/nft", "-j", "list", "ruleset")))


def journal_records(raw):
    records = []
    for line in raw.splitlines():
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(entry, dict):
            continue
        message = entry.get("MESSAGE", "")
        if isinstance(message, list):
            message = "İkili günlük verisi"
        unit = entry.get("_SYSTEMD_UNIT") or entry.get("SYSLOG_IDENTIFIER") or "Sistem"
        try:
            priority = int(entry.get("PRIORITY", 6))
            if not 0 <= priority <= 7:
                priority = 6
        except (TypeError, ValueError):
            priority = 6
        try:
            stamp = datetime.fromtimestamp(int(entry["__REALTIME_TIMESTAMP"]) / 1_000_000).strftime("%H:%M:%S")
        except (KeyError, TypeError, ValueError, OSError, OverflowError):
            stamp = "—"
        records.append((stamp, str(unit), priority, str(message)[:4000]))
    return records


def journal_snapshot():
    return journal_records(read_command(
        "sudo", "-n", "--", "/usr/bin/journalctl", "--boot=0", "--quiet", "--no-pager",
        "--output=json", f"--lines={JOURNAL_LIMIT}",
    ))


@dataclass(frozen=True)
class UsbDrive:
    path: str
    device: str
    size: int
    model: str


def usb_drives():
    data = json.loads(read_command(
        "/usr/bin/lsblk", "--json", "--bytes", "--paths", "--nodeps",
        "--output", "NAME,TYPE,TRAN,RM,SIZE,MODEL,MAJ:MIN",
    ))
    return [
        UsbDrive(row["name"], row["maj:min"], int(row["size"]), (row.get("model") or "USB bellek").strip())
        for row in data["blockdevices"]
        if row["type"] == "disk" and (row.get("tran") == "usb" or row.get("rm") is True)
    ]


def hash_prefix(source, size, cancel):
    digest = sha256()
    remaining = size
    while remaining:
        if cancel.is_set():
            raise ReportStopped
        block = source.read(min(remaining, 1024 * 1024))
        if not block:
            raise ValueError("Veri beklenen boyuta ulaşmadan sona erdi.")
        digest.update(block)
        remaining -= len(block)
    return digest.hexdigest()


def stamped_file_hash(path, stamp, cancel):
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), "rb") as source:
        info = os.fstat(source.fileno())
        if not stat.S_ISREG(info.st_mode) or (info.st_dev, info.st_ino) != stamp[:2]:
            raise ValueError("Dosya okuma başlamadan değişti.")
        digest = hash_prefix(source, stamp[2], cancel)
    if file_stamp(path) != stamp:
        raise ValueError("Dosya okunurken değişti.")
    if cancel.is_set():
        raise ReportStopped
    return digest


def compare_usb(path, device, size):
    drive = next((drive for drive in usb_drives() if (drive.path, drive.device) == (path, device)), None)
    if drive is None or not 0 < size <= drive.size:
        raise ValueError("USB aygıtı değişti veya ISO, aygıttan büyük.")
    with os.fdopen(os.open(drive.path, os.O_RDONLY | os.O_NOFOLLOW), "rb") as source:
        info = os.fstat(source.fileno())
        number = f"{os.major(info.st_rdev)}:{os.minor(info.st_rdev)}"
        if not stat.S_ISBLK(info.st_mode) or number != drive.device:
            raise ValueError("Seçilen USB aygıtı artık bağlı değil.")
        return hash_prefix(source, size, Event())


def read_usb_hash(drive, size, cancel):
    command = ["sudo", "-n", "--", "/usr/local/lib/kage/usb-checksum", drive.path, drive.device, str(size)]
    with subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          text=True) as process:
        while process.poll() is None:
            if cancel.wait(0.12) and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                raise ReportStopped
        output, errors = process.communicate()
        if process.returncode:
            raise ValueError(errors.strip() or "USB okunamadı.")
        checksum = expected_sha256(output)
        if checksum is None:
            raise ValueError("USB özeti alınamadı.")
        return checksum


def verify_media(filename, expected, drive, cancel):
    filename = regular_file(filename, "ISO dosyası")
    expected = expected_sha256(expected)
    original = file_stamp(filename)
    size = original[2]
    if not size:
        raise ValueError("ISO dosyası boş.")
    if drive and size > drive.size:
        raise ValueError("ISO dosyası seçilen USB aygıtından büyük.")

    result = stamped_file_hash(filename, original, cancel)
    usb_hash = read_usb_hash(drive, size, cancel) if drive else None
    if file_stamp(filename) != original:
        raise ValueError("ISO dosyası doğrulama sırasında değişti.")
    if cancel.is_set():
        raise ReportStopped
    return result, None if expected is None else result == expected, None if usb_hash is None else usb_hash == result
