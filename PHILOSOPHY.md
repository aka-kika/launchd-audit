# Why this should exist

## The layer this tool lives in

launchd and cron are the **background schedulers** of your computer — the thing that makes programs run automatically:

- **cron** — "run this command every day at 3am."
- **launchd** — macOS's newer, fancier version of the same idea: "run this script on every login," or "start this server when I boot the Mac," or "restart it if it crashes."

You almost certainly have a bunch of these running *right now* without thinking about it: backup scripts, analytics pings, a dev server that auto-starts, a tool that syncs data.

## The problem: they're invisible, and they rot

- You (or a colleague, or a tool you installed 6 months ago) set one up, forgot about it, and it's been silently running — or *silently failing* — ever since.
- Nothing shows up. No notification. The log goes to a file nobody reads.
- You find out about it the bad way: your Mac runs hot at night, your battery drains, a disk fills up with logs, or a script keeps emailing you at 3am and you have *no idea where it's coming from.*

## The gap in the MCP world

Everyone's building MCP tools for *visible, loud* stuff — GitHub, databases, web browsers, chat apps. Almost nobody builds one for the **quiet background layer** that actually degrades your machine over time — because it's unglamorous and nobody's thinking about it. That's exactly the kind of gap where a small, sharp tool wins.

## What it looks like in practice

You just ask your AI: *"what scheduled jobs are running on this machine?"*

And it:

1. **Lists everything** — every launchd job and cron entry, with plain-English descriptions.
2. **Shows health** — last time it ran, did it succeed or crash, how long it's been quiet.
3. **Spots the rot** — "this job hasn't run in 40 days," "this one crashes every single time," "this one is logging 2GB a week."
4. **Can act** — pause, clean up, or fix one, with your OK.

**In one sentence:** it turns "what's secretly running on my Mac, and is anything broken?" from a 30-minute digging-around job into a one-line question.

## Design principles

1. **Read-first.** Four of the five tools are read-only. Mutation is the exception, and it demands explicit confirmation.
2. **Plain English.** Schedules as "daily at 03:00", not `StartCalendarInterval → {Hour: 3, Minute: 0}`.
3. **Actions are reversible.** Unload + move to Trash, never `rm`.
4. **No secret leakage.** `EnvironmentVariables` in plists get masked before they ever reach an LLM context.
5. **Honest failure.** A plist that won't parse is reported, not silently dropped.
