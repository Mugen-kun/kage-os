#!/usr/bin/env python3
"""Build the signed, architecture-independent Kage Toolbox metapackages."""

import argparse
from email.utils import formatdate
import gzip
from hashlib import sha256
from pathlib import Path
import re
import subprocess
import sys
import tempfile


PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "config/includes.chroot/usr/share/kage"))
from toolbox import BUNDLE, GROUPS


def run(*arguments, **kwargs):
    return subprocess.run(arguments, check=True, **kwargs)


def package(group, version, stage):
    with tempfile.TemporaryDirectory(prefix="kage-package-") as work:
        assembly = Path(work)
        debian = assembly / "DEBIAN"
        debian.mkdir()
        assembly.chmod(0o755)
        debian.chmod(0o755)
        control = "\n".join((
            f"Package: {group.name}", f"Version: {version}", "Architecture: all",
            "Section: metapackages", "Priority: optional", "Installed-Size: 1",
            "Maintainer: Kage OS <kage-os@localhost>",
            "Depends: " + ", ".join(group.packages),
            f"Description: {group.title} için Kage OS araçları",
            " " + group.description,
        )) + "\n"
        control_file = debian / "control"
        control_file.write_text(control, encoding="utf-8")
        control_file.chmod(0o644)
        relative = Path("pool/main/k/kage-toolbox") / f"{group.name}_{version}_all.deb"
        target = stage / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        run("dpkg-deb", "--root-owner-group", "--build", str(assembly), str(target), stdout=subprocess.DEVNULL)
        return control + f"Filename: {relative}\nSize: {target.stat().st_size}\nSHA256: {sha256(target.read_bytes()).hexdigest()}\n"


def build(output, fingerprint, home):
    version = (PROJECT / "VERSION").read_text().strip()
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise ValueError("Çıktı için yeni bir dizin seç.")
    with tempfile.TemporaryDirectory(prefix=".toolbox-", dir=output.parent) as work:
        stage = Path(work) / "repository"
        distribution = stage / "dists/trixie"
        index = distribution / "main/binary-amd64/Packages"
        index.parent.mkdir(parents=True)
        data = "\n".join(package(group, version, stage) for group in (*GROUPS.values(), BUNDLE)).encode()
        index.write_bytes(data)
        compressed = index.with_suffix(".gz")
        compressed.write_bytes(gzip.compress(data, mtime=0))
        sums = "\n".join(
            f" {sha256(item.read_bytes()).hexdigest()} {item.stat().st_size:15d} {item.relative_to(distribution)}"
            for item in (index, compressed)
        )
        release = distribution / "Release"
        release.write_text(
            "Origin: Kage OS\nLabel: Kage Toolbox\nSuite: trixie\nCodename: trixie\n"
            f"Architectures: amd64\nComponents: main\nDate: {formatdate(usegmt=True)}\nSHA256:\n{sums}\n",
            encoding="utf-8",
        )
        gpg = ["gpg", "--batch", "--no-tty", "--homedir", str(home)]
        for signature, method in (("InRelease", "--clearsign"), ("Release.gpg", "--detach-sign")):
            run(*gpg, "--local-user", fingerprint, "--digest-algo", "SHA256", "--output",
                str(distribution / signature), method, str(release))
        with (stage / "kage-toolbox.gpg").open("wb") as key:
            run(*gpg, "--export", fingerprint, stdout=key)
        for item in (stage, *stage.rglob("*")):
            item.chmod(0o755 if item.is_dir() else 0o644)
        stage.rename(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--key", required=True, help="Full fingerprint of the signing key")
    parser.add_argument("--gnupg-home", required=True, type=Path)
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Fa-f0-9]{40}|[A-Fa-f0-9]{64}", args.key):
        parser.error("--key requires a full OpenPGP fingerprint")
    build(args.output.resolve(), args.key, args.gnupg_home.resolve())


if __name__ == "__main__":
    main()
