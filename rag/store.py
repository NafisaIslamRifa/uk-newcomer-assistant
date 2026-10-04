"""One place that decides how to connect to Qdrant.

- QDRANT_PATH set  -> embedded Qdrant (no server; data in a local folder)
- otherwise        -> Qdrant server at QDRANT_URL (Docker, or Qdrant Cloud with an API key)
"""

from __future__ import annotations

from functools import lru_cache

from qdrant_client import QdrantClient

from rag.config import QDRANT_API_KEY, QDRANT_PATH, QDRANT_URL


@lru_cache(maxsize=1)
def get_client() -> QdrantClient:
    if QDRANT_PATH:
        return QdrantClient(path=QDRANT_PATH)
    return QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)


def describe() -> str:
    return f"embedded at {QDRANT_PATH}" if QDRANT_PATH else QDRANT_URL
