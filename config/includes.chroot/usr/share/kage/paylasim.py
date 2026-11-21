"""Temporary, opt-in file transfers on a selected local IPv4 interface."""

from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from ipaddress import IPv4Address, IPv4Interface, IPv4Network
import json
import os
from pathlib import Path
import re
import secrets
import socket
import stat
from threading import BoundedSemaphore, Event, Lock, Thread, Timer
import time
from urllib.parse import quote, unquote

from bakim import read_command
from gunluk_dosyalar import BLOCK_SIZE, publish_file, require_directory, staged_file, stat_signature
from rapor import regular_file


ASSETS = Path(__file__).resolve().parent / "gunluk"
SESSION_SECONDS = 10 * 60
MAX_FILE = 128 * 1024**2
MAX_RECEIVED = 256 * 1024**2
MAX_TRANSFERS = 32
PRIVATE_NETWORKS = tuple(map(IPv4Network, ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "169.254.0.0/16")))
PAGES = {
    "": ("telefon.html", "text/html; charset=utf-8"),
    "style.css": ("telefon.css", "text/css; charset=utf-8"),
    "app.js": ("telefon.js", "text/javascript; charset=utf-8"),
}


def local_addresses():
    data = json.loads(read_command("ip", "-j", "-4", "addr", "show", "up"))
    choices = []
    for interface in data:
        for address in interface.get("addr_info", ()):
            binding = IPv4Interface(f'{address["local"]}/{address["prefixlen"]}')
            if any(binding.ip in network for network in PRIVATE_NETWORKS):
                choices.append((interface["ifname"], binding))
    return choices


def filename_from_header(encoded):
    if not encoded or len(encoded) > 900:
        raise ValueError("Dosya adı geçersiz.")
    name = unquote(encoded, encoding="utf-8", errors="strict")
    if (not name.strip() or name != name.strip() or name.startswith(".")
            or "/" in name or "\\" in name or not name.isprintable() or len(name.encode("utf-8")) > 200):
        raise ValueError("Dosya adı geçersiz.")
    return name


class TransferServer(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 8

    def __init__(self, binding, session):
        self.session = session
        self.slots = BoundedSemaphore(8)
        self.requests_lock = Lock()
        self.active_requests = set()
        super().__init__((str(binding.ip), 0), TransferRequest)

    def verify_request(self, request, address):
        request.settimeout(15)
        return self.session.remaining > 0 and IPv4Address(address[0]) in self.session.binding.network

    def process_request(self, request, client_address):
        if self.slots.acquire(blocking=False):
            with self.requests_lock:
                self.active_requests.add(request)
            super().process_request(request, client_address)
        else:
            self.shutdown_request(request)

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            with self.requests_lock:
                self.active_requests.discard(request)
            self.slots.release()

    def disconnect(self):
        with self.requests_lock:
            for request in self.active_requests:
                try:
                    request.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass

    def handle_error(self, _request, _address):
        # A closed connection must not log the tokenized URL.
        pass


class ShareSession:
    def __init__(self, binding, outgoing, destination=None, *, lifetime=SESSION_SECONDS):
        self.binding = IPv4Interface(binding)
        if not self.binding.ip.is_loopback and not any(self.binding.ip in subnet for subnet in PRIVATE_NETWORKS):
            raise ValueError("Paylaşım için yerel bir IPv4 adresi seç.")
        self.destination = require_directory(destination) if destination else None
        self.outgoing = []
        for value in outgoing:
            source = regular_file(value, "Paylaşılacak dosyayı")
            try:
                source.name.encode("utf-8")
            except UnicodeError as error:
                raise ValueError("Paylaşılacak dosyanın adı UTF-8 olarak okunamadı.") from error
            self.outgoing.append((source, stat_signature(source.stat())))
        if not self.outgoing and not self.destination:
            raise ValueError("Gönderilecek dosya veya alınacak bir klasör seç.")
        self.prefix = f"/{secrets.token_urlsafe(20)}/"
        self.ended = Event()
        self.lock = Lock()
        self.received = []
        self.bytes_received = 0
        self.in_progress = 0
        self.pending_bytes = 0
        self.deadline = time.monotonic() + lifetime
        self.server = TransferServer(self.binding, self)
        self.endpoint = f"{self.binding.ip}:{self.server.server_port}"
        self.url = f"http://{self.endpoint}{self.prefix}"
        Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.15}, daemon=True).start()
        self.timer = Timer(lifetime, self.close)
        self.timer.daemon = True
        self.timer.start()

    @property
    def remaining(self):
        return 0 if self.ended.is_set() else max(0, self.deadline - time.monotonic())

    def reserve(self, size):
        with self.lock:
            if (not self.remaining or self.bytes_received + self.pending_bytes + size > MAX_RECEIVED
                    or self.in_progress + len(self.received) >= MAX_TRANSFERS):
                return False
            self.pending_bytes += size
            self.in_progress += 1
            return True

    def finish(self, size, received):
        with self.lock:
            self.in_progress -= 1
            self.pending_bytes -= size
            if received:
                self.bytes_received += size
                self.received.append(received)

    def received_count(self):
        with self.lock:
            return len(self.received)

    def close(self):
        with self.lock:
            if self.ended.is_set():
                return
            self.ended.set()
        self.timer.cancel()
        self.server.shutdown()
        self.server.disconnect()
        self.server.server_close()


class TransferRequest(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    @property
    def session(self):
        return self.server.session

    def route(self):
        session = self.session
        if not session.remaining or self.headers.get("Host") != session.endpoint or not self.path.startswith(session.prefix):
            self.send_error(HTTPStatus.NOT_FOUND)
            return None
        return self.path[len(session.prefix):]

    def headers_for(self, status, size, content_type, filename=None):
        self.send_response(status)
        self.send_header("Content-Length", str(size))
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy",
                         "default-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        if filename is not None:
            self.send_header("Content-Disposition", "attachment; filename*=UTF-8''" + quote(filename, safe=""))
        self.end_headers()

    def payload(self, data, mime, status=HTTPStatus.OK):
        self.headers_for(status, len(data), mime)
        self.wfile.write(data)

    def json(self, data, status=HTTPStatus.OK):
        self.payload(json.dumps(data, ensure_ascii=True).encode("utf-8"), "application/json", status)

    def do_GET(self):
        route = self.route()
        if route is None:
            return
        session = self.session
        if route in PAGES:
            name, mime = PAGES[route]
            self.payload((ASSETS / name).read_bytes(), mime)
        elif route == "files":
            self.json({"files": [source.name for source, _stamp in session.outgoing],
                       "receive": session.destination is not None, "limit": MAX_FILE,
                       "seconds": int(session.remaining)})
        elif (download := re.fullmatch(r"download/([0-9]{1,5})", route)) and int(download[1]) < len(session.outgoing):
            self.download(*session.outgoing[int(download[1])])
        else:
            self.send_error(HTTPStatus.NOT_FOUND)

    def download(self, source, expected):
        try:
            fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        except OSError:
            self.send_error(HTTPStatus.GONE)
            return
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or stat_signature(info) != expected:
                self.send_error(HTTPStatus.GONE)
                return
            self.headers_for(HTTPStatus.OK, info.st_size, "application/octet-stream", source.name)
            left = info.st_size
            while left > 0 and self.session.remaining:
                data = stream.read(min(BLOCK_SIZE, left))
                if not data:
                    break
                self.wfile.write(data)
                left -= len(data)

    def do_POST(self):
        route = self.route()
        if route is None:
            return
        session = self.session
        origin = self.headers.get("Origin")
        if route != "upload" or session.destination is None or (origin and origin != f"http://{session.endpoint}"):
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        fields = self.headers.get_all("Content-Length", [])
        if len(fields) != 1 or not re.fullmatch(r"[0-9]{1,9}", fields[0]) or self.headers.get("Transfer-Encoding"):
            self.send_error(HTTPStatus.LENGTH_REQUIRED)
            return
        size = int(fields[0])
        if size > MAX_FILE or not session.reserve(size):
            self.json({"error": "Dosya boyutu veya oturum kotası aşıldı."}, HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
            return
        saved = None
        try:
            name = filename_from_header(self.headers.get("X-Kage-Filename"))
            with staged_file(session.destination) as temporary:
                with temporary.open("wb") as output:
                    left = size
                    while left:
                        if not session.remaining:
                            raise ConnectionError("Paylaşım süresi doldu.")
                        data = self.rfile.read(min(65536, left))
                        if not data:
                            raise ConnectionError("Dosya eksik ulaştı.")
                        output.write(data)
                        left -= len(data)
                with session.lock:
                    if not session.remaining:
                        raise ConnectionError("Paylaşım süresi doldu.")
                    saved = publish_file(temporary, session.destination, name)
        except (ValueError, UnicodeError) as error:
            self.json({"error": str(error)}, HTTPStatus.BAD_REQUEST)
        except OSError:
            self.json({"error": "Bağlantı kesildi veya dosya kaydedilemedi."}, HTTPStatus.INTERNAL_SERVER_ERROR)
        else:
            self.json({"name": saved.name}, HTTPStatus.CREATED)
        finally:
            session.finish(size, saved)
