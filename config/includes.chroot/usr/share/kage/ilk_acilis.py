"""The skippable first-run assistant for user-owned Kage preferences."""

import subprocess

from gi.repository import Gtk

from bakim_ekranlari import button, column, label
from kurtarma import create_user_point
from masaustu import saved_theme
from tercihler import (DRIVER_CHOICES, KEYBOARDS, LANGUAGES, THEME_CHOICES, apply_preferences, keyboard_status,
                      read_preferences, set_keyboard, xkb_apply)
from toolbox import GROUPS


class FirstRun(Gtk.Dialog):
    def __init__(self, parent, run_job, complete):
        super().__init__(title="Kage ilk açılış", transient_for=parent, modal=True, destroy_with_parent=True)
        self.set_default_size(575, 405)
        self.run_job = run_job
        self.complete = complete
        self.original_keyboard = None
        self.busy = False
        self.index = 0
        self.choices = read_preferences()
        if saved_theme() in THEME_CHOICES:
            self.choices["theme"] = saved_theme()
        self.skip = self.add_button("Daha sonra", Gtk.ResponseType.CANCEL)
        self.previous = self.add_button("Geri", Gtk.ResponseType.REJECT)
        self.next = self.add_button("İleri", Gtk.ResponseType.APPLY)
        self.next.get_style_context().add_class("kage-primary")
        self.stack = Gtk.Stack(vhomogeneous=True)
        box = self.get_content_area()
        box.set_border_width(14)
        box.set_spacing(10)
        self.stack.add_named(self.language_page(), "0")
        self.stack.add_named(self.appearance_page(), "1")
        self.stack.add_named(self.review_page(), "2")
        box.pack_start(self.stack, True, True, 0)
        self.status = label("")
        box.pack_start(self.status, False, False, 0)
        self.connect("response", self.respond)
        self.connect("delete-event", self.delete)
        self.connect("destroy", lambda _dialog: self.restore_keyboard())
        self.sync()
        self.show_all()

    def dropdown(self, options, key):
        chooser = Gtk.ComboBoxText()
        for identifier, title in options.items():
            chooser.append(identifier, title)
        chooser.set_active_id(self.choices[key])
        return chooser

    def language_page(self):
        page = column()
        title = label("Dil ve klavye")
        title.get_style_context().add_class("kage-section")
        page.pack_start(title, False, False, 0)
        page.pack_start(label("Oturum dili bir sonraki girişte uygulanır."), False, False, 0)
        self.language = self.dropdown(LANGUAGES, "language")
        self.language.get_accessible().set_name("Oturum dili")
        page.pack_start(self.language, False, False, 0)
        self.keyboard = self.dropdown(KEYBOARDS, "keyboard")
        self.keyboard.get_accessible().set_name("Klavye düzeni")
        page.pack_start(self.keyboard, False, False, 0)
        page.pack_start(button("Klavyeyi dene", self.preview_keyboard), False, False, 0)
        entry = Gtk.Entry(placeholder_text="Bu alana yazarak tuşları dene")
        entry.get_accessible().set_name("Klavye deneme alanı")
        page.pack_start(entry, False, False, 0)
        return page

    def preview_keyboard(self, _widget):
        try:
            if self.original_keyboard is None:
                keyboard = keyboard_status()
                if not keyboard[0]:
                    raise ValueError("Geçerli klavye düzeni okunamadı.")
                self.original_keyboard = keyboard
            xkb_apply(self.keyboard.get_active_id())
            self.status.set_text("Deneme klavyesi açık.")
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            self.status.set_text(str(error))

    def restore_keyboard(self):
        if self.original_keyboard:
            layout, variant = self.original_keyboard
            self.original_keyboard = None
            try:
                set_keyboard(layout, variant)
            except (OSError, ValueError, subprocess.SubprocessError):
                pass

    def appearance_page(self):
        page = column(7)
        page.pack_start(label("Görünüm ve uygulamalar"), False, False, 0)
        self.theme = self.dropdown(THEME_CHOICES, "theme")
        self.theme.get_accessible().set_name("Masaüstü görünümü")
        page.pack_start(self.theme, False, False, 0)
        self.preview = label("")
        self.preview.set_margin_bottom(4)
        self.preview.get_style_context().add_class("kage-theme-sample")
        page.pack_start(self.preview, False, False, 0)
        self.theme.connect("changed", lambda _field: self.update_preview())
        self.update_preview()
        page.pack_start(label("Toolbox’a eklemek istediğin uygulama kategorilerini seç."), False, False, 0)
        self.groups = {}
        for key, group in GROUPS.items():
            self.groups[key] = Gtk.CheckButton(label=group.title, active=key in self.choices["groups"])
            page.pack_start(self.groups[key], False, False, 0)
        return page

    def update_preview(self):
        choice = self.theme.get_active_id()
        context = self.preview.get_style_context()
        context.remove_class("kage-sample-light")
        if choice == "acik":
            context.add_class("kage-sample-light")
        self.preview.set_text("07.00 açık · 19.00 koyu" if choice == "otomatik" else f"{THEME_CHOICES[choice]} tema")

    def review_page(self):
        page = column()
        page.pack_start(label("Sürücü tercihi"), False, False, 0)
        self.driver = self.dropdown(DRIVER_CHOICES, "driver")
        self.driver.get_accessible().set_name("Sürücü tercihi")
        page.pack_start(self.driver, False, False, 0)
        page.pack_start(label("Kurulum için seçilen paketleri Toolbox ekranından uygulayabilirsin."), False, False, 0)
        self.summary = label("")
        page.pack_start(self.summary, False, False, 0)
        return page

    def values(self):
        return {"language": self.language.get_active_id(), "keyboard": self.keyboard.get_active_id(),
                "theme": self.theme.get_active_id(), "driver": self.driver.get_active_id(),
                "groups": [key for key, field in self.groups.items() if field.get_active()]}

    def sync(self):
        self.stack.set_visible_child_name(str(self.index))
        self.previous.set_sensitive(self.index > 0)
        self.next.set_label("Seçimleri uygula" if self.index == 2 else "İleri")
        self.status.set_text("")
        if self.index == 2:
            choice = self.values()
            groups = ", ".join(GROUPS[key].title for key in choice["groups"])
            self.summary.set_text(
                f"{LANGUAGES[choice['language']]} · {KEYBOARDS[choice['keyboard']]} · {THEME_CHOICES[choice['theme']]}"
                + (f"\nToolbox · {groups}" if groups else "")
            )

    def delete(self, _dialog, _event):
        self.response(Gtk.ResponseType.CANCEL)
        return True

    def respond(self, _dialog, response):
        if self.busy:
            return
        if response == Gtk.ResponseType.CANCEL:
            self.restore_keyboard()
            self.complete(None, True)
            self.destroy()
            return
        if response == Gtk.ResponseType.REJECT and self.index > 0:
            self.index -= 1
            self.sync()
        elif response == Gtk.ResponseType.APPLY and self.index < 2:
            self.index += 1
            self.sync()
        elif response == Gtk.ResponseType.APPLY:
            self.commit()

    def commit(self):
        self.restore_keyboard()
        values = self.values()
        self.busy = True
        for item in (self.skip, self.previous, self.next, self.stack):
            item.set_sensitive(False)
        self.status.set_text("Tercihler kaydediliyor…")

        def work():
            create_user_point("İlk açılış tercihleri öncesi")
            return apply_preferences(values)

        def done(scheduled, error):
            self.busy = False
            for item in (self.skip, self.previous, self.next, self.stack):
                item.set_sensitive(True)
            if error:
                self.status.set_text(error)
            else:
                self.complete(values, scheduled)
                self.destroy()

        self.run_job(work, done)
