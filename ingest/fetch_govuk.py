"""Fetch GOV.UK pages via the Content API and save clean text + metadata.

Usage:
    python -m ingest.fetch_govuk

Output:
    data/raw/govuk_docs.jsonl  - one JSON object per page, with sections kept
                                 separate so Day 2 chunking can respect them.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from ingest.sources import SOURCES

API_BASE = "https://www.gov.uk/api/content/"
SITE_BASE = "https://www.gov.uk/"
OUT_PATH = Path("data/raw/govuk_docs.jsonl")
HEADERS = {"User-Agent": "UKNest-AI-portfolio-project/0.1 (learning project)"}
DELAY_SECONDS = 0.5  # be polite to GOV.UK


def html_to_sections(html: str, default_heading: str) -> list[dict]:
    """Split GOV.UK body HTML into {heading, text} sections on h2/h3 tags."""
    soup = BeautifulSoup(html or "", "html.parser")
    sections: list[dict] = []
    heading = default_heading
    buffer: list[str] = []

    def flush() -> None:
        text = "\n".join(line for line in buffer if line).strip()
        if text:
            sections.append({"heading": heading, "text": text})

    for el in soup.find_all(["h2", "h3", "p", "li", "td", "th"]):
        if el.name in ("h2", "h3"):
            flush()
            heading = el.get_text(" ", strip=True)
            buffer = []
        elif el.name == "li" and el.find(["p", "ul", "ol"]):
            continue  # nested content is captured by the inner tags
        else:
            line = el.get_text(" ", strip=True)
            buffer.append(f"- {line}" if el.name == "li" else line)
    flush()
    return sections


def extract_sections(item: dict) -> list[dict]:
    """Handle the different GOV.UK document shapes."""
    details = item.get("details", {}) or {}
    title = item.get("title", "")

    # Multi-part guides (e.g. /council-tax) have details.parts
    if details.get("parts"):
        sections = []
        for part in details["parts"]:
            for sec in html_to_sections(part.get("body", ""), part.get("title", title)):
                # prefix the part title so context isn't lost
                if sec["heading"] != part.get("title"):
                    sec["heading"] = f"{part.get('title')} > {sec['heading']}"
                sections.append(sec)
        return sections

    # Simple pages, answers, transactions
    html = details.get("body") or details.get("introductory_paragraph") or ""
    sections = html_to_sections(html, title)

    # Some transaction pages keep extra info here
    for key in ("more_information", "other_ways_to_apply", "what_you_need_to_know"):
        if details.get(key):
            sections += html_to_sections(details[key], key.replace("_", " ").title())

    # Publications pages (e.g. how-to-rent) mostly link to attachments
    if not sections and item.get("description"):
        sections = [{"heading": title, "text": item["description"]}]
    return sections


def fetch_page(path: str) -> dict | None:
    resp = requests.get(API_BASE + path, headers=HEADERS, timeout=20)
    if resp.status_code != 200:
        print(f"  ! {path}: HTTP {resp.status_code}")
        return None
    return resp.json()


def main() -> None:
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    fetched_at = datetime.now(timezone.utc).isoformat()
    ok, failed = 0, []

    with OUT_PATH.open("w", encoding="utf-8") as f:
        for src in SOURCES:
            path = src["path"]
            print(f"Fetching {path} ...")
            item = fetch_page(path)
            time.sleep(DELAY_SECONDS)
            if item is None:
                failed.append(path)
                continue

            sections = extract_sections(item)
            if not sections:
                print(f"  ! {path}: no text extracted")
                failed.append(path)
                continue

            doc = {
                "doc_id": path.replace("/", "__"),
                "title": item.get("title"),
                "url": SITE_BASE + path,
                "source": "GOV.UK",
                "category": src["category"],
                "document_type": item.get("document_type"),
                "public_updated_at": item.get("public_updated_at"),
                "fetched_at": fetched_at,
                "licence": "Open Government Licence v3.0",
                "sections": sections,
            }
            f.write(json.dumps(doc, ensure_ascii=False) + "\n")
            words = sum(len(s["text"].split()) for s in sections)
            print(f"  ok: {len(sections)} sections, {words} words")
            ok += 1

    print(f"\nSaved {ok} docs to {OUT_PATH}")
    if failed:
        print("Failed (check paths on gov.uk):", ", ".join(failed))


if __name__ == "__main__":
    main()
