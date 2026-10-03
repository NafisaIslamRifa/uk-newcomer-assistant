"""Semantic search over the GOV.UK chunks.

Usage:
    python -m rag.retriever "Do students pay council tax?"
"""

from __future__ import annotations

import sys

from qdrant_client import QdrantClient

from rag.config import COLLECTION, QDRANT_URL
from rag.embeddings import embed_query

_client: QdrantClient | None = None


def _get_client() -> QdrantClient:
    global _client
    if _client is None:
        _client = QdrantClient(url=QDRANT_URL)
    return _client


def retrieve(question: str, k: int = 5, client: QdrantClient | None = None,
             embed=embed_query) -> list[dict]:
    """Return the top-k chunks with their score and source metadata."""
    client = client or _get_client()
    result = client.query_points(
        collection_name=COLLECTION,
        query=embed(question),
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
