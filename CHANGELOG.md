# Changelog

## Unreleased

- **Fix:** declared dependency floor was `mcp>=1.2.0` but the code imports `MCPServer`,
  which only exists in mcp 2.x. Now `mcp>=2.0.0`. Fresh installs without `uv.lock`
  would have failed at import.
- **Fix (safety):** a brew plist under `/Library/LaunchDaemons` (from `sudo brew services`)
  was classified `brew-service` and slipped past the system-daemon guard in `job_action`.
  Such plists now stay `launchd-system`, and the guard additionally checks the plist path.
- **Fix:** `remove` on a plist in a directory this user cannot write (e.g. root-owned
  `/Library/LaunchAgents`) is refused at plan time instead of booting the job out and then
  failing the move to Trash.
- **Fix:** the Trash filename is computed once in the plan and reused by apply, so the undo
  recipe always names the real file.
- **Fix:** cron `remove` matched lines byte-for-byte, so any extra whitespace in the crontab
  meant "removed 0 lines" reported as success. Matching is now whitespace-normalised, and a
  zero-match run is reported as a failure with the crontab left untouched.
- Docs: brew services are detected from `homebrew.mxcl.*` plists; `brew services list`
  was never called.
- Tests: 40 → 58 (discovery, runtime parsing, cron removal, Trash path, guards).

## 0.2.0 — 2026-09-07

- **Fleet rollout.** Registered across all five agent surfaces: Claude Code
  (`~/.claude.json`), Cursor (`~/.cursor/mcp.json`), Grok (`~/.grok/config.toml`, since
  2026-08-27), Goose (`~/.config/goose/config.yaml`, dormant entry enabled), and the AKA
  sidecar (`POST /api/mcp/servers`, id 106, connected).
- **Catalog pages.** 5 per-tool pages logged into the MCP-Catalog from a live stdio
  `tools/list` probe; servers.conf + README + INDEX updated.
- **Test suite: 35 → 40** (schedule humanizers, masking, audit logic, action guards).
- **Born as a test, promoted on merit.** Started 2026-08-27 as a Qwen-model exercise;
  a full health check 2026-09-07 (40/40 tests, smoke green, live audit) earned it a
  permanent slot. Its own `job_health` sweep flagged the only failing job on the Mac —
  a drift detector exiting 1 by design — which triggered a full ledger reconcile.
- **Decision: no companion skill.** Five self-describing tools with server-side
  guardrails; safety lives in the server, not in prompts.
- Published to private GitHub repo (aka-kika/launchd-audit).

## 0.1.0 — 2026-08-27

- Initial build: 5 tools (`list_scheduled_jobs`, `job_health`, `job_detail`,
  `search_job_logs`, `job_action`), 35 unit tests, stdio smoke test.
- First real audit run found 5 silently-dead `recall.*` jobs (dead ~5 weeks).
- Dry-run-first actions, Trash-not-rm, undo recipes, secrets masking, no sudo,
  system daemons read-only.
