"""Read and search portable, local reference material."""

from html.parser import HTMLParser
from pathlib import Path
import tempfile
from threading import Event
from zipfile import BadZipFile, ZipFile

from arac_metin import normalize
from gunluk_dosyalar import check_cancel, file_digest, publish_file, staged_file
from rapor import regular_file, run_command


TYPES = {".txt", ".md", ".pdf", ".epub"}
ASSETS = Path(__file__).resolve().parent
CHAPTER_LIMIT = 2 * 1024 * 1024


def library_directory():
    return Path.home() / "Kage-Kitaplik"


def import_books(paths, cancel):
    root = library_directory()
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    saved = []
    for value in paths:
        check_cancel(cancel)
        source = regular_file(value, "Kitaplık dosyasını")
        if source.suffix.lower() not in TYPES:
            raise ValueError("Kitaplık TXT, Markdown, PDF ve EPUB dosyalarını destekler.")
        if source.parent == root.resolve():
            continue
        with staged_file(root) as temporary:
            with source.open("rb") as original, temporary.open("wb") as copy:
                file_digest(original, cancel, copy)
            check_cancel(cancel)
            saved.append(publish_file(temporary, root, source.name))
    return saved


class ChapterText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.hidden += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style"} and self.hidden:
            self.hidden -= 1
        elif tag in {"h1", "h2", "h3", "p", "div", "li"}:
            self.parts.append("\n")

    def handle_data(self, text):
        if not self.hidden:
            self.parts.append(text)


def document_lines(path, cancel):
    if path.suffix.lower() == ".pdf":
        with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as errors:
            if run_command(["pdftotext", str(path), "-"], output, errors, cancel):
                raise ValueError("PDF metni okunamadı.")
            output.seek(0)
            while line := output.readline(65536):
                yield line.decode("utf-8", errors="replace")
    elif path.suffix.lower() == ".epub":
        with ZipFile(path) as archive:
            for member in archive.infolist():
                check_cancel(cancel)
                if not member.filename.lower().endswith((".htm", ".html", ".xhtml")) or member.file_size > CHAPTER_LIMIT:
                    continue
                chapter = ChapterText()
                chapter.feed(archive.read(member).decode("utf-8", errors="replace"))
                yield from "".join(chapter.parts).splitlines()
    else:
        with path.open("r", encoding="utf-8", errors="replace") as stream:
            while line := stream.readline(65536):
                yield line


def book_preview(path, limit=600_000):
    remaining = limit
    excerpts = []
    for line in document_lines(path, Event()):
        text = " ".join(line.split())
        if text:
            excerpts.append(text[:remaining])
            remaining -= len(text) + 2
            if remaining < 1:
                return "\n\n".join(excerpts), True
    return "\n\n".join(excerpts), False


def search_library(query, cancel):
    terms = normalize(query).split()
    if not terms:
        raise ValueError("Aranacak bir kelime veya ifade yaz.")
    root = library_directory()
    documents = [ASSETS / "gunluk/mini-sozluk.txt", ASSETS / "Kage-Kullanim.txt"]
    documents += [path for path in sorted(root.glob("*")) if path.is_file() and path.suffix.lower() in TYPES]
    results, errors = [], []
    for path in documents:
        matches = 0
        try:
            for content in document_lines(path, cancel):
                check_cancel(cancel)
                line = " ".join(content.split())
                normalized = normalize(line)
                if all(term in normalized for term in terms):
                    first = max(0, normalized.find(terms[0]) - 50)
                    excerpt = ("…" if first else "") + line[first:first + 260]
                    results.append((path, excerpt))
                    matches += 1
                    if matches >= 10 or len(results) >= 100:
                        break
        except (BadZipFile, OSError, ValueError, RuntimeError) as error:
            errors.append(f"{path.name} · {error}")
        if len(results) >= 100:
            break
    return results, errors
