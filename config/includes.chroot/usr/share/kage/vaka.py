"""Local case records and report folders indexed by a generated identifier."""

from datetime import datetime, timezone
from fcntl import LOCK_EX, flock
import json
from pathlib import Path
import re
import tempfile
import uuid
from urllib.parse import urlsplit

from bakim import stamped_file_hash
from rapor import ReportStopped, file_stamp, regular_file


def case_root():
    return Path.home() / "Kage-Vakalar"


def timestamp():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def case_path(case_id):
    if not isinstance(case_id, str) or not re.fullmatch(r"vaka-[a-f0-9]{32}", case_id):
        raise ValueError("Vaka kimliği geçersiz.")
    path = case_root() / case_id
    if not path.is_dir() or path.is_symlink():
        raise ValueError("Vaka klasörü bulunamadı.")
    return path


def read_case(path):
    with (path / "vaka.json").open(encoding="utf-8") as stream:
        data = json.load(stream)
    fields = ("path", "name", "kind", "sha256", "added")
    if not isinstance(data, dict) or not isinstance(data.get("name"), str) or not isinstance(data.get("files"), list):
        raise ValueError("Vaka kayıt dosyasının biçimi geçersiz.")
    if any(not isinstance(item, dict) or not isinstance(item.get("size"), int)
           or any(not isinstance(item.get(key), str) for key in fields) for item in data["files"]):
        raise ValueError("Vakanın dosya kayıtlarının biçimi geçersiz.")
    return data


def write_case(path, data):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", dir=path, prefix=".vaka-", encoding="utf-8", delete=False
        ) as stream:
            temporary = Path(stream.name)
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        temporary.replace(path / "vaka.json")
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)


def list_cases():
    names = [
        (path.name, read_case(path)["name"])
        for path in case_root().glob("vaka-*")
        if re.fullmatch(r"vaka-[a-f0-9]{32}", path.name) and not path.is_symlink() and (path / "vaka.json").is_file()
    ]
    return sorted(names, key=lambda entry: entry[1].casefold())


def create_case(name):
    name = name.strip()
    if not name or len(name) > 80 or any(ord(char) < 32 for char in name):
        raise ValueError("Vaka adı 1–80 karakter olmalı.")
    case_root().mkdir(mode=0o700, parents=True, exist_ok=True)
    path = case_root() / f"vaka-{uuid.uuid4().hex}"
    path.mkdir(mode=0o700)
    (path / "raporlar").mkdir(mode=0o700)
    write_case(path, {"name": name, "created": timestamp(), "files": []})
    return path.name


def report_destination(case_id):
    path = case_path(case_id)
    destination = path / "raporlar"
    if not destination.is_dir() or destination.is_symlink():
        raise ValueError("Vakanın rapor klasörü bulunamadı.")
    return read_case(path)["name"], destination


def file_kind(path):
    extension = path.suffix.lower()
    if extension in {".pcap", ".pcapng", ".cap"}:
        return "Ağ kaydı"
    if extension in {".iso", ".img", ".raw", ".dd", ".e01"}:
        return "Disk imajı"
    return "Dosya veya rapor"


def register_file(case_id, filename, cancel):
    folder = case_path(case_id)
    source = regular_file(filename, "Kaydedilecek dosya")
    stamp = file_stamp(source)
    digest = stamped_file_hash(source, stamp, cancel)
    entry = {"path": str(source), "name": source.name, "kind": file_kind(source),
             "sha256": digest, "size": stamp[2], "modified_ns": stamp[3], "added": timestamp()}
    with (folder / ".lock").open("ab") as lock:
        flock(lock, LOCK_EX)
        if cancel.is_set():
            raise ReportStopped
        data = read_case(folder)
        if any((item["path"], item["sha256"]) == (entry["path"], digest) for item in data["files"]):
            return False
        data["files"].append(entry)
        write_case(folder, data)
    return True


CTF_PROFILES = {"bash": "/bin/bash", "zsh": "/bin/zsh"}


def lab_link(text):
    url = text.strip()
    if not url or len(url) > 2048 or any(char.isspace() or ord(char) < 32 for char in url):
        raise ValueError("Laboratuvar için tek bir HTTP veya HTTPS adresi yaz.")
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username is not None or parsed.password is not None:
        raise ValueError("Laboratuvar bağlantısı kullanıcı bilgisi içermeyen bir HTTP veya HTTPS adresi olmalı.")
    return url


def workspace_values(notes="", links=(), shell="bash"):
    if shell not in CTF_PROFILES or not isinstance(notes, str) or len(notes) > 500_000:
        raise ValueError("CTF çalışma alanı kaydı geçersiz.")
    if not isinstance(links, (tuple, list)) or len(links) > 100 or any(not isinstance(url, str) for url in links):
        raise ValueError("Laboratuvar bağlantıları okunamadı.")
    urls = list(dict.fromkeys(lab_link(url) for url in links if url.strip()))
    return {"notes": notes, "links": urls, "shell": shell}


def read_workspace(case_id):
    values = read_case(case_path(case_id)).get("workspace", {})
    if not isinstance(values, dict):
        raise ValueError("CTF çalışma alanı kaydı geçersiz.")
    return workspace_values(values.get("notes", ""), values.get("links", ()), values.get("shell", "bash"))


def save_workspace(case_id, notes, links, shell):
    folder = case_path(case_id)
    values = workspace_values(notes, links, shell)
    with (folder / ".lock").open("ab") as lock:
        flock(lock, LOCK_EX)
        data = read_case(folder)
        data["workspace"] = values
        write_case(folder, data)
