"""End-to-end agent evaluation (uses your LLM API, roughly 10 questions per run).

Checks per question type:
- answerable   : called search_uk_guidance AND cited the expected GOV.UK page
- tool         : called the expected tool
- multi_tool   : called ALL expected tools
- should_defer : no definitive "yes"/"you can" AND answer refers to an adviser
- out_of_scope : made no tool calls and did not invent UK guidance links
Plus, for every answer: no unverified (invented) links.

Usage:
    python -m eval.eval_agent
"""

from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from agent.agent import UKNestAgent
from agent.guardrails import REFERRAL_HINTS
from agent.mcp_tools import MCPToolbox

QUESTIONS = Path("eval/agent_questions.json")
RESULTS = Path("eval/results_agent.json")
DEFINITIVE_YES = re.compile(r"^\s*(yes\b|yes,|you can\b|you are allowed)", re.I | re.M)


def grade(q: dict, r) -> dict:
    tools_used = [t["tool"] for t in r.trace]
    answer = r.answer.lower()
    checks = {"no_error": True, "no_invented_links": not r.guardrails.get("unsupported_urls")}

    if q["type"] == "answerable":
        checks["used_search"] = "search_uk_guidance" in tools_used
        checks["cited_expected"] = q["expected_url"] in r.answer
    elif q["type"] == "tool":
        checks["right_tool"] = all(t in tools_used for t in q["expected_tools"])
    elif q["type"] == "multi_tool":
        checks["all_tools"] = all(t in tools_used for t in q["expected_tools"])
    elif q["type"] == "should_defer":
        checks["no_definitive_yes"] = not DEFINITIVE_YES.search(r.answer)
        checks["refers_to_adviser"] = any(h in answer for h in REFERRAL_HINTS)
        checks["referral_by_model"] = not r.guardrails.get("referral_added")  # model did it itself
    elif q["type"] == "out_of_scope":
        checks["no_tools"] = not tools_used

    return {"id": q["id"], "type": q["type"], "question": q["question"],
            "tools_used": tools_used, "checks": checks, "passed": all(checks.values()),
            "seconds": r.seconds, "usage": r.usage, "answer": r.answer}


async def main() -> None:
    questions = json.loads(QUESTIONS.read_text())
    rows = []
    async with MCPToolbox() as toolbox:
        for q in questions:
            agent = UKNestAgent(toolbox)  # fresh conversation per question
            try:
                r = await agent.ask(q["question"])
            except Exception as exc:  # e.g. daily quota used up: record and continue
                print(f"⚠️  {q['id']} errored: {type(exc).__name__}: {str(exc)[:150]}")
                rows.append({"id": q["id"], "type": q["type"], "question": q["question"],
                             "tools_used": [], "checks": {"no_error": False}, "passed": False,
                             "seconds": 0, "usage": {}, "answer": ""})
                continue
            row = grade(q, r)
            rows.append(row)
            failed = [k for k, v in row["checks"].items() if not v]
            print(f"{'✅' if row['passed'] else '❌'} {q['id']} {q['type']:<13} "
                  f"tools={row['tools_used']} {('FAILED: ' + ', '.join(failed)) if failed else ''}")

    n = len(rows)
    by_type: dict[str, list] = {}
    for row in rows:
        by_type.setdefault(row["type"], []).append(row["passed"])
    tool_rows = [r for r in rows if r["type"] in ("answerable", "tool", "multi_tool")]
    tool_acc = sum(all(c for k, c in r["checks"].items()
                       if k in ("used_search", "right_tool", "all_tools")) for r in tool_rows)
    tokens_in = sum(r["usage"].get("input_tokens", 0) for r in rows)
    tokens_out = sum(r["usage"].get("output_tokens", 0) for r in rows)

    summary = {
        "run_at": datetime.now(timezone.utc).isoformat(),
        "pass_rate": round(sum(r["passed"] for r in rows) / n, 3),
        "tool_selection_accuracy": round(tool_acc / len(tool_rows), 3) if tool_rows else None,
        "citation_accuracy": round(
            sum(r["checks"].get("cited_expected", False) for r in rows if r["type"] == "answerable")
            / max(1, len(by_type.get("answerable", []))), 3),
        "safe_deferral_rate": round(
            sum(by_type.get("should_defer", [])) / max(1, len(by_type.get("should_defer", []))), 3),
        "invented_link_rate": round(
            sum(not r["checks"].get("no_invented_links", True) for r in rows) / n, 3),
        "avg_seconds": round(sum(r["seconds"] for r in rows) / n, 2),
        "tokens": {"input": tokens_in, "output": tokens_out},
        "rows": rows,
    }
    RESULTS.write_text(json.dumps(summary, indent=2, ensure_ascii=False))

    print(f"\nPass rate              {summary['pass_rate']:.2f}")
    print(f"Tool selection acc.    {summary['tool_selection_accuracy']:.2f}")
    print(f"Citation accuracy      {summary['citation_accuracy']:.2f}")
    print(f"Safe deferral rate     {summary['safe_deferral_rate']:.2f}")
    print(f"Invented-link rate     {summary['invented_link_rate']:.2f}")
    print(f"Avg latency            {summary['avg_seconds']}s   tokens in/out {tokens_in}/{tokens_out}")
    print(f"Saved to {RESULTS}")


if __name__ == "__main__":
    asyncio.run(main())
