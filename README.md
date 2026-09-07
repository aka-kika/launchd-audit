# launchd-audit

MCP server for macOS that lists launchd jobs, cron entries, and brew services in plain English, flags the ones that are failing or stale, and can act on them without `rm` or sudo.

Ask an agent: *what's running in the background on this Mac, and is anything broken?*

```
totals: {"jobs": 31, "running": 8, "disabled": 0, "failing": 1, "stale": 1}
[failing] com.kika.claude-tools-ledger-audit | exit=1
```

v0.2.0. Private. macOS only. Python 3.11+.

## Why

A machine that has been alive for a while accumulates agents from apps you uninstalled, cron lines from a test, brew services that log megabytes a day. `launchctl list` is a wall of PIDs. Plists are XML. Answering "is anything wrong?" means reading a dozen files by hand.

Four of the five tools are read-only. Mutation is one tool, dry-run by default. Design notes live in [PHILOSOPHY.md](PHILOSOPHY.md). Tool contracts live in [SPEC.md](SPEC.md).

## Tools

| Tool | Role |
|---|---|
| `list_scheduled_jobs` | Every launchd job, cron entry, and brew service. Schedules as "every 15 min", "daily at 03:00", "keep alive (respawn)". |
| `job_health` | The audit. Failing, stale, or writing huge logs — with totals and reasons. |
| `job_detail` | One job: plist (secrets masked), live `launchctl` state, log tails. |
| `search_job_logs` | Regex search in that job's output files, optional `since` date. |
| `job_action` | The only mutating tool. Dry-run unless `confirm=true`. |

Sources scanned: `~/Library/LaunchAgents`, `/Library/LaunchAgents`, `/Library/LaunchDaemons`, `crontab -l` plus `/etc/cron.d` and `/etc/crontab`, `brew services list`. `/System/Library` is skipped on purpose.

## Safety

Guardrails are in the server, not in a companion skill.

- Dry-run by default. Without `confirm=true`, `job_action` only reports what it would run.
- System daemons are listable and never modified.
- `remove` unloads the plist and moves it to Trash. Every applied action returns an undo recipe.
- No sudo.
- `EnvironmentVariables` are masked at parse time. Values never leave the process.
- Applied actions append to `~/.launchd-audit/actions.jsonl`.

## Install

Requires macOS, Python 3.11+, and [uv](https://docs.astral.sh/uv/).

```bash
git clone git@github.com:aka-kika/launchd-audit.git
cd launchd-audit
uv sync
uv run pytest -q
uv run python scripts/smoke.py
```

Run the server on stdio:

```bash
uv run launchd-audit
```

## Client config

Point any MCP client at the repo directory:

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

Then ask the client something like:

- "What scheduled jobs are on this Mac?"
- "Is anything quietly failing?"
- "Did the backup run yesterday?"
- "Preview disabling `com.vendor.sync`."

Worked conversations are in [EXAMPLES.md](EXAMPLES.md).

## Limitations (v1)

- `/System/Library` launchd items are not scanned.
- Full `system/` domain runtime state needs root. Refused by design, so system daemon state is partial.
- Stale detection uses log-file mtimes. Jobs with no declared output logs are not flagged stale.
- A job visible in two `launchctl` views can appear twice in `job_health` offenders.
- Not Windows Task Scheduler. Not Linux systemd.

## Docs

| File | Contents |
|---|---|
| [PHILOSOPHY.md](PHILOSOPHY.md) | Why it exists |
| [SPEC.md](SPEC.md) | Inputs, outputs, safety rules |
| [EXAMPLES.md](EXAMPLES.md) | Five example sessions |
| [CHANGELOG.md](CHANGELOG.md) | Version history |

Built August–September 2026. Last reviewed 2026-09-07.
