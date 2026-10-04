"""Semantic search over the GOV.UK chunks.

Usage:
    python -m rag.retriever "Do students pay council tax?"
"""

from __future__ import annotations

import sys

from qdrant_client import QdrantClient, models

from rag.config import COLLECTION
from rag.embeddings import embed_query
from rag.store import get_client as _get_client


def retrieve(question: str, k: int = 5, category: str | None = None,
             client: QdrantClient | None = None, embed=embed_query) -> list[dict]:
    """Return the top-k chunks with their score and source metadata.

    category: optional filter, e.g. "council_tax", to search one topic only.
    """
    client = client or _get_client()
    query_filter = None
    if category:
        query_filter = models.Filter(must=[
            models.FieldCondition(key="category", match=models.MatchValue(value=category))
        ])
    result = client.query_points(
        collection_name=COLLECTION,
        query=embed(question),
        query_filter=query_filter,
        limit=k,
        with_payload=True,
    )
    return [{"score": round(p.score, 3), **p.payload} for p in result.points]


def print_results(question: str, results: list[dict]) -> None:
    print(f"\nQ: {question}\n")
    for i, r in enumerate(results, 1):
        updated = (r.get("public_updated_at") or "")[:10]
        print(f"[{i}] score={r['score']}  {r['title']} > {r['heading']}")
        print(f"    {r['url']}  (updated {updated})")
        body = r["text"].split("\n\n", 1)[-1].replace("\n", " ")
        print(f"    {body[:200]}...\n")


if __name__ == "__main__":
    q = " ".join(sys.argv[1:]) or "Do full-time students pay council tax?"
    print_results(q, retrieve(q))
