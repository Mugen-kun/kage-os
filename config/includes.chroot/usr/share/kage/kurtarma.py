"""Local restore points for the Kage and Xfce settings that the UI manages."""

from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
import uuid

from aygitlar import POWER, power_status, set_power
from masaustu import get_setting, store_theme, theme_timer, write_setting, xfconf
from sistem import command_output, read_text
from tercihler import (THEME_CHOICES, config_file, keyboard_status, read_preferences, set_keyboard, validated,
                      write_setting_file)


XFC_SETTINGS = (
    ("xsettings", "/Net/ThemeName", "string"),
    ("xsettings", "/Net/IconThemeName", "string"),
    ("xsettings", "/Gtk/FontName", "string"),
    ("xsettings", "/Gtk/MonospaceFontName", "string"),
    ("keyboard-layout", "/Default/XkbLayout", "string"),
    ("keyboard-layout", "/Default/XkbVariant", "string"),
    ("keyboard-layout", "/Default/XkbDisable", "bool"),
)
POINT = re.compile(r"[0-9]{8}T[0-9]{6}Z-[a-f0-9]{12}")


def recovery_directory():
    return Path.home() / "Kage-Kurtarma-Noktalari"


def point_id():
    return f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:12]}"


def create_user_point(reason):
    identifier = point_id()
    preferences = read_preferences() if config_file("tercihler.json").is_file() else None
    mode = read_text(config_file("gorunum"))
    remembered_power = read_text(config_file("guc-profili")) in POWER
    power_service = command_output("systemctl", "is-active", "power-profiles-daemon.service")
    current_power = power_status()[1] if remembered_power or power_service == "active" else ""
    try:
        keyboard = keyboard_status()
    except (OSError, ValueError, subprocess.SubprocessError):
        keyboard = None
    point = {
        "reason": reason, "preferences": preferences,
        "theme": mode if mode in THEME_CHOICES else None,
        "power": current_power if current_power in POWER else None,
        "remember_power": remembered_power,
        "keyboard": list(keyboard) if keyboard and keyboard[0] else None,
        "xfce": [get_setting(channel, prop) for channel, prop, _kind in XFC_SETTINGS],
    }
    write_setting_file(recovery_directory() / f"{identifier}.json", json.dumps(point, ensure_ascii=False, indent=2) + "\n")
    return identifier


def load_user_point(identifier):
    if not POINT.fullmatch(identifier or ""):
        raise ValueError("Kurtarma noktası geçersiz.")
    path = recovery_directory() / f"{identifier}.json"
    if path.is_symlink():
        raise ValueError("Kurtarma noktası geçersiz.")
    point = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(point, dict) or not isinstance(point.get("reason"), str):
        raise ValueError("Kurtarma noktası okunamadı.")
    settings = point.get("xfce")
    if (not isinstance(settings, list) or len(settings) != len(XFC_SETTINGS)
            or any(value is not None and (not isinstance(value, str) or "\0" in value or len(value) > 500)
                   for value in settings)):
        raise ValueError("Kurtarma noktasındaki Xfce ayarları geçersiz.")
    if settings[-1] not in {None, "true", "false"}:
        raise ValueError("Kurtarma noktasındaki klavye ayarı geçersiz.")
    if point.get("theme") not in (*THEME_CHOICES, None) or point.get("power") not in (*POWER, None):
        raise ValueError("Kurtarma noktasındaki görünüm veya güç seçimi geçersiz.")
    if point.get("preferences") is not None:
        point["preferences"] = validated(point["preferences"])
    keyboard = point.get("keyboard")
    if keyboard is not None and (not isinstance(keyboard, list) or len(keyboard) != 2
                                 or any(not isinstance(value, str) or len(value) > 80 for value in keyboard)):
        raise ValueError("Kurtarma noktasındaki klavye düzeni geçersiz.")
    return point


def user_points():
    points = []
    for item in sorted(recovery_directory().glob("*.json"), reverse=True):
        if POINT.fullmatch(item.stem):
            try:
                point = load_user_point(item.stem)
            except (OSError, ValueError):
                continue
            points.append((item.stem, point["reason"]))
    return points


def restore_user_point(identifier, *, authorize=None):
    point = load_user_point(identifier)
    create_user_point("Kişisel geri alma öncesi")
    for (channel, prop, kind), value in zip(XFC_SETTINGS, point["xfce"]):
        if value is None:
            xfconf(channel, prop, "--reset")
        else:
            write_setting(channel, prop, kind, value)
    if point.get("keyboard"):
        set_keyboard(*point["keyboard"])
    if point.get("theme"):
        store_theme(point["theme"])
    else:
        config_file("gorunum").unlink(missing_ok=True)
        theme_timer("stop")
    path = config_file("tercihler.json")
    if point.get("preferences"):
        write_setting_file(path, json.dumps(point["preferences"], ensure_ascii=False, indent=2) + "\n")
    else:
        path.unlink(missing_ok=True)
    if point.get("power") and point["power"] in power_status()[0]:
        set_power(point["power"], authorize=authorize)
    if not point.get("remember_power"):
        config_file("guc-profili").unlink(missing_ok=True)
