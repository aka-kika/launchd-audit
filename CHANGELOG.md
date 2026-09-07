# Changelog

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
