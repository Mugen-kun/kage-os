"""Package groups shared by Kage Merkez and the APT repository builder."""

from dataclasses import dataclass
import subprocess


@dataclass(frozen=True)
class PackageGroup:
    name: str
    title: str
    description: str
    packages: tuple[str, ...]


GROUPS = {
    "network": PackageGroup(
        "kage-tools-network", "Ağ analizi",
        "Kaydedilmiş ağ trafiğini incele ve bağlantı durumunu denetle.",
        ("wireshark", "tshark", "bind9-dnsutils", "ethtool"),
    ),
    "forensics": PackageGroup(
        "kage-tools-forensics", "Dijital inceleme",
        "Disk imajlarını, dosya bütünlüğünü ve meta verileri incele.",
        ("sleuthkit", "ewf-tools", "libimage-exiftool-perl", "gddrescue"),
    ),
    "office": PackageGroup(
        "kage-tools-office", "Ofis",
        "Writer ve Calc ile belge ve hesap tablosu düzenle.",
        ("libreoffice-writer", "libreoffice-calc", "libreoffice-l10n-tr"),
    ),
    "media": PackageGroup(
        "kage-tools-media", "Medya",
        "Salon ekranı için mpv ve telefon videosu hazırlamak için FFmpeg.",
        ("mpv", "ffmpeg"),
    ),
}
BUNDLE = PackageGroup(
    "kage-hack-tool", "Kage inceleme araçları",
    "Ağ analizi ve dijital inceleme paketlerini bir araya getirir.",
    (GROUPS["network"].name, GROUPS["forensics"].name),
)


def installed_packages():
    names = sorted({name for group in GROUPS.values() for name in (group.name, *group.packages)})
    result = subprocess.run(
        ["dpkg-query", "-W", "-f=${binary:Package}\t${db:Status-Status}\n", *names],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, timeout=8,
    )
    return {fields[0].partition(":")[0] for line in result.stdout.splitlines()
            if (fields := line.split("\t", 1))[1:] == ["installed"]}


def upgrade_command():
    return ["/usr/bin/apt-get", "--assume-yes", "--no-remove", "upgrade"]


def packages_to_install(groups):
    """Prefer the signed bundled metapackages when the index is available."""
    import apt

    cache = apt.Cache(memonly=True)
    packages = []
    for identifier in groups:
        group = GROUPS[identifier]
        candidate = cache[group.name].candidate if group.name in cache else None
        if candidate and any(origin.trusted and origin.origin == "Kage OS" for origin in candidate.origins):
            packages.append(group.name)
        else:
            packages.extend(group.packages)
    return list(dict.fromkeys(packages))
