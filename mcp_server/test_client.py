"""A tiny MCP client that starts the server, lists its tools and calls each one.

This is exactly what the agent will do on Day 4, minus the LLM.

Usage:
    python -m mcp_server.test_client
    python -m mcp_server.test_client "E1 6AN"      # try your own postcode
"""

from __future__ import annotations

import asyncio
import json
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SERVER = StdioServerParameters(command=sys.executable, args=["-m", "mcp_server.server"])


def show(result) -> None:
    if result.isError:
        print("  TOOL ERROR:", result.content[0].text if result.content else result)
        return
    data = result.structuredContent or json.loads(result.content[0].text)
    data = data.get("result", data)  # FastMCP may wrap dict results
    print(json.dumps(data, indent=2, ensure_ascii=False)[:1500])


async def main(postcode: str) -> None:
    async with stdio_client(SERVER) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            print("Tools the server offers:")
            for t in tools.tools:
                print(f"  - {t.name}: {t.description.splitlines()[0]}")

            print("\n1) search_uk_guidance")
            show(await session.call_tool("search_uk_guidance", {
                "query": "Do full-time students pay council tax?", "k": 2}))

            print(f"\n2) lookup_postcode {postcode}")
            show(await session.call_tool("lookup_postcode", {"postcode": postcode}))

            print(f"\n3) find_nearby_services pharmacy near {postcode}")
            show(await session.call_tool("find_nearby_services", {
                "postcode": postcode, "service_type": "pharmacy", "limit": 3}))


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "SW1A 1AA"))
