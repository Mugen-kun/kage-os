#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname -- "$0")/.."
source_image=${1:-branding/kuzgun-kaynak.png}
chroot=config/includes.chroot
boot=config/bootloaders
font=${KAGE_BRAND_FONT:-/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf}
art="$chroot/usr/share/kage/kuzgun.png"

# Reuse the supplied raven symbol at readable sizes in each system surface.
convert "$source_image" -crop 885x1030+151+34 +repage -resize 650x650 \
    -background none -gravity center -extent 650x650 -strip PNG32:"$art"
convert "$art" -resize 112x112 \
    "$chroot/usr/share/kage/.menu-symbol.png"
{
    printf '%s' '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="112" height="112" viewBox="0 0 112 112"><image width="112" height="112" xlink:href="data:image/png;base64,'
    base64 -w 0 "$chroot/usr/share/kage/.menu-symbol.png"
    printf '%s\n' '"/></svg>'
} > "$chroot/usr/share/icons/hicolor/scalable/apps/kage.svg"
rm -- "$chroot/usr/share/kage/.menu-symbol.png"

convert -size 2560x1440 radial-gradient:'#33202a-#101015' \
    -fill '#21171e' -draw 'polygon 0,1024 902,0 1032,0 0,1172 polygon 2560,360 1598,1440 1800,1440 2560,582' \
    -fill none -stroke '#412630' -strokewidth 2 \
    -draw 'line 0,1211 1068,0 line 1475,1440 2560,234' \
    \( "$art" -resize 630x630 \) -gravity center -geometry +0-69 -compose over -composite \
    -gravity center -font "$font" -pointsize 89 -kerning 12 -fill '#fff0d3' -stroke none \
    -annotate +0+327 'KAGE OS' -strip -sampling-factor 4:4:4 -quality 90 "$chroot/usr/share/backgrounds/kage/kage.jpg"

convert -size 800x600 radial-gradient:'#361d28-#130f14' \
    -fill '#140f16' -stroke '#503040' -strokewidth 1 -draw 'roundrectangle 110,252 690,513 15,15' \
    \( "$art" -resize 158x158 \) -gravity north -geometry +0+34 -compose over -composite \
    -gravity north -font "$font" -pointsize 26 -kerning 4 -stroke none -fill '#fff0d3' \
    -annotate +0+202 'KAGE OS' -strip PNG24:"$boot/grub-pc/splash.png"
convert "$boot/grub-pc/splash.png" -resize 640x480 -strip PNG24:"$boot/syslinux_common/splash.png"
