from __future__ import annotations

import re

from .models import WindowInfo


_SPACES = re.compile(r"\s+")


def normalize_title(title: str | None) -> str:
    if not title:
        return "unknown"
    normalized = _SPACES.sub(" ", title.strip()).casefold()
    return normalized or "unknown"


def normalize_part(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = _SPACES.sub(" ", value.strip()).casefold()
    return normalized or None


def window_key(window: WindowInfo) -> str:
    window_class = normalize_part(window.window_class)
    instance = normalize_part(window.instance)
    title = normalize_title(window.title)
    if window_class and instance:
        return f"{window_class}|{instance}"
    if window_class:
        return f"{window_class}|{title}"
    return title
