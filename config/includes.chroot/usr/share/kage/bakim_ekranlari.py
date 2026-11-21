"""GTK views for the firewall, media verifier and local system journal."""

from pathlib import Path
from threading import Event

from gi.repository import Gtk, Pango

from araclar import normalize
from bakim import JOURNAL_LIMIT, firewall_snapshot, journal_records, journal_snapshot, usb_drives, verify_media
from donanim import hardware_snapshot
from rapor import ReportStopped, STOPPED


def label(text, selectable=False):
    return Gtk.Label(label=text, xalign=0, wrap=True, selectable=selectable)


def column(spacing=9):
    return Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=spacing)


def button(text, action, primary=False):
    result = Gtk.Button(label=text, halign=Gtk.Align.START)
    if primary:
        result.get_style_context().add_class("kage-primary")
    result.connect("clicked", action)
    return result


def table(model, titles):
    view = Gtk.TreeView(model=model)
    for index, title in enumerate(titles):
        renderer = Gtk.CellRendererText(ellipsize=Pango.EllipsizeMode.END)
        field = Gtk.TreeViewColumn(title, renderer, text=index)
        field.set_expand(index == 1 or index == len(titles) - 1)
        field.set_resizable(True)
        view.append_column(field)
    scrolled = Gtk.ScrolledWindow()
    scrolled.set_shadow_type(Gtk.ShadowType.IN)
    scrolled.add(view)
    return scrolled, view


class Maintenance(Gtk.Box):
    def __init__(self, run_job):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.run_job = run_job
        self.cancel = None
        self.drives = {}
        self.stack = Gtk.Stack()
        self.stack.add_titled(self.firewall_page(), "firewall", "Güvenlik duvarı")
        self.stack.add_titled(self.media_page(), "media", "ISO ve USB")
        self.stack.add_titled(self.journal_page(), "journal", "Sistem günlükleri")
        self.stack.add_titled(self.hardware_page(), "hardware", "Donanım")
        tabs = Gtk.StackSwitcher(stack=self.stack, halign=Gtk.Align.CENTER)
        self.pack_start(tabs, False, False, 0)
        self.pack_start(self.stack, True, True, 0)

    def firewall_page(self):
        page = column()
        page.pack_start(label("Mevcut nftables zincirleri, politikaları ve kural sayıları"), False, False, 0)
        self.firewall_status = label("Kuralları okumak için Yenile’ye bas.")
        page.pack_start(button("Yenile", self.load_firewall, True), False, False, 0)
        page.pack_start(self.firewall_status, False, False, 0)
        self.firewall_store = Gtk.ListStore(str, str, str, str, str)
        display, _view = table(self.firewall_store, ("Aile", "Tablo / zincir", "Yön", "Politika", "Kural"))
        page.pack_start(display, True, True, 0)
        return page

    def load_firewall(self, control):
        control.set_sensitive(False)
        self.firewall_status.set_text("Güvenlik duvarı okunuyor…")

        def done(result, error):
            control.set_sensitive(True)
            self.firewall_store.clear()
            if error:
                self.firewall_status.set_text(f"Güvenlik duvarı okunamadı. {error}")
                return
            count, rows = result
            for row in rows:
                self.firewall_store.append(row)
            self.firewall_status.set_text(f"nftables · {len(rows)} zincir · {count} kural")

        self.run_job(firewall_snapshot, done)

    def journal_page(self):
        page = column()
        self.journal_title = label(f"Bu açılışın son {JOURNAL_LIMIT} sistem kaydı")
        page.pack_start(self.journal_title, False, False, 0)
        actions = Gtk.Box(spacing=8)
        self.journal_live_button = button("Kayıtları yükle", self.load_journal, True)
        self.journal_example_button = button("Örnek kayıtlar", self.load_example_journal)
        actions.pack_start(self.journal_live_button, False, False, 0)
        actions.pack_start(self.journal_example_button, False, False, 0)
        self.journal_search = Gtk.SearchEntry(placeholder_text="İleti veya hizmet ara")
        self.journal_search.connect("search-changed", self.filter_journal)
        actions.pack_start(self.journal_search, True, True, 0)
        self.severity = Gtk.ComboBoxText()
        for value, title in (("7", "Tüm önem düzeyleri"), ("4", "Uyarılar ve hatalar"), ("3", "Hatalar")):
            self.severity.append(value, title)
        self.severity.set_active(0)
        self.severity.connect("changed", self.filter_journal)
        actions.pack_start(self.severity, False, False, 0)
        page.pack_start(actions, False, False, 0)
        self.journal_status = label("Kayıtları yüklemeye hazır.")
        page.pack_start(self.journal_status, False, False, 0)
        self.journal_store = Gtk.ListStore(str, str, str, str, int, str)
        self.journal_filter = self.journal_store.filter_new()
        self.journal_filter.set_visible_func(self.journal_visible)
        display, view = table(self.journal_filter, ("Saat", "Hizmet", "Önem", "İleti"))
        view.get_selection().connect("changed", self.show_journal_detail)
        page.pack_start(display, True, True, 0)
        self.journal_detail = Gtk.TextView(editable=False, cursor_visible=False, wrap_mode=Gtk.WrapMode.WORD_CHAR)
        details = Gtk.ScrolledWindow()
        details.set_min_content_height(76)
        details.set_shadow_type(Gtk.ShadowType.IN)
        details.add(self.journal_detail)
        page.pack_start(details, False, False, 0)
        return page

    def load_journal(self, _control):
        self.load_records(journal_snapshot, f"Bu açılışın son {JOURNAL_LIMIT} sistem kaydı")

    def load_example_journal(self, _control):
        example = Path(__file__).with_name("ornekler") / "sistem-gunlugu.jsonl"
        self.load_records(lambda: journal_records(example.read_text(encoding="utf-8")), "Çevrimdışı örnek sistem günlüğü")

    def load_records(self, work, title):
        self.journal_live_button.set_sensitive(False)
        self.journal_example_button.set_sensitive(False)
        self.journal_title.set_text(title)
        self.journal_status.set_text("Günlükler okunuyor…")
        names = ("Acil", "Uyarı", "Kritik", "Hata", "Uyarı", "Bildirim", "Bilgi", "Hata ayıklama")

        def done(rows, error):
            self.journal_store.clear()
            self.journal_live_button.set_sensitive(True)
            self.journal_example_button.set_sensitive(True)
            if error:
                self.journal_status.set_text(f"Günlükler okunamadı. {error}")
                return
            for stamp, unit, priority, message in reversed(rows):
                self.journal_store.append((stamp, unit, names[priority], message, priority, normalize(f"{stamp} {unit} {message}")))
            self.filter_journal()

        self.run_job(work, done)

    def journal_visible(self, model, item, *_args):
        threshold = int(self.severity.get_active_id() or "7")
        terms = normalize(self.journal_search.get_text()).split()
        return model.get_value(item, 4) <= threshold and all(term in model.get_value(item, 5) for term in terms)

    def filter_journal(self, *_args):
        self.journal_filter.refilter()
        self.journal_status.set_text(f"{len(self.journal_filter)} / {len(self.journal_store)} kayıt")

    def show_journal_detail(self, selection):
        model, item = selection.get_selected()
        self.journal_detail.get_buffer().set_text(model.get_value(item, 3) if item else "")

    def hardware_page(self):
        page = column()
        page.pack_start(label("Ağ, ekran ve ses aygıtları ile bağlı sürücüler"), False, False, 0)
        page.pack_start(button("Donanımı denetle", self.load_hardware, True), False, False, 0)
        self.hardware_status = label("Donanım denetimi başlatılabilir.")
        page.pack_start(self.hardware_status, False, False, 0)
        self.hardware_store = Gtk.ListStore(str, str, str)
        display, _view = table(self.hardware_store, ("Tür", "Aygıt", "Sürücü"))
        page.pack_start(display, True, True, 0)
        page.pack_start(label("Eksik firmware uyarıları"), False, False, 0)
        self.hardware_warnings = Gtk.ListStore(str)
        warnings, _view = table(self.hardware_warnings, ("Çekirdek günlüğü",))
        warnings.set_min_content_height(70)
        page.pack_start(warnings, False, False, 0)
        return page

    def load_hardware(self, control):
        control.set_sensitive(False)
        self.hardware_status.set_text("Donanım okunuyor…")

        def done(value, error):
            control.set_sensitive(True)
            self.hardware_store.clear()
            self.hardware_warnings.clear()
            if error:
                self.hardware_status.set_text(f"Donanım okunamadı. {error}")
                return
            rows, warnings = value
            for row in rows:
                self.hardware_store.append(row)
            wifi = sum(kind == "Wi-Fi" for kind, _name, _driver in rows)
            self.hardware_status.set_text(f"{len(rows)} donanım kaydı · {wifi} Wi-Fi arayüzü")
            messages = ["Çekirdek günlüğü okunamadı."] if warnings is None else warnings or ["Eksik firmware uyarısı bulunmadı."]
            for message in messages:
                self.hardware_warnings.append((message,))

        self.run_job(hardware_snapshot, done)

    def media_page(self):
        page = column()
        page.pack_start(label("ISO’nun SHA-256 özetini hesapla. Yazılmış bir USB seçtiğinde ISO boyutundaki veri de karşılaştırılır."), False, False, 0)
        self.iso = Gtk.FileChooserButton(title="ISO dosyası seç", action=Gtk.FileChooserAction.OPEN)
        file_filter = Gtk.FileFilter()
        file_filter.set_name("ISO dosyaları")
        file_filter.add_pattern("*.[iI][sS][oO]")
        self.iso.add_filter(file_filter)
        page.pack_start(self.iso, False, False, 0)
        self.expected = Gtk.Entry(placeholder_text="Beklenen SHA-256 (isteğe bağlı)")
        page.pack_start(self.expected, False, False, 0)
        usb = Gtk.Box(spacing=8)
        self.usb = Gtk.ComboBoxText()
        self.usb.get_accessible().set_name("Karşılaştırılacak USB aygıtı")
        self.usb.append("iso", "Yalnızca ISO dosyası")
        self.usb.set_active_id("iso")
        usb.pack_start(self.usb, True, True, 0)
        self.load_usb = button("USB aygıtlarını listele", self.refresh_drives)
        usb.pack_start(self.load_usb, False, False, 0)
        page.pack_start(usb, False, False, 0)
        actions = Gtk.Box(spacing=8)
        self.verify = button("Doğrula", self.start_verification, True)
        self.stop = button("Durdur", lambda _button: self.cancel_media())
        self.stop.set_sensitive(False)
        actions.pack_start(self.verify, False, False, 0)
        actions.pack_start(self.stop, False, False, 0)
        page.pack_start(actions, False, False, 0)
        self.media_status = label("Doğrulamaya hazır.", True)
        self.media_status.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
        page.pack_start(self.media_status, False, False, 0)
        return page

    def refresh_drives(self, control):
        control.set_sensitive(False)
        self.verify.set_sensitive(False)
        self.media_status.set_text("USB aygıtları aranıyor…")

        def done(rows, error):
            control.set_sensitive(True)
            self.verify.set_sensitive(True)
            if error:
                self.media_status.set_text(f"USB aygıtları okunamadı. {error}")
                return
            old = self.usb.get_active_id()
            self.drives = {drive.path: drive for drive in rows}
            self.usb.remove_all()
            self.usb.append("iso", "Yalnızca ISO dosyası")
            for drive in rows:
                self.usb.append(drive.path, f"{drive.model} · {drive.path} · {drive.size / 1024**3:.2f} GiB")
            self.usb.set_active_id(old if old in self.drives else "iso")
            self.media_status.set_text(f"{len(rows)} USB aygıtı bulundu.")

        self.run_job(usb_drives, done)

    def start_verification(self, _control):
        path = self.iso.get_filename()
        if not path:
            self.media_status.set_text("Önce bir ISO dosyası seç.")
            return
        expected = self.expected.get_text()
        drive = self.drives.get(self.usb.get_active_id())
        self.cancel = Event()
        cancel = self.cancel
        for widget in (self.iso, self.expected, self.usb, self.load_usb, self.verify):
            widget.set_sensitive(False)
        self.stop.set_sensitive(True)
        self.media_status.set_text("Veri okunuyor ve SHA-256 hesaplanıyor…")

        def work():
            try:
                return verify_media(path, expected, drive, cancel)
            except ReportStopped:
                return None

        def done(result, error):
            self.cancel = None
            self.stop.set_sensitive(False)
            for widget in (self.iso, self.expected, self.usb, self.load_usb, self.verify):
                widget.set_sensitive(True)
            if error:
                self.media_status.set_text(error)
            elif result is None:
                self.media_status.set_text(STOPPED)
            else:
                digest, expected_match, usb_match = result
                lines = [f"ISO SHA-256\n{digest}"]
                if expected_match is not None:
                    lines.append("Beklenen SHA-256 eşleşti." if expected_match else "Beklenen SHA-256 eşleşmedi.")
                if usb_match is not None:
                    lines.append("USB, ISO ile eşleşti." if usb_match else "USB, ISO ile eşleşmedi.")
                self.media_status.set_text("\n".join(lines))

        self.run_job(work, done)

    def cancel_media(self):
        if self.cancel:
            self.cancel.set()
            self.stop.set_sensitive(False)
