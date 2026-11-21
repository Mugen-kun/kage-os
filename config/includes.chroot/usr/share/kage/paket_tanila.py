"""Read-only package diagnostics and an optional connection test to Debian."""

from dataclasses import dataclass
from datetime import datetime
import json
import os
from pathlib import Path
import re
import subprocess

from sistem import APT_LISTS


PACKAGE = re.compile(r"[a-z0-9][a-z0-9+.-]{1,119}(?::[a-z0-9][a-z0-9-]{0,19})?")
LOCKS = (
    Path("/var/lib/dpkg/lock-frontend"),
    Path("/var/lib/dpkg/lock"),
    APT_LISTS / "lock",
    Path("/var/cache/apt/archives/lock"),
)
DEBIAN_HOST = "deb.debian.org"
DEBIAN_INDEX = "https://deb.debian.org/debian/dists/trixie/InRelease"
CACHE_OPTIONS = ("-o", "Dir::Cache::pkgcache=", "-o", "Dir::Cache::srcpkgcache=")
READY = "Hazır"
CHECK = "Kontrol et"
BLOCKED = "Sorun var"
UNKNOWN = "Belirlenemedi"


@dataclass(frozen=True)
class Finding:
    name: str
    state: str
    detail: str


ERRORS = (
    (("could not get lock", "unable to acquire the dpkg frontend lock"),
     "Kilit", "Başka bir paket işlemi çalışıyor. Bitince tekrar dene."),
    (("temporary failure resolving", "could not resolve"),
     "DNS", "Depo adı çözümlenemedi. Ağ bağlantısını ve DNS’i denetle."),
    (("network is unreachable", "could not connect", "connection timed out"),
     "Bağlantı", "Depoya bağlanılamadı. Bağlantıyı ve varsa proxy ayarını kontrol et."),
    (("certificate verification failed", "ssl certificate problem", "certificate is not trusted"),
     "Sertifika", "HTTPS sertifikası doğrulanamadı. Sistem saatini ve CA sertifikalarını kontrol et."),
    (("not valid yet", "release file is expired", "invalid for another"),
     "Depo tarihi", "Depo yayım zamanı doğrulanamadı. Sistem saatini kontrol et ve listeleri yenile."),
    (("no_pubkey", "expkeysig", "badsig", "signature verification failed", "is not signed", "hash sum mismatch"),
     "İmza veya bütünlük", "Debian deposunu ve imza anahtarını kontrol et, ardından listeleri yenile."),
    (("404 not found", "does not have a release file"),
     "Depo adresi", "Depo adresini ve Debian sürümünü kontrol et. Kage’nin tabanı Debian 13 (trixie)."),
    (("no space left on device", "not enough free space"),
     "Boş alan", "APT’nin yazdığı diskte yer aç ve işlemi tekrarla."),
    (("read-only file system",),
     "Salt okunur depolama", "APT’nin kullandığı yazılabilir dosya sistemini kontrol et."),
    (("dpkg was interrupted",),
     "Yarım kurulum", "Bekleyen paket yapılandırmasını yönetici olarak tamamla. Synaptic’te paket durumunu denetle."),
    (("unmet dependencies", "held broken packages", "pkgproblemresolver"),
     "Bağımlılıklar", "Paket bağımlılıkları çözümlenemedi. Synaptic’te bekletilen veya bozuk paketleri kontrol et."),
    (("unable to locate package", "has no installation candidate"),
     "Paket adayı", "Paket adı veya etkin depolar kontrol edilmeli. Paket listelerini yenile."),
)


def classify_error(output):
    lower = output.casefold()
    return next(((category, solution) for needles, category, solution in ERRORS
                 if any(needle in lower for needle in needles)), None)


def run(*arguments, timeout=6):
    return subprocess.run(
        arguments, capture_output=True, text=True, errors="replace",
        env=dict(os.environ, LC_ALL="C"), timeout=timeout,
    )


def locks_in_use(raw, targets):
    found = set()
    for line in raw.splitlines():
        fields = line.split()
        if len(fields) < 8 or fields[1] == "->":
            continue
        try:
            major, minor, inode = fields[5].split(":")
            identity = int(major, 16), int(minor, 16), int(inode)
        except ValueError:
            continue
        if identity in targets:
            found.add(targets[identity])
    return found


def lock_finding():
    targets = {}
    for path in LOCKS:
        try:
            info = path.stat()
        except FileNotFoundError:
            continue
        except OSError:
            return Finding("APT kilidi", UNKNOWN, "Paket yöneticisinin kilit dosyaları okunamadı.")
        targets[(os.major(info.st_dev), os.minor(info.st_dev), info.st_ino)] = path.name
    try:
        raw = Path("/proc/locks").read_text(encoding="ascii", errors="replace")
    except OSError:
        return Finding("APT kilidi", UNKNOWN, "Çekirdek kilit bilgisi okunamadı.")
    active = sorted(locks_in_use(raw, targets))
    if active:
        return Finding("APT kilidi", BLOCKED, "Başka bir paket işlemi sürüyor. Bitince tekrar dene. " + ", ".join(active))
    return Finding("APT kilidi", READY, "Paket yöneticisinin izlenen kilitleri boşta.")


def storage_finding():
    folders = (("Paket listeleri", APT_LISTS), ("Paket önbelleği", Path("/var/cache/apt/archives")))
    report = []
    state = READY
    for title, path in folders:
        try:
            info = os.statvfs(path)
        except OSError:
            report.append(f"{title} için alan bilgisi okunamadı.")
            if state == READY:
                state = UNKNOWN
            continue
        free = info.f_bavail * info.f_frsize
        readonly = bool(info.f_flag & os.ST_RDONLY)
        full = free == 0 or (info.f_files and info.f_favail == 0)
        report.append(f"{title} · {free / 1024**2:.0f} MiB boş.")
        if readonly or full:
            state = BLOCKED
            report.append("Bu dosya sistemi salt okunur." if readonly else "Kullanılabilir alan veya dosya girdisi kalmadı.")
    return Finding("Depolama", state, " ".join(report))


def route_finding():
    known = False
    for family in ("-4", "-6"):
        try:
            result = run("/usr/bin/ip", "-j", family, "route", "show", "default", timeout=3)
            routes = json.loads(result.stdout) if result.returncode == 0 else None
        except (OSError, ValueError, subprocess.SubprocessError):
            continue
        if isinstance(routes, list):
            known = True
            if routes:
                return Finding("Varsayılan rota", READY, "Sistemde IPv4 veya IPv6 varsayılan rotası var.")
    if known:
        return Finding("Varsayılan rota", CHECK, "Varsayılan rota yok. İnternet depoları için ağ bağlantısını kontrol et.")
    return Finding("Varsayılan rota", UNKNOWN, "Yerel rota tablosu okunamadı.")


def clock_finding():
    local_time = datetime.now().astimezone().strftime("%d.%m.%Y %H:%M %Z")
    try:
        value = run("/usr/bin/timedatectl", "show", "-p", "NTPSynchronized", "--value", timeout=3).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        value = ""
    if value == "yes":
        return Finding("Sistem saati", READY, f"{local_time} · Saat eşitlenmiş.")
    if value == "no":
        return Finding("Sistem saati", CHECK, f"{local_time} · Saat eşitlenmemiş. Tarih ve saati doğrula.")
    return Finding("Sistem saati", UNKNOWN, f"{local_time} · Eşitleme durumu okunamadı.")


def index_finding():
    if not next(APT_LISTS.glob("*_Packages*"), None):
        return Finding("Paket listeleri", BLOCKED, "Yerel APT listesi bulunamadı. Güncellemeler’den depoları yenile.")
    return Finding("Paket listeleri", READY, "Yerel paket listesi mevcut.")


def package_findings(name):
    if not PACKAGE.fullmatch(name):
        raise ValueError("Tek bir Debian paket adı yaz. Örneğin tree veya curl:amd64.")
    try:
        policy = run("/usr/bin/apt-cache", *CACHE_OPTIONS, "policy", "--", name, timeout=12)
    except (OSError, subprocess.SubprocessError):
        return [Finding("Paket adayı", UNKNOWN, f"{name} için yerel APT sorgusu tamamlanamadı.")]
    versions = {}
    for line in policy.stdout.splitlines():
        key, _, value = line.strip().partition(":")
        if key in {"Installed", "Candidate"}:
            versions[key] = value.strip()
    candidate = versions.get("Candidate", "(none)")
    if policy.returncode:
        classified = classify_error(policy.stderr)
        detail = classified[1] if classified else "APT yapılandırmasını Güncellemeler’deki APT ayrıntılarından kontrol et."
        return [Finding("Paket adayı", UNKNOWN, detail)]
    if candidate == "(none)":
        return [Finding("Paket adayı", BLOCKED, f"{name} için aday sürüm yok. Adı kontrol et ve depoları yenile.")]
    installed = versions.get("Installed", "(none)")
    version = f" · Kurulu {installed}" if installed != "(none)" else ""
    findings = [Finding("Paket adayı", READY, f"{name} · Aday {candidate}{version}")]
    try:
        plan = run("/usr/bin/apt-get", *CACHE_OPTIONS, "--simulate", "--no-remove", "install", "--", name, timeout=15)
    except (OSError, subprocess.SubprocessError):
        return findings + [Finding("Kurulum önizlemesi", UNKNOWN, "APT kurulum planını süresinde çıkaramadı.")]
    if plan.returncode:
        classified = classify_error(plan.stdout + "\n" + plan.stderr)
        detail = classified[1] if classified else "APT kurulum planı başarısız. APT ayrıntıları veya Synaptic ile incele."
        return findings + [Finding("Kurulum önizlemesi", BLOCKED, detail)]
    changes = sum(line.startswith("Inst ") for line in plan.stdout.splitlines())
    report = f"Kurulum veya yükseltme bekleyen {changes} paket." if changes else "Gerekli paket sürümü zaten hazır."
    return findings + [Finding("Kurulum önizlemesi", READY, report)]


def connection_findings():
    try:
        dns = run("/usr/bin/getent", "ahosts", DEBIAN_HOST, timeout=5)
        resolved = dns.returncode == 0 and bool(dns.stdout.strip())
        lookup = Finding("Debian DNS", READY if resolved else BLOCKED,
                         "deb.debian.org çözümlendi." if resolved else "deb.debian.org çözümlenemedi. DNS ayarını kontrol et.")
    except subprocess.TimeoutExpired:
        lookup = Finding("Debian DNS", CHECK, "Debian DNS sorgusu 5 saniyede yanıt vermedi.")
    except (OSError, subprocess.SubprocessError):
        lookup = Finding("Debian DNS", UNKNOWN, "Debian DNS denetimi tamamlanamadı.")
    try:
        web = run("/usr/bin/curl", "--disable", "--proto", "=https", "--head", "--max-time", "6",
                  "--silent", "--show-error", "--output", "/dev/null", "--write-out", "%{http_code}",
                  DEBIAN_INDEX, timeout=8)
    except (OSError, subprocess.SubprocessError):
        return [lookup, Finding("Debian HTTPS", UNKNOWN, "HTTPS denetimi tamamlanamadı.")]
    code = web.stdout.strip()
    if web.returncode == 0 and code == "200":
        return [lookup, Finding("Debian HTTPS", READY, "Resmî Debian dizinine doğrulanmış HTTPS bağlantısı kuruldu.")]
    if web.returncode in {51, 60, 77}:
        detail = "Sertifika doğrulanamadı. Sistem saatini ve CA sertifikalarını kontrol et."
    elif web.returncode == 28:
        detail = "Debian HTTPS bağlantısı zaman aşımına uğradı. Ağı ve varsa proxy ayarını kontrol et."
    elif web.returncode == 0:
        detail = f"Debian dizini HTTP {code} yanıtını verdi." if re.fullmatch(r"[0-9]{3}", code) else "Depo yanıtı okunamadı."
    else:
        classified = classify_error(web.stderr)
        detail = classified[1] if classified else "Resmî Debian dizinine bağlanılamadı. Ağ bağlantısını kontrol et."
    return [lookup, Finding("Debian HTTPS", BLOCKED, detail)]


def diagnose(package="", *, online=False, previous_error=""):
    package = package.strip()
    if package and not PACKAGE.fullmatch(package):
        raise ValueError("Tek bir Debian paket adı yaz. Örneğin tree veya curl:amd64.")
    result = [lock_finding(), storage_finding(), index_finding(), route_finding(), clock_finding()]
    if previous_error and (failure := classify_error(previous_error)):
        result.insert(0, Finding("Son APT hatası", BLOCKED, f"{failure[0]} · {failure[1]}"))
    if package:
        result.extend(package_findings(package))
    if online:
        result.extend(connection_findings())
    return result
