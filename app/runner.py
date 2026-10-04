"""Bridges Streamlit (synchronous, reruns on every click) and the agent
(asynchronous, keeps an MCP connection open).

One background thread runs an asyncio event loop forever. The MCP server is
started once on that loop and reused for every question, so each question
doesn't pay the cost of starting a server and loading the embedding model.
"""

from __future__ import annotations

import asyncio
import threading

from agent.agent import AgentResult, UKNestAgent
from agent.llm import make_chat
from agent.mcp_tools import MCPToolbox
from agent.prompts import build_system_prompt


class AgentRunner:
    def __init__(self, timeout: int = 300):
        self.timeout = timeout
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self.loop.run_forever, daemon=True)
        self.thread.start()
        self.toolbox = MCPToolbox()
        self._run(self.toolbox.__aenter__())

    def _run(self, coro):
        return asyncio.run_coroutine_threadsafe(coro, self.loop).result(self.timeout)

    @property
    def tool_names(self) -> list[str]:
        return [t["name"] for t in self.toolbox.tools]

    def new_chat(self, profile: dict | None):
        """A fresh conversation (LLM message history) for one browser session."""
        return make_chat(build_system_prompt(profile))

    def ask(self, chat, question: str) -> AgentResult:
        agent = UKNestAgent(self.toolbox, chat=chat)
        return self._run(agent.ask(question))
