"""Kage Merkez pages for everyday desktop work."""

from pathlib import Path
import shutil
import subprocess
from threading import Event

from gi.repository import Gdk, GdkPixbuf, Gio, GLib, Gtk, Pango

from bakim_ekranlari import button, column, label, table
from gunluk_dosyalar import FORMATS, export_files, plan_copy, run_copy
from kitaplik import ASSETS, TYPES, book_preview, import_books, library_directory, search_library
from kurtarma import create_user_point
from masaustu import Presentation, open_study, saved_theme, store_theme
from paylasim import ShareSession, local_addresses
from rapor import ReportStopped, regular_file


def heading(text):
    title = label(text)
    title.get_style_context().add_class("kage-section")
    return title


def save_folder(title, initial=None):
    chooser = Gtk.FileChooserButton(title=title, action=Gtk.FileChooserAction.SELECT_FOLDER)
    if initial:
        chooser.set_filename(str(initial))
    chooser.get_accessible().set_name(title)
    chooser.set_width_chars(14)
    return chooser


def file_filter(title, extensions):
    option = Gtk.FileFilter()
    option.set_name(title)
    for extension in sorted(extensions):
        option.add_pattern("*" + extension)
        option.add_pattern("*" + extension.upper())
    return option


def toolbar(*widgets):
    bar = Gtk.Box(spacing=8)
    for widget in widgets:
        bar.pack_start(widget, False, False, 0)
    return bar


class DailyWorkspace(Gtk.Box):
    def __init__(self, run_job, notice):
        super().__init__(spacing=14)
        self.run_job = run_job
        self.notice = notice
        self.cancel = None
        self.presentation = Presentation()
        self.inhibit = None
        self.share = None
        self.share_tick = 0
        self.address_rows = []
        self.address_requested = False
        self.plan = None
        self.workshop_sources = []
        self.outgoing = []

        self.stack = Gtk.Stack(hhomogeneous=False, vhomogeneous=False)
        for key, title, page in (
            ("desktop", "Masaüstü düzenleri", self.desktop_page()),
            ("workshop", "Dosya atölyesi", self.workshop_page()),
            ("share", "Telefon paylaşımı", self.share_page()),
            ("library", "Çevrimdışı kitaplık", self.library_page()),
            ("recovery", "Dosya kurtarma", self.recovery_page()),
            ("appearance", "Görünüm", self.appearance_page()),
        ):
            scrolled = Gtk.ScrolledWindow()
            scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
            page.set_margin_end(10)
            page.set_margin_bottom(4)
            scrolled.add(page)
            self.stack.add_titled(scrolled, key, title)
        self.stack.connect("notify::visible-child-name", self.on_page)
        sidebar = Gtk.StackSidebar(stack=self.stack)
        sidebar.set_name("kage-daily-nav")
        sidebar.get_accessible().set_name("Günlük kullanım bölümleri")
        self.pack_start(sidebar, False, False, 0)
        self.pack_start(self.stack, True, True, 0)

    def on_page(self, _stack, _property):
        if self.stack.get_visible_child_name() == "share" and not self.address_requested:
            self.refresh_addresses(None)

    def close(self):
        if self.cancel:
            self.cancel.set()
        self.stop_share()
        self.end_presentation()

    def choose(self, title, *, extensions=(), multiple=True):
        dialog = Gtk.FileChooserNative.new(title, self.get_toplevel(), Gtk.FileChooserAction.OPEN, "Seç", "Vazgeç")
        dialog.set_select_multiple(multiple)
        if extensions:
            dialog.add_filter(file_filter("Desteklenen dosyalar", extensions))
        try:
            return dialog.get_filenames() if dialog.run() == Gtk.ResponseType.ACCEPT else []
        finally:
            dialog.destroy()

    def open_path(self, path):
        try:
            Gtk.show_uri_on_window(self.get_toplevel(), Path(path).absolute().as_uri(), Gdk.CURRENT_TIME)
        except GLib.Error as error:
            self.notice("Dosya açılamadı", error.message)

    def launch(self, *arguments):
        try:
            Gio.Subprocess.new(list(arguments), Gio.SubprocessFlags.NONE)
        except GLib.Error as error:
            self.notice("Uygulama açılamadı", error.message)

    def cancel_button(self):
        def stop(widget):
            if self.cancel:
                self.cancel.set()
                widget.set_sensitive(False)

        control = button("Durdur", stop)
        control.set_sensitive(False)
        return control

    def task(self, status, start, stop, running, work, on_done):
        if self.cancel:
            status.set_text("Başka bir dosya işlemi sürüyor.")
            return
        self.cancel = Event()
        token = self.cancel
        status.set_text(running)
        start.set_sensitive(False)
        stop.set_sensitive(True)

        def execute():
            try:
                return work(token)
            except ReportStopped:
                return None

        def done(result, error):
            self.cancel = None
            stop.set_sensitive(False)
            start.set_sensitive(True)
            if error:
                status.set_text(error)
            elif result is None:
                status.set_text("İşlem durduruldu.")
            else:
                on_done(result)

        self.run_job(execute, done)

    def desktop_page(self):
        page = column()
        page.pack_start(heading("Masaüstü düzenleri"), False, False, 0)
        study = column(5)
        study.get_style_context().add_class("kage-card")
        study.pack_start(heading("Ders"), False, False, 0)
        study.pack_start(label("PDF’yi ve ders notlarını yan yana aç."), False, False, 0)
        self.study_pdf = Gtk.FileChooserButton(title="Ders PDF’sini seç", action=Gtk.FileChooserAction.OPEN)
        self.study_pdf.add_filter(file_filter("PDF", {".pdf"}))
        self.study_pdf.set_width_chars(14)
        study_row = Gtk.Box(spacing=8)
        study_row.pack_start(self.study_pdf, True, True, 0)
        study_row.pack_start(button("Ders düzenini aç", self.study), False, False, 0)
        study.pack_start(study_row, False, False, 0)
        self.desktop_status = label("")
        study.pack_start(self.desktop_status, False, False, 0)
        page.pack_start(study, False, False, 0)

        presentation = column(5)
        presentation.get_style_context().add_class("kage-card")
        presentation.pack_start(heading("Sunum"), False, False, 0)
        self.presentation_status = label("Bildirimleri sustur ve istersen ikinci ekranı ayarla.")
        presentation.pack_start(self.presentation_status, False, False, 0)
        self.presentation_begin = button("Başlat", self.begin_presentation, True)
        self.presentation_end = button("Bitir", lambda _widget: self.end_presentation())
        self.presentation_end.set_sensitive(False)
        presentation.pack_start(toolbar(
            self.presentation_begin,
            button("İkinci ekran", lambda _widget: self.launch("xfce4-display-settings", "--minimal")),
            self.presentation_end,
        ), False, False, 0)
        page.pack_start(presentation, False, False, 0)

        lounge = column(5)
        lounge.get_style_context().add_class("kage-card")
        lounge.pack_start(heading("Salon"), False, False, 0)
        lounge.pack_start(label("TV’de film veya müzik aç. Oynatma için mpv paketi kullanılır."), False, False, 0)
        lounge.pack_start(button("Salon ekranını aç", self.open_lounge), False, False, 0)
        page.pack_start(lounge, False, False, 0)
        return page

    def study(self, control):
        top = self.get_toplevel()
        window = top.get_window()
        area = top.get_display().get_monitor_at_window(window).get_workarea()
        workarea = area.x, area.y, area.width, area.height
        document = self.study_pdf.get_filename()
        control.set_sensitive(False)
        self.desktop_status.set_text("Ders düzeni açılıyor…")

        def done(tiled, error):
            control.set_sensitive(True)
            note = "Ders notları Kage-Notlar/ders.txt dosyasında."
            self.desktop_status.set_text(error or ("PDF ve notlar yan yana açıldı." if tiled else note))

        self.run_job(lambda: open_study(document, workarea), done)

    def begin_presentation(self, _control):
        try:
            self.presentation.start()
            top = self.get_toplevel()
            app = top.get_application()
            token = app.inhibit(top, Gtk.ApplicationInhibitFlags.IDLE, "Kage sunumu sürüyor")
            if token:
                self.inhibit = app, token
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            self.presentation_status.set_text(str(error))
            return
        self.presentation_begin.set_sensitive(False)
        self.presentation_end.set_sensitive(True)
        self.presentation_status.set_text("Sunum açık. Bildirimler sessizde.")

    def end_presentation(self):
        if self.inhibit:
            app, token = self.inhibit
            app.uninhibit(token)
            self.inhibit = None
        if self.presentation.active:
            try:
                self.presentation.stop()
                self.presentation_status.set_text("Önceki bildirim ayarına dönüldü.")
            except (OSError, ValueError, subprocess.SubprocessError) as error:
                self.presentation_status.set_text(str(error))
                return
            self.presentation_begin.set_sensitive(True)
            self.presentation_end.set_sensitive(False)

    def open_lounge(self, _control):
        if not shutil.which("mpv"):
            self.notice("Salon için oynatıcı gerekiyor", "Synaptic’te mpv paketini seç veya terminalde sudo apt install mpv çalıştır.")
            return
        screen = Gtk.Window(title="Kage Salon", transient_for=self.get_toplevel(), modal=True, destroy_with_parent=True)
        screen.fullscreen()
        screen.connect("key-press-event", lambda widget, event: self.close_lounge(widget, event))
        pane = column(18)
        pane.set_halign(Gtk.Align.CENTER)
        pane.set_valign(Gtk.Align.CENTER)
        screen.add(pane)
        title = label("Kage Salon")
        title.get_style_context().add_class("kage-title")
        pane.pack_start(title, False, False, 0)
        pane.pack_start(label("Boşluk oynatır veya duraklatır. Ok tuşlarıyla konumu değiştir. Q ile oynatıcıdan çık."), False, False, 0)

        def play(_widget):
            dialog = Gtk.FileChooserNative.new("Film veya müzik seç", screen, Gtk.FileChooserAction.OPEN, "Oynat", "Vazgeç")
            media = Gtk.FileFilter()
            media.set_name("Film ve müzik")
            media.add_mime_type("video/*")
            media.add_mime_type("audio/*")
            dialog.add_filter(media)
            chosen = dialog.get_filename() if dialog.run() == Gtk.ResponseType.ACCEPT else None
            dialog.destroy()
            if chosen:
                try:
                    source = regular_file(chosen, "Oynatılacak dosyayı")
                    self.launch("mpv", "--fullscreen", "--force-window=yes", "--osc=yes", "--", str(source))
                except (OSError, ValueError) as error:
                    self.notice("Dosya açılamadı", str(error))

        for text, activation in (("Film veya müzik seç", play), ("Masaüstüne dön", lambda _widget: screen.destroy())):
            action = button(text, activation, text.startswith("Film"))
            action.set_size_request(280, 64)
            pane.pack_start(action, False, False, 0)
        screen.show_all()

    @staticmethod
    def close_lounge(window, event):
        if event.keyval == Gdk.KEY_Escape:
            window.destroy()
            return True
        return False

    def workshop_page(self):
        page = column()
        page.pack_start(heading("Dosya atölyesi"), False, False, 0)
        self.operation = Gtk.ComboBoxText()
        for key, title in (("pdf", "PDF’den sayfa ayır"), ("photo", "Fotoğrafları küçült"), ("video", "Telefon için MP4 hazırla")):
            self.operation.append(key, title)
        self.operation.set_active_id("pdf")
        page.pack_start(self.operation, False, False, 0)

        self.settings = Gtk.Stack()
        self.pages = Gtk.Entry(placeholder_text="Sayfa aralığı, örneğin 2-5")
        self.pages.set_text("1")
        self.pages.get_accessible().set_name("PDF sayfa aralığı")
        self.settings.add_named(self.pages, "pdf")
        self.dimension = Gtk.SpinButton.new_with_range(128, 3840, 16)
        self.dimension.set_value(1280)
        self.dimension.get_accessible().set_name("Fotoğrafın en uzun kenarı, piksel")
        self.settings.add_named(toolbar(label("En uzun kenar (piksel)"), self.dimension), "photo")
        self.settings.add_named(label("En fazla 1280 piksel genişliğinde H.264 ve AAC sesli MP4. ffmpeg paketi gerekir."), "video")
        self.operation.connect("changed", lambda field: self.settings.set_visible_child_name(field.get_active_id()))
        page.pack_start(self.settings, False, False, 0)

        drop = Gtk.EventBox()
        drop.get_style_context().add_class("kage-card")
        self.workshop_selection = label("Dosyaları bu alana sürükle.")
        drop.add(self.workshop_selection)
        drop.drag_dest_set(Gtk.DestDefaults.ALL, [], Gdk.DragAction.COPY)
        drop.drag_dest_add_uri_targets()
        drop.connect("drag-data-received", self.drop_workshop_files)
        page.pack_start(drop, False, False, 0)
        page.pack_start(button("Dosya seç", self.choose_workshop_files), False, False, 0)

        self.workshop_destination = save_folder("Çıktı klasörü", Path.home())
        page.pack_start(toolbar(label("Çıktı klasörü"), self.workshop_destination), False, False, 0)
        self.workshop_start = button("Hazırla", self.start_workshop, True)
        self.workshop_stop = self.cancel_button()
        page.pack_start(toolbar(self.workshop_start, self.workshop_stop,
                                button("Klasörü aç", lambda _widget: self.open_selected_folder(self.workshop_destination))), False, False, 0)
        self.workshop_status = label("")
        self.workshop_status.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
        page.pack_start(self.workshop_status, False, False, 0)
        return page

    def workshop_files(self, values):
        self.workshop_sources = list(dict.fromkeys(values))
        if self.workshop_sources:
            self.workshop_selection.set_text(f"{len(self.workshop_sources)} dosya seçildi · {Path(values[0]).name}")

    def choose_workshop_files(self, _control):
        chosen = self.choose("Dönüştürülecek dosyaları seç", extensions=FORMATS[self.operation.get_active_id()])
        if chosen:
            self.workshop_files(chosen)

    def drop_workshop_files(self, _widget, context, _x, _y, selection, _kind, timestamp):
        files = [Gio.File.new_for_uri(uri).get_path() for uri in selection.get_uris()]
        local = [path for path in files if path]
        if local:
            self.workshop_files(local)
        Gtk.drag_finish(context, bool(local), False, timestamp)

    def open_selected_folder(self, chooser):
        if path := chooser.get_filename():
            self.open_path(path)

    def start_workshop(self, _control):
        if not self.workshop_sources:
            self.workshop_status.set_text("Önce bir dosya seç veya sürükle.")
            return
        action = self.operation.get_active_id()
        value = self.pages.get_text() if action == "pdf" else self.dimension.get_value_as_int()
        paths = self.workshop_sources.copy()
        folder = self.workshop_destination.get_filename()

        def done(result):
            outputs, errors, stopped = result
            lines = [f"{len(outputs)} dosya hazır." + (" İşlem durduruldu." if stopped else "")]
            if outputs:
                lines.append(", ".join(path.name for path in outputs[:4]))
            lines.extend(errors[:3])
            if len(errors) > 3:
                lines.append(f"{len(errors) - 3} dosya daha işlenemedi.")
            self.workshop_status.set_text("\n".join(lines))

        self.task(self.workshop_status, self.workshop_start, self.workshop_stop, "Dosyalar hazırlanıyor…",
                  lambda cancel: export_files(action, paths, folder, value, cancel), done)

    def share_page(self):
        page = column()
        page.pack_start(heading("Telefon paylaşımı"), False, False, 0)
        page.pack_start(label("Telefon ve bilgisayar aynı yerel ağa bağlıyken QR koduyla dosya gönder veya al."), False, False, 0)
        self.share_form = column(7)
        self.address = Gtk.ComboBoxText()
        self.address.get_accessible().set_name("Paylaşım için ağ adresi")
        addresses = Gtk.Box(spacing=8)
        addresses.pack_start(self.address, True, True, 0)
        addresses.pack_start(button("Yenile", self.refresh_addresses), False, False, 0)
        self.share_form.pack_start(addresses, False, False, 0)
        self.outgoing_text = label("Gönderilecek dosya seçilmedi.")
        self.share_form.pack_start(self.outgoing_text, False, False, 0)
        self.share_form.pack_start(toolbar(
            button("Dosya ekle", self.choose_outgoing),
            button("Seçimi temizle", self.clear_outgoing),
        ), False, False, 0)
        self.receive = Gtk.CheckButton(label="Telefondan gelenleri Kage-Paylasim klasörüne kaydet", active=True)
        self.share_form.pack_start(self.receive, False, False, 0)
        page.pack_start(self.share_form, False, False, 0)
        self.share_start = button("QR paylaşımını başlat", self.start_share, True)
        self.share_stop = button("Paylaşımı bitir", lambda _widget: self.stop_share())
        self.share_stop.set_sensitive(False)
        page.pack_start(toolbar(self.share_start, self.share_stop, button("Alınanları aç", self.open_received)), False, False, 0)
        self.share_status = label("")
        page.pack_start(self.share_status, False, False, 0)
        self.qr_area = Gtk.Box(spacing=12)
        self.qr_area.set_no_show_all(True)
        self.qr = Gtk.Image()
        self.qr.get_accessible().set_name("Telefonla okutulacak QR kodu")
        self.qr_area.pack_start(self.qr, False, False, 0)
        qr_text = column(6)
        qr_text.set_valign(Gtk.Align.CENTER)
        qr_text.pack_start(label("Telefonun kamerasıyla QR kodunu okut veya bu adresi aç."), False, False, 0)
        self.share_url = Gtk.Entry(editable=False)
        self.share_url.get_accessible().set_name("Telefon paylaşımı adresi")
        self.share_url.set_width_chars(20)
        qr_text.pack_start(self.share_url, False, False, 0)
        self.qr_area.pack_start(qr_text, True, True, 0)
        page.pack_start(self.qr_area, False, False, 0)
        return page

    def refresh_addresses(self, _control):
        if self.share:
            return
        self.address_requested = True
        self.share_start.set_sensitive(False)

        def done(rows, error):
            if self.share:
                return
            self.address_rows = rows or []
            self.address.remove_all()
            for index, (name, binding) in enumerate(self.address_rows):
                self.address.append(str(index), f"{name} · {binding.ip}")
            if self.address_rows:
                self.address.set_active(0)
            self.share_start.set_sensitive(bool(self.address_rows))
            self.share_status.set_text(error or ("" if self.address_rows else "Yerel IPv4 adresi bulunamadı. Ağa bağlanınca yenile."))

        self.run_job(local_addresses, done)

    def choose_outgoing(self, _control):
        if chosen := self.choose("Telefona gönderilecek dosyaları seç"):
            self.outgoing = list(dict.fromkeys(chosen))
            self.outgoing_text.set_text(f"{len(self.outgoing)} dosya gönderime hazır.")

    def clear_outgoing(self, _control):
        self.outgoing.clear()
        self.outgoing_text.set_text("Gönderilecek dosya seçilmedi.")

    def open_received(self, _control):
        destination = Path.home() / "Kage-Paylasim"
        if destination.is_dir():
            self.open_path(destination)
        else:
            self.share_status.set_text("Kage-Paylasim klasörü ilk alım oturumunda açılır.")

    def start_share(self, _control):
        if self.share or self.address.get_active() < 0:
            return
        try:
            destination = None
            if self.receive.get_active():
                destination = Path.home() / "Kage-Paylasim"
                destination.mkdir(mode=0o700, parents=True, exist_ok=True)
            self.share = ShareSession(self.address_rows[self.address.get_active()][1], self.outgoing, destination)
            qr = subprocess.check_output(
                ["qrencode", "-t", "PNG", "-s", "4", "-m", "4", "-o", "-", "--", self.share.url],
                stderr=subprocess.DEVNULL, timeout=4,
            )
            decoder = GdkPixbuf.PixbufLoader.new_with_type("png")
            decoder.write(qr)
            decoder.close()
            self.qr.set_from_pixbuf(decoder.get_pixbuf())
        except (OSError, ValueError, GLib.Error, subprocess.SubprocessError) as error:
            self.stop_share()
            self.share_status.set_text(f"Paylaşım başlatılamadı. {error}")
            return
        self.share_form.set_sensitive(False)
        self.share_start.set_sensitive(False)
        self.share_stop.set_sensitive(True)
        self.share_url.set_text(self.share.url)
        self.qr_area.set_no_show_all(False)
        self.qr_area.show_all()
        self.share_tick = GLib.timeout_add_seconds(1, self.update_share)
        self.update_share()

    def update_share(self):
        if self.share and self.share.remaining:
            minutes, seconds = divmod(int(self.share.remaining), 60)
            self.share_status.set_text(f"Kalan süre {minutes}:{seconds:02d} · Alınan {self.share.received_count()} dosya")
            return True
        self.share_tick = 0
        self.stop_share("Paylaşım süresi doldu.")
        return False

    def stop_share(self, message="Paylaşım kapatıldı."):
        if self.share_tick:
            GLib.source_remove(self.share_tick)
            self.share_tick = 0
        if self.share:
            self.share.close()
            self.share = None
        self.qr_area.hide()
        self.qr_area.set_no_show_all(True)
        self.qr.clear()
        self.share_url.set_text("")
        self.share_status.set_text(message)
        self.share_form.set_sensitive(True)
        self.share_start.set_sensitive(bool(self.address_rows))
        self.share_stop.set_sensitive(False)

    def library_page(self):
        page = column()
        page.pack_start(heading("Çevrimdışı kitaplık"), False, False, 0)
        page.pack_start(label("Mini sözlüğü, Kage kılavuzunu ve eklediğin PDF, EPUB, Markdown veya metin dosyalarını ara."), False, False, 0)
        row = Gtk.Box(spacing=8)
        self.library_query = Gtk.SearchEntry(placeholder_text="Sözcük veya ifade ara")
        self.library_query.connect("activate", self.search_books)
        row.pack_start(self.library_query, True, True, 0)
        self.library_go = button("Ara", self.search_books, True)
        row.pack_start(self.library_go, False, False, 0)
        page.pack_start(row, False, False, 0)
        self.library_add = button("Kaynak ekle", self.add_books)
        self.library_stop = self.cancel_button()
        page.pack_start(toolbar(self.library_add,
                                button("Mini sözlüğü aç", lambda _widget: self.open_path(ASSETS / "gunluk/mini-sozluk.txt")),
                                self.library_stop), False, False, 0)
        self.library_status = label("")
        page.pack_start(self.library_status, False, False, 0)
        self.matches = Gtk.ListStore(str, str, str)
        result, view = table(self.matches, ("Kaynak", "Eşleşme"))
        result.set_min_content_height(145)
        view.connect("row-activated", self.open_library_result)
        view.get_selection().connect("changed", self.show_excerpt)
        page.pack_start(result, True, True, 0)
        self.excerpt = label("", selectable=True)
        self.excerpt.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
        page.pack_start(self.excerpt, False, False, 0)
        return page

    def show_excerpt(self, view_selection):
        model, item = view_selection.get_selected()
        self.excerpt.set_text(model[item][1] if item else "")

    def open_library_result(self, _view, row, _column):
        path = Path(self.matches[row][2])
        if path.suffix.lower() == ".pdf":
            self.launch("zathura", str(path))
        elif path.suffix.lower() == ".epub":
            self.run_job(lambda: book_preview(path), lambda value, error: self.show_book(path, value, error))
        else:
            self.open_path(path)

    def show_book(self, path, value, error):
        if error:
            self.library_status.set_text(error)
            return
        text, shortened = value
        dialog = Gtk.Dialog(title=path.name, transient_for=self.get_toplevel(), modal=True)
        dialog.set_default_size(650, 445)
        dialog.add_button("Kapat", Gtk.ResponseType.CLOSE)
        content = dialog.get_content_area()
        if shortened:
            content.pack_start(label("Önizleme kitabın ilk 600.000 karakterini gösterir."), False, False, 8)
        scroll = Gtk.ScrolledWindow()
        book = Gtk.TextView(editable=False, wrap_mode=Gtk.WrapMode.WORD_CHAR, left_margin=12, right_margin=12)
        book.get_buffer().set_text(text or "Okunabilir EPUB metni bulunamadı.")
        scroll.add(book)
        content.pack_start(scroll, True, True, 6)
        dialog.show_all()
        dialog.run()
        dialog.destroy()

    def add_books(self, _control):
        paths = self.choose("Kitaplığa eklenecek dosyaları seç", extensions=TYPES)
        if paths:
            def done(saved):
                self.library_status.set_text(f"{len(saved)} kaynak {library_directory().name} klasörüne eklendi.")
            self.task(self.library_status, self.library_add, self.library_stop, "Kaynaklar kopyalanıyor…",
                      lambda cancel: import_books(paths, cancel), done)

    def search_books(self, _control):
        text = self.library_query.get_text()

        def done(result):
            hits, errors = result
            self.matches.clear()
            for source, excerpt in hits:
                self.matches.append((source.name, excerpt, str(source)))
            message = f"{len(hits)} eşleşme. Kaynağı açmak için sonuca çift tıkla." if hits else "Eşleşme bulunamadı."
            if errors:
                message += f" {len(errors)} kaynak okunamadı."
            self.library_status.set_text(message)

        self.task(self.library_status, self.library_go, self.library_stop, "Kitaplık aranıyor…",
                  lambda cancel: search_library(text, cancel), done)

    def recovery_page(self):
        page = column()
        page.pack_start(heading("Dosya kurtarma"), False, False, 0)
        page.pack_start(label("Kaynak klasörü ve farklı bir hedef konumu seç. Kage gerekli alanı hesaplar ve kopyaları SHA-256 ile doğrular."), False, False, 0)
        self.recovery_source = save_folder("Kaynak klasör")
        self.recovery_target = save_folder("Hedef klasör")
        for text, field in (("Kaynak klasör", self.recovery_source), ("Hedef klasör", self.recovery_target)):
            field.connect("file-set", self.clear_plan)
            row = Gtk.Box(spacing=8)
            title = label(text)
            title.set_width_chars(14)
            row.pack_start(title, False, False, 0)
            row.pack_start(field, True, True, 0)
            page.pack_start(row, False, False, 0)
        page.pack_start(button("Diskleri dosya yöneticisinde aç", lambda _widget: self.launch("thunar")), False, False, 0)
        self.recovery_scan = button("Gereken alanı hesapla", self.measure)
        self.recovery_start = button("Kopyala ve doğrula", self.recover, True)
        self.recovery_start.set_sensitive(False)
        self.recovery_stop = self.cancel_button()
        page.pack_start(toolbar(self.recovery_scan, self.recovery_start, self.recovery_stop), False, False, 0)
        self.recovery_open = button("Kopyaları aç", lambda _widget: self.open_path(self.recovery_result))
        self.recovery_open.set_sensitive(False)
        page.pack_start(self.recovery_open, False, False, 0)
        self.recovery_status = label("")
        self.recovery_status.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
        page.pack_start(self.recovery_status, False, False, 0)
        return page

    def clear_plan(self, _chooser):
        self.plan = None
        self.recovery_start.set_sensitive(False)
        self.recovery_status.set_text("Gereken alanı yeniden hesapla.")

    def measure(self, _control):
        source = self.recovery_source.get_filename()
        destination = self.recovery_target.get_filename()
        self.plan = None
        self.recovery_start.set_sensitive(False)

        def done(plan):
            if source != self.recovery_source.get_filename() or destination != self.recovery_target.get_filename():
                self.clear_plan(None)
                return
            self.plan = plan
            free = shutil.disk_usage(plan.destination).free
            text = f"{len(plan.entries)} dosya, gereken {GLib.format_size(plan.size)}, boş {GLib.format_size(free)}."
            if plan.unreadable:
                text += f" {len(plan.unreadable)} konum okunamadı."
            self.recovery_status.set_text(text)
            self.recovery_start.set_sensitive(bool(plan.entries and plan.size <= free))

        self.task(self.recovery_status, self.recovery_scan, self.recovery_stop, "Kaynak klasör okunuyor…",
                  lambda cancel: plan_copy(source, destination, cancel), done)

    def recover(self, _control):
        plan = self.plan
        if plan is None:
            return

        def done(result):
            folder, count, errors, stopped = result
            self.recovery_result = folder
            self.recovery_open.set_sensitive(True)
            message = f"{count} dosya doğrulandı."
            if stopped:
                message += " Kopyalama durduruldu."
            if errors:
                message += f" {len(errors)} dosya veya konum atlandı.\n" + "\n".join(errors[:3])
            self.recovery_status.set_text(message)
            if self.plan is None:
                self.recovery_start.set_sensitive(False)

        self.task(self.recovery_status, self.recovery_start, self.recovery_stop, "Dosyalar kopyalanıyor ve doğrulanıyor…",
                  lambda cancel: run_copy(plan, cancel), done)

    def appearance_page(self):
        page = column()
        hero = column(6)
        hero.get_style_context().add_class("kage-hero")
        logo = Gtk.Image.new_from_icon_name("kage", Gtk.IconSize.DIALOG)
        logo.set_halign(Gtk.Align.START)
        logo.set_pixel_size(54)
        hero.pack_start(logo, False, False, 0)
        hero.pack_start(heading("Kage görünümü"), False, False, 0)
        hero.pack_start(label("Açık veya koyu tema seç. Otomatik düzen yerel saatle 07.00 ve 19.00’da geçiş yapar."), False, False, 0)
        page.pack_start(hero, False, False, 0)
        self.theme = Gtk.ComboBoxText()
        self.theme.get_accessible().set_name("Masaüstü teması")
        for key, title in (("acik", "Açık"), ("koyu", "Koyu"), ("otomatik", "Gündüz açık, akşam koyu")):
            self.theme.append(key, title)
        if not self.theme.set_active_id(saved_theme()):
            self.theme.set_active_id("koyu")
        page.pack_start(self.theme, False, False, 0)
        page.pack_start(toolbar(
            button("Temayı uygula", self.apply_theme, True),
            button("Duvar kâğıdı ayarları", lambda _widget: self.launch("xfdesktop-settings")),
        ), False, False, 0)
        self.theme_status = label("")
        page.pack_start(self.theme_status, False, False, 0)
        return page

    def apply_theme(self, control):
        selection = self.theme.get_active_id()
        self.theme.set_sensitive(False)
        control.set_sensitive(False)

        def done(scheduled, error):
            self.theme.set_sensitive(True)
            control.set_sensitive(True)
            if error:
                message = error
            elif scheduled:
                message = "Otomatik geçiş açık." if selection == "otomatik" else "Tema uygulandı."
            else:
                message = "Şimdiki tema uygulandı. Otomatik saat geçişi bu oturumda başlatılamadı."
            self.theme_status.set_text(message)

        def work():
            create_user_point("Görünüm değişikliği öncesi")
            return store_theme(selection)

        self.run_job(work, done)
