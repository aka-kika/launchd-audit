# launchd-audit

> **Your Mac has a secret life. This is how you read it.**

An MCP server that turns the quiet, background layer of your Mac — the launchd jobs, cron
entries, and brew services you forgot you set up — into something visible, diagnosable,
and safely manageable.

**One-liner:** `"what's secretly running on my Mac, and is anything broken?"` —
from a 30-minute digging-around job into a one-line question.

```
$ "is anything on my mac quietly broken?"

  totals: {"jobs": 31, "running": 8, "disabled": 0, "failing": 1, "stale": 1}
  [failing] com.kika.claude-tools-ledger-audit | exit=1
```

That's the pitch. One call, the whole truth.

---

## Why this exists

Every Mac that's been alive for a while accumulates a hidden layer: agents from apps you
uninstalled months ago, cron jobs you set up "just for a test," brew services quietly
logging megabytes a day. launchd is powerful but opaque — `launchctl list` gives you a
wall of PIDs, plists are XML, and answering "is anything *wrong*?" means hand-reading a
dozen files.

launchd-audit gives that layer a voice. See [PHILOSOPHY.md](PHILOSOPHY.md) for the full
gap analysis and design principles.

## The five tools

| Tool | What it does |
|---|---|
| `list_scheduled_jobs` | Every launchd job + cron entry + brew service, plain-English schedules ("every 15 min", "daily at 03:00", "keep alive (respawn)") |
| `job_health` | **The audit.** Which jobs are failing, stale, or writing huge logs — with totals and reasons |
| `job_detail` | Full deep-dive on one job: plist (secrets masked), live launchctl state, log tails |
| `search_job_logs` | Regex search inside a job's output files, with a `since` date cutoff |
| `job_action` | The **only** mutating tool — and it's safe by construction (below) |

## Safety is in the server, not in the prompt

The mutating tool can't be misused into damage, even by a careless agent:

- **Dry-run by default.** Without `confirm=true` it only reports what *would* happen.
- **System daemons are refused.** Read-only territory, period.
- **Trash, not `rm`.** Removals land in the Trash with an undo recipe returned every time.
- **Never sudo.**
- Secrets are masked at parse time — they never leave the process.

That's also why there's no companion skill: five self-describing tools with server-side
guardrails don't need a prompt-layer manual.

## Status

**v0.2.0 — fleet-wide and battle-tested.** 40 unit tests passing, stdio smoke test green.
First real audit (2026-08-27) found 5 silently-dead `recall.*` jobs on its first run —
since fixed. Its 2026-09-07 sweep flagged the only failing job on the machine (a
drift-detector exiting 1 by design), which led to a full ledger reconcile the same day.

Registered across the whole agent fleet: Claude Code, Cursor, Grok, Goose, and the AKA
sidecar. Catalog pages live in the MCP-Catalog (`launchd-audit/`, 5 tool pages).

## Quickstart

```bash
cd launchd-audit
uv sync                        # install deps
uv run pytest -q               # 40 tests
uv run python scripts/smoke.py # e2e: spawn server, list tools, call two of them
uv run launchd-audit           # run the server on stdio (what an MCP client does)
```

## Client config

```json
{
  "mcpServers": {
    "launchd-audit": {
      "command": "uv",
      "args": [
        "--directory", "/path/to/launchd-audit",
        "run",
        "launchd-audit"
      ]
    }
  }
}
```

## Docs

| Path | What it is |
|---|---|
| [PHILOSOPHY.md](PHILOSOPHY.md) | Why it should exist — the gap, the failure modes, the design principles |
| [SPEC.md](SPEC.md) | The 5 tools — inputs, outputs, safety rules, scope |
| [EXAMPLES.md](EXAMPLES.md) | Example conversations showing the tools in action |
| [CHANGELOG.md](CHANGELOG.md) | Version history |

## Implementation notes

- **macOS only (v1).** Shells out to `launchctl`, `crontab`, plist parsing — no special system access needed.
- **Read-only by default.** Four tools never mutate. `job_action` is the sole mutation path.
- **Actions log** — every applied action appends to `~/.launchd-audit/actions.jsonl`.
- Built on `mcp` SDK 2.x (`MCPServer`, formerly FastMCP).

## Known limitations (v1)

- `/System/Library` launchd items are not scanned (hundreds of Apple-internal jobs = noise).
- System daemon runtime state is limited (reading the `system/` domain fully requires root — refused by design).
- Stale detection relies on log-file mtimes; jobs with no declared output logs are not flagged stale.
- A job in two launchctl views can surface twice in `job_health` offenders (observed once, cosmetic).
- Windows Task Scheduler / Linux systemd: same five tools would port cleanly — future.

---

*Built by Kika (aka-kika), August 2026. Private for now.*
