"""Xfce desktop arrangements, presentation and theme scheduling."""

from datetime import datetime
import os
from pathlib import Path
import subprocess
import sys
import time

from gunluk_dosyalar import staged_file
from rapor import regular_file


DND = ("xfce4-notifyd", "/do-not-disturb")
THEMES = {"acik": ("Adwaita", "Papirus"), "koyu": ("Adwaita-dark", "Papirus-Dark")}
THEME_TIMER = "kage-gorunum.timer"


def command(*arguments):
    return subprocess.run(arguments, capture_output=True, text=True, errors="replace", timeout=4)


def xfconf(channel, property_name, *arguments):
    return command("xfconf-query", "-c", channel, "-p", property_name, *arguments)


def get_setting(channel, property_name):
    result = xfconf(channel, property_name)
    return result.stdout.strip() if result.returncode == 0 else None


def write_setting(channel, property_name, kind, value):
    result = xfconf(channel, property_name, "--create", "--type", kind, "--set", value)
    if result.returncode:
        raise ValueError(result.stderr.strip() or "Xfce ayarı yazılamadı.")


class Presentation:
    def __init__(self):
        self.active = False
        self.previous = None

    def start(self):
        if self.active:
            return
        self.previous = get_setting(*DND)
        write_setting(*DND, "bool", "true")
        self.active = True

    def stop(self):
        if not self.active:
            return
        if self.previous is None:
            result = xfconf(*DND, "--reset")
            if result.returncode and get_setting(*DND) is not None:
                raise ValueError(result.stderr.strip() or "Bildirim ayarı geri alınamadı.")
        else:
            write_setting(*DND, "bool", self.previous)
        self.active = False


def windows():
    result = command("wmctrl", "-lx")
    if result.returncode:
        raise ValueError(result.stderr.strip() or "Xfce pencereleri listelenemedi.")
    return [fields for line in result.stdout.splitlines() if len(fields := line.split(None, 4)) == 5]


def open_study(document, workarea):
    note_folder = Path.home() / "Kage-Notlar"
    note_folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    notes = note_folder / "ders.txt"
    if not notes.exists():
        notes.touch(mode=0o600, exist_ok=True)
    if not document:
        subprocess.Popen(["mousepad", "--opening-mode=window", str(notes)], start_new_session=True)
        return False
    pdf = regular_file(document, "Ders PDF’sini")
    initial = {fields[0] for fields in windows()}
    subprocess.Popen(["zathura", str(pdf)], start_new_session=True)
    subprocess.Popen(["mousepad", "--disable-server", str(notes)], start_new_session=True)
    deadline = time.monotonic() + 4
    while time.monotonic() < deadline:
        current = windows()
        viewer = next((fields[0] for fields in current
                       if "zathura" in fields[2].casefold()
                       and (fields[0] not in initial or pdf.name.casefold() in fields[4].casefold())), None)
        editor = next((fields[0] for fields in current
                       if "mousepad" in fields[2].casefold() and fields[0] not in initial), None)
        if viewer and editor:
            x, y, width, height = workarea
            left = int(width * 0.58)
            for wid, position, size in ((viewer, x, left), (editor, x + left, width - left)):
                command("wmctrl", "-ir", wid, "-b", "remove,maximized_vert,maximized_horz")
                result = command("wmctrl", "-ir", wid, "-e", f"0,{position},{y},{max(1, size - 8)},{max(1, height - 35)}")
                if result.returncode:
                    return False
            return True
        time.sleep(0.1)
    return False


def theme_config():
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "kage-os" / "gorunum"


def saved_theme():
    try:
        return theme_config().read_text(encoding="ascii").strip()
    except (OSError, UnicodeError):
        return ""


def theme_for_hour(hour):
    return "acik" if 7 <= hour < 19 else "koyu"


def apply_theme(theme):
    gtk, icons = THEMES[theme]
    write_setting("xsettings", "/Net/ThemeName", "string", gtk)
    write_setting("xsettings", "/Net/IconThemeName", "string", icons)


def theme_timer(action):
    return command("systemctl", "--user", action, THEME_TIMER)


def store_theme(mode):
    if mode not in THEMES and mode != "otomatik":
        raise ValueError("Geçersiz görünüm seçimi.")
    apply_theme(theme_for_hour(datetime.now().hour) if mode == "otomatik" else mode)
    state = theme_config()
    state.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    with staged_file(state.parent) as temporary:
        temporary.write_text(mode + "\n", encoding="ascii")
        temporary.replace(state)
    result = theme_timer("start" if mode == "otomatik" else "stop")
    return mode != "otomatik" or result.returncode == 0


def automatic_theme(*, on_login=False):
    if saved_theme() == "otomatik":
        apply_theme(theme_for_hour(datetime.now().hour))
        if on_login:
            result = theme_timer("start")
            if result.returncode:
                raise ValueError(result.stderr.strip() or "Görünüm zamanlayıcısı başlatılamadı.")


if __name__ == "__main__":
    try:
        automatic_theme(on_login=sys.argv[1:] == ["--oturum-acilisi"])
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(error, file=sys.stderr)
        raise SystemExit(1) from error
