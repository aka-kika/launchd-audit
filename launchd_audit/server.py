"""The MCP server: five tools over stdio. Read-only by default; job_action is the only mutation path."""

from __future__ import annotations

import json
import os
import re
from typing import Literal

from mcp.server.mcpserver import MCPServer

from . import __version__, actions, discovery, health, runtime
from .model import Job
from .util import tail_text

INSTRUCTIONS = """\
launchd-audit inspects macOS background jobs (launchd agents/daemons, cron, brew services).
Start with job_health for "is anything broken?", list_scheduled_jobs for "what runs here?".
Four tools are read-only. job_action is the only tool that changes anything: it is a
dry-run unless confirm=true, so always show the user the dry-run plan (commands, files,
warnings, undo) and get their OK before calling it again with confirm=true.
System daemons are never modified. Nothing is deleted; removed plists go to Trash.
Environment variable values and secret-looking program arguments are masked."""

mcp = MCPServer("launchd-audit", instructions=INSTRUCTIONS, version=__version__)

Scope = Literal["all", "user", "system", "cron", "brew-service"]


def _collect_jobs(scope: str = "all", include_disabled: bool = True) -> tuple[list[Job], list[dict]]:
    errors: list[dict] = []
    jobs = discovery.scan_launchd(errors) + discovery.scan_cron(errors)

    if scope == "user":
        jobs = [j for j in jobs if j.source in ("launchd-user", "brew-service")]
    elif scope == "system":
        jobs = [j for j in jobs if j.source == "launchd-system"]
    elif scope == "cron":
        jobs = [j for j in jobs if j.source == "cron"]
    elif scope == "brew-service":
        jobs = [j for j in jobs if j.source == "brew-service"]

    # Two launchctl calls for the whole listing, however many jobs there are.
    disabled_overrides = runtime.launchctl_disabled_overrides()
    loaded = runtime.launchctl_list()
    for j in jobs:
        runtime.merge_runtime(j, disabled_overrides, loaded)

    if not include_disabled:
        jobs = [j for j in jobs if j.state != "disabled" and not j.disabled]
    return jobs, errors


def _find_job(job_id: str) -> tuple[Job | None, list[dict]]:
    jobs, errors = _collect_jobs("all", True)
    for j in jobs:
        if j.id == job_id:
            return j, errors
    return None, errors


def _dumps(payload: dict) -> str:
    return json.dumps(payload, indent=2, default=str)


@mcp.tool()
def list_scheduled_jobs(scope: Scope = "all", include_disabled: bool = True) -> str:
    """List every scheduled job on this Mac (launchd, cron, brew services) with plain-English
    schedules and current state. scope: all|user|system|cron|brew-service."""
    jobs, errors = _collect_jobs(scope, include_disabled)
    payload = {
        "jobs": [j.to_dict() for j in jobs],
        "totals": {
            "jobs": len(jobs),
            "running": sum(1 for j in jobs if j.state == "running"),
            "disabled": sum(1 for j in jobs if j.disabled or j.state == "disabled"),
        },
        "errors": errors,
    }
    return _dumps(payload)


@mcp.tool()
def job_health() -> str:
    """The audit: which jobs are failing (non-zero exit, keep-alive not loaded), stale (log
    evidence older than 3x their cadence), or writing huge logs (>100 MB). Start here."""
    jobs, errors = _collect_jobs("all", True)
    result = health.audit(jobs)
    result["errors"] = errors
    return _dumps(result)


@mcp.tool()
def job_detail(id: str) -> str:
    """Everything about one job: plist contents (secrets masked), live launchctl state, log tails."""
    job, errors = _find_job(id)
    if job is None:
        return _dumps({"error": f"no job with id '{id}'", "errors": errors})
    info = runtime.launchctl_print(job.id) if job.source != "cron" else None
    if info:
        runtime.merge_print_details(job, info)
    env = job.raw.get("EnvironmentVariables")
    payload = {
        **job.to_dict(),
        "plist": job.raw if job.source != "cron" else None,
        "cron": job.raw if job.source == "cron" else None,
        "launchctl_print": info,
        "environment": (
            {"masked_keys": sorted(env.keys()), "note": "values are never shown"}
            if isinstance(env, dict) and env else None
        ),
        "logs": [
            {
                "path": p,
                "exists": os.path.exists(p),
                "bytes": os.path.getsize(p) if os.path.exists(p) else None,
                "tail": tail_text(p, 8 * 1024).splitlines()[-20:] if os.path.exists(p) else None,
            }
            for p in job.output_paths
        ],
        "errors": errors,
    }
    return _dumps(payload)


@mcp.tool()
def search_job_logs(id: str, pattern: str, since: str | None = None, limit: int = 50) -> str:
    """Regex-search a job's output log files (case-insensitive). `since` is an ISO date
    (YYYY-MM-DD); lines whose leading date is older are skipped, lines without a parseable
    date are always included."""
    job, errors = _find_job(id)
    if job is None:
        return _dumps({"error": f"no job with id '{id}'", "errors": errors})
    if not job.output_paths:
        return _dumps({"error": f"job '{id}' declares no output log files", "errors": errors})
    try:
        rx = re.compile(pattern, re.IGNORECASE)
    except re.error as e:
        return _dumps({"error": f"bad regex: {e}"})
    if since and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", since):
        return _dumps({"error": "since must be an ISO date like 2026-08-01"})

    date_rx = re.compile(r"(\d{4}-\d{2}-\d{2})")
    matches: list[dict] = []
    for path in job.output_paths:
        text = tail_text(path)
        for line in text.splitlines():
            if not rx.search(line):
                continue
            m = date_rx.search(line[:64])
            ts = m.group(1) if m else None
            if since and ts and ts < since:
                continue
            matches.append({"ts": ts, "file": path, "line": line[:400]})
            if len(matches) >= limit:
                break
        if len(matches) >= limit:
            break
    return _dumps({"matches": matches, "truncated": len(matches) >= limit, "errors": errors})


@mcp.tool()
def job_action(
    id: str,
    action: Literal["enable", "disable", "start", "stop", "truncate_logs", "remove"],
    confirm: bool = False,
) -> str:
    """The ONLY mutating tool, dry-run by default. Set confirm=true to actually apply.
    System daemons are refused. Removals go to Trash with an undo recipe. Never uses sudo."""
    job, errors = _find_job(id)
    if job is None:
        return _dumps({"error": f"no job with id '{id}'", "errors": errors})
    plan = actions.plan_action(job, action)
    if plan.get("error"):
        return _dumps(plan)
    if not confirm:
        plan["next_step"] = "call job_action again with confirm=true to apply"
        return _dumps(plan)
    result = actions.apply_action(job, plan)
    result["errors"] = errors
    return _dumps(result)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
