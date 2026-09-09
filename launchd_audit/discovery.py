"""Discover scheduled jobs: scan launchd plist dirs, user crontab, /etc/crontab, /etc/cron.d."""

from __future__ import annotations

import os
import plistlib
import subprocess

from . import schedule
from .model import Job
from .util import expand, mask_mapping, redact_args

USER_AGENT_DIRS = ["~/Library/LaunchAgents", "/Library/LaunchAgents"]
SYSTEM_DAEMON_DIRS = ["/Library/LaunchDaemons"]


def parse_plist(path: str, kind: str, errors: list[dict]) -> Job | None:
    try:
        with open(path, "rb") as fh:
            raw = plistlib.load(fh)
    except Exception as e:  # noqa: BLE001 — honest failure: report, never crash
        errors.append({"path": path, "reason": f"plist parse failed: {e}"})
        return None

    label = raw.get("Label") or os.path.basename(path)

    program = None
    prog_args = raw.get("ProgramArguments")
    if isinstance(prog_args, list) and prog_args:
        prog_args = redact_args(prog_args)
        raw["ProgramArguments"] = prog_args
        program = " ".join(prog_args)
    elif raw.get("Program"):
        program = str(raw["Program"])

    sched_parts: list[str] = []
    cadence: float | None = None

    si = schedule.interval_seconds(raw.get("StartInterval"))
    if si:
        sched_parts.append(schedule.human_interval(si))
        cadence = si
    if raw.get("StartCalendarInterval") is not None:
        human, cad = schedule.human_calendar_interval(raw["StartCalendarInterval"])
        if human:
            sched_parts.append(human)
        cadence = cadence or cad
    if raw.get("RunAtLoad"):
        sched_parts.append("at load/login")
    if raw.get("KeepAlive"):
        sched_parts.append("keep alive (respawn)")
    if raw.get("WatchPaths"):
        wp = raw["WatchPaths"]
        sched_parts.append(f"on change of {len(wp)} path(s)")
    if raw.get("QueueDirectories"):
        sched_parts.append("on queued directories")

    # Only user-domain brew plists become "brew-service"; a brew plist installed with
    # `sudo brew services` lives in /Library/LaunchDaemons and must keep the
    # launchd-system source so job_action's read-only guard still applies.
    is_brew = os.path.basename(path).startswith("homebrew.mxcl.")
    source = "brew-service" if is_brew and kind == "launchd-user" else kind
    outputs = [p for p in (raw.get("StandardOutPath"), raw.get("StandardErrorPath")) if p]

    return Job(
        id=label,
        source=source,
        path=expand(path),
        program=program,
        schedule_human="; ".join(sched_parts) or None,
        cadence_seconds=cadence,
        disabled=bool(raw.get("Disabled")) or False,
        output_paths=[expand(p) for p in outputs],
        # EnvironmentVariables values are masked (and ProgramArguments redacted above)
        # before anything can leave this process
        raw={k: (mask_mapping(v) if k == "EnvironmentVariables" else v) for k, v in raw.items()},
    )


def scan_launchd(errors: list[dict]) -> list[Job]:
    jobs: list[Job] = []
    for d in USER_AGENT_DIRS:
        dd = expand(d)
        if not os.path.isdir(dd):
            continue
        for name in sorted(os.listdir(dd)):
            if name.endswith(".plist"):
                j = parse_plist(os.path.join(dd, name), "launchd-user", errors)
                if j:
                    jobs.append(j)
    for d in SYSTEM_DAEMON_DIRS:
        dd = expand(d)
        if not os.path.isdir(dd):
            continue
        for name in sorted(os.listdir(dd)):
            if name.endswith(".plist"):
                j = parse_plist(os.path.join(dd, name), "launchd-system", errors)
                if j:
                    jobs.append(j)
    return jobs


def _cron_line_job(line: str, origin: str, lineno: int, has_user_field: bool, errors: list[dict]) -> Job | None:
    parts = line.split(None, 6 if has_user_field else 5)
    needed = 7 if has_user_field else 6
    if len(parts) < needed:
        errors.append({"path": f"{origin} line {lineno}", "reason": "could not parse cron line"})
        return None
    spec = " ".join(parts[:5])
    user = parts[5] if has_user_field else None
    cmd = parts[6] if has_user_field else parts[5]
    human, cad = schedule.cron_human(spec)
    return Job(
        id=f"cron:{origin.replace(' ', '_')}:{lineno}",
        source="cron",
        path=f"{origin} line {lineno}",
        program=cmd,
        schedule_human=human,
        cadence_seconds=cad,
        raw={"spec": spec, "command": cmd, "user": user},
    )


def scan_cron(errors: list[dict]) -> list[Job]:
    jobs: list[Job] = []

    # user crontab
    try:
        out = subprocess.run(["crontab", "-l"], capture_output=True, text=True, timeout=10)
        if out.returncode == 0:
            for i, line in enumerate(out.stdout.splitlines(), 1):
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                j = _cron_line_job(line, "crontab", i, has_user_field=False, errors=errors)
                if j:
                    jobs.append(j)
        elif out.returncode != 1:  # rc 1 = "no crontab for user" — perfectly fine
            errors.append({"path": "crontab", "reason": out.stderr.strip()[:200]})
    except Exception as e:  # noqa: BLE001
        errors.append({"path": "crontab", "reason": str(e)})

    # system-wide cron (rare on macOS, best effort)
    for etc_path in ("/etc/crontab",):
        if os.path.isfile(etc_path):
            try:
                with open(etc_path) as fh:
                    for i, line in enumerate(fh, 1):
                        line = line.strip()
                        if not line or line.startswith("#"):
                            continue
                        j = _cron_line_job(line, "/etc/crontab", i, has_user_field=True, errors=errors)
                        if j:
                            jobs.append(j)
            except OSError as e:
                errors.append({"path": etc_path, "reason": str(e)})
    cron_d = "/etc/cron.d"
    if os.path.isdir(cron_d):
        for name in sorted(os.listdir(cron_d)):
            fp = os.path.join(cron_d, name)
            if not os.path.isfile(fp):
                continue
            try:
                with open(fp) as fh:
                    for i, line in enumerate(fh, 1):
                        line = line.strip()
                        if not line or line.startswith("#"):
                            continue
                        j = _cron_line_job(line, f"/etc/cron.d/{name}", i, has_user_field=True, errors=errors)
                        if j:
                            jobs.append(j)
            except OSError as e:
                errors.append({"path": fp, "reason": str(e)})

    return jobs
