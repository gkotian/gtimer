from __future__ import annotations

from .config import MatchRule
from .models import WindowInfo


def _contains_any(value: str | None, needles: tuple[str, ...]) -> bool:
    if not needles:
        return True
    if not value:
        return False
    lowered = value.casefold()
    return any(needle.casefold() in lowered for needle in needles)


def matches_rule(window: WindowInfo, rule: MatchRule) -> bool:
    if rule.is_empty:
        return False
    return (
        _contains_any(window.title, rule.title_contains)
        and _contains_any(window.window_class, rule.class_contains)
        and _contains_any(window.instance, rule.instance_contains)
    )
