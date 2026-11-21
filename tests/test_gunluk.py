from http.client import HTTPConnection
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from urllib.parse import quote
from zipfile import ZipFile
import sys
import unittest
from unittest.mock import patch


source = Path(__file__).resolve().parents[1] / "config/includes.chroot/usr/share/kage"
sys.path.insert(0, str(source))

from gunluk_dosyalar import pdf_range, plan_copy, publish_file, run_copy, staged_file
from kitaplik import book_preview, import_books, search_library
from masaustu import theme_for_hour
from paylasim import ShareSession


class EverydayTests(unittest.TestCase):
    def test_page_ranges_and_outputs_never_replace_an_existing_file(self):
        self.assertEqual(pdf_range("3 - 5"), (3, 5))
        self.assertEqual(pdf_range("1"), (1, 1))
        for invalid in ("0", "3-2", "1-1001", "first"):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                pdf_range(invalid)
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            (folder / "çıktı.pdf").write_text("original")
            with staged_file(folder) as temporary:
                temporary.write_text("new")
                result = publish_file(temporary, folder, "çıktı.pdf")
            self.assertEqual(result.name, "çıktı-2.pdf")
            self.assertEqual(result.read_text(), "new")
            self.assertEqual((folder / "çıktı.pdf").read_text(), "original")
            self.assertEqual(len(list(folder.iterdir())), 2)

    def test_recovery_copies_nested_files_and_skips_changed_or_linked_sources(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "Belgeler"
            destination = root / "Hedef"
            (source / "Fotoğraflar").mkdir(parents=True)
            destination.mkdir()
            photo = source / "Fotoğraflar/a.jpg"
            photo.write_bytes(b"Original photo bytes")
            changed = source / "not.txt"
            changed.write_bytes(b"An old note")
            (source / "bağlantı").symlink_to(photo)
            with self.assertRaises(ValueError):
                plan_copy(source, source / "Fotoğraflar", Event())
            plan = plan_copy(source, destination, Event())
            self.assertEqual(len(plan.entries), 2)
            self.assertEqual(plan.size, len(photo.read_bytes()) + len(changed.read_bytes()))
            changed.write_text("A revised note")
            folder, copied, errors, stopped = run_copy(plan, Event())
            self.assertEqual(copied, 1)
            self.assertEqual(len(errors), 1)
            self.assertFalse(stopped)
            self.assertEqual((folder / "Fotoğraflar/a.jpg").read_bytes(), photo.read_bytes())
            self.assertFalse((folder / "not.txt").exists())
            self.assertFalse((folder / "bağlantı").exists())
            self.assertFalse(list(folder.rglob("*.part")))

    def test_offline_library_imports_and_searches_epubs_without_running_html(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            ebook = root / "Kitap.epub"
            with ZipFile(ebook, "w") as archive:
                archive.writestr("book/1.xhtml", "<p>Gökçe'nin çalışma notları.</p><script>sakli</script>")
            library = root / "Kage-Kitaplik"
            with patch("kitaplik.library_directory", return_value=library):
                saved, = import_books([ebook], Event())
                self.assertEqual(saved.read_bytes(), ebook.read_bytes())
                results, errors = search_library("gokce calisma", Event())
                self.assertEqual(results, [(saved, "Gökçe'nin çalışma notları.")])
                self.assertEqual(errors, [])
                self.assertEqual(search_library("sakli", Event())[0], [])
                self.assertTrue(any("sözlük" in hit for _path, hit in search_library("dictionary", Event())[0]))
                self.assertEqual(book_preview(saved), ("Gökçe'nin çalışma notları.", False))

    def test_automatic_theme_resolves_local_clock_boundaries(self):
        self.assertEqual([theme_for_hour(hour) for hour in (0, 6, 7, 18, 19, 23)],
                         ["koyu", "koyu", "acik", "acik", "koyu", "koyu"])

    def test_phone_transfer_uses_only_the_session_url_and_explicit_files(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            file = root / "notlar.txt"
            file.write_bytes(b"Phone fixture")
            for_upload = root / "Gelen"
            for_upload.mkdir()
            session = ShareSession("127.0.0.1/8", [file], for_upload)
            try:
                def request(method, path, body=None, headers=None):
                    connection = HTTPConnection(session.endpoint, timeout=2)
                    try:
                        connection.request(method, path, body=body, headers=headers or {})
                        reply = connection.getresponse()
                        return reply.status, reply.read()
                    finally:
                        connection.close()

                self.assertEqual(request("GET", "/")[0], 404)
                self.assertEqual(request("GET", session.prefix, headers={"Host": "fixture.invalid"})[0], 404)
                self.assertEqual(request("GET", session.prefix)[0], 200)
                self.assertEqual(request("GET", session.prefix + "download/0"), (200, b"Phone fixture"))
                self.assertEqual(request("GET", session.prefix + "download/1")[0], 404)
                self.assertEqual(request("GET", session.prefix + "%2e%2e/download/0")[0], 404)
                upload = session.prefix + "upload"
                self.assertEqual(request("POST", upload, b"data", {"X-Kage-Filename": "..%2Fnotlar.txt"})[0], 400)
                self.assertEqual(request("POST", upload, b"data", {"X-Kage-Filename": "a.txt", "Origin": "https://other.invalid"})[0], 404)
                for payload in (b"first", b"second"):
                    status, result = request("POST", upload, payload, {"X-Kage-Filename": quote("Sınav.pdf")})
                    self.assertEqual(status, 201, result)
                self.assertEqual((for_upload / "Sınav.pdf").read_bytes(), b"first")
                self.assertEqual((for_upload / "Sınav-2.pdf").read_bytes(), b"second")
                self.assertEqual(sorted(path.name for path in for_upload.iterdir()), ["Sınav-2.pdf", "Sınav.pdf"])
                self.assertEqual(file.read_bytes(), b"Phone fixture")
            finally:
                session.close()
            self.assertEqual(session.remaining, 0)

    def test_phone_session_expires_without_an_open_window(self):
        with TemporaryDirectory() as directory:
            session = ShareSession("127.0.0.1/8", [], directory, lifetime=0.12)
            try:
                self.assertTrue(session.ended.wait(timeout=2))
                self.assertEqual(session.remaining, 0)
            finally:
                session.close()
