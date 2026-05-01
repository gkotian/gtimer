from __future__ import annotations


def system_uptime_seconds() -> float:
    with open("/proc/uptime", encoding="utf-8") as uptime_file:
        return float(uptime_file.read().split()[0])
