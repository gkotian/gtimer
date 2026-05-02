from __future__ import annotations


def format_duration(seconds: float) -> str:
    total = max(0, int(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def format_signed_duration(seconds: float, include_plus: bool = False) -> str:
    sign = ""
    if seconds < 0:
        sign = "-"
    elif include_plus:
        sign = "+"
    return f"{sign}{format_duration(abs(seconds))}"


def format_percent(value: float) -> str:
    return f"{value * 100:.1f}%"
