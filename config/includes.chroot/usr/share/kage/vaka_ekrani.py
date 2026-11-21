"""GTK workspace for local evidence references and case report folders."""

from threading import Event

from gi.repository import Gdk, Gio, GLib, Gtk, Pango

from bakim_ekranlari import button, column, label, table
from rapor import ReportStopped
from vaka import (CTF_PROFILES, case_path, create_case, lab_link, list_cases, read_case, read_workspace,
                  register_file, report_destination, save_workspace)


class CaseWorkspace(Gtk.Box):
    def __init__(self, run_job):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.run_job = run_job
        self.cancel = None
        self.timeline = None
        form = Gtk.Box(spacing=8)
        self.name = Gtk.Entry(placeholder_text="Yeni vakanın adı", max_length=80)
        self.name.connect("activate", self.new_case)
        self.create = button("Vaka oluştur", self.new_case, True)
        form.pack_start(self.name, True, True, 0)
        form.pack_start(self.create, False, False, 0)
        self.pack_start(form, False, False, 0)

        self.selection = Gtk.ComboBoxText()
        self.selection.get_accessible().set_name("Vaka seç")
        self.selection.connect("changed", self.show_case)
        self.pack_start(self.selection, False, False, 0)
        actions = Gtk.Box(spacing=8)
        self.add_file = button("Dosya kaydet", self.choose_file, True)
        self.analyze = button("Vakada incele", self.open_analysis)
        self.open_reports = button("Rapor klasörü", self.show_reports)
        self.ctf = button("CTF alanı", self.open_workspace)
        self.timeline_button = button("Zaman çizelgesi", self.open_timeline)
        self.stop = button("Durdur", lambda _button: self.cancel_hash())
        for control in (self.add_file, self.analyze, self.open_reports, self.ctf, self.timeline_button, self.stop):
            actions.pack_start(control, False, False, 0)
        self.pack_start(actions, False, False, 0)
        self.info = label("Ağ kayıtları ve disk imajları için bir vaka oluştur.")
        self.pack_start(self.info, False, False, 0)
        self.files = Gtk.ListStore(str, str, str, str, str, str)
        display, view = table(self.files, ("Tür", "Dosya", "SHA-256", "Kayıt (UTC)"))
        view.get_selection().connect("changed", self.show_file_detail)
        self.pack_start(display, True, True, 0)
        self.detail = label("", selectable=True)
        self.detail.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
        self.pack_start(self.detail, False, False, 0)
        self.controls()

    def controls(self):
        available = self.selection.get_active_id() is not None and self.cancel is None
        for control in (self.name, self.create, self.selection):
            control.set_sensitive(self.cancel is None)
        for control in (self.add_file, self.analyze, self.open_reports, self.ctf, self.timeline_button):
            control.set_sensitive(available)
        self.stop.set_sensitive(self.cancel is not None)

    def reload_cases(self, preferred=None):
        if self.cancel:
            return
        current = preferred or self.selection.get_active_id()
        try:
            choices = list_cases()
        except (OSError, ValueError) as error:
            self.info.set_text(f"Vakalar okunamadı. {error}")
            return
        self.selection.remove_all()
        for case_id, name in choices:
            self.selection.append(case_id, name)
        if current and any(case_id == current for case_id, _name in choices):
            self.selection.set_active_id(current)
        elif choices:
            self.selection.set_active(0)
        else:
            self.controls()

    def new_case(self, _control):
        try:
            case_id = create_case(self.name.get_text())
        except (OSError, ValueError) as error:
            self.info.set_text(str(error))
            return
        self.name.set_text("")
        self.reload_cases(case_id)

    def show_case(self, _selection):
        self.files.clear()
        self.detail.set_text("")
        self.controls()
        case_id = self.selection.get_active_id()
        if not case_id:
            return
        try:
            case = read_case(case_path(case_id))
        except (OSError, ValueError) as error:
            self.info.set_text(str(error))
            return
        for entry in case["files"]:
            self.files.append((entry["kind"], entry["name"], entry["sha256"], entry["added"][:19].replace("T", " "),
                               entry["path"], str(entry["size"])))
        self.info.set_text(f'{len(case["files"])} dosya kaydı. Dosyalar kendi konumlarından okunur.')

    def show_file_detail(self, selection):
        model, item = selection.get_selected()
        if item is None:
            self.detail.set_text("")
            return
        self.detail.set_text(f"{model[item][4]} · {model[item][5]} bayt\nSHA-256 {model[item][2]}")

    def choose_file(self, _control):
        dialog = Gtk.FileChooserNative.new(
            "Vakaya kaydedilecek dosyayı seç", self.get_toplevel(), Gtk.FileChooserAction.OPEN, "Kaydet", "Vazgeç"
        )
        chosen = dialog.run() == Gtk.ResponseType.ACCEPT
        filename = dialog.get_filename()
        dialog.destroy()
        if not chosen or not filename:
            return
        case_id = self.selection.get_active_id()
        self.cancel = Event()
        event = self.cancel
        self.controls()
        self.info.set_text("Dosya okunuyor ve SHA-256 hesaplanıyor…")

        def work():
            try:
                return register_file(case_id, filename, event)
            except ReportStopped:
                return None

        def done(written, error):
            self.cancel = None
            self.show_case(self.selection)
            if error:
                self.info.set_text(error)
            elif written is None:
                self.info.set_text("İşlem durduruldu.")
            elif not written:
                self.info.set_text("Dosya bu SHA-256 değeriyle zaten kayıtlı.")

        self.run_job(work, done)

    def cancel_hash(self):
        if self.cancel:
            self.cancel.set()
            self.stop.set_sensitive(False)

    def open_analysis(self, _control):
        try:
            case_id = self.selection.get_active_id()
            report_destination(case_id)
            Gio.Subprocess.new(["kage-inceleme", "--vaka", case_id], Gio.SubprocessFlags.NONE)
        except (OSError, ValueError, GLib.Error) as error:
            self.info.set_text(str(error))

    def show_reports(self, _control):
        try:
            _name, destination = report_destination(self.selection.get_active_id())
            Gtk.show_uri_on_window(self.get_toplevel(), destination.as_uri(), Gdk.CURRENT_TIME)
        except (OSError, ValueError, GLib.Error) as error:
            self.info.set_text(str(error))

    def open_timeline(self, _control=None):
        from zaman_ekrani import CaseTimeline

        if self.timeline is not None:
            self.timeline.present()
            return
        case_id = self.selection.get_active_id()
        if not case_id:
            self.info.set_text("Zaman çizelgesi için bir vaka oluştur veya seç.")
            return
        try:
            title = read_case(case_path(case_id))["name"]
        except (OSError, ValueError) as error:
            self.info.set_text(str(error))
            return
        self.timeline = CaseTimeline(self.get_toplevel(), case_id, title, self.run_job)
        self.timeline.connect("destroy", lambda _dialog: setattr(self, "timeline", None))
        self.timeline.present()

    def open_workspace(self, _control=None):
        case_id = self.selection.get_active_id()
        if not case_id:
            self.info.set_text("CTF alanını açmak için bir vaka oluştur veya seç.")
            return
        try:
            folder = case_path(case_id)
            values = read_workspace(case_id)
        except (OSError, ValueError) as error:
            self.info.set_text(str(error))
            return
        dialog = Gtk.Dialog(title="CTF çalışma alanı", transient_for=self.get_toplevel(), modal=True)
        dialog.set_default_size(620, 460)
        dialog.add_button("Vazgeç", Gtk.ResponseType.CANCEL)
        dialog.add_button("Kaydet", Gtk.ResponseType.OK)
        content = dialog.get_content_area()
        content.set_border_width(12)
        content.set_spacing(8)
        content.pack_start(label("Notlar"), False, False, 0)
        notes = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR)
        notes.get_buffer().set_text(values["notes"])
        notes_window = Gtk.ScrolledWindow()
        notes_window.set_min_content_height(130)
        notes_window.add(notes)
        content.pack_start(notes_window, True, True, 0)
        content.pack_start(label("Laboratuvar bağlantıları · her satıra bir adres"), False, False, 0)
        links = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR)
        links.get_buffer().set_text("\n".join(values["links"]))
        links_window = Gtk.ScrolledWindow()
        links_window.set_min_content_height(64)
        links_window.add(links)
        content.pack_start(links_window, False, False, 0)
        line = Gtk.Box(spacing=8)
        shell = Gtk.ComboBoxText()
        shell.get_accessible().set_name("Terminal profili")
        for name in CTF_PROFILES:
            shell.append(name, name)
        shell.set_active_id(values["shell"])
        status = label("")

        def text(view):
            buffer = view.get_buffer()
            return buffer.get_text(*buffer.get_bounds(), True)

        def open_link(_widget):
            try:
                buffer = links.get_buffer()
                it = buffer.get_iter_at_mark(buffer.get_insert())
                it.set_line_offset(0)
                end = it.copy()
                end.forward_to_line_end()
                url = lab_link(buffer.get_text(it, end, True))
                Gtk.show_uri_on_window(dialog, url, Gdk.CURRENT_TIME)
            except (ValueError, GLib.Error) as error:
                status.set_text(str(error))

        def terminal(_widget):
            try:
                Gio.Subprocess.new(["xfce4-terminal", "--disable-server", "--working-directory", str(folder),
                                    "--execute", CTF_PROFILES[shell.get_active_id()], "-li"], Gio.SubprocessFlags.NONE)
            except GLib.Error as error:
                status.set_text(error.message)

        for widget in (shell, button("Terminali aç", terminal), button("İmleçteki bağlantıyı aç", open_link)):
            line.pack_start(widget, False, False, 0)
        content.pack_start(line, False, False, 0)
        content.pack_start(status, False, False, 0)
        dialog.show_all()
        while dialog.run() == Gtk.ResponseType.OK:
            try:
                save_workspace(case_id, text(notes), text(links).splitlines(), shell.get_active_id())
            except (OSError, ValueError) as error:
                status.set_text(str(error))
            else:
                self.info.set_text("CTF çalışma alanı kaydedildi.")
                break
        dialog.destroy()
