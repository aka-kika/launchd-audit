# Tool spec

One MCP server (stdio), five tools. All tools return a single JSON block as text content.

## Shared conventions

- Timestamps: ISO 8601 with local offset (e.g. `2026-08-27T03:00:02+03:00`).
- Schedules always include a `*_human` string ("every 15 min", "daily at 03:00", "at login", "keep alive (respawn)").
- Every job object carries the same core shape:

```json
{
  "id": "com.example.backup",
  "source": "launchd-user | launchd-system | cron | brew-service",
  "state": "running | idle | disabled | unknown",
  "last_run": "2026-08-27T03:00:02+03:00",
  "last_exit": 0
}
```

- `last_exit` is `null` when the server has never observed a run.
- Anything that can't be parsed goes into an `errors` array with `{path, reason}` — never silently dropped, never a failed call.

---

## 1. `list_scheduled_jobs`

Every job on the machine, in one call.

**Input**

```json
{
  "scope": "all | user | system | cron | brew-service",   // default "all"
  "include_disabled": true                                 // default true
}
```

**Output**

```json
{
  "jobs": [
    {
      "id": "com.example.backup",
      "source": "launchd-user",
      "path": "~/Library/LaunchAgents/com.example.backup.plist",
      "program": "/usr/local/bin/backup.sh",
      "schedule_human": "daily at 03:00",
      "state": "idle",
      "running_pid": null,
      "last_run": "2026-08-27T03:00:02+03:00",
      "last_exit": 0,
      "output_paths": ["~/Library/Logs/backup.out", "~/Library/Logs/backup.err"]
    }
  ],
  "totals": { "jobs": 42, "running": 3, "disabled": 7 },
  "errors": []
}
```

**Sources scanned:** `~/Library/LaunchAgents`, `/Library/LaunchAgents`, `/Library/LaunchDaemons`, `crontab -l` (+ `/etc/cron.d`, `/etc/crontab`), `brew services list`.

---

## 2. `job_health` — the audit

The headline tool. Answer: *what's rotting?*

**Input**

```json
{ "since_days": 30 }   // optional window for "stale" detection
```

**Output**

```json
{
  "totals": { "jobs": 42, "running": 3, "disabled": 7, "failing": 2, "stale": 5 },
  "failing": [
    {
      "id": "com.vendor.sync",
      "consecutive_failures": 12,
      "last_error_excerpt": "curl: (6) Could not resolve host: sync.vendor.example"
    }
  ],
  "stale": [
    { "id": "com.example.backup", "expected_cadence": "daily", "days_since_last_run": 41 }
  ],
  "log_pressure": [
    { "id": "com.vendor.analytics", "output_path": "~/Library/Logs/analytics.out", "bytes": 2147483648, "last_modified": "2026-08-27T14:02:11+03:00" }
  ],
  "notes": [
    "3 jobs share the same binary — likely redundant",
    "com.vendor.sync has not succeeded since 2026-07-30"
  ]
}
```

**Definitions**

- `failing` — recent runs exited non-zero, or launchd reports repeated spawn failures.
- `stale` — a calendar/interval job that hasn't run in more than 3× its expected cadence.
- `log_pressure` — job output files > 100 MB, or grown significantly inside `since_days`.

---

## 3. `job_detail`

Everything about one job.

**Input**

```json
{ "id": "com.example.backup" }
```

**Output**

```json
{
  "id": "com.example.backup",
  "plist_raw": { "Label": "com.example.backup", "ProgramArguments": ["...", "..."], "StartCalendarInterval": { "Hour": 3 } },
  "schedule_human": "daily at 03:00",
  "launchctl_print": { "state": "waiting", "pid": null, "spawned": 41, "last_exit_reason": "exited", "last_exit_status": 0 },
  "ownership": { "kind": "brew-service", "hint": "installed via `brew services start backup-tool`" },
  "environment": { "TOKEN": "***", "PATH_NOTE": "1 key masked" },
  "logs": [
    { "path": "~/Library/Logs/backup.out", "bytes": 524288, "last_modified": "2026-08-27T03:00:02+03:00", "tail": ["...last 20 lines..."] }
  ]
}
```

**Notes:** `environment` is always masked (values → `"***"`). `ownership` is best-effort inference (brew service, app bundle, hand-rolled).

---

## 4. `search_job_logs`

Regex search inside a job's output files.

**Input**

```json
{
  "id": "com.vendor.sync",
  "pattern": "error|fail",   // case-insensitive regex
  "since": "2026-08-01",     // optional
  "limit": 50                // default 50
}
```

**Output**

```json
{
  "matches": [
    { "ts": "2026-08-27T03:00:04+03:00", "file": "~/Library/Logs/sync.err", "line": "curl: (6) Could not resolve host: sync.vendor.example" }
  ],
  "truncated": false
}
```

---

## 5. `job_action` — the only mutating tool (protected)

**Input**

```json
{
  "id": "com.vendor.analytics",
  "action": "enable | disable | start | stop | truncate_logs | remove",
  "confirm": false
}
```

**Behavior**

- `confirm: false` (default) → **dry-run preview**: the exact commands it would run and files it would touch. Nothing happens.
- `confirm: true` → applies, then returns the result **plus an undo recipe** (e.g. "re-enable with `launchctl bootstrap ...`").
- `truncate_logs` → truncates output files to zero, keeps the files.
- `remove` → unload + move the plist to **Trash** (never `rm`). The undo recipe names the file in Trash.

**Safety rules**

- Read-only by default; this is the sole mutation path.
- All writes are reversible (Trash, not deletion; truncate, not delete).
- System daemons (`launchd-system`) are **read-only for this tool** — listable, never modified.
- No sudo, ever.
- Secret values in `EnvironmentVariables` are masked in every response, including previews.

---

## Out of scope (v1)

- Windows Task Scheduler, Linux systemd (the same five tools port cleanly later).
- `at` queue, `periodic`.
- Power/CPU correlation ("which job is draining my battery") — a v2 idea, pairs well with the telemetry-timeline tool.
