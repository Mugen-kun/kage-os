"""Portable selections for the existing Kage Toolbox package groups."""

import json
from pathlib import Path

from rapor import regular_file
from tercihler import config_file, write_setting_file
from toolbox import GROUPS


FORMAT = "kage-toolbox-profile"
VERSION = 1
MAX_BYTES = 16_384


def validated_groups(groups):
    if not isinstance(groups, (tuple, list)) or len(groups) > 64 or any(
        not isinstance(group, str) or group not in GROUPS for group in groups
    ):
        raise ValueError("Profilde tanınmayan Toolbox kategorisi var.")
    return list(dict.fromkeys(groups))


def profile_document(groups):
    return {"format": FORMAT, "version": VERSION, "groups": validated_groups(groups)}


def read_profile(path=None):
    saved = config_file("paket-profili.json") if path is None else Path(path)
    try:
        source = regular_file(saved, "Paket profili")
        with source.open("rb") as stream:
            data = stream.read(MAX_BYTES + 1)
    except FileNotFoundError:
        if path is None:
            return None
        raise
    if len(data) > MAX_BYTES:
        raise ValueError("Paket profili çok büyük.")
    try:
        profile = json.loads(data.decode("utf-8"))
    except (ValueError, UnicodeError) as error:
        raise ValueError("Paket profili JSON olarak okunamadı.") from error
    if (not isinstance(profile, dict) or profile.get("format") != FORMAT
            or type(profile.get("version")) is not int or profile["version"] != VERSION):
        raise ValueError("Bu dosya desteklenen bir Kage paket profili değil.")
    return validated_groups(profile.get("groups"))


def save_profile(groups, path=None):
    saved = config_file("paket-profili.json") if path is None else Path(path)
    data = json.dumps(profile_document(groups), ensure_ascii=False, indent=2) + "\n"
    write_setting_file(saved, data)


def missing_groups(groups, installed):
    return [key for key in validated_groups(groups) if not set(GROUPS[key].packages).issubset(installed)]
