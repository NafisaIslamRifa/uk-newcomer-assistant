"""One-off start-up job: make sure Qdrant has the GOV.UK index.

Runs as the `init` service in docker-compose before the MCP server and app start.
- Waits for Qdrant to accept connections.
- If the collection already has data, does nothing (fast restarts).
- Otherwise fetches GOV.UK pages (only if they're not already on disk) and
  builds the index.

Set FORCE_REINDEX=1 to rebuild anyway (e.g. after editing ingest/sources.py).

Usage:
    python -m scripts.bootstrap
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

from qdrant_client import QdrantClient

from rag.config import COLLECTION, QDRANT_PATH, QDRANT_URL, RAW_DOCS_PATH


def wait_for_qdrant(url: str, attempts: int = 30, delay: float = 2.0) -> QdrantClient:
    for i in range(1, attempts + 1):
        try:
            client = QdrantClient(url=url, timeout=5)
            client.get_collections()
            print(f"Qdrant is ready at {url}")
            return client
        except Exception as exc:  # not up yet
            print(f"Waiting for Qdrant ({i}/{attempts}): {type(exc).__name__}: {exc}")
            time.sleep(delay)
    sys.exit(f"Qdrant did not become ready at {url}")


def index_is_ready(client: QdrantClient) -> bool:
    if not client.collection_exists(COLLECTION):
        return False
    return client.count(COLLECTION).count > 0


def main(client: QdrantClient | None = None, fetch=None, build=None) -> str:
    if client is None:
        if QDRANT_PATH:  # embedded mode: nothing to wait for
            from rag.store import get_client
            client = get_client()
        else:
            client = wait_for_qdrant(QDRANT_URL)
    force = os.getenv("FORCE_REINDEX", "").lower() in ("1", "true", "yes")

    if index_is_ready(client) and not force:
        n = client.count(COLLECTION).count
        print(f"Index '{COLLECTION}' already has {n} chunks. Nothing to do.")
        return "skipped"

    if not Path(RAW_DOCS_PATH).exists():
        print("No GOV.UK data on disk yet, fetching it...")
        if fetch is None:
            from ingest.fetch_govuk import main as fetch
        fetch()

    print("Building the search index...")
    if build is None:
        from rag.build_index import build_index as build
    build(client=client)
    return "built"


if __name__ == "__main__":
    main()
