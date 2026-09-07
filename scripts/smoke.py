"""End-to-end smoke test: spawn the server over stdio, list tools, call two of them.

Run:  uv run python scripts/smoke.py
"""

from __future__ import annotations

import asyncio
import json
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main() -> int:
    params = StdioServerParameters(command=sys.executable, args=["-m", "launchd_audit"])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            names = [t.name for t in tools.tools]
            print("tools:", names)
            assert len(names) == 5, f"expected 5 tools, got {names}"

            r = await session.call_tool("list_scheduled_jobs", {})
            data = json.loads(r.content[0].text)
            print(f"list_scheduled_jobs -> {data['totals']['jobs']} jobs, "
                  f"{data['totals']['running']} running, {len(data['errors'])} parse errors")
            for j in data["jobs"][:5]:
                print(f"  [{j['source']}] {j['id']} | {j['schedule_human']} | {j['state']}")

            r = await session.call_tool("job_health", {"since_days": 30})
            h = json.loads(r.content[0].text)
            print(f"job_health -> totals: {h['totals']}")
            print(f"  failing: {len(h['failing'])}, stale: {len(h['stale'])}, log_pressure: {len(h['log_pressure'])}")

            r = await session.call_tool("job_action", {"id": "__nonexistent__", "action": "disable"})
            guard = json.loads(r.content[0].text)
            assert "error" in guard, "expected an error for unknown job id"
            print("job_action guard ok:", guard["error"])

    print("\nSMOKE OK")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
