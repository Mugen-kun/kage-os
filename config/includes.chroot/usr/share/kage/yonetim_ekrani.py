"""Kage Merkez management screens and explicit administrative actions."""

import os
import subprocess

from gi.repository import Gio, GLib, Gtk, Pango

from aygitlar import POWER, desktop_arguments, gpu_variables, graphics_devices, live_session, power_status, set_power
from bakim_ekranlari import button, column, label
from kalicilik import persistence_status, usb_partitions
from kurtarma import create_user_point, restore_user_point, user_points
from paket_profili import missing_groups, read_profile, save_profile
from sistem import boot_mode
from sistem_kurtarma import active_device
from tercihler import read_preferences
from toolbox import GROUPS, installed_packages


def privileged(*action, secret=None):
    result = subprocess.run(
        ["pkexec", "--disable-internal-agent", "/usr/local/lib/kage/system-action", *action],
        input=secret or b"", stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    output = result.stdout.decode("utf-8", errors="replace")
    if result.returncode:
        raise ValueError(output.strip()[-2600:] or "Yönetici işlemi tamamlanamadı.")
    return output


def choice_box(title):
    chooser = Gtk.ComboBoxText()
    chooser.get_accessible().set_name(title)
    for cell in chooser.get_cells():
        cell.set_property("ellipsize", Pango.EllipsizeMode.END)
    return chooser


def headline(text):
    title = label(text)
    title.get_style_context().add_class("kage-section")
    return title


def actions(*controls):
    row = Gtk.Box(spacing=8)
    for control in controls:
        row.pack_start(control, False, False, 0)
    return row


class Management(Gtk.Box):
    def __init__(self, run_job, notice, navigate):
        super().__init__(spacing=14)
        self.run_job = run_job
        self.notice = notice
        self.navigate = navigate
        self.active_job = False
        self.loaded = set()
        self.gpus = {}
        self.apps = []
        self.partitions = {}
        self.group_installed = None
        self.stack = Gtk.Stack(hhomogeneous=False, vhomogeneous=False)
        for identifier, title, page in (
            ("power", "Güç", self.power_page()),
            ("gpu", "GPU ve sürücüler", self.gpu_page()),
            ("toolbox", "Araç paketleri", self.toolbox_page()),
            ("recovery", "Kurtarma noktaları", self.recovery_page()),
            ("usb", "USB kalıcılığı", self.usb_page()),
        ):
            scroll = Gtk.ScrolledWindow()
            scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
            page.set_margin_end(10)
            page.set_margin_bottom(6)
            scroll.add(page)
            self.stack.add_titled(scroll, identifier, title)
        sidebar = Gtk.StackSidebar(stack=self.stack)
        sidebar.set_name("kage-daily-nav")
        sidebar.get_accessible().set_name("Yönetim bölümleri")
        self.pack_start(sidebar, False, False, 0)
        self.pack_start(self.stack, True, True, 0)
        self.stack.connect("notify::visible-child-name", lambda *_: self.refresh())
        try:
            groups = read_profile()
        except (OSError, ValueError) as error:
            groups = None
            self.group_info.set_text(str(error))
        self.select_groups(groups if groups is not None else read_preferences()["groups"])

    def refresh(self, *, force=False):
        selected = self.stack.get_visible_child_name()
        loaders = {"power": self.read_power, "gpu": self.read_gpus, "toolbox": self.read_groups,
                   "recovery": self.read_points, "usb": self.read_usb}
        if selected in loaders and (force or selected not in self.loaded):
            self.loaded.add(selected)
            loaders[selected]()

    def confirm(self, title, detail):
        dialog = Gtk.MessageDialog(transient_for=self.get_toplevel(), modal=True, message_type=Gtk.MessageType.QUESTION,
                                   buttons=Gtk.ButtonsType.OK_CANCEL, text=title)
        dialog.format_secondary_text(detail)
        try:
            return dialog.run() == Gtk.ResponseType.OK
        finally:
            dialog.destroy()

    def admin_job(self, status, controls, work, finish, initial="İşlem sürüyor…"):
        if self.active_job:
            status.set_text("Başka bir yönetim işlemi sürüyor.")
            return
        self.active_job = True
        for control in controls:
            control.set_sensitive(False)
        status.set_text(initial)

        def done(result, error):
            self.active_job = False
            for control in controls:
                control.set_sensitive(True)
            if error:
                status.set_text(error)
            else:
                finish(result)

        self.run_job(work, done)

    def power_page(self):
        page = column()
        page.pack_start(headline("Güç profili"), False, False, 0)
        self.power_choice = choice_box("Güç profili")
        page.pack_start(self.power_choice, False, False, 0)
        self.power_apply = button("Uygula", self.apply_power, True)
        self.power_apply.set_sensitive(False)
        page.pack_start(actions(
            self.power_apply,
            button("Yenile", lambda _control: self.read_power()),
            button("Xfce güç ayarları", lambda _control: self.launch(["xfce4-power-manager-settings"])),
        ), False, False, 0)
        self.power_info = label("")
        page.pack_start(self.power_info, False, False, 0)
        return page

    def read_power(self):
        self.power_apply.set_sensitive(False)
        self.power_info.set_text("Desteklenen güç profilleri okunuyor…")

        def done(value, error):
            self.power_choice.remove_all()
            profiles, current = value or ([], "")
            for name in profiles:
                self.power_choice.append(name, POWER[name])
            if current in profiles:
                self.power_choice.set_active_id(current)
            else:
                self.power_choice.set_active(0 if profiles else -1)
            self.power_info.set_text(error or (f"Etkin profil {POWER[current]}." if current in POWER else
                                               "Güç profili hizmeti veya donanım desteği bulunamadı."))
            self.power_apply.set_sensitive(bool(profiles) and not self.active_job)

        self.run_job(power_status, done)

    def apply_power(self, _widget):
        profile = self.power_choice.get_active_id()
        if profile not in POWER:
            return

        def work():
            create_user_point("Güç profili değişikliği öncesi")
            set_power(profile, authorize=lambda choice: privileged("power", choice))

        self.admin_job(self.power_info, [self.power_apply], work, lambda _: self.read_power())

    def gpu_page(self):
        page = column()
        page.pack_start(headline("GPU ve sürücüler"), False, False, 0)
        self.gpu_hardware = label("")
        page.pack_start(self.gpu_hardware, False, False, 0)
        self.gpu_choice = choice_box("Uygulamanın kullanacağı GPU")
        self.gpu_choice.connect("changed", lambda _field: self.gpu_controls())
        page.pack_start(self.gpu_choice, False, False, 0)
        self.app_choice = choice_box("GPU ile açılacak uygulama")
        self.app_choice.connect("changed", lambda _field: self.gpu_controls())
        page.pack_start(self.app_choice, False, False, 0)
        self.gpu_launch = button("Uygulamayı aç", self.open_gpu_app, True)
        self.gpu_test = button("OpenGL’i dene", self.test_gpu)
        page.pack_start(actions(self.gpu_launch, self.gpu_test,
                                button("Donanımı yenile", lambda _control: self.read_gpus())), False, False, 0)
        self.nvidia = button("NVIDIA sürücüsünü kur / güncelle", self.install_nvidia)
        self.nvidia.set_sensitive(False)
        page.pack_start(self.nvidia, False, False, 0)
        self.gpu_info = label("")
        self.gpu_info.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
        page.pack_start(self.gpu_info, False, False, 0)
        return page

    def read_gpus(self):
        self.gpu_info.set_text("Grafik aygıtları okunuyor…")

        def done(devices, error):
            self.gpus = {device.address: device for device in (devices or ()) if gpu_variables(device)}
            self.gpu_hardware.set_text("\n".join(f"{gpu.title} · {gpu.driver}" for gpu in (devices or ())) or "GPU kaydı yok.")
            self.gpu_choice.remove_all()
            self.gpu_choice.append("default", "Sistem varsayılanı")
            for device in self.gpus.values():
                self.gpu_choice.append(device.address, f"{device.title} ile aç")
            self.gpu_choice.set_active(0)
            self.app_choice.remove_all()
            self.apps = sorted(
                [app for app in Gio.AppInfo.get_all() if isinstance(app, Gio.DesktopAppInfo)
                 and app.should_show() and app.get_commandline() and not app.get_boolean("Terminal")
                 and app.get_id() != "kage-merkez.desktop"],
                key=lambda app: app.get_display_name().casefold(),
            )
            for i, app in enumerate(self.apps):
                self.app_choice.append(str(i), app.get_display_name())
            self.app_choice.set_active(0 if self.apps else -1)
            nvidia = any(device.vendor == "NVIDIA" for device in (devices or ()))
            active = nvidia and not live_session() and not self.active_job
            self.nvidia.set_sensitive(active)
            status = "Sürücü değişikliği için yeniden başlatma gerekir."
            if live_session() and nvidia:
                status = "Canlı oturumda yüklü sürücüyle uygulama açabilirsin. Sürücü kurulumu kalıcı sistemde yapılır."
            elif not nvidia:
                status = "NVIDIA donanımı bulunamadı."
            self.gpu_info.set_text(error or status)
            self.gpu_controls()

        self.run_job(graphics_devices, done)

    def gpu_controls(self):
        if hasattr(self, "gpu_launch"):
            self.gpu_launch.set_sensitive(self.app_choice.get_active() >= 0)
            self.gpu_test.set_sensitive(self.gpu_choice.get_active() >= 0)

    def gpu_environment(self):
        env = os.environ.copy()
        for name in ("DRI_PRIME", "__NV_PRIME_RENDER_OFFLOAD", "__GLX_VENDOR_LIBRARY_NAME", "__VK_LAYER_NV_optimus"):
            env.pop(name, None)
        device = self.gpus.get(self.gpu_choice.get_active_id())
        if device:
            env.update(gpu_variables(device))
        return env

    def open_gpu_app(self, _widget):
        selected = self.app_choice.get_active()
        if selected < 0:
            return
        app = self.apps[selected]
        try:
            arguments = desktop_arguments(app.get_commandline(), name=app.get_display_name(), desktop=app.get_filename() or "")
            subprocess.Popen(arguments, env=self.gpu_environment(), start_new_session=True)
            self.gpu_info.set_text("Uygulama başlatıldı. Bazı uygulamalarda açık tüm pencereleri kapatıp yeniden açmak gerekir.")
        except (OSError, ValueError) as error:
            self.gpu_info.set_text(str(error))

    def test_gpu(self, _widget):
        env = self.gpu_environment()

        def work():
            output = subprocess.check_output(["glxinfo", "-B"], env=env, text=True, stderr=subprocess.STDOUT, timeout=12)
            return next((line.split(":", 1)[1].strip() for line in output.splitlines()
                         if line.startswith("OpenGL renderer string:")), "OpenGL işleyicisi belirlenemedi.")

        self.admin_job(self.gpu_info, [self.gpu_test], work, self.gpu_info.set_text, "OpenGL işleyicisi sınanıyor…")

    def install_nvidia(self, _widget):
        detail = "Debian’ın imzalı NVIDIA deposu etkinleştirilir. Sürücü ve çalışan çekirdeğin başlıkları kurulur."
        if "Secure Boot açık" in boot_mode():
            detail += " Secure Boot için DKMS anahtarının kaydı yeniden başlatmada gerekebilir."
        if self.confirm("NVIDIA sürücüsünü kur", detail):
            self.admin_job(self.gpu_info, [self.nvidia], lambda: privileged("nvidia"),
                           lambda _output: self.gpu_info.set_text("NVIDIA paketi hazır. Sürücüyü yüklemek için sistemi yeniden başlat."))

    def toolbox_page(self):
        page = column()
        page.pack_start(headline("Kage Toolbox"), False, False, 0)
        self.group_checks, self.group_states = {}, {}
        for key, group in GROUPS.items():
            row = column(3)
            row.get_style_context().add_class("kage-card")
            check = Gtk.CheckButton(label=group.title)
            self.group_checks[key] = check
            row.pack_start(check, False, False, 0)
            row.pack_start(label(group.description), False, False, 0)
            self.group_states[key] = label(f"APT paketi {group.name}")
            row.pack_start(self.group_states[key], False, False, 0)
            page.pack_start(row, False, False, 0)
        self.group_install = button("Seçilileri kur", self.install_groups, True)
        self.group_restore = button("Seçilen eksikleri kur", lambda _control: self.install_groups(None, only_missing=True))
        self.group_restore.set_sensitive(False)
        page.pack_start(actions(self.group_install, self.group_restore,
                                button("Durumu yenile", lambda _control: self.read_groups())), False, False, 0)
        self.profile_controls = (
            button("Seçimi hatırla", self.remember_groups),
            button("Profili dışa aktar", self.export_profile),
            button("Profili içe al", self.import_profile),
        )
        page.pack_start(actions(*self.profile_controls), False, False, 0)
        page.pack_start(button("Paket sorun giderme", lambda _control: self.navigate("--paket-tanila")), False, False, 0)
        self.profile_info = label("")
        self.profile_info.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
        page.pack_start(self.profile_info, False, False, 0)
        self.group_info = label("")
        self.group_info.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
        page.pack_start(self.group_info, False, False, 0)
        for control in self.group_checks.values():
            control.connect("toggled", lambda _field: self.show_group_selection())
        return page

    def select_groups(self, groups):
        for key, check in self.group_checks.items():
            check.set_active(key in groups)
        self.show_group_selection()

    def selected_groups(self):
        return [key for key, field in self.group_checks.items() if field.get_active()]

    def show_group_selection(self):
        selected = self.selected_groups()
        missing = [] if self.group_installed is None else missing_groups(selected, self.group_installed)
        self.group_restore.set_sensitive(bool(missing) and not self.active_job)
        if not selected:
            self.profile_info.set_text("Profil için kategori seç.")
        elif self.group_installed is None:
            self.profile_info.set_text(f"{len(selected)} kategori seçili.")
        else:
            self.profile_info.set_text(f"{len(selected)} kategori seçili. {len(missing)} kategoride eksik paket var.")

    def read_groups(self):
        def done(installed, error):
            if error:
                self.group_info.set_text(error)
                self.group_installed = None
                self.show_group_selection()
                return
            self.group_installed = installed
            for key, group in GROUPS.items():
                missing = set(group.packages) - installed
                description = "Hazır" if not missing else f"{len(missing)} paket kurulabilir"
                self.group_states[key].set_text(f"{description} · {group.name}")
            self.show_group_selection()

        self.run_job(installed_packages, done)

    def install_groups(self, _widget, *, only_missing=False):
        if self.active_job:
            self.group_info.set_text("Başka bir yönetim işlemi sürüyor.")
            return
        chosen = self.selected_groups()
        if only_missing and self.group_installed is None:
            self.group_info.set_text("Kurulu paket bilgisi okunuyor. Biraz sonra tekrar dene.")
            return
        groups = missing_groups(chosen, self.group_installed) if only_missing else chosen
        if not groups:
            self.group_info.set_text("Seçilen kategoriler hazır." if chosen else "Kurmak istediğin kategorileri seç.")
            return
        if self.confirm("Araç paketlerini kur", ", ".join(GROUPS[key].title for key in groups)):
            def done(_output):
                try:
                    save_profile(chosen)
                except (OSError, ValueError) as error:
                    self.group_info.set_text(f"Paketler kuruldu. Profil kaydedilemedi. {error}")
                else:
                    self.group_info.set_text("Paketler kuruldu ve seçim paket profiline kaydedildi.")
                self.read_groups()
            controls = (self.group_install, self.group_restore, *self.group_checks.values(), *self.profile_controls)
            self.admin_job(self.group_info, controls, lambda: privileged("packages", *groups), done,
                           "APT paketleri kuruluyor…")

    def remember_groups(self, _widget):
        try:
            save_profile(self.selected_groups())
        except (OSError, ValueError) as error:
            self.group_info.set_text(str(error))
        else:
            self.group_info.set_text("Seçim ev dizinine kaydedildi ve sonraki oturumda gösterilecek.")

    def profile_path(self, save):
        action = Gtk.FileChooserAction.SAVE if save else Gtk.FileChooserAction.OPEN
        title = "Paket profilini dışa aktar" if save else "Paket profilini içe al"
        picker = Gtk.FileChooserNative.new(title, self.get_toplevel(), action, "Kaydet" if save else "Aç", "Vazgeç")
        profile_filter = Gtk.FileFilter()
        profile_filter.set_name("Kage paket profili (.json)")
        profile_filter.add_pattern("*.json")
        picker.add_filter(profile_filter)
        if save:
            picker.set_current_name("kage-paket-profili.json")
            picker.set_do_overwrite_confirmation(True)
        try:
            return picker.get_filename() if picker.run() == Gtk.ResponseType.ACCEPT else None
        finally:
            picker.destroy()

    def export_profile(self, _widget):
        if destination := self.profile_path(True):
            try:
                save_profile(self.selected_groups(), destination)
            except (OSError, ValueError) as error:
                self.group_info.set_text(str(error))
            else:
                self.group_info.set_text("Paket profili dışa aktarıldı.")

    def import_profile(self, _widget):
        if source := self.profile_path(False):
            try:
                groups = read_profile(source)
                save_profile(groups)
            except (OSError, ValueError) as error:
                self.group_info.set_text(str(error))
            else:
                self.select_groups(groups)
                self.group_info.set_text("Paket profili içe alındı. Kurmak istediğin kategorileri gözden geçir.")

    def recovery_page(self):
        page = column()
        page.pack_start(headline("Kurtarma noktaları"), False, False, 0)
        page.pack_start(label("Kişisel noktalar tema, klavye, Kage tercihleri ve güç profilini saklar."), False, False, 0)
        self.points = choice_box("Kişisel kurtarma noktası")
        page.pack_start(self.points, False, False, 0)
        self.user_point = button("Kişisel nokta oluştur", self.save_user_point, True)
        self.restore_point = button("Seçileni geri al", self.apply_user_point)
        self.restore_point.set_sensitive(False)
        page.pack_start(actions(self.user_point, self.restore_point), False, False, 0)
        page.pack_start(button("Dosya yedeklemeyi aç", lambda _control: self.navigate("--dosya-kurtarma")), False, False, 0)
        page.pack_start(headline("Kurulu sistem"), False, False, 0)
        self.system_point = button("Sistem noktası oluştur", self.save_system_point)
        self.system_point.set_sensitive(False)
        page.pack_start(self.system_point, False, False, 0)
        self.point_layout = label("")
        page.pack_start(self.point_layout, False, False, 0)
        self.point_info = label("")
        self.point_info.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
        page.pack_start(self.point_info, False, False, 0)
        return page

    def read_points(self):
        def done(data, error):
            if error:
                self.point_info.set_text(error)
                return
            records, device = data
            selected = self.points.get_active_id()
            self.points.remove_all()
            for key, reason in records:
                date = f"{key[:4]}-{key[4:6]}-{key[6:8]}  {key[9:11]}:{key[11:13]} UTC"
                self.points.append(key, f"{date} · {reason}")
            if not self.points.set_active_id(selected or ""):
                self.points.set_active(0 if records else -1)
            self.restore_point.set_sensitive(bool(records) and not self.active_job)
            self.system_point.set_sensitive(bool(device) and not self.active_job)
            self.point_layout.set_text("Btrfs sistem noktası bu kök bölümde kullanılabilir." if device else (
                "Sistem noktaları @ kök ve ayrı @home kullanan kurulu Btrfs sistemlerinde kullanılabilir."
            ))

        self.run_job(lambda: (user_points(), active_device()), done)

    def save_user_point(self, _widget):
        def done(_identifier):
            self.point_info.set_text("Kişisel kurtarma noktası kaydedildi.")
            self.read_points()
        self.admin_job(self.point_info, [self.user_point], lambda: create_user_point("Kişisel ayar noktası"), done)

    def apply_user_point(self, _widget):
        selected = self.points.get_active_id()
        if selected and self.confirm("Kişisel ayarları geri al", "Şimdiki ayarlar ayrıca bir kurtarma noktası olarak kaydedilir."):
            def done(_value):
                self.point_info.set_text("Kişisel ayarlar geri alındı. Dil bir sonraki oturum açılışında uygulanır.")
                self.read_points()
            self.admin_job(self.point_info, [self.restore_point],
                           lambda: restore_user_point(selected, authorize=lambda choice: privileged("power", choice)), done)

    def save_system_point(self, _widget):
        self.admin_job(self.point_info, [self.system_point], lambda: privileged("point"),
                       lambda identifier: self.point_info.set_text(f"Sistem noktası hazır · {identifier.strip()}"))

    def usb_page(self):
        page = column()
        page.pack_start(headline("Canlı USB kalıcılığı"), False, False, 0)
        self.usb_mode = label("")
        page.pack_start(self.usb_mode, False, False, 0)
        page.pack_start(label("Ev dizini için çıkarılabilir USB’deki boş bir bölümü seç. Hazırlama seçilen bölümü biçimlendirir."),
                        False, False, 0)
        self.usb_choice = choice_box("Boş USB bölümü")
        page.pack_start(self.usb_choice, False, False, 0)
        self.encrypt = Gtk.CheckButton(label="LUKS2 ile şifrele", active=True)
        self.encrypt.connect("toggled", lambda field: self.usb_secret.set_visible(field.get_active()))
        page.pack_start(self.encrypt, False, False, 0)
        self.usb_secret = column(5)
        self.passphrase = Gtk.Entry(visibility=False, placeholder_text="LUKS parolası", input_purpose=Gtk.InputPurpose.PASSWORD)
        self.repeated = Gtk.Entry(visibility=False, placeholder_text="Parolayı yeniden yaz", input_purpose=Gtk.InputPurpose.PASSWORD)
        self.usb_secret.pack_start(self.passphrase, False, False, 0)
        self.usb_secret.pack_start(self.repeated, False, False, 0)
        page.pack_start(self.usb_secret, False, False, 0)
        self.usb_prepare = button("Bölümü hazırla", self.prepare_usb, True)
        self.usb_prepare.set_sensitive(False)
        page.pack_start(actions(self.usb_prepare, button("USB listesini yenile", lambda _control: self.read_usb())),
                        False, False, 0)
        self.usb_info = label("")
        page.pack_start(self.usb_info, False, False, 0)
        return page

    def read_usb(self):
        def done(result, error):
            if error:
                self.usb_info.set_text(error)
                return
            mode, choices = result
            self.usb_mode.set_text(mode)
            self.partitions = {part.identity: part for part in choices}
            self.usb_choice.remove_all()
            for part in choices:
                self.usb_choice.append(part.identity, f"{part.path} · {part.model} · {GLib.format_size(part.size)}")
            self.usb_choice.set_active(0 if choices else -1)
            self.usb_prepare.set_sensitive(bool(choices) and not self.active_job)
            if not choices and not self.usb_info.get_text():
                self.usb_info.set_text("Hazırlanabilecek boş bir USB bölümü bulunamadı.")

        self.run_job(lambda: (persistence_status(), usb_partitions()), done)

    def prepare_usb(self, _widget):
        part = self.partitions.get(self.usb_choice.get_active_id())
        if not part:
            return
        encrypted = self.encrypt.get_active()
        secret = self.passphrase.get_text() if encrypted else ""
        if encrypted and (not secret or secret != self.repeated.get_text()):
            self.usb_info.set_text("LUKS parolası ve tekrarı eşleşmeli.")
            return
        if not self.confirm("USB bölümünü biçimlendir", f"{part.path} · {part.model} · {GLib.format_size(part.size)}"):
            return
        self.passphrase.set_text("")
        self.repeated.set_text("")
        key = secret.encode("utf-8") if encrypted else None

        def done(_output):
            entry = "Sifreli ev diziniyle baslat" if encrypted else "Kalici ev diziniyle baslat"
            self.usb_info.set_text(f"USB bölümü hazır. Bir sonraki açılışta {entry} seçeneğini kullan.")
            self.read_usb()

        self.admin_job(self.usb_info, [self.usb_prepare],
                       lambda: privileged("usb", part.path, part.identity, "luks" if encrypted else "plain", secret=key),
                       done, "USB bölümü hazırlanıyor…")

    def launch(self, command):
        try:
            Gio.Subprocess.new(command, Gio.SubprocessFlags.NONE)
        except GLib.Error as error:
            self.notice("Uygulama açılamadı", error.message)
