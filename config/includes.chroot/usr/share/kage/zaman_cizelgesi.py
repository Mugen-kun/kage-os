"""Build a case timeline from local captures, exported journals and notes."""

import csv
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, DecimalException
from fcntl import LOCK_EX, flock
import json
from pathlib import Path
import tempfile

from bakim import stamped_file_hash
from gunluk_dosyalar import check_cancel, staged_file
from rapor import file_stamp, regular_file, run_command
from vaka import case_path, read_case, write_case


UTC = timezone.utc
EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
CAPTURES = {".pcap", ".pcapng", ".cap"}
SOURCE_LIMIT = 2_000
SOURCES_LIMIT = 16
CONTENT_LIMIT = 6_000


@dataclass(frozen=True)
class Event:
    time: datetime
    category: str
    source: str
    detail: str


def parse_time(value):
    try:
        event_time = datetime.fromisoformat(value.strip() if isinstance(value, str) else value)
        if event_time.utcoffset() is not None:
            return event_time.astimezone(UTC)
    except (TypeError, ValueError, OverflowError):
        pass
    raise ValueError("Saat farkı belirtilen bir tarih yaz. Örneğin 2026-11-20 13:30:00+03:00.")


def epoch_time(value, multiplier):
    if type(value) not in (str, int) or len(str(value)) > 32:
        raise ValueError("Geçersiz olay zamanı.")
    try:
        scaled = Decimal(value) * multiplier
        if not scaled.is_finite() or abs(scaled) > Decimal("316000000000000000"):
            raise ValueError("Geçersiz olay zamanı.")
        microseconds = int(scaled)
        return EPOCH + timedelta(microseconds=microseconds)
    except (DecimalException, OverflowError, ValueError) as error:
        raise ValueError("Geçersiz olay zamanı.") from error


def display_time(value):
    timespec = "microseconds" if value.microsecond else "seconds"
    return value.astimezone(UTC).isoformat(sep=" ", timespec=timespec).removesuffix("+00:00") + "Z"


def plain_text(value, max_length=1_000):
    return "".join(char if char.isprintable() or char in "\t\n" else " " for char in value[:max_length])


def case_notes(data):
    notes = data.get("timeline_notes", [])
    if not isinstance(notes, list) or any(not isinstance(note, dict) for note in notes):
        raise ValueError("Vaka zaman çizelgesindeki notlar okunamadı.")
    return notes


def add_note(case_id, when, content):
    note = plain_text(content.strip(), 2_001)
    if not note.strip() or len(note) > 2_000:
        raise ValueError("1–2.000 karakterlik bir not yaz.")
    time = parse_time(when).isoformat()
    folder = case_path(case_id)
    with (folder / ".lock").open("ab") as lock:
        flock(lock, LOCK_EX)
        data = read_case(folder)
        data["timeline_notes"] = case_notes(data) + [{"time": time, "text": note}]
        write_case(folder, data)


def capture_events(path, limit, cancel):
    command = [
        "tshark", "-n", "-r", str(path), "-c", str(limit + 1),
        "-T", "fields", "-E", "occurrence=f", "-e", "frame.time_epoch", "-e", "frame.number",
        "-e", "_ws.col.Protocol", "-e", "_ws.col.Info",
    ]
    with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as errors:
        if run_command(command, output, errors, cancel):
            raise ValueError("Paket kaydı TShark ile okunamadı.")
        output.seek(0)
        rows = []
        inspected = 0
        for raw in output:
            check_cancel(cancel)
            inspected += 1
            if inspected > limit:
                return rows, True
            fields = raw.decode("utf-8", errors="replace").rstrip("\n\r").split("\t", 3)
            if len(fields) != 4:
                continue
            try:
                when = epoch_time(fields[0], 1_000_000)
            except ValueError:
                continue
            detail = plain_text(f"Paket {fields[1]} · {fields[2]} · {fields[3]}")
            rows.append(Event(when, "Ağ kaydı", path.name, detail))
        return rows, False


def journal_events(path, limit, cancel):
    rows = []
    with path.open("rb") as stream:
        for index in range(limit + 1):
            check_cancel(cancel)
            line = stream.readline(65_537)
            if not line:
                return rows, False
            if index == limit or len(line) > 65_536:
                return rows, True
            try:
                data = json.loads(line)
                if not isinstance(data, dict):
                    continue
                time = epoch_time(data.get("__REALTIME_TIMESTAMP"), 1)
            except (ValueError, RecursionError):
                continue
            message = data.get("MESSAGE", "")
            if isinstance(message, list):
                message = "İkili günlük iletisi"
            unit = data.get("_SYSTEMD_UNIT") or data.get("SYSLOG_IDENTIFIER") or "Sistem"
            message = message if isinstance(message, str) else ""
            unit = unit if isinstance(unit, str) else "Sistem"
            rows.append(Event(time, "Sistem günlüğü", path.name, plain_text(f"{unit} · {message}")))
    return rows, False


def list_events(case_id, cancel):
    data = read_case(case_path(case_id))
    events, warnings = [], []

    def add_time(value, category, source, detail):
        try:
            stamp = parse_time(value)
        except ValueError:
            warnings.append(f"{source} · Geçersiz tarih atlandı.")
        else:
            events.append(Event(stamp, category, source, detail))

    if data.get("created"):
        add_time(data["created"], "Vaka", data["name"], "Vaka oluşturuldu.")
    for note in case_notes(data):
        check_cancel(cancel)
        text = note.get("text")
        if isinstance(text, str):
            add_time(note.get("time"), "Not", "Vaka notu", plain_text(text, 2_000))

    sources = 0
    source_rows = 0
    limited = False
    for entry in data["files"]:
        check_cancel(cancel)
        name = plain_text(entry["name"])
        add_time(entry["added"], "Dosya kaydı", name, f'{entry["kind"]} · SHA-256 {entry["sha256"]}')
        file_type = Path(entry["path"]).suffix.lower()
        reader = capture_events if file_type in CAPTURES else journal_events if file_type == ".jsonl" else None
        recorded_time = entry.get("modified_ns")
        if type(recorded_time) is int:
            try:
                events.append(Event(epoch_time(recorded_time, Decimal("0.001")), "Dosya zamanı", name,
                                    "Dosya vakaya eklenirken kaydedilen değiştirilme zamanı."))
            except ValueError:
                warnings.append(f"{name} · Dosya zamanı okunamadı.")
        if reader is None:
            continue
        if sources >= SOURCES_LIMIT or source_rows >= CONTENT_LIMIT:
            limited = True
            continue
        sources += 1
        maximum = min(SOURCE_LIMIT, CONTENT_LIMIT - source_rows)
        try:
            path = regular_file(entry["path"], "Vaka kaynağını")
            stamp = file_stamp(path)
            if stamp[2] != entry["size"]:
                raise ValueError("Kaynak kayıt sonrasında değişmiş. Yeni sürümü ayrı bir dosya kaydı olarak ekle.")
            if type(recorded_time) is int and stamp[3] != recorded_time:
                if stamped_file_hash(path, stamp, cancel) != entry["sha256"]:
                    raise ValueError("Kaynak kayıt sonrasında değişmiş. Yeni sürümü ayrı bir dosya kaydı olarak ekle.")
            if type(recorded_time) is not int:
                events.append(Event(epoch_time(stamp[3], Decimal("0.001")), "Dosya zamanı", name,
                                    "Eski vaka kaydındaki dosyanın güncel değiştirilme zamanı."))
            rows, clipped = reader(path, maximum, cancel)
            if file_stamp(path) != stamp:
                raise ValueError("Dosya okunurken değişti. Olaylar eklenmedi.")
            if not rows and not clipped:
                warnings.append(f"{name} · Zamanı okunabilen olay bulunamadı.")
            if clipped:
                warnings.append(f"{name} · Okuma sınırına ulaşıldı.")
            source_rows += len(rows)
            events.extend(rows)
        except (OSError, ValueError) as error:
            warnings.append(f"{name} · {error}")
    if limited:
        warnings.append("Büyük vakalarda içerik okuması 16 kaynak ve 6.000 olay ile sınırlıdır.")
    return sorted(events, key=lambda event: event.time), warnings


def csv_cell(value):
    # Treat note and packet text as literal cells in spreadsheet applications.
    if value.startswith(("\t", "\n", "\r")) or value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def export_csv(destination, rows):
    path = Path(destination)
    with staged_file(path.parent) as temporary:
        with temporary.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(("UTC", "Tür", "Kaynak", "Ayrıntı"))
            for event in rows:
                writer.writerow(csv_cell(value) for value in (
                    display_time(event.time), event.category, event.source, event.detail,
                ))
        temporary.replace(path)
