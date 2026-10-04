"""Agent tests with a scripted fake LLM and fake toolbox (no API key, no network)."""

import asyncio
import json

from agent.agent import UKNestAgent
from agent.guardrails import check_answer, is_high_risk
from agent.llm import Reply, ToolCall, _simplify_schema

SEARCH_RESULT = json.dumps({"results": [{
    "rank": 1, "title": "Council Tax", "section": "Discounts for full-time students",
    "url": "https://www.gov.uk/council-tax", "last_updated": "2026-03-12",
    "score": 0.8, "text": "Full-time students do not pay Council Tax."}]})


class FakeToolbox:
    tools = [{"name": "search_uk_guidance", "description": "x", "input_schema": {}}]

    def __init__(self):
        self.calls = []

    async def call(self, name, args):
        self.calls.append((name, args))
        return SEARCH_RESULT, False


class ScriptedChat:
    """Replays a fixed list of replies, like a recorded LLM."""
    def __init__(self, replies):
        self.replies, self.user, self.tool_results = list(replies), [], []

    def add_user(self, text):
        self.user.append(text)

    def complete(self, tools):
        return self.replies.pop(0)

    def add_tool_results(self, results):
        self.tool_results.extend(results)


def run(agent, q):
    return asyncio.run(agent.ask(q))


def test_tool_loop_and_sources():
    chat = ScriptedChat([
        Reply("", [ToolCall("1", "search_uk_guidance", {"query": "students council tax"})]),
        Reply("Full-time students don't pay. [Council Tax](https://www.gov.uk/council-tax) "
              "(updated 2026-03-12)"),
    ])
    box = FakeToolbox()
    r = run(UKNestAgent(box, chat=chat), "Do students pay council tax?")
    assert box.calls[0][0] == "search_uk_guidance"
    assert r.sources[0]["url"] == "https://www.gov.uk/council-tax"
    assert r.guardrails["unsupported_urls"] == []
    assert len(r.trace) == 1


def test_invented_link_is_flagged():
    chat = ScriptedChat([
        Reply("", [ToolCall("1", "search_uk_guidance", {"query": "x"})]),
        Reply("See https://www.gov.uk/made-up-page for details."),
    ])
    r = run(UKNestAgent(FakeToolbox(), chat=chat), "council tax?")
    assert r.guardrails["unsupported_urls"] == ["https://www.gov.uk/made-up-page"]
    assert "could not be verified" in r.answer


def test_high_risk_gets_reminder_and_referral():
    chat = ScriptedChat([Reply("Students usually have limits on working hours.")])
    r = run(UKNestAgent(FakeToolbox(), chat=chat), "Can I work 30 hours a week on my visa?")
    assert "Guardrail note" in chat.user[0]
    assert r.guardrails["referral_added"] and "OISC" in r.answer


def test_step_limit_stops_runaway_loop():
    looping = [Reply("", [ToolCall(str(i), "search_uk_guidance", {"query": "x"})]) for i in range(10)]
    r = run(UKNestAgent(FakeToolbox(), chat=ScriptedChat(looping)), "loop?")
    assert "could not finish" in r.answer


def test_is_high_risk():
    assert is_high_risk("Can I work full time on my student visa?")
    assert is_high_risk("my visa expires next month, what now")
    assert not is_high_risk("Do students pay council tax?")
    assert not is_high_risk("Find a pharmacy near E1 6AN")


def test_check_answer_allows_tool_urls():
    out = check_answer("[a](https://www.gov.uk/evisa).", "what is an evisa",
                       {"https://www.gov.uk/evisa"})
    assert out["report"]["unsupported_urls"] == []


def test_simplify_schema_removes_optional_wrapper():
    s = {"properties": {"c": {"anyOf": [{"enum": ["a"], "type": "string"}, {"type": "null"}],
                              "default": None, "title": "C"}}, "title": "X", "type": "object"}
    out = _simplify_schema(s)
    assert out["properties"]["c"] == {"enum": ["a"], "type": "string"}
    assert "title" not in out
