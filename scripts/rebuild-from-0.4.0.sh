#!/usr/bin/env bash
set -Eeuo pipefail

project="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
if [[ $EUID -ne 0 || $# -lt 1 || $# -gt 2 ]]; then
    printf 'Kullanım: sudo %s KAGE_0.4.0_ISO [ÇIKTI_DİZİNİ]\n' "$0" >&2
    exit 2
fi
for tool in xorriso mksquashfs python3; do
    command -v "$tool" >/dev/null || { printf 'Derleme aracı bulunamadı: %s\n' "$tool" >&2; exit 1; }
done
base="$(realpath -- "$1")"
output="${2:-$project/dist}"
python3 "$project/scripts/pack-iso.py" --check-base "$base"
work="$(mktemp -d "${TMPDIR:-/var/tmp}/kage-release.XXXXXXXX")"
cleanup() {
    status=$?
    trap - EXIT
    if mountpoint -q "$work/base"; then
        if ! umount "$work/base"; then
            printf 'Bağlı çalışma dizini: %s\n' "$work" >&2
            exit 1
        fi
    fi
    rm -rf --one-file-system -- "$work"
    exit "$status"
}
trap cleanup EXIT
mkdir -- "$work/base" "$work/rootfs"
xorriso -osirrox on -indev "$base" -extract /live/filesystem.squashfs "$work/base.squashfs" -end
mount -t squashfs -o loop,ro,nosuid,nodev "$work/base.squashfs" "$work/base"
"$project/scripts/prepare-rootfs.sh" "$work/base" "$work/rootfs"
python3 "$project/scripts/pack-iso.py" "$base" "$work/rootfs" "$output"
