#!/usr/bin/python3
"""Kage OS başlangıç, güncelleme ve tanılama merkezi."""

from pathlib import Path
import subprocess
import sys
import threading

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gdk, Gio, GLib, Gtk

from sistem import diagnostics, index_updated_at, package_index_state, read_package_snapshot, save_diagnostics, system_rows


ASSETS = Path(__file__).resolve().parent
STYLE = b"""
.kage-hero {
    background-image: linear-gradient(to right, #1d1319, #301b24);
    border: 1px solid #673344;
    border-radius: 14px;
    padding: 13px 19px;
}
.kage-hero label { color: #fff0d8; }
.kage-title { font-size: 20pt; font-weight: 700; }
.kage-section { font-size: 13pt; font-weight: 700; }
.kage-value { font-weight: 600; }
.kage-card {
    padding: 12px;
    border-radius: 10px;
    border: 1px solid alpha(@theme_fg_color, 0.20);
    background-color: alpha(@theme_fg_color, 0.04);
}
#kage-nav button { padding-left: 9px; padding-right: 9px; }
#kage-nav button:checked { border-bottom: 2px solid #c62b50; }
.kage-theme-sample { background-color: #30232b; color: #fff0d8; border: 1px solid #88475d; border-radius: 7px; padding: 12px; }
.kage-theme-sample.kage-sample-light { background-color: #fff1db; color: #34252b; }
#kage-daily-nav row:selected { background-color: #872544; color: #fff3e1; }
.kage-primary {
    background-image: none;
    background-color: #a11a3d;
    color: #fff6e4;
    border-color: #a11a3d;
    font-weight: 700;
}
.kage-primary:hover { background-color: #b82148; }
.kage-primary:disabled { opacity: 0.55; }
"""
MAINTENANCE_PAGES = {
    "--guvenlik-duvari": "firewall", "--medya-dogrulama": "media", "--gunlukler": "journal",
    "--donanim": "hardware",
}
DAILY_PAGES = {
    "--masaustu-duzenleri": "desktop", "--dosya-atolyesi": "workshop",
    "--telefon-paylasimi": "share", "--kitaplik": "library",
    "--dosya-kurtarma": "recovery", "--kage-gorunum": "appearance",
}
MANAGEMENT_PAGES = {
    "--guc": "power", "--gpu": "gpu", "--toolbox": "toolbox",
    "--kurtarma": "recovery", "--usb-kalicilik": "usb",
}
PAGES = {
    "--araclar": "tools", "--guncellemeler": "updates", "--tanilama": "diagnostics",
    "--paket-tanila": "welcome",
    "--vakalar": "cases", "--ctf": "cases", "--zaman-cizelgesi": "cases", "--gunluk": "daily", "--ilk-kurulum": "welcome",
    **dict.fromkeys(MAINTENANCE_PAGES, "maintenance"),
    **dict.fromkeys(DAILY_PAGES, "daily"),
    **dict.fromkeys(MANAGEMENT_PAGES, "management"),
}
TAB_TITLES = {
    "daily": "Günlük kullanım", "tools": "Araçlar", "updates": "Güncellemeler",
    "diagnostics": "Tanılama", "management": "Yönetim", "maintenance": "Sistem araçları", "cases": "Vakalar",
}


def label(text, style=None):
    result = Gtk.Label(label=text, xalign=0)
    result.set_line_wrap(True)
    if style:
        result.get_style_context().add_class(style)
    return result


def button(text, callback, primary=False):
    result = Gtk.Button.new_with_label(text)
    result.connect("clicked", callback)
    if primary:
        result.get_style_context().add_class("kage-primary")
    return result


def column(spacing=12):
    return Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=spacing)


def scroll(content):
    window = Gtk.ScrolledWindow()
    window.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    window.add(content)
    return window


def row_grid():
    result = Gtk.Grid(column_spacing=20, row_spacing=9)
    result.get_style_context().add_class("kage-card")
    return result


def fill_rows(grid, rows):
    for widget in grid.get_children():
        grid.remove(widget)
    for i, (key, value) in enumerate(rows):
        name = label(key)
        name.set_valign(Gtk.Align.START)
        data = label(value, "kage-value")
        data.set_hexpand(True)
        data.set_selectable(True)
        grid.attach(name, 0, i, 1, 1)
        grid.attach(data, 1, i, 1, 1)
    grid.show_all()


class KageCenter(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="org.kage.Center", flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        self.window = None
        self.first_run = Path(GLib.get_user_state_dir()) / "kage-os" / "ilk-acilis-0.7"
        self.wizard = None
        self.package_diagnostics = None
        self.summary = []
        self.services = []
        self.update_logs = ""
        self.update_failure = ""
        self.update_snapshot = None
        self.update_state = None
        self.updates_busy = False

    def do_command_line(self, command_line):
        args = command_line.get_arguments()[1:]
        if args == ["--ilk-acilis"] and self.first_run.is_file():
            return 0
        if args and args != ["--ilk-acilis"] and (len(args) != 1 or args[0] not in PAGES):
            return 2
        self.activate()
        if args == ["--ilk-acilis"]:
            self.open_wizard()
        elif args:
            self.navigate(args[0])
        return 0

    def navigate(self, page):
        if page == "--paket-tanila":
            self.open_package_diagnostics()
            return
        self.ensure_page(PAGES[page])
        if page in MAINTENANCE_PAGES:
            self.maintenance.stack.set_visible_child_name(MAINTENANCE_PAGES[page])
        if page in DAILY_PAGES:
            self.daily.stack.set_visible_child_name(DAILY_PAGES[page])
        if page in MANAGEMENT_PAGES:
            self.management.stack.set_visible_child_name(MANAGEMENT_PAGES[page])
        self.stack.set_visible_child_name(PAGES[page])
        if page == "--araclar":
            self.tools.search.grab_focus()
        elif page == "--ilk-kurulum":
            self.open_wizard()
        elif page == "--ctf":
            self.cases.open_workspace()
        elif page == "--zaman-cizelgesi":
            self.cases.open_timeline()

    def open_wizard(self):
        if self.wizard is None:
            from ilk_acilis import FirstRun

            self.wizard = FirstRun(self.window, self.run_job, self.finish_wizard)
            self.wizard.connect("destroy", lambda _wizard: setattr(self, "wizard", None))
        self.wizard.present()

    def finish_wizard(self, values, scheduled):
        try:
            self.first_run.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            self.first_run.touch(mode=0o600, exist_ok=True)
        except OSError:
            pass
        if values and values["groups"]:
            self.navigate("--toolbox")
            self.management.select_groups(values["groups"])
        elif values and values["driver"] == "nvidia":
            self.navigate("--gpu")
        if values and not scheduled:
            GLib.idle_add(self.notice, "Görünüm tercihi kaydedildi", "Otomatik saat geçişi bu oturumda başlatılamadı.")

    def do_activate(self):
        if self.window:
            self.window.present()
            return

        provider = Gtk.CssProvider()
        provider.load_from_data(STYLE)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
        self.window = Gtk.ApplicationWindow(application=self, title="Kage Merkez")
        self.window.set_icon_name("kage")
        self.window.set_default_size(782, 545)
        self.window.connect("destroy", self.destroy_window)
        self.updates_busy = False
        self.daily = self.maintenance = self.cases = None
        layout = column()
        layout.set_border_width(16)
        self.window.add(layout)
        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        self.stack.add_titled(self.welcome_page(), "welcome", "Başlangıç")
        self.tab_contents = {}
        for name, title in TAB_TITLES.items():
            container = column(0)
            self.stack.add_titled(container, name, title)
            self.tab_contents[name] = container
        self.stack.connect("notify::visible-child-name", self.page_changed)
        layout.pack_start(self.navigation(), False, False, 0)
        layout.pack_start(self.stack, True, True, 0)
        self.window.show_all()
        self.run_job(system_rows, self.show_overview)

    def ensure_page(self, name):
        container = self.tab_contents.get(name)
        if container is None or container.get_children():
            return
        if name == "daily":
            from gunluk_ekrani import DailyWorkspace

            page = self.daily = DailyWorkspace(self.run_job, self.notice)
        elif name == "tools":
            from araclar import ToolCatalog

            page = self.tools = ToolCatalog(self.notice)
        elif name == "management":
            from yonetim_ekrani import Management

            page = self.management = Management(self.run_job, self.notice, self.navigate)
        elif name == "maintenance":
            from bakim_ekranlari import Maintenance

            page = self.maintenance = Maintenance(self.run_job)
        elif name == "cases":
            from vaka_ekrani import CaseWorkspace

            page = self.cases = CaseWorkspace(self.run_job)
        else:
            page = self.updates_page() if name == "updates" else self.diagnostics_page()
        container.pack_start(page, True, True, 0)
        page.show_all()
        if name == "diagnostics":
            self.refresh_system()

    def navigation(self):
        bar = Gtk.Box(halign=Gtk.Align.CENTER)
        bar.set_name("kage-nav")
        bar.get_style_context().add_class(Gtk.STYLE_CLASS_LINKED)
        group = None
        buttons = {}
        for page in self.stack.get_children():
            name = self.stack.child_get_property(page, "name")
            title = self.stack.child_get_property(page, "title")
            tab = Gtk.RadioButton.new_with_label_from_widget(group, title)
            tab.set_mode(False)
            tab.connect("toggled", self.select_page, name)
            group = tab
            buttons[name] = tab
            bar.pack_start(tab, False, False, 0)
        def follow_stack(stack, _property):
            if tab := buttons.get(stack.get_visible_child_name()):
                tab.set_active(True)

        self.stack.connect("notify::visible-child-name", follow_stack)
        return bar

    def select_page(self, tab, name):
        if tab.get_active():
            self.stack.set_visible_child_name(name)

    def destroy_window(self, _window):
        self.window = None
        if self.maintenance is not None:
            self.maintenance.cancel_media()
        if self.cases is not None:
            self.cases.cancel_hash()
        if self.daily is not None:
            self.daily.close()

    def page_changed(self, stack, _property):
        if self.window is None:
            return
        name = stack.get_visible_child_name()
        self.ensure_page(name)
        if name == "tools":
            if not self.tools.loaded:
                self.tools.reload()
            self.tools.search.grab_focus()
        elif name == "cases":
            self.cases.reload_cases()
        elif name == "management":
            self.management.refresh()
        elif name == "updates":
            self.read_updates()

    def run_job(self, task, complete):
        window = self.window

        def delivered(value, error):
            if self.window is window:
                complete(value, error)
            return GLib.SOURCE_REMOVE

        def run():
            try:
                value = task()
            except Exception as error:
                GLib.idle_add(delivered, None, str(error) or type(error).__name__)
            else:
                GLib.idle_add(delivered, value, "")

        threading.Thread(target=run, daemon=True).start()

    def launch_button(self, title, *command, primary=False):
        def launch(_button):
            try:
                Gio.Subprocess.new(list(command), Gio.SubprocessFlags.NONE)
            except GLib.Error:
                self.notice(f"{title} açılamadı.", "Uygulamanın kurulu olduğunu kontrol et.")

        return button(title, launch, primary)

    def notice(self, heading, details):
        dialog = Gtk.MessageDialog(
            transient_for=self.window, modal=True, message_type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.CLOSE, text=heading,
        )
        dialog.format_secondary_text(details)
        dialog.run()
        dialog.destroy()

    def welcome_page(self):
        page = column()
        hero = Gtk.Box(spacing=16)
        hero.get_style_context().add_class("kage-hero")
        logo = Gtk.Image.new_from_icon_name("kage", Gtk.IconSize.DIALOG)
        logo.set_pixel_size(123)
        hero.pack_start(logo, False, False, 0)
        intro = column(6)
        intro.set_valign(Gtk.Align.CENTER)
        intro.pack_start(label("Kage OS’a hoş geldin", "kage-title"), False, False, 0)
        intro.pack_start(label("Günlük işlerini yap, sistemini düzenle veya yerel incelemeye başla."), False, False, 0)
        quick = Gtk.Box(spacing=8)
        quick.pack_start(button("Günlük kullanım", lambda _control: self.stack.set_visible_child_name("daily"), True), False, False, 0)
        quick.pack_start(self.launch_button("Kage İnceleme", "kage-inceleme"), False, False, 0)
        intro.pack_start(quick, False, False, 0)
        hero.pack_start(intro, True, True, 0)
        page.pack_start(hero, False, False, 0)
        shortcuts = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, homogeneous=True, column_spacing=6,
                                row_spacing=3, min_children_per_line=2, max_children_per_line=4)
        for title, route in (
            ("Görünüm", "--kage-gorunum"), ("Güncellemeler", "--guncellemeler"),
            ("Güç", "--guc"), ("GPU ve sürücüler", "--gpu"),
            ("Araç paketleri", "--toolbox"), ("Kurtarma noktaları", "--kurtarma"),
            ("USB kalıcılığı", "--usb-kalicilik"), ("İlk açılış sihirbazı", "--ilk-kurulum"),
        ):
            shortcuts.add(button(title, lambda _control, action=route: self.navigate(action)))
        page.pack_start(shortcuts, False, False, 0)
        page.pack_start(label("Sistem bilgileri", "kage-section"), False, False, 0)
        self.system_grid = row_grid()
        self.system_grid.add(label("Sistem okunuyor…"))
        page.pack_start(self.system_grid, False, False, 0)
        actions = Gtk.FlowBox()
        actions.set_selection_mode(Gtk.SelectionMode.NONE)
        actions.set_max_children_per_line(4)
        actions.set_column_spacing(8)
        for title, command in (
            ("Sistem ayarları", ("xfce4-settings-manager",)),
            ("Ağ bağlantıları", ("nm-connection-editor",)),
            ("Çevrimdışı kılavuz", ("xdg-open", str(ASSETS / "Kage-Kullanim.txt"))),
        ):
            actions.add(self.launch_button(title, *command))
        page.pack_start(actions, False, False, 0)
        return scroll(page)

    def updates_page(self):
        page = column()
        page.pack_start(label("Paket güncellemeleri", "kage-section"), False, False, 0)
        self.package_status = label("Yerel APT listesi okunuyor…")
        page.pack_start(self.package_status, False, False, 0)
        toolbar = Gtk.Box(spacing=8)
        self.refresh_button = button("Debian depolarını yenile", self.refresh_index, True)
        toolbar.pack_start(self.refresh_button, False, False, 0)
        toolbar.pack_start(self.launch_button("Synaptic’i aç", "synaptic-pkexec"), False, False, 0)
        self.package_filter = Gtk.ComboBoxText()
        self.package_filter.append("all", "Tüm güncellemeler")
        self.package_filter.append("security", "Güvenlik güncellemeleri")
        self.package_filter.set_active_id("all")
        self.package_filter.connect("changed", lambda _field: self.read_updates())
        toolbar.pack_start(self.package_filter, False, False, 0)
        self.logs_button = button("APT ayrıntıları", self.show_logs)
        self.logs_button.set_sensitive(False)
        toolbar.pack_end(self.logs_button, False, False, 0)
        page.pack_start(toolbar, False, False, 0)
        self.upgrade_button = button("Paketleri yükselt", self.upgrade_packages)
        self.upgrade_button.set_halign(Gtk.Align.START)
        self.upgrade_button.set_sensitive(False)
        package_actions = Gtk.Box(spacing=8)
        package_actions.pack_start(self.upgrade_button, False, False, 0)
        package_actions.pack_start(button("Paket sorun giderme", lambda _control: self.open_package_diagnostics()), False, False, 0)
        page.pack_start(package_actions, False, False, 0)
        self.packages = Gtk.ListStore(str, str, str)
        table = Gtk.TreeView(model=self.packages)
        for i, title in enumerate(("Paket", "Kurulu sürüm", "Yeni sürüm")):
            entry = Gtk.TreeViewColumn(title, Gtk.CellRendererText(), text=i)
            entry.set_expand(True)
            entry.set_resizable(True)
            entry.set_sort_column_id(i)
            table.append_column(entry)
        listing = Gtk.ScrolledWindow()
        listing.set_shadow_type(Gtk.ShadowType.IN)
        listing.add(table)
        page.pack_start(listing, True, True, 0)
        return page

    def read_updates(self, status_prefix=""):
        if self.updates_busy:
            return
        state = package_index_state()
        if self.update_snapshot is not None and state == self.update_state:
            self.show_package_rows(self.update_snapshot, "", status_prefix)
            return
        self.updates_busy = True
        self.refresh_button.set_sensitive(False)
        self.package_filter.set_sensitive(False)
        self.upgrade_button.set_sensitive(False)
        self.package_status.set_text("Yerel APT listesi okunuyor…")

        def show(snapshot, error):
            self.updates_busy = False
            self.update_snapshot = snapshot
            self.update_state = state
            self.show_package_rows(snapshot, error, status_prefix)

        self.run_job(read_package_snapshot, show)

    def show_package_rows(self, snapshot, error, status_prefix):
        security_only = self.package_filter.get_active_id() == "security"
        packages = snapshot[int(security_only)] if snapshot is not None else None
        self.refresh_button.set_sensitive(True)
        self.package_filter.set_sensitive(True)
        self.packages.clear()
        self.upgrade_button.set_sensitive(bool(packages and not security_only))
        if error:
            status = "Paket listesi okunamadı."
            self.update_logs += "\n" + error
            self.update_failure = error
            self.logs_button.set_sensitive(True)
        elif packages is None:
            index = "Debian güvenlik listesi" if security_only else "APT listesi"
            status = f"{index} hazır değil. Debian depolarını yenile."
        else:
            for package in packages:
                self.packages.append(package)
            if security_only:
                status = f"Debian güvenlik güncellemesi olan {len(packages)} paket."
            else:
                status = f"Yeni sürümü olan {len(packages)} paket var." if packages else "Yerel listede yeni paket sürümü yok."
            stamp = index_updated_at()
            if stamp:
                status += f" Son yenileme {stamp}."
        self.package_status.set_text(" ".join(filter(None, (status_prefix, status))))

    def refresh_index(self, _button):
        if self.updates_busy:
            return
        self.updates_busy = True
        self.refresh_button.set_sensitive(False)
        self.package_filter.set_sensitive(False)
        self.logs_button.set_sensitive(False)
        self.upgrade_button.set_sensitive(False)
        self.package_status.set_text("Debian paket listeleri yenileniyor…")

        def refresh():
            return subprocess.run(
                ["sudo", "-n", "--", "/usr/local/bin/kage-paket-yenile"],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace",
            )

        def done(result, error):
            self.updates_busy = False
            self.update_snapshot = None
            self.update_logs = error or result.stdout
            self.update_failure = self.update_logs if error or result.returncode else ""
            self.logs_button.set_sensitive(bool(self.update_logs.strip()))
            status = "Debian depoları yenilendi." if result and result.returncode == 0 else "Yenileme başarısız. APT ayrıntılarını aç."
            self.read_updates(status)

        self.run_job(refresh, done)

    def upgrade_packages(self, _button):
        from kurtarma import create_user_point
        from yonetim_ekrani import privileged

        self.ensure_page("management")
        detail = "APT, paket silmeden yükseltir. Kişisel ayarlar ve desteklenen Btrfs kökü için kurtarma noktası oluşturulur."
        if self.updates_busy or self.management.active_job or not self.management.confirm("Paketleri yükselt", detail):
            return
        self.updates_busy = True
        self.management.active_job = True
        for control in (self.refresh_button, self.package_filter, self.logs_button, self.upgrade_button):
            control.set_sensitive(False)
        self.package_status.set_text("Paketler yükseltiliyor…")

        def work():
            create_user_point("APT yükseltme öncesi")
            return privileged("upgrade")

        def done(result, error):
            self.updates_busy = False
            self.update_snapshot = None
            self.management.active_job = False
            self.update_logs = error or result or ""
            self.update_failure = error or ""
            self.logs_button.set_sensitive(bool(self.update_logs.strip()))
            self.read_updates("Yükseltme ayrıntıları APT kaydında." if error else "Paketler yükseltildi.")

        self.run_job(work, done)

    def open_package_diagnostics(self):
        from paket_tanila_ekrani import PackageDiagnostics

        if self.package_diagnostics is not None:
            self.package_diagnostics.present()
            return
        dialog = PackageDiagnostics(self.window, self.run_job, self.update_failure)
        self.package_diagnostics = dialog
        dialog.connect("destroy", lambda _dialog: setattr(self, "package_diagnostics", None))
        dialog.present()
        dialog.scan(False)

    def show_logs(self, _button):
        dialog = Gtk.Dialog(title="APT ayrıntıları", transient_for=self.window, modal=True)
        dialog.add_button("Kapat", Gtk.ResponseType.CLOSE)
        dialog.set_default_size(600, 330)
        view = Gtk.TextView(editable=False, monospace=True, cursor_visible=False, wrap_mode=Gtk.WrapMode.WORD_CHAR)
        view.get_buffer().set_text(self.update_logs.strip())
        dialog.get_content_area().pack_start(scroll(view), True, True, 6)
        dialog.show_all()
        dialog.run()
        dialog.destroy()

    def diagnostics_page(self):
        page = column()
        page.pack_start(label("Yerel sistem tanılaması", "kage-section"), False, False, 0)
        page.pack_start(label("Rapor sistem bilgilerini ve hizmet durumlarını içerir. IP adresleri, ağ adları ve aygıt kimlikleri rapora yazılmaz."), False, False, 0)
        self.services_grid = row_grid()
        self.services_grid.add(label("Hizmetler okunuyor…"))
        page.pack_start(self.services_grid, False, False, 0)
        toolbar = Gtk.Box(spacing=8)
        self.system_button = button("Bilgileri yenile", lambda _button: self.refresh_system())
        self.export_button = button("Raporu kaydet", self.export_report, True)
        toolbar.pack_start(self.export_button, False, False, 0)
        toolbar.pack_start(self.system_button, False, False, 0)
        page.pack_start(toolbar, False, False, 0)
        return scroll(page)

    def show_overview(self, rows, error):
        fill_rows(self.system_grid, rows if not error else [("Sistem", "Sistem bilgileri okunamadı.")])

    def refresh_system(self):
        self.system_button.set_sensitive(False)
        self.export_button.set_sensitive(False)

        def display(result, error):
            self.system_button.set_sensitive(True)
            if error:
                fill_rows(self.services_grid, [("Tanılama", "Sistem bilgileri okunamadı.")])
                return
            self.summary, self.services = result
            fill_rows(self.system_grid, self.summary)
            fill_rows(self.services_grid, self.services)
            self.export_button.set_sensitive(True)

        self.run_job(lambda: (system_rows(), diagnostics()), display)

    def export_report(self, _button):
        picker = Gtk.FileChooserNative.new(
            "Tanılama raporunu kaydet", self.window, Gtk.FileChooserAction.SAVE, "Kaydet", "Vazgeç"
        )
        picker.set_current_name("kage-tanilama.txt")
        picker.set_do_overwrite_confirmation(True)
        response = picker.run()
        path = picker.get_filename()
        picker.destroy()
        if response != Gtk.ResponseType.ACCEPT or path is None:
            return
        try:
            save_diagnostics(path, [*self.summary, *self.services])
        except OSError as error:
            self.notice("Rapor kaydedilemedi.", error.strerror or str(error))
        else:
            self.notice("Tanılama raporu kaydedildi.", path)


if __name__ == "__main__":
    raise SystemExit(KageCenter().run(sys.argv))
