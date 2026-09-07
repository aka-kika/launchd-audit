"""Humanizers: turn launchd/cron schedule structures into plain English + cadence estimates."""

from __future__ import annotations

import json

# launchd Weekday numbering: 0 and 7 = Sunday, 1 = Monday, ... 6 = Saturday
WEEKDAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]


def interval_seconds(si) -> float | None:
    try:
        v = float(si)
        return v if v > 0 else None
    except (TypeError, ValueError):
        return None


def human_interval(seconds: int | float) -> str:
    s = int(seconds)
    if s >= 86400 and s % 86400 == 0:
        d = s // 86400
        return f"every {d} day{'s' if d > 1 else ''}"
    if s >= 3600 and s % 3600 == 0:
        h = s // 3600
        return f"every {h} hour{'s' if h > 1 else ''}"
    if s >= 60 and s % 60 == 0:
        m = s // 60
        return f"every {m} minute{'s' if m > 1 else ''}"
    return f"every {s} second{'s' if s != 1 else ''}"


def human_calendar_interval(ci) -> tuple[str, float | None]:
    """StartCalendarInterval value -> (human string, cadence estimate in seconds)."""
    if ci is None:
        return "", None
    items = ci if isinstance(ci, list) else [ci]
    parts: list[str] = []
    cadences: list[float] = []

    for d in items:
        if not isinstance(d, dict):
            parts.append(str(d))
            continue
        h, m = d.get("Hour"), d.get("Minute")
        hm = None
        if h is not None:
            hm = f"{int(h):02d}:{int(m or 0):02d}"
        elif m is not None:
            hm = f":{int(m):02d}"
        wd, day, month = d.get("Weekday"), d.get("Day"), d.get("Month")

        if month is not None and day is not None:
            label = f"on {int(month):02d}-{int(day):02d}" + (f" at {hm}" if hm else "")
            cad: float | None = 366 * 86400  # ~yearly
        elif day is not None:
            label = f"monthly on day {int(day)}" + (f" at {hm}" if hm else "")
            cad = 2629800  # ~month
        elif wd is not None:
            try:
                name = WEEKDAYS[int(wd) % 7]
            except (TypeError, ValueError):
                name = str(wd)
            label = f"weekly on {name}" + (f" at {hm}" if hm else "")
            cad = 604800
        elif h is not None:
            label = f"daily at {hm}"
            cad = 86400
        elif m is not None:
            label = f"hourly at :{int(m):02d}"
            cad = 3600
        else:
            label = json.dumps(d)
            cad = None
        parts.append(label)
        if cad:
            cadences.append(cad)

    return "; ".join(parts), (min(cadences) if cadences else None)


def cron_human(spec: str) -> tuple[str, float | None]:
    """5-field cron spec -> (human string, cadence estimate in seconds)."""
    parts = spec.split()
    if len(parts) != 5:
        return spec, None
    mi, h, dom, mon, dow = parts

    def num(x: str):
        try:
            return int(x)
        except ValueError:
            return None

    if parts == ["*", "*", "*", "*", "*"]:
        return "every minute", 60
    if mi.startswith("*/") and h == "*" and dom == "*" and mon == "*" and dow == "*":
        n = num(mi[2:])
        if n:
            return f"every {n} minute{'s' if n > 1 else ''}", n * 60
        return spec, None
    M, H = num(mi), num(h)
    if M is not None and H is not None:
        hm = f"{H:02d}:{M:02d}"
        if dom == "*" and mon == "*" and dow == "*":
            return f"daily at {hm}", 86400
        if dom == "*" and mon == "*" and dow != "*":
            return f"weekly (weekday {dow}) at {hm}", 604800
        if dom != "*" and mon == "*" and dow == "*":
            return f"monthly on day {dom} at {hm}", 2629800
        if mon != "*" and dom != "*" and dow == "*":
            return f"yearly on {mon}-{dom} at {hm}", 31557600
    return spec, None
