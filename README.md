# launchd-audit

MCP server for macOS that lists launchd jobs, cron entries, and brew services in plain English, flags the ones that are failing or stale, and can act on them without `rm` or sudo.

Ask an agent: *what's running in the background on this Mac, and is anything broken?*

```
totals: {"jobs": 31, "running": 8, "disabled": 0, "failing": 1, "stale": 1}
[failing] com.example.drift-check | exit=1
[stale]   com.example.backup      | daily at 03:00, no evidence for 41 days
```

macOS only. Python 3.11+. MIT.

## Why

A machine that has been alive for a while accumulates agents from apps you uninstalled, cron lines from a test, brew services that log megabytes a day. `launchctl list` is a wall of PIDs. Plists are XML. Answering "is anything wrong?" means reading a dozen files by hand.

Four of the five tools are read-only. Mutation is one tool, dry-run by default. Design notes live in [PHILOSOPHY.md](PHILOSOPHY.md). Tool contracts live in [SPEC.md](SPEC.md).

## Tools

| Tool | Role |
|---|---|
| `job_health` | The audit. Failing, stale, or writing huge logs, with totals and reasons. Start here. |
| `list_scheduled_jobs` | Every launchd job, cron entry, and brew service. Schedules as "every 15 minutes", "daily at 03:00", "keep alive (respawn)". |
| `job_detail` | One job: plist (secrets masked), live `launchctl` state, log tails. |
| `search_job_logs` | Regex search in that job's output files, optional `since` date. |
| `job_action` | The only mutating tool. Dry-run unless `confirm=true`. |

Sources scanned: `~/Library/LaunchAgents`, `/Library/LaunchAgents`, `/Library/LaunchDaemons`, `crontab -l` plus `/etc/cron.d` and `/etc/crontab`. Brew services are recognised by their `homebrew.mxcl.*` plists in `~/Library/LaunchAgents`; `brew` itself is never called. `/System/Library` is skipped on purpose.

## Safety

Guardrails are in the server, not in a companion skill or prompt.

- **Dry-run by default.** Without `confirm=true`, `job_action` only reports what it would run: commands, files, warnings, and an undo recipe.
- **System daemons are listable and never modified.** Anything in `/Library/LaunchDaemons` is refused, whatever it is called.
- **Nothing is deleted.** `remove` unloads the plist and moves it to Trash. Every applied action returns an undo recipe.
- **No sudo.** A plist the current user cannot move is refused up front, not half-removed.
- **Secrets are masked at parse time.** `EnvironmentVariables` values never leave the process. Secret-looking `ProgramArguments` (`--token=…`, `API_KEY=…`, `--password …`) are redacted too. Masking is a heuristic: a secret hidden in a plain positional argument or inside a script the job runs is not covered.
- **Every applied action is appended** to `~/.launchd-audit/actions.jsonl`.

## Install

Requires macOS, Python 3.11+, and [uv](https://docs.astral.sh/uv/). No clone needed: `uvx` fetches and runs the server straight from GitHub.

### Claude Code

```bash
claude mcp add launchd-audit -- uvx --from git+https://github.com/aka-kika/launchd-audit launchd-audit
```

### Claude Desktop, Cursor, and other JSON-configured clients

```json
{
  "mcpServers": {
    "launchd-audit": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/aka-kika/launchd-audit", "launchd-audit"]
    }
  }
}
```

Pin a release with `git+https://github.com/aka-kika/launchd-audit@v0.3.0`.

### From a local checkout

```bash
git clone https://github.com/aka-kika/launchd-audit.git
cd launchd-audit
uv sync
uv run pytest -q
uv run python scripts/smoke.py   # spawns the server over stdio and calls the read-only tools
```

Then point the client at the checkout:

```json
{
  "mcpServers": {
    "launchd-audit": {
      "command": "uv",
      "args": ["--directory", "/path/to/launchd-audit", "run", "launchd-audit"]
    }
  }
}
```

## Use

Ask the client something like:

- "What scheduled jobs are on this Mac?"
- "Is anything quietly failing?"
- "Did the backup run yesterday?"
- "Preview disabling `com.vendor.sync`."

Worked conversations are in [EXAMPLES.md](EXAMPLES.md).

## Limitations

- `/System/Library` launchd items are not scanned.
- Full `system/` domain runtime state needs root. Refused by design, so system daemon state shows as `not-loaded` and `last_exit` is unknown.
- Stale detection uses log-file mtimes. Jobs with no declared output logs are not flagged stale.
- `last_exit` in listings comes from `launchctl list`, which reports 0 for a job that has never run. `job_detail` uses `launchctl print` and reports `null` in that case.
- Cron entries have no live state (macOS cron does not expose one). Only `remove` is supported for them.
- Not Windows Task Scheduler. Not Linux systemd.

## Docs

| File | Contents |
|---|---|
| [PHILOSOPHY.md](PHILOSOPHY.md) | Why it exists |
| [SPEC.md](SPEC.md) | Inputs, outputs, safety rules |
| [EXAMPLES.md](EXAMPLES.md) | Five example sessions |
| [CHANGELOG.md](CHANGELOG.md) | Version history |

## License

[MIT](LICENSE).
