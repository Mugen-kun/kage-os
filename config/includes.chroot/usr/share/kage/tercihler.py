"""Persist the language, input and package choices for a Kage desktop session."""

import json
import os
from pathlib import Path
import re
import subprocess
import sys

from gunluk_dosyalar import staged_file
from bakim import read_command
from masaustu import store_theme, write_setting
from toolbox import GROUPS


LANGUAGES = {"tr_TR.UTF-8": "Türkçe", "en_US.UTF-8": "English"}
KEYBOARDS = {"tr": "Türkçe Q", "tr:f": "Türkçe F", "us": "English (US)"}
THEME_CHOICES = {"koyu": "Koyu", "acik": "Açık", "otomatik": "Saatle otomatik"}
DRIVER_CHOICES = {"default": "Mevcut sürücüyü kullan", "nvidia": "NVIDIA yardımcısını aç"}
DEFAULTS = {"language": "tr_TR.UTF-8", "keyboard": "tr", "theme": "koyu",
            "groups": [], "driver": "default"}


def config_file(name):
    directory = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return directory / "kage-os" / name


def write_setting_file(path, content):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with staged_file(path.parent) as temporary:
        temporary.write_text(content, encoding="utf-8")
        temporary.replace(path)


def validated(data):
    if not isinstance(data, dict):
        raise ValueError("Oturum tercihleri okunamadı.")
    result = DEFAULTS.copy()
    for key, choices in (("language", LANGUAGES), ("keyboard", KEYBOARDS),
                         ("theme", THEME_CHOICES), ("driver", DRIVER_CHOICES)):
        value = data.get(key, result[key])
        if not isinstance(value, str) or value not in choices:
            raise ValueError(f"Geçersiz oturum tercihi · {key}")
        result[key] = value
    groups = data.get("groups", [])
    if not isinstance(groups, list) or any(not isinstance(group, str) or group not in GROUPS for group in groups):
        raise ValueError("Uygulama paketi seçimi geçersiz.")
    result["groups"] = list(dict.fromkeys(groups))
    return result


def read_preferences():
    try:
        return validated(json.loads(config_file("tercihler.json").read_text(encoding="utf-8")))
    except (OSError, ValueError, UnicodeError):
        return DEFAULTS.copy()


def keyboard_status():
    info = {}
    for line in read_command("setxkbmap", "-query").splitlines():
        title, _, value = line.partition(":")
        info[title] = value.strip()
    return info.get("layout", ""), info.get("variant", "")


def set_keyboard(layout, variant):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_,.-]{0,79}", layout) or not re.fullmatch(r"[A-Za-z0-9_,.-]{0,80}", variant):
        raise ValueError("Klavye düzeni geçersiz.")
    result = subprocess.run(
        ["setxkbmap", "-layout", layout, "-variant", variant], capture_output=True, text=True, timeout=8,
    )
    if result.returncode:
        raise ValueError(result.stderr.strip() or "Klavye düzeni değiştirilemedi.")


def xkb_apply(choice):
    if choice not in KEYBOARDS:
        raise ValueError("Klavye düzeni geçersiz.")
    layout, _, variant = choice.partition(":")
    set_keyboard(layout, variant)


def apply_preferences(data):
    values = validated(data)
    layout, _, variant = values["keyboard"].partition(":")
    xkb_apply(values["keyboard"])
    write_setting("keyboard-layout", "/Default/XkbLayout", "string", layout)
    write_setting("keyboard-layout", "/Default/XkbVariant", "string", variant)
    write_setting("keyboard-layout", "/Default/XkbDisable", "bool", "false")
    scheduled = store_theme(values["theme"])
    write_setting_file(config_file("tercihler.json"), json.dumps(values, ensure_ascii=False, indent=2) + "\n")
    return scheduled


if __name__ == "__main__" and sys.argv[1:] == ["--locale"]:
    if config_file("tercihler.json").is_file():
        print(read_preferences()["language"])
