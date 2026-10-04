"""Deterministic guardrails that run in code, around the LLM.

The system prompt asks the model to behave; these checks make sure of it:
1. Before: flag personal immigration-eligibility questions so the model is
   reminded, at the moment it matters, not to give a yes/no.
2. After: every URL the model cites must have come from a tool result
   (catches invented citations), and high-risk answers must include a
   referral to proper advice.
"""

from __future__ import annotations

import re

HIGH_RISK_PATTERNS = [
    r"\b(can|could|am|may)\s+i\b.*\b(work|study|stay|travel|claim|switch|extend|bring)\b",
    r"\bmy (visa|brp|evisa|status|sponsor|cos|leave)\b",
    r"\b(hours?|overstay|overstayed|deport|deportation|asylum|refused|curtailed)\b.*\bvisa\b",
    r"\bvisa\b.*\b(hours?|allowed|permitted|illegal|overstay)\b",
]

REFERRAL_HINTS = ("oisc", "citizens advice", "immigration adviser", "immigration advisor")

REFERRAL_FOOTER = (
    "\n\n---\n*This is general information, not immigration advice. Your own conditions "
    "are shown in your eVisa / UKVI account. For advice about your situation, speak to an "
    "[OISC-regulated adviser](https://www.gov.uk/find-an-immigration-adviser) or "
    "[Citizens Advice](https://www.citizensadvice.org.uk/).*"
)

URL_RE = re.compile(r"https?://[^\s)\]>\"']+")


def is_high_risk(question: str) -> bool:
    q = question.lower()
    return any(re.search(p, q) for p in HIGH_RISK_PATTERNS)


def high_risk_reminder() -> str:
    return ("[Guardrail note: this is a personal immigration-eligibility question. "
            "Do not answer yes or no. Give the general guidance with citations and "
            "recommend checking their eVisa conditions and an OISC-regulated adviser.]")


def extract_urls(text: str) -> set[str]:
    return {u.rstrip(".,;:") for u in URL_RE.findall(text)}


ALWAYS_ALLOWED = {
    "https://www.gov.uk",
    "https://www.gov.uk/",
    "https://www.gov.uk/find-an-immigration-adviser",
    "https://www.citizensadvice.org.uk/",
    "https://www.citizensadvice.org.uk",
}


def check_answer(answer: str, question: str, allowed_urls: set[str]) -> dict:
    """Return the (possibly amended) answer plus a report of what was checked."""
    cited = extract_urls(answer)
    allowed = allowed_urls | ALWAYS_ALLOWED
    unsupported = sorted(u for u in cited if u not in allowed)

    report = {
        "high_risk": is_high_risk(question),
        "cited_urls": sorted(cited),
        "unsupported_urls": unsupported,
        "referral_added": False,
    }

    if unsupported:
        answer += ("\n\n> ⚠️ Some links above could not be verified against the "
                   "official sources this assistant searched. Please check them on GOV.UK.")

    if report["high_risk"] and not any(h in answer.lower() for h in REFERRAL_HINTS):
        answer += REFERRAL_FOOTER
        report["referral_added"] = True

    return {"answer": answer, "report": report}
