"""Small pure functions used by the Streamlit app (easy to unit-test)."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

RAW_DOCS = Path("data/raw/govuk_docs.jsonl")

VISA_TYPES = ["Prefer not to say", "Student", "Graduate", "Skilled Worker",
              "Health and Care Worker", "Family", "Settled / pre-settled (EUSS)",
              "Ukraine / Hong Kong BN(O) scheme", "Other"]

QUICK_QUESTIONS = {
    "Renting a home": "What should I check before renting a flat, and does my deposit have to be protected?",
    "Proving right to work": "How do I prove my right to work to a new employer?",
    "eVisas and share codes": "What is an eVisa and how do I get a share code?",
    "Council tax": "Who has to pay council tax, and can students get a discount?",
    "GP and NHS care": "How do I register with a GP and do I have to pay to see a doctor?",
    "Services near me": "Find the nearest pharmacy and GP to my postcode.",
}


def knowledge_base_info(path: Path = RAW_DOCS) -> dict:
    """How many GOV.UK pages are indexed and when they were fetched."""
    if not path.exists():
        return {"pages": 0, "fetched": None}
    pages, fetched = 0, None
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        doc = json.loads(line)
        pages += 1
        fetched = max(filter(None, [fetched, doc.get("fetched_at")]), default=None)
    return {"pages": pages, "fetched": fetched}


def nice_date(iso: str | None) -> str:
    if not iso:
        return "unknown"
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).strftime("%-d %b %Y")
    except ValueError:
        return iso[:10]


def build_profile(visa: str, postcode: str) -> dict:
    return {
        "visa_type": None if visa in ("", "Prefer not to say") else visa,
        "postcode": postcode.strip().upper() or None,
    }


def describe_tool_call(step: dict) -> str:
    """One human-readable line for the 'How I answered' panel."""
    name, args = step["tool"], step["args"]
    if name == "search_uk_guidance":
        cat = f" in *{args['category'].replace('_', ' ')}*" if args.get("category") else ""
        text = f"Searched GOV.UK guidance{cat} for “{args.get('query', '')}”"
    elif name == "lookup_postcode":
        text = f"Looked up postcode **{args.get('postcode', '')}**"
    elif name == "find_nearby_services":
        kind = args.get("service_type", "services").replace("_", " ")
        text = f"Found nearby **{kind}** around {args.get('postcode', '')}"
    else:
        text = f"Called `{name}`"
    return text + (" (failed)" if step.get("error") else "")


def friendly_error(exc: Exception) -> str:
    name = type(exc).__name__
    if name == "RateLimitError":
        return ("The free AI quota is used up for the moment. Please wait a minute and "
                "try again (daily limits reset overnight).")
    if name in ("AuthenticationError", "PermissionDeniedError"):
        return "The AI service rejected the API key. Check `LLM_API_KEY` in `.env`."
    if name == "NotFoundError":
        return "The AI model wasn't found. Check `LLM_MODEL` in `.env`."
    if name in ("InternalServerError", "ServiceUnavailableError", "OverloadedError",
                "APITimeoutError", "APIConnectionError"):
        return ("The AI service is having a temporary problem on its side. "
                "Please try again in a minute.")
    if name == "TimeoutError":
        return "That took too long to answer. Please try again."
    return f"Something went wrong ({name}). Please try again."
