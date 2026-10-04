"""The agent loop: LLM decides -> tools run -> LLM answers -> guardrails check.

    question
       │
       ▼
  ┌─────────┐  tool calls   ┌──────────────┐
  │   LLM   │ ────────────▶ │  MCP server  │  search_uk_guidance /
  │         │ ◀──────────── │   (tools)    │  lookup_postcode / find_nearby_services
  └─────────┘  tool results └──────────────┘
       │ final text (repeat up to MAX_STEPS)
       ▼
  guardrails (citations verified, referral added if needed)
       │
       ▼
    answer + sources + trace
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field

from agent.guardrails import check_answer, extract_urls, high_risk_reminder, is_high_risk
from agent.llm import make_chat
from agent.mcp_tools import MCPToolbox
from agent.prompts import build_system_prompt

MAX_STEPS = 6  # max LLM turns per question, stops runaway tool loops


@dataclass
class AgentResult:
    answer: str
    sources: list[dict] = field(default_factory=list)
    trace: list[dict] = field(default_factory=list)
    guardrails: dict = field(default_factory=dict)
    usage: dict = field(default_factory=lambda: {"input_tokens": 0, "output_tokens": 0})
    seconds: float = 0.0


def _collect_sources(tool_name: str, text: str, sources: dict) -> None:
    """Remember every GOV.UK passage a tool returned, for citation checks + UI."""
    if tool_name != "search_uk_guidance":
        return
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return
    for r in data.get("results", []):
        key = (r["url"], r["section"])
        sources.setdefault(key, {"title": r["title"], "section": r["section"],
                                 "url": r["url"], "last_updated": r.get("last_updated")})


class UKNestAgent:
    """Holds one conversation. Reuse it for follow-up questions."""

    def __init__(self, toolbox: MCPToolbox, profile: dict | None = None, chat=None):
        self.toolbox = toolbox
        self.chat = chat or make_chat(build_system_prompt(profile))

    async def ask(self, question: str) -> AgentResult:
        start = time.time()
        result = AgentResult(answer="")
        sources: dict = {}
        tool_urls: set[str] = set()  # every URL any tool returned

        user_text = question
        if is_high_risk(question):
            user_text += "\n\n" + high_risk_reminder()
        self.chat.add_user(user_text)

        for step in range(1, MAX_STEPS + 1):
            reply = self.chat.complete(self.toolbox.tools)
            for k, v in reply.usage.items():
                result.usage[k] = result.usage.get(k, 0) + v

            if not reply.tool_calls:
                result.answer = reply.text.strip()
                break

            outputs = []
            for call in reply.tool_calls:
                text, is_err = await self.toolbox.call(call.name, call.args)
                _collect_sources(call.name, text, sources)
                tool_urls |= extract_urls(text)
                result.trace.append({"step": step, "tool": call.name, "args": call.args,
                                     "error": is_err, "result_preview": text[:300]})
                outputs.append((call, text, is_err))
            self.chat.add_tool_results(outputs)
        else:
            result.answer = ("Sorry, I could not finish answering that. Please try "
                             "rephrasing, or check https://www.gov.uk directly.")

        checked = check_answer(result.answer, question, tool_urls)
        result.answer = checked["answer"]
        result.guardrails = checked["report"]
        result.sources = list(sources.values())
        result.seconds = round(time.time() - start, 2)
        return result

