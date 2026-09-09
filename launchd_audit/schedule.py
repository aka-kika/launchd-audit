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


DOW_SHORT = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
MONTH_SHORT = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
_DOW_ALIASES = {n.lower(): i for i, n in enumerate(DOW_SHORT)}
_MON_ALIASES = {n.lower(): i for i, n in enumerate(MONTH_SHORT) if n}


def _expand(field: str, lo: int, hi: int, aliases: dict[str, int] | None = None) -> list[int]:
    """Expand one cron field ('*', '*/5', '1,15', '9-17', 'mon-fri', '1-5/2') into sorted ints.
    Raises ValueError on anything it doesn't understand."""
    def atom(x: str) -> int:
        x = x.lower()
        if aliases and x in aliases:
            return aliases[x]
        return int(x)

    vals: set[int] = set()
    for part in field.split(","):
        step = 1
        if "/" in part:
            part, step_s = part.split("/", 1)
            step = int(step_s)
            if step <= 0:
                raise ValueError(step_s)
        if part == "*":
            rng = range(lo, hi + 1)
        elif "-" in part:
            a, b = part.split("-", 1)
            rng = range(atom(a), atom(b) + 1)
        else:
            a = atom(part)
            rng = range(a, hi + 1) if step > 1 else range(a, a + 1)
        vals.update(rng[::step])
    if not vals or min(vals) < lo or max(vals) > hi:
        raise ValueError(field)
    return sorted(vals)


def _regular_step(vals: list[int], lo: int, hi: int) -> int | None:
    """If vals is lo, lo+n, lo+2n ... covering the range, return n."""
    if len(vals) < 2 or vals[0] != lo:
        return None
    n = vals[1] - vals[0]
    if any(b - a != n for a, b in zip(vals, vals[1:])):
        return None
    if vals[-1] + n <= hi:
        return None
    return n


def _list_names(vals: list[int], names: list[str]) -> str:
    """[1,2,3,4,5] -> 'Mon-Fri'; [1,3,5] -> 'Mon, Wed, Fri'."""
    if len(vals) > 2 and vals == list(range(vals[0], vals[-1] + 1)):
        return f"{names[vals[0]]}-{names[vals[-1]]}"
    return ", ".join(names[v] for v in vals)


def _list_nums(vals: list[int]) -> str:
    if len(vals) > 2 and vals == list(range(vals[0], vals[-1] + 1)):
        return f"{vals[0]}-{vals[-1]}"
    return ", ".join(str(v) for v in vals)


def cron_human(spec: str) -> tuple[str, float | None]:
    """5-field cron spec -> (human string, cadence estimate in seconds).

    Handles lists, ranges, steps and day/month names. Falls back to the raw
    spec with no cadence when a field can't be understood."""
    parts = spec.split()
    if len(parts) != 5:
        return spec, None
    try:
        minutes = _expand(parts[0], 0, 59)
        hours = _expand(parts[1], 0, 23)
        dom = _expand(parts[2], 1, 31)
        months = _expand(parts[3], 1, 12, _MON_ALIASES)
        dow = _expand(parts[4], 0, 7, _DOW_ALIASES)
    except ValueError:
        return spec, None

    dow = sorted({d % 7 for d in dow})
    all_min, all_hr = len(minutes) == 60, len(hours) == 24
    all_dom, all_mon, all_dow = len(dom) == 31, len(months) == 12, len(dow) == 7

    # --- time-of-day part -------------------------------------------------
    cad: float | None
    if all_min and all_hr:
        when, cad = "every minute", 60
    elif all_hr and (n := _regular_step(minutes, 0, 59)):
        when, cad = f"every {n} minute{'s' if n > 1 else ''}", n * 60
    elif all_hr and len(minutes) == 1:
        when, cad = f"hourly at :{minutes[0]:02d}", 3600
    elif all_hr:
        when, cad = "hourly at " + ", ".join(f":{m:02d}" for m in minutes), 3600 / len(minutes)
    elif len(minutes) == 1 and (n := _regular_step(hours, 0, 23)):
        when, cad = f"every {n} hour{'s' if n > 1 else ''} at :{minutes[0]:02d}", n * 3600
    elif len(minutes) == 1 and len(hours) == 1:
        when, cad = f"daily at {hours[0]:02d}:{minutes[0]:02d}", 86400
    elif len(minutes) == 1:
        when = "daily at " + ", ".join(f"{h:02d}:{minutes[0]:02d}" for h in hours)
        cad = 86400 / len(hours)
    elif (n := _regular_step(minutes, 0, 59)):
        when = f"every {n} minute{'s' if n > 1 else ''} during hours {_list_nums(hours)}"
        cad = n * 60
    else:
        when = f"at minutes {_list_nums(minutes)} of hours {_list_nums(hours)}"
        cad = 3600 / len(minutes)

    # --- day restrictions ---------------------------------------------------
    if not all_dow and all_dom:
        if len(dow) == 1 and when.startswith("daily at "):
            when = f"weekly on {WEEKDAYS[dow[0]]} at {when[len('daily at '):]}"
        else:
            when += f" on {_list_names(dow, DOW_SHORT)}"
        if cad and cad >= 86400:
            cad = 7 * 86400 / len(dow)
    if not all_dom:
        if len(dom) == 1 and when.startswith("daily at "):
            when = f"monthly on day {dom[0]} at {when[len('daily at '):]}"
        else:
            when += f" on day{'s' if len(dom) > 1 else ''} {_list_nums(dom)}"
        if not all_dow:
            when += f" and on {_list_names(dow, DOW_SHORT)}"  # cron ORs dom with dow
        if cad and cad >= 86400:
            cad = 2629800 / len(dom)
    if not all_mon:
        when += f" in {_list_names(months, MONTH_SHORT)}"
        if cad and cad >= 86400:
            cad = 31557600 / len(months)

    return when, cad
