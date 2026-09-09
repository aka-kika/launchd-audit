"""Ask launchctl for live runtime state and merge it into Job objects.

Listing uses ONE `launchctl list` call for every job (pid + last exit status).
`launchctl print` is richer (run count, precise "never exited") but costs a
subprocess per job, so it is only used by job_detail.
"""

from __future__ import annotations

import os
import re
import subprocess

from .model import Job

LoadedTable = dict[str, tuple[int | None, int | None]]


def launchctl_list() -> LoadedTable:
    """Label -> (pid, last_exit) for every job loaded in this user's domain.

    Output looks like:
        PID     Status  Label
        -       0       com.example.idle
        4242    0       com.example.running
        -       78      com.example.failed
    Status is the last exit status; negative means killed by that signal.
    """
    table: LoadedTable = {}
    try:
        out = subprocess.run(["launchctl", "list"], capture_output=True, text=True, timeout=15)
        for line in out.stdout.splitlines():
            parts = line.split("\t") if "\t" in line else line.split(None, 2)
            if len(parts) < 3:
                continue
            pid_s, status_s, label = (p.strip() for p in parts[:3])
            if label == "Label":
                continue
            pid = int(pid_s) if pid_s.isdigit() else None
            try:
                status: int | None = int(status_s)
            except ValueError:
                status = None
            table[label] = (pid, status)
    except Exception:  # noqa: BLE001 — no launchctl (not macOS) or it hung; treat as nothing loaded
        pass
    return table


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


def merge_runtime(
    job: Job,
    disabled_overrides: dict[str, bool] | None = None,
    loaded: LoadedTable | None = None,
) -> None:
    """Fill state / running_pid / last_exit on a Job from the `launchctl list` table.

    Cron jobs have no live state. Pass `loaded` when merging many jobs so
    launchctl is invoked once, not once per job.
    """
    if job.source == "cron":
        job.state = "scheduled"
        return

    if disabled_overrides is not None and disabled_overrides.get(job.id):
        job.disabled = True

    if loaded is None:
        loaded = launchctl_list()

    entry = loaded.get(job.id)
    if entry is None:
        job.state = "not-loaded"
    else:
        pid, status = entry
        if pid:
            job.running_pid = pid
            job.state = "running"
        else:
            job.state = "idle"
        job.last_exit = status

    if job.disabled:
        job.state = "disabled"


def merge_print_details(job: Job, info: dict) -> None:
    """Refine a Job with `launchctl print` output (job_detail only): run count and
    a precise last exit ("(never exited)" -> null, which `launchctl list` reports as 0)."""
    runs = info.get("runs")
    if runs and runs.isdigit():
        job.runs = int(runs)
    lec = info.get("last exit code")
    if lec is None:
        return
    if lec.startswith("("):
        job.last_exit = None
        return
    try:
        job.last_exit = int(lec)
    except ValueError:
        pass
