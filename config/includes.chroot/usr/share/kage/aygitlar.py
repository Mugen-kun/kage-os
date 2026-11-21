"""Power profiles and per-application GPU selection."""

from dataclasses import dataclass
from pathlib import Path
import re
import shlex
import subprocess

from bakim import read_command
from donanim import SYS, driver_name, pci_names
from sistem import command_output, read_text
from tercihler import config_file, write_setting_file


POWER = {"power-saver": "Pil tasarrufu", "balanced": "Dengeli", "performance": "Performans"}
VENDORS = {"0x8086": "Intel", "0x1002": "AMD", "0x10de": "NVIDIA"}
MESA_DRIVERS = {"i915", "xe", "amdgpu", "radeon", "nouveau"}


def power_status():
    try:
        raw = read_command("/usr/bin/powerprofilesctl", "list")
        available = [match[1] for match in re.finditer(r"(?m)^\s*\*?\s*(power-saver|balanced|performance):\s*$", raw)]
        current = read_command("/usr/bin/powerprofilesctl", "get").strip()
    except (OSError, ValueError, subprocess.SubprocessError):
        return [], ""
    return available, current


def apply_power_profile(profile):
    if profile not in POWER or profile not in power_status()[0]:
        raise ValueError("Bu güç profili cihazda kullanılamıyor.")
    read_command("/usr/bin/powerprofilesctl", "set", profile)


def set_power(profile, authorize=None):
    try:
        apply_power_profile(profile)
    except ValueError as error:
        if not authorize or "org.freedesktop.DBus.Error.AccessDenied" not in str(error):
            raise
        authorize(profile)
    write_setting_file(config_file("guc-profili"), profile + "\n")


def restore_power():
    profile = read_text(config_file("guc-profili"))
    if profile in POWER and profile in power_status()[0]:
        read_command("/usr/bin/powerprofilesctl", "set", profile)


@dataclass(frozen=True)
class GPU:
    address: str
    vendor: str
    title: str
    driver: str


def graphics_devices(sysfs=SYS, names=None):
    if names is None:
        names = pci_names(command_output("lspci", "-Dmm"))
    rows = []
    for device in sorted((sysfs / "bus/pci/devices").glob("*")):
        if read_text(device / "class").startswith("0x03"):
            vendor_id = read_text(device / "vendor")
            vendor = VENDORS.get(vendor_id, vendor_id)
            title = names.get(device.name) or f"{vendor} {read_text(device / 'device')}"
            rows.append(GPU(device.name, vendor, title, driver_name(device)))
    return rows


def gpu_variables(device):
    if device.vendor == "NVIDIA" and device.driver == "nvidia":
        return {"__NV_PRIME_RENDER_OFFLOAD": "1", "__GLX_VENDOR_LIBRARY_NAME": "nvidia",
                "__VK_LAYER_NV_optimus": "NVIDIA_only"}
    if device.driver in MESA_DRIVERS and re.fullmatch(r"[a-f0-9]{4}:[a-f0-9]{2}:[a-f0-9]{2}\.[0-7]", device.address):
        address = device.address.replace(":", "_").replace(".", "_")
        return {"DRI_PRIME": "pci-" + address}
    return {}


def desktop_arguments(command, *, name="", desktop=""):
    fields = {"c": name, "k": desktop, "%": "%", "f": "", "F": "", "u": "", "U": ""}
    arguments = []
    for word in shlex.split(command):
        if word == "%i":
            continue

        def substitute(match):
            if match[1] not in fields:
                raise ValueError("Uygulama başlatıcısındaki alan desteklenmiyor.")
            return fields[match[1]]

        value = re.sub(r"%(.)", substitute, word)
        if value:
            arguments.append(value)
    if not arguments:
        raise ValueError("Uygulama komutu bulunamadı.")
    return arguments


def live_session():
    return "boot=live" in read_text("/proc/cmdline").split()


if __name__ == "__main__":
    restore_power()
