from __future__ import annotations

import datetime as _dt
import os

_BYTES_UNITS = ["B", "KB", "MB", "GB", "TB"]


def iso_of(ts: float) -> str:
    """Unix timestamp -> local ISO 8601 string."""
    return _dt.datetime.fromtimestamp(ts).astimezone().isoformat(timespec="seconds")


def human_bytes(n: int) -> str:
    f = float(n)
    for unit in _BYTES_UNITS:
        if f < 1024 or unit == _BYTES_UNITS[-1]:
            if unit == "B":
                return f"{int(f)} B"
            return f"{f:.1f} {unit}"
        f /= 1024
    return f"{n} B"


def expand(p: str) -> str:
    return os.path.abspath(os.path.expanduser(p))


def mask_mapping(d: dict | None) -> dict:
    """Keep keys, mask every value — secrets never reach the LLM context."""
    if not d:
        return {}
    return {str(k): "***" for k in d}


def tail_text(path: str, max_bytes: int = 5 * 1024 * 1024) -> str:
    """Read (at most) the last max_bytes of a file as text. '' on any error."""
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as fh:
            if size > max_bytes:
                fh.seek(size - max_bytes)
            data = fh.read()
        return data.decode("utf-8", errors="replace")
    except OSError:
        return ""
