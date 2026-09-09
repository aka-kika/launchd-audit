"""The audit: which jobs are failing, stale, or filling the disk with logs?"""

from __future__ import annotations

import os
import time
from collections import Counter

from .model import Job
from .util import human_bytes, iso_of

LOG_PRESSURE_BYTES = 100 * 1024 * 1024  # 100 MB
_LOG_SUFFIXES = (".log", ".out", ".err", ".txt")


def _name_matches(job_stem: str, filename: str) -> bool:
    """Does this file plausibly belong to this job?

    job_stem is the last dot-component of the label (e.g. 'dailyreport').
    Matches when the file's stem and the job's stem are prefix- or
    substring-related in either direction — enough to pair
    'com.example.sync.watcher' with 'watcher.log' and
    'com.example.sync.dailyreport' with 'report.log'."""
    name = filename.lower()
    for suffix in _LOG_SUFFIXES:
        if name.endswith(suffix):
            name = name[: -len(suffix)]
            break
    name = name.lstrip(".")
    if len(name) < 4 or len(job_stem) < 4:
        return False
    return (
        name.startswith(job_stem)
        or job_stem.startswith(name)
        or job_stem.endswith(name)
        or name in job_stem
    )


def evidence_files(job: Job) -> list[str]:
    """Declared log paths PLUS sibling files that look like the job's own logs.

    Many scripts write their own log file (e.g. ~/sync/logs/watcher.log) and
    leave the plist's StandardOutPath/StandardErrorPath untouched on successful
    runs. stderr mtime alone would flag such healthy jobs as stale — a false
    positive this function exists to prevent."""
    paths = {p for p in job.output_paths}
    stem = job.id.rsplit(".", 1)[-1].lower()
    dirs = {os.path.dirname(p) for p in job.output_paths if os.path.dirname(p)}
    for d in dirs:
        try:
            for name in os.listdir(d):
                if _name_matches(stem, name):
                    paths.add(os.path.join(d, name))
        except OSError:
            continue
    return sorted(paths)


def sibling_listing(job: Job, limit: int = 20) -> list[dict]:
    """Everything in the job's log dir(s) by mtime — evidence for the verdict.

    Staleness is a heuristic; when a job is flagged, showing the whole
    directory lets the reader spot the fresh file the script *actually*
    writes to (e.g. a hidden .last-run.log)."""
    seen: dict[str, dict] = {}
    dirs = {os.path.dirname(p) for p in job.output_paths if os.path.dirname(p)}
    for d in dirs:
        try:
            for name in os.listdir(d):
                fp = os.path.join(d, name)
                try:
                    st = os.stat(fp)
                except OSError:
                    continue
                if not os.path.isfile(fp):
                    continue
                seen[fp] = {
                    "path": fp,
                    "bytes": st.st_size,
                    "last_modified": iso_of(st.st_mtime),
                }
        except OSError:
            continue
    ranked = sorted(seen.values(), key=lambda s: s["last_modified"], reverse=True)
    return ranked[:limit]


def log_stats(job: Job, paths: list[str] | None = None) -> list[dict]:
    stats = []
    for p in paths if paths is not None else job.output_paths:
        try:
            st = os.stat(p)
            stats.append({"path": p, "bytes": st.st_size, "mtime": st.st_mtime})
        except OSError:
            continue
    return stats


def audit(jobs: list[Job]) -> dict:
    failing: list[dict] = []
    stale: list[dict] = []
    pressure: list[dict] = []
    notes: list[str] = []
    running = 0
    disabled = 0
    now = time.time()

    for job in jobs:
        if job.state == "running":
            running += 1
        if job.disabled or job.state == "disabled":
            disabled += 1

        # --- failing -----------------------------------------------------
        if job.source != "cron" and job.last_exit not in (None, 0) and job.state != "running":
            failing.append({
                "id": job.id,
                "last_exit": job.last_exit,
                "state": job.state,
                "note": (
                    f"last run was killed by signal {-job.last_exit}"
                    if job.last_exit < 0 else "last observed exit was non-zero"
                ),
            })
        elif job.raw.get("KeepAlive") and job.state in ("not-loaded",):
            failing.append({
                "id": job.id,
                "last_exit": job.last_exit,
                "state": job.state,
                "note": "keep-alive job is not loaded",
            })

        # --- stale -------------------------------------------------------
        if job.cadence_seconds and job.source != "cron":
            stats = log_stats(job, evidence_files(job))
            if stats:
                newest = max(s["mtime"] for s in stats)
                age_days = (now - newest) / 86400
                threshold_days = max(3 * job.cadence_seconds / 86400, 1.0)
                if age_days > threshold_days:
                    stale.append({
                        "id": job.id,
                        "expected_cadence": job.schedule_human,
                        "days_since_last_evidence": round(age_days, 1),
                        "note": (
                            "suspected stale: declared/name-matched log evidence is older "
                            "than 3x the expected cadence — check 'log_dir_evidence' for a "
                            "fresh file the script may write to under another name"
                        ),
                        "log_dir_evidence": sibling_listing(job),
                    })

        # --- log pressure ------------------------------------------------
        for s in log_stats(job):
            if s["bytes"] >= LOG_PRESSURE_BYTES:
                pressure.append({
                    "id": job.id,
                    "output_path": s["path"],
                    "bytes": s["bytes"],
                    "human": human_bytes(s["bytes"]),
                    "last_modified": iso_of(s["mtime"]),
                })

    # --- notes -----------------------------------------------------------
    progs = Counter(j.program for j in jobs if j.program)
    for prog, n in progs.most_common():
        if n > 1:
            notes.append(f"{n} jobs share the same program: {prog[:80]}")

    return {
        "totals": {
            "jobs": len(jobs),
            "running": running,
            "disabled": disabled,
            "failing": len(failing),
            "stale": len(stale),
        },
        "failing": failing,
        "stale": stale,
        "log_pressure": pressure,
        "notes": notes,
    }
