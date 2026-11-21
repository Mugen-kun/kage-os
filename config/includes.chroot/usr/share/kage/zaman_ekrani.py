"""GTK case timeline with live filters, annotations and CSV export."""

from datetime import datetime
from threading import Event

from gi.repository import Gtk

from arac_metin import normalize
from bakim_ekranlari import button, label, table
from rapor import ReportStopped
from zaman_cizelgesi import add_note, display_time, export_csv, list_events


KINDS = ("Vaka", "Dosya kaydı", "Dosya zamanı", "Ağ kaydı", "Sistem günlüğü", "Not")


class CaseTimeline(Gtk.Dialog):
    def __init__(self, parent, case_id, title, run_job):
        super().__init__(title=f"Zaman çizelgesi · {title}", transient_for=parent, modal=True, destroy_with_parent=True)
        self.set_default_size(745, 490)
        self.case_id = case_id
        self.run_job = run_job
        self.events = []
        self.warnings = []
        self.cancel = None
        self.closed = False
        self.add_button("Kapat", Gtk.ResponseType.CLOSE)
        self.connect("response", lambda dialog, _response: dialog.destroy())
        self.connect("destroy", self.cancel_on_destroy)

        page = self.get_content_area()
        page.set_spacing(8)
        page.set_border_width(12)
        filters = Gtk.Box(spacing=8)
        self.search = Gtk.SearchEntry(placeholder_text="Olay, kaynak veya not ara")
        self.search.get_accessible().set_name("Zaman çizelgesinde ara")
        self.kind = Gtk.ComboBoxText()
        self.kind.get_accessible().set_name("Olay türü")
        self.kind.append("all", "Tüm olaylar")
        for kind in KINDS:
            self.kind.append(kind, kind)
        self.kind.set_active_id("all")
        filters.pack_start(self.search, True, True, 0)
        filters.pack_start(self.kind, False, False, 0)
        page.pack_start(filters, False, False, 0)

        toolbar = Gtk.Box(spacing=7)
        self.reload_button = button("Yenile", lambda _control: self.reload())
        self.note_button = button("Not ekle", self.note_dialog, True)
        self.export_button = button("CSV kaydet", self.save_visible)
        self.stop_button = button("Durdur", lambda _control: self.stop_loading())
        self.warning_button = button("Okuma ayrıntıları", self.show_warnings)
        for control in (self.reload_button, self.note_button, self.export_button, self.stop_button, self.warning_button):
            toolbar.pack_start(control, False, False, 0)
        page.pack_start(toolbar, False, False, 0)

        self.status = label("")
        page.pack_start(self.status, False, False, 0)
        self.rows = Gtk.ListStore(str, str, str, str, int, str)
        self.filtered = self.rows.filter_new()
        self.filtered.set_visible_func(self.is_visible)
        scrolled, tree = table(self.filtered, ("Zaman (UTC)", "Tür", "Kaynak", "Olay"))
        tree.get_selection().connect("changed", self.show_detail)
        page.pack_start(scrolled, True, True, 0)
        self.detail = Gtk.TextView(editable=False, cursor_visible=False, wrap_mode=Gtk.WrapMode.WORD_CHAR)
        self.detail.set_left_margin(6)
        self.detail.set_right_margin(6)
        detail_scroll = Gtk.ScrolledWindow()
        detail_scroll.set_min_content_height(64)
        detail_scroll.set_shadow_type(Gtk.ShadowType.IN)
        detail_scroll.add(self.detail)
        page.pack_start(detail_scroll, False, False, 0)
        self.search.connect("search-changed", self.apply_filter)
        self.kind.connect("changed", self.apply_filter)
        self.export_button.set_sensitive(False)
        self.warning_button.set_sensitive(False)
        self.stop_button.set_sensitive(False)
        self.show_all()
        self.reload()

    def is_visible(self, model, item, _data=None):
        kind = self.kind.get_active_id()
        terms = normalize(self.search.get_text()).split()
        return (kind in {None, "all", model[item][1]}) and all(term in model[item][5] for term in terms)

    def apply_filter(self, _widget=None):
        self.filtered.refilter()
        if self.cancel is None:
            self.show_count()
        self.export_button.set_sensitive(bool(len(self.filtered)) and self.cancel is None)

    def show_count(self):
        self.status.set_text(f"{len(self.filtered)} / {len(self.events)} olay"
                             + (f" · {len(self.warnings)} okuma notu" if self.warnings else ""))

    def show_detail(self, selection):
        model, item = selection.get_selected()
        self.detail.get_buffer().set_text(model[item][3] if item else "")

    def reload(self):
        if self.cancel is not None:
            return
        self.cancel = Event()
        cancel = self.cancel
        for control in (self.reload_button, self.note_button, self.export_button):
            control.set_sensitive(False)
        self.stop_button.set_sensitive(True)
        self.status.set_text("Vaka kayıtları okunuyor…")

        def work():
            try:
                return list_events(self.case_id, cancel)
            except ReportStopped:
                return None

        def done(result, error):
            if self.closed:
                return
            self.cancel = None
            self.stop_button.set_sensitive(False)
            self.reload_button.set_sensitive(True)
            self.note_button.set_sensitive(True)
            if error or result is None:
                self.status.set_text(error or "Okuma durduruldu.")
                self.export_button.set_sensitive(bool(len(self.filtered)))
                return
            self.events, self.warnings = result
            self.rows.clear()
            self.detail.get_buffer().set_text("")
            for index, event in enumerate(self.events):
                stamp = display_time(event.time)
                text = normalize(f"{stamp} {event.category} {event.source} {event.detail}")
                self.rows.append((stamp, event.category, event.source, event.detail, index, text))
            self.warning_button.set_sensitive(bool(self.warnings))
            self.apply_filter()

        self.run_job(work, done)

    def stop_loading(self):
        if self.cancel is not None:
            self.cancel.set()
            self.stop_button.set_sensitive(False)
            self.status.set_text("Durduruluyor…")

    def cancel_on_destroy(self, _dialog):
        self.closed = True
        if self.cancel is not None:
            self.cancel.set()

    def note_dialog(self, _control):
        dialog = Gtk.Dialog(title="Zaman çizelgesine not ekle", transient_for=self, modal=True)
        dialog.set_default_size(590, 275)
        dialog.add_button("Vazgeç", Gtk.ResponseType.CANCEL)
        dialog.add_button("Notu kaydet", Gtk.ResponseType.OK)
        page = dialog.get_content_area()
        page.set_border_width(14)
        page.set_spacing(8)
        stamp = Gtk.Entry(text=datetime.now().astimezone().isoformat(sep=" ", timespec="seconds"), max_length=40)
        stamp.get_accessible().set_name("Olay tarihi, saat ve saat farkı")
        page.pack_start(label("Olay tarihi, saat ve saat farkı"), False, False, 0)
        page.pack_start(stamp, False, False, 0)
        note = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR)
        note.get_accessible().set_name("Olay notu")
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_shadow_type(Gtk.ShadowType.IN)
        scrolled.add(note)
        page.pack_start(scrolled, True, True, 0)
        guidance = label("")
        page.pack_start(guidance, False, False, 0)
        dialog.show_all()
        while dialog.run() == Gtk.ResponseType.OK:
            buffer = note.get_buffer()
            try:
                add_note(self.case_id, stamp.get_text(), buffer.get_text(*buffer.get_bounds(), True))
            except (OSError, ValueError) as error:
                guidance.set_text(str(error))
            else:
                self.reload()
                break
        dialog.destroy()

    def save_visible(self, _control):
        selected = [self.events[row[4]] for row in self.filtered]
        picker = Gtk.FileChooserNative.new("Görünen olayları kaydet", self, Gtk.FileChooserAction.SAVE, "Kaydet", "Vazgeç")
        picker.set_current_name("zaman-cizelgesi.csv")
        picker.set_do_overwrite_confirmation(True)
        try:
            destination = picker.get_filename() if picker.run() == Gtk.ResponseType.ACCEPT else None
        finally:
            picker.destroy()
        if destination:
            try:
                export_csv(destination, selected)
            except OSError as error:
                self.status.set_text(str(error))
            else:
                self.status.set_text(f"{len(selected)} olay CSV olarak kaydedildi.")

    def show_warnings(self, _control):
        dialog = Gtk.Dialog(title="Zaman çizelgesi okuma ayrıntıları", transient_for=self, modal=True)
        dialog.set_default_size(610, 315)
        dialog.add_button("Kapat", Gtk.ResponseType.CLOSE)
        scrolled = Gtk.ScrolledWindow()
        text = Gtk.TextView(editable=False, cursor_visible=False, wrap_mode=Gtk.WrapMode.WORD_CHAR)
        text.get_buffer().set_text("\n".join(self.warnings))
        scrolled.add(text)
        dialog.get_content_area().pack_start(scrolled, True, True, 9)
        dialog.show_all()
        dialog.run()
        dialog.destroy()
