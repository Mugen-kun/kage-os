#!/usr/bin/python3
"""Kage'nin yerel ağ kaydı ve dosya inceleme arayüzü."""

from pathlib import Path
import sys
import threading

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, Gio, GLib, Gtk


from rapor import REPORT_NAMES, create_report, expected_sha256, regular_file
from vaka import report_destination


PAGES = {"ag": "network", "dijital": "forensics"}
STYLE = b"""
#kage-window { background-color: @theme_bg_color; color: @theme_fg_color; }
#kage-header label { color: @theme_fg_color; }
.kage-heading { font-size: 20pt; font-weight: bold; }
.kage-caption { color: alpha(@theme_fg_color, 0.85); }
.kage-card {
    background-color: alpha(@theme_fg_color, 0.04);
    border: 1px solid alpha(@theme_fg_color, 0.20);
    border-radius: 10px;
    padding: 12px;
}
.kage-title { font-size: 13pt; font-weight: bold; }
button.kage-action {
    background-image: none;
    background-color: #a11a3d;
    color: #fff6e4;
    border-color: #a11a3d;
    border-radius: 7px;
    font-weight: bold;
}
button.kage-action:hover { background-color: #b82148; }
button.kage-action:disabled { opacity: 0.55; }
#kage-tabs button:checked { border-bottom: 2px solid #c62b50; }
"""


def label(text, style=None):
    widget = Gtk.Label(label=text, xalign=0)
    widget.set_line_wrap(True)
    if style:
        widget.get_style_context().add_class(style)
    return widget


def file_chooser(title, patterns=()):
    chooser = Gtk.FileChooserButton(title=title, action=Gtk.FileChooserAction.OPEN)
    chooser.set_hexpand(True)
    if patterns:
        pattern_filter = Gtk.FileFilter()
        pattern_filter.set_name(title)
        for pattern in patterns:
            pattern_filter.add_pattern(pattern)
        chooser.add_filter(pattern_filter)
        all_filter = Gtk.FileFilter()
        all_filter.set_name("Tüm dosyalar")
        all_filter.add_pattern("*")
        chooser.add_filter(all_filter)
    return chooser


class KageAnalysis(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="org.kage.Analysis", flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        self.window = None
        self.report_folder = None
        self.cancel = None
        self.close_after_report = False

    def do_command_line(self, command_line):
        args = command_line.get_arguments()[1:]
        if len(args) == 2 and args[0] == "--vaka":
            self.activate()
            if self.cancel:
                self.status.set_text("Rapor konumunu değiştirmek için mevcut işlemin tamamlanmasını bekle.")
                return 1
            try:
                name, folder = report_destination(args[1])
                if not self.destination.set_filename(str(folder)):
                    raise ValueError("Vakanın rapor klasörü seçilemedi.")
            except (OSError, ValueError) as error:
                self.status.set_text(str(error))
                return 2
            self.status.set_text(f"Yeni raporlar {name} vakasına kaydedilecek.")
            return 0
        if len(args) > 1 or (args and args[0] not in PAGES):
            return 2
        self.activate()
        if args:
            self.stack.set_visible_child_name(PAGES[args[0]])
        return 0

    def do_activate(self):
        if self.window:
            self.window.present()
            return

        provider = Gtk.CssProvider()
        provider.load_from_data(STYLE)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        self.window = Gtk.ApplicationWindow(application=self, title="Kage İnceleme")
        self.window.set_default_size(730, 540)
        self.window.set_icon_name("system-search")
        self.window.set_name("kage-window")
        self.window.connect("delete-event", self.on_close)

        layout = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        layout.set_border_width(18)
        self.window.add(layout)

        header = Gtk.Box(spacing=12)
        header.set_name("kage-header")
        icon = Gtk.Image.new_from_icon_name("kage", Gtk.IconSize.DIALOG)
        icon.set_pixel_size(48)
        header.pack_start(icon, False, False, 0)
        headings = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        headings.pack_start(label("Kage İnceleme", "kage-heading"), False, False, 0)
        headings.pack_start(label("Ağ kayıtları ve dosyalar için yerel raporlar", "kage-caption"), False, False, 0)
        header.pack_start(headings, True, True, 0)
        layout.pack_start(header, False, False, 0)

        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        self.stack.add_titled(self.network_page(), "network", "Ağ analizi")
        self.stack.add_titled(self.forensics_page(), "forensics", "Dijital inceleme")
        tabs = Gtk.StackSwitcher(stack=self.stack)
        tabs.set_name("kage-tabs")
        layout.pack_start(tabs, False, False, 0)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.add(self.stack)
        self.input_area = scroll
        layout.pack_start(scroll, True, True, 0)

        output = Gtk.Box(spacing=10)
        output.pack_start(label("Rapor konumu"), False, False, 0)
        self.destination = Gtk.FileChooserButton(
            title="Raporların kaydedileceği klasörü seç", action=Gtk.FileChooserAction.SELECT_FOLDER
        )
        default_folder = Path.home() / "Kage-Raporlar"
        try:
            default_folder.mkdir(mode=0o700, exist_ok=True)
            self.destination.set_filename(str(default_folder))
        except OSError:
            self.destination.set_current_folder(str(Path.home()))
        output.pack_start(self.destination, True, True, 0)
        layout.pack_start(output, False, False, 0)

        footer = Gtk.Box(spacing=8)
        self.spinner = Gtk.Spinner()
        self.spinner.set_no_show_all(True)
        footer.pack_start(self.spinner, False, False, 0)
        self.status = label("İncelemek istediğin işlemi seç.", "kage-caption")
        self.status.set_name("kage-status")
        footer.pack_start(self.status, True, True, 0)
        self.stop_button = Gtk.Button(label="Durdur")
        self.stop_button.set_no_show_all(True)
        self.stop_button.connect("clicked", self.stop_report)
        footer.pack_end(self.stop_button, False, False, 0)
        self.open_folder = Gtk.Button(label="Klasörü aç")
        self.open_folder.set_sensitive(False)
        self.open_folder.connect("clicked", self.show_path, "report_folder")
        footer.pack_end(self.open_folder, False, False, 0)
        self.open_report = Gtk.Button(label="Raporu aç")
        self.open_report.set_sensitive(False)
        self.open_report.connect("clicked", self.show_path, "report_path")
        footer.pack_end(self.open_report, False, False, 0)
        layout.pack_start(footer, False, False, 0)
        layout.pack_start(
            label("Canlı oturumu kapatmadan önce raporlarını kalıcı bir konuma kopyala.", "kage-caption"),
            False, False, 0
        )
        self.window.show_all()

    def card(self, title, description):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=9)
        box.get_style_context().add_class("kage-card")
        box.pack_start(label(title, "kage-title"), False, False, 0)
        box.pack_start(label(description, "kage-caption"), False, False, 0)
        return box

    def action_button(self, text, action, source=None, rules=None, expected=None):
        button = Gtk.Button(label=text)
        button.get_style_context().add_class("kage-action")
        button.set_halign(Gtk.Align.START)
        button.connect("clicked", self.start_report, action, source, rules, expected)
        return button

    def network_page(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box = self.card("PCAP özeti", "Kaydedilmiş trafiğin protokollerini ve IP uç noktalarını raporla.")
        capture = file_chooser("PCAP veya PCAPNG dosyası seç", ("*.pcap", "*.pcapng", "*.cap", "*.PCAP", "*.PCAPNG"))
        box.pack_start(capture, False, False, 0)

        actions = Gtk.Box(spacing=8)
        actions.pack_start(self.action_button("Özet çıkar", "pcap", capture), False, False, 0)
        wireshark = Gtk.Button(label="Wireshark’ta aç")
        wireshark.connect("clicked", self.open_capture, capture)
        actions.pack_start(wireshark, False, False, 0)
        box.pack_start(actions, False, False, 0)
        page.pack_start(box, False, False, 0)

        local = self.card("Yerel ağ arayüzleri", "Bu bilgisayarın bağlantı durumunu ve IP adreslerini raporla.")
        local.pack_start(self.action_button("Arayüzleri listele", "interfaces"), False, False, 0)
        page.pack_start(local, False, False, 0)
        return page

    def forensics_page(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        tools = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        switcher = Gtk.StackSwitcher(stack=tools)
        page.pack_start(switcher, False, False, 0)
        page.pack_start(tools, True, True, 0)

        digest = self.card("Dosya bütünlüğü", "SHA-256 özetini hesapla veya bilinen bir değerle karşılaştır.")
        image = file_chooser("Disk imajı veya dosya seç")
        expected = Gtk.Entry()
        expected.set_placeholder_text("Beklenen SHA-256 (isteğe bağlı)")
        expected.get_accessible().set_name("Beklenen SHA-256")
        expected.set_input_purpose(Gtk.InputPurpose.FREE_FORM)
        digest.pack_start(image, False, False, 0)
        digest.pack_start(expected, False, False, 0)
        digest.pack_start(self.action_button("Özeti hesapla", "sha256", image, expected=expected), False, False, 0)
        tools.add_titled(digest, "sha256", "SHA-256")

        partitions = self.card("Disk imajı bölümleri", "Bir imajın bölüm tablosunu Sleuth Kit ile oku.")
        disk = file_chooser("Disk imajı seç")
        partitions.pack_start(disk, False, False, 0)
        partitions.pack_start(self.action_button("Bölüm tablosunu çıkar", "partitions", disk), False, False, 0)
        tools.add_titled(partitions, "partitions", "Bölümler")

        scan = self.card("YARA dosya taraması", "Seçtiğin kural dosyasını tek bir dosyaya uygula.")
        rules = file_chooser("YARA kural dosyası seç", ("*.yar", "*.yara"))
        target = file_chooser("Taranacak dosyayı seç")
        scan.pack_start(rules, False, False, 0)
        scan.pack_start(target, False, False, 0)
        scan.pack_start(self.action_button("Dosyayı tara", "yara", target, rules), False, False, 0)
        tools.add_titled(scan, "yara", "YARA")

        metadata = self.card("Dosya meta verisi", "ExifTool ile dosyadaki tür, tarih ve diğer meta verileri oku.")
        file = file_chooser("Meta verisi okunacak dosyayı seç")
        metadata.pack_start(file, False, False, 0)
        metadata.pack_start(self.action_button("Meta veriyi çıkar", "metadata", file), False, False, 0)
        tools.add_titled(metadata, "metadata", "Meta veri")
        return page

    def open_capture(self, _button, capture):
        try:
            path = regular_file(capture.get_filename(), "PCAP dosyasını")
            Gio.Subprocess.new(["wireshark", "-n", "-r", str(path)], Gio.SubprocessFlags.NONE)
        except (OSError, ValueError, GLib.Error) as error:
            self.status.set_text(str(error))

    def start_report(self, _button, action, source, rules, expected):
        filename = source.get_filename() if source else None
        rules_filename = rules.get_filename() if rules else None
        if (source and not filename) or (rules and not rules_filename):
            self.status.set_text("Önce gerekli dosyaları seç.")
            return
        try:
            checksum = expected_sha256(expected.get_text()) if expected else None
        except ValueError as error:
            self.status.set_text(str(error))
            return

        destination = self.destination.get_filename()
        folder = Path(destination) if destination else Path.home() / "Kage-Raporlar"
        cancel = threading.Event()
        self.cancel = cancel
        self.input_area.set_sensitive(False)
        self.destination.set_sensitive(False)
        self.open_folder.set_sensitive(False)
        self.open_report.set_sensitive(False)
        self.spinner.show()
        self.spinner.start()
        self.stop_button.set_sensitive(True)
        self.stop_button.show()
        self.status.set_text("İnceleme sürüyor…")

        def run():
            try:
                report, message = create_report(action, filename, rules_filename, folder, expected=checksum, cancel=cancel)
            except (OSError, ValueError) as error:
                report, message = None, str(error)
            GLib.idle_add(self.finish_report, action, report, message)

        threading.Thread(target=run, daemon=True).start()

    def stop_report(self, _button=None):
        if self.cancel:
            self.cancel.set()
            self.stop_button.set_sensitive(False)
            self.status.set_text("İşlem durduruluyor…")

    def finish_report(self, action, folder, message):
        self.cancel = None
        if self.close_after_report:
            self.window.destroy()
            return

        self.input_area.set_sensitive(True)
        self.destination.set_sensitive(True)
        self.spinner.stop()
        self.spinner.hide()
        self.stop_button.hide()
        self.report_folder = folder
        report = folder / REPORT_NAMES[action] if folder else None
        self.report_path = report if report and report.is_file() else None
        self.open_folder.set_sensitive(folder is not None)
        self.open_report.set_sensitive(self.report_path is not None)
        self.status.set_text(message)

    def show_path(self, _button, attribute):
        path = getattr(self, attribute)
        try:
            Gtk.show_uri_on_window(self.window, path.as_uri(), Gdk.CURRENT_TIME)
        except GLib.Error as error:
            self.status.set_text(str(error))

    def on_close(self, _window, _event):
        if not self.cancel:
            return False
        self.close_after_report = True
        self.stop_report()
        return True


if __name__ == "__main__":
    raise SystemExit(KageAnalysis().run(sys.argv))
