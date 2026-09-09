# Changelog

## 0.3.0 — 2026-09-09

First public release.

### Fixed

- Declared dependency floor was `mcp>=1.2.0` but the code imports `MCPServer`, which only
  exists in mcp 2.x. Now `mcp>=2.0.0`. Fresh installs without `uv.lock` failed at import.
- **Safety:** a brew plist under `/Library/LaunchDaemons` (from `sudo brew services`) was
  classified `brew-service` and slipped past the system-daemon guard in `job_action`. Such
  plists now stay `launchd-system`, and the guard additionally checks the plist path.
- `remove` on a plist in a directory this user cannot write (e.g. root-owned
  `/Library/LaunchAgents`) is refused at plan time instead of booting the job out and then
  failing the move to Trash.
- The Trash filename is computed once in the plan and reused by apply, so the undo recipe
  always names the real file.
- Cron `remove` matched lines byte-for-byte, so extra whitespace in the crontab meant
  "removed 0 lines" reported as success. Matching is now whitespace-normalised, and a
  zero-match run is a failure with the crontab left untouched.

### Changed

- Listing uses one `launchctl list` call for all jobs instead of one `launchctl print` per
  job. `job_detail` still calls `launchctl print` for run counts and the precise
  "never exited" state.
- Secret-looking values in `ProgramArguments` (`--token=…`, `API_KEY=…`, `--password …`)
  are redacted, in addition to `EnvironmentVariables`.
- Cron humanizer understands lists, ranges, steps and day/month names
  (`*/10 9-17 * * mon-fri` → "every 10 minutes during hours 9-17 on Mon-Fri").
- `job_health` no longer takes `since_days`; the parameter was accepted but never used.
- Job objects carry a `disabled` field. `job_detail` log entries carry `bytes`.
- Server advertises `instructions` to clients (dry-run first, confirm second).
- `search_job_logs` validates the `since` date format.

### Added

- MIT license, PyPI metadata, GitHub Actions CI (ubuntu + macOS, Python 3.11 and 3.13).
- Tests: 40 → 76 (discovery, runtime parsing, redaction, cron humanizer, removal paths).

## 0.2.0 — 2026-09-07

- Stale detection looks at sibling log files that share the job's name, not only the
  declared `StandardOutPath`/`StandardErrorPath`, so scripts that keep their own log are
  not false positives. Flagged jobs carry a `log_dir_evidence` listing.
- Test suite 35 → 40.
- Decision: no companion skill. Five self-describing tools with server-side guardrails;
  safety lives in the server, not in prompts.

## 0.1.0 — 2026-08-27

- Initial build: 5 tools (`list_scheduled_jobs`, `job_health`, `job_detail`,
  `search_job_logs`, `job_action`), 35 unit tests, stdio smoke test.
- Dry-run-first actions, Trash-not-rm, undo recipes, secrets masking, no sudo,
  system daemons read-only.
