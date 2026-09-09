# Tool spec

One MCP server (stdio), five tools. Every tool returns a single JSON object as text content. This document describes what the code returns today; if it disagrees with the code, the code wins and this is a bug.

## Shared conventions

- Timestamps are ISO 8601 with local offset (e.g. `2026-08-27T03:00:02+03:00`).
- Every job carries the same core shape:

```json
{
  "id": "com.example.backup",
  "source": "launchd-user | launchd-system | cron | brew-service",
  "path": "/Users/me/Library/LaunchAgents/com.example.backup.plist",
  "program": "/usr/local/bin/backup --full",
  "schedule_human": "daily at 03:00",
  "state": "running | idle | disabled | not-loaded | scheduled",
  "disabled": false,
  "running_pid": null,
  "last_exit": 0,
  "runs": null,
  "output_paths": ["/Users/me/Library/Logs/backup.out"]
}
```

- `id` is the launchd `Label`. Cron entries get `cron:<origin>:<line>`, e.g. `cron:crontab:3` or `cron:/etc/cron.d/php:14`.
- `source`: `launchd-user` for `~/Library/LaunchAgents` and `/Library/LaunchAgents`; `launchd-system` for `/Library/LaunchDaemons`; `brew-service` for `homebrew.mxcl.*` plists in the user domain; `cron` for crontab lines.
- `state`: `running` (has a PID), `idle` (loaded, not running), `not-loaded`, `disabled` (`launchctl print-disabled` override or plist `Disabled` key), `scheduled` (cron: no live state exists).
- `last_exit` comes from `launchctl list`. Negative means killed by that signal. `null` when the job is not loaded. `launchctl list` reports 0 for a job that has never run; `job_detail` refines this to `null` using `launchctl print`.
- `runs` is `null` in listings and filled by `job_detail`.
- `program` and the plist's `ProgramArguments` are redacted: values of secret-looking flags and `KEY=value` pairs become `***`.
- Anything that cannot be parsed goes into an `errors` array of `{path, reason}`. A call never fails because one plist is broken.

---

## 1. `job_health`

The audit. Answers: *what is rotting?*

**Input:** none.

**Output**

```json
{
  "totals": { "jobs": 42, "running": 3, "disabled": 7, "failing": 2, "stale": 1 },
  "failing": [
    { "id": "com.vendor.sync", "last_exit": 1, "state": "idle", "note": "last observed exit was non-zero" },
    { "id": "com.example.agent", "last_exit": null, "state": "not-loaded", "note": "keep-alive job is not loaded" }
  ],
  "stale": [
    {
      "id": "com.example.backup",
      "expected_cadence": "daily at 03:00",
      "days_since_last_evidence": 41.2,
      "note": "suspected stale: declared/name-matched log evidence is older than 3x the expected cadence — check 'log_dir_evidence' for a fresh file the script may write to under another name",
      "log_dir_evidence": [
        { "path": "/Users/me/Library/Logs/backup.out", "bytes": 1204, "last_modified": "2026-07-18T03:00:02+03:00" }
      ]
    }
  ],
  "log_pressure": [
    { "id": "com.vendor.analytics", "output_path": "/Users/me/Library/Logs/analytics.out", "bytes": 2147483648, "human": "2.0 GB", "last_modified": "2026-08-27T14:02:11+03:00" }
  ],
  "notes": ["3 jobs share the same program: /usr/local/bin/sync"],
  "errors": []
}
```

**Definitions**

- `failing`: a non-cron job whose last exit was non-zero and is not currently running, or a `KeepAlive` job that is not loaded.
- `stale`: a launchd job with a computable cadence whose newest log evidence is older than `max(3 × cadence, 1 day)`. Evidence is the declared `StandardOutPath`/`StandardErrorPath` plus sibling files in the same directory whose name matches the job's label. Jobs with no evidence files are never flagged.
- `log_pressure`: a declared output file of 100 MB or more.
- `notes`: programs shared by more than one job.

---

## 2. `list_scheduled_jobs`

**Input**

```json
{
  "scope": "all | user | system | cron | brew-service",
  "include_disabled": true
}
```

`scope` defaults to `all`. `user` includes `brew-service`.

**Output**

```json
{
  "jobs": [ { "...core job shape..." } ],
  "totals": { "jobs": 42, "running": 3, "disabled": 7 },
  "errors": []
}
```

**Sources scanned:** `~/Library/LaunchAgents`, `/Library/LaunchAgents`, `/Library/LaunchDaemons`, `crontab -l` (+ `/etc/cron.d`, `/etc/crontab`). Brew services are the `homebrew.mxcl.*` plists in `~/Library/LaunchAgents`; `brew` is not invoked.

**Cost:** two `launchctl` calls per invocation (`list` and `print-disabled`), regardless of job count.

---

## 3. `job_detail`

**Input:** `{ "id": "com.example.backup" }`

**Output** (core job shape plus):

```json
{
  "plist": { "Label": "com.example.backup", "ProgramArguments": ["/usr/local/bin/backup", "--token=***"], "EnvironmentVariables": { "API_KEY": "***" }, "StartCalendarInterval": { "Hour": 3 } },
  "cron": null,
  "launchctl_print": { "state": "waiting", "runs": "41", "last exit code": "0", "path": "..." },
  "environment": { "masked_keys": ["API_KEY"], "note": "values are never shown" },
  "logs": [
    { "path": "/Users/me/Library/Logs/backup.out", "exists": true, "bytes": 524288, "tail": ["...last 20 lines..."] }
  ],
  "errors": []
}
```

For cron entries `plist` and `launchctl_print` are `null` and `cron` is `{ "spec": "0 3 * * *", "command": "...", "user": null }`.

---

## 4. `search_job_logs`

**Input**

```json
{
  "id": "com.vendor.sync",
  "pattern": "error|fail",
  "since": "2026-08-01",
  "limit": 50
}
```

`pattern` is a case-insensitive regex. `since` is optional, `YYYY-MM-DD`; lines whose first 64 characters contain an older date are skipped, lines with no date are always included. Only the last 5 MB of each file is read.

**Output**

```json
{
  "matches": [ { "ts": "2026-08-27", "file": "/Users/me/Library/Logs/sync.err", "line": "curl: (6) Could not resolve host" } ],
  "truncated": false,
  "errors": []
}
```

---

## 5. `job_action`

The only mutating tool.

**Input**

```json
{
  "id": "com.vendor.analytics",
  "action": "enable | disable | start | stop | truncate_logs | remove",
  "confirm": false
}
```

**Dry-run output** (`confirm` false, the default):

```json
{
  "id": "com.vendor.analytics",
  "action": "remove",
  "dry_run": true,
  "commands": ["launchctl bootout gui/501/com.vendor.analytics"],
  "files_affected": ["/Users/me/Library/LaunchAgents/com.vendor.analytics.plist"],
  "warnings": ["plist moves to /Users/me/.Trash/com.vendor.analytics.plist.20260909120000 — nothing is deleted."],
  "undo": [
    "Move /Users/me/.Trash/com.vendor.analytics.plist.20260909120000 back to /Users/me/Library/LaunchAgents/com.vendor.analytics.plist",
    "launchctl bootstrap gui/501 /Users/me/Library/LaunchAgents/com.vendor.analytics.plist"
  ],
  "trash_path": "/Users/me/.Trash/com.vendor.analytics.plist.20260909120000",
  "next_step": "call job_action again with confirm=true to apply"
}
```

**Applied output** (`confirm` true):

```json
{
  "id": "com.vendor.analytics",
  "action": "remove",
  "dry_run": false,
  "results": [
    { "step": "launchctl bootout gui/501/com.vendor.analytics", "ok": true, "detail": null },
    { "step": "moved /Users/me/Library/LaunchAgents/com.vendor.analytics.plist -> /Users/me/.Trash/com.vendor.analytics.plist.20260909120000", "ok": true }
  ],
  "all_ok": true,
  "undo": ["..."],
  "errors": []
}
```

A refused action returns `{ "error": "..." }` and nothing else.

**Actions**

| Action | launchd job | cron entry |
|---|---|---|
| `enable` | `launchctl enable gui/<uid>/<label>` | refused |
| `disable` | `launchctl disable gui/<uid>/<label>` | refused |
| `start` | `launchctl kickstart gui/<uid>/<label>` | refused |
| `stop` | `launchctl kill TERM gui/<uid>/<label>` | refused |
| `truncate_logs` | declared output files truncated to zero bytes (kept, not deleted) | refused |
| `remove` | `launchctl bootout`, then the plist moves to `~/.Trash/<name>.<timestamp>` | the matching line is removed from the user crontab; no match is a failure and the crontab is left untouched |

**Safety rules**

- Read-only by default; this is the sole mutation path.
- `launchd-system` jobs and any plist under `/Library/LaunchDaemons` are refused, whatever their label.
- `remove` is refused at plan time when the plist's directory is not writable by the current user.
- No sudo, ever.
- Nothing is deleted: Trash for plists, truncation for logs. `truncate_logs` is the one action whose contents cannot be recovered; the plan says so.
- Every applied action is appended to `~/.launchd-audit/actions.jsonl` with a timestamp.

---

## Out of scope

- Windows Task Scheduler, Linux systemd.
- `at` queue, `periodic`.
- `/System/Library` launchd items.
- Power/CPU correlation ("which job is draining my battery").
