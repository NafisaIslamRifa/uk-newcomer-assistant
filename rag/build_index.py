"""Chunk -> embed -> load into Qdrant.

Usage:
    python -m rag.build_index

Safe to re-run: it rebuilds the collection from scratch each time.
"""

from __future__ import annotations

import time
import uuid

from qdrant_client import QdrantClient, models

from rag.chunking import build_chunks
from rag.config import COLLECTION, QDRANT_URL
from rag.embeddings import embed_passages

BATCH_SIZE = 64


def get_client() -> QdrantClient:
    return QdrantClient(url=QDRANT_URL)


def build_index(client: QdrantClient | None = None, embed=embed_passages) -> int:
    client = client or get_client()
    chunks = build_chunks()
    if not chunks:
        raise SystemExit("No chunks found. Run `python -m ingest.fetch_govuk` first.")

    start = time.time()
    print("Embedding chunks (first run downloads the model, ~1 min)...")
    vectors = embed([c["text"] for c in chunks])
    dim = len(vectors[0])
    print(f"  {len(vectors)} vectors, dimension {dim}, {time.time() - start:.1f}s")

    if client.collection_exists(COLLECTION):
        client.delete_collection(COLLECTION)
    client.create_collection(
        collection_name=COLLECTION,
        vectors_config=models.VectorParams(size=dim, distance=models.Distance.COSINE),
    )

    points = [
        models.PointStruct(
            # Qdrant needs int or UUID ids; derive a stable UUID from chunk_id
            id=str(uuid.uuid5(uuid.NAMESPACE_URL, c["chunk_id"])),
            vector=v,
            payload=c,
        )
        for c, v in zip(chunks, vectors)
    ]
    for i in range(0, len(points), BATCH_SIZE):
        client.upsert(collection_name=COLLECTION, points=points[i:i + BATCH_SIZE])

    count = client.count(COLLECTION).count
    print(f"Loaded {count} chunks into Qdrant collection '{COLLECTION}'")
    return count


if __name__ == "__main__":
    build_index()
