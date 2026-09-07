# Example conversations

Five realistic sessions. `→` marks the tool call(s) behind each answer.

---

## 1. "What scheduled jobs are running on this Mac?"

→ `list_scheduled_jobs`

> 42 jobs. 3 running right now, 7 disabled. Notable: `com.example.backup` (daily 03:00), `com.vendor.analytics` (keep alive, **2 GB of logs**), and 5 brew services. Want the health audit?

---

## 2. "My battery drains overnight. Anything running at night?"

→ `job_health` + `list_scheduled_jobs` (filter: calendar schedules 22:00–07:00)

> Two jobs run at night: `com.example.backup` at 03:00 (healthy) and `com.vendor.sync` at 02:30 — it's **failing every run**, retrying for 12 days straight, and burning CPU on failed network calls. That's your 2–3am heat. Want me to disable it? (dry-run first)

---

## 3. "A script emails me at 3am and I have no idea what it is."

→ `list_scheduled_jobs` (filter: "daily at 03:00") → `job_detail`

> It's `com.mystery.report` in `~/Library/LaunchAgents` — a bash script pointing at `~/scripts/weekly-report.sh`, which calls a Gmail API with a token (masked: `***`) set in its environment. It's yours, added 2024-11-03. Kill it? I'll move the plist to Trash — undo recipe included.

---

## 4. "Did my backup actually run yesterday?"

→ `job_detail`

> Yes — `com.example.backup` ran 2026-08-27 at 03:00:02, exit code 0, log tail says "backup complete, 4.2 GB". First successful run in 3 weeks; it was failing with "disk full" before that.

---

## 5. "Clean up the log files from jobs I don't use anymore."

→ `job_health` (log_pressure) → for each: `job_detail` → `job_action {action: "truncate_logs"}` dry-run → user confirms → apply

> Found 4 jobs writing 6.1 GB of logs total. Biggest: `com.vendor.analytics` (2 GB, and the job itself fails every run — logs are pure garbage). Preview: I'd truncate 4 files, freeing ~5.9 GB. Nothing else touches. Confirm?
