"""Accent-insensitive search text shared by Kage's catalogues."""

import unicodedata


def normalize(text):
    folded = unicodedata.normalize("NFKD", text.casefold().replace("ı", "i"))
    return "".join(char for char in folded if not unicodedata.combining(char))
