"""Split GOV.UK sections into retrieval-sized chunks.

Strategy:
- Never mix two sections in one chunk (keeps citations precise).
- Short sections become one chunk.
- Long sections are split on line boundaries into ~CHUNK_MAX_WORDS pieces,
  with CHUNK_OVERLAP_WORDS of overlap so a sentence at the edge isn't lost.
- Every chunk carries the page title + section heading in its text, so the
  embedding knows what the chunk is about even if the body is vague.
"""

from __future__ import annotations

import json
from pathlib import Path

from rag.config import CHUNK_MAX_WORDS, CHUNK_OVERLAP_WORDS, CHUNKS_PATH, RAW_DOCS_PATH


def split_text(text: str, max_words: int, overlap: int) -> list[str]:
    """Split text into pieces of at most ~max_words, breaking between lines."""
    lines = [ln for ln in text.split("\n") if ln.strip()]
    pieces: list[str] = []
    current: list[str] = []
    count = 0

    for line in lines:
        words = len(line.split())
        if current and count + words > max_words:
            pieces.append("\n".join(current))
            # carry the tail of the previous piece forward as overlap
            tail: list[str] = []
            tail_count = 0
            for prev in reversed(current):
                tail_count += len(prev.split())
                if tail_count > overlap:
                    break
                tail.insert(0, prev)
            current = tail
            count = sum(len(t.split()) for t in tail)
        current.append(line)
        count += words

    if current:
        pieces.append("\n".join(current))
    return pieces


def chunk_document(doc: dict) -> list[dict]:
    chunks = []
    for s_idx, section in enumerate(doc["sections"]):
        pieces = split_text(section["text"], CHUNK_MAX_WORDS, CHUNK_OVERLAP_WORDS)
        for p_idx, piece in enumerate(pieces):
            chunks.append({
                "chunk_id": f"{doc['doc_id']}::{s_idx}::{p_idx}",
                "doc_id": doc["doc_id"],
                "title": doc["title"],
                "heading": section["heading"],
                "url": doc["url"],
                "category": doc["category"],
                "source": doc["source"],
                "public_updated_at": doc.get("public_updated_at"),
                "fetched_at": doc.get("fetched_at"),
                # This is what gets embedded and shown to the LLM
                "text": f"{doc['title']} — {section['heading']}\n\n{piece}",
            })
    return chunks


def load_docs(path: str = RAW_DOCS_PATH) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def build_chunks() -> list[dict]:
    docs = load_docs()
    chunks = [c for d in docs for c in chunk_document(d)]

    Path(CHUNKS_PATH).parent.mkdir(parents=True, exist_ok=True)
    with open(CHUNKS_PATH, "w", encoding="utf-8") as f:
        for c in chunks:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")

    sizes = [len(c["text"].split()) for c in chunks]
    print(f"{len(docs)} docs -> {len(chunks)} chunks "
          f"(avg {sum(sizes) // max(len(sizes), 1)} words, max {max(sizes, default=0)})")
    return chunks


if __name__ == "__main__":
    build_chunks()
