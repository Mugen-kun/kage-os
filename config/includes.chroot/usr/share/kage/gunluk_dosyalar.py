"""On-demand file conversions and verified folder copies."""

from dataclasses import dataclass
from hashlib import sha256
from itertools import count
from pathlib import Path
from contextlib import contextmanager
import ctypes
import errno
import os
import re
import shutil
import stat
import subprocess
import tempfile

from rapor import ReportStopped, regular_file, run_command


BLOCK_SIZE = 1024 * 1024
AT_FDCWD = -100
RENAME_NOREPLACE = 1
FORMATS = {
    "pdf": {".pdf"},
    "photo": {".jpg", ".jpeg", ".png"},
    "video": {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"},
}
RENAME = ctypes.CDLL(None, use_errno=True).renameat2
RENAME.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint)
RENAME.restype = ctypes.c_int


@contextmanager
def staged_file(folder):
    descriptor, name = tempfile.mkstemp(prefix=".kage-", suffix=".part", dir=folder)
    temporary = Path(name)
    try:
        os.close(descriptor)
        yield temporary
    finally:
        temporary.unlink(missing_ok=True)


def publish_file(temporary, folder, filename):
    """Move a finished file into view without replacing an existing name."""
    name = Path(filename)
    maximum = os.pathconf(folder, "PC_NAME_MAX")
    for index in count(1):
        ending = name.suffix if index == 1 else f"-{index}{name.suffix}"
        available = maximum - len(os.fsencode(ending))
        stem = name.stem
        if len(os.fsencode(stem)) > available:
            stem = os.fsencode(stem)[:available].decode("utf-8", errors="ignore")
        proposed = folder / (stem + ending)
        if RENAME(AT_FDCWD, os.fsencode(temporary), AT_FDCWD, os.fsencode(proposed), RENAME_NOREPLACE) == 0:
            return proposed
        error = ctypes.get_errno()
        if error != errno.EEXIST:
            raise OSError(error, os.strerror(error), str(proposed))


def require_directory(path):
    if not path:
        raise ValueError("Bir klasör seç.")
    folder = Path(path).resolve(strict=True)
    if not folder.is_dir():
        raise ValueError("Bir klasör seç.")
    return folder


def check_cancel(cancel):
    if cancel.is_set():
        raise ReportStopped


def run_tool(command, cancel):
    with tempfile.TemporaryFile() as errors:
        status = run_command(command, subprocess.DEVNULL, errors, cancel)
        if status:
            size = errors.tell()
            errors.seek(max(0, size - 1500))
            detail = errors.read().decode("utf-8", errors="replace").strip()
            raise ValueError(detail or f"{command[0]} işlemi tamamlayamadı.")


def pdf_range(text):
    match = re.fullmatch(r"([1-9][0-9]{0,5})(?:\s*-\s*([1-9][0-9]{0,5}))?", text.strip())
    if not match:
        raise ValueError("Sayfa numarası veya 2-5 biçiminde bir aralık yaz.")
    first = int(match[1])
    last = int(match[2] or match[1])
    if last < first or last - first >= 1000:
        raise ValueError("Bir işlemde artan sırayla en fazla 1000 sayfalık bir aralık seç.")
    return first, last


def extract_pdf(source, temporary, pages, cancel):
    first, last = pages
    with tempfile.TemporaryDirectory(prefix=".kage-sayfalar-", dir=temporary.parent) as work:
        directory = Path(work)
        run_tool(["pdfseparate", "-f", str(first), "-l", str(last), str(source), str(directory / "%d.pdf")], cancel)
        extracted = [directory / f"{page}.pdf" for page in range(first, last + 1)]
        if not all(page.is_file() for page in extracted):
            raise ValueError("Seçilen sayfaların tamamı bu PDF’de bulunamadı.")
        run_tool(["pdfunite", *map(str, extracted), str(temporary)], cancel)


def resize_photo(source, temporary, dimension):
    import gi

    gi.require_version("GdkPixbuf", "2.0")
    from gi.repository import GdkPixbuf, GLib

    try:
        _format, width, height = GdkPixbuf.Pixbuf.get_file_info(str(source))
        if min(width, height) < 1:
            raise ValueError("Fotoğrafın boyutu okunamadı.")
        photo = GdkPixbuf.Pixbuf.new_from_file_at_scale(str(source), min(dimension, max(width, height)),
                                                        min(dimension, max(width, height)), True)
        photo = photo.apply_embedded_orientation() or photo
        if source.suffix.lower() == ".png":
            photo.savev(str(temporary), "png", [], [])
        else:
            photo.savev(str(temporary), "jpeg", ["quality"], ["88"])
    except GLib.Error as error:
        raise ValueError(error.message) from error


def export_files(action, paths, target, setting, cancel):
    target = require_directory(target)
    pages = pdf_range(setting) if action == "pdf" else None
    if action == "video" and not shutil.which("ffmpeg"):
        raise ValueError("Video dönüştürmek için ffmpeg paketini kur.")
    outputs, failures = [], []
    for value in paths:
        try:
            check_cancel(cancel)
            source = regular_file(value, "Kaynak dosyayı")
            suffix = source.suffix.lower()
            if suffix not in FORMATS[action]:
                raise ValueError("Bu işlem için dosya biçimi desteklenmiyor.")
            with staged_file(target) as temporary:
                if action == "pdf":
                    extract_pdf(source, temporary, pages, cancel)
                    name = f"{source.stem}-sayfa-{pages[0]}-{pages[1]}.pdf"
                elif action == "photo":
                    resize_photo(source, temporary, int(setting))
                    name = f"{source.stem}-kucuk{suffix}"
                else:
                    run_tool([
                        "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
                        "-protocol_whitelist", "file,pipe", "-i", str(source),
                        "-map", "0:v:0", "-map", "0:a:0?", "-sn", "-dn",
                        "-vf", "scale='trunc(min(1280,iw)/2)*2':-2", "-c:v", "libx264",
                        "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p", "-threads", "2",
                        "-c:a", "aac", "-movflags", "+faststart", "-f", "mp4", str(temporary),
                    ], cancel)
                    name = f"{source.stem}-telefon.mp4"
                check_cancel(cancel)
                outputs.append(publish_file(temporary, target, name))
        except ReportStopped:
            return outputs, failures, True
        except (OSError, ValueError) as error:
            failures.append(f"{Path(value).name} · {error}")
    return outputs, failures, False


def stat_signature(info):
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns


def directory_contents(folder, cancel, errors):
    for directory, subfolders, files in os.walk(folder, onerror=lambda error: errors.append(str(error))):
        check_cancel(cancel)
        base = Path(directory)
        subfolders[:] = sorted(name for name in subfolders if not (base / name).is_symlink())
        for name in sorted(files):
            check_cancel(cancel)
            path = base / name
            try:
                info = path.lstat()
                if stat.S_ISREG(info.st_mode):
                    yield path, stat_signature(info)
            except OSError as error:
                errors.append(str(error))


@dataclass(frozen=True)
class CopyPlan:
    source: Path
    destination: Path
    entries: tuple
    unreadable: tuple

    @property
    def size(self):
        return sum(stamp[2] for _name, stamp in self.entries)


def plan_copy(source, destination, cancel):
    source = require_directory(source)
    destination = require_directory(destination)
    if destination.is_relative_to(source):
        raise ValueError("Hedef için kaynak klasörün dışında bir konum seç.")
    errors = []
    entries = tuple((path.relative_to(source), stamp) for path, stamp in directory_contents(source, cancel, errors))
    return CopyPlan(source, destination, entries, tuple(errors))


def file_digest(stream, cancel, output=None):
    digest = sha256()
    while data := stream.read(BLOCK_SIZE):
        check_cancel(cancel)
        digest.update(data)
        if output is not None:
            output.write(data)
    return digest.digest()


def copy_one(source, stamp, destination, cancel):
    if source.resolve(strict=True) != source:
        raise ValueError("Kaynak dosya taşınmış veya bağlantıya dönüşmüş.")
    with staged_file(destination.parent) as temporary:
        fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as original, temporary.open("wb") as copy:
            info = os.fstat(original.fileno())
            if not stat.S_ISREG(info.st_mode) or stat_signature(info) != stamp:
                raise ValueError("Kaynak dosya plan oluşturulduktan sonra değişmiş.")
            expected = file_digest(original, cancel, copy)
            if stat_signature(os.fstat(original.fileno())) != stamp:
                raise ValueError("Kaynak dosya kopyalanırken değişmiş.")
        with temporary.open("rb") as copy:
            if file_digest(copy, cancel) != expected:
                raise ValueError("Kopyanın SHA-256 değeri eşleşmedi.")
        check_cancel(cancel)
        temporary.replace(destination)


def run_copy(plan, cancel):
    check_cancel(cancel)
    if not plan.entries:
        raise ValueError("Kopyalanacak dosya bulunamadı.")
    if shutil.disk_usage(plan.destination).free < plan.size:
        raise ValueError("Hedefte yeterli boş alan yok.")
    folder = Path(tempfile.mkdtemp(prefix="Kage-Kurtarma-", dir=plan.destination))
    done = 0
    errors = list(plan.unreadable)
    stopped = False
    for relative, stamp in plan.entries:
        try:
            check_cancel(cancel)
            target = folder / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            copy_one(plan.source / relative, stamp, target, cancel)
            done += 1
        except ReportStopped:
            stopped = True
            break
        except (ValueError, OSError) as error:
            errors.append(f"{relative} · {error}")
    return folder, done, errors, stopped
