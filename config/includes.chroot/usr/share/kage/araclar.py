"""Catalogue of visible desktop applications and local command guides."""

import shutil

from gi.repository import Gio, GLib, Gtk

from arac_metin import normalize
from terminal import command_packages


CATEGORIES = {
    "X-KageForensics": "Dijital inceleme", "X-KageNetwork": "Ağ",
    "X-KageDaily": "Günlük kullanım",
    "X-KageManagement": "Yönetim",
    "System": "Sistem", "Settings": "Ayarlar", "Network": "İnternet",
    "Development": "Geliştirme", "Graphics": "Grafik", "Office": "Ofis",
    "AudioVideo": "Ses ve video", "Education": "Eğitim", "Game": "Oyun",
    "Utility": "Donatılar",
}

GUIDES = {
    "kage-paket-tanila.desktop": "Paket adını gir ve Yerel denetim ile aday sürümü, APT kilidini ve kurulum planını gör. Debian bağlantısını ayrıca sınayabilirsin.",
    "kage-zaman-cizelgesi.desktop": "Bir vaka seçip zaman çizelgesini aç. Yerel PCAP ve JSONL olaylarını, dosya zamanlarını ve notlarını UTC ile filtrele veya CSV kaydet.",
    "kage-guc.desktop": "Cihazda kullanılabilen pil tasarrufu, dengeli veya performans profilini seç ve Uygula’ya bas.",
    "kage-gpu.desktop": "Yüklü sürücüyü kontrol et. Bir GPU ve uygulama seç, ardından Uygulamayı aç veya OpenGL’i dene düğmesine bas.",
    "kage-toolbox.desktop": "Kategorilerini seç, Seçimi hatırla ile sakla. Sonraki oturumda Seçilen eksikleri kur düğmesini kullanabilir veya profili JSON olarak taşıyabilirsin.",
    "kage-ilk-kurulum.desktop": "Dil, klavye, görünüm ve uygulama tercihlerini seç. Klavyeyi dene düğmesi seçtiğin düzeni geçici olarak uygular.",
    "kage-kurtarma.desktop": "Kişisel ayar noktası oluştur veya kayıtlı noktadan geri dön. Uygun kurulu Btrfs sistemlerinde kök noktası da oluşturabilirsin.",
    "kage-usb-kalicilik.desktop": "Bağlı olmayan boş bir USB bölümünü seç. Şifreli veya düz kalıcılık biçimini belirleyip bölümü hazırla.",
    "kage-ctf.desktop": "Bir vaka seç, CTF alanını aç ve notlarını, bağlantılarını ve kabuk profilini kaydet.",
    "kage-masaustu-duzenleri.desktop": "Ders için PDF’yi ve notları aç. Sunumda bildirimleri sustur, ikinci ekranı seç. mpv paketiyle Salon ekranını kullan.",
    "kage-dosya-atolyesi.desktop": "PDF sayfası, fotoğraf küçültme veya telefon videosu işlemini seç. Dosyayı sürükle ve çıktı klasörünü seç.",
    "kage-telefon-paylasimi.desktop": "Aynı yerel ağdaki adresini seç, QR paylaşımını başlat ve kodu telefonun kamerasıyla okut.",
    "kage-kitaplik.desktop": "Mini sözlükte veya eklediğin TXT, Markdown, PDF ve EPUB dosyalarında tek kutudan ara.",
    "kage-dosya-kurtarma.desktop": "Kaynak ve hedef klasörleri seç. Gereken alanı ölç, ardından Kopyala ve doğrula düğmesine bas.",
    "kage-gorunum.desktop": "Açık ve koyu temalar arasından seç veya yerel saatle 07.00 ve 19.00’a otomatik geçiş ayarla.",
    "kage-inceleme.desktop": "Ağ analizi veya Dijital inceleme sekmesini seç. Kaynak dosyayı seçtikten sonra rapor konumunu belirleyebilirsin.",
    "kage-ag.desktop": "Kaydedilmiş bir PCAP dosyasını seç ve protokol özetini oluştur. Yerel bağlantıları Arayüzleri listele ile gör.",
    "kage-dijital.desktop": "Dosyanı seç ve SHA-256, bölümler, YARA ya da meta veri bölümünden incelemeyi başlat.",
    "kage-guvenlik-duvari.desktop": "Yenile düğmesi mevcut nftables zincirlerini, politikaları ve kural sayılarını okur.",
    "kage-medya-dogrulama.desktop": "ISO dosyasını seç. Beklenen SHA-256 değerini girerek dosyayı karşılaştırabilir veya yazılmış bir USB seçerek ISO boyutundaki bölümü doğrulayabilirsin.",
    "kage-sistem-gunlukleri.desktop": "Kayıtları yükle. Arama kutusuna iletiyi veya sistem hizmetini yaz. Önem düzeyiyle sonucu daralt ve ayrıntı için bir satır seç.",
    "kage-donanim.desktop": "Donanımı denetle düğmesiyle ağ, Wi-Fi, ekran ve ses aygıtlarının sürücülerini ve bu açılıştaki eksik ürün yazılımı kayıtlarını gör.",
    "kage-vakalar.desktop": "Bir vaka oluştur ve Dosya kaydet ile SHA-256 ve kaynak konumunu kaydet. Vakada incele düğmesi, rapor hedefini vaka klasörüne ayarlar.",
    "kage-ornekler.desktop": "Kılavuzu açarak yerel DNS kaydını, SHA-256 örneğini ve örnek sistem günlüklerini incele.",
    "firefox-esr.desktop": "Adres çubuğuna adres veya arama sözcüğü yaz. Ctrl+L adres çubuğunu seçer. uBlock Origin ayarlarına Firefox’un Eklentiler ve temalar menüsünden ulaş.",
    "org.wireshark.Wireshark.desktop": "Dosya → Aç ile kaydedilmiş bir PCAP dosyasını aç. Bir paketi seçerek protokol alanlarını incele.",
    "synaptic.desktop": "Ara düğmesiyle paketini bul. İstediğin değişiklikleri işaretledikten sonra Uygula ile işlem özetini incele.",
    "xfce4-terminal.desktop": "Komutu yazıp Enter’a bas. Ctrl+Shift+C ve Ctrl+Shift+V terminalde kopyalama ve yapıştırma için kullanılır.",
    "thunar.desktop": "Konum çubuğuna bir klasör yolu yazmak için Ctrl+L’ye bas. Bağlı aygıtlara sol panelden ulaş.",
}

COMMANDS = {
    "apt": ("Debian paketlerini arar ve yönetir.", "apt search PAKET ile paket arayabilir, apt show PAKET ile ayrıntılarını görebilirsin."),
    "bash": ("Bash etkileşimli kabuğunu açar.", "Terminalde bash ile Bash’i başlat. exit ile önceki kabuğa dön."),
    "zsh": ("Zsh etkileşimli kabuğunu açar.", "Terminalde zsh ile Zsh’yi başlat. exit ile önceki kabuğa dön."),
    "ifconfig": ("Ağ arayüzlerini ve adresleri gösterir.", "Terminalde ifconfig çalıştır. Kapalı arayüzler de listelensin diye ifconfig -a kullan."),
    "iwconfig": ("Kablosuz arayüz ayarlarını gösterir.", "Terminalde iwconfig çalıştır. Çıktı sürücünün kablosuz uzantı desteğine bağlıdır."),
    "iw": ("Modern kablosuz arayüz bilgilerini gösterir.", "Terminalde iw dev ile kablosuz arayüzleri listele."),
    "reboot": ("Sistemi yeniden başlatır.", "Açık işlerini kaydet ve yeniden başlatmak istediğinde terminalde reboot çalıştır. Yönetici onayı gerektiğinde sudo reboot kullan."),
    "ip": ("Ağ arayüzlerini, adresleri ve rotaları gösterir.", "ip -brief address ile yerel adresleri, ip route ile yönlendirme tablosunu gör."),
    "ss": ("Yerel ağ soketlerini gösterir.", "ss -lnt ile dinleyen yerel TCP soketlerini listele."),
    "nmcli": ("NetworkManager bağlantı bilgilerini gösterir.", "nmcli device status ile ağ aygıtlarının durumunu gör."),
    "lsblk": ("Diskleri ve bölümleri listeler.", "lsblk -f ile dosya sistemi biçimini ve etiketleri gör."),
    "lsusb": ("Bağlı USB aygıtlarını listeler.", "Terminalde lsusb çalıştır."),
    "lspci": ("PCI aygıtlarını listeler.", "lspci -k ile kullanılan çekirdek sürücülerini gör."),
    "htop": ("İşlemci, bellek ve süreçleri gösterir.", "Terminalde htop çalıştır. F10 uygulamayı kapatır."),
    "free": ("Kullanılan ve kullanılabilir belleği gösterir.", "free -h ile belleği okunabilir birimlerle gör."),
    "tree": ("Klasörleri ve dosyaları ağaç biçiminde gösterir.", "tree -L 2 ile çalışma klasörünün ilk iki düzeyini gör."),
    "journalctl": ("Sistem günlüklerini okur.", "journalctl -b ile bu açılışın kayıtlarını gör. Listeleyiciden q ile çık."),
    "sha256sum": ("Bir dosyanın SHA-256 özetini hesaplar.", "sha256sum DOSYA komutuna dosyanın adını ver ve çıktıyı beklenen değerle karşılaştır."),
    "dig": ("DNS kayıtlarını sorgular.", "Alan adının DNS kayıtlarını sorgulamak için dig ALAN_ADI çalıştır."),
    "netstat": ("Yerel ağ bağlantılarını ve soketlerini gösterir.", "Açık yerel soketleri sayısal adreslerle görmek için netstat -an çalıştır."),
    "ssh": ("SSH sunucusuna istemci olarak bağlanır.", "Kendi sunucuna bağlanmak için ssh KULLANICI@SUNUCU kullan. Bağlanmadan önce sunucu anahtarını doğrula."),
    "git": ("Yerel Git depolarını ve değişiklikleri yönetir.", "git status ile bulunduğun deponun çalışma durumunu gör."),
    "tmux": ("Aynı terminalde birden fazla oturumu yönetir.", "tmux ile oturum başlat. Ctrl+B ardından D, oturumu arka planda bırakır."),
    "python3": ("Python betiklerini ve sanal ortamları çalıştırır.", "python3 -m venv .venv ile sanal ortam oluştur. . .venv/bin/activate ile etkinleştir."),
    "kage-terminal-kontrol": ("Temel terminal komutlarını denetler.", "kage-terminal-kontrol ile temel listeyi denetle. Ardına komut adlarını yazarak yalnızca o komutların yolunu gör."),
}


def category_for(app):
    tags = (app.get_categories() or "").split(";")
    return next((name for key, name in CATEGORIES.items() if key in tags), "Diğer")


class ToolCatalog(Gtk.Box):
    def __init__(self, notice):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.notice = notice
        self.rows = []
        self.loaded = False
        toolbar = Gtk.Box(spacing=8)
        self.search = Gtk.SearchEntry(placeholder_text="Uygulama veya terminal komutu ara")
        self.search.get_accessible().set_name("Araç ara")
        self.search.connect("search-changed", self.filter_rows)
        toolbar.pack_start(self.search, True, True, 0)
        self.category = Gtk.ComboBoxText()
        self.category.get_accessible().set_name("Araç kategorisi")
        self.category.connect("changed", self.filter_rows)
        toolbar.pack_start(self.category, False, False, 0)
        refresh = Gtk.Button(label="Yenile")
        refresh.connect("clicked", lambda _button: self.reload())
        toolbar.pack_start(refresh, False, False, 0)
        self.pack_start(toolbar, False, False, 0)
        self.status = Gtk.Label(xalign=0)
        self.pack_start(self.status, False, False, 0)
        self.results = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        self.results.set_filter_func(self.included)
        view = Gtk.ScrolledWindow()
        view.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        view.add(self.results)
        self.pack_start(view, True, True, 0)

    def reload(self):
        selected = self.category.get_active_id()
        for row in self.rows:
            self.results.remove(row)
        self.rows.clear()
        apps = {}
        for app in Gio.AppInfo.get_all():
            if isinstance(app, Gio.DesktopAppInfo) and app.get_id() and app.should_show():
                apps.setdefault(app.get_id(), app)
        for app in sorted(apps.values(), key=lambda item: normalize(item.get_display_name())):
            name = app.get_display_name()
            category = category_for(app)
            description = app.get_description() or app.get_generic_name() or f"{category} kategorisindeki uygulama."
            keywords = " ".join(app.get_keywords() or [])
            guide = GUIDES.get(app.get_id(), "Aç düğmesiyle uygulamayı başlat. Uygulamaya özgü bilgileri Yardım menüsünden veya paket belgelerinden incele.")
            self.add_item(name, description, category, f"{app.get_id()} {app.get_executable()} {keywords}", app, guide)
        command_index = command_packages()
        for command in sorted(command_index.keys() | COMMANDS.keys()):
            if shutil.which(command):
                if command in COMMANDS:
                    description, guide = COMMANDS[command]
                else:
                    package = command_index[command]
                    description = f"Debian paketi {package}"
                    guide = f"Terminalde man {command} ile kılavuzu ara. Paket belgeleri /usr/share/doc/{package} altında bulunur."
                self.add_item(command, description, "Terminal komutları", command, None, guide)
        self.category.remove_all()
        self.category.append("Tümü", "Tümü")
        categories = sorted({row.category for row in self.rows}, key=normalize)
        for category in categories:
            self.category.append(category, category)
        self.category.set_active_id(selected if selected in categories else "Tümü")
        self.loaded = True
        self.filter_rows()

    def add_item(self, title, description, category, keywords, app, guide):
        row = Gtk.ListBoxRow(activatable=False)
        row.category = category
        row.search_text = normalize(f"{title} {description} {category} {keywords}")
        box = Gtk.Box(spacing=10)
        box.set_margin_top(4)
        box.set_margin_bottom(4)
        box.get_style_context().add_class("kage-card")
        icon = app.get_icon() if app else None
        image = Gtk.Image.new_from_gicon(icon, Gtk.IconSize.DIALOG) if icon else Gtk.Image.new_from_icon_name(
            "utilities-terminal" if not app else "application-x-executable", Gtk.IconSize.DIALOG
        )
        box.pack_start(image, False, False, 0)
        labels = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        name = Gtk.Label(label=title, xalign=0)
        name.get_style_context().add_class("kage-value")
        name.set_line_wrap(True)
        labels.pack_start(name, False, False, 0)
        detail = Gtk.Label(label=description, xalign=0, wrap=True)
        detail.set_max_width_chars(58)
        labels.pack_start(detail, False, False, 0)
        box.pack_start(labels, True, True, 0)
        help_button = Gtk.Button(label="Kılavuz", valign=Gtk.Align.CENTER)
        help_button.get_accessible().set_name(f"{title} kullanım kılavuzu")
        help_button.connect("clicked", lambda _button: self.notice(title, f"{description}\n\n{guide}"))
        if app:
            launch = Gtk.Button(label="Aç", valign=Gtk.Align.CENTER)
            launch.get_accessible().set_name(f"{title} uygulamasını aç")
            launch.connect("clicked", self.launch, app)
            box.pack_start(launch, False, False, 0)
        box.pack_start(help_button, False, False, 0)
        row.add(box)
        self.rows.append(row)
        self.results.add(row)
        row.show_all()

    def included(self, row):
        category = self.category.get_active_id()
        terms = normalize(self.search.get_text()).split()
        return (not category or category == "Tümü" or row.category == category) and all(
            term in row.search_text for term in terms
        )

    def filter_rows(self, *_args):
        self.results.invalidate_filter()
        visible = sum(self.included(row) for row in self.rows)
        self.status.set_text(f"{visible} sonuç" if visible else "Aramana uygun araç bulunamadı.")

    def launch(self, _button, app):
        try:
            if app.launch([], None):
                return
        except GLib.Error as error:
            self.notice(app.get_display_name(), error.message)
            return
        self.notice(app.get_display_name(), "Uygulama açılamadı.")
