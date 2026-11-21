"""Describe and verify the baseline commands visible in the current PATH."""

import argparse
import gzip
from pathlib import Path
import re
import shutil
import sys


INDEX = Path(__file__).with_name("terminal-komutlari.list")
OFFLINE_INDEX = Path(__file__).with_name("debian-komutlar.tsv.gz")
COMMAND = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.+-]{0,127}")


def command_packages():
    packages = {}
    for line in INDEX.read_text(encoding="utf-8").splitlines():
        entry = line.partition("#")[0].split()
        if entry:
            command, package = entry
            if command in packages:
                raise ValueError(f"Komut listesinde yinelenen kayıt: {command}")
            packages[command] = package
    if not packages:
        raise ValueError("Terminal komut listesi boş.")
    return packages


def suggested_packages(command, baseline):
    if not COMMAND.fullmatch(command):
        return []
    if command in baseline:
        return [baseline[command]]
    try:
        with gzip.open(OFFLINE_INDEX, "rt", encoding="utf-8") as source:
            for line in source:
                if line.startswith("#"):
                    continue
                name, _, packages = line.partition("\t")
                if name == command:
                    return packages.split()
                if name > command:
                    break
    except (OSError, EOFError):
        pass
    return []


def main():
    parser = argparse.ArgumentParser(description="Kage terminal komutlarını bu oturumun PATH değeriyle denetle.")
    parser.add_argument("komut", nargs="*", help="Belirli komutları denetle. Boş bırakılırsa Kage’nin komut listesi denetlenir.")
    parser.add_argument("--oner", metavar="KOMUT", help="Komut bulunamadığında Debian paket adını göster.")
    args = parser.parse_args()
    packages = command_packages()
    if args.oner is not None:
        names = suggested_packages(args.oner, packages)
        hint = f" · Debian paketleri {', '.join(names)}" if names else ""
        print(f"Komut bulunamadı {args.oner!r}{hint}", file=sys.stderr)
        return 127
    commands = list(dict.fromkeys(args.komut)) if args.komut else packages
    missing = 0
    for command in commands:
        path = shutil.which(command)
        if path:
            if args.komut:
                print(f"{command}\t{path}")
            continue
        missing += 1
        names = suggested_packages(command, packages)
        hint = f" · Debian paketleri {', '.join(names)}" if names else ""
        print(f"Eksik: {command}{hint}", file=sys.stderr)
    print(f"Terminal denetimi · {len(commands) - missing}/{len(commands)} komut hazır.")
    return int(bool(missing))


if __name__ == "__main__":
    raise SystemExit(main())
