"""Read visible hardware and firmware diagnostics from the current system."""

from pathlib import Path
import re
import shlex
import subprocess

from bakim import read_command
from sistem import command_output, read_text


SYS = Path("/sys")
FIRMWARE = re.compile(
    r"(?:direct firmware load for\s+|firmware:\s+failed to load\s+|failed to load firmware\s+)"
    r"(?P<file>[^\s:]+).*?(?:error\s+-2\b|\(-2\)|\bENOENT\b|not found|no such file)",
    re.IGNORECASE,
)


def pci_names(raw):
    names = {}
    for line in raw.splitlines():
        try:
            fields = shlex.split(line)
        except ValueError:
            continue
        if len(fields) >= 4:
            names[fields[0]] = f"{fields[2]} {fields[3]}"
    return names


def driver_name(device):
    try:
        return (device / "driver").readlink().name
    except OSError:
        return "Sürücü bağlı değil"


def firmware_warnings(log):
    return list(dict.fromkeys(match["file"] for match in FIRMWARE.finditer(log)))


def hardware_rows(sys=SYS, names=None):
    if names is None:
        names = pci_names(command_output("lspci", "-Dmm"))
    rows = []
    for device in sorted((sys / "bus/pci/devices").glob("*")):
        kind = read_text(device / "class")
        if kind.startswith("0x02"):
            category = "Ağ"
        elif kind.startswith("0x03"):
            category = "Ekran"
        elif kind.startswith(("0x0401", "0x0403")):
            category = "Ses denetleyicisi"
        else:
            continue
        name = names.get(device.name) or f"{read_text(device / 'vendor')}:{read_text(device / 'device')}"
        rows.append((category, name, driver_name(device)))
    for interface in sorted((sys / "class/net").glob("*")):
        device = interface / "device"
        if (interface / "wireless").is_dir() or (interface / "phy80211").exists():
            rows.append(("Wi-Fi", interface.name, driver_name(device)))
        elif device.exists():
            rows.append(("Ağ arayüzü", interface.name, driver_name(device)))
    for card in sorted((sys / "class/sound").glob("card[0-9]*")):
        rows.append(("Ses kartı", read_text(card / "id") or card.name, driver_name(card / "device")))
    return rows


def hardware_snapshot():
    try:
        log = read_command(
            "sudo", "-n", "--", "/usr/bin/journalctl", "--boot=0", "--dmesg", "--quiet",
            "--no-pager", "--output=cat", "--lines=800",
        )
    except (OSError, ValueError, subprocess.SubprocessError):
        warnings = None
    else:
        warnings = firmware_warnings(log)
    return hardware_rows(), warnings
