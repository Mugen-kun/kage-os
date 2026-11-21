#!/usr/bin/env bash
set -euo pipefail

project="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
version="$(<"$project/VERSION")"
image="kage-${version}-amd64"
output="${1:-$project/dist}"

if [[ $EUID != 0 ]]; then
    printf 'Debian 13 amd64 üzerinde sudo ./build.sh çalıştırın.\n' >&2
    exit 1
fi

if [[ $(dpkg --print-architecture) != amd64 ]]; then
    printf 'Bu yapılandırma bir amd64 Debian derleme ortamı gerektiriyor.\n' >&2
    exit 1
fi

for tool in lb debootstrap xorriso mksquashfs; do
    if ! command -v "$tool" >/dev/null; then
        printf 'Derleme aracı bulunamadı: %s. README.md içindeki paketleri kurun.\n' "$tool" >&2
        exit 1
    fi
done
(cd "$project/config/includes.chroot/usr/share/kage/firefox" && sha256sum -c ublock-origin.xpi.sha256)

mkdir -p -- "$output"
output="$(realpath -- "$output")"
work="$(mktemp -d "${TMPDIR:-/var/tmp}/kage-build.XXXXXXXX")"
printf 'Derleme dizini: %s\n' "$work"
cd -- "$work"
cp -a -- "$project/config" .

mirror="${KAGE_BUILD_MIRROR:-https://deb.debian.org/debian}"
security="${KAGE_BUILD_SECURITY_MIRROR:-https://deb.debian.org/debian-security}"

boot_args="boot=live components hostname=kage username=kage user-fullname=Kage locales=tr_TR.UTF-8 keyboard-layouts=tr"

lb config \
    --mode debian \
    --distribution trixie \
    --architectures amd64 \
    --linux-flavours amd64 \
    --binary-images iso-hybrid \
    --bootloaders "syslinux grub-efi" \
    --debian-installer none \
    --archive-areas "main non-free-firmware" \
    --apt-recommends false \
    --apt-indices true \
    --apt-source-archives false \
    --firmware-binary false \
    --firmware-chroot false \
    --chroot-filesystem squashfs \
    --chroot-squashfs-compression-type zstd \
    --chroot-squashfs-compression-level 12 \
    --iso-application "Kage OS $version" \
    --iso-publisher "Kage OS" \
    --iso-volume "KAGE_${version//./_}" \
    --image-name "kage-$version" \
    --mirror-bootstrap "$mirror" \
    --mirror-chroot "$mirror" \
    --mirror-chroot-security "$security" \
    --mirror-binary https://deb.debian.org/debian \
    --mirror-binary-security https://deb.debian.org/debian-security \
    --bootappend-live "$boot_args quiet" \
    --bootappend-live-failsafe "$boot_args nomodeset noapic noapm nodma nomce nosmp nosplash"

lb build

if [[ ! -s "${image}.hybrid.iso" ]]; then
    printf 'ISO dosyası bulunamadı. Derleme dizini: %s\n' "$work" >&2
    exit 1
fi

iso_temp="$(mktemp "$output/.kage-iso.XXXXXXXX")"
sum_temp="$(mktemp "$output/.kage-sha256.XXXXXXXX")"
trap 'rm -f -- "$iso_temp" "$sum_temp"' EXIT
install -m 0644 "${image}.hybrid.iso" "$iso_temp"
checksum="$(sha256sum < "$iso_temp")"
printf '%s  %s.iso\n' "${checksum%% *}" "$image" > "$sum_temp"
chmod 0644 "$sum_temp"
mv -f -- "$iso_temp" "$output/$image.iso"
mv -f -- "$sum_temp" "$output/$image.iso.sha256"
printf 'ISO: %s/%s.iso\n' "$output" "$image"

if lb clean --purge && ! findmnt -rn -o TARGET | awk -v dir="$work/" 'index($0, dir) == 1 { found = 1 } END { exit !found }'; then
    cd /
    rm -rf --one-file-system -- "$work"
else
    printf 'Derleme artıkları %s dizininde duruyor.\n' "$work" >&2
fi
