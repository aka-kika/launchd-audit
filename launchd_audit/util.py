from __future__ import annotations

import datetime as _dt
import os
import re

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


_SECRET_KEY_RX = re.compile(
    r"(?i)(token|secret|passw(or)?d|api[-_]?key|apikey|auth|bearer|credential|private[-_]?key|access[-_]?key)"
)
_KV_RX = re.compile(r"^(--?[\w.-]+|[A-Za-z_]\w*)=(.+)$", re.DOTALL)


def redact_args(args: list) -> list[str]:
    """Mask values that look like secrets in a ProgramArguments list.

    Covers `--token=abc`, `API_KEY=abc`, and `--password abc` (the argument
    following a secret-looking flag). Keys stay visible; values become ***.
    Heuristic by design: it masks a little too much rather than too little.
    """
    out: list[str] = []
    mask_next = False
    for a in args:
        s = str(a)
        if mask_next:
            out.append("***")
            mask_next = False
            continue
        m = _KV_RX.match(s)
        if m:
            key, val = m.group(1), m.group(2)
            out.append(f"{key}=***" if _SECRET_KEY_RX.search(key) and val else s)
            continue
        if s.startswith("-") and _SECRET_KEY_RX.search(s):
            out.append(s)
            mask_next = True
            continue
        out.append(s)
    return out
