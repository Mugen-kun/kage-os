"""GTK view for package and Debian connection diagnostics."""

from gi.repository import Gtk, Pango

from bakim_ekranlari import button, label, table
from paket_tanila import BLOCKED, CHECK, diagnose


class PackageDiagnostics(Gtk.Dialog):
    def __init__(self, parent, run_job, previous_error="", initial_package=""):
        super().__init__(title="Paket sorun giderme", transient_for=parent, modal=True, destroy_with_parent=True)
        self.set_default_size(680, 455)
        self.run_job = run_job
        self.previous_error = previous_error
        self.closed = False
        self.add_button("Kapat", Gtk.ResponseType.CLOSE)
        self.connect("response", lambda dialog, _response: dialog.destroy())
        self.connect("destroy", lambda _dialog: setattr(self, "closed", True))

        page = self.get_content_area()
        page.set_border_width(14)
        page.set_spacing(8)
        self.package = Gtk.Entry(placeholder_text="Paket adı (ör. tree)", max_length=140, activates_default=False)
        self.package.get_accessible().set_name("Tanılanacak Debian paketi")
        self.package.set_text(initial_package)
        self.package.connect("activate", lambda _entry: self.scan(False))
        page.pack_start(self.package, False, False, 0)
        actions = Gtk.Box(spacing=8)
        self.local_button = button("Yerel denetim", lambda _control: self.scan(False), True)
        self.online_button = button("Debian bağlantısını sına", lambda _control: self.scan(True))
        actions.pack_start(self.local_button, False, False, 0)
        actions.pack_start(self.online_button, False, False, 0)
        page.pack_start(actions, False, False, 0)
        self.status = label("Paket adını girersen APT kurulum önizlemesini görürsün.")
        self.status.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
        page.pack_start(self.status, False, False, 0)
        self.rows = Gtk.ListStore(str, str, str)
        scrolled, tree = table(self.rows, ("Denetim", "Durum", "Ayrıntı"))
        self.tree = tree
        tree.get_selection().connect("changed", self.show_detail)
        page.pack_start(scrolled, True, True, 0)
        self.detail = label("", selectable=True)
        self.detail.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
        page.pack_start(self.detail, False, False, 0)
        self.show_all()

    def show_detail(self, selection):
        model, item = selection.get_selected()
        self.detail.set_text(model[item][2] if item else "")

    def scan(self, online):
        if not self.local_button.get_sensitive():
            return
        package = self.package.get_text()
        for control in (self.package, self.local_button, self.online_button):
            control.set_sensitive(False)
        self.status.set_text("Denetleniyor…")

        def done(findings, error):
            if self.closed:
                return
            for control in (self.package, self.local_button, self.online_button):
                control.set_sensitive(True)
            self.rows.clear()
            self.detail.set_text("")
            if error:
                self.status.set_text(error)
                return
            for item in findings:
                self.rows.append((item.name, item.state, item.detail))
            issues = sum(item.state in {BLOCKED, CHECK} for item in findings)
            self.status.set_text(f"{len(findings)} denetim tamamlandı. {issues} sonuç dikkat gerektiriyor.")
            first = next((i for i, item in enumerate(findings) if item.state == BLOCKED), 0)
            if findings:
                self.tree.get_selection().select_path(Gtk.TreePath.new_from_indices([first]))

        self.run_job(lambda: diagnose(package, online=online, previous_error=self.previous_error), done)
