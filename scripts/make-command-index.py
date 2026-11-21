#!/usr/bin/env python3
"""Build a compact offline command index from authenticated Debian Contents."""

import argparse
from collections import defaultdict
import gzip
from hashlib import file_digest
from pathlib import Path
import re
import subprocess
import tempfile


CONTENTS_NAME = "main/Contents-amd64.gz"
COMMAND = re.compile(r"(?:usr/)?s?bin/([A-Za-z0-9][A-Za-z0-9_.+-]{0,127})")
PACKAGE = re.compile(r"[a-z0-9][a-z0-9+.-]+")


def authenticate(release, contents):
    with tempfile.TemporaryDirectory(prefix="kage-release-") as work:
        signed = Path(work) / "Release"
        subprocess.run(
            ["sqv", "--keyring", "/usr/share/keyrings/debian-archive-keyring.pgp",
             "--output", str(signed), "--cleartext", str(release)],
            check=True, stdout=subprocess.DEVNULL,
        )
        data = signed.read_text(encoding="utf-8")
    if not re.search(r"^Codename: trixie$", data, re.M):
        raise SystemExit("Debian Trixie yayın kaydı gerekli.")
    section = data.partition("\nSHA256:\n")[2].split("\nSHA512:", 1)[0]
    expected = next((line.split()[0] for line in section.splitlines() if line.endswith(" " + CONTENTS_NAME)), "")
    with contents.open("rb") as source:
        actual = file_digest(source, "sha256").hexdigest()
    if expected != actual:
        raise SystemExit("İmzalı yayın kaydındaki Contents özeti eşleşmedi.")
    return actual


def collect(contents):
    commands = defaultdict(set)
    with gzip.open(contents, "rt", encoding="utf-8", errors="replace") as source:
        for line in source:
            fields = line.rsplit(maxsplit=1)
            if len(fields) != 2 or not (match := COMMAND.fullmatch(fields[0])):
                continue
            for location in fields[1].split(","):
                candidate = location.rsplit("/", 1)[-1]
                if PACKAGE.fullmatch(candidate):
                    commands[match[1]].add(candidate)
    return commands


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("release", type=Path)
    parser.add_argument("contents", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    digest = authenticate(args.release, args.contents)
    commands = collect(args.contents)
    if not commands:
        raise SystemExit("Contents dosyasında komut bulunamadı.")
    with tempfile.TemporaryDirectory(dir=args.output.parent) as work:
        temporary = Path(work) / args.output.name
        with temporary.open("wb") as target:
            with gzip.GzipFile(filename="", mode="wb", fileobj=target, mtime=0) as index:
                index.write(f"# Debian trixie main amd64 · Contents SHA-256 {digest}\n".encode())
                for name, packages in sorted(commands.items()):
                    index.write(f"{name}\t{' '.join(sorted(packages))}\n".encode())
        temporary.chmod(0o644)
        temporary.replace(args.output)
    print(f"{len(commands)} komut adı indekslendi.")


if __name__ == "__main__":
    main()
