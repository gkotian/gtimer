from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import tomllib


def _as_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, list):
        return tuple(str(item) for item in value if str(item))
    raise TypeError(f"Expected a string or list of strings, got {type(value).__name__}")


@dataclass(frozen=True)
class MatchRule:
    title_contains: tuple[str, ...] = ()
    class_contains: tuple[str, ...] = ()
    instance_contains: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MatchRule":
        return cls(
            title_contains=_as_tuple(data.get("title_contains")),
            class_contains=_as_tuple(data.get("class_contains")),
            instance_contains=_as_tuple(data.get("instance_contains")),
        )

    @property
    def is_empty(self) -> bool:
        return not (self.title_contains or self.class_contains or self.instance_contains)


@dataclass(frozen=True)
class TimerConfig:
    name: str
    label: str
    prominent: bool
    match: MatchRule


@dataclass
class AppConfig:
    database_path: Path = Path("~/.config/gtimer/gtimer.db").expanduser()
    refresh_interval_ms: int = 1000
    regular_application_limit: int = 5
    timers: dict[str, TimerConfig] = field(default_factory=dict)
    ignore: MatchRule = field(
        default_factory=lambda: MatchRule(title_contains=("gTimer",))
    )

    def prominent_timer(self) -> TimerConfig:
        for timer in self.timers.values():
            if timer.prominent:
                return timer
        return next(iter(self.timers.values()))


def default_config() -> AppConfig:
    minecraft = TimerConfig(
        name="minecraft",
        label="Minecraft Time",
        prominent=True,
        match=MatchRule(title_contains=("Minecraft",)),
    )
    return AppConfig(timers={"minecraft": minecraft})


def load_config(path: Path) -> AppConfig:
    if not path.exists():
        return default_config()

    with path.open("rb") as config_file:
        data = tomllib.load(config_file)

    config = default_config()
    app_data = data.get("app", {})
    if "database_path" in app_data:
        config.database_path = Path(str(app_data["database_path"])).expanduser()
    if "refresh_interval_ms" in app_data:
        config.refresh_interval_ms = int(app_data["refresh_interval_ms"])
    if "regular_application_limit" in app_data:
        config.regular_application_limit = int(app_data["regular_application_limit"])

    timers_data = data.get("timers", {})
    timers: dict[str, TimerConfig] = {}
    for name, timer_data in timers_data.items():
        rule = MatchRule.from_dict(timer_data)
        timers[name] = TimerConfig(
            name=name,
            label=str(timer_data.get("label", name.title())),
            prominent=bool(timer_data.get("prominent", False)),
            match=rule,
        )
    if timers:
        if not any(timer.prominent for timer in timers.values()):
            first_name = next(iter(timers))
            first = timers[first_name]
            timers[first_name] = TimerConfig(
                name=first.name,
                label=first.label,
                prominent=True,
                match=first.match,
            )
        config.timers = timers

    ignore_data = data.get("ignore", {})
    if ignore_data:
        config.ignore = MatchRule.from_dict(ignore_data)

    return config
