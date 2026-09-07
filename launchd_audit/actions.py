"""job_action: the ONLY mutating path. Plan is pure; apply requires confirm=True.

Safety rules (non-negotiable):
- System daemons are read-only here. No sudo, ever.
- Actions are reversible: Trash, never rm; bootout/disable, never delete.
- Every plan ships with an undo recipe.
- Every applied action is appended to ~/.launchd-audit/actions.jsonl.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import shutil
import subprocess

from .model import Job
from .util import expand

ALLOWED_ACTIONS = ("enable", "disable", "start", "stop", "truncate_logs", "remove")
GUARDED_SOURCES = ("launchd-system",)
ACTIONS_LOG = expand("~/.launchd-audit/actions.jsonl")


def _target(job: Job) -> str:
    return f"gui/{os.getuid()}/{job.id}"


def plan_action(job: Job, action: str) -> dict:
    """Pure planning. Returns commands / files / warnings / undo. Never mutates anything."""
    if action not in ALLOWED_ACTIONS:
        return {"error": f"unknown action '{action}' (allowed: {', '.join(ALLOWED_ACTIONS)})"}
    if job.source in GUARDED_SOURCES:
        return {"error": f"refused: '{job.id}' is a system daemon and is read-only for this tool (no sudo)."}
    if job.source == "cron" and action != "remove":
        return {"error": f"action '{action}' is not supported for cron entries; only 'remove' is."}
    if job.source != "cron" and not job.path:
        return {"error": "this job has no associated plist file to act on"}

    t = _target(job)
    commands: list[list[str]] = []
    files: list[str] = []
    warnings: list[str] = []
    undo: list[str] = []

    if action == "disable":
        commands.append(["launchctl", "disable", t])
        undo.append(f"launchctl enable {t}")
        warnings.append("Prevents the job from loading; takes effect on next boot/login for some job types.")
    elif action == "enable":
        commands.append(["launchctl", "enable", t])
        undo.append(f"launchctl disable {t}")
        warnings.append("If the job is currently unloaded you may also need to bootstrap it again.")
    elif action == "start":
        commands.append(["launchctl", "kickstart", t])
        undo.append(f"launchctl kill TERM {t}")
        warnings.append("Fails if the job is not loaded — in that case, enable it and log out/in.")
    elif action == "stop":
        commands.append(["launchctl", "kill", "TERM", t])
        undo.append(f"launchctl kickstart {t}")
        warnings.append("Sends SIGTERM to the running process; keep-alive jobs will respawn.")
    elif action == "truncate_logs":
        files = [p for p in job.output_paths if os.path.exists(p)]
        if not files:
            return {"error": f"job '{job.id}' declares no output log files (StandardOutPath/StandardErrorPath)"}
        warnings.append("Log contents will be LOST — truncation cannot be undone.")
        undo.append("Not recoverable. Re-run the job to regenerate logs.")
    elif action == "remove":
        if job.source == "cron":
            warnings.append(f"Removes cron line: {job.raw.get('spec')} {job.raw.get('command')}")
            undo.append("Re-add the line with `crontab -e`.")
        else:
            commands.append(["launchctl", "bootout", t])
            files = [job.path] if job.path else []
            trash_name = f"{os.path.basename(job.path)}.{_dt.datetime.now():%Y%m%d%H%M%S}"
            warnings.append(f"plist moves to ~/.Trash/{trash_name} — nothing is deleted.")
            undo.append(f"Move ~/.Trash/{trash_name} back to {job.path}")
            undo.append(f"launchctl bootstrap gui/{os.getuid()} {job.path}")
        if job.source == "brew-service":
            warnings.append("This looks like a brew service — `brew services stop <name>` is the cleaner path.")

    return {
        "id": job.id,
        "action": action,
        "dry_run": True,
        "commands": [" ".join(c) for c in commands],
        "files_affected": files,
        "warnings": warnings,
        "undo": undo,
    }


def apply_action(job: Job, plan: dict) -> dict:
    """Execute a confirmed plan. Returns results + undo recipe. Logs to actions.jsonl."""
    results: list[dict] = []

    try:
        if plan["action"] == "truncate_logs":
            for p in plan["files_affected"]:
                size = os.path.getsize(p)
                with open(p, "w"):
                    pass
                results.append({"step": f"truncate {p}", "ok": True, "freed_bytes": size})
        elif plan["action"] == "remove" and job.source == "cron":
            results.append(_remove_cron_line(job))
        else:
            for cmd in [c.split() for c in plan["commands"]]:
                # bootout of an already-unloaded job errors — expected, not fatal
                ok_required = cmd[0:2] != ["launchctl", "bootout"]
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                ok = r.returncode == 0 or not ok_required
                results.append({
                    "step": " ".join(cmd),
                    "ok": ok,
                    "detail": (r.stderr or r.stdout).strip()[:200] or None,
                })
            if plan["action"] == "remove" and job.path and os.path.exists(job.path):
                trash_name = f"{os.path.basename(job.path)}.{_dt.datetime.now():%Y%m%d%H%M%S}"
                trash_path = os.path.join(expand("~/.Trash"), trash_name)
                shutil.move(job.path, trash_path)
                results.append({"step": f"moved {job.path} -> {trash_path}", "ok": True})
    except Exception as e:  # noqa: BLE001
        results.append({"step": "error", "ok": False, "detail": str(e)})

    outcome = {
        "id": job.id,
        "action": plan["action"],
        "dry_run": False,
        "results": results,
        "all_ok": all(r.get("ok") for r in results),
        "undo": plan["undo"],
    }
    _log_action(outcome)
    return outcome


def _remove_cron_line(job: Job) -> dict:
    r = subprocess.run(["crontab", "-l"], capture_output=True, text=True, timeout=10)
    if r.returncode != 0:
        return {"step": "read crontab", "ok": False, "detail": r.stderr.strip()[:200]}
    spec = job.raw.get("spec")
    cmd = job.raw.get("command")
    kept = []
    removed = 0
    for line in r.stdout.splitlines():
        if spec and cmd and line.strip() == f"{spec} {cmd}".strip():
            removed += 1
            continue
        kept.append(line)
    new = "\n".join(kept) + ("\n" if kept else "")
    p = subprocess.run(["crontab", "-"], input=new, capture_output=True, text=True, timeout=10)
    if p.returncode != 0:
        return {"step": "write crontab", "ok": False, "detail": p.stderr.strip()[:200]}
    return {"step": f"removed {removed} crontab line(s)", "ok": True}


def _log_action(outcome: dict) -> None:
    try:
        os.makedirs(os.path.dirname(ACTIONS_LOG), exist_ok=True)
        with open(ACTIONS_LOG, "a") as fh:
            fh.write(json.dumps({
                "ts": _dt.datetime.now().astimezone().isoformat(timespec="seconds"),
                **outcome,
            }, default=str) + "\n")
    except OSError:
        pass
