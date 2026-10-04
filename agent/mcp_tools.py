"""Connects the agent to the UKNest MCP server.

The agent never imports the tools directly: it starts the MCP server,
asks it which tools exist, and calls them over the MCP protocol.
"""

from __future__ import annotations

import json
import os
import sys
from contextlib import AsyncExitStack

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


class MCPToolbox:
    """Usage:
        async with MCPToolbox() as toolbox:
            toolbox.tools                     # list of {name, description, input_schema}
            await toolbox.call(name, args)    # -> (text, is_error)
    """

    def __init__(self, server_url: str | None = None):
        # Day 6: set MCP_SERVER_URL to talk to the server in its own container
        self.server_url = server_url or os.getenv("MCP_SERVER_URL")
        self._stack = AsyncExitStack()
        self.session: ClientSession | None = None
        self.tools: list[dict] = []

    async def __aenter__(self) -> "MCPToolbox":
        if self.server_url:
            from mcp.client.streamable_http import streamablehttp_client
            read, write, _ = await self._stack.enter_async_context(
                streamablehttp_client(self.server_url))
        else:
            # Pass our environment on: hosts like Streamlit Cloud provide settings as
            # environment variables, and the SDK only forwards a few by default.
            params = StdioServerParameters(command=sys.executable,
                                           args=["-m", "mcp_server.server"],
                                           env=dict(os.environ))
            read, write = await self._stack.enter_async_context(stdio_client(params))
        self.session = await self._stack.enter_async_context(ClientSession(read, write))
        await self.session.initialize()
        listed = await self.session.list_tools()
        self.tools = [
            {"name": t.name, "description": t.description or "", "input_schema": t.inputSchema}
            for t in listed.tools
        ]
        return self

    async def __aexit__(self, *exc) -> None:
        await self._stack.aclose()

    async def call(self, name: str, args: dict) -> tuple[str, bool]:
        try:
            result = await self.session.call_tool(name, args)
        except Exception as exc:  # network issue, bad args...
            return json.dumps({"error": f"Tool call failed: {exc}"}), True
        if result.structuredContent is not None:
            data = result.structuredContent
            data = data.get("result", data) if isinstance(data, dict) else data
            text = json.dumps(data, ensure_ascii=False)
        else:
            text = "\n".join(getattr(c, "text", "") for c in result.content)
        return text, bool(result.isError)
