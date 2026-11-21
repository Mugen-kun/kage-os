# Kage OS’a katkı

Kage OS, Debian 13 ve Xfce tabanlı bir canlı dağıtımdır. Masaüstü, paket seçimi, açılış ve inceleme araçları için katkı gönderebilirsin.

## Sorun bildirirsen

Issue’da Kage sürümünü, makinenin sanal veya fiziksel olduğunu, BIOS ya da UEFI kullandığını ve hatayı yeniden görmek için izlediğin adımları yaz. Günlüklerden yalnızca sorunla ilgili satırları ekle.

## Değişiklik gönderirsen

1. Depoyu çatalla ve her değişiklik için ayrı bir dal aç.
2. Python testlerini çalıştır. Açılış veya paket listesi değiştiğinde README’deki canlı ISO derlemesini ve bir sanal makine açılışını da dene.
3. Pull request’te değişikliğin neyi düzelttiğini ve hangi adımları sınadığını yaz.

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
```

Paket listeleri `config/package-lists/`, Kage Merkez kodu `config/includes.chroot/usr/share/kage/`, açılış menüleri `config/bootloaders/` dizinindedir.
