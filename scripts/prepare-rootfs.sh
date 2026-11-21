#!/usr/bin/env bash
set -Eeuo pipefail
export LC_ALL=C

project="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
if [[ $EUID -ne 0 || $# -ne 2 ]]; then
    printf 'Kullanım: sudo %s TABAN_DOSYA_SİSTEMİ ÇIKTI_DİZİNİ\n' "$0" >&2
    exit 2
fi
(cd "$project/config/includes.chroot/usr/share/kage/firefox" && sha256sum -c ublock-origin.xpi.sha256)
base="$(realpath -- "$1")"
if [[ $(<"$base/etc/kage-release") != 'Kage OS 0.4.0' ]]; then
    printf 'Taban dosya sistemi Kage OS 0.4.0 olmalı.\n' >&2
    exit 1
fi
mkdir -p -- "$2"
output="$(realpath -- "$2")"
work="$(mktemp -d "${KAGE_BUILD_WORKDIR:-${TMPDIR:-/var/tmp}}/kage-rootfs.XXXXXXXX")"
temporary="$(mktemp -d "$output/.kage-rootfs.XXXXXXXX")"
image="$work/merged"

cleanup() {
    status=$?
    trap - EXIT
    for path in run sys proc dev; do
        if mountpoint -q "$image/$path"; then umount -R "$image/$path" || status=1; fi
    done
    if mountpoint -q "$image"; then umount "$image" || status=1; fi
    if mountpoint -q "$image"; then
        printf 'Bağlı çalışma dizini: %s\n' "$work" >&2
    else
        if mountpoint -q "$work" && ! umount "$work"; then
            printf 'Bağlı çalışma dizini: %s\n' "$work" >&2
            status=1
        else
            rm -rf --one-file-system -- "$work"
        fi
    fi
    rm -rf --one-file-system -- "$temporary"
    exit "$status"
}
trap cleanup EXIT

# A live session already uses OverlayFS. Its writable layer cannot back another overlay.
if [[ $(findmnt -n -o FSTYPE -T "$work") == overlay ]]; then
    mount -t tmpfs -o mode=0700 tmpfs "$work"
fi
mkdir -- "$work/upper" "$work/work" "$image"
mount -t overlay -o "lowerdir=$base,upperdir=$work/upper,workdir=$work/work" overlay "$image"
mount --rbind /dev "$image/dev"
mount --make-rslave "$image/dev"
mount -t proc -o nosuid,nodev,noexec proc "$image/proc"
mount --rbind /sys "$image/sys"
mount --make-rslave "$image/sys"
mount -t tmpfs -o mode=0755,nosuid,nodev tmpfs "$image/run"

printf '#!/bin/sh\nexit 101\n' > "$image/usr/sbin/policy-rc.d"
chmod 755 "$image/usr/sbin/policy-rc.d"
printf '%s\n' \
    'deb [signed-by=/usr/share/keyrings/debian-archive-keyring.gpg] https://deb.debian.org/debian trixie main non-free-firmware' \
    'deb [signed-by=/usr/share/keyrings/debian-archive-keyring.gpg] https://deb.debian.org/debian trixie-updates main non-free-firmware' \
    'deb [signed-by=/usr/share/keyrings/debian-archive-keyring.gpg] https://deb.debian.org/debian-security trixie-security main non-free-firmware' \
    > "$image/etc/apt/sources.list"

transport=()
if [[ -n ${KAGE_BUILD_APT_PROXY:-} ]]; then
    transport+=("-o" "Acquire::https::Proxy=$KAGE_BUILD_APT_PROXY")
fi
if [[ -n ${KAGE_BUILD_CA:-} ]]; then
    install -m 644 "$KAGE_BUILD_CA" "$image/run/kage-build-ca.crt"
    transport+=("-o" "Acquire::https::CaInfo=/run/kage-build-ca.crt")
fi
apt_in_image() {
    chroot "$image" env DEBIAN_FRONTEND=noninteractive apt-get \
        -o Acquire::Languages=none -o Acquire::Retries=2 -o Acquire::GzipIndexes=true \
        "${transport[@]}" "$@"
}

apt_in_image -o APT::Update::Error-Mode=any update
apt_in_image -y --no-install-recommends upgrade
mapfile -t packages < <(cat "$project"/config/package-lists/*.list.chroot | sort -u)
apt_in_image -y --no-install-recommends --no-upgrade install "${packages[@]}"
apt_in_image clean

shopt -s nullglob
kernels=("$base"/boot/vmlinuz-*)
shopt -u nullglob
if [[ ${#kernels[@]} != 1 ]] || ! cmp -s "${kernels[0]}" "$image/boot/${kernels[0]##*/}"; then
    printf 'Taban çekirdek değişti. ISO’yu build.sh ile baştan üretin.\n' >&2
    exit 1
fi
kernel="${kernels[0]##*/vmlinuz-}"
if [[ -n $(chroot "$image" dpkg --audit) ]]; then
    chroot "$image" dpkg --audit >&2
    exit 1
fi

rm -f -- "$image/usr/sbin/policy-rc.d"
tar -C "$project/config/includes.chroot" -cf - . | tar --no-same-owner -xf - -C "$image"
chroot "$image" /usr/local/lib/kage/set-os-release
chroot "$image" /usr/local/lib/kage/set-wallpaper
systemctl --root="$image" disable nftables.service power-profiles-daemon.service
chroot "$image" /usr/local/lib/kage/configure-terminal
chroot "$image" /usr/local/lib/kage/index-toolbox
chroot "$image" /bin/sh -lc 'kage-terminal-kontrol'
chroot "$image" update-initramfs -u -k "$kernel"
chroot "$image" lsinitramfs "/boot/initrd.img-$kernel" > "$temporary/initramfs-files"
grep -Exq '(usr/)?sbin/cryptsetup' "$temporary/initramfs-files"
grep -Exq '(usr/)?lib/cryptsetup/askpass' "$temporary/initramfs-files"
grep -Eq '/dm-crypt\.ko(\.[a-z0-9]+)?$' "$temporary/initramfs-files"
install -m 644 "$image/boot/initrd.img-$kernel" "$temporary/initrd.img"
chroot "$image" dpkg-query -W -f='${binary:Package}\t${Version}\n' > "$temporary/filesystem.packages"
chroot "$image" apt-cache policy nmap tree
chroot "$image" nmap --version

umount -R "$image/dev"
umount "$image/proc"
umount -R "$image/sys"
umount "$image/run"
"${KAGE_BUILD_MKSQUASHFS:-mksquashfs}" "$image" "$temporary/filesystem.squashfs" \
    -comp zstd -Xcompression-level 12 -noappend -no-progress
chmod 644 "$temporary/filesystem.squashfs" "$temporary/filesystem.packages"
mv -f -- "$temporary/filesystem.squashfs" "$temporary/filesystem.packages" "$temporary/initrd.img" "$output/"
printf 'Kage kök dosya sistemi hazır.\n'
