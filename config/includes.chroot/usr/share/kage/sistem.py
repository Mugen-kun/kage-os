"""Kage Merkez'in yerel sistem bilgileri ve güncelleme verileri."""

from datetime import datetime
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile


RUN_STAMP = Path("/run/kage/apt-listeleri-yenilendi")
EFI = Path("/sys/firmware/efi")
APT_LISTS = Path("/var/lib/apt/lists")
DPKG_STATUS = Path("/var/lib/dpkg/status")
SECURITY_INDEX = "*_dists_*security_*_Packages*"


def read_text(path):
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""


def command_output(*args):
    try:
        return subprocess.check_output(args, text=True, stderr=subprocess.DEVNULL, timeout=3).strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def boot_mode(efi=EFI):
    if not efi.is_dir():
        return "BIOS"
    states = {b"\x00": "kapalı", b"\x01": "açık"}
    for entry in (efi / "efivars").glob("SecureBoot-*"):
        try:
            with entry.open("rb") as variable:
                variable.seek(4)
                state = states.get(variable.read(1))
        except OSError:
            continue
        if state:
            return f"UEFI · Secure Boot {state}"
    return "UEFI"


def session_mode(arguments, mount, *, encrypted=False):
    args = arguments.split()
    if "boot=live" not in args:
        return "Yerel oturum"
    if "persistence" in args and (mount == "/home" or mount.startswith("/home/")):
        return "Canlı · Ev dizini şifreli kalıcı depolamada" if encrypted else "Canlı · Ev dizini kalıcı depolamada"
    if "persistence" in args:
        return "Canlı · Kalıcı ev dizini bulunamadı"
    return "Canlı · Geçici oturum"


def system_rows(home=None):
    home = Path.home() if home is None else Path(home)
    args = read_text("/proc/cmdline")
    mount = command_output("findmnt", "--noheadings", "--output", "TARGET", "--target", str(home))
    encrypted = False
    if mount == "/home" or mount.startswith("/home/"):
        source = command_output("findmnt", "--noheadings", "--output", "SOURCE", "--target", str(home))
        device = source.split("[", 1)[0]
        if device.startswith("/dev/"):
            encrypted = command_output("lsblk", "--nodeps", "--noheadings", "--output", "TYPE", device) == "crypt"
    processor = "Bilinmiyor"
    for line in read_text("/proc/cpuinfo").splitlines():
        key, _, value = line.partition(":")
        if key.strip() == "model name" and value.strip():
            processor = value.strip()
            break
    processor += f" · {os.cpu_count() or 1} mantıksal işlemci"

    ram = {}
    for line in read_text("/proc/meminfo").splitlines():
        key, _, value = line.partition(":")
        if key in {"MemAvailable", "MemTotal"} and value.strip():
            ram[key] = value.split()[0]
    try:
        memory = f'{int(ram["MemAvailable"]) / 1024**2:.1f} / {int(ram["MemTotal"]) / 1024**2:.1f} GiB kullanılabilir'
    except (ValueError, KeyError):
        memory = "Bilinmiyor"
    try:
        disk = shutil.disk_usage(home)
        storage = f"{disk.free / 1024**3:.1f} / {disk.total / 1024**3:.1f} GiB boş"
    except OSError:
        storage = "Bilinmiyor"
    try:
        os_name = platform.freedesktop_os_release().get("PRETTY_NAME", "Kage OS")
    except OSError:
        os_name = "Kage OS"
    return [
        ("Dağıtım", os_name),
        ("Oturum", session_mode(args, mount, encrypted=encrypted)),
        ("Açılış", boot_mode()),
        ("İşlemci", processor),
        ("Bellek", memory),
        ("Ev dizini depolaması", storage),
        ("Çekirdek", f"{platform.release()} · {platform.machine()}"),
    ]


def diagnostics():
    rows = []
    for service, title in [
        ("NetworkManager.service", "Ağ yöneticisi"),
        ("lightdm.service", "Oturum yöneticisi"),
        ("udisks2.service", "Disk hizmeti"),
    ]:
        state = command_output("systemctl", "show", "--property=ActiveState", "--value", service)
        labels = {"active": "Çalışıyor", "inactive": "Kapalı", "failed": "Hata", "activating": "Başlatılıyor"}
        rows.append((title, labels.get(state, "Bilinmiyor")))
    links = [
        read_text(net / "operstate")
        for net in Path("/sys/class/net").iterdir()
        if net.name != "lo"
    ] if Path("/sys/class/net").is_dir() else []
    rows.append(("Ağ arayüzleri", f"{links.count('up')} etkin / {len(links)} toplam"))
    return rows


def index_updated_at():
    try:
        return datetime.fromtimestamp(RUN_STAMP.stat().st_mtime).strftime("%d.%m.%Y %H:%M")
    except OSError:
        return ""


def security_update_available(package, compare):
    for version in package.versions:
        installed_to_version = compare(package.installed.version, version.version)
        version_to_candidate = compare(version.version, package.candidate.version)
        if installed_to_version >= 0 or version_to_candidate > 0:
            continue
        if any(
            origin.trusted and origin.origin == "Debian" and (
                origin.label == "Debian-Security" or (origin.codename or "").endswith("-security")
            )
            for origin in version.origins
        ):
            return True
    return False


def package_updates(*, security_only=False):
    pattern = SECURITY_INDEX if security_only else "*_Packages*"
    if not next(APT_LISTS.glob(pattern), None):
        return None
    updates = upgradable_packages()
    if security_only:
        from apt_pkg import version_compare

        updates = [package for package in updates if security_update_available(package, version_compare)]
    return update_rows(updates)


def upgradable_packages():
    import apt

    return [package for package in apt.Cache(memonly=True) if package.is_upgradable and package.installed and package.candidate]


def update_rows(updates):
    return sorted(
        (package.name, package.installed.version, package.candidate.version)
        for package in updates
    )


def package_snapshot():
    if not next(APT_LISTS.glob("*_Packages*"), None):
        return None, None
    updates = upgradable_packages()
    security = None
    if next(APT_LISTS.glob(SECURITY_INDEX), None):
        from apt_pkg import version_compare

        security = update_rows(package for package in updates if security_update_available(package, version_compare))
    return update_rows(updates), security


def package_index_state():
    state = []
    for path in (APT_LISTS, DPKG_STATUS):
        try:
            info = path.stat()
            state.append((info.st_ino, info.st_mtime_ns, info.st_ctime_ns))
        except OSError:
            state.append(None)
    return tuple(state)


def read_package_snapshot():
    result = subprocess.run([sys.executable, "-I", __file__, "--paket-durumu"], capture_output=True,
                            text=True, errors="replace", timeout=30)
    if result.returncode:
        raise ValueError(result.stderr.strip() or "APT bilgisi okunamadı.")
    return json.loads(result.stdout)


def save_diagnostics(destination, rows):
    destination = Path(destination)
    timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
    content = "\n".join(["Kage OS tanılama", timestamp, "", *(f"{key}\t{value}" for key, value in rows)])
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", dir=destination.parent, prefix=".kage-tanilama-", encoding="utf-8", delete=False
        ) as stream:
            temporary = Path(stream.name)
            stream.write(content + "\n")
        temporary.replace(destination)
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)


if __name__ == "__main__" and sys.argv[1:] == ["--paket-durumu"]:
    print(json.dumps(package_snapshot()))
