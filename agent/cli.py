"""Chat with UKNest in the terminal.

Usage:
    python -m agent.cli                                   # interactive chat
    python -m agent.cli "Do students pay council tax?"    # one question
    python -m agent.cli --postcode "IG11 7LU" --visa Student

Type 'exit' to quit. Follow-up questions keep the conversation context.
"""

from __future__ import annotations

import argparse
import asyncio
import json

from agent.agent import UKNestAgent
from agent.mcp_tools import MCPToolbox


def print_result(r) -> None:
    for t in r.trace:
        flag = " (error)" if t["error"] else ""
        print(f"  🔧 step {t['step']}: {t['tool']}({json.dumps(t['args'], ensure_ascii=False)}){flag}")
    print("\n" + r.answer + "\n")
    g = r.guardrails
    notes = []
    if g.get("high_risk"):
        notes.append("high-risk question")
    if g.get("referral_added"):
        notes.append("adviser referral added")
    if g.get("unsupported_urls"):
        notes.append(f"unverified links: {g['unsupported_urls']}")
    print(f"  ⏱ {r.seconds}s · tokens in/out {r.usage.get('input_tokens', 0)}/"
          f"{r.usage.get('output_tokens', 0)} · sources {len(r.sources)}"
          + (f" · 🛡 {', '.join(notes)}" if notes else ""))


async def safe_ask(agent, question: str) -> None:
    """Ask, but show a friendly message instead of a crash on API problems."""
    try:
        print_result(await agent.ask(question))
    except Exception as exc:
        name = type(exc).__name__
        if name == "RateLimitError":
            print("\n⚠️  The LLM's free-tier limit was reached. Wait a minute and try again "
                  "(daily limits reset at midnight Pacific time).\n")
        elif name in ("AuthenticationError", "PermissionDeniedError"):
            print("\n⚠️  The API key was rejected. Check LLM_API_KEY in .env.\n")
        elif name == "NotFoundError":
            print(f"\n⚠️  Model not found. Check LLM_MODEL in .env. Details: {exc}\n")
        else:
            print(f"\n⚠️  Something went wrong ({name}): {exc}\n")


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("question", nargs="*")
    ap.add_argument("--postcode")
    ap.add_argument("--visa", help="e.g. Student, Skilled Worker")
    args = ap.parse_args()
    profile = {"postcode": args.postcode, "visa_type": args.visa}

    async with MCPToolbox() as toolbox:
        agent = UKNestAgent(toolbox, profile)
        print(f"UKNest ready · tools: {', '.join(t['name'] for t in toolbox.tools)}\n")

        if args.question:
            await safe_ask(agent, " ".join(args.question))
            return

        while True:
            try:
                q = input("You: ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if q.lower() in {"exit", "quit", ""}:
                break
            await safe_ask(agent, q)


if __name__ == "__main__":
    asyncio.run(main())
