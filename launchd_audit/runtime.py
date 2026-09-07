"""Ask launchctl for live runtime state and merge it into Job objects."""

from __future__ import annotations

import os
import re
import subprocess

from .model import Job


def launchctl_disabled_overrides() -> dict[str, bool]:
    """Label -> disabled flag from `launchctl print-disabled gui/<uid>`."""
    uid = os.getuid()
    table: dict[str, bool] = {}
    try:
        out = subprocess.run(
            ["launchctl", "print-disabled", f"gui/{uid}"],
            capture_output=True, text=True, timeout=10,
        )
        for line in out.stdout.splitlines():
            m = re.match(r'\s*"?([^"\s]+)"?\s*=>\s*(true|false)', line)
            if m:
                table[m.group(1)] = m.group(2) == "true"
    except Exception:  # noqa: BLE001
        pass
    return table


def launchctl_print(label: str) -> dict:
    """Parsed `launchctl print gui/<uid>/<label>` ({} if not loaded / not readable)."""
    uid = os.getuid()
    info: dict[str, str] = {}
    try:
        out = subprocess.run(
            ["launchctl", "print", f"gui/{uid}/{label}"],
            capture_output=True, text=True, timeout=10,
        )
        if out.returncode != 0:
            return {}
        for line in out.stdout.splitlines():
            m = re.match(r"\s*(state|pid|last exit code|runs|spawn type|path) = (.+)", line.strip())
            if m:
                info[m.group(1)] = m.group(2)
    except Exception:  # noqa: BLE001
        pass
    return info


def merge_runtime(job: Job, disabled_overrides: dict[str, bool] | None = None) -> None:
    """Fill state / running_pid / last_exit / runs on a Job. Cron jobs have no live state."""
    if job.source == "cron":
        job.state = "scheduled"
        return

    if disabled_overrides is not None and disabled_overrides.get(job.id):
        job.disabled = True

    info = launchctl_print(job.id)
    pid_s = info.get("pid")
    state = info.get("state")

    if pid_s and pid_s.isdigit():
        job.running_pid = int(pid_s)
        job.state = "running"
    elif state in ("waiting", "not running"):
        job.state = "idle"
    elif state:
        job.state = state
    else:
        job.state = "not-loaded"

    lec = info.get("last exit code")
    if lec not in (None, "(never)") and not lec.startswith("("):
        try:
            job.last_exit = int(lec)
        except ValueError:
            pass

    runs = info.get("runs")
    if runs and runs.isdigit():
        job.runs = int(runs)

    if job.disabled:
        job.state = "disabled"
