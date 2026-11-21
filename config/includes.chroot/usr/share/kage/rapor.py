"""Kage'nin yerel, salt okunur inceleme komutlarını ve raporlarını yönetir."""

from datetime import datetime
from pathlib import Path
import re
import subprocess
import tempfile
import threading


REPORT_NAMES = {
    "pcap": "protokoller.txt",
    "interfaces": "ag-arayuzleri.txt",
    "sha256": "sha256.txt",
    "yara": "yara-eslesmeleri.txt",
    "partitions": "bolum-tablosu.txt",
    "metadata": "meta-veri.txt",
}
STOPPED = "İşlem durduruldu."


class ReportStopped(Exception):
    """İnceleme kullanıcı tarafından durduruldu."""


def regular_file(value, label):
    if not value:
        raise ValueError(f"{label} seç.")
    path = Path(value).resolve(strict=True)
    if not path.is_file():
        raise ValueError(f"{label} sıradan bir dosya olmalı.")
    return path


def expected_sha256(value):
    text = (value or "").strip()
    if not text:
        return None
    # Also accept the first field of a copied line from a sha256sum file.
    checksum = text.split(maxsplit=1)[0].removeprefix("\\")
    if not re.fullmatch(r"[a-fA-F0-9]{64}", checksum):
        raise ValueError("Beklenen SHA-256 değeri 64 onaltılık karakter olmalı.")
    return checksum.lower()


def command_for(action, source, rules):
    if action == "pcap":
        return ["tshark", "-n", "-r", str(source), "-q", "-z", "io,phs", "-z", "endpoints,ip", "-z", "endpoints,ipv6"]
    if action == "interfaces":
        return ["ip", "-brief", "address"]
    if action == "sha256":
        return ["sha256sum", "--", str(source)]
    if action == "yara":
        return ["yara", str(rules), str(source)]
    if action == "partitions":
        return ["mmls", str(source)]
    return ["exiftool", "-G1", "-s", str(source)]


def run_command(command, stdout, stderr, cancel):
    if cancel.is_set():
        raise ReportStopped
    with subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr) as process:
        while process.poll() is None:
            if cancel.wait(0.1) and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                raise ReportStopped
        return process.returncode


def file_stamp(source):
    info = source.stat()
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns


def create_report(action, filename, rules_filename, parent, *, expected=None, cancel=None):
    if action not in REPORT_NAMES:
        raise ValueError("Bilinmeyen inceleme işlemi.")
    source = regular_file(filename, "İncelenecek dosyayı") if action != "interfaces" else None
    rules = regular_file(rules_filename, "YARA kural dosyasını") if action == "yara" else None
    expected = expected_sha256(expected) if action == "sha256" else None
    original_stamp = file_stamp(source) if action == "sha256" else None
    cancel = cancel if cancel is not None else threading.Event()

    parent = Path(parent)
    parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    now = datetime.now().astimezone()
    folder = Path(tempfile.mkdtemp(prefix=f"{now:%Y%m%d-%H%M%S}-{action}-", dir=parent))
    report = folder / REPORT_NAMES[action]
    errors = folder / "uyarilar.txt"
    context = [f"Tarih {now.isoformat(timespec='seconds')}"]
    if source:
        context.append(f"Kaynak {source}")
    if rules:
        context.append(f"Kurallar {rules}")
    if expected:
        context.append(f"Beklenen SHA-256 {expected}")
    summary = folder / "islem.txt"

    try:
        with report.open("xb") as stdout, errors.open("xb") as stderr:
            code = run_command(command_for(action, source, rules), stdout, stderr, cancel)
        if code:
            report.rename(folder / ("tamamlanmayan-" + report.name))
            message = f"İşlem hata koduyla sonlandı ({code}). Ayrıntılar rapor klasöründe."
        elif action == "sha256" and file_stamp(source) != original_stamp:
            report.unlink()
            message = "Dosya işlem sırasında değişti. Özet geçersiz."
        elif expected:
            with report.open("rb") as digest:
                actual = digest.read(65).lstrip(b"\\")[:64].decode("ascii")
            message = "SHA-256 eşleşti." if actual == expected else "SHA-256 eşleşmedi."
        else:
            if action == "yara" and report.stat().st_size == 0:
                report.write_text("YARA eşleşmesi bulunamadı.\n", encoding="utf-8")
            message = "Rapor hazır."
    except ReportStopped:
        report.unlink(missing_ok=True)
        message = STOPPED
    except OSError as error:
        report.unlink(missing_ok=True)
        with errors.open("a", encoding="utf-8", errors="backslashreplace") as warning:
            warning.write(f"{error}\n")
        message = "İşlem tamamlanamadı. Ayrıntılar rapor klasöründe."

    if errors.stat().st_size == 0:
        errors.unlink()
    context.append(f"Durum {message}")
    summary.write_text("\n".join(context) + "\n", encoding="utf-8", errors="backslashreplace")
    return folder, message
