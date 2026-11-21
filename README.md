# Kage OS 0.8.0

Kage OS, Debian 13 (Trixie) tabanlı Türkçe Xfce canlı dağıtımıdır. Günlük masaüstü işleriyle ağ ve dosya incelemesini bir araya getirir. 64 bit Intel ve AMD bilgisayarlarda USB bellekten veya sanal makinede kullanılabilir.

## Canlı oturum

- İlk sanal makine denemesi için 2 sanal işlemci ve 2 GiB RAM ayır. ISO’yu sanal optik sürücüye bağla.
- USB için ISO’yu bir imaj yazdırma aracıyla belleğe yaz. İşlem seçilen belleğin içeriğini siler.
- ISO ile özet dosyasının bulunduğu dizinde `sha256sum -c kage-0.8.0-amd64.iso.sha256` çalıştır. Açılış menüsünün **Araclar** bölümünden ortam bütünlüğünü de denetleyebilirsin.
- Canlı kullanıcı `kage`, başlangıç parolası `live`. Kendi oturumunda `passwd` komutuyla değiştirilebilir. Oturumu kapatmadan önce saklamak istediğin verileri harici bir konuma kopyala.

## Kage Merkez

Merkez ilk açılışta görünür. Sonraki kullanımlarda üstteki Kage OS menüsünden veya alt paneldeki kuzgun simgesinden açılır.

Merkez Başlangıç ekranıyla açılır. Diğer sekmeler ilk ziyaret edildiğinde hazırlanır. Güncellemeler sekmesi genel ve güvenlik listelerini tek APT okumasından alır. Paket listesi veya kurulu paketler değiştiğinde görünüm yeniden okunur. Güç hizmeti ilk profil sorgusuyla başlar. Kaydedilmiş bir profil varsa oturum açılışında yeniden uygulanır.

- **Başlangıç** bölümünde görünüm, güncellemeler, güç, GPU ve sürücüler, araç paketleri, kurtarma, USB kalıcılığı ve ilk açılış sihirbazına doğrudan geçebilirsin. Oturum ve donanım bilgileri aynı sayfada yer alır.
- **Günlük kullanım** bölümünde masaüstü düzenleri, dosya atölyesi, telefon paylaşımı, kitaplık, dosya kurtarma ve görünüm bulunur.
- **Güncellemeler** yerel APT bilgisine göre paketlerin kurulu ve yeni sürümlerini listeler. **Güvenlik güncellemeleri** görünümü güvenilir Debian güvenlik düzeltmelerini içeren paketleri gösterir. **Paketleri yükselt** düğmesi önce kişisel ayar noktası, desteklenen kurulu Btrfs sisteminde de kök noktası oluşturur. Ardından APT yükseltmesini çalıştırır. Paketleri ayrıca Synaptic’ten yönetebilirsin.
- **Tanılama** temel hizmetlerin durumunu gösterir ve bir metin raporu kaydeder. Rapora IP adresleri, kablosuz ağ adları, aygıt kimlikleri ve ev dizini yolu yazılmaz.
- **Araçlar** yüklü uygulamaları kategoriye göre veya adlarıyla bulur. Uygulama kartında açıklama, **Aç** ve **Kılavuz** vardır. **Ctrl+Alt+A** arama kutusunu açar. Masaüstüne yeni uygulama eklediğinde **Yenile** ile listeyi güncelle.
- **Sistem araçları** güvenlik duvarı, ISO ve USB doğrulaması, sistem günlükleri ve donanım denetimini bir araya getirir.
- **Vakalar** bir incelemenin kaynak dosyalarını ve raporlarını aynı çalışma kaydında toplar.

Üst menü **Ağ Analizi** ve **Dijital İnceleme** kategorilerini içerir. Alt panelde Kage Merkez, dosya yöneticisi, uçbirim, Firefox ESR, Kage İnceleme, Synaptic, görev yöneticisi ve ayarlar bulunur. Bir pencere paneli kapatırsa imleci ekranın alt kenarına getir.

**Paket Listelerini Yenile** kısayolu Debian depolarını APT ile yeniler ve sonucun nedenini uçbirimde gösterir. Synaptic grafik paket yöneticisidir. Nmap imajla birlikte kurulu gelir. Menüden Nmap kılavuzunu açabilir, sürümünü `nmap --version` ile kontrol edebilirsin. Çevrimdışı yardım **Kage Kullanım Kılavuzu** adıyla menüden açılır.

## İlk açılış ve yönetim

- **İlk açılış sihirbazı** ilk Xfce oturumunda açılır. Türkçe veya İngilizce oturum dili, Türkçe Q, Türkçe F veya US klavye, tema, isteğe bağlı uygulama kategorileri ve sürücü yardımcısı seçilebilir. **Klavyeyi dene** seçilen düzeni deneme alanında etkinleştirir. Oturum dili bir sonraki girişte Xfce ve destekleyen uygulamalara uygulanır. Paket seçimi yaptıysan **Seçimleri uygula** seni Toolbox’a yönlendirir. Sihirbazı **Daha sonra** ile kapatabilir veya Kage Merkez’den yeniden açabilirsin.
- **Güç** sayfası, güç hizmetinin cihazda bildirdiği profilleri gösterir. Uyguladığın profil ev dizinindeki Kage ayarına kaydedilir ve sonraki oturumda destekleniyorsa yeniden seçilir.
- **GPU ve sürücüler** algılanan Intel, AMD ve NVIDIA aygıtlarını ve bağlı sürücülerini gösterir. Bir GPU ve uygulama seçerek yeni süreç başlatabilir veya **OpenGL’i dene** ile işleyiciyi görebilirsin. NVIDIA’nın bağlı `nvidia` sürücüsüyle PRIME, desteklenen Mesa sürücüleriyle `DRI_PRIME` kullanılır. Kurulu Debian 13 tabanlı Kage’de NVIDIA düğmesi imzalı Debian sürücü bileşenlerini ve çalışan çekirdeğin başlıklarını kullanır. Yüklemeden sonra yeniden başlat. Secure Boot açıksa DKMS anahtarının UEFI ekranında kaydı gerekebilir.
- **Kage Toolbox** ağ analizi, dijital inceleme, ofis ve medya gruplarını gösterir. Kategori seçip **Seçilileri kur** düğmesine basabilir veya APT kullanabilirsin. İmajın içindeki yerel APT dizini imzalıdır. Bir kategorinin eksik bağımlılıkları Debian depolarından alınır.

**Seçimi hatırla** Toolbox kategorilerini ev dizininde saklar. Başarılı kurulumdan sonra seçim de kaydedilir. Kalıcı USB ile sonraki açılışta **Seçilen eksikleri kur** düğmesini kullan. **Profili dışa aktar** ve **Profili içe al** seçenekleri aynı kategorileri başka bir Kage oturumuna taşır.

**Paket sorun giderme** ekranına Güncellemeler veya Toolbox’tan ulaş. **Yerel denetim** paket listelerini, varsayılan rotayı, sistem saatini, depolamayı ve APT kilidini okur. Bir paket adı girersen aday sürümü ve APT kurulum önizlemesini görürsün. **Debian bağlantısını sına** düğmesi resmî Debian sunucusunda DNS ve HTTPS denetimi yapar.

```sh
sudo apt install kage-hack-tool
sudo apt install kage-tools-office
```

Kage paketlerini bir imzalama anahtarınla yeniden oluşturmak için `scripts/build-toolbox-repo.py` betiğini kullan. Betik `.deb` dosyalarını, imzalı dizinleri ve açık anahtarı çıktıya koyar.

## Kurtarma noktaları

**Yönetim → Kurtarma noktaları** tema, klavye, Kage tercihleri ve güç profili için kişisel noktaları kaydeder. Önceki noktayı seçip geri alabilirsin. Geri alma işleminden önce şimdiki ayarlar yeni bir noktaya yazılır. **Dosya yedeklemeyi aç** belgeleri ve fotoğrafları başka bir konuma doğrulayarak kopyalar.

Sistem noktaları, kökü `@` ve ev dizini ayrı `@home` olan bir Kage Btrfs kurulumu içindir. `/boot`, `/usr`, `/etc` ve `/var/lib/dpkg` kök alt biriminde bulunmalı. Kök `fstab` girdisi `subvol=@` ile açılmalı. Kökün içindeki başka Btrfs alt birimleri için ayrı yedek gerekir. **Sistem noktası oluştur** kökün salt okunur bir kopyasını kaydeder. Uygun kurulumda Merkez’den başlattığın paket yükseltmesi bu noktayı önce alır.

Sistem noktasına dönmek için canlı Kage’yi aç. Kurulu Btrfs bölümünün bağlı olmadığını doğrula. Aşağıdaki komutlarda aygıtı ve nokta kimliğini kendi seçimlerinle değiştir. Geri alma, kayıtlı kökten yeni `@` oluşturur ve eski kökü `.kage-previous-roots` altında saklar.

```sh
sudo kage-sistem-kurtar listele /dev/sdXN
sudo kage-sistem-kurtar geri-al /dev/sdXN NOKTA_KIMLIGI --onayla
```

## Günlük kullanım

- **Masaüstü düzenleri** bölümündeki **Ders**, seçtiğin PDF’yi ve `~/Kage-Notlar/ders.txt` dosyasını Xfce’de yan yana açar. **Sunum** bildirimleri susturur ve ikinci ekran ayarına geçiş verir. **Bitir** önceki bildirim ayarını geri yükler. **Salon** tam ekran film ve müzik seçimi sunar.
- **Dosya atölyesi** PDF’den tek sayfa veya aralık çıkarır. Birden fazla JPEG veya PNG dosyasının en uzun kenarını seçtiğin boyuta küçültür. Video işlemi H.264/AAC MP4 çıktısı üretir. Dosyaları sürükleyebilir veya dosya seçiciyi kullanabilirsin. Çıktılar seçtiğin klasörde yeni adlarla kaydedilir.
- **Telefon paylaşımı** için telefon ve bilgisayarı aynı yerel IPv4 ağına bağla. Bilgisayardaki ağ adresini ve göndereceğin dosyaları seç. **QR paylaşımını başlat** düğmesine bas ve QR’ı kamerayla okut. Telefondan gelenler `~/Kage-Paylasim` klasörüne kaydedilir. Oturum 10 dakika sürer. Gelen dosya başına 128 MiB, oturum başına toplam 256 MiB alabilirsin. Paylaşım adresi yerel HTTP kullanır.
- **Çevrimdışı kitaplık** mini İngilizce–Türkçe sözlüğü ve Kage kılavuzunu içerir. **Kaynak ekle** düğmesi TXT, Markdown, PDF veya EPUB belgelerini `~/Kage-Kitaplik` klasörüne kopyalar. Sonuçlara çift tıklayarak belgeni veya EPUB metin önizlemesini aç.
- **Dosya kurtarma** için kaynak diski Thunar’da aç ve kopyalanacak klasörü seç. Hedefe harici diskinde bir klasör ver. **Gereken alanı hesapla** boş alanı karşılaştırır. **Kopyala ve doğrula** sıradan dosyaları yeni bir `Kage-Kurtarma` klasörüne kopyalar ve SHA-256 özetlerini karşılaştırır.
- **Kage görünümü** açık ve koyu Xfce temalarını ve Papirus simgelerini uygular. Otomatik seçim yerel saatle 07.00’de açık, 19.00’da koyu temaya geçer. Duvar kâğıdı seçimi Xfce görünüm ayarlarında yapılır.

Salon oynatıcısı `mpv` ve video dönüştürücüsü `ffmpeg` isteğe bağlıdır. Bu iki özelliği kullanmak için Synaptic’ten ilgili paketleri seçebilir veya `sudo apt install mpv ffmpeg` çalıştırabilirsin.

## Terminal, Firefox ve sistem araçları

- Terminal paketi Bash, Zsh, OpenSSH istemcisini, Git, Python sanal ortamları, GCC ve CMake araçlarını içerir. Ağ, disk, arşiv, servis ve süreç yönetimi için standart Debian komutları da kurulur.
- `kage-terminal-kontrol` bu oturumda temel komutların tamamını denetler ve bulunamayan komutun Debian paketini gösterir. Belirli komutların yolunu görmek için `kage-terminal-kontrol ifconfig iwconfig reboot` çalıştır. Komut listesi `/usr/share/kage/terminal-komutlari.list` dosyasındadır ve derleme sırasında doğrulanır.
- Bash veya Zsh bir komutu bulamazsa Kage, beraberinde gelen Debian 13 paket dizinini çevrimdışı arar. Eşleşen paketleri terminalde gösterir. Kurulum için paket adını doğrulayıp `sudo apt install PAKET` kullanabilirsin.
- Yönetici izni isteyen işlemlerde `sudo` kullan. `iwconfig` çıktısını kablosuz sürücünün desteklediği uzantılar belirler.
- Firefox ESR, imzalı uBlock Origin eklentisini ilk açılışta yerel dosyadan yükler. Eklentiyi **Eklentiler ve temalar** sayfasından yönet. [Mozilla Eklentiler](https://addons.mozilla.org/firefox/addon/ublock-origin/)
- Firefox ESR açılırken **Kage Başlangıç** sayfasını gösterir. Kage kılavuzu ve terminal kısayolları internet bağlantısı olmadan açılır. Arama kutusu DuckDuckGo’ya gider. Başlangıç sayfası Firefox ayarlarından değiştirilebilir.
- **Güvenlik duvarı** mevcut nftables kurallarını, zincirlerini ve varsayılan politikalarını gösterir. Okuma için canlı kullanıcının yönetici yetkisi kullanılır.
- **ISO ve USB** bir ISO dosyasının SHA-256 değerini hesaplar. Beklenen değer ve yazılmış bir USB seçebilirsin. USB karşılaştırmasında ISO boyutundaki ilk baytlar okunur.
- **Sistem günlükleri** bu açılışın son 300 kaydını açar. İleti veya hizmet adıyla arayabilir, önem düzeyine göre filtreleyebilir ve satırın ayrıntısını okuyabilirsin.
- **Donanım** ağ arayüzlerini, ekran ve ses aygıtlarını, kullanılan çekirdek sürücülerini ve bu açılışın günlüklerindeki eksik ürün yazılımı bildirimlerini gösterir.

## Kalıcı ev dizini

Dosyalarını, raporlarını ve kişisel ayarlarını sonraki oturumda kullanmak için ayrı bir bölüm veya sanal disk hazırla.

**Yönetim → USB kalıcılığı** çıkarılabilir USB’deki bağlı olmayan, dosya sistemi imzası bulunmayan bölümleri listeler. Boş bir bölüm seç, **LUKS2 ile şifrele** tercihini belirle ve biçimlendirmeyi onayla. Bölümün en az 64 MiB olması gerekir. Kage ext4 etiketini ve `/home` için `persistence.conf` dosyasını yazar. Açılış menüsünde seçimine uyan kalıcılık modunu başlat ve aynı ekrandan oturum durumunu kontrol et.

### Şifreli USB

1. Hazırladığın USB bölümünde dış etiketi `persistence` olan bir LUKS2 kapsayıcısı kullan.
2. Açılmış kapsayıcının içindeki ext4 dosya sistemine `kage-persistence` etiketini ver. Köküne tek satırı `/home` olan `persistence.conf` dosyasını koy.
3. Açılış menüsünden **Sifreli ev diziniyle baslat** seçeneğini seç. LUKS parolasını gir. Kage Merkez’de oturum satırının **Ev dizini şifreli kalıcı depolamada** olduğunu kontrol et.

### Düz ext4

1. Ayrı ext4 dosya sistemine `kage-persistence` etiketini ver.
2. Dosya sisteminin köküne `persistence.conf` adlı bir metin dosyası koy. Dosyanın içeriği tek satır `/home` olmalı.
3. Kage OS açılış menüsünden **Kalici ev diziniyle baslat** seçeneğini kullan. Kage Merkez’in başlangıç ekranındaki oturum satırı **Ev dizini kalıcı depolamada** durumunu göstermeli.

Bu iki seçenek `/home` altında kaydedilenleri korur. APT ile yüklenen paketler ve sistem değişiklikleri canlı oturum kapanınca sıfırlanır. Varsayılan açılış geçici oturum açar.

## Kage İnceleme

- **Ağ analizi** bir PCAP veya PCAPNG kaydının protokol hiyerarşisini ve IP uç noktalarını raporlar. Kaydı Wireshark’ta açabilir ve yerel ağ arayüzlerinin adreslerini listeleyebilirsin.
- **Dijital inceleme** dosya veya disk imajı için SHA-256 hesaplar ve isteğe bağlı olarak beklenen özetle karşılaştırır. Bir `.sha256` dosyasından özet satırının tamamını yapıştırabilirsin. Bölüm tablosu, YARA ve ExifTool meta veri işlemleri aynı sekmede ayrı seçimler olarak bulunur.
- Bir inceleme sürerken **Durdur** düğmesi işlemi keser. İptal ve hata nedeni rapor klasöründeki `islem.txt` dosyasına yazılır. **Raporu aç** tamamlanan raporu, **Klasörü aç** da raporun ve varsa hata kayıtlarının bulunduğu klasörü açar.

Raporlar varsayılan olarak `~/Kage-Raporlar` altında tarihli klasörlere yazılır. Kalıcı kayıt için uygulamanın **Rapor konumu** alanında harici bir dizin seçebilirsin. Fiziksel medyayla adli inceleme yaparken kendi delil prosedürünü uygula.

**Vakalar** sekmesinde bir vaka oluştur. **Dosya kaydet** ile kaynak konumunu, SHA-256 özetini, boyutu ve UTC kayıt zamanını kaydet. Kaynak dosya mevcut konumunda kalır. **Vakada incele** rapor hedefini o vakanın `~/Kage-Vakalar` altındaki `raporlar` klasörüne ayarlar.

**CTF alanı** seçili vakaya not, kendi laboratuvar bağlantıların ve Bash veya Zsh profili ekler. **İmleçteki bağlantıyı aç** bulunduğun satırdaki adresi tarayıcıya gönderir. **Terminali aç** seçtiğin kabuğu vaka klasöründe başlatır.

**Zaman çizelgesi** kayıtlı dosya zamanlarını, PCAP ve PCAPNG paketlerini, `journalctl` JSONL çıktısını ve eklediğin olay notlarını UTC ile sıralar. Örnekleri denemek için `/usr/share/kage/ornekler/` içindeki PCAP ve JSONL dosyalarını vakaya ekle. Bir olay notu yazarken saatin saat farkını da belirt. **CSV kaydet** görünen filtre sonucunu kaydeder. İçerik önizlemesi en fazla 16 kaynak, kaynak başına 2.000 kayıt ve toplam 6.000 olay okur. Bu sınırlar veya okunamayan dosyalar **Okuma ayrıntıları** altında görünür.

**Örnek İncelemeler** kılavuzu **Dijital İnceleme** menüsünden açılır. `/usr/share/kage/ornekler` içindeki DNS kaydı, SHA-256 dosyası ve kurgusal sistem günlüğü çevrimdışı kullanılabilir. Örnek günlüğü Merkez’de **Sistem araçları → Sistem günlükleri → Örnek kayıtlar** yolundan filtrele.

## Kaynaktan üretim

Debian 13 amd64 üzerinde ağ erişimi ve 10 GiB boş alan ayır. Canlı ortamda derleyeceksen 4 GiB RAM kullan. Doğrulama dosyasına uyan Kage OS 0.4.0 ISO’suyla bu sürümün imajını üretebilirsin.

```sh
sudo apt update
sudo apt install xorriso squashfs-tools python3
sudo ./scripts/rebuild-from-0.4.0.sh /yol/kage-0.4.0-amd64.iso
```

Betik taban ISO’nun SHA-256 özetini doğrular, imzalı Debian depolarından paketleri hazırlar ve yeni ISO’nun içerik özetlerini denetler. Paketler derleme günündeki Debian depolarından gelir. Yeni bir çekirdek ve initramfs gerektiğinde temiz derleme yolunu kullan.

```sh
sudo apt install live-build debootstrap xorriso squashfs-tools isolinux \
  syslinux-common grub-pc-bin grub-efi-amd64-bin mtools dosfstools rsync xz-utils
sudo ./build.sh
```

Her iki yol da varsayılan olarak `dist/` dizinine ISO ve SHA-256 çıktısı verir. `config/package-lists/` paketleri, `config/includes.chroot/` masaüstü ile uygulamaları, `config/bootloaders/` ise açılış temasını belirler. Sağlanan kuzgun görselinin şeffaf uyarlamasından duvar kâğıdını ve simgeleri yeniden üretmek için ImageMagick ile `./branding/render.sh` çalıştır.

İki derleme yolu da canlı dosya sistemini SquashFS ve Zstandard seviye 12 ile sıkıştırır.

Raporlama ve Kage Merkez testlerini çalıştırmak için şu komutu kullan.

```sh
python3 -m unittest discover -s tests -v
```

## Katkı ve lisans

Hata bildirimlerini Issues’a, kod önerilerini Pull Requests’e gönderebilirsin. [Katkı kılavuzu](CONTRIBUTING.md)

Kage OS için yazılan kod GNU Genel Kamu Lisansı sürüm 3 (GPL-3.0-only) ile yayımlanır. [Lisans metni](LICENSE)

Debian paketleri, üretici ürün yazılımları ve Firefox eklentisi kendi lisans koşullarıyla dağıtılır. Paket lisans bildirimlerine canlı sistemde `/usr/share/doc/` dizininden erişebilirsin. İmajla gelen uBlock Origin 1.76.4’ün lisans bildirimi imzalı XPI dosyasındadır. [uBlock Origin 1.76.4 kaynak sürümü](https://github.com/gorhill/uBlock/releases/tag/1.76.4)
